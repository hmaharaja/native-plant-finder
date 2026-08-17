from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from etl.client_data import build_boundary_lookup, build_runtime_plant_image_index, copy_app_data


PLANT_IMAGE_RUNTIME_INDEX = Path("client/public/data/app_data/plant_images/index.json")
PLANT_IMAGE_RUNTIME_INDEX_MAX_BYTES = 10 * 1024 * 1024


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
                        "64": plant_image_record(
                            64,
                            plant_image("https://example.test/image.jpg", "https://example.test/image.jpg"),
                        )
                    }
                ),
                encoding="utf-8",
            )
            (source / "buckets" / "01.json").write_text(
                json.dumps(
                    {
                        "65": plant_image_record(
                            65,
                            plant_image("https://example.test/second.jpg", "https://example.test/second.jpg"),
                        )
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

    def test_runtime_plant_image_index_rejects_malformed_bucket_records(self):
        base_record = plant_image_record(
            64,
            plant_image("https://example.test/plant.jpg", "https://example.test/thumb.jpg"),
        )
        missing_creator_image = dict(base_record["primaryImage"])
        del missing_creator_image["creator"]
        cases = {
            "non-object record": ("not an object", "must be a JSON object"),
            "missing numeric usageKey": ({**base_record, "usageKey": None}, "usageKey"),
            "mismatched usageKey": ({**base_record, "usageKey": 65}, "match bucket key"),
            "missing valid primary image": ({**base_record, "primaryImage": None}, "primaryImage"),
            "invalid imageUrl": (
                {
                    **base_record,
                    "primaryImage": {**base_record["primaryImage"], "imageUrl": "http://example.test/plant.jpg"},
                },
                "imageUrl",
            ),
            "invalid thumbnailUrl": (
                {
                    **base_record,
                    "primaryImage": {**base_record["primaryImage"], "thumbnailUrl": "not a url"},
                },
                "thumbnailUrl",
            ),
            "invalid required nullable metadata": (
                {
                    **base_record,
                    "primaryImage": {**base_record["primaryImage"], "creator": 123},
                },
                "creator",
            ),
            "missing required nullable metadata": (
                {
                    **base_record,
                    "primaryImage": missing_creator_image,
                },
                "creator",
            ),
        }
        for label, (record, message) in cases.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    source = root / "plant_images" / "buckets"
                    output = root / "public" / "plant_images" / "index.json"
                    source.mkdir(parents=True)
                    (source / "00.json").write_text(json.dumps({"64": record}), encoding="utf-8")

                    with self.assertRaisesRegex(ValueError, message):
                        build_runtime_plant_image_index(source.parent, output)
                    self.assertFalse(output.exists())

    def test_runtime_plant_image_index_rejects_duplicate_numeric_usage_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "plant_images" / "buckets"
            output = root / "public" / "plant_images" / "index.json"
            source.mkdir(parents=True)
            image = plant_image("https://example.test/plant.jpg", "https://example.test/thumb.jpg")
            (source / "00.json").write_text(json.dumps({"64": plant_image_record(64, image)}), encoding="utf-8")
            (source / "01.json").write_text(json.dumps({"64": plant_image_record(64, image)}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "duplicate plant image usageKey: 64"):
                build_runtime_plant_image_index(source.parent, output)
            self.assertFalse(output.exists())

    def test_committed_runtime_plant_image_index_stays_under_size_budget(self):
        size = PLANT_IMAGE_RUNTIME_INDEX.stat().st_size

        self.assertLessEqual(
            size,
            PLANT_IMAGE_RUNTIME_INDEX_MAX_BYTES,
            "client plant image runtime index exceeds 10 MiB; larger indexes should revisit "
            "bucketed or per-ecoregion runtime loading before committing the artifact",
        )

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
