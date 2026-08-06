from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests

from etl.gbif_images import (
    bucket_for_usage_key,
    build_gbif_image_index,
    build_gbif_image_index_from_dwca,
    build_qa_report,
    configure_http_session,
    fetch_gbif_occurrences,
    filter_usage_keys,
    normalize_license,
    read_dwca_occurrences,
    read_problem_usage_keys,
    rejection_reason,
    select_images_for_usage_key,
    validate_image_url,
    write_bucketed_index,
)


def occurrence(**overrides):
    row = {
        "gbifID": "10",
        "taxonKey": "100",
        "acceptedTaxonKey": "100",
        "speciesKey": "100",
        "basisOfRecord": "HUMAN_OBSERVATION",
        "occurrenceStatus": "PRESENT",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "publisher": "Fixture publisher",
        "datasetKey": "dataset-a",
        "media": [media()],
    }
    row.update(overrides)
    return row


def media(**overrides):
    row = {
        "type": "StillImage",
        "identifier": "https://images.example/plant.jpg",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creator": "Fixture photographer",
        "width": 640,
        "height": 480,
    }
    row.update(overrides)
    return row


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        url: str = "https://images.example/plant.jpg",
        headers: dict[str, str] | None = None,
        payload: dict | None = None,
        history: list | None = None,
    ):
        self.status_code = status_code
        self.url = url
        self.headers = headers or {"Content-Type": "image/jpeg", "Content-Length": "5120"}
        self._payload = payload or {}
        self.history = history or []

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"status {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


class FakeSession:
    def __init__(
        self,
        *,
        head_response: FakeResponse | None = None,
        get_response: FakeResponse | None = None,
        head_responses: list[FakeResponse | requests.RequestException] | None = None,
        get_responses: list[FakeResponse | requests.RequestException] | None = None,
    ):
        self.head_responses = list(head_responses or [head_response or FakeResponse()])
        self.get_responses = list(get_responses or [get_response or FakeResponse()])
        self.max_redirects = 30
        self.headers = {}
        self.head_calls = []
        self.get_calls = []

    def _next(self, responses):
        response = responses.pop(0) if len(responses) > 1 else responses[0]
        if isinstance(response, requests.RequestException):
            raise response
        return response

    def head(self, url, **kwargs):
        self.head_calls.append((url, kwargs))
        return self._next(self.head_responses)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self._next(self.get_responses)


def write_dwca_zip(
    path: Path,
    *,
    occurrence_rows: list[dict],
    multimedia_rows: list[dict] | None,
    occurrence_columns: list[str] | None = None,
    multimedia_columns: list[str] | None = None,
):
    occurrence_columns = occurrence_columns or [
        "id",
        "gbifID",
        "taxonKey",
        "acceptedTaxonKey",
        "speciesKey",
        "occurrenceStatus",
        "basisOfRecord",
        "license",
        "publisher",
        "datasetKey",
        "issues",
    ]
    multimedia_columns = multimedia_columns or [
        "coreid",
        "identifier",
        "type",
        "license",
        "creator",
        "width",
        "height",
        "references",
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "occurrence.txt",
            pd.DataFrame(occurrence_rows, columns=occurrence_columns).to_csv(sep="\t", index=False),
        )
        if multimedia_rows is not None:
            archive.writestr(
                "multimedia.txt",
                pd.DataFrame(multimedia_rows, columns=multimedia_columns).to_csv(sep="\t", index=False),
            )


class GbifImageAcceptanceTests(unittest.TestCase):
    def test_license_allowlist_accepts_only_open_display_licenses(self):
        self.assertEqual(normalize_license("https://creativecommons.org/publicdomain/zero/1.0/"), "CC0")
        self.assertEqual(normalize_license("https://creativecommons.org/licenses/by/4.0/"), "CC BY")
        self.assertEqual(normalize_license("https://creativecommons.org/licenses/by-sa/4.0/"), "CC BY-SA")
        self.assertIsNone(normalize_license("https://creativecommons.org/licenses/by-nc/4.0/"))
        self.assertIsNone(normalize_license("https://creativecommons.org/licenses/by-nd/4.0/"))
        self.assertIsNone(normalize_license(""))

    def test_rejection_reason_enforces_strict_gates(self):
        cases = [
            ("non_image_media", occurrence(media=[media(type="MovingImage")]), media(type="MovingImage")),
            ("missing_image_url", occurrence(media=[media(identifier="")]), media(identifier="")),
            (
                "disallowed_or_missing_license",
                occurrence(media=[media(license="https://creativecommons.org/licenses/by-nc/4.0/")]),
                media(license="https://creativecommons.org/licenses/by-nc/4.0/"),
            ),
            ("taxon_mismatch", occurrence(taxonKey="999", acceptedTaxonKey="999", speciesKey="999"), media()),
            ("not_present", occurrence(occurrenceStatus="ABSENT"), media()),
            ("major_gbif_issue", occurrence(issues=["TAXON_MATCH_HIGHERRANK"]), media()),
            ("likely_specimen_image", occurrence(basisOfRecord="PRESERVED_SPECIMEN"), media()),
            ("low_resolution", occurrence(media=[media(width=80, height=60)]), media(width=80, height=60)),
        ]
        for expected, occurrence_row, media_row in cases:
            with self.subTest(expected):
                self.assertEqual(
                    rejection_reason("100", occurrence_row, media_row, validate_url=False),
                    expected,
                )

    def test_selection_ranks_human_observation_exact_match(self):
        weaker = occurrence(
            gbifID="20",
            taxonKey="100",
            acceptedTaxonKey="",
            speciesKey="100",
            basisOfRecord="OBSERVATION",
            license="https://creativecommons.org/licenses/by-sa/4.0/",
            media=[media(identifier="https://images.example/weaker.jpg", license="https://creativecommons.org/licenses/by-sa/4.0/")],
        )
        better = occurrence(
            gbifID="10",
            taxonKey="100",
            acceptedTaxonKey="100",
            speciesKey="100",
            basisOfRecord="HUMAN_OBSERVATION",
            license="https://creativecommons.org/publicdomain/zero/1.0/",
            media=[media(identifier="https://images.example/better.jpg", license="https://creativecommons.org/publicdomain/zero/1.0/")],
        )

        selected, rejected = select_images_for_usage_key(
            "100", [weaker, better], validate_url=False, accepted_at="2026-07-31T00:00:00Z"
        )

        self.assertEqual(rejected, [])
        self.assertEqual(selected[0]["gbifId"], "10")
        self.assertEqual(selected[0]["license"], "CC0")
        self.assertEqual(selected[0]["rank"], 1)
        self.assertEqual(selected[1]["gbifId"], "20")

    def test_validate_image_url_rejects_non_image_content(self):
        session = FakeSession(head_response=FakeResponse(headers={"Content-Type": "text/html"}))

        validation = validate_image_url(session, "https://images.example/plant")

        self.assertFalse(validation.ok)
        self.assertEqual(validation.reason, "non_image_content_type")

    def test_validate_image_url_falls_back_to_get_when_head_blocked(self):
        session = FakeSession(
            head_response=FakeResponse(status_code=405),
            get_response=FakeResponse(headers={"Content-Type": "image/jpeg", "Content-Length": "1000"}),
        )

        validation = validate_image_url(session, "https://images.example/plant")

        self.assertTrue(validation.ok)
        self.assertEqual(len(session.get_calls), 1)

    def test_known_dimension_boundaries(self):
        self.assertIsNone(rejection_reason("100", occurrence(), media(width=320, height=240), validate_url=False))
        for width, height in ((319, 240), (320, 239), (76800, 1), (1000, 77)):
            with self.subTest(width=width, height=height):
                self.assertEqual(
                    rejection_reason("100", occurrence(), media(width=width, height=height), validate_url=False),
                    "low_resolution",
                )

    def test_species_key_only_match_is_accepted_unless_gbif_flags_high_rank(self):
        species_key_occurrence = occurrence(taxonKey="999", acceptedTaxonKey="999", speciesKey="100")

        self.assertIsNone(rejection_reason("100", species_key_occurrence, media(), validate_url=False))
        self.assertEqual(
            rejection_reason(
                "100",
                occurrence(taxonKey="999", acceptedTaxonKey="999", speciesKey="100", issues=["TAXON_MATCH_HIGHERRANK"]),
                media(),
                validate_url=False,
            ),
            "major_gbif_issue",
        )

    def test_unknown_dimensions_require_url_validation(self):
        unknown_dimension_media = media(width="", height="")

        self.assertEqual(
            rejection_reason("100", occurrence(), unknown_dimension_media, validate_url=False),
            "unknown_dimensions_unvalidated",
        )
        with patch("etl.gbif_images.validate_image_url", return_value=type("Result", (), {"ok": True, "reason": None})()):
            self.assertIsNone(rejection_reason("100", occurrence(), unknown_dimension_media, validate_url=True))

    def test_validate_image_url_retries_transient_failure(self):
        session = FakeSession(head_responses=[FakeResponse(status_code=503), FakeResponse()])

        validation = validate_image_url(session, "https://images.example/plant", retries=1, backoff_factor=0)

        self.assertTrue(validation.ok)
        self.assertEqual(len(session.head_calls), 2)

    def test_validate_image_url_reports_exhausted_transient_failure(self):
        session = FakeSession(head_responses=[FakeResponse(status_code=503), FakeResponse(status_code=503)])

        validation = validate_image_url(session, "https://images.example/plant", retries=1, backoff_factor=0)

        self.assertFalse(validation.ok)
        self.assertEqual(validation.reason, "transient_image_url_failure")

    def test_fetch_gbif_occurrences_retries_transient_failure(self):
        session = FakeSession(
            get_responses=[
                FakeResponse(status_code=500, headers={"Content-Type": "application/json"}),
                FakeResponse(payload={"results": [occurrence()]}, headers={"Content-Type": "application/json"}),
            ]
        )

        results = fetch_gbif_occurrences(session, "100", retries=1, backoff_factor=0)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(session.get_calls), 2)

    def test_retry_after_on_429_is_honored_and_capped(self):
        session = FakeSession(
            head_responses=[
                FakeResponse(status_code=429, headers={"Retry-After": "999", "Content-Type": "image/jpeg"}),
                FakeResponse(),
            ]
        )

        with patch("etl.gbif_images.time.sleep") as sleep:
            validation = validate_image_url(session, "https://images.example/plant", retries=1)

        self.assertTrue(validation.ok)
        sleep.assert_called_once_with(120.0)

    def test_configure_http_session_sets_user_agent_header(self):
        session = FakeSession()

        configured = configure_http_session(session, user_agent="native-plant-finder-test/1.0")

        self.assertIs(configured, session)
        self.assertEqual(session.headers["User-Agent"], "native-plant-finder-test/1.0")

    def test_selection_validates_urls_after_cheap_filtering_and_ranking(self):
        rejected_by_license = occurrence(
            gbifID="5",
            media=[media(identifier="https://images.example/rejected.jpg", license="https://creativecommons.org/licenses/by-nc/4.0/")],
        )
        lower_ranked = occurrence(gbifID="20", basisOfRecord="OBSERVATION", media=[media(identifier="https://images.example/lower.jpg")])
        best = occurrence(gbifID="10", media=[media(identifier="https://images.example/best.jpg")])
        qa_counters = Counter()

        with patch("etl.gbif_images.validate_image_url", return_value=type("Result", (), {"ok": True, "reason": None})()) as validate:
            selected, rejected = select_images_for_usage_key(
                "100",
                [rejected_by_license, lower_ranked, best],
                validate_url=True,
                max_images=1,
                qa_counters=qa_counters,
            )

        self.assertEqual([record["gbifId"] for record in selected], ["10"])
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(qa_counters["skipped_lower_rank_after_slots_filled"], 1)
        self.assertEqual(rejected[0]["rejectionReason"], "disallowed_or_missing_license")

    def test_selection_delays_between_url_checks_and_skips_lower_ranked_after_slots_fill(self):
        occurrences = [
            occurrence(gbifID="10", media=[media(identifier="https://images.example/one.jpg")]),
            occurrence(gbifID="20", media=[media(identifier="https://images.example/two.jpg")]),
            occurrence(gbifID="30", basisOfRecord="OBSERVATION", media=[media(identifier="https://images.example/three.jpg")]),
        ]
        qa_counters = Counter()

        with patch("etl.gbif_images.validate_image_url", return_value=type("Result", (), {"ok": True, "reason": None})()) as validate, patch(
            "etl.gbif_images.time.sleep"
        ) as sleep:
            selected, rejected = select_images_for_usage_key(
                "100",
                occurrences,
                validate_url=True,
                max_images=2,
                delay_between_url_checks=0.25,
                qa_counters=qa_counters,
            )

        self.assertEqual(len(selected), 2)
        self.assertEqual(rejected, [])
        self.assertEqual(validate.call_count, 2)
        sleep.assert_called_once_with(0.25)
        self.assertEqual(qa_counters["skipped_lower_rank_after_slots_filled"], 1)


class GbifImageOutputTests(unittest.TestCase):
    def test_bucket_for_usage_key_uses_modulo_bucket(self):
        self.assertEqual(bucket_for_usage_key("100", 64), "36")
        self.assertEqual(bucket_for_usage_key("64", 64), "00")

    def test_write_bucketed_index_uses_object_keyed_by_usage_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            manifest = write_bucketed_index(
                {
                    "100": {
                        "usageKey": 100,
                        "primaryImage": {"source": "gbif"},
                        "secondaryImage": None,
                    }
                },
                output,
                bucket_count=4,
            )

            self.assertEqual(manifest["bucketCount"], 4)
            bucket = json.loads((output / "buckets" / "00.json").read_text(encoding="utf-8"))
            self.assertEqual(bucket["100"]["primaryImage"]["source"], "gbif")

    def test_build_qa_report_counts_rejections_and_accepted_metadata(self):
        report = build_qa_report(
            ["100", "200"],
            {
                "100": {
                    "primaryImage": {"license": "CC BY", "publisher": "Dataset A"},
                    "secondaryImage": None,
                }
            },
            [
                {"rejectionReason": "low_resolution"},
                {"rejectionReason": "likely_specimen_image"},
                {"rejectionReason": "disallowed_or_missing_license"},
            ],
            qa_counters={"skipped_lower_rank_after_slots_filled": 3},
        )

        self.assertEqual(report["uniqueUsageKeysChecked"], 2)
        self.assertEqual(report["usageKeysWithAcceptedImage"], 1)
        self.assertEqual(report["lowResolutionCount"], 1)
        self.assertEqual(report["specimenRejectedCount"], 1)
        self.assertEqual(report["missingLicenseCount"], 1)
        self.assertEqual(report["skippedLowerRankCandidateCount"], 3)

    def test_build_gbif_image_index_writes_reports_and_buckets(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            session = FakeSession(
                get_response=FakeResponse(
                    payload={"results": [occurrence()]},
                    headers={"Content-Type": "application/json"},
                )
            )

            with patch("etl.gbif_images.validate_image_url", return_value=type("Result", (), {"ok": True, "reason": None})()):
                report = build_gbif_image_index(
                    ["100"],
                    output,
                    session=session,
                    validate_urls=True,
                    bucket_count=4,
                )

            self.assertEqual(report["usageKeysWithAcceptedImage"], 1)
            self.assertTrue((output / "manifest.json").exists())
            self.assertTrue((output / "qa_report.json").exists())
            self.assertTrue((output / "manual_review.csv").exists())
            self.assertIn("100", (output / "buckets" / "00.json").read_text(encoding="utf-8"))

    def test_build_gbif_image_index_uses_shared_session_headers_and_taxa_delay(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = FakeSession(
                get_responses=[
                    FakeResponse(payload={"results": []}, headers={"Content-Type": "application/json"}),
                    FakeResponse(payload={"results": []}, headers={"Content-Type": "application/json"}),
                ]
            )

            with patch("etl.gbif_images.time.sleep") as sleep:
                build_gbif_image_index(
                    ["100", "200"],
                    Path(tmp),
                    session=session,
                    validate_urls=False,
                    bucket_count=4,
                    delay_between_taxa=1.5,
                    user_agent="native-plant-finder-test/1.0",
                )

            self.assertEqual(session.headers["User-Agent"], "native-plant-finder-test/1.0")
            sleep.assert_called_once_with(1.5)

    def test_mocked_api_smoke_writes_only_final_image_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            session = FakeSession(
                get_response=FakeResponse(
                    payload={"results": [occurrence()]},
                    headers={"Content-Type": "application/json"},
                )
            )

            with patch("etl.gbif_images.validate_image_url", return_value=type("Result", (), {"ok": True, "reason": None})()):
                build_gbif_image_index(
                    ["100"],
                    output,
                    session=session,
                    bucket_count=4,
                    delay_between_taxa=0,
                    delay_between_url_checks=0,
                )

            files = sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file())
            self.assertEqual(
                files,
                [
                    "buckets/00.json",
                    "buckets/01.json",
                    "buckets/02.json",
                    "buckets/03.json",
                    "manifest.json",
                    "manual_review.csv",
                    "qa_report.json",
                ],
            )

    def test_build_gbif_image_index_reports_api_transient_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = FakeSession(
                get_responses=[
                    FakeResponse(status_code=503, headers={"Content-Type": "application/json"}),
                    FakeResponse(status_code=503, headers={"Content-Type": "application/json"}),
                ]
            )

            report = build_gbif_image_index(
                ["100"],
                Path(tmp),
                session=session,
                validate_urls=False,
                bucket_count=4,
                retries=1,
                backoff_factor=0,
            )

            self.assertEqual(report["rejectedByReason"], {"gbif_api_transient_failure": 1})

    def test_manual_review_flags_accepted_unknown_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            session = FakeSession(
                get_response=FakeResponse(
                    payload={"results": [occurrence(media=[media(width="", height="")])]},
                    headers={"Content-Type": "application/json"},
                )
            )

            with patch("etl.gbif_images.validate_image_url", return_value=type("Result", (), {"ok": True, "reason": None})()):
                report = build_gbif_image_index(["100"], output, session=session, bucket_count=4)

            review = pd.read_csv(output / "manual_review.csv")
            self.assertEqual(report["usageKeysWithAcceptedImage"], 1)
            self.assertEqual(review.loc[0, "manualReviewReason"], "unknown_dimensions")


class GbifImageInputTests(unittest.TestCase):
    def test_read_usage_keys_sorts_and_deduplicates_normalized_keys(self):
        from etl.gbif_images import read_usage_keys

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plants.csv"
            pd.DataFrame({"usageKey": ["200.0", "100", "200", None]}).to_csv(path, index=False)

            self.assertEqual(read_usage_keys(path), ["100", "200"])

    def test_read_problem_usage_keys_excludes_higherrank_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "problems.csv"
            pd.DataFrame(
                {
                    "usageKey": ["100", "200", "300"],
                    "matchType": ["HIGHERRANK", "VARIANT", "higherrank"],
                }
            ).to_csv(path, index=False)

            self.assertEqual(read_problem_usage_keys(path), {"100", "300"})

    def test_filter_usage_keys_applies_exclusion_offset_and_limit_deterministically(self):
        filtered = filter_usage_keys(
            ["100", "200", "300", "400", "500"],
            excluded_usage_keys={"200"},
            offset=1,
            limit=2,
        )

        self.assertEqual(filtered, ["300", "400"])

    def test_read_dwca_occurrences_validates_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbif.zip"
            write_dwca_zip(path, occurrence_rows=[occurrence(id="occ-1")], multimedia_rows=None)

            with self.assertRaisesRegex(ValueError, "multimedia.txt"):
                read_dwca_occurrences(path, ["100"])

    def test_read_dwca_occurrences_joins_multimedia_to_occurrences(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbif.zip"
            write_dwca_zip(
                path,
                occurrence_rows=[
                    occurrence(id="skip-1", taxonKey="999", acceptedTaxonKey="999", speciesKey="999"),
                    occurrence(id="occ-1"),
                ],
                multimedia_rows=[
                    media(coreid="skip-1", references="https://gbif.example/skip-1"),
                    media(coreid="occ-1", references="https://gbif.example/occ-1"),
                ],
            )

            grouped = read_dwca_occurrences(path, ["100"], chunksize=1)

            self.assertEqual(len(grouped["100"]), 1)
            self.assertEqual(grouped["100"][0]["media"][0]["identifier"], "https://images.example/plant.jpg")

    def test_read_dwca_occurrences_skips_multimedia_without_matching_occurrence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbif.zip"
            write_dwca_zip(
                path,
                occurrence_rows=[occurrence(id="occ-1")],
                multimedia_rows=[media(coreid="missing", references="https://gbif.example/missing")],
            )

            self.assertEqual(read_dwca_occurrences(path, ["100"]), {})

    def test_read_dwca_occurrences_uses_occurrence_id_before_media_row_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbif.zip"
            write_dwca_zip(
                path,
                occurrence_rows=[occurrence(id="occ-1", occurrenceID="occ-1")],
                multimedia_rows=[
                    {
                        "id": "media-row-1",
                        "occurrenceID": "occ-1",
                        "identifier": "https://images.example/plant.jpg",
                        "type": "StillImage",
                        "license": "https://creativecommons.org/licenses/by/4.0/",
                        "width": 640,
                        "height": 480,
                    }
                ],
                multimedia_columns=["id", "occurrenceID", "identifier", "type", "license", "width", "height"],
            )

            grouped = read_dwca_occurrences(path, ["100"])

            self.assertEqual(len(grouped["100"]), 1)
            self.assertEqual(grouped["100"][0]["media"][0]["id"], "media-row-1")

    def test_build_gbif_image_index_from_dwca_accepts_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "plant_images"
            dwca_path = Path(tmp) / "gbif.zip"
            write_dwca_zip(
                dwca_path,
                occurrence_rows=[occurrence(id="occ-1")],
                multimedia_rows=[media(coreid="occ-1", references="https://gbif.example/occ-1")],
            )

            with patch("etl.gbif_images.validate_image_url", return_value=type("Result", (), {"ok": True, "reason": None})()):
                report = build_gbif_image_index_from_dwca(["100"], dwca_path, output, bucket_count=4)

            self.assertEqual(report["usageKeysWithAcceptedImage"], 1)
            bucket = json.loads((output / "buckets" / "00.json").read_text(encoding="utf-8"))
            self.assertEqual(bucket["100"]["primaryImage"]["gbifId"], "10")

    def test_dwca_optional_metadata_columns_flow_to_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "plant_images"
            dwca_path = Path(tmp) / "gbif.zip"
            write_dwca_zip(
                dwca_path,
                occurrence_rows=[
                    {
                        "id": "occ-1",
                        "gbifID": "10",
                        "taxonKey": "100",
                        "acceptedTaxonKey": "100",
                    }
                ],
                multimedia_rows=[
                    {
                        "coreid": "occ-1",
                        "identifier": "https://images.example/plant.jpg",
                        "type": "StillImage",
                        "license": "https://creativecommons.org/licenses/by/4.0/",
                    }
                ],
                occurrence_columns=["id", "gbifID", "taxonKey", "acceptedTaxonKey"],
                multimedia_columns=["coreid", "identifier", "type", "license"],
            )

            with patch("etl.gbif_images.validate_image_url", return_value=type("Result", (), {"ok": True, "reason": None})()):
                report = build_gbif_image_index_from_dwca(["100"], dwca_path, output, bucket_count=4)

            review = pd.read_csv(output / "manual_review.csv")
            self.assertEqual(report["usageKeysWithAcceptedImage"], 1)
            self.assertEqual(review.loc[0, "manualReviewReason"], "unknown_dimensions")

    def test_build_gbif_image_index_from_dwca_records_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "plant_images"
            dwca_path = Path(tmp) / "gbif.zip"
            write_dwca_zip(
                dwca_path,
                occurrence_rows=[
                    occurrence(id="bad-license"),
                    occurrence(id="high-rank", taxonKey="999", acceptedTaxonKey="999", speciesKey="100", issues="TAXON_MATCH_HIGHERRANK"),
                    occurrence(id="specimen", basisOfRecord="PRESERVED_SPECIMEN"),
                    occurrence(id="low-dimension"),
                ],
                multimedia_rows=[
                    media(coreid="bad-license", license="https://creativecommons.org/licenses/by-nc/4.0/", references="https://gbif.example/bad-license"),
                    media(coreid="high-rank", references="https://gbif.example/high-rank"),
                    media(coreid="specimen", references="https://gbif.example/specimen"),
                    media(coreid="low-dimension", width=319, height=240, references="https://gbif.example/low-dimension"),
                ],
            )

            report = build_gbif_image_index_from_dwca(["100"], dwca_path, output, validate_urls=False, bucket_count=4)

            self.assertEqual(
                report["rejectedByReason"],
                {
                    "disallowed_or_missing_license": 1,
                    "major_gbif_issue": 1,
                    "likely_specimen_image": 1,
                    "low_resolution": 1,
                },
            )


if __name__ == "__main__":
    unittest.main()
