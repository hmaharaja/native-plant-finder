from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .http import HttpClient
from .models import MatchStatus
from .normalizer import normalize_traits
from .page_parser import scrape_page
from .persistence import append_record, generate_outputs, load_records
from .searcher import find_match


def run(input_path: Path, output_dir: Path, limit: int | None = None,
        delay: float = 1, timeout: float = 20, retries: int = 3) -> Counter:
    raw_path = output_dir / "lbj_raw.jsonl"
    records = load_records(raw_path)
    totals: Counter = Counter()
    client = HttpClient(timeout=timeout, delay=delay, retries=retries)
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        considered = 0
        for row in rows:
            key = str(row["usageKey"])
            if key in records:
                totals["skipped"] += 1
                continue
            if limit is not None and considered >= limit:
                break
            considered += 1
            record = {
                "usageKey": key,
                "canonicalName": row.get("canonicalName"),
                "vernacularName": row.get("vernacularName"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attempts": 1,
            }
            try:
                match = find_match(client, row["canonicalName"], row.get("vernacularName"))
                record["status"] = match.status.value
                record["match"] = match.as_dict()
                if match.candidate and match.status in (MatchStatus.MATCHED, MatchStatus.SYNONYM_MATCHED):
                    page = scrape_page(client, match.candidate.url)
                    record["raw_sections"] = page["sections"]
                    record["normalized_traits"] = normalize_traits(
                        page["sections"],
                        page["identity"]["scientific_name"] or match.candidate.scientific_name,
                        page["lbj_url"],
                    )
            except Exception as exc:
                record.update(status=MatchStatus.FAILED.value, error=f"{type(exc).__name__}: {exc}")
            append_record(raw_path, record)
            records[key] = record
            totals[record["status"]] += 1
    generate_outputs(output_dir, records)
    return totals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resumable Lady Bird Johnson gardening-traits scraper")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=1)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--retries", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    totals = run(args.input, args.output_dir, args.limit, args.delay, args.timeout, args.retries)
    labels = ["matched", "synonym_matched", "unmatched", "ambiguous", "failed", "skipped"]
    print(" ".join(f"{label}={totals[label]}" for label in labels))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
