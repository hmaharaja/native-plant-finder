from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from etl.client_data import build_boundary_lookup, build_runtime_plant_image_index, copy_app_data


def plant_image(image_url: str, thumbnail_url: str) -> dict[str, object]:
    return {
        "source": "gbif",
        "gbifId": "1",
        "imageUrl": image_url,
        "thumbnailUrl": thumbnail_url,
        "sourceUrl": "https://www.gbif.org/occurrence/1",
        "license": "CC0",
        "creator": None,
        "credit": None,
        "publisher": None,
        "width": None,
        "height": None,
        "acceptedAt": "2026-08-05T00:00:00Z",
        "rank": 1,
    }


def plant_image_record(usage_key: int, image: dict[str, object]) -> dict[str, object]:
    return {
        "usageKey": usage_key,
        "primaryImage": image,
        "secondaryImage": None,
    }


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

    def test_copy_app_data_excludes_plant_image_audit_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            (source / "plant_images" / "buckets").mkdir(parents=True)
            (source / "ecoregions").mkdir(parents=True)
            (source / "manifest.json").write_text('{"ecoregions":[]}', encoding="utf-8")
            (source / "plant_images" / "manual_review.csv").write_text("large,audit\n", encoding="utf-8")
            (source / "plant_images" / "qa_report.json").write_text("{}", encoding="utf-8")
            (source / "plant_images" / "buckets" / "00.json").write_text("{}", encoding="utf-8")

            copy_app_data(source, target)

            self.assertFalse((target / "plant_images").exists())

    def test_runtime_plant_image_index_merges_bucket_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "plant_images"
            output = root / "public" / "plant_images" / "index.json"
            (source / "buckets").mkdir(parents=True)
            (source / "manual_review.csv").write_text("usageKey\n1\n", encoding="utf-8")
            (source / "qa_report.json").write_text("{}", encoding="utf-8")
            (source / "buckets" / "00.json").write_text(
                json.dumps(
                    {
                        "64": {
                            "usageKey": 64,
                            "primaryImage": {
                                "source": "gbif",
                                "imageUrl": "https://example.test/image.jpg",
                                "thumbnailUrl": "https://example.test/image.jpg",
                            },
                            "secondaryImage": None,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (source / "buckets" / "01.json").write_text(
                json.dumps(
                    {
                        "65": {
                            "usageKey": 65,
                            "primaryImage": {
                                "source": "wikimedia_commons",
                                "imageUrl": "https://example.test/second.jpg",
                                "thumbnailUrl": "https://example.test/second.jpg",
                            },
                            "secondaryImage": None,
                        }
                    }
                ),
                encoding="utf-8",
            )

            image_index = build_runtime_plant_image_index(source, output)
            saved = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(sorted(image_index), ["64", "65"])
            self.assertEqual(saved["64"]["usageKey"], 64)
            self.assertFalse((output.parent / "manual_review.csv").exists())
            self.assertFalse((output.parent / "qa_report.json").exists())

    def test_runtime_plant_image_index_uses_small_inaturalist_thumbnails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "plant_images" / "buckets"
            output = root / "public" / "plant_images" / "index.json"
            source.mkdir(parents=True)
            image_url = "https://inaturalist-open-data.s3.amazonaws.com/photos/123/original.jpeg?ix=1"
            (source / "00.json").write_text(
                json.dumps({"64": plant_image_record(64, plant_image(image_url, image_url))}),
                encoding="utf-8",
            )

            build_runtime_plant_image_index(source.parent, output)
            saved = json.loads(output.read_text(encoding="utf-8"))

            primary = saved["64"]["primaryImage"]
            self.assertEqual(primary["imageUrl"], image_url)
            self.assertEqual(
                primary["thumbnailUrl"],
                "https://inaturalist-open-data.s3.amazonaws.com/photos/123/small.jpeg?ix=1",
            )

    def test_runtime_plant_image_index_reduces_commons_thumb_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "plant_images" / "buckets"
            output = root / "public" / "plant_images" / "index.json"
            source.mkdir(parents=True)
            image_url = "https://upload.wikimedia.org/wikipedia/commons/4/47/Example.JPG"
            thumbnail_url = (
                "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/Example.JPG/"
                "960px-Example.JPG"
            )
            (source / "00.json").write_text(
                json.dumps({"64": plant_image_record(64, plant_image(image_url, thumbnail_url))}),
                encoding="utf-8",
            )

            build_runtime_plant_image_index(source.parent, output)
            saved = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(saved["64"]["primaryImage"]["imageUrl"], image_url)
            self.assertEqual(
                saved["64"]["primaryImage"]["thumbnailUrl"],
                "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/Example.JPG/240px-Example.JPG",
            )

    def test_runtime_plant_image_index_preserves_unknown_thumbnail_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "plant_images" / "buckets"
            output = root / "public" / "plant_images" / "index.json"
            source.mkdir(parents=True)
            image_url = "https://images.example.test/plant.jpg"
            thumbnail_url = "https://images.example.test/thumb.jpg"
            (source / "00.json").write_text(
                json.dumps({"64": plant_image_record(64, plant_image(image_url, thumbnail_url))}),
                encoding="utf-8",
            )

            build_runtime_plant_image_index(source.parent, output)
            saved = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(saved["64"]["primaryImage"]["imageUrl"], image_url)
            self.assertEqual(saved["64"]["primaryImage"]["thumbnailUrl"], thumbnail_url)

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
