from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scraper.constants import LBJ_RAW_FILENAME, LBJ_REVIEW_FILENAME, LBJ_TRAITS_FILENAME
from scraper.persistence import append_record, generate_outputs, load_records

from helpers import temp_filename


class PersistenceTests(unittest.TestCase):
    def test_checkpoint_dedup_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / LBJ_RAW_FILENAME
            base = {"usageKey": "1", "canonicalName": "A b", "vernacularName": "x"}
            append_record(raw, {**base, "status": "unmatched", "match": {"reason": "none"}})
            append_record(raw, {**base, "status": "matched", "normalized_traits": {"lbj_url": "u"}})
            raw.write_text(raw.read_text(encoding="utf-8") + "{partial", encoding="utf-8")

            with self.assertLogs("scraper.persistence", level="WARNING"):
                records = load_records(raw)

            self.assertEqual(len(records), 1)
            self.assertEqual(records["1"]["status"], "matched")
            generate_outputs(root, records)

            with (root / LBJ_TRAITS_FILENAME).open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["usageKey"] for row in rows], ["1"])

            with (root / LBJ_REVIEW_FILENAME).open(encoding="utf-8-sig") as handle:
                self.assertEqual(list(csv.DictReader(handle)), [])

            self.assertFalse((root / temp_filename(LBJ_TRAITS_FILENAME)).exists())
            self.assertFalse((root / temp_filename(LBJ_REVIEW_FILENAME)).exists())

    def test_checkpoint_loader_rejects_non_final_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / LBJ_RAW_FILENAME
            raw.write_text(
                '{"usageKey": "1", "status": "matched"}\n{bad}\n{"usageKey": "2"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Malformed checkpoint JSON"):
                load_records(raw)

    def test_checkpoint_loader_rejects_missing_usage_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / LBJ_RAW_FILENAME
            raw.write_text('{"status": "matched"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing usageKey"):
                load_records(raw)

    def test_checkpoint_loader_tolerates_partial_final_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / LBJ_RAW_FILENAME
            raw.write_text('{"usageKey": "1", "status": "matched"}\n{partial', encoding="utf-8")
            with self.assertLogs("scraper.persistence", level="WARNING"):
                records = load_records(raw)
            self.assertEqual(list(records), ["1"])


if __name__ == "__main__":
    unittest.main()
