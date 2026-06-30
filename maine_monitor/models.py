"""Normalized data model for a Maine bill (LD).

Plain dataclasses so the whole record serializes cleanly to JSON and flattens to
CSV. Everything is keyed on the LD number; chambers (House/Senate) are tracked
on actions, roll-calls, and sponsors rather than split into separate records.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Sponsor:
    name: str
    role: str            # "Sponsor", "Cosponsor"
    chamber: str = ""    # "House", "Senate"
    title: str = ""      # "Representative", "Senator", "Speaker", "President"
    district: str = ""   # town/county, e.g. "Falmouth"


@dataclass
class Action:
    date: str            # ISO yyyy-mm-dd when parseable, else raw
    date_raw: str
    chamber: str         # "House", "Senate", or ""
    description: str


@dataclass
class MemberVote:
    member: str
    party: str           # "D", "R", "I", ...
    vote: str            # "Y", "N", "X" (absent), "E" (excused)


@dataclass
class RollCall:
    chamber: str         # "House" or "Senate"
    number: str          # serial number, e.g. "739"
    date: str
    date_raw: str
    motion: str
    outcome: str
    yeas: Optional[int]
    nays: Optional[int]
    absent: Optional[int] = None
    excused: Optional[int] = None
    vacant: Optional[int] = None
    yeas_required: Optional[int] = None
    members: List[MemberVote] = field(default_factory=list)
    url: str = ""


@dataclass
class Amendment:
    label: str             # e.g. 'C "A" (H-716)'
    new_title: str = ""    # replacement title, if the amendment changes it
    house_action: str = ""
    senate_action: str = ""
    adopted: bool = False
    pdf_url: str = ""


@dataclass
class Subject:
    major: str = ""
    minor: str = ""
    detail: str = ""


@dataclass
class Document:
    kind: str            # "bill_text", "amendment", "fiscal_note"
    label: str
    url: str


@dataclass
class Bill:
    # Identity
    ld: int
    paper: str                       # "HP1220"
    paper_display: str               # "HP 1220"
    origin_chamber: str              # "House" / "Senate" / "Initiative"
    snum: int                        # Legislature number (PS), e.g. 132
    session_id: Optional[int] = None  # LawMakerWeb SessionID
    lawmaker_id: Optional[str] = None  # LawMakerWeb internal ID

    # Descriptive
    title: str = ""
    committee: str = ""              # reference committee
    status_summary: str = ""
    final_disposition: str = ""      # e.g. "Emergency Enacted, Apr 22, 2025"
    governor_action: str = ""        # e.g. "Emergency Signed, Apr 22, 2025"
    chaptered_law: str = ""          # e.g. "ACTPUB, Chapter 33"
    chapter: str = ""                # e.g. "33"
    became_law: bool = False
    last_house_action: str = ""
    last_senate_action: str = ""

    # Collections
    sponsors: List[Sponsor] = field(default_factory=list)
    subjects: List[Subject] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    roll_calls: List[RollCall] = field(default_factory=list)
    amendments: List[Amendment] = field(default_factory=list)
    documents: List[Document] = field(default_factory=list)

    # Provenance
    ps_url: str = ""
    lawmaker_summary_url: str = ""
    scraped_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Bill":
        """Rebuild a Bill (and its nested records) from a stored JSON dict."""
        d = dict(data)
        d["sponsors"] = [Sponsor(**s) for s in d.get("sponsors", [])]
        d["subjects"] = [Subject(**s) for s in d.get("subjects", [])]
        d["actions"] = [Action(**a) for a in d.get("actions", [])]
        d["amendments"] = [Amendment(**a) for a in d.get("amendments", [])]
        d["documents"] = [Document(**x) for x in d.get("documents", [])]
        roll_calls = []
        for rc in d.get("roll_calls", []):
            rc = dict(rc)
            rc["members"] = [MemberVote(**m) for m in rc.get("members", [])]
            roll_calls.append(RollCall(**rc))
        d["roll_calls"] = roll_calls
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
