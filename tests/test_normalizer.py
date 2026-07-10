from __future__ import annotations

import unittest

from scraper.normalizer import normalize_traits
from scraper.page_parser import parse_identity, parse_sections

from helpers import PAGE


class NormalizerTests(unittest.TestCase):
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

    def test_height_ranges_accept_hyphen_en_dash_and_em_dash(self):
        for value in ("1-3 feet", "1–3 feet", "1—3 feet", "1 to 3 feet"):
            with self.subTest(value=value):
                traits = normalize_traits({"Plant Characteristics": {"Size Notes": value}}, None, "url")
                self.assertEqual(traits["mature_height_min_ft"], 1)
                self.assertEqual(traits["mature_height_max_ft"], 3)

    def test_unknown_controlled_trait_values_warn_and_pass_through(self):
        sections = {"Plant Characteristics": {"Habit": "Herb, Mat-forming"}}
        with self.assertLogs("scraper.normalizer", level="WARNING") as logs:
            traits = normalize_traits(sections, None, "url")
        self.assertEqual(traits["growth_habit"], "herb|Mat-forming")
        self.assertIn("Unmapped LBJ growth_habit value: 'Mat-forming'", logs.output[0])


if __name__ == "__main__":
    unittest.main()
