"""Full bill-text extraction.

Maine serves bill text as PDF (getPDF.asp). Download the main bill-text PDF and
pull plain text out with PyMuPDF. Text is written to data/text/, separate from
the JSON; the PDFs are not committed (large, and reproducible from the URLs).
"""

from __future__ import annotations

from typing import Optional

from .http import Fetcher
from .models import Bill

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF (fitz) is required for text extraction. "
            "Install it with `pip install pymupdf`."
        )
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc).strip()


def fetch_bill_text(fetcher: Fetcher, bill: Bill) -> Optional[str]:
    """Return the extracted text of the bill's main document, or None."""
    url = ""
    for doc in bill.documents:
        if doc.kind == "bill_text":
            url = doc.url
            break
    if not url:
        return None
    try:
        pdf_bytes = fetcher.get_bytes(url)
        return extract_pdf_text(pdf_bytes)
    except Exception:  # pragma: no cover - a single bad PDF must not kill a run
        return None
