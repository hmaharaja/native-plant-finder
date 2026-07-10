from __future__ import annotations

import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "scraper" / "fixtures"

PAGE = """
<html><h2>White trillium (Trillium grandiflorum)</h2>
<div class="section"><h4>Plant Characteristics</h4>
<strong>Duration:</strong> Perennial<br/><strong>Habit:</strong> Herb
<strong>Size Notes:</strong> 1-3 feet</div>
<div class="section"><h4>Growing Conditions</h4>
<strong>Light Requirement:</strong> Sun, Part Shade
<strong>Soil Moisture:</strong> Moist<strong>Water Use:</strong> Medium
<strong>Soil Description:</strong> Rich clay or loam.</div>
<div class="section"><h4>Bloom Information</h4>
<strong>Bloom Time:</strong> Apr, May<strong>Bloom Color:</strong> White</div></html>
"""

PLANT_ID_PATTERN = re.compile(r"[?&]id_plant=([^&]+)")


def lbj_id_from_record(record: dict) -> str | None:
    candidate = (record.get("match") or {}).get("candidate") or {}
    match = PLANT_ID_PATTERN.search(candidate.get("url") or "")
    return match.group(1) if match else None


def expected_id_mismatches(records: dict[str, dict], expected: dict[str, str | None]) -> list[tuple[str, str | None, str | None]]:
    mismatches: list[tuple[str, str | None, str | None]] = []
    for record in records.values():
        canonical_name = record["canonicalName"]
        actual = lbj_id_from_record(record)
        if actual != expected[canonical_name]:
            mismatches.append((canonical_name, expected[canonical_name], actual))
    return mismatches


def temp_filename(filename: str) -> str:
    return f".{filename}.tmp"
