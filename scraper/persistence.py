from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Callable

from .constants import LBJ_REVIEW_FILENAME, LBJ_TRAITS_FILENAME
from .models import MatchStatus

LOGGER = logging.getLogger(__name__)

TRAIT_FIELDS = [
    "matched_scientific_name", "lbj_url", "growth_habit", "duration",
    "mature_height_min_ft", "mature_height_max_ft", "light", "moisture",
    "water_use", "soil_categories", "soil_description", "bloom_time", "bloom_color",
]
TRAIT_HEADERS = ["usageKey", "canonicalName", "vernacularName", "match_status"] + TRAIT_FIELDS
REVIEW_HEADERS = ["usageKey", "canonicalName", "vernacularName", "status", "reason", "error", "candidates"]


def load_records(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            records[str(record["usageKey"])] = record
        except json.JSONDecodeError as exc:
            is_partial_final_line = line_number == len(lines) and not line.endswith(("\n", "\r"))
            if is_partial_final_line:
                LOGGER.warning("Ignoring partial final checkpoint line in %s", path)
                continue
            raise ValueError(f"Malformed checkpoint JSON at {path}:{line_number}") from exc
        except KeyError as exc:
            raise ValueError(f"Checkpoint record missing usageKey at {path}:{line_number}") from exc
    return records


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def write_trait_rows(writer: csv.DictWriter, records: list[dict]) -> None:
    for record in records:
        if record["status"] in (MatchStatus.MATCHED.value, MatchStatus.SYNONYM_MATCHED.value):
            row = {key: record.get(key) for key in TRAIT_HEADERS}
            row["match_status"] = record["status"]
            row.update(record.get("normalized_traits") or {})
            writer.writerow(row)


def write_review_rows(writer: csv.DictWriter, records: list[dict]) -> None:
    for record in records:
        if record["status"] not in (MatchStatus.MATCHED.value, MatchStatus.SYNONYM_MATCHED.value):
            evidence = record.get("match") or {}
            writer.writerow({
                **{key: record.get(key) for key in REVIEW_HEADERS},
                "reason": evidence.get("reason", record.get("reason", "")),
                "candidates": json.dumps(evidence.get("candidates", []), ensure_ascii=False),
            })


def write_csv_atomic(
    path: Path,
    headers: list[str],
    row_writer: Callable[[csv.DictWriter, list[dict]], None],
    records: list[dict],
) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        row_writer(writer, records)
    os.replace(temp_path, path)


def generate_outputs(output_dir: Path, records: dict[str, dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = list(records.values())
    write_csv_atomic(output_dir / LBJ_TRAITS_FILENAME, TRAIT_HEADERS, write_trait_rows, ordered)
    write_csv_atomic(output_dir / LBJ_REVIEW_FILENAME, REVIEW_HEADERS, write_review_rows, ordered)
