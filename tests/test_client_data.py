from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from etl.client_data import build_boundary_lookup, copy_app_data


class ClientDataTests(unittest.TestCase):
    def test_copy_app_data_replaces_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            (source / "ecoregions").mkdir(parents=True)
            (source / "manifest.json").write_text('{"ecoregions":[]}', encoding="utf-8")
            (target / "old").mkdir(parents=True)

            output = copy_app_data(source, target)

            self.assertEqual(output, target)
            self.assertTrue((target / "manifest.json").exists())
            self.assertFalse((target / "old").exists())

    def test_boundary_lookup_writes_minimal_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ecoregions.geojson"
            output = root / "boundaries.json"
            gdf = gpd.GeoDataFrame(
                {
                    "ECOREGION_ID": [7],
                    "ECOREGION_NAME_EN": ["Fixture"],
                    "geometry": [Polygon([(-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)])],
                },
                crs="EPSG:4326",
            )
            gdf.to_file(source, driver="GeoJSON")

            payload = build_boundary_lookup(source, output, tolerance=0)
            saved = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(payload["ecoregions"][0]["ecoregionId"], 7)
            self.assertEqual(saved["ecoregions"][0]["ecoregionName"], "Fixture")
            self.assertEqual(saved["ecoregions"][0]["geometry"]["type"], "Polygon")


if __name__ == "__main__":
    unittest.main()
