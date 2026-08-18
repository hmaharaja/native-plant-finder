from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import pandas as pd

from dataset_columns import (
    CANONICAL_NAME,
    IMAGE_GBIF_ID,
    IMAGE_LICENSE,
    IMAGE_SOURCE,
    IMAGE_SOURCE_URL,
    IMAGE_URL,
    USAGE_KEY,
    VERNACULAR_NAME,
)
from etl.functions import normalize_key


DEFAULT_BUCKET_DIR = Path("datasets/app_data/plant_images/buckets")
DEFAULT_PLANTS_CSV_PATH = Path("datasets/derived/plant_ecoregions.csv")
DEFAULT_REVIEW_CSV_PATH = Path("docs/plant-images-secondary-variety-review.csv")
DEFAULT_REPORT_PATH = Path("docs/plant-images-carousel-evaluation.md")

VISUAL_ROLE_FIELDS = (
    "visualRole",
    "visualRoles",
    "visualClassification",
    "visualClass",
    "contentRole",
    "contentRoles",
    "imageRole",
    "imageRoles",
    "plantPart",
    "plantParts",
    "subject",
    "subjects",
)

REVIEW_CSV_FIELDS = [
    USAGE_KEY,
    CANONICAL_NAME,
    VERNACULAR_NAME,
    "primaryImageUrl",
    "secondaryImageUrl",
    "primarySourceUrl",
    "secondarySourceUrl",
    "primaryGbifId",
    "secondaryGbifId",
    "primarySource",
    "secondarySource",
    "primaryLicense",
    "secondaryLicense",
    "primaryVisualRole",
    "secondaryVisualRole",
    "primaryExplicitVisualRoleField",
    "secondaryExplicitVisualRoleField",
    "sameImageUrl",
    "sameGbifId",
    "visualRoleReviewStatus",
    "reviewerVisualVariety",
    "reviewerNotes",
]


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _normalized_url(value: object) -> str | None:
    text = _text(value)
    return text.casefold() if text else None


def _normalized_role_values(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        parts = value
    else:
        parts = str(value).replace("|", ";").split(";")
    return {str(part).strip().casefold() for part in parts if str(part).strip()}


def explicit_visual_role(image: Mapping[str, object] | None) -> tuple[str | None, str | None, set[str]]:
    if not image:
        return None, None, set()
    for field in VISUAL_ROLE_FIELDS:
        if field not in image:
            continue
        roles = _normalized_role_values(image.get(field))
        if roles:
            return field, _text(image.get(field)), roles
    return None, None, set()


def read_image_index(bucket_dir: str | Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for path in sorted(Path(bucket_dir).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"{path} must contain an object keyed by usageKey")
        for raw_usage_key, record in payload.items():
            usage_key = normalize_key(raw_usage_key)
            if usage_key is None:
                raise ValueError(f"{path} contains an invalid usageKey: {raw_usage_key!r}")
            if usage_key in records:
                raise ValueError(f"duplicate plant image usageKey: {usage_key}")
            if not isinstance(record, Mapping):
                raise ValueError(f"{path} record for usageKey {usage_key} must be an object")
            records[usage_key] = dict(record)
    return records


def read_plant_names(path: str | Path | None) -> dict[str, dict[str, str]]:
    if path is None or not Path(path).exists():
        return {}
    rows = pd.read_csv(path, dtype=str)
    if USAGE_KEY not in rows.columns:
        return {}
    available = [column for column in (USAGE_KEY, CANONICAL_NAME, VERNACULAR_NAME) if column in rows.columns]
    names = rows[available].copy()
    names[USAGE_KEY] = names[USAGE_KEY].map(normalize_key)
    names = names[names[USAGE_KEY].notna()].drop_duplicates(subset=[USAGE_KEY], keep="first")
    return {
        str(row[USAGE_KEY]): {
            CANONICAL_NAME: _text(row.get(CANONICAL_NAME)),
            VERNACULAR_NAME: _text(row.get(VERNACULAR_NAME)),
        }
        for row in names.to_dict("records")
    }


def _source_license_key(image: Mapping[str, object]) -> str:
    source = _text(image.get(IMAGE_SOURCE)) or "unknown"
    license_name = _text(image.get(IMAGE_LICENSE)) or "unknown"
    return f"{source} / {license_name}"


def _accepted_images(records: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    images: list[Mapping[str, object]] = []
    for record in records:
        for slot in ("primaryImage", "secondaryImage"):
            image = record.get(slot)
            if isinstance(image, Mapping):
                images.append(image)
    return images


def build_audit(records: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    image_backed_records = [
        record
        for record in records.values()
        if isinstance(record.get("primaryImage"), Mapping)
    ]
    secondary_records = [
        record
        for record in image_backed_records
        if isinstance(record.get("secondaryImage"), Mapping)
    ]
    accepted_images = _accepted_images(image_backed_records)

    duplicate_url_pair_count = 0
    same_gbif_id_pair_count = 0
    secondary_pairs_missing_visual_classification_count = 0
    classified_secondary_pair_count = 0
    complementary_visual_role_pair_count = 0

    for record in secondary_records:
        primary = record.get("primaryImage")
        secondary = record.get("secondaryImage")
        primary_url = _normalized_url(primary.get(IMAGE_URL) if isinstance(primary, Mapping) else None)
        secondary_url = _normalized_url(secondary.get(IMAGE_URL) if isinstance(secondary, Mapping) else None)
        if primary_url and secondary_url and primary_url == secondary_url:
            duplicate_url_pair_count += 1
        primary_gbif_id = _text(primary.get(IMAGE_GBIF_ID) if isinstance(primary, Mapping) else None)
        secondary_gbif_id = _text(secondary.get(IMAGE_GBIF_ID) if isinstance(secondary, Mapping) else None)
        if primary_gbif_id and secondary_gbif_id and primary_gbif_id == secondary_gbif_id:
            same_gbif_id_pair_count += 1

        _, _, primary_roles = explicit_visual_role(primary if isinstance(primary, Mapping) else None)
        _, _, secondary_roles = explicit_visual_role(secondary if isinstance(secondary, Mapping) else None)
        if primary_roles and secondary_roles:
            classified_secondary_pair_count += 1
            if primary_roles != secondary_roles:
                complementary_visual_role_pair_count += 1
        else:
            secondary_pairs_missing_visual_classification_count += 1

    url_counts = Counter(
        url
        for url in (_normalized_url(image.get(IMAGE_URL)) for image in accepted_images)
        if url
    )
    repeated_url_slot_count = sum(count - 1 for count in url_counts.values() if count > 1)
    missing_visual_image_count = sum(
        1 for image in accepted_images if not explicit_visual_role(image)[2]
    )
    source_license = Counter(_source_license_key(image) for image in accepted_images)

    image_backed_count = len(image_backed_records)
    secondary_count = len(secondary_records)
    return {
        "imageBackedPlantCount": image_backed_count,
        "plantsWithSecondaryImage": secondary_count,
        "secondaryImagePercent": round((secondary_count / image_backed_count * 100), 1) if image_backed_count else 0.0,
        "acceptedImageCount": len(accepted_images),
        "duplicateUrlPairCount": duplicate_url_pair_count,
        "acceptedRepeatedUrlSlotCount": repeated_url_slot_count,
        "sameGbifIdPairCount": same_gbif_id_pair_count,
        "sourceLicenseBreakdown": dict(sorted(source_license.items())),
        "missingExplicitVisualClassificationCount": missing_visual_image_count,
        "secondaryPairsMissingVisualClassificationCount": secondary_pairs_missing_visual_classification_count,
        "classifiedSecondaryPairCount": classified_secondary_pair_count,
        "complementaryVisualRolePairCount": complementary_visual_role_pair_count,
    }


def secondary_review_rows(
    records: Mapping[str, Mapping[str, object]],
    plant_names: Mapping[str, Mapping[str, str]] | None = None,
) -> list[dict[str, object]]:
    rows = []
    plant_names = plant_names or {}
    for usage_key in sorted(records, key=lambda value: int(value) if value.isdigit() else value):
        record = records[usage_key]
        primary = record.get("primaryImage")
        secondary = record.get("secondaryImage")
        if not isinstance(primary, Mapping) or not isinstance(secondary, Mapping):
            continue
        primary_role_field, primary_role, primary_roles = explicit_visual_role(primary)
        secondary_role_field, secondary_role, secondary_roles = explicit_visual_role(secondary)
        names = plant_names.get(usage_key, {})
        row = {
            USAGE_KEY: usage_key,
            CANONICAL_NAME: names.get(CANONICAL_NAME, ""),
            VERNACULAR_NAME: names.get(VERNACULAR_NAME, ""),
            "primaryImageUrl": _text(primary.get(IMAGE_URL)),
            "secondaryImageUrl": _text(secondary.get(IMAGE_URL)),
            "primarySourceUrl": _text(primary.get(IMAGE_SOURCE_URL)),
            "secondarySourceUrl": _text(secondary.get(IMAGE_SOURCE_URL)),
            "primaryGbifId": _text(primary.get(IMAGE_GBIF_ID)),
            "secondaryGbifId": _text(secondary.get(IMAGE_GBIF_ID)),
            "primarySource": _text(primary.get(IMAGE_SOURCE)),
            "secondarySource": _text(secondary.get(IMAGE_SOURCE)),
            "primaryLicense": _text(primary.get(IMAGE_LICENSE)),
            "secondaryLicense": _text(secondary.get(IMAGE_LICENSE)),
            "primaryVisualRole": primary_role or "",
            "secondaryVisualRole": secondary_role or "",
            "primaryExplicitVisualRoleField": primary_role_field or "",
            "secondaryExplicitVisualRoleField": secondary_role_field or "",
            "sameImageUrl": _normalized_url(primary.get(IMAGE_URL)) == _normalized_url(secondary.get(IMAGE_URL)),
            "sameGbifId": _text(primary.get(IMAGE_GBIF_ID)) == _text(secondary.get(IMAGE_GBIF_ID)),
            "visualRoleReviewStatus": "classified" if primary_roles and secondary_roles else "needs_manual_classification",
            "reviewerVisualVariety": "",
            "reviewerNotes": "",
        }
        rows.append(row)
    return rows


def write_review_csv(rows: Sequence[Mapping[str, object]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(audit: Mapping[str, object], *, review_csv_path: str | Path = DEFAULT_REVIEW_CSV_PATH) -> str:
    source_license = audit.get("sourceLicenseBreakdown") or {}
    lines = [
        "# Plant images carousel evaluation",
        "",
        "**Recommendation: DEFER / NO-GO for Phase 5 carousel UI.**",
        "",
        "The current image buckets prove that many plants have a second accepted image, but they do not prove that the second image adds a distinct visual role. Under the Phase 5 decision rule, carousel UX needs explicit evidence such as flower, foliage, fruit, whole plant, bark, seed, or similar classification. URL, dimensions, publisher, and occurrence metadata are not enough.",
        "",
        "## Audit summary",
        "",
        f"- Image-backed plants: {int(audit['imageBackedPlantCount']):,}",
        f"- Plants with `secondaryImage`: {int(audit['plantsWithSecondaryImage']):,} ({float(audit['secondaryImagePercent']):.1f}%)",
        f"- Accepted image records: {int(audit['acceptedImageCount']):,}",
        f"- Primary/secondary duplicate URL pairs: {int(audit['duplicateUrlPairCount']):,}",
        f"- Repeated accepted image URL slots across the index: {int(audit['acceptedRepeatedUrlSlotCount']):,}",
        f"- Primary/secondary pairs with the same `gbifId`: {int(audit['sameGbifIdPairCount']):,}",
        f"- Accepted images missing explicit visual classification: {int(audit['missingExplicitVisualClassificationCount']):,}",
        f"- Secondary pairs missing visual classification on one or both images: {int(audit['secondaryPairsMissingVisualClassificationCount']):,}",
        f"- Classified secondary pairs with complementary roles: {int(audit['complementaryVisualRolePairCount']):,}",
        "",
        "## Source and license breakdown",
        "",
        "| Source / license | Accepted images |",
        "|---|---:|",
    ]
    for key, count in source_license.items():
        lines.append(f"| `{key}` | {int(count):,} |")
    lines.extend(
        [
            "",
            "## Review artifact",
            "",
            f"- Secondary-image review CSV: `{Path(review_csv_path).as_posix()}`",
            "- The CSV is keyed by `usageKey`, includes plant names when available, primary/secondary image URLs, source links, source/license metadata, duplicate/same-occurrence flags, and empty reviewer fields for manual visual-variety classification.",
            "",
            "## Decision",
            "",
            "Phase 5 should not ship carousel UI from the current data alone. Secondary-image coverage is high enough to investigate further, but the strict visual-variety evidence is absent. A later phase can move to `GO` only after accepted records or a manual review layer contains explicit complementary visual roles for most image-backed plants with two images.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate whether plant image data justifies carousel UI.")
    parser.add_argument("--bucket-dir", type=Path, default=DEFAULT_BUCKET_DIR)
    parser.add_argument("--plants", type=Path, default=DEFAULT_PLANTS_CSV_PATH)
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records = read_image_index(args.bucket_dir)
    plant_names = read_plant_names(args.plants)
    audit = build_audit(records)
    rows = secondary_review_rows(records, plant_names)
    write_review_csv(rows, args.review_csv)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        render_markdown(audit, review_csv_path=args.review_csv) + "\n",
        encoding="utf-8",
    )
    print(
        " ".join(
            [
                f"image_backed={audit['imageBackedPlantCount']}",
                f"secondary={audit['plantsWithSecondaryImage']}",
                f"secondary_percent={audit['secondaryImagePercent']:.1f}",
                f"missing_visual_classification={audit['missingExplicitVisualClassificationCount']}",
                "recommendation=DEFER/NO-GO",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
