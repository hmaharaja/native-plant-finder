"""Offline tests for the Lady Bird Johnson scraper."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scraper.http import HttpClient
from scraper.models import Candidate, MatchStatus
from scraper.normalizer import normalize_traits
from scraper.page_parser import parse_identity, parse_sections
from scraper.persistence import append_record, generate_outputs, load_records
from scraper.searcher import choose_verified, parse_search_response

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


class ScraperTests(unittest.TestCase):
    def test_redirect_and_result_list(self):
        direct = parse_search_response(
            "https://www.wildflower.org/plants/result.php?id_plant=TRGR4", PAGE
        )
        self.assertTrue(direct[0].direct_redirect)
        html = '<a href="result.php?id_plant=SOCA6">Canada Goldenrod (Solidago canadensis)</a>'
        candidates = parse_search_response("https://www.wildflower.org/plants/search.php", html)
        self.assertEqual(candidates[0].scientific_name, "Solidago canadensis")
        self.assertEqual(choose_verified(candidates, "Solidago canadensis").status, MatchStatus.MATCHED)

    def test_conservative_and_synonym_matching(self):
        fuzzy = Candidate("x", scientific_name="Solidago canadensis var. canadensis")
        self.assertEqual(choose_verified([fuzzy], "Solidago canadensis").status, MatchStatus.UNMATCHED)
        synonym = Candidate("x", scientific_name="New name", synonyms=["Old name"])
        self.assertEqual(choose_verified([synonym], "Old name").status, MatchStatus.SYNONYM_MATCHED)

    def test_parse_and_normalize_sparse_sections(self):
        sections = parse_sections(PAGE)
        identity = parse_identity(PAGE)
        traits = normalize_traits(sections, identity["scientific_name"], "url")
        self.assertEqual(traits["mature_height_min_ft"], 1)
        self.assertEqual(traits["mature_height_max_ft"], 3)
        self.assertEqual(traits["soil_categories"], "clay|loam")
        self.assertIsNone(normalize_traits({}, None, "url")["duration"])
        fraction = normalize_traits(
            {"Plant Characteristics": {"Size Notes": "Up to about 3-1/2 feet tall."}},
            None,
            "url",
        )
        self.assertIsNone(fraction["mature_height_min_ft"])
        self.assertEqual(fraction["mature_height_max_ft"], 3.5)

    def test_retry(self):
        client = HttpClient(delay=0, retries=3, backoff=2)
        policy = client.session.get_adapter("https://").max_retries
        self.assertEqual(policy.total, 2)
        self.assertEqual(policy.backoff_factor, 2)
        self.assertIn("POST", policy.allowed_methods)
        self.assertIn(429, policy.status_forcelist)

    def test_checkpoint_dedup_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "lbj_raw.jsonl"
            base = {"usageKey": "1", "canonicalName": "A b", "vernacularName": "x"}
            append_record(raw, {**base, "status": "unmatched", "match": {"reason": "none"}})
            append_record(raw, {**base, "status": "matched", "normalized_traits": {"lbj_url": "u"}})
            with raw.open("a", encoding="utf8") as handle:
                handle.write("{partial")
            records = load_records(raw)
            self.assertEqual(len(records), 1)
            self.assertEqual(records["1"]["status"], "matched")
            generate_outputs(root, records)
            with (root / "lbj_traits.csv").open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r["usageKey"] for r in rows], ["1"])
            with (root / "lbj_review.csv").open(encoding="utf-8-sig") as handle:
                self.assertEqual(list(csv.DictReader(handle)), [])


if __name__ == "__main__":
    unittest.main()
