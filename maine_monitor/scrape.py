"""Assemble a complete ``Bill`` record by combining the PS and LawMakerWeb pages.

``build_bill`` fetches every view for one LD and merges it. ``scrape_session``
enumerates a whole session and yields finished records, with optional
incremental skipping driven by a caller-supplied "fingerprint" of prior state.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import lawmaker, ps_parser
from .directory import DirectoryEntry
from .http import Fetcher
from .models import Bill


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fingerprint(bill: Bill) -> str:
    """Cheap change signal from the PS + summary pages.

    Captures the fields that move when a bill sees activity, so the daily run
    can skip the deep scrape for dormant bills.
    """
    return "|".join([
        bill.final_disposition,
        bill.governor_action,
        bill.chaptered_law,
        bill.last_house_action,
        bill.last_senate_action,
    ])


def build_head(fetcher: Fetcher, entry: DirectoryEntry) -> Bill:
    """Fetch only the two cheap pages (PS + LawMakerWeb summary).

    This is enough to identify the bill, get its disposition/status, and compute
    a fingerprint. The deep sub-pages are filled in by ``build_detail``.
    """
    bill = Bill(
        ld=entry.ld,
        paper=entry.paper,
        paper_display=entry.paper_display,
        origin_chamber=entry.chamber,
        snum=entry.snum,
        title=entry.title,
        ps_url=entry.ps_url,
        scraped_at=_now_iso(),
    )

    ps = ps_parser.parse_ps(fetcher.get(entry.ps_url))
    bill.session_id = ps["session_id"]
    bill.final_disposition = ps["final_disposition"]
    bill.governor_action = ps["governor_action"]
    bill.chaptered_law = ps["chaptered_law"]
    bill.chapter = ps["chapter"]
    bill.became_law = ps["became_law"]
    bill.documents = ps["documents"]

    if bill.session_id is None:
        return bill  # PS-only record (rare); no LawMakerWeb link.

    bill.lawmaker_summary_url = lawmaker.summary_url(entry.paper, bill.session_id)
    summary = lawmaker.parse_summary(fetcher.get(bill.lawmaker_summary_url))
    bill.lawmaker_id = summary["lawmaker_id"]
    bill.committee = summary["committee"]
    bill.last_house_action = summary["last_house_action"]
    bill.last_senate_action = summary["last_senate_action"]
    return bill


def build_detail(
    fetcher: Fetcher,
    bill: Bill,
    *,
    include_member_votes: bool = True,
) -> Bill:
    """Fill in the deep sub-pages on a bill already populated by ``build_head``."""
    lid = bill.lawmaker_id
    if not lid:
        return bill

    bill.actions = lawmaker.parse_actions(
        fetcher.get(lawmaker._sub_url("dockets.asp", lid))
    )
    bill.sponsors = lawmaker.parse_sponsors(
        fetcher.get(lawmaker._sub_url("sponsors.asp", lid))
    )
    bill.subjects = lawmaker.parse_subjects(
        fetcher.get(lawmaker._sub_url("subjects.asp", lid))
    )
    bill.amendments = lawmaker.parse_amendments(
        fetcher.get(lawmaker._sub_url("amendments.asp", lid))
    )

    # 7. Roll calls (+ optional per-member detail).
    bill.roll_calls = lawmaker.parse_rollcall_index(
        fetcher.get(lawmaker._sub_url("rollcalls.asp", lid))
    )
    if include_member_votes:
        for rc in bill.roll_calls:
            lawmaker.fetch_member_votes(fetcher, rc)

    return bill


def build_bill(
    fetcher: Fetcher,
    entry: DirectoryEntry,
    *,
    include_member_votes: bool = True,
) -> Bill:
    """Fetch a complete bill record (head + all deep sub-pages)."""
    bill = build_head(fetcher, entry)
    return build_detail(fetcher, bill, include_member_votes=include_member_votes)
