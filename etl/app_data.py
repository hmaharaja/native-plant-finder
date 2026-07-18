from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Iterable

import pandas as pd

from etl.functions import normalize_key


LOGGER = logging.getLogger(__name__)

DEFAULT_PLANT_ECOREGIONS_PATH = Path("datasets/derived/plant_ecoregions.csv")
DEFAULT_LBJ_TRAITS_PATHS = [
    Path("datasets/lbj/lbj_traits.csv"),
    Path("datasets/lbj_rerun/lbj_traits.csv"),
]
DEFAULT_OUTPUT_DIR = Path("datasets/app_data")

PLANT_ECOREGION_COLUMNS = [
    "usageKey",
    "canonicalName",
    "vernacularName",
    "occurrence_count",
    "human_observation_count",
    "preserved_specimen_count",
    "coordinate_uncertainty_median_m",
    "first_year",
    "last_year",
    "ecoregion_id",
    "ecoregion_name",
]

LBJ_TRAIT_COLUMNS = [
    "usageKey",
    "growth_habit",
    "duration",
    "mature_height_min_ft",
    "mature_height_max_ft",
    "light",
    "moisture",
    "water_use",
    "soil_categories",
    "bloom_time",
    "bloom_color",
    "lbj_url",
]

ARRAY_TRAIT_FIELDS = {
    "growthHabit",
    "light",
    "moisture",
    "soilCategories",
    "bloomTime",
    "bloomColor",
}

INT_FIELDS = {
    "usageKey",
    "occurrenceCount",
    "humanObservationCount",
    "preservedSpecimenCount",
    "firstYear",
    "lastYear",
}

FLOAT_FIELDS = {
    "coordinateUncertaintyMedianM",
    "matureHeightMinFt",
    "matureHeightMaxFt",
}

FIELD_MAP = {
    "usageKey": "usageKey",
    "canonicalName": "canonicalName",
    "vernacularName": "vernacularName",
    "occurrence_count": "occurrenceCount",
    "human_observation_count": "humanObservationCount",
    "preserved_specimen_count": "preservedSpecimenCount",
    "coordinate_uncertainty_median_m": "coordinateUncertaintyMedianM",
    "first_year": "firstYear",
    "last_year": "lastYear",
    "growth_habit": "growthHabit",
    "duration": "duration",
    "mature_height_min_ft": "matureHeightMinFt",
    "mature_height_max_ft": "matureHeightMaxFt",
    "light": "light",
    "moisture": "moisture",
    "water_use": "waterUse",
    "soil_categories": "soilCategories",
    "bloom_time": "bloomTime",
    "bloom_color": "bloomColor",
    "lbj_url": "lbjUrl",
}


def read_lbj_traits(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Read LBJ traits, preferring later files for duplicate usageKey values."""
    frames = []
    for path in paths:
        frame = pd.read_csv(path, dtype=str)
        frame["usageKey"] = frame["usageKey"].map(normalize_key)
        frame = frame[frame["usageKey"].notna()].copy()
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=LBJ_TRAIT_COLUMNS)

    combined = pd.concat(frames, ignore_index=True)
    available_columns = [column for column in LBJ_TRAIT_COLUMNS if column in combined.columns]
    combined = combined[available_columns]
    return combined.drop_duplicates(subset=["usageKey"], keep="last").reset_index(drop=True)


def merge_plant_ecoregions_with_traits(
    plant_ecoregions: pd.DataFrame,
    lbj_traits: pd.DataFrame,
) -> pd.DataFrame:
    rows = plant_ecoregions.copy()
    rows["usageKey"] = rows["usageKey"].map(normalize_key)

    traits = lbj_traits.copy()
    if "usageKey" in traits.columns:
        traits["usageKey"] = traits["usageKey"].map(normalize_key)

    trait_columns = [column for column in LBJ_TRAIT_COLUMNS if column in traits.columns]
    return rows.merge(traits[trait_columns], on="usageKey", how="left")


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
    for source, target in FIELD_MAP.items():
        value = row[source] if source in row.index else None
        if target in ARRAY_TRAIT_FIELDS:
            record[target] = _to_array(value)
        elif target in INT_FIELDS:
            record[target] = _to_number(value, integer=True)
        elif target in FLOAT_FIELDS:
            record[target] = _to_number(value)
        else:
            record[target] = _to_scalar(value)
    return record


def build_ecoregion_payloads(plant_traits: pd.DataFrame) -> list[dict]:
    rows = plant_traits.copy()
    rows["_sort_vernacular"] = rows["vernacularName"].fillna("").str.lower()
    rows["_sort_canonical"] = rows["canonicalName"].fillna("").str.lower()
    rows["_sort_ecoregion_id"] = pd.to_numeric(rows["ecoregion_id"], errors="coerce")
    rows = rows.sort_values(
        ["_sort_ecoregion_id", "ecoregion_id", "_sort_vernacular", "_sort_canonical"]
    )

    payloads = []
    for ecoregion_id, group in rows.groupby("ecoregion_id", dropna=False, sort=False):
        ecoregion_id_value = _to_number(ecoregion_id, integer=True)
        plants = [plant_record_from_row(row) for _, row in group.iterrows()]
        ecoregion_name = (
            _to_scalar(group["ecoregion_name"].dropna().iloc[0])
            if group["ecoregion_name"].notna().any()
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
) -> dict:
    output_dir = Path(output_dir)
    ecoregion_dir = output_dir / "ecoregions"
    ecoregion_dir.mkdir(parents=True, exist_ok=True)

    merged = merge_plant_ecoregions_with_traits(plant_ecoregions, lbj_traits)
    trait_presence = merged[
        [column for column in LBJ_TRAIT_COLUMNS if column in merged.columns and column != "usageKey"]
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
) -> dict:
    plant_ecoregions = pd.read_csv(plant_ecoregions_path, dtype=str)
    lbj_traits = read_lbj_traits(lbj_traits_paths)

    LOGGER.info(
        "plant ecoregion input rows=%s path=%s",
        len(plant_ecoregions),
        plant_ecoregions_path,
    )
    LOGGER.info("combined unique LBJ trait rows=%s", len(lbj_traits))

    manifest = write_app_data(plant_ecoregions, lbj_traits, output_dir)
    LOGGER.info("ecoregion JSON files written=%s", manifest["ecoregionCount"])
    LOGGER.info("plant/ecoregion records written=%s", manifest["plantEcoregionCount"])
    LOGGER.info("plant/ecoregion records missing LBJ traits=%s", manifest["missingLbjTraitCount"])
    return manifest
