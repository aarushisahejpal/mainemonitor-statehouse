"""Parser for the PS bill page (display_ps.asp).

The canonical document record. Three things here that LawMakerWeb doesn't give:
the LawMakerWeb SessionID (needed to reach the tracking pages), the final
disposition and date, and links to every printed PDF (bill text, amendments,
fiscal notes).
"""

from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup

from . import config
from .models import Document
from .parse_utils import clean

_SESSION_ID_RE = re.compile(r"summary\.asp\?paper=[A-Z0-9]+&SessionID=(\d+)", re.I)
_GETPDF_RE = re.compile(r"getPDF\.asp\?[^\"'\s>]+", re.I)


def _abs(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    return f"{config.PS_BASE}/{url.lstrip('/')}"


def parse_ps(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    session_id: Optional[int] = None
    m = _SESSION_ID_RE.search(html)
    if m:
        session_id = int(m.group(1))

    # Disposition fields live in the sec0 "Documents and Disposition" block.
    sec0 = soup.find(id="sec0")
    scope = clean(sec0.get_text(" ") if sec0 else soup.get_text(" "))
    disposition = _parse_disposition(scope)

    return {
        "session_id": session_id,
        "documents": _parse_documents(soup),
        **disposition,
    }


# Markers that end a labeled field within the disposition block.
_DISPO_STOPS = (
    "Governor's Action",
    "Chaptered Law",
    "Printed Chapter PDF",
    "Need a paper copy",
    "These are unofficial",
)


def _field_between(text: str, label: str) -> str:
    idx = text.find(label)
    if idx < 0:
        return ""
    start = idx + len(label)
    end = len(text)
    for stop in _DISPO_STOPS:
        s = text.find(stop, start)
        if 0 <= s < end:
            end = s
    return text[start:end].strip(" -:.,")


def _parse_disposition(scope: str) -> dict:
    final_disposition = _field_between(scope, "Final Disposition")
    governor_action = _field_between(scope, "Governor's Action")

    chaptered_law = ""
    chapter = ""
    ch = re.search(r"Chaptered Law\s+([A-Z]+)\s*,\s*Chapter\s+(\w+)", scope)
    if ch:
        chaptered_law = f"{ch.group(1)}, Chapter {ch.group(2)}"
        chapter = ch.group(2)

    became_law = bool(
        chaptered_law
        or re.search(r"\b(Enacted|Finally Passed|Signed|Became Law|Chaptered)\b",
                     final_disposition + " " + governor_action)
    )

    return {
        "final_disposition": final_disposition,
        "governor_action": governor_action,
        "chaptered_law": chaptered_law,
        "chapter": chapter,
        "became_law": became_law,
    }


def _parse_documents(soup: BeautifulSoup) -> List[Document]:
    documents: List[Document] = []
    seen = set()
    for a in soup.find_all("a", href=_GETPDF_RE):
        href = a["href"]
        url = _abs(href)
        if url in seen:
            continue
        seen.add(url)
        label = clean(a.get_text(" ")) or "PDF"

        # Classify by item number and surrounding context.
        item = re.search(r"item=(\d+)", href)
        item_no = int(item.group(1)) if item else None
        context = clean(a.find_parent().get_text(" ")) if a.find_parent() else ""
        lower = context.lower()
        if "fiscal note" in lower:
            kind = "fiscal_note"
        elif item_no == 1:
            kind = "bill_text"
        elif re.search(r"\b[CHS]-?[AB]\b|amendment", lower):
            kind = "amendment"
        else:
            kind = "document"
        documents.append(Document(kind=kind, label=label, url=url))
    return documents


def bill_text_url(documents: List[Document]) -> str:
    for doc in documents:
        if doc.kind == "bill_text":
            return doc.url
    return ""
