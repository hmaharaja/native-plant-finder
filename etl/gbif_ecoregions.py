from __future__ import annotations

import logging
import zipfile
from collections import defaultdict
from pathlib import Path
import pyarrow.parquet as pq
from typing import Iterable, Iterator

import geopandas as gpd
import pandas as pd


LOGGER = logging.getLogger(__name__)

OCCURRENCE_MEMBER = "occurrence.txt"
DEFAULT_ZIP_PATH = Path("datasets/0026180-260623161305970.zip")
DEFAULT_PLANTS_CSV_PATH = Path("datasets/gbif_species_match_cleaned.csv")
DEFAULT_ECOREGIONS_GEOJSON_PATH = Path("datasets/ecoregions.geojson")
DEFAULT_OUTPUT_DIR = Path("datasets/derived")
DEFAULT_MATCHED_OCCURRENCES_FILENAME = "gbif_matched_occurrences.parquet"
DEFAULT_PLANT_ECOREGIONS_FILENAME = "plant_ecoregions.csv"

REQUIRED_OCCURRENCE_COLUMNS = [
    "gbifID",
    "taxonKey",
    "acceptedTaxonKey",
    "speciesKey",
    "scientificName",
    "acceptedScientificName",
    "decimalLatitude",
    "decimalLongitude",
    "coordinateUncertaintyInMeters",
    "hasGeospatialIssues",
    "basisOfRecord",
    "occurrenceStatus",
    "eventDate",
    "year",
    "datasetKey",
    "institutionCode",
    "collectionCode",
    "countryCode",
    "stateProvince",
    "locality",
]

TAXON_KEY_COLUMNS = ["taxonKey", "acceptedTaxonKey", "speciesKey"]
MATCHED_OCCURRENCE_COLUMNS = [
    "gbifID",
    "decimalLatitude",
    "decimalLongitude",
    "coordinateUncertaintyInMeters",
    "basisOfRecord",
    "year",
    "datasetKey",
    "usageKey",
    "input_name",
    "canonicalName",
    "vernacularName",
]


class OccurrenceArchiveError(ValueError):
    """Raised when the GBIF occurrence archive cannot be read as expected."""


def _normalize_key(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def validate_occurrence_archive(
    zip_path: str | Path,
    member_name: str = OCCURRENCE_MEMBER,
    required_columns: Iterable[str] = REQUIRED_OCCURRENCE_COLUMNS,
) -> list[str]:
    """Validate that a GBIF zip contains occurrence.txt with required columns."""
    zip_path = Path(zip_path)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            if member_name not in names:
                raise OccurrenceArchiveError(f"{zip_path} does not contain {member_name}")

            with archive.open(member_name) as occurrence_file:
                columns = pd.read_csv(occurrence_file, sep="\t", nrows=0).columns.tolist()
    except zipfile.BadZipFile as exc:
        raise OccurrenceArchiveError(f"{zip_path} is not a valid zip archive") from exc

    missing = sorted(set(required_columns) - set(columns))
    if missing:
        raise OccurrenceArchiveError(
            f"{member_name} is missing required columns: {', '.join(missing)}"
        )
    return columns


def stream_occurrence_chunks(
    zip_path: str | Path,
    chunksize: int = 100_000,
    limit: int | None = None,
    member_name: str = OCCURRENCE_MEMBER,
    required_columns: Iterable[str] = REQUIRED_OCCURRENCE_COLUMNS,
):
    """Yield selected occurrence columns from occurrence.txt without extracting it."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be a positive integer")

    validate_occurrence_archive(zip_path, member_name, required_columns)
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member_name) as occurrence_file:
            yield from pd.read_csv(
                occurrence_file,
                sep="\t",
                dtype=str,
                usecols=list(required_columns),
                chunksize=chunksize,
                nrows=limit,
            )


def filter_occurrences(df: pd.DataFrame) -> pd.DataFrame:
    """Keep Canadian, present occurrences with valid coordinates and no GBIF geo issues."""
    filtered = df.copy()
    filtered["decimalLatitude"] = pd.to_numeric(filtered["decimalLatitude"], errors="coerce")
    filtered["decimalLongitude"] = pd.to_numeric(filtered["decimalLongitude"], errors="coerce")
    filtered["coordinateUncertaintyInMeters"] = pd.to_numeric(
        filtered["coordinateUncertaintyInMeters"], errors="coerce"
    )

    mask = (
        filtered["countryCode"].fillna("").str.upper().eq("CA")
        & filtered["occurrenceStatus"].fillna("").str.upper().eq("PRESENT")
        & filtered["hasGeospatialIssues"].fillna("").str.lower().eq("false")
        & filtered["decimalLatitude"].between(-90, 90)
        & filtered["decimalLongitude"].between(-180, 180)
    )
    return filtered.loc[mask].copy()


def match_occurrences_to_plants(
    occurrences: pd.DataFrame,
    plants: pd.DataFrame,
    plant_key_column: str = "usageKey",
) -> pd.DataFrame:
    """Attach cleaned plant rows by matching any GBIF interpreted taxon key column."""
    if plant_key_column not in plants.columns:
        raise KeyError(f"plants is missing {plant_key_column}")

    plant_rows = plants.copy()
    plant_rows[plant_key_column] = plant_rows[plant_key_column].map(_normalize_key)
    plant_rows = plant_rows[plant_rows[plant_key_column].notna()].drop_duplicates(
        subset=[plant_key_column]
    )

    occurrence_rows = occurrences.copy()
    occurrence_rows["_occurrence_row_id"] = range(len(occurrence_rows))
    for column in TAXON_KEY_COLUMNS:
        occurrence_rows[column] = occurrence_rows[column].map(_normalize_key)

    long_keys = occurrence_rows.melt(
        id_vars=["_occurrence_row_id"],
        value_vars=TAXON_KEY_COLUMNS,
        value_name=plant_key_column,
    )
    long_keys = long_keys[long_keys[plant_key_column].notna()].drop_duplicates(
        subset=["_occurrence_row_id", plant_key_column]
    )

    matched_keys = long_keys.merge(
        plant_rows,
        how="inner",
        on=plant_key_column,
        suffixes=("", "_plant"),
    )
    matched = occurrence_rows.merge(
        matched_keys.drop(columns=["variable"]),
        how="inner",
        on="_occurrence_row_id",
    ).drop(columns=["_occurrence_row_id"])

    dedupe_columns = ["gbifID", plant_key_column] if "gbifID" in matched.columns else [plant_key_column]
    return matched.drop_duplicates(subset=dedupe_columns).copy()


def spatial_join_ecoregions(
    occurrences: pd.DataFrame,
    ecoregions: gpd.GeoDataFrame,
    ecoregion_id_column: str = "ECOREGION_ID",
    ecoregion_name_column: str = "ECOREGION_NAME_EN",
    predicate: str = "within",
) -> pd.DataFrame:
    """Join points to polygons. The default 'within' predicate excludes boundaries."""
    if ecoregion_id_column not in ecoregions.columns:
        raise KeyError(f"ecoregions is missing {ecoregion_id_column}")

    point_gdf = gpd.GeoDataFrame(
        occurrences.copy(),
        geometry=gpd.points_from_xy(occurrences["decimalLongitude"], occurrences["decimalLatitude"]),
        crs="EPSG:4326",
    )
    polygon_gdf = ecoregions
    if polygon_gdf.crs is None:
        polygon_gdf = polygon_gdf.set_crs("EPSG:4326")
    elif polygon_gdf.crs != point_gdf.crs:
        polygon_gdf = polygon_gdf.to_crs(point_gdf.crs)

    right_columns = [ecoregion_id_column, "geometry"]
    if ecoregion_name_column in polygon_gdf.columns:
        right_columns.insert(1, ecoregion_name_column)

    joined = gpd.sjoin(point_gdf, polygon_gdf[right_columns], how="inner", predicate=predicate)
    joined = joined.drop(columns=["geometry", "index_right"])
    joined = joined.rename(
        columns={
            ecoregion_id_column: "ecoregion_id",
            ecoregion_name_column: "ecoregion_name",
        }
    )
    return pd.DataFrame(joined)


def aggregate_plant_ecoregions(joined: pd.DataFrame) -> pd.DataFrame:
    """Collapse occurrence evidence to one row per plant/ecoregion pair."""
    rows = joined.copy()
    rows["coordinateUncertaintyInMeters"] = pd.to_numeric(
        rows["coordinateUncertaintyInMeters"], errors="coerce"
    )
    rows["year"] = pd.to_numeric(rows["year"], errors="coerce")

    rows["_human_observation"] = rows["basisOfRecord"].eq("HUMAN_OBSERVATION").astype(int)
    rows["_preserved_specimen"] = rows["basisOfRecord"].eq("PRESERVED_SPECIMEN").astype(int)

    grouped = rows.groupby(["usageKey", "ecoregion_id"], dropna=False)
    result = grouped.agg(
        occurrence_count=("gbifID", "nunique"),
        human_observation_count=("_human_observation", "sum"),
        preserved_specimen_count=("_preserved_specimen", "sum"),
        coordinate_uncertainty_min_m=("coordinateUncertaintyInMeters", "min"),
        coordinate_uncertainty_median_m=("coordinateUncertaintyInMeters", "median"),
        coordinate_uncertainty_max_m=("coordinateUncertaintyInMeters", "max"),
        first_year=("year", "min"),
        last_year=("year", "max"),
        dataset_count=("datasetKey", "nunique"),
    ).reset_index()

    optional_first_columns = [
        "input_name",
        "canonicalName",
        "vernacularName",
        "ecoregion_name",
    ]
    first_values = grouped[
        [column for column in optional_first_columns if column in rows.columns]
    ].first().reset_index()
    if len(first_values.columns) > 2:
        result = result.merge(first_values, on=["usageKey", "ecoregion_id"], how="left")

    sort_columns = ["usageKey", "ecoregion_id"]
    return result.sort_values(sort_columns).reset_index(drop=True)


def _empty_plant_ecoregion_output() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "usageKey",
            "ecoregion_id",
            "occurrence_count",
            "human_observation_count",
            "preserved_specimen_count",
            "coordinate_uncertainty_min_m",
            "coordinate_uncertainty_median_m",
            "coordinate_uncertainty_max_m",
            "first_year",
            "last_year",
            "dataset_count",
            "input_name",
            "canonicalName",
            "vernacularName",
            "ecoregion_name",
        ]
    )


def _accumulate_joined_ecoregions(accumulator: dict, joined: pd.DataFrame) -> None:
    rows = joined.copy()
    rows["coordinateUncertaintyInMeters"] = pd.to_numeric(
        rows["coordinateUncertaintyInMeters"], errors="coerce"
    )
    rows["year"] = pd.to_numeric(rows["year"], errors="coerce")

    for (usage_key, ecoregion_id), group in rows.groupby(["usageKey", "ecoregion_id"], dropna=False):
        state = accumulator[(usage_key, ecoregion_id)]
        state["usageKey"] = usage_key
        state["ecoregion_id"] = ecoregion_id
        state["occurrence_count"] += group["gbifID"].nunique()
        state["human_observation_count"] += group["basisOfRecord"].eq("HUMAN_OBSERVATION").sum()
        state["preserved_specimen_count"] += group["basisOfRecord"].eq("PRESERVED_SPECIMEN").sum()

        uncertainties = group["coordinateUncertaintyInMeters"].dropna()
        if not uncertainties.empty:
            state["uncertainties"].extend(uncertainties.tolist())

        years = group["year"].dropna()
        if not years.empty:
            first_year = years.min()
            last_year = years.max()
            state["first_year"] = (
                first_year if state["first_year"] is None else min(state["first_year"], first_year)
            )
            state["last_year"] = (
                last_year if state["last_year"] is None else max(state["last_year"], last_year)
            )

        state["dataset_keys"].update(group["datasetKey"].dropna().astype(str))
        for column in ["input_name", "canonicalName", "vernacularName", "ecoregion_name"]:
            if state[column] is None and column in group.columns:
                value = group[column].dropna()
                if not value.empty:
                    state[column] = value.iloc[0]


def _plant_ecoregion_output_from_accumulator(accumulator: dict) -> pd.DataFrame:
    if not accumulator:
        return _empty_plant_ecoregion_output()

    rows = []
    for state in accumulator.values():
        uncertainties = pd.Series(state["uncertainties"], dtype="float64")
        rows.append(
            {
                "usageKey": state["usageKey"],
                "ecoregion_id": state["ecoregion_id"],
                "occurrence_count": state["occurrence_count"],
                "human_observation_count": state["human_observation_count"],
                "preserved_specimen_count": state["preserved_specimen_count"],
                "coordinate_uncertainty_min_m": (
                    uncertainties.min() if not uncertainties.empty else pd.NA
                ),
                "coordinate_uncertainty_median_m": (
                    uncertainties.median() if not uncertainties.empty else pd.NA
                ),
                "coordinate_uncertainty_max_m": (
                    uncertainties.max() if not uncertainties.empty else pd.NA
                ),
                "first_year": state["first_year"],
                "last_year": state["last_year"],
                "dataset_count": len(state["dataset_keys"]),
                "input_name": state["input_name"],
                "canonicalName": state["canonicalName"],
                "vernacularName": state["vernacularName"],
                "ecoregion_name": state["ecoregion_name"],
            }
        )
    return pd.DataFrame(rows).sort_values(["usageKey", "ecoregion_id"]).reset_index(drop=True)


def stream_parquet_chunks(
    parquet_path: str | Path,
    batch_size: int = 100_000,
    columns: Iterable[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Yield Parquet row groups in bounded DataFrame batches."""
    if batch_size < 1:
        raise ValueError("batch_size must be a positive integer")

    parquet_file = pq.ParquetFile(parquet_path)
    for batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
        yield batch.to_pandas()


def parquet_row_count(parquet_path: str | Path) -> int:
    """Return Parquet row count from metadata without reading the data."""
    return pq.ParquetFile(parquet_path).metadata.num_rows


def _new_ecoregion_accumulator_state() -> dict:
    return {
        "usageKey": None,
        "ecoregion_id": None,
        "occurrence_count": 0,
        "human_observation_count": 0,
        "preserved_specimen_count": 0,
        "uncertainties": [],
        "first_year": None,
        "last_year": None,
        "dataset_keys": set(),
        "input_name": None,
        "canonicalName": None,
        "vernacularName": None,
        "ecoregion_name": None,
    }


def _existing_parquet_columns(parquet_path: str | Path, requested_columns: Iterable[str]) -> list[str]:
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(parquet_path)
    existing = set(parquet_file.schema.names)
    return [column for column in requested_columns if column in existing]


def build_matched_occurrence_parquet(
    zip_path: str | Path,
    plants_csv_path: str | Path,
    output_parquet_path: str | Path,
    chunksize: int = 100_000,
    limit: int | None = None,
) -> pd.DataFrame:
    """Filter and taxon-match GBIF occurrences, then persist a Parquet checkpoint."""
    plants = pd.read_csv(plants_csv_path, dtype=str)
    chunks = []
    raw_rows = 0
    matched_rows = 0
    for chunk_number, chunk in enumerate(
        stream_occurrence_chunks(zip_path, chunksize=chunksize, limit=limit),
        start=1,
    ):
        raw_rows += len(chunk)
        filtered = filter_occurrences(chunk)
        matched = match_occurrences_to_plants(filtered, plants)
        matched_rows += len(matched)
        LOGGER.info(
            "chunk=%s raw_rows=%s cumulative_raw_rows=%s filtered_rows=%s "
            "matched_rows=%s cumulative_matched_rows=%s",
            chunk_number,
            len(chunk),
            raw_rows,
            len(filtered),
            len(matched),
            matched_rows,
        )
        if not matched.empty:
            chunks.append(matched)

    output = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    output_parquet_path = Path(output_parquet_path)
    output_parquet_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(output_parquet_path, index=False)
    LOGGER.info("wrote matched occurrences path=%s rows=%s", output_parquet_path, len(output))
    return output


def build_plant_ecoregion_csv(
    matched_occurrences: pd.DataFrame,
    ecoregions_geojson_path: str | Path,
    output_csv_path: str | Path,
) -> pd.DataFrame:
    """Spatially join matched occurrences, aggregate evidence, and write the CSV artifact."""
    ecoregions = gpd.read_file(ecoregions_geojson_path)
    joined = spatial_join_ecoregions(matched_occurrences, ecoregions)
    output = aggregate_plant_ecoregions(joined)
    output_csv_path = Path(output_csv_path)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_csv_path, index=False)
    LOGGER.info("wrote plant ecoregions path=%s rows=%s", output_csv_path, len(output))
    return output


def build_plant_ecoregion_csv_from_parquet(
    matched_occurrences_parquet_path: str | Path,
    ecoregions_geojson_path: str | Path,
    output_csv_path: str | Path,
    chunksize: int = 100_000,
) -> pd.DataFrame:
    """Spatially join a matched-occurrence Parquet checkpoint in bounded batches."""
    ecoregions = gpd.read_file(ecoregions_geojson_path)
    accumulator = defaultdict(_new_ecoregion_accumulator_state)
    columns = _existing_parquet_columns(matched_occurrences_parquet_path, MATCHED_OCCURRENCE_COLUMNS)
    spatial_rows = 0

    for chunk_number, matched_chunk in enumerate(
        stream_parquet_chunks(matched_occurrences_parquet_path, batch_size=chunksize, columns=columns),
        start=1,
    ):
        joined = spatial_join_ecoregions(matched_chunk, ecoregions)
        spatial_rows += len(joined)
        _accumulate_joined_ecoregions(accumulator, joined)
        LOGGER.info(
            "spatial_chunk=%s matched_rows=%s joined_rows=%s cumulative_joined_rows=%s",
            chunk_number,
            len(matched_chunk),
            len(joined),
            spatial_rows,
        )

    output = _plant_ecoregion_output_from_accumulator(accumulator)
    output_csv_path = Path(output_csv_path)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_csv_path, index=False)
    LOGGER.info("wrote plant ecoregions path=%s rows=%s", output_csv_path, len(output))
    return output


def run_pipeline(
    zip_path: str | Path = DEFAULT_ZIP_PATH,
    plants_csv_path: str | Path = DEFAULT_PLANTS_CSV_PATH,
    ecoregions_geojson_path: str | Path = DEFAULT_ECOREGIONS_GEOJSON_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    matched_occurrences_filename: str = DEFAULT_MATCHED_OCCURRENCES_FILENAME,
    plant_ecoregions_filename: str = DEFAULT_PLANT_ECOREGIONS_FILENAME,
    chunksize: int = 100_000,
    limit: int | None = None,
) -> pd.DataFrame:
    """Run the GBIF occurrence to plant/ecoregion ETL."""
    output_dir = Path(output_dir)
    parquet_path = output_dir / matched_occurrences_filename
    csv_path = output_dir / plant_ecoregions_filename
    matched = build_matched_occurrence_parquet(
        zip_path, plants_csv_path, parquet_path, chunksize=chunksize, limit=limit
    )
    matched_count = len(matched)
    del matched
    LOGGER.info(
        "matched occurrence total before spatial join rows=%s path=%s",
        matched_count,
        parquet_path,
    )
    return build_plant_ecoregion_csv_from_parquet(
        parquet_path, ecoregions_geojson_path, csv_path, chunksize=chunksize
    )
