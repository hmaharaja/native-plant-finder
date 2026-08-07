from __future__ import annotations

import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

import geopandas as gpd


DEFAULT_APP_DATA_DIR = Path("datasets/app_data")
DEFAULT_ECOREGIONS_GEOJSON_PATH = Path("datasets/ecoregions.geojson")
DEFAULT_CLIENT_DATA_DIR = Path("client/public/data")
DEFAULT_BOUNDARY_TOLERANCE = 0.01
PLANT_IMAGES_DIR_NAME = "plant_images"
PLANT_IMAGE_INDEX_PATH = Path(PLANT_IMAGES_DIR_NAME) / "index.json"
COMMONS_THUMB_WIDTH_PX = 240

_INATURALIST_ORIGINAL_IMAGE_PATH = re.compile(r"/original\.([A-Za-z0-9]+)$")
_COMMONS_THUMB_IMAGE_PATH = re.compile(r"/(\d+)px-([^/]+)$")
_IMAGE_NULLABLE_STRING_FIELDS = ("gbifId", "sourceUrl", "license", "creator", "credit", "publisher", "acceptedAt")
_IMAGE_NULLABLE_NUMBER_FIELDS = ("width", "height")


def copy_app_data(
    source_dir: str | Path = DEFAULT_APP_DATA_DIR,
    target_dir: str | Path = DEFAULT_CLIENT_DATA_DIR / "app_data",
) -> Path:
    source = Path(source_dir)
    target = Path(target_dir)
    if not (source / "manifest.json").exists():
        raise FileNotFoundError(f"app data manifest not found: {source / 'manifest.json'}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(PLANT_IMAGES_DIR_NAME))
    return target


def _read_image_bucket(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"image bucket must be a JSON object: {path}")
    return payload


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_integer_number(value: object) -> bool:
    return _is_number(value) and int(value) == value


def _is_nullable_string(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_nullable_number(value: object) -> bool:
    return value is None or _is_number(value)


def _is_https_url(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parts = urlsplit(value)
    return parts.scheme == "https" and bool(parts.netloc)


def _validate_runtime_plant_image(image: object, context: str) -> None:
    if not isinstance(image, dict):
        raise ValueError(f"{context} must be a JSON object")
    source = image.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError(f"{context}.source must be a non-empty string")
    if not _is_https_url(image.get("imageUrl")):
        raise ValueError(f"{context}.imageUrl must be a valid HTTPS URL")
    if not _is_https_url(image.get("thumbnailUrl")):
        raise ValueError(f"{context}.thumbnailUrl must be a valid HTTPS URL")
    rank = image.get("rank")
    if not _is_number(rank):
        raise ValueError(f"{context}.rank must be a finite number")
    for field in _IMAGE_NULLABLE_STRING_FIELDS:
        if field not in image or not _is_nullable_string(image.get(field)):
            raise ValueError(f"{context}.{field} must be a string or null")
    for field in _IMAGE_NULLABLE_NUMBER_FIELDS:
        if field not in image or not _is_nullable_number(image.get(field)):
            raise ValueError(f"{context}.{field} must be a number or null")


def _validate_runtime_plant_image_record(record: object, usage_key: str, bucket_path: Path) -> int:
    context = f"plant image bucket record {usage_key} in {bucket_path}"
    if not isinstance(record, dict):
        raise ValueError(f"{context} must be a JSON object")
    record_usage_key = record.get("usageKey")
    if not _is_integer_number(record_usage_key):
        raise ValueError(f"{context}.usageKey must be an integer number")
    numeric_usage_key = int(record_usage_key)
    if str(numeric_usage_key) != usage_key:
        raise ValueError(f"{context}.usageKey must match bucket key {usage_key}")
    _validate_runtime_plant_image(record.get("primaryImage"), f"{context}.primaryImage")
    if "secondaryImage" not in record:
        raise ValueError(f"{context}.secondaryImage must be an object or null")
    secondary_image = record.get("secondaryImage")
    if secondary_image is not None:
        _validate_runtime_plant_image(secondary_image, f"{context}.secondaryImage")
    return numeric_usage_key


def _normalize_thumbnail_url(thumbnail_url: object, *, commons_width_px: int = COMMONS_THUMB_WIDTH_PX) -> object:
    if not isinstance(thumbnail_url, str):
        return thumbnail_url
    parts = urlsplit(thumbnail_url)
    if parts.scheme != "https":
        return thumbnail_url
    if parts.netloc == "inaturalist-open-data.s3.amazonaws.com":
        path = _INATURALIST_ORIGINAL_IMAGE_PATH.sub(r"/small.\1", parts.path)
        if path != parts.path:
            return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    if parts.netloc == "upload.wikimedia.org" and "/wikipedia/commons/thumb/" in parts.path:
        path = _COMMONS_THUMB_IMAGE_PATH.sub(rf"/{commons_width_px}px-\2", parts.path)
        if path != parts.path:
            return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    return thumbnail_url


def _normalize_runtime_plant_image(image: object) -> object:
    if not isinstance(image, dict):
        return image
    normalized = dict(image)
    normalized["thumbnailUrl"] = _normalize_thumbnail_url(normalized.get("thumbnailUrl"))
    return normalized


def _normalize_runtime_plant_image_record(record: object) -> object:
    if not isinstance(record, dict):
        return record
    normalized = dict(record)
    normalized["primaryImage"] = _normalize_runtime_plant_image(normalized.get("primaryImage"))
    if normalized.get("secondaryImage") is not None:
        normalized["secondaryImage"] = _normalize_runtime_plant_image(normalized.get("secondaryImage"))
    return normalized


def build_runtime_plant_image_index(
    source_dir: str | Path = DEFAULT_APP_DATA_DIR / PLANT_IMAGES_DIR_NAME,
    output_path: str | Path = DEFAULT_CLIENT_DATA_DIR / "app_data" / PLANT_IMAGE_INDEX_PATH,
) -> dict[str, object]:
    source = Path(source_dir)
    bucket_dir = source / "buckets"
    if not bucket_dir.exists():
        raise FileNotFoundError(f"plant image bucket directory not found: {bucket_dir}")

    image_index: dict[str, object] = {}
    seen_usage_keys: set[int] = set()
    for bucket_path in sorted(bucket_dir.glob("*.json")):
        for usage_key, record in sorted(_read_image_bucket(bucket_path).items()):
            key = str(usage_key)
            numeric_usage_key = _validate_runtime_plant_image_record(record, key, bucket_path)
            if numeric_usage_key in seen_usage_keys:
                raise ValueError(f"duplicate plant image usageKey: {numeric_usage_key}")
            seen_usage_keys.add(numeric_usage_key)
            if key in image_index:
                raise ValueError(f"duplicate plant image usageKey: {key}")
            image_index[key] = _normalize_runtime_plant_image_record(record)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(image_index, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return image_index


def _geometry_mapping(geometry):
    return json.loads(gpd.GeoSeries([geometry], crs="EPSG:4326").to_json())["features"][0]["geometry"]


def build_boundary_lookup(
    ecoregions_geojson_path: str | Path = DEFAULT_ECOREGIONS_GEOJSON_PATH,
    output_path: str | Path = DEFAULT_CLIENT_DATA_DIR / "ecoregion-boundaries.json",
    tolerance: float = DEFAULT_BOUNDARY_TOLERANCE,
) -> dict:
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")

    source = Path(ecoregions_geojson_path)
    output = Path(output_path)
    ecoregions = gpd.read_file(source).to_crs("EPSG:4326")
    simplified = ecoregions.copy()
    simplified["geometry"] = simplified.geometry.simplify(tolerance, preserve_topology=True)

    records = []
    for _, row in simplified.sort_values("ECOREGION_ID").iterrows():
        geometry = row.geometry
        minx, miny, maxx, maxy = geometry.bounds
        records.append(
            {
                "ecoregionId": int(row["ECOREGION_ID"]),
                "ecoregionName": row.get("ECOREGION_NAME_EN") or None,
                "bbox": [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)],
                "geometry": _geometry_mapping(geometry),
            }
        )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": str(source.as_posix()),
        "tolerance": tolerance,
        "ecoregions": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def prepare_client_data(
    app_data_dir: str | Path = DEFAULT_APP_DATA_DIR,
    ecoregions_geojson_path: str | Path = DEFAULT_ECOREGIONS_GEOJSON_PATH,
    client_data_dir: str | Path = DEFAULT_CLIENT_DATA_DIR,
    tolerance: float = DEFAULT_BOUNDARY_TOLERANCE,
) -> dict:
    client_dir = Path(client_data_dir)
    app_data_target = copy_app_data(app_data_dir, client_dir / "app_data")
    image_index_target = app_data_target / PLANT_IMAGE_INDEX_PATH
    image_source = Path(app_data_dir) / PLANT_IMAGES_DIR_NAME
    image_index = None
    if image_source.exists():
        image_index = build_runtime_plant_image_index(image_source, image_index_target)
    boundaries = build_boundary_lookup(ecoregions_geojson_path, client_dir / "ecoregion-boundaries.json", tolerance)
    return {
        "appDataTarget": str(app_data_target),
        "boundaryCount": len(boundaries["ecoregions"]),
        "plantImageIndexTarget": str(image_index_target) if image_index is not None else None,
        "plantImageCount": len(image_index) if image_index is not None else 0,
    }
