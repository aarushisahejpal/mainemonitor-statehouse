# Maine Monitor — Statehouse bill tracker

Self-owned pipeline that pulls the full public record for every bill (LD) in a
Maine legislative session straight from the Legislature's own systems, normalizes
it, and commits it here as JSON + CSV. No BillTrack50, no third-party API — the
data matches the official source because it comes from the official source.

The data updates automatically (see [Automation](#automation)) so it can power a
newsroom page and back analysis.

## What gets captured

For every LD in the session:

- **Identity** — LD number, paper number (HP/SP/IB), origin chamber, title
- **Status** — reference committee, final disposition, governor's action,
  whether it became law, chaptered-law chapter number
- **Sponsors** — primary sponsor + cosponsors, with chamber and town
- **Subjects** — major / minor / detail subject coding
- **Actions** — full chronological history, House and Senate, with dates
- **Roll calls** — every recorded vote, House and Senate, with the motion,
  outcome, tallies, *and individual member votes* (member, party, Y/N/X/E)
- **Amendments** — label, new title, House/Senate action, adoption
- **Documents** — links to printed bill text, amendments, fiscal notes (PDF)
- **Full bill text** — extracted to plain text for search and NLP

## Data sources

Two official systems, joined on the LD number:

| System | URL | Used for |
| --- | --- | --- |
| PS (Bill Text & Status) | `legislature.maine.gov/legis/bills/display_ps.asp` | disposition, chaptered law, document PDFs, session id |
| LawMakerWeb | `legislature.maine.gov/LawMakerWeb/` | actions, roll calls, sponsors, subjects, amendments |

## Output layout

```
data/
  manifest.json            run metadata + integrity summary
  bills.json               every bill, full nested record (site/API feed)
  bills/LD####.json        one file per bill (clean per-bill git diffs)
  text/<snum>/<paper>.txt  extracted full bill text
  csv/
    bills.csv              one flat row per bill
    sponsors.csv
    actions.csv
    roll_calls.csv
    member_votes.csv       one row per member per vote
    amendments.csv
    subjects.csv
    documents.csv
```

## Running it

```bash
pip install -r requirements.txt

# Full current session (132nd), everything:
python scripts/run.py

# Quick smoke test:
python scripts/run.py --limit 5 --no-votes --no-text

# Backfill the previous session:
python scripts/run.py --snum 131

# Force a complete re-scrape (ignore stored data):
python scripts/run.py --full
```

Useful flags: `--snum`, `--limit`, `--only 1,3,1822`, `--no-votes`, `--no-text`,
`--full`, `--delay`, `--cache-dir`.

## Automation

`.github/workflows/update.yml` runs on a schedule and commits any changes:

- **Mon–Sat** — incremental update. Reuses stored bills and only deep-scrapes
  the ones whose status changed, so it's fast and gentle on the source.
- **Sunday** — full reconciliation (`--full`), re-scraping every bill so the
  dataset is guaranteed to match the source.

Git history is the append-only audit log: each commit is a diff showing exactly
which bills changed that day. Change the cadence by editing the `cron` lines.

## Accuracy

Because this powers reporting, every run verifies itself (`maine_monitor/qa.py`):
vote tallies must reconcile with counted member votes, enacted bills must carry a
chapter number, active bills must have actions, and the bill count must match the
directory. Anything off is written to `manifest.json` and printed at the end of
the run.
