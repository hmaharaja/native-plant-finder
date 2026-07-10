from __future__ import annotations

import csv
import json
import unittest

from scraper.constants import LIVE_SAMPLE_EXPECTED_IDS_FILENAME, LIVE_SAMPLE_FILENAME

from helpers import FIXTURES, expected_id_mismatches


class LiveSampleExpectationTests(unittest.TestCase):
    def test_live_sample_expected_ids_fixture_covers_input(self):
        expected = json.loads((FIXTURES / LIVE_SAMPLE_EXPECTED_IDS_FILENAME).read_text(encoding="utf-8"))
        with (FIXTURES / LIVE_SAMPLE_FILENAME).open(encoding="utf-8-sig") as handle:
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


if __name__ == "__main__":
    unittest.main()
