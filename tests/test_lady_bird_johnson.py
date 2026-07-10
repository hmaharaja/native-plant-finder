"""Offline tests for the Lady Bird Johnson scraper."""

import csv
import io
import json
import logging
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scraper.http import HttpClient
from scraper.lady_bird_johnson import main, run
from scraper.models import Candidate, Match, MatchStatus
from scraper.normalizer import normalize_traits
from scraper.page_parser import parse_identity, parse_sections, scrape_page
from scraper.persistence import append_record, generate_outputs, load_records
from scraper.searcher import choose_verified, parse_search_response

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


class ScraperTests(unittest.TestCase):
    def test_redirect_and_result_list(self):
        direct = parse_search_response(
            "https://www.wildflower.org/plants/result.php?id_plant=TRGR4", PAGE
        )
        self.assertTrue(direct[0].direct_redirect)
        self.assertEqual(direct[0].scientific_name, "Trillium grandiflorum")
        self.assertIn("<html>", direct[0].page_html)
        match = choose_verified(direct, "Trillium grandiflorum")
        self.assertNotIn("page_html", match.as_dict()["candidate"])
        html = '<a href="result.php?id_plant=SOCA6">Canada Goldenrod (Solidago canadensis)</a>'
        candidates = parse_search_response("https://www.wildflower.org/plants/search.php", html)
        self.assertEqual(candidates[0].scientific_name, "Solidago canadensis")
        self.assertEqual(choose_verified(candidates, "Solidago canadensis").status, MatchStatus.MATCHED)

    def test_conservative_and_synonym_matching(self):
        fuzzy = Candidate("x", scientific_name="Solidago canadensis var. canadensis")
        self.assertEqual(choose_verified([fuzzy], "Solidago canadensis").status, MatchStatus.UNMATCHED)
        synonym = Candidate("x", scientific_name="New name", synonyms=["Old name"])
        self.assertEqual(choose_verified([synonym], "Old name").status, MatchStatus.SYNONYM_MATCHED)

    def test_conflicting_verified_candidates_are_ambiguous(self):
        exact = Candidate("exact", scientific_name="Old name")
        synonym = Candidate("synonym", scientific_name="New name", synonyms=["Old name"])
        result = choose_verified([exact, synonym], "Old name")
        self.assertEqual(result.status, MatchStatus.AMBIGUOUS)
        self.assertEqual(result.reason, "conflicting verified candidates")

    def test_synonym_parsing_preserves_infraspecific_names_and_ignores_other_fields(self):
        html = """
        <html><h2>Example plant (New name)</h2>
        <p><strong>Synonym(s):</strong> Old name var. minor; Other name subsp. major
        <strong>Family:</strong> Notasynonym plantus</p></html>
        """
        identity = parse_identity(html)
        self.assertEqual(identity["synonyms"], ["Old name var. minor", "Other name subsp. major"])

    def test_scrape_page_reuses_supplied_html(self):
        class FailingClient:
            def get(self, url):
                raise AssertionError("scrape_page should not fetch when html is supplied")

        page = scrape_page(FailingClient(), "https://example.test/result.php?id_plant=X", PAGE)
        self.assertEqual(page["lbj_url"], "https://example.test/result.php?id_plant=X")
        self.assertEqual(page["identity"]["scientific_name"], "Trillium grandiflorum")

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

    def test_unknown_controlled_trait_values_warn_and_pass_through(self):
        sections = {"Plant Characteristics": {"Habit": "Herb, Mat-forming"}}
        with self.assertLogs("scraper.normalizer", level="WARNING") as logs:
            traits = normalize_traits(sections, None, "url")
        self.assertEqual(traits["growth_habit"], "herb|Mat-forming")
        self.assertIn("Unmapped LBJ growth_habit value: 'Mat-forming'", logs.output[0])

    def test_retry(self):
        client = HttpClient(delay=0, retries=3, backoff=2)
        policy = client.session.get_adapter("https://").max_retries
        self.assertEqual(policy.total, 2)
        self.assertEqual(policy.backoff_factor, 2)
        self.assertIn("POST", policy.allowed_methods)
        self.assertIn(429, policy.status_forcelist)

    def test_attempt_count_includes_retry_history(self):
        class FakeResponse:
            raw = type("Raw", (), {"retries": type("Retries", (), {"history": (object(), object())})()})()

            def raise_for_status(self):
                return None

        class FakeSession:
            headers: dict[str, str] = {}

            def mount(self, prefix, adapter):
                return None

            def request(self, method, url, timeout, **kwargs):
                return FakeResponse()

        client = HttpClient(delay=0, session=FakeSession())
        client.get("https://example.test")
        self.assertEqual(client.attempts, 3)
        client.reset_attempts()
        self.assertEqual(client.attempts, 0)

    def test_checkpoint_dedup_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "lbj_raw.jsonl"
            base = {"usageKey": "1", "canonicalName": "A b", "vernacularName": "x"}
            append_record(raw, {**base, "status": "unmatched", "match": {"reason": "none"}})
            append_record(raw, {**base, "status": "matched", "normalized_traits": {"lbj_url": "u"}})
            with raw.open("a", encoding="utf8") as handle:
                handle.write("{partial")
            with self.assertLogs("scraper.persistence", level="WARNING"):
                records = load_records(raw)
            self.assertEqual(len(records), 1)
            self.assertEqual(records["1"]["status"], "matched")
            generate_outputs(root, records)
            with (root / "lbj_traits.csv").open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r["usageKey"] for r in rows], ["1"])
            with (root / "lbj_review.csv").open(encoding="utf-8-sig") as handle:
                self.assertEqual(list(csv.DictReader(handle)), [])
            self.assertFalse((root / ".lbj_traits.csv.tmp").exists())
            self.assertFalse((root / ".lbj_review.csv.tmp").exists())

    def test_checkpoint_loader_rejects_non_final_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "lbj_raw.jsonl"
            raw.write_text(
                '{"usageKey": "1", "status": "matched"}\n{bad}\n{"usageKey": "2"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Malformed checkpoint JSON"):
                load_records(raw)

    def test_checkpoint_loader_rejects_missing_usage_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "lbj_raw.jsonl"
            raw.write_text('{"status": "matched"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing usageKey"):
                load_records(raw)

    def test_checkpoint_loader_tolerates_partial_final_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "lbj_raw.jsonl"
            raw.write_text('{"usageKey": "1", "status": "matched"}\n{partial', encoding="utf-8")
            with self.assertLogs("scraper.persistence", level="WARNING"):
                records = load_records(raw)
            self.assertEqual(list(records), ["1"])

    def test_live_sample_expected_ids_fixture_covers_input(self):
        expected = json.loads((FIXTURES / "live_sample_expected_lbj_ids.json").read_text(encoding="utf-8"))
        with (FIXTURES / "live_sample.csv").open(encoding="utf-8-sig") as handle:
            canonical_names = [row["canonicalName"] for row in csv.DictReader(handle)]
        self.assertEqual(set(expected), set(canonical_names))

    def test_expected_id_validation_helper(self):
        expected = {"Trillium grandiflorum": "TRGR4", "Equisetum braunii": None}
        records = {
            "1": {
                "canonicalName": "Trillium grandiflorum",
                "match": {"candidate": {"url": "https://example.test/result.php?id_plant=TRGR4"}},
            },
            "2": {
                "canonicalName": "Equisetum braunii",
                "match": {"candidate": {"url": "https://example.test/result.php?id_plant=EQTEB"}},
            },
        }
        self.assertEqual(expected_id_mismatches(records, expected), [("Equisetum braunii", None, "EQTEB")])

    def test_run_records_http_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.csv"
            input_path.write_text(
                "usageKey,canonicalName,vernacularName\n1,Trillium grandiflorum,white trillium\n",
                encoding="utf-8",
            )
            candidate = Candidate(
                "https://example.test/result.php?id_plant=TRGR4",
                scientific_name="Trillium grandiflorum",
                direct_redirect=True,
                page_html=PAGE,
            )

            def fake_find_match(client, canonical_name, vernacular_name):
                client._attempts += 2
                return Match(MatchStatus.MATCHED, candidate, "exact scientific-name match")

            with patch("scraper.lady_bird_johnson.find_match", fake_find_match):
                totals = run(input_path, root / "out", delay=0)

            self.assertEqual(totals["matched"], 1)
            raw = (root / "out" / "lbj_raw.jsonl").read_text(encoding="utf-8")
            record = json.loads(raw)
            self.assertEqual(record["attempts"], 2)

    def test_main_configures_logging(self):
        with patch("scraper.lady_bird_johnson.run", return_value={label: 0 for label in [
            "matched", "synonym_matched", "unmatched", "ambiguous", "failed", "skipped"
        ]}), patch.object(logging, "basicConfig") as basic_config, patch("sys.stdout", new=io.StringIO()):
            exit_code = main(["--input", "input.csv", "--output-dir", "out", "--log-level", "INFO"])
        self.assertEqual(exit_code, 0)
        basic_config.assert_called_once()
        self.assertEqual(basic_config.call_args.kwargs["level"], "INFO")


if __name__ == "__main__":
    unittest.main()
