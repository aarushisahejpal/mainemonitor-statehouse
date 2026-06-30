"""Maine State Legislature bill scraper.

Pulls every bill (LD) in a session from the Legislature's own systems — the PS
bill pages (display_ps.asp) for documents and disposition, and LawMakerWeb for
actions, roll calls, sponsors, subjects, and amendments — and writes normalized
JSON + CSV.
"""

__version__ = "0.1.0"
