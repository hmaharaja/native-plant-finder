from __future__ import annotations

import io
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from etl.gbif_ecoregions_cli import main


class GbifEcoregionsCliTests(unittest.TestCase):
    def test_main_configures_logging_and_forwards_defaults(self):
        with patch(
            "etl.gbif_ecoregions_cli.run_pipeline",
            return_value=pd.DataFrame([{"usageKey": "100", "ecoregion_id": 7}]),
        ) as run_pipeline, patch.object(logging, "basicConfig") as basic_config, patch(
            "sys.stdout", new=io.StringIO()
        ) as stdout:
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        basic_config.assert_called_once()
        self.assertEqual(basic_config.call_args.kwargs["level"], "INFO")
        self.assertEqual(stdout.getvalue().strip(), "plant_ecoregion_rows=1")
        run_pipeline.assert_called_once()
        self.assertEqual(run_pipeline.call_args.kwargs["zip_path"], Path("datasets/0026180-260623161305970.zip"))
        self.assertEqual(run_pipeline.call_args.kwargs["limit"], None)

    def test_main_forwards_custom_limit_paths_and_filenames(self):
        with patch(
            "etl.gbif_ecoregions_cli.run_pipeline",
            return_value=pd.DataFrame(),
        ) as run_pipeline, patch.object(logging, "basicConfig"), patch(
            "sys.stdout", new=io.StringIO()
        ):
            exit_code = main(
                [
                    "--zip",
                    "data/source.zip",
                    "--plants",
                    "data/plants.csv",
                    "--ecoregions",
                    "data/ecoregions.geojson",
                    "--output-dir",
                    "out",
                    "--matched-occurrences-filename",
                    "matched-test.parquet",
                    "--plant-ecoregions-filename",
                    "plant-ecoregions-test.csv",
                    "--chunksize",
                    "25",
                    "--limit",
                    "100",
                    "--log-level",
                    "DEBUG",
                ]
            )

        self.assertEqual(exit_code, 0)
        run_pipeline.assert_called_once_with(
            zip_path=Path("data/source.zip"),
            plants_csv_path=Path("data/plants.csv"),
            ecoregions_geojson_path=Path("data/ecoregions.geojson"),
            output_dir=Path("out"),
            matched_occurrences_filename="matched-test.parquet",
            plant_ecoregions_filename="plant-ecoregions-test.csv",
            chunksize=25,
            limit=100,
        )


if __name__ == "__main__":
    unittest.main()
