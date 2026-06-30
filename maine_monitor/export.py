"""Write scraped bills to the data/ tree: combined + per-bill JSON, flat CSVs,
extracted text, and a run manifest. See README for the full layout.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

from . import __version__
from .models import Bill


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Exporter:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.bills_dir = self.data_dir / "bills"
        self.csv_dir = self.data_dir / "csv"
        self.text_dir = self.data_dir / "text"
        for d in (self.bills_dir, self.csv_dir, self.text_dir):
            d.mkdir(parents=True, exist_ok=True)

    # -- per-bill ------------------------------------------------------------
    def write_bill_json(self, bill: Bill) -> None:
        path = self.bills_dir / f"LD{bill.ld:04d}.json"
        path.write_text(
            json.dumps(bill.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_bill_text(self, bill: Bill, text: str) -> Path:
        out = self.text_dir / str(bill.snum)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{bill.paper}.txt"
        path.write_text(text, encoding="utf-8")
        return path

    # -- whole-session aggregates -------------------------------------------
    def write_all(
        self, bills: Sequence[Bill], snum: int, anomalies: List[str] = None
    ) -> None:
        bills = sorted(bills, key=lambda b: b.ld)
        anomalies = anomalies or []
        self._write_combined_json(bills)
        self._write_csvs(bills)
        self._write_manifest(bills, snum, anomalies)
        (self.data_dir / "integrity.json").write_text(
            json.dumps({"count": len(anomalies), "issues": anomalies}, indent=2),
            encoding="utf-8",
        )

    def _write_combined_json(self, bills: Sequence[Bill]) -> None:
        path = self.data_dir / "bills.json"
        path.write_text(
            json.dumps([b.to_dict() for b in bills], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_manifest(
        self, bills: Sequence[Bill], snum: int, anomalies: List[str]
    ) -> None:
        manifest = {
            "generator": "maine-monitor",
            "version": __version__,
            "snum": snum,
            "generated_at": _now_iso(),
            "bill_count": len(bills),
            "enacted_count": sum(1 for b in bills if b.became_law),
            "with_roll_calls": sum(1 for b in bills if b.roll_calls),
            "total_actions": sum(len(b.actions) for b in bills),
            "total_roll_calls": sum(len(b.roll_calls) for b in bills),
            "ld_min": bills[0].ld if bills else None,
            "ld_max": bills[-1].ld if bills else None,
            "integrity_warnings": len(anomalies),
        }
        (self.data_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def _write_csvs(self, bills: Sequence[Bill]) -> None:
        self._csv(
            "bills.csv",
            ["ld", "paper", "origin_chamber", "snum", "title", "committee",
             "final_disposition", "governor_action", "chaptered_law", "chapter",
             "became_law", "last_house_action", "last_senate_action",
             "sponsor_count", "action_count", "roll_call_count", "amendment_count",
             "ps_url", "lawmaker_summary_url"],
            ([b.ld, b.paper, b.origin_chamber, b.snum, b.title, b.committee,
              b.final_disposition, b.governor_action, b.chaptered_law, b.chapter,
              b.became_law, b.last_house_action, b.last_senate_action,
              len(b.sponsors), len(b.actions), len(b.roll_calls), len(b.amendments),
              b.ps_url, b.lawmaker_summary_url] for b in bills),
        )
        self._csv(
            "sponsors.csv",
            ["ld", "paper", "role", "title", "name", "chamber", "district"],
            ([b.ld, b.paper, s.role, s.title, s.name, s.chamber, s.district]
             for b in bills for s in b.sponsors),
        )
        self._csv(
            "actions.csv",
            ["ld", "paper", "seq", "date", "chamber", "description"],
            ([b.ld, b.paper, i, a.date, a.chamber, a.description]
             for b in bills for i, a in enumerate(b.actions)),
        )
        self._csv(
            "roll_calls.csv",
            ["ld", "paper", "chamber", "number", "date", "motion", "outcome",
             "yeas", "nays", "absent", "excused", "vacant", "yeas_required", "url"],
            ([b.ld, b.paper, r.chamber, r.number, r.date, r.motion, r.outcome,
              r.yeas, r.nays, r.absent, r.excused, r.vacant, r.yeas_required, r.url]
             for b in bills for r in b.roll_calls),
        )
        self._csv(
            "member_votes.csv",
            ["ld", "paper", "rc_chamber", "rc_number", "rc_date",
             "member", "party", "vote"],
            ([b.ld, b.paper, r.chamber, r.number, r.date, m.member, m.party, m.vote]
             for b in bills for r in b.roll_calls for m in r.members),
        )
        self._csv(
            "amendments.csv",
            ["ld", "paper", "label", "adopted", "new_title",
             "house_action", "senate_action"],
            ([b.ld, b.paper, a.label, a.adopted, a.new_title,
              a.house_action, a.senate_action]
             for b in bills for a in b.amendments),
        )
        self._csv(
            "subjects.csv",
            ["ld", "paper", "major", "minor", "detail"],
            ([b.ld, b.paper, s.major, s.minor, s.detail]
             for b in bills for s in b.subjects),
        )
        self._csv(
            "documents.csv",
            ["ld", "paper", "kind", "label", "url"],
            ([b.ld, b.paper, d.kind, d.label, d.url]
             for b in bills for d in b.documents),
        )

    def _csv(self, name: str, header: List[str], rows) -> None:
        with (self.csv_dir / name).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows)
