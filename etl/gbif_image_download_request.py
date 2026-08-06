from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd
import requests
from dotenv import load_dotenv

from etl.gbif_download_request import (
    CLEANED_PROBLEMS_FILE_PATH,
    GBIF_IMAGE_REQ_TEMPLATE,
    GBIF_SPECIES_MATCH_CLEANED_FILE_PATH,
    format_download_request,
)


GBIF_DOWNLOAD_REQUEST_URL = "https://api.gbif.org/v1/occurrence/download/request"
DEFAULT_OUTPUT_PATH = Path("datasets/gbif_image_download_request.json")
DEFAULT_EXCLUDED_MATCH_TYPES = ("HIGHERRANK",)


def read_excluded_usage_keys(
    problems_csv_path: str | Path,
    *,
    excluded_match_types: Iterable[str] = DEFAULT_EXCLUDED_MATCH_TYPES,
) -> set[str]:
    problems_path = Path(problems_csv_path)
    if not problems_path.exists():
        return set()

    problems = pd.read_csv(problems_path, dtype=str)
    if "usageKey" not in problems.columns or "matchType" not in problems.columns:
        return set()

    excluded = {match_type.upper() for match_type in excluded_match_types}
    mask = problems["matchType"].fillna("").str.upper().isin(excluded)
    return set(problems.loc[mask, "usageKey"].dropna().astype(str))


def image_taxon_key_rows(
    plants_csv_path: str | Path = GBIF_SPECIES_MATCH_CLEANED_FILE_PATH,
    *,
    problems_csv_path: str | Path | None = CLEANED_PROBLEMS_FILE_PATH,
    excluded_match_types: Iterable[str] = DEFAULT_EXCLUDED_MATCH_TYPES,
) -> pd.DataFrame:
    plants = pd.read_csv(plants_csv_path, dtype=str)
    if "usageKey" not in plants.columns:
        raise ValueError(f"{plants_csv_path} must contain usageKey")

    rows = plants[plants["usageKey"].notna()].copy()
    if problems_csv_path is not None:
        excluded_keys = read_excluded_usage_keys(
            problems_csv_path,
            excluded_match_types=excluded_match_types,
        )
        if excluded_keys:
            rows = rows[~rows["usageKey"].astype(str).isin(excluded_keys)]
    return rows


def sort_taxon_key_values(request: dict) -> dict:
    sorted_request = copy.deepcopy(request)

    for predicate in sorted_request.get("predicate", {}).get("predicates", []):
        if predicate.get("key") == "TAXON_KEY" and isinstance(predicate.get("values"), list):
            predicate["values"] = sorted(
                (str(value) for value in predicate["values"]),
                key=lambda value: int(value) if value.isdigit() else value,
            )
    return sorted_request


def build_image_download_request(
    plants_csv_path: str | Path = GBIF_SPECIES_MATCH_CLEANED_FILE_PATH,
    *,
    problems_csv_path: str | Path | None = CLEANED_PROBLEMS_FILE_PATH,
    template_path: str | Path = GBIF_IMAGE_REQ_TEMPLATE,
    excluded_match_types: Iterable[str] = DEFAULT_EXCLUDED_MATCH_TYPES,
) -> dict:
    taxon_rows = image_taxon_key_rows(
        plants_csv_path,
        problems_csv_path=problems_csv_path,
        excluded_match_types=excluded_match_types,
    )
    request = format_download_request(
        taxon_rows,
        template_path=str(template_path),
    )
    return sort_taxon_key_values(request)


def write_image_download_request(
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    *,
    plants_csv_path: str | Path = GBIF_SPECIES_MATCH_CLEANED_FILE_PATH,
    problems_csv_path: str | Path | None = CLEANED_PROBLEMS_FILE_PATH,
    template_path: str | Path = GBIF_IMAGE_REQ_TEMPLATE,
    excluded_match_types: Iterable[str] = DEFAULT_EXCLUDED_MATCH_TYPES,
) -> dict:
    request = build_image_download_request(
        plants_csv_path,
        problems_csv_path=problems_csv_path,
        template_path=template_path,
        excluded_match_types=excluded_match_types,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    return request


def submit_image_download_request(
    request: Mapping[str, object],
    *,
    username: str | None = None,
    password: str | None = None,
    session: requests.Session | None = None,
) -> str:
    gbif_user = username or os.getenv("GBIF_USER")
    gbif_password = password or os.getenv("GBIF_PWD")
    if not gbif_user or not gbif_password:
        raise RuntimeError("GBIF_USER and GBIF_PWD must be set to submit a download request")

    active_session = session or requests.Session()
    response = active_session.post(
        GBIF_DOWNLOAD_REQUEST_URL,
        json=dict(request),
        auth=(gbif_user, gbif_password),
    )
    response.raise_for_status()
    return response.text.strip()


def load_request(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def positive_or_zero(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and optionally submit a GBIF DWCA request for plant image ETL."
    )
    parser.add_argument("--plants", type=Path, default=GBIF_SPECIES_MATCH_CLEANED_FILE_PATH)
    parser.add_argument("--problems", type=Path, default=CLEANED_PROBLEMS_FILE_PATH)
    parser.add_argument("--template", type=Path, default=GBIF_IMAGE_REQ_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--exclude-match-type",
        action="append",
        default=list(DEFAULT_EXCLUDED_MATCH_TYPES),
        help="Problem matchType to exclude from the TAXON_KEY request. Can be repeated.",
    )
    parser.add_argument(
        "--no-problems",
        action="store_true",
        help="Do not exclude usageKeys from the problems CSV.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit the generated request to GBIF after writing it.",
    )
    parser.add_argument(
        "--skip-dotenv",
        action="store_true",
        help="Do not load .env before submission.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.submit and not args.skip_dotenv:
        load_dotenv()

    problems_path = None if args.no_problems else args.problems
    request = write_image_download_request(
        args.output,
        plants_csv_path=args.plants,
        problems_csv_path=problems_path,
        template_path=args.template,
        excluded_match_types=args.exclude_match_type,
    )

    taxon_values = request["predicate"]["predicates"][0]["values"]
    print(f"wrote={args.output} taxon_keys={len(taxon_values)}")

    if args.submit:
        download_key = submit_image_download_request(request)
        print(f"download_key={download_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
