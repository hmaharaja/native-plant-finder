from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from etl.app_data import (
    build_app_data,
    build_ecoregion_payloads,
    merge_plant_ecoregions_with_traits,
    plant_record_from_row,
    read_lbj_traits,
    read_recommendation_categories,
    write_app_data,
)
from etl.app_data_cli import main


class AppDataTests(unittest.TestCase):
    FIXTURES = Path(__file__).parent / "fixtures"

    def test_recommendation_categories_reject_duplicates_and_invalid_values(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            read_recommendation_categories(
                self.FIXTURES / "recommendation_categories_duplicate.csv"
            )
        with self.assertRaisesRegex(ValueError, "invalid recommendation"):
            read_recommendation_categories(
                self.FIXTURES / "recommendation_categories_invalid.csv"
            )

    def test_lbj_merge_prefers_later_duplicate_usage_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "lbj.csv"
            second = Path(tmp) / "lbj_rerun.csv"
            pd.DataFrame(
                [
                    {"usageKey": "100", "growth_habit": "herb", "lbj_url": "old"},
                    {"usageKey": "200", "growth_habit": "shrub", "lbj_url": "only"},
                ]
            ).to_csv(first, index=False)
            pd.DataFrame(
                [{"usageKey": "100", "growth_habit": "tree", "lbj_url": "new"}]
            ).to_csv(second, index=False)

            traits = read_lbj_traits([first, second])

        self.assertEqual(len(traits), 2)
        duplicate = traits[traits["usageKey"].eq("100")].iloc[0]
        self.assertEqual(duplicate["growth_habit"], "tree")
        self.assertEqual(duplicate["lbj_url"], "new")

    def test_json_normalization_uses_camel_case_nulls_and_arrays(self):
        row = pd.Series(
            {
                "usageKey": "100.0",
                "canonicalName": "Achillea millefolium",
                "vernacularName": "",
                "occurrence_count": "3",
                "human_observation_count": "2",
                "preserved_specimen_count": "1",
                "coordinate_uncertainty_median_m": "12.3456",
                "first_year": "2018.0",
                "last_year": "2020.0",
                "growth_habit": "herb|subshrub",
                "duration": pd.NA,
                "mature_height_min_ft": "",
                "mature_height_max_ft": "2.333333333333333",
                "light": "sun|part shade",
                "moisture": float("nan"),
                "water_use": "medium",
                "soil_categories": "loam|sand",
                "bloom_time": "jun|jul",
                "bloom_color": "white|pink",
                "lbj_url": "https://example.test",
                "recommendation_category": "conditional",
            }
        )

        record = plant_record_from_row(row)

        self.assertEqual(record["usageKey"], 100)
        self.assertEqual(record["canonicalName"], "Achillea millefolium")
        self.assertIsNone(record["vernacularName"])
        self.assertEqual(record["coordinateUncertaintyMedianM"], 12.35)
        self.assertIsNone(record["duration"])
        self.assertIsNone(record["matureHeightMinFt"])
        self.assertEqual(record["matureHeightMaxFt"], 2.33)
        self.assertEqual(record["growthHabit"], ["herb", "subshrub"])
        self.assertEqual(record["light"], ["sun", "part shade"])
        self.assertEqual(record["moisture"], [])
        self.assertEqual(record["soilCategories"], ["loam", "sand"])
        self.assertEqual(record["recommendationCategory"], "conditional")

    def test_ecoregion_output_writes_files_manifest_and_sorted_plants(self):
        plant_ecoregions = pd.DataFrame(
            [
                {
                    "usageKey": "200",
                    "canonicalName": "Zizia aurea",
                    "vernacularName": "golden alexanders",
                    "occurrence_count": "1",
                    "human_observation_count": "1",
                    "preserved_specimen_count": "0",
                    "coordinate_uncertainty_median_m": "10",
                    "first_year": "2020",
                    "last_year": "2020",
                    "ecoregion_id": "7",
                    "ecoregion_name": "Fixture",
                },
                {
                    "usageKey": "100",
                    "canonicalName": "Aster laevis",
                    "vernacularName": "smooth aster",
                    "occurrence_count": "2",
                    "human_observation_count": "1",
                    "preserved_specimen_count": "1",
                    "coordinate_uncertainty_median_m": "5",
                    "first_year": "2019",
                    "last_year": "2021",
                    "ecoregion_id": "7",
                    "ecoregion_name": "Fixture",
                },
                {
                    "usageKey": "300",
                    "canonicalName": "Carex stricta",
                    "vernacularName": "tussock sedge",
                    "occurrence_count": "1",
                    "human_observation_count": "0",
                    "preserved_specimen_count": "1",
                    "coordinate_uncertainty_median_m": "3",
                    "first_year": "2018",
                    "last_year": "2018",
                    "ecoregion_id": "9",
                    "ecoregion_name": "Other",
                },
            ]
        )
        lbj_traits = pd.DataFrame(
            [
                {"usageKey": "100", "growth_habit": "herb", "lbj_url": "https://a.test"},
                {"usageKey": "200", "growth_habit": "herb", "lbj_url": "https://z.test"},
            ]
        )
        recommendation_categories = read_recommendation_categories(
            self.FIXTURES / "recommendation_categories_valid.csv"
        )

        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_app_data(
                plant_ecoregions, lbj_traits, tmp, recommendation_categories
            )
            first_payload = json.loads((Path(tmp) / "ecoregions" / "7.json").read_text())
            manifest_json = json.loads((Path(tmp) / "manifest.json").read_text())

        self.assertEqual(manifest["ecoregionCount"], 2)
        self.assertEqual(manifest["plantEcoregionCount"], 3)
        self.assertEqual(manifest["missingLbjTraitCount"], 1)
        self.assertEqual(manifest_json["ecoregions"][0]["path"], "ecoregions/7.json")
        self.assertEqual(manifest_json["ecoregions"][0]["plantCount"], 2)
        self.assertEqual(first_payload["ecoregionId"], 7)
        self.assertEqual(first_payload["plantCount"], 2)
        self.assertIsNone(first_payload["plants"][0]["recommendationCategory"])
        self.assertEqual(
            [plant["vernacularName"] for plant in first_payload["plants"]],
            ["golden alexanders", "smooth aster"],
        )
        second_payload = next(
            payload for payload in build_ecoregion_payloads(
                merge_plant_ecoregions_with_traits(
                    plant_ecoregions, lbj_traits, recommendation_categories
                )
            )
            if payload["ecoregionId"] == 9
        )
        self.assertEqual(
            second_payload["plants"][0]["recommendationCategory"],
            "specialist_restoration",
        )

    def test_missing_app_relevant_unenriched_category_is_rejected(self):
        plants = pd.DataFrame([{"usageKey": "999", "ecoregion_id": "1"}])
        traits = pd.DataFrame([{"usageKey": "100", "growth_habit": "herb"}])
        categories = read_recommendation_categories(
            self.FIXTURES / "recommendation_categories_missing.csv"
        )
        with self.assertRaisesRegex(ValueError, "missing recommendation categories"):
            merge_plant_ecoregions_with_traits(plants, traits, categories)

    def test_payload_builder_sorts_by_vernacular_then_canonical(self):
        rows = pd.DataFrame(
            [
                {"usageKey": "2", "canonicalName": "Beta", "vernacularName": "Same", "ecoregion_id": "1", "ecoregion_name": "One"},
                {"usageKey": "1", "canonicalName": "Alpha", "vernacularName": "Same", "ecoregion_id": "1", "ecoregion_name": "One"},
            ]
        )

        payloads = build_ecoregion_payloads(rows)

        self.assertEqual([plant["canonicalName"] for plant in payloads[0]["plants"]], ["Alpha", "Beta"])

    def test_payload_builder_sorts_ecoregions_numerically(self):
        rows = pd.DataFrame(
            [
                {"usageKey": "10", "canonicalName": "Ten", "vernacularName": "Ten", "ecoregion_id": "10", "ecoregion_name": "Ten"},
                {"usageKey": "2", "canonicalName": "Two", "vernacularName": "Two", "ecoregion_id": "2", "ecoregion_name": "Two"},
            ]
        )

        payloads = build_ecoregion_payloads(rows)

        self.assertEqual([payload["ecoregionId"] for payload in payloads], [2, 10])

    def test_build_app_data_reads_csvs_and_logs_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plant_path = root / "plants.csv"
            lbj_path = root / "traits.csv"
            output_dir = root / "out"
            categories_path = root / "categories.csv"
            pd.DataFrame(
                [
                    {
                        "usageKey": "100",
                        "canonicalName": "Aster laevis",
                        "vernacularName": "smooth aster",
                        "occurrence_count": "1",
                        "human_observation_count": "1",
                        "preserved_specimen_count": "0",
                        "coordinate_uncertainty_median_m": "5",
                        "first_year": "2020",
                        "last_year": "2020",
                        "ecoregion_id": "7",
                        "ecoregion_name": "Fixture",
                    }
                ]
            ).to_csv(plant_path, index=False)
            pd.DataFrame([{"usageKey": "100", "growth_habit": "herb"}]).to_csv(lbj_path, index=False)
            pd.DataFrame(
                [{"usageKey": "999", "recommendation_category": "conditional"}]
            ).to_csv(categories_path, index=False)

            with self.assertLogs("etl.app_data", level="INFO") as logs:
                manifest = build_app_data(
                    plant_path, [lbj_path], output_dir, categories_path
                )

            self.assertEqual(manifest["ecoregionCount"], 1)
            self.assertTrue((output_dir / "ecoregions" / "7.json").exists())
            self.assertTrue(any("plant ecoregion input rows=1" in line for line in logs.output))
            self.assertTrue(any("combined unique LBJ trait rows=1" in line for line in logs.output))

    def test_merge_keeps_rows_without_lbj_traits(self):
        plant_ecoregions = pd.DataFrame([{"usageKey": "999", "ecoregion_id": "1"}])
        lbj_traits = pd.DataFrame([{"usageKey": "100", "growth_habit": "herb"}])

        merged = merge_plant_ecoregions_with_traits(plant_ecoregions, lbj_traits)

        self.assertEqual(len(merged), 1)
        self.assertTrue(pd.isna(merged.iloc[0]["growth_habit"]))


class AppDataCliTests(unittest.TestCase):
    def test_main_forwards_args_and_prints_summary(self):
        with patch(
            "etl.app_data_cli.build_app_data",
            return_value={
                "ecoregionCount": 2,
                "plantEcoregionCount": 3,
                "missingLbjTraitCount": 1,
                "ecoregions": [],
            },
        ) as build_app_data_func, patch.object(logging, "basicConfig") as basic_config, patch(
            "sys.stdout", new=io.StringIO()
        ) as stdout:
            exit_code = main(
                [
                    "--plant-ecoregions",
                    "derived/plants.csv",
                    "--lbj-traits",
                    "lbj/a.csv",
                    "--lbj-traits",
                    "lbj/b.csv",
                    "--output-dir",
                    "public/data",
                    "--recommendation-categories",
                    "curation/categories.csv",
                    "--log-level",
                    "DEBUG",
                ]
            )

        self.assertEqual(exit_code, 0)
        basic_config.assert_called_once()
        self.assertEqual(basic_config.call_args.kwargs["level"], "DEBUG")
        build_app_data_func.assert_called_once_with(
            plant_ecoregions_path=Path("derived/plants.csv"),
            lbj_traits_paths=[Path("lbj/a.csv"), Path("lbj/b.csv")],
            output_dir=Path("public/data"),
            recommendation_categories_path=Path("curation/categories.csv"),
        )
        self.assertEqual(
            stdout.getvalue().splitlines(),
            [
                "ecoregion_json_files=2",
                "plant_ecoregion_records=3",
                "missing_lbj_traits=1",
            ],
        )


if __name__ == "__main__":
    unittest.main()
