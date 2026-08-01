from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from etl.gbif_images import (
    DEFAULT_BUCKET_COUNT,
    DEFAULT_LIMIT_PER_TAXON,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PLANTS_CSV_PATH,
    build_gbif_image_index,
    build_gbif_image_index_from_dwca,
    read_usage_keys,
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a static GBIF plant image index keyed by usageKey"
    )
    parser.add_argument("--plants", type=Path, default=DEFAULT_PLANTS_CSV_PATH)
    parser.add_argument(
        "--dwca",
        type=Path,
        help="Read occurrence.txt and multimedia.txt from an existing GBIF Darwin Core Archive zip.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit-per-taxon", type=positive_int, default=DEFAULT_LIMIT_PER_TAXON)
    parser.add_argument("--bucket-count", type=positive_int, default=DEFAULT_BUCKET_COUNT)
    parser.add_argument(
        "--limit-usage-keys",
        type=positive_int,
        help="Limit unique usageKeys for smoke runs.",
    )
    parser.add_argument(
        "--skip-url-validation",
        action="store_true",
        help="Do not validate image URLs. Intended only for offline development fixtures.",
    )
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
    usage_keys = read_usage_keys(args.plants)
    if args.limit_usage_keys is not None:
        usage_keys = usage_keys[: args.limit_usage_keys]
    if args.dwca is not None:
        report = build_gbif_image_index_from_dwca(
            usage_keys,
            args.dwca,
            args.output_dir,
            validate_urls=not args.skip_url_validation,
            bucket_count=args.bucket_count,
        )
    else:
        report = build_gbif_image_index(
            usage_keys,
            args.output_dir,
            limit_per_taxon=args.limit_per_taxon,
            validate_urls=not args.skip_url_validation,
            bucket_count=args.bucket_count,
        )
    print(
        " ".join(
            [
                f"usage_keys_checked={report['uniqueUsageKeysChecked']}",
                f"accepted={report['usageKeysWithAcceptedImage']}",
                f"missing={report['usageKeysWithoutAcceptedImage']}",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
