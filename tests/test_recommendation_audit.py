from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from etl.app_data import lbj_enrichment_mask, read_lbj_traits
from etl.recommendation_audit import build_audit, render_markdown


class RecommendationAuditTests(unittest.TestCase):
    def test_audit_uses_later_file_precedence_and_partial_enrichment_predicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.csv"
            later = Path(tmp) / "later.csv"
            pd.DataFrame([
                {"usageKey": "1", "growth_habit": "herb", "light": "sun"},
                {"usageKey": "2", "growth_habit": "shrub"},
            ]).to_csv(first, index=False)
            pd.DataFrame([{"usageKey": "1", "growth_habit": "tree"}]).to_csv(later, index=False)
            traits = read_lbj_traits([first, later])

        self.assertEqual(traits.loc[traits["usageKey"].eq("1"), "growth_habit"].iloc[0], "tree")
        self.assertTrue(lbj_enrichment_mask(traits).all())
        audit = build_audit(
            pd.DataFrame([
                {"usageKey": "1", "ecoregion_id": "10"},
                {"usageKey": "2", "ecoregion_id": "10"},
                {"usageKey": "3", "ecoregion_id": "20"},
            ]),
            traits,
            pd.DataFrame([{"usageKey": "3", "recommendation_category": "specialist_restoration"}]),
        )
        self.assertEqual(audit["enriched"], 2)
        self.assertEqual(audit["unenriched"], 1)
        self.assertEqual(audit["partially_enriched"], 2)
        self.assertIn("toxicity", render_markdown(audit))


if __name__ == "__main__":
    unittest.main()
