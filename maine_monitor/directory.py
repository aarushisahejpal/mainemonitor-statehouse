"""Enumerate every bill (LD) in a session from the PS bill directory.

The directory pages 200 LDs at a time via ``ldFrom`` (1, 201, 401, ...). Each
result row carries the LD number, paper number (HP/SP + origin chamber), and
title. Paging stops when a request returns no rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from bs4 import BeautifulSoup

from . import config
from .http import Fetcher

_NUMBERS_RE = re.compile(r"LD\s+(\d+),\s*([A-Z]{2})\s+(\d+)")


@dataclass
class DirectoryEntry:
    ld: int
    paper: str          # zero-padded, e.g. "SP0029"
    paper_display: str  # human form, e.g. "SP 29"
    chamber: str        # "House" or "Senate" (origin chamber of the paper)
    title: str
    snum: int

    @property
    def ps_url(self) -> str:
        return (
            f"{config.PS_BASE}/display_ps.asp"
            f"?snum={self.snum}&paper={self.paper}"
        )


# HP = House paper, SP = Senate paper, IB = citizen-initiated bill (ballot initiative).
_CHAMBER_BY_PREFIX = {"HP": "House", "SP": "Senate", "IB": "Initiative"}


def _directory_url(snum: int, ld_from: int) -> str:
    return f"{config.PS_BASE}/billdirectory_ps.asp?snum={snum}&ldFrom={ld_from}"


def _parse_page(html: str, snum: int) -> List[DirectoryEntry]:
    soup = BeautifulSoup(html, "lxml")
    entries: List[DirectoryEntry] = []
    for row in soup.select("table#search-results tr"):
        numbers = row.find("td", class_="RecordNumbers")
        title = row.find("td", class_="RecordTitle")
        if not numbers or not title:
            continue
        match = _NUMBERS_RE.search(numbers.get_text(" ", strip=True))
        if not match:
            continue
        ld = int(match.group(1))
        prefix = match.group(2)
        number = int(match.group(3))
        paper = f"{prefix}{number:04d}"
        entries.append(
            DirectoryEntry(
                ld=ld,
                paper=paper,
                paper_display=f"{prefix} {number}",
                chamber=_CHAMBER_BY_PREFIX.get(prefix, prefix),
                title=title.get_text(" ", strip=True),
                snum=snum,
            )
        )
    return entries


def list_bills(
    fetcher: Fetcher,
    snum: int = config.DEFAULT_SNUM,
    *,
    max_pages: int = 50,
) -> List[DirectoryEntry]:
    """Return every bill in ``snum``, ordered by LD number."""
    by_paper: dict = {}
    ld_from = 1
    for _ in range(max_pages):
        html = fetcher.get(_directory_url(snum, ld_from), use_cache=False)
        page = _parse_page(html, snum)
        if not page:
            break
        for entry in page:
            by_paper[entry.paper] = entry
        ld_from += config.DIRECTORY_PAGE_SIZE
    return sorted(by_paper.values(), key=lambda e: e.ld)
