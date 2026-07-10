from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scraper.constants import LBJ_RAW_FILENAME
from scraper.lady_bird_johnson import main, run
from scraper.models import Candidate, Match, MatchStatus

from helpers import PAGE


class LadyBirdJohnsonCliTests(unittest.TestCase):
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
            raw = (root / "out" / LBJ_RAW_FILENAME).read_text(encoding="utf-8")
            record = json.loads(raw)
            self.assertEqual(record["attempts"], 2)

    def test_main_configures_logging(self):
        totals = {label: 0 for label in ["matched", "synonym_matched", "unmatched", "ambiguous", "failed", "skipped"]}
        with patch("scraper.lady_bird_johnson.run", return_value=totals), \
                patch.object(logging, "basicConfig") as basic_config, \
                patch("sys.stdout", new=io.StringIO()):
            exit_code = main(["--input", "input.csv", "--output-dir", "out", "--log-level", "INFO"])
        self.assertEqual(exit_code, 0)
        basic_config.assert_called_once()
        self.assertEqual(basic_config.call_args.kwargs["level"], "INFO")


if __name__ == "__main__":
    unittest.main()
