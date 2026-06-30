"""Static configuration: base URLs and session identifiers.

Maine identifies a Legislature two different ways:

  * ``snum``      — the Legislature number used by the PS system, e.g. 132.
  * ``SessionID`` — an internal id used by LawMakerWeb, e.g. 16.

The mapping isn't hard-coded: each PS bill page links to its LawMakerWeb summary
with the right ``SessionID``, so it's read off the page at scrape time (see
``ps_parser``). ``DEFAULT_SNUM`` just sets which Legislature to crawl by default.
"""

from __future__ import annotations

# Current Legislature (132nd, 2025-2026). Override with --snum or env MM_SNUM.
DEFAULT_SNUM = 132

PS_BASE = "https://legislature.maine.gov/legis/bills"
LAWMAKER_BASE = "https://legislature.maine.gov/LawMakerWeb"

# The directory pages 200 LDs at a time via the ldFrom query parameter.
DIRECTORY_PAGE_SIZE = 200

# Be a polite citizen of a government web server.
REQUEST_DELAY_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 4
USER_AGENT = (
    "MaineMonitor/0.1 (newsroom bill tracker; "
    "https://github.com/aarushisahejpal/mainemonitor-statehouse)"
)
