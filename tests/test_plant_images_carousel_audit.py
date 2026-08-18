from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from etl.plant_images_carousel_audit import (
    REVIEW_CSV_FIELDS,
    build_audit,
    explicit_visual_role,
    read_image_index,
    render_markdown,
    secondary_review_rows,
    write_review_csv,
)


def image(**overrides):
    row = {
        "source": "gbif",
        "gbifId": "10",
        "imageUrl": "https://images.example/plant.jpg",
        "sourceUrl": "https://www.gbif.org/occurrence/10",
        "license": "CC BY",
    }
    row.update(overrides)
    return row


class PlantImagesCarouselAuditTests(unittest.TestCase):
    def test_read_image_index_loads_bucket_files_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            bucket_dir = Path(tmp)
            (bucket_dir / "00.json").write_text(
                json.dumps(
                    {
                        "100": {
                            "usageKey": 100,
                            "primaryImage": image(),
                            "secondaryImage": None,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (bucket_dir / "01.json").write_text(
                json.dumps(
                    {
                        "200": {
                            "usageKey": 200,
                            "primaryImage": image(gbifId="20"),
                            "secondaryImage": None,
                        }
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(sorted(read_image_index(bucket_dir)), ["100", "200"])

            (bucket_dir / "02.json").write_text(
                json.dumps({"100": {"usageKey": 100, "primaryImage": image()}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate plant image usageKey: 100"):
                read_image_index(bucket_dir)

    def test_build_audit_counts_secondary_quality_signals(self):
        records = {
            "100": {
                "primaryImage": image(
                    gbifId="same",
                    imageUrl="https://images.example/dup.jpg",
                    visualRole="flower",
                ),
                "secondaryImage": image(
                    gbifId="same",
                    imageUrl="https://images.example/dup.jpg",
                    visualRole="foliage",
                    license="CC0",
                ),
            },
            "200": {
                "primaryImage": image(gbifId="20", imageUrl="https://images.example/one.jpg"),
                "secondaryImage": image(gbifId="21", imageUrl="https://images.example/two.jpg"),
            },
            "300": {
                "primaryImage": image(gbifId="30", imageUrl="https://images.example/one.jpg"),
                "secondaryImage": None,
            },
        }

        audit = build_audit(records)

        self.assertEqual(audit["imageBackedPlantCount"], 3)
        self.assertEqual(audit["plantsWithSecondaryImage"], 2)
        self.assertEqual(audit["secondaryImagePercent"], 66.7)
        self.assertEqual(audit["duplicateUrlPairCount"], 1)
        self.assertEqual(audit["acceptedRepeatedUrlSlotCount"], 2)
        self.assertEqual(audit["sameGbifIdPairCount"], 1)
        self.assertEqual(audit["missingExplicitVisualClassificationCount"], 3)
        self.assertEqual(audit["secondaryPairsMissingVisualClassificationCount"], 1)
        self.assertEqual(audit["classifiedSecondaryPairCount"], 1)
        self.assertEqual(audit["complementaryVisualRolePairCount"], 1)
        self.assertEqual(
            audit["sourceLicenseBreakdown"],
            {"gbif / CC BY": 4, "gbif / CC0": 1},
        )

    def test_explicit_visual_role_requires_named_classification_field(self):
        self.assertEqual(explicit_visual_role(image(title="flower close-up"))[2], set())
        field, value, roles = explicit_visual_role(image(plantPart="flower; seed"))

        self.assertEqual(field, "plantPart")
        self.assertEqual(value, "flower; seed")
        self.assertEqual(roles, {"flower", "seed"})

    def test_review_csv_is_parseable_and_includes_manual_classification_fields(self):
        records = {
            "100": {
                "primaryImage": image(gbifId="10", visualRole="flower"),
                "secondaryImage": image(gbifId="11", imageUrl="https://images.example/leaf.jpg"),
            }
        }
        rows = secondary_review_rows(
            records,
            {"100": {"canonicalName": "Plantus example", "vernacularName": "example plant"}},
        )

        self.assertEqual(rows[0]["usageKey"], "100")
        self.assertEqual(rows[0]["canonicalName"], "Plantus example")
        self.assertEqual(rows[0]["primaryVisualRole"], "flower")
        self.assertEqual(rows[0]["visualRoleReviewStatus"], "needs_manual_classification")
        self.assertEqual(set(REVIEW_CSV_FIELDS).difference(rows[0]), set())

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.csv"
            write_review_csv(rows, path)
            with path.open(newline="", encoding="utf-8") as handle:
                parsed = list(csv.DictReader(handle))

        self.assertEqual(parsed[0]["secondaryImageUrl"], "https://images.example/leaf.jpg")
        self.assertIn("reviewerVisualVariety", parsed[0])

    def test_render_markdown_keeps_no_go_decision_visible(self):
        markdown = render_markdown(
            {
                "imageBackedPlantCount": 1,
                "plantsWithSecondaryImage": 1,
                "secondaryImagePercent": 100.0,
                "acceptedImageCount": 2,
                "duplicateUrlPairCount": 0,
                "acceptedRepeatedUrlSlotCount": 0,
                "sameGbifIdPairCount": 0,
                "sourceLicenseBreakdown": {"gbif / CC BY": 2},
                "missingExplicitVisualClassificationCount": 2,
                "secondaryPairsMissingVisualClassificationCount": 1,
                "complementaryVisualRolePairCount": 0,
            }
        )

        self.assertIn("DEFER / NO-GO", markdown)
        self.assertIn("explicit visual classification", markdown)


if __name__ == "__main__":
    unittest.main()
