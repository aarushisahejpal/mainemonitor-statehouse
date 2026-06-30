#!/usr/bin/env python3
"""Scrape a Maine legislative session and write the data tree.

Examples
--------
Full current session (132nd), everything:
    python scripts/run.py

Quick smoke test (first 5 bills, no per-member votes, no text):
    python scripts/run.py --limit 5 --no-votes --no-text

Backfill the previous session as a test:
    python scripts/run.py --snum 131
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running as a script without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json  # noqa: E402

from maine_monitor import billtext, config  # noqa: E402
from maine_monitor.changelog import append_changes, detect_changes  # noqa: E402
from maine_monitor.directory import list_bills  # noqa: E402
from maine_monitor.export import Exporter  # noqa: E402
from maine_monitor.http import Fetcher  # noqa: E402
from maine_monitor.models import Bill  # noqa: E402
from maine_monitor.qa import check_integrity  # noqa: E402
from maine_monitor.scrape import build_detail, build_head, fingerprint  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--snum", type=int, default=config.DEFAULT_SNUM,
                   help=f"Legislature number (default {config.DEFAULT_SNUM})")
    p.add_argument("--data-dir", default="data", help="Output directory")
    p.add_argument("--cache-dir", default=None,
                   help="Optional HTML cache dir (speeds re-runs; off in CI)")
    p.add_argument("--limit", type=int, default=None,
                   help="Only scrape the first N bills (testing)")
    p.add_argument("--only", type=str, default=None,
                   help="Comma-separated LD numbers to scrape (testing)")
    p.add_argument("--no-votes", action="store_true",
                   help="Skip per-member roll-call detail (faster)")
    p.add_argument("--no-text", action="store_true",
                   help="Skip full bill-text extraction")
    p.add_argument("--full", action="store_true",
                   help="Deep-scrape every bill, ignoring stored data "
                        "(default reuses unchanged bills)")
    p.add_argument("--delay", type=float, default=config.REQUEST_DELAY_SECONDS,
                   help="Seconds between requests")
    return p.parse_args(argv)


def load_prior(bills_dir: Path) -> dict:
    """Load stored per-bill JSON, keyed by LD, with its fingerprint."""
    prior = {}
    if not bills_dir.is_dir():
        return prior
    for path in bills_dir.glob("LD*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            bill = Bill.from_dict(data)
            prior[bill.ld] = (bill, fingerprint(bill))
        except Exception:
            continue
    return prior


def main(argv=None) -> int:
    args = parse_args(argv)
    fetcher = Fetcher(cache_dir=args.cache_dir, delay=args.delay)
    exporter = Exporter(Path(args.data_dir))

    entries = list_bills(fetcher, args.snum)
    if args.only:
        wanted = {int(x) for x in args.only.split(",") if x.strip()}
        entries = [e for e in entries if e.ld in wanted]
    if args.limit is not None:
        entries = entries[: args.limit]

    # Always load stored bills for change detection; only reuse them when
    # not doing a full reconciliation.
    prior = load_prior(exporter.bills_dir)
    had_prior = len(prior) > 0
    total = len(entries)
    mode = "full" if args.full else f"incremental ({len(prior)} stored)"
    print(f"Scraping {total} bills from the {args.snum}th Legislature "
          f"[{mode}, votes={'off' if args.no_votes else 'on'}, "
          f"text={'off' if args.no_text else 'on'}]", flush=True)

    bills = []
    changes = []
    reused = failed = 0
    start = time.monotonic()
    for i, entry in enumerate(entries, 1):
        try:
            head = build_head(fetcher, entry)
            stored = prior.get(entry.ld)
            if (not args.full and stored
                    and fingerprint(head) == stored[1] and stored[0].lawmaker_id):
                # Unchanged since last run: keep the full stored record.
                bill = stored[0]
                bill.scraped_at = head.scraped_at
                reused += 1
            else:
                bill = build_detail(fetcher, head,
                                    include_member_votes=not args.no_votes)
                if not args.no_text:
                    text = billtext.fetch_bill_text(fetcher, bill)
                    if text:
                        exporter.write_bill_text(bill, text)
                if had_prior:
                    prior_bill = stored[0] if stored else None
                    changes.extend(
                        detect_changes(prior_bill, bill, bill.scraped_at))
            exporter.write_bill_json(bill)
            bills.append(bill)
        except Exception as exc:  # one bad bill must not kill the run
            failed += 1
            print(f"  ! LD {entry.ld} ({entry.paper}) failed: {exc}", flush=True)
            continue

        if i % 50 == 0 or i == total:
            rate = i / (time.monotonic() - start)
            eta = (total - i) / rate if rate else 0
            print(f"  [{i:>4}/{total}] LD {entry.ld:<4} {entry.paper}  "
                  f"reused={reused} ({rate:.1f}/s, ETA {eta/60:.0f}m)", flush=True)

    anomalies = check_integrity(bills, expected=total - failed)
    exporter.write_all(bills, args.snum, anomalies)
    append_changes(Path(args.data_dir) / "changes.csv", changes)
    print(f"Done: {len(bills)} bills ({reused} reused, {failed} failed, "
          f"{len(changes)} changes) in {(time.monotonic()-start)/60:.1f} min",
          flush=True)
    if anomalies:
        print(f"Integrity warnings ({len(anomalies)}):", flush=True)
        for a in anomalies[:20]:
            print(f"  - {a}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
