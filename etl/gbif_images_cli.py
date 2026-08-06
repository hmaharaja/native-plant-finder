from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from etl.gbif_images import (
    DEFAULT_BUCKET_COUNT,
    DEFAULT_DELAY_BETWEEN_TAXA,
    DEFAULT_DELAY_BETWEEN_URL_CHECKS,
    DEFAULT_LIMIT_PER_TAXON,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PLANTS_CSV_PATH,
    DEFAULT_PROBLEMS_CSV_PATH,
    build_gbif_image_index,
    build_gbif_image_index_from_dwca,
    default_user_agent,
    filter_usage_keys,
    read_problem_usage_keys,
    read_usage_keys,
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative number")
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
    parser.add_argument(
        "--problems",
        type=Path,
        default=DEFAULT_PROBLEMS_CSV_PATH,
        help="Problems CSV used to exclude HIGHERRANK usageKeys in API and DWCA runs.",
    )
    parser.add_argument("--limit-per-taxon", type=positive_int, default=DEFAULT_LIMIT_PER_TAXON)
    parser.add_argument("--bucket-count", type=positive_int, default=DEFAULT_BUCKET_COUNT)
    parser.add_argument(
        "--limit-usage-keys",
        type=positive_int,
        help="Limit unique usageKeys for smoke runs.",
    )
    parser.add_argument(
        "--usage-key-offset",
        type=non_negative_int,
        default=0,
        help="Skip this many filtered usageKeys before applying --limit-usage-keys.",
    )
    parser.add_argument(
        "--include-problem-keys",
        action="store_true",
        help="Include usageKeys flagged as HIGHERRANK in the problems CSV.",
    )
    parser.add_argument(
        "--delay-between-taxa",
        type=non_negative_float,
        default=DEFAULT_DELAY_BETWEEN_TAXA,
    )
    parser.add_argument(
        "--delay-between-url-checks",
        type=non_negative_float,
        default=DEFAULT_DELAY_BETWEEN_URL_CHECKS,
    )
    parser.add_argument(
        "--user-agent",
        default=default_user_agent(),
        help="User-Agent for GBIF and image URL requests. Defaults to GBIF_USER_AGENT or a repo fallback.",
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
    excluded_usage_keys = set()
    if not args.include_problem_keys:
        excluded_usage_keys = read_problem_usage_keys(args.problems)
        if excluded_usage_keys:
            logging.getLogger(__name__).info(
                "Excluding %s problem usageKeys from %s",
                len(excluded_usage_keys),
                args.problems,
            )
    usage_keys = filter_usage_keys(
        usage_keys,
        excluded_usage_keys=excluded_usage_keys,
        offset=args.usage_key_offset,
        limit=args.limit_usage_keys,
    )
    if args.dwca is not None:
        report = build_gbif_image_index_from_dwca(
            usage_keys,
            args.dwca,
            args.output_dir,
            validate_urls=not args.skip_url_validation,
            bucket_count=args.bucket_count,
            delay_between_url_checks=args.delay_between_url_checks,
            user_agent=args.user_agent,
        )
    else:
        report = build_gbif_image_index(
            usage_keys,
            args.output_dir,
            limit_per_taxon=args.limit_per_taxon,
            validate_urls=not args.skip_url_validation,
            bucket_count=args.bucket_count,
            delay_between_taxa=args.delay_between_taxa,
            delay_between_url_checks=args.delay_between_url_checks,
            user_agent=args.user_agent,
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
