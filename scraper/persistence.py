from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import MatchStatus

TRAIT_FIELDS = [
    "matched_scientific_name", "lbj_url", "growth_habit", "duration",
    "mature_height_min_ft", "mature_height_max_ft", "light", "moisture",
    "water_use", "soil_categories", "soil_description", "bloom_time", "bloom_color",
]


def load_records(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                records[str(record["usageKey"])] = record
            except (json.JSONDecodeError, KeyError):
                # A partial final append must not make earlier checkpoints unusable.
                if line_number:
                    continue
    return records


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def generate_outputs(output_dir: Path, records: dict[str, dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = list(records.values())
    trait_headers = ["usageKey", "canonicalName", "vernacularName", "match_status"] + TRAIT_FIELDS
    with (output_dir / "lbj_traits.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=trait_headers, extrasaction="ignore")
        writer.writeheader()
        for record in ordered:
            if record["status"] in (MatchStatus.MATCHED.value, MatchStatus.SYNONYM_MATCHED.value):
                row = {k: record.get(k) for k in trait_headers}
                row["match_status"] = record["status"]
                row.update(record.get("normalized_traits") or {})
                writer.writerow(row)
    review_headers = ["usageKey", "canonicalName", "vernacularName", "status", "reason", "error", "candidates"]
    with (output_dir / "lbj_review.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_headers)
        writer.writeheader()
        for record in ordered:
            if record["status"] not in (MatchStatus.MATCHED.value, MatchStatus.SYNONYM_MATCHED.value):
                evidence = record.get("match") or {}
                writer.writerow({
                    **{k: record.get(k) for k in review_headers},
                    "reason": evidence.get("reason", record.get("reason", "")),
                    "candidates": json.dumps(evidence.get("candidates", []), ensure_ascii=False),
                })
