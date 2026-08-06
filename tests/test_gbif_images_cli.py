from __future__ import annotations

import io
import logging
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from etl.gbif_images_cli import main


class GbifImagesCliTests(unittest.TestCase):
    def test_main_configures_logging_reads_usage_keys_and_prints_report(self):
        with patch("etl.gbif_images_cli.read_usage_keys", return_value=["100", "200"]) as read_keys, patch(
            "etl.gbif_images_cli.read_problem_usage_keys", return_value=set()
        ), patch(
            "etl.gbif_images_cli.build_gbif_image_index",
            return_value={
                "uniqueUsageKeysChecked": 2,
                "usageKeysWithAcceptedImage": 1,
                "usageKeysWithoutAcceptedImage": 1,
            },
        ) as build_index, patch(
            "etl.gbif_images_cli.build_gbif_image_index_from_dwca",
        ) as build_dwca_index, patch.object(logging, "basicConfig") as basic_config, patch(
            "sys.stdout", new=io.StringIO()
        ) as stdout:
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        basic_config.assert_called_once()
        self.assertEqual(basic_config.call_args.kwargs["level"], "INFO")
        read_keys.assert_called_once_with(Path("datasets/gbif_species_match_cleaned.csv"))
        build_index.assert_called_once()
        build_dwca_index.assert_not_called()
        self.assertEqual(build_index.call_args.args[0], ["100", "200"])
        self.assertEqual(build_index.call_args.args[1], Path("datasets/app_data/plant_images"))
        self.assertEqual(stdout.getvalue().strip(), "usage_keys_checked=2 accepted=1 missing=1")

    def test_main_forwards_custom_paths_limits_and_validation_flag(self):
        with patch("etl.gbif_images_cli.read_usage_keys", return_value=["100", "200", "300"]), patch(
            "etl.gbif_images_cli.read_problem_usage_keys", return_value=set()
        ), patch(
            "etl.gbif_images_cli.build_gbif_image_index",
            return_value={
                "uniqueUsageKeysChecked": 1,
                "usageKeysWithAcceptedImage": 1,
                "usageKeysWithoutAcceptedImage": 0,
            },
        ) as build_index, patch.object(logging, "basicConfig"), patch(
            "sys.stdout", new=io.StringIO()
        ):
            exit_code = main(
                [
                    "--plants",
                    "data/plants.csv",
                    "--output-dir",
                    "out/images",
                    "--limit-per-taxon",
                    "7",
                    "--bucket-count",
                    "8",
                    "--limit-usage-keys",
                    "1",
                    "--skip-url-validation",
                    "--delay-between-taxa",
                    "0",
                    "--delay-between-url-checks",
                    "0",
                    "--user-agent",
                    "native-plant-finder-test/1.0",
                    "--log-level",
                    "DEBUG",
                ]
            )

        self.assertEqual(exit_code, 0)
        build_index.assert_called_once_with(
            ["100"],
            Path("out/images"),
            limit_per_taxon=7,
            validate_urls=False,
            bucket_count=8,
            delay_between_taxa=0.0,
            delay_between_url_checks=0.0,
            user_agent="native-plant-finder-test/1.0",
        )

    def test_main_routes_dwca_argument_to_dwca_builder(self):
        with patch("etl.gbif_images_cli.read_usage_keys", return_value=["100", "200"]) as read_keys, patch(
            "etl.gbif_images_cli.read_problem_usage_keys", return_value=set()
        ), patch(
            "etl.gbif_images_cli.build_gbif_image_index"
        ) as build_index, patch(
            "etl.gbif_images_cli.build_gbif_image_index_from_dwca",
            return_value={
                "uniqueUsageKeysChecked": 2,
                "usageKeysWithAcceptedImage": 1,
                "usageKeysWithoutAcceptedImage": 1,
            },
        ) as build_dwca_index, patch.object(logging, "basicConfig"), patch(
            "sys.stdout", new=io.StringIO()
        ):
            exit_code = main(["--dwca", "datasets/gbif.zip", "--output-dir", "out/images"])

        self.assertEqual(exit_code, 0)
        read_keys.assert_called_once_with(Path("datasets/gbif_species_match_cleaned.csv"))
        build_index.assert_not_called()
        build_dwca_index.assert_called_once_with(
            ["100", "200"],
            Path("datasets/gbif.zip"),
            Path("out/images"),
            validate_urls=True,
            bucket_count=64,
            delay_between_url_checks=0.25,
            user_agent=ANY,
        )

    def test_main_excludes_problem_keys_before_offset_and_limit(self):
        with patch("etl.gbif_images_cli.read_usage_keys", return_value=["100", "200", "300", "400"]), patch(
            "etl.gbif_images_cli.read_problem_usage_keys", return_value={"200"}
        ) as read_problems, patch(
            "etl.gbif_images_cli.build_gbif_image_index",
            return_value={
                "uniqueUsageKeysChecked": 2,
                "usageKeysWithAcceptedImage": 0,
                "usageKeysWithoutAcceptedImage": 2,
            },
        ) as build_index, patch.object(logging, "basicConfig"), patch(
            "sys.stdout", new=io.StringIO()
        ):
            main(
                [
                    "--problems",
                    "data/problems.csv",
                    "--usage-key-offset",
                    "1",
                    "--limit-usage-keys",
                    "2",
                ]
            )

        read_problems.assert_called_once_with(Path("data/problems.csv"))
        self.assertEqual(build_index.call_args.args[0], ["300", "400"])

    def test_main_include_problem_keys_preserves_current_key_selection(self):
        with patch("etl.gbif_images_cli.read_usage_keys", return_value=["100", "200"]), patch(
            "etl.gbif_images_cli.read_problem_usage_keys"
        ) as read_problems, patch(
            "etl.gbif_images_cli.build_gbif_image_index",
            return_value={
                "uniqueUsageKeysChecked": 2,
                "usageKeysWithAcceptedImage": 0,
                "usageKeysWithoutAcceptedImage": 2,
            },
        ) as build_index, patch.object(logging, "basicConfig"), patch(
            "sys.stdout", new=io.StringIO()
        ):
            main(["--include-problem-keys"])

        read_problems.assert_not_called()
        self.assertEqual(build_index.call_args.args[0], ["100", "200"])


if __name__ == "__main__":
    unittest.main()
