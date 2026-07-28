from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Iterable

import pandas as pd

from dataset_columns import (
    APP_DATA_ARRAY_FIELDS,
    APP_DATA_FIELD_MAP,
    APP_DATA_FLOAT_FIELDS,
    APP_DATA_INT_FIELDS,
    APP_DATA_LBJ_TRAIT_COLUMNS,
    CANONICAL_NAME,
    ECOREGION_ID,
    ECOREGION_NAME,
    RECOMMENDATION_CATEGORY,
    RecommendationCategory,
    USAGE_KEY,
    VERNACULAR_NAME,
)
from etl.functions import normalize_key


LOGGER = logging.getLogger(__name__)

DEFAULT_PLANT_ECOREGIONS_PATH = Path("datasets/derived/plant_ecoregions.csv")
DEFAULT_LBJ_TRAITS_PATHS = [
    Path("datasets/lbj/lbj_traits.csv"),
    Path("datasets/lbj_rerun/lbj_traits.csv"),
]
DEFAULT_OUTPUT_DIR = Path("datasets/app_data")
DEFAULT_RECOMMENDATION_CATEGORIES_PATH = Path("curation/recommendation_categories.csv")
RECOMMENDATION_CATEGORIES = frozenset(category.value for category in RecommendationCategory)

def lbj_enrichment_mask(rows: pd.DataFrame) -> pd.Series:
    """Return the production enrichment predicate: any non-key app LBJ field is present."""
    value_columns = [
        column
        for column in APP_DATA_LBJ_TRAIT_COLUMNS
        if column != USAGE_KEY and column in rows.columns
    ]
    if not value_columns:
        return pd.Series(False, index=rows.index, dtype=bool)
    return rows[value_columns].notna().any(axis=1)


def read_recommendation_categories(path: str | Path) -> pd.DataFrame:
    """Read and strictly validate the local recommendation-category mapping."""
    categories = pd.read_csv(path, dtype=str)
    required = {USAGE_KEY, RECOMMENDATION_CATEGORY}
    missing_columns = required.difference(categories.columns)
    if missing_columns:
        raise ValueError(
            "recommendation categories missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    categories = categories.copy()
    categories[USAGE_KEY] = categories[USAGE_KEY].map(normalize_key)
    categories[RECOMMENDATION_CATEGORY] = categories[RECOMMENDATION_CATEGORY].map(
        lambda value: value.strip() if isinstance(value, str) else value
    )
    if categories[USAGE_KEY].isna().any():
        raise ValueError("recommendation categories contain a missing or invalid usageKey")
    duplicate_keys = categories.loc[
        categories[USAGE_KEY].duplicated(keep=False), USAGE_KEY
    ].unique()
    if len(duplicate_keys):
        raise ValueError(
            "duplicate recommendation category usageKey values: "
            + ", ".join(sorted(duplicate_keys))
        )
    invalid = sorted(
        set(categories[RECOMMENDATION_CATEGORY].dropna()).difference(
            RECOMMENDATION_CATEGORIES
        )
    )
    if categories[RECOMMENDATION_CATEGORY].isna().any() or invalid:
        values = ", ".join(invalid) if invalid else "<missing>"
        raise ValueError(f"invalid recommendation categories: {values}")
    return categories[[USAGE_KEY, RECOMMENDATION_CATEGORY]].reset_index(drop=True)

def read_lbj_traits(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Read LBJ traits, preferring later files for duplicate usageKey values."""
    frames = []
    for path in paths:
        frame = pd.read_csv(path, dtype=str)
        frame[USAGE_KEY] = frame[USAGE_KEY].map(normalize_key)
        frame = frame[frame[USAGE_KEY].notna()].copy()
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=APP_DATA_LBJ_TRAIT_COLUMNS)

    combined = pd.concat(frames, ignore_index=True)
    available_columns = [column for column in APP_DATA_LBJ_TRAIT_COLUMNS if column in combined.columns]
    combined = combined[available_columns]
    return combined.drop_duplicates(subset=[USAGE_KEY], keep="last").reset_index(drop=True)


def merge_plant_ecoregions_with_traits(
    plant_ecoregions: pd.DataFrame,
    lbj_traits: pd.DataFrame,
    recommendation_categories: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows = plant_ecoregions.copy()
    rows[USAGE_KEY] = rows[USAGE_KEY].map(normalize_key)

    traits = lbj_traits.copy()
    if USAGE_KEY in traits.columns:
        traits[USAGE_KEY] = traits[USAGE_KEY].map(normalize_key)

    trait_columns = [column for column in APP_DATA_LBJ_TRAIT_COLUMNS if column in traits.columns]
    merged = rows.merge(traits[trait_columns], on=USAGE_KEY, how="left")
    if recommendation_categories is None:
        merged[RECOMMENDATION_CATEGORY] = pd.NA
        return merged

    category_rows = recommendation_categories[[USAGE_KEY, RECOMMENDATION_CATEGORY]].copy()
    category_rows[USAGE_KEY] = category_rows[USAGE_KEY].map(normalize_key)
    category_by_key = category_rows.set_index(USAGE_KEY)[RECOMMENDATION_CATEGORY]
    enriched = lbj_enrichment_mask(merged)
    missing_keys = sorted(
        set(merged.loc[~enriched, USAGE_KEY].dropna()).difference(category_by_key.index)
    )
    if missing_keys:
        preview = ", ".join(missing_keys[:10])
        suffix = "..." if len(missing_keys) > 10 else ""
        raise ValueError(
            f"missing recommendation categories for {len(missing_keys)} app-relevant "
            f"unenriched species: {preview}{suffix}"
        )
    merged[RECOMMENDATION_CATEGORY] = merged[USAGE_KEY].map(category_by_key)
    merged.loc[enriched, RECOMMENDATION_CATEGORY] = pd.NA
    return merged


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return pd.isna(value)


def _to_array(value: object) -> list[str]:
    if _is_missing(value):
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def _to_number(value: object, integer: bool = False) -> int | float | None:
    if _is_missing(value) or str(value).strip() == "":
        return None
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    if integer:
        return int(number)
    float_value = float(number)
    rounded = round(float_value, 2)
    return int(rounded) if rounded.is_integer() else rounded


def _to_scalar(value: object) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text if text else None


def plant_record_from_row(row: pd.Series) -> dict:
    record = {}
    for source, target in APP_DATA_FIELD_MAP.items():
        value = row[source] if source in row.index else None
        if target in APP_DATA_ARRAY_FIELDS:
            record[target] = _to_array(value)
        elif target in APP_DATA_INT_FIELDS:
            record[target] = _to_number(value, integer=True)
        elif target in APP_DATA_FLOAT_FIELDS:
            record[target] = _to_number(value)
        else:
            record[target] = _to_scalar(value)
    return record


def build_ecoregion_payloads(plant_traits: pd.DataFrame) -> list[dict]:
    rows = plant_traits.copy()
    rows["_sort_vernacular"] = rows[VERNACULAR_NAME].fillna("").str.lower()
    rows["_sort_canonical"] = rows[CANONICAL_NAME].fillna("").str.lower()
    rows["_sort_ecoregion_id"] = pd.to_numeric(rows[ECOREGION_ID], errors="coerce")
    rows = rows.sort_values(
        ["_sort_ecoregion_id", ECOREGION_ID, "_sort_vernacular", "_sort_canonical"]
    )

    payloads = []
    for ecoregion_id, group in rows.groupby(ECOREGION_ID, dropna=False, sort=False):
        ecoregion_id_value = _to_number(ecoregion_id, integer=True)
        plants = [plant_record_from_row(row) for _, row in group.iterrows()]
        ecoregion_name = (
            _to_scalar(group[ECOREGION_NAME].dropna().iloc[0])
            if group[ECOREGION_NAME].notna().any()
            else None
        )
        payloads.append(
            {
                "ecoregionId": ecoregion_id_value,
                "ecoregionName": ecoregion_name,
                "plantCount": len(plants),
                "plants": plants,
            }
        )
    return payloads


def write_app_data(
    plant_ecoregions: pd.DataFrame,
    lbj_traits: pd.DataFrame,
    output_dir: str | Path,
    recommendation_categories: pd.DataFrame | None = None,
) -> dict:
    output_dir = Path(output_dir)
    ecoregion_dir = output_dir / "ecoregions"
    ecoregion_dir.mkdir(parents=True, exist_ok=True)

    merged = merge_plant_ecoregions_with_traits(
        plant_ecoregions, lbj_traits, recommendation_categories
    )
    trait_presence = merged[
        [
            column
            for column in APP_DATA_LBJ_TRAIT_COLUMNS
            if column in merged.columns and column != USAGE_KEY
        ]
    ]
    missing_lbj_traits = int(trait_presence.isna().all(axis=1).sum()) if not trait_presence.empty else len(merged)

    manifest_entries = []
    for payload in build_ecoregion_payloads(merged):
        file_name = f"{payload['ecoregionId']}.json"
        relative_path = f"ecoregions/{file_name}"
        path = ecoregion_dir / file_name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_entries.append(
            {
                "ecoregionId": payload["ecoregionId"],
                "ecoregionName": payload["ecoregionName"],
                "path": relative_path,
                "plantCount": payload["plantCount"],
            }
        )

    manifest = {
        "ecoregionCount": len(manifest_entries),
        "plantEcoregionCount": len(merged),
        "missingLbjTraitCount": missing_lbj_traits,
        "ecoregions": manifest_entries,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_app_data(
    plant_ecoregions_path: str | Path = DEFAULT_PLANT_ECOREGIONS_PATH,
    lbj_traits_paths: Iterable[str | Path] = DEFAULT_LBJ_TRAITS_PATHS,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    recommendation_categories_path: str | Path = DEFAULT_RECOMMENDATION_CATEGORIES_PATH,
) -> dict:
    plant_ecoregions = pd.read_csv(plant_ecoregions_path, dtype=str)
    lbj_traits = read_lbj_traits(lbj_traits_paths)
    recommendation_categories = read_recommendation_categories(
        recommendation_categories_path
    )

    LOGGER.info(
        "plant ecoregion input rows=%s path=%s",
        len(plant_ecoregions),
        plant_ecoregions_path,
    )
    LOGGER.info("combined unique LBJ trait rows=%s", len(lbj_traits))

    manifest = write_app_data(
        plant_ecoregions, lbj_traits, output_dir, recommendation_categories
    )
    LOGGER.info("ecoregion JSON files written=%s", manifest["ecoregionCount"])
    LOGGER.info("plant/ecoregion records written=%s", manifest["plantEcoregionCount"])
    LOGGER.info("plant/ecoregion records missing LBJ traits=%s", manifest["missingLbjTraitCount"])
    return manifest
