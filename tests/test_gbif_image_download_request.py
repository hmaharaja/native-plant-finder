from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from etl.gbif_image_download_request import (
    build_image_download_request,
    main,
    submit_image_download_request,
    write_image_download_request,
)


class FakeResponse:
    text = "0000000-260803000000000"

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def write_template(path: Path):
    path.write_text(
        json.dumps(
            {
                "creator": "hmah",
                "sendNotification": True,
                "notification_address": ["fixture@example.com"],
                "format": "DWCA",
                "predicate": {
                    "type": "and",
                    "predicates": [
                        {"type": "in", "key": "TAXON_KEY", "values": []},
                        {"type": "equals", "key": "MEDIA_TYPE", "value": "StillImage"},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


class GbifImageDownloadRequestTests(unittest.TestCase):
    def test_build_request_excludes_high_rank_keys_sorts_taxa_and_preserves_template_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plants = root / "plants.csv"
            problems = root / "problems.csv"
            template = root / "template.json"

            pd.DataFrame({"usageKey": ["300", "200", "100", "200"]}).to_csv(plants, index=False)
            pd.DataFrame(
                {
                    "usageKey": ["200", "300"],
                    "matchType": ["HIGHERRANK", "VARIANT"],
                }
            ).to_csv(problems, index=False)
            write_template(template)

            request = build_image_download_request(
                plants,
                problems_csv_path=problems,
                template_path=template,
            )

            self.assertEqual(request["predicate"]["predicates"][0]["values"], ["100", "300"])
            self.assertEqual(request["notification_address"], ["fixture@example.com"])
            self.assertNotIn("notificationAddresses", request)

    def test_write_request_creates_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plants = root / "plants.csv"
            template = root / "template.json"
            output = root / "request.json"

            pd.DataFrame({"usageKey": ["100"]}).to_csv(plants, index=False)
            write_template(template)

            request = write_image_download_request(
                output,
                plants_csv_path=plants,
                problems_csv_path=None,
                template_path=template,
            )

            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), request)

    def test_submit_request_uses_gbif_credentials_and_returns_download_key(self):
        session = FakeSession()
        request = {"format": "DWCA", "predicate": {"type": "equals", "key": "MEDIA_TYPE", "value": "StillImage"}}

        key = submit_image_download_request(
            request,
            username="user",
            password="password",
            session=session,
        )

        self.assertEqual(key, "0000000-260803000000000")
        self.assertEqual(session.calls[0][1]["json"], request)
        self.assertEqual(session.calls[0][1]["auth"], ("user", "password"))

    def test_main_writes_request_without_submit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plants = root / "plants.csv"
            template = root / "template.json"
            output = root / "request.json"

            pd.DataFrame({"usageKey": ["100"]}).to_csv(plants, index=False)
            write_template(template)

            with patch("sys.stdout"):
                exit_code = main(
                    [
                        "--plants",
                        str(plants),
                        "--template",
                        str(template),
                        "--output",
                        str(output),
                        "--no-problems",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
