from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from etl.app_data import (
    DEFAULT_LBJ_TRAITS_PATHS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PLANT_ECOREGIONS_PATH,
    build_app_data,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build static app JSON files for plant ecoregion lookup"
    )
    parser.add_argument("--plant-ecoregions", type=Path, default=DEFAULT_PLANT_ECOREGIONS_PATH)
    parser.add_argument(
        "--lbj-traits",
        type=Path,
        action="append",
        default=None,
        help="LBJ traits CSV path. Pass multiple times; later files win on duplicate usageKey.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
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
    manifest = build_app_data(
        plant_ecoregions_path=args.plant_ecoregions,
        lbj_traits_paths=args.lbj_traits or DEFAULT_LBJ_TRAITS_PATHS,
        output_dir=args.output_dir,
    )
    print(f"ecoregion_json_files={manifest['ecoregionCount']}")
    print(f"plant_ecoregion_records={manifest['plantEcoregionCount']}")
    print(f"missing_lbj_traits={manifest['missingLbjTraitCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
