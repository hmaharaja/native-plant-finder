from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from etl.gbif_ecoregions import (
    DEFAULT_ECOREGIONS_GEOJSON_PATH,
    DEFAULT_MATCHED_OCCURRENCES_FILENAME,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PLANT_ECOREGIONS_FILENAME,
    DEFAULT_PLANTS_CSV_PATH,
    DEFAULT_ZIP_PATH,
    run_pipeline,
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build plant/ecoregion evidence from a GBIF occurrence download"
    )
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP_PATH)
    parser.add_argument("--plants", type=Path, default=DEFAULT_PLANTS_CSV_PATH)
    parser.add_argument("--ecoregions", type=Path, default=DEFAULT_ECOREGIONS_GEOJSON_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--matched-occurrences-filename",
        default=DEFAULT_MATCHED_OCCURRENCES_FILENAME,
    )
    parser.add_argument(
        "--plant-ecoregions-filename",
        default=DEFAULT_PLANT_ECOREGIONS_FILENAME,
    )
    parser.add_argument("--chunksize", type=positive_int, default=100_000)
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(levelname)s:%(name)s:%(message)s",
        stream=sys.stdout,
    )
    output = run_pipeline(
        zip_path=args.zip,
        plants_csv_path=args.plants,
        ecoregions_geojson_path=args.ecoregions,
        output_dir=args.output_dir,
        matched_occurrences_filename=args.matched_occurrences_filename,
        plant_ecoregions_filename=args.plant_ecoregions_filename,
        chunksize=args.chunksize,
        limit=args.limit,
    )
    print(f"plant_ecoregion_rows={len(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
