"""Append-only log of bill status changes, run over run.

Each scrape compares a bill against its stored version and appends one row per
changed field to ``data/changes.csv``. Git already records *that* something
changed; this records *what* changed in a flat, queryable form — useful for
"what moved this week" reporting.

The first run (no stored data) writes no rows; it just establishes the baseline.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Optional

from .models import Bill

CHANGES_HEADER = ["detected_at", "ld", "paper", "field", "old", "new"]

# (attribute, label) pairs whose movement is worth logging.
_TRACKED = [
    ("final_disposition", "disposition"),
    ("governor_action", "governor_action"),
    ("chaptered_law", "chaptered_law"),
    ("last_house_action", "last_house_action"),
    ("last_senate_action", "last_senate_action"),
]


def detect_changes(prior: Optional[Bill], new: Bill, detected_at: str) -> List[list]:
    rows: List[list] = []

    if prior is None:
        rows.append([detected_at, new.ld, new.paper, "added", "", new.title])
        return rows

    for attr, label in _TRACKED:
        old, now = getattr(prior, attr), getattr(new, attr)
        if old != now:
            rows.append([detected_at, new.ld, new.paper, label, old, now])

    if not prior.became_law and new.became_law:
        rows.append([detected_at, new.ld, new.paper, "became_law", "False", "True"])

    if len(new.actions) != len(prior.actions):
        rows.append([detected_at, new.ld, new.paper, "action_count",
                     len(prior.actions), len(new.actions)])

    return rows


def append_changes(path: Path, rows: List[list]) -> None:
    if not rows:
        return
    path = Path(path)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(CHANGES_HEADER)
        writer.writerows(rows)
