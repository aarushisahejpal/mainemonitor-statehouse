"""Small shared parsing helpers."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_DATE_FORMATS = (
    "%m/%d/%Y",        # 4/29/2025
    "%B %d, %Y",       # March 5, 2026
    "%b %d, %Y",       # Apr 13, 2026
    "%b. %d, %Y",      # Feb. 10, 2026
)


def to_iso_date(raw: str) -> str:
    """Best-effort conversion of Maine's date strings to ISO ``yyyy-mm-dd``.

    Returns "" when nothing parseable is found (caller keeps the raw string).
    """
    if not raw:
        return ""
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    # Try to pull a date substring out of a longer string.
    match = re.search(r"[A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}", text)
    if match:
        return to_iso_date(match.group(0))
    return ""


def to_int(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    match = re.search(r"-?\d+", raw.replace(",", ""))
    return int(match.group(0)) if match else None


def clean(text: str) -> str:
    """Collapse whitespace and strip non-breaking spaces."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
