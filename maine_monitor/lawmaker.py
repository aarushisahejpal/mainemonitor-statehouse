"""Parsers for the LawMakerWeb tracking system.

Each bill has an internal numeric ID in LawMakerWeb. The summary page
(summary.asp?paper=<paper>&SessionID=<id>) carries that ID and the status
summary; the structured sub-pages hang off the ID:

    dockets.asp?ID=    -> chronological actions (House + Senate)
    sponsors.asp?ID=   -> sponsors / cosponsors
    subjects.asp?ID=   -> subject taxonomy
    rollcalls.asp?ID=  -> roll-call index (links into per-member detail)
    rollcall.asp?ID=&chamber=&serialnumber=  -> per-member votes
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from . import config
from .http import Fetcher
from .models import Action, Amendment, MemberVote, RollCall, Sponsor, Subject
from .parse_utils import clean, to_int, to_iso_date


def summary_url(paper: str, session_id: int) -> str:
    return f"{config.LAWMAKER_BASE}/summary.asp?paper={paper}&SessionID={session_id}"


def _sub_url(name: str, lawmaker_id: str) -> str:
    return f"{config.LAWMAKER_BASE}/{name}?ID={lawmaker_id}"


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #

def parse_summary(html: str) -> dict:
    """Return ``{lawmaker_id, committee, status_summary, last_house_action,
    last_senate_action}`` from a summary page."""
    soup = BeautifulSoup(html, "lxml")

    lawmaker_id = None
    for a in soup.find_all("a", href=True):
        m = re.search(r"(?:dockets|sponsors|rollcalls|subjects)\.asp\?ID=(\d+)", a["href"])
        if m:
            lawmaker_id = m.group(1)
            break

    text = clean(soup.get_text(" "))

    def _between(label: str, *stop_labels: str) -> str:
        idx = text.find(label)
        if idx < 0:
            return ""
        start = idx + len(label)
        end = len(text)
        for stop in stop_labels:
            s = text.find(stop, start)
            if 0 <= s < end:
                end = s
        return text[start:end].strip(" -:")

    committee = _between(
        "Reference Committee",
        "Last House Action",
        "Last Senate Action",
        "Last Engrossed",
        "Related Links",
    )
    last_house = _between(
        "Last House Action",
        "Last Senate Action",
        "Last Engrossed",
        "Related Links",
    )
    last_senate = _between(
        "Last Senate Action",
        "Last Engrossed",
        "Related Links",
    )

    return {
        "lawmaker_id": lawmaker_id,
        "committee": committee,
        "last_house_action": last_house,
        "last_senate_action": last_senate,
    }


# --------------------------------------------------------------------------- #
# Actions (dockets)
# --------------------------------------------------------------------------- #

def parse_actions(html: str) -> List[Action]:
    soup = BeautifulSoup(html, "lxml")
    actions: List[Action] = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td", class_="sectionbody")
        if len(cells) < 3:
            continue
        date_raw = clean(cells[0].get_text(" "))
        chamber = clean(cells[1].get_text(" "))
        # Preserve line breaks in the action description.
        for br in cells[2].find_all("br"):
            br.replace_with("\n")
        description = clean(cells[2].get_text(" ")).replace(" \n ", " ")
        if not (date_raw or description):
            continue
        actions.append(
            Action(
                date=to_iso_date(date_raw),
                date_raw=date_raw,
                chamber=chamber if chamber in ("House", "Senate") else "",
                description=description,
            )
        )
    return actions


# --------------------------------------------------------------------------- #
# Sponsors
# --------------------------------------------------------------------------- #

_SPONSOR_RE = re.compile(
    r"(Representative|Senator|Speaker|President)\s+"
    r"([A-Z][\w.'-]*(?:\s+[\w.'-]+)*?)\s+of\s+"
    r"([A-Z][A-Za-z .'-]+?)(?=\s+(?:Representative|Senator|Speaker|President)\b|$)"
)


def parse_sponsors(html: str) -> List[Sponsor]:
    soup = BeautifulSoup(html, "lxml")
    # Scope to the "Sponsors and Cosponsors" block so nav links are excluded.
    text = clean(soup.get_text(" "))
    start = text.find("Sponsored By")
    end = text.find("Related Links", start if start >= 0 else 0)
    block = text[start if start >= 0 else 0 : end if end > 0 else len(text)]

    co_idx = block.find("Cosponsored By")
    if co_idx >= 0:
        segments = [("Sponsor", block[:co_idx]), ("Cosponsor", block[co_idx:])]
    else:
        segments = [("Sponsor", block)]

    sponsors: List[Sponsor] = []
    for role, segment in segments:
        for m in _SPONSOR_RE.finditer(segment):
            title = m.group(1)
            chamber = "Senate" if title in ("Senator", "President") else "House"
            sponsors.append(
                Sponsor(
                    name=clean(m.group(2)),
                    role=role,
                    chamber=chamber,
                    title=title,
                    district=clean(m.group(3)),
                )
            )
    return sponsors


# --------------------------------------------------------------------------- #
# Subjects
# --------------------------------------------------------------------------- #

def _data_table(soup: BeautifulSoup, header_text: str):
    """Return the smallest table containing ``header_text``.

    The LawMakerWeb layout nests data tables inside navigation tables, so the
    table we want is the innermost (smallest) one carrying the header — picking
    by text length reliably skips the enclosing layout/nav tables.
    """
    candidates = [t for t in soup.find_all("table") if header_text in t.get_text()]
    if not candidates:
        return None
    return min(candidates, key=lambda t: len(t.get_text()))


def parse_subjects(html: str) -> List[Subject]:
    soup = BeautifulSoup(html, "lxml")
    subjects: List[Subject] = []
    table = _data_table(soup, "Major Subject")
    if not table:
        return subjects
    for row in table.find_all("tr"):
        cells = [clean(c.get_text(" ")) for c in row.find_all("td")]
        cells = [c for c in cells if c]
        if not cells or any("Major Subject" in c for c in cells):
            continue
        major = cells[0] if len(cells) > 0 else ""
        minor = cells[1] if len(cells) > 1 else ""
        detail = cells[2] if len(cells) > 2 else ""
        if major or minor or detail:
            subjects.append(Subject(major=major, minor=minor, detail=detail))
    return subjects


# --------------------------------------------------------------------------- #
# Amendments
# --------------------------------------------------------------------------- #

# Amendment labels look like: C "A" (H-716), H "A" (H-788) to C "A" (H-716).
_AMENDMENT_LABEL = re.compile(r'^[A-Z]\s*"[A-Z]"\s*\(')


def parse_amendments(html: str) -> List[Amendment]:
    soup = BeautifulSoup(html, "lxml")
    table = _data_table(soup, "New Title")
    amendments: List[Amendment] = []
    if not table:
        return amendments
    for row in table.find_all("tr"):
        cells = [clean(c.get_text(" ")) for c in row.find_all("td")]
        if not cells or not _AMENDMENT_LABEL.match(cells[0]):
            continue
        label = cells[0]
        new_title = cells[2] if len(cells) > 2 else ""
        house_action = cells[3] if len(cells) > 3 else ""
        senate_action = cells[4] if len(cells) > 4 else ""
        adopted = "Adopted" in (house_action + senate_action)
        amendments.append(
            Amendment(
                label=label,
                new_title=new_title,
                house_action=house_action,
                senate_action=senate_action,
                adopted=adopted,
            )
        )
    return amendments


# --------------------------------------------------------------------------- #
# Roll calls
# --------------------------------------------------------------------------- #

_RC_HREF = re.compile(
    r"rollcall\.asp\?ID=(\d+)&chamber=(House|Senate)&serialnumber=(\d+)"
)


def parse_rollcall_index(html: str) -> List[RollCall]:
    """Parse the roll-call list page into ``RollCall`` records (no members yet)."""
    soup = BeautifulSoup(html, "lxml")
    roll_calls: List[RollCall] = []
    for row in soup.find_all("tr"):
        link = row.find("a", href=_RC_HREF)
        if not link:
            continue
        href = link["href"]
        m = _RC_HREF.search(href)
        cells = [clean(c.get_text(" ")) for c in row.find_all("td")]
        cells = [c for c in cells if c]
        # cells: [RC #739, March 5, 2026, MOTION, OUTCOME, yeas, nays]
        date_raw = cells[1] if len(cells) > 1 else ""
        motion = cells[2] if len(cells) > 2 else ""
        outcome = cells[3] if len(cells) > 3 else ""
        yeas = to_int(cells[4]) if len(cells) > 4 else None
        nays = to_int(cells[5]) if len(cells) > 5 else None
        roll_calls.append(
            RollCall(
                chamber=m.group(2),
                number=m.group(3),
                date=to_iso_date(date_raw),
                date_raw=date_raw,
                motion=motion,
                outcome=outcome,
                yeas=yeas,
                nays=nays,
                url=f"{config.LAWMAKER_BASE}/{href.lstrip('/')}",
            )
        )
    return roll_calls


def parse_rollcall_detail(html: str) -> Tuple[dict, List[MemberVote]]:
    """Parse a per-roll-call detail page: overview counts + member votes."""
    soup = BeautifulSoup(html, "lxml")
    text = clean(soup.get_text(" "))

    def _field(label: str) -> Optional[str]:
        m = re.search(re.escape(label) + r"\s*:?\s*([0-9]+)", text)
        return m.group(1) if m else None

    overview = {
        "yeas": to_int(_field("Yeas (Y)")),
        "nays": to_int(_field("Nays (N)")),
        "absent": to_int(_field("Absent (X)")),
        "excused": to_int(_field("Excused (E)")),
        "vacant": to_int(_field("Vacant")),
        "yeas_required": to_int(_field("Number of Yeas Required")),
    }

    members: List[MemberVote] = []
    table = None
    for t in soup.find_all("table"):
        header = t.get_text(" ")
        if "Member" in header and "Party" in header and "Vote" in header:
            table = t
            break
    if table:
        for row in table.find_all("tr"):
            cells = [clean(c.get_text(" ")) for c in row.find_all("td")]
            cells = [c for c in cells if c]
            if len(cells) < 3:
                continue
            if cells[0].startswith("Member"):
                continue
            member, party, vote = cells[-3], cells[-2], cells[-1]
            if vote in ("Y", "N", "X", "E"):
                members.append(MemberVote(member=member, party=party, vote=vote))
    return overview, members


# --------------------------------------------------------------------------- #
# Orchestration helper
# --------------------------------------------------------------------------- #

def fetch_member_votes(fetcher: Fetcher, roll_call: RollCall) -> None:
    """Populate a roll-call's overview counts and member list in place."""
    html = fetcher.get(roll_call.url)
    overview, members = parse_rollcall_detail(html)
    roll_call.absent = overview["absent"]
    roll_call.excused = overview["excused"]
    roll_call.vacant = overview["vacant"]
    roll_call.yeas_required = overview["yeas_required"]
    if overview["yeas"] is not None:
        roll_call.yeas = overview["yeas"]
    if overview["nays"] is not None:
        roll_call.nays = overview["nays"]
    roll_call.members = members
