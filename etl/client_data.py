from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd


DEFAULT_APP_DATA_DIR = Path("datasets/app_data")
DEFAULT_ECOREGIONS_GEOJSON_PATH = Path("datasets/ecoregions.geojson")
DEFAULT_CLIENT_DATA_DIR = Path("client/public/data")
DEFAULT_BOUNDARY_TOLERANCE = 0.01


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
    shutil.copytree(source, target)
    return target


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
    boundaries = build_boundary_lookup(ecoregions_geojson_path, client_dir / "ecoregion-boundaries.json", tolerance)
    return {
        "appDataTarget": str(app_data_target),
        "boundaryCount": len(boundaries["ecoregions"]),
    }
