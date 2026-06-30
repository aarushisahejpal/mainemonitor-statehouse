"""Integrity checks that catch a bad parse before it's trusted.

Each looks for a way the scrape could silently disagree with the source: vote
tallies that don't reconcile, a bill that reached LawMakerWeb but came back
empty, an active bill with no actions, an enacted bill with no chapter.
"""

from __future__ import annotations

from typing import List, Sequence

from .models import Bill


def check_bill(bill: Bill) -> List[str]:
    issues: List[str] = []
    tag = f"LD {bill.ld} ({bill.paper})"

    if not bill.title:
        issues.append(f"{tag}: empty title")

    # Reached LawMakerWeb but no internal id -> tracking pages were missed.
    if bill.session_id is not None and not bill.lawmaker_id:
        issues.append(f"{tag}: has SessionID but no LawMakerWeb id")

    # An active bill with zero actions usually means a docket parse failure.
    settled = bill.became_law or bool(bill.final_disposition)
    if bill.lawmaker_id and not bill.actions and not settled:
        issues.append(f"{tag}: active bill with no actions")

    # Enacted bills should carry a chapter number.
    if bill.became_law and not bill.chapter:
        issues.append(f"{tag}: marked enacted but no chapter number")

    for rc in bill.roll_calls:
        if not rc.members:
            continue
        counts = {"Y": 0, "N": 0, "X": 0, "E": 0}
        for m in rc.members:
            if m.vote in counts:
                counts[m.vote] += 1
        if rc.yeas is not None and counts["Y"] != rc.yeas:
            issues.append(
                f"{tag} RC {rc.chamber} #{rc.number}: "
                f"counted {counts['Y']} yeas, header says {rc.yeas}"
            )
        if rc.nays is not None and counts["N"] != rc.nays:
            issues.append(
                f"{tag} RC {rc.chamber} #{rc.number}: "
                f"counted {counts['N']} nays, header says {rc.nays}"
            )
    return issues


def check_integrity(bills: Sequence[Bill], expected: int = None) -> List[str]:
    issues: List[str] = []
    if expected is not None and len(bills) != expected:
        issues.append(f"expected {expected} bills, wrote {len(bills)}")
    for bill in bills:
        issues.extend(check_bill(bill))
    return issues
