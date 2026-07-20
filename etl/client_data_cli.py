from __future__ import annotations

import argparse
from pathlib import Path

from etl.client_data import (
    DEFAULT_APP_DATA_DIR,
    DEFAULT_BOUNDARY_TOLERANCE,
    DEFAULT_CLIENT_DATA_DIR,
    DEFAULT_ECOREGIONS_GEOJSON_PATH,
    prepare_client_data,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare static data files for the GitHub Pages client")
    parser.add_argument("--app-data-dir", type=Path, default=DEFAULT_APP_DATA_DIR)
    parser.add_argument("--ecoregions", type=Path, default=DEFAULT_ECOREGIONS_GEOJSON_PATH)
    parser.add_argument("--client-data-dir", type=Path, default=DEFAULT_CLIENT_DATA_DIR)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_BOUNDARY_TOLERANCE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = prepare_client_data(
        app_data_dir=args.app_data_dir,
        ecoregions_geojson_path=args.ecoregions,
        client_data_dir=args.client_data_dir,
        tolerance=args.tolerance,
    )
    print(f"app_data_target={result['appDataTarget']}")
    print(f"boundary_records={result['boundaryCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
