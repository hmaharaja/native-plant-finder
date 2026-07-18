from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from etl.gbif_ecoregions import (
    OCCURRENCE_MEMBER,
    OccurrenceArchiveError,
    aggregate_plant_ecoregions,
    build_plant_ecoregion_csv_from_parquet,
    build_matched_occurrence_parquet,
    filter_occurrences,
    match_occurrences_to_plants,
    run_pipeline,
    spatial_join_ecoregions,
    stream_occurrence_chunks,
    validate_occurrence_archive,
)


def occurrence_row(**overrides):
    row = {
        "gbifID": "1",
        "taxonKey": "100",
        "acceptedTaxonKey": "",
        "speciesKey": "",
        "scientificName": "Plant one",
        "acceptedScientificName": "Plant one",
        "decimalLatitude": "45.0",
        "decimalLongitude": "-75.0",
        "coordinateUncertaintyInMeters": "25",
        "hasGeospatialIssues": "false",
        "basisOfRecord": "HUMAN_OBSERVATION",
        "occurrenceStatus": "PRESENT",
        "eventDate": "2020-06-01",
        "year": "2020",
        "datasetKey": "dataset-a",
        "institutionCode": "inst",
        "collectionCode": "coll",
        "countryCode": "CA",
        "stateProvince": "Ontario",
        "locality": "Ottawa",
    }
    row.update(overrides)
    return row


def occurrence_df(*rows):
    return pd.DataFrame(rows or [occurrence_row()])


class GbifEcoregionArchiveTests(unittest.TestCase):
    def write_zip(self, path: Path, df: pd.DataFrame | None = None, member_name: str = OCCURRENCE_MEMBER):
        df = df if df is not None else occurrence_df()
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(member_name, df.to_csv(sep="\t", index=False))

    def test_streams_occurrence_from_zip_without_extracting(self):
        with self.subTest("valid archive"):
            tmp = Path(self._testMethodName + ".zip")
            self.addCleanup(lambda: tmp.unlink(missing_ok=True))
            self.write_zip(tmp)

            columns = validate_occurrence_archive(tmp)
            chunks = list(stream_occurrence_chunks(tmp, chunksize=1))

            self.assertIn("gbifID", columns)
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].iloc[0]["gbifID"], "1")
            self.assertFalse(Path(OCCURRENCE_MEMBER).exists())

    def test_stream_limit_caps_raw_occurrence_rows(self):
        tmp = Path(self._testMethodName + ".zip")
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))
        self.write_zip(
            tmp,
            occurrence_df(
                occurrence_row(gbifID="1"),
                occurrence_row(gbifID="2"),
                occurrence_row(gbifID="3"),
            ),
        )

        chunks = list(stream_occurrence_chunks(tmp, chunksize=10, limit=1))

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["gbifID"].tolist(), ["1"])

    def test_missing_occurrence_member_fails_clearly(self):
        tmp = Path(self._testMethodName + ".zip")
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))
        self.write_zip(tmp, member_name="verbatim.txt")

        with self.assertRaisesRegex(OccurrenceArchiveError, "does not contain occurrence.txt"):
            validate_occurrence_archive(tmp)

    def test_missing_required_columns_fail_clearly(self):
        tmp = Path(self._testMethodName + ".zip")
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))
        self.write_zip(tmp, occurrence_df().drop(columns=["decimalLatitude"]))

        with self.assertRaisesRegex(OccurrenceArchiveError, "decimalLatitude"):
            validate_occurrence_archive(tmp)


class GbifEcoregionTransformTests(unittest.TestCase):
    def test_filter_keeps_only_valid_canadian_present_records(self):
        df = occurrence_df(
            occurrence_row(gbifID="keep"),
            occurrence_row(gbifID="geo-issue", hasGeospatialIssues="true"),
            occurrence_row(gbifID="absent", occurrenceStatus="ABSENT"),
            occurrence_row(gbifID="usa", countryCode="US"),
            occurrence_row(gbifID="missing-lat", decimalLatitude=""),
            occurrence_row(gbifID="bad-lon", decimalLongitude="-181"),
        )

        filtered = filter_occurrences(df)

        self.assertEqual(filtered["gbifID"].tolist(), ["keep"])
        self.assertEqual(filtered.iloc[0]["decimalLatitude"], 45.0)

    def test_taxon_matching_uses_all_interpreted_key_columns_and_deduplicates(self):
        occurrences = occurrence_df(
            occurrence_row(gbifID="taxon", taxonKey="100", acceptedTaxonKey="", speciesKey=""),
            occurrence_row(gbifID="accepted", taxonKey="999", acceptedTaxonKey="200", speciesKey=""),
            occurrence_row(gbifID="species", taxonKey="999", acceptedTaxonKey="", speciesKey="300"),
            occurrence_row(gbifID="dedupe", taxonKey="100", acceptedTaxonKey="100", speciesKey="100"),
        )
        plants = pd.DataFrame(
            [
                {"usageKey": "100", "input_name": "Taxon match"},
                {"usageKey": "200", "input_name": "Accepted match"},
                {"usageKey": "300", "input_name": "Species match"},
            ]
        )

        matched = match_occurrences_to_plants(occurrences, plants)

        self.assertCountEqual(matched["gbifID"].tolist(), ["taxon", "accepted", "species", "dedupe"])
        self.assertEqual(len(matched[matched["gbifID"].eq("dedupe")]), 1)

    def test_spatial_join_maps_inside_points_and_drops_outside_points(self):
        occurrences = occurrence_df(
            occurrence_row(gbifID="inside", decimalLatitude="0.5", decimalLongitude="0.5"),
            occurrence_row(gbifID="outside", decimalLatitude="2", decimalLongitude="2"),
            occurrence_row(gbifID="boundary", decimalLatitude="0", decimalLongitude="0"),
        )
        filtered = filter_occurrences(occurrences)
        ecoregions = gpd.GeoDataFrame(
            {
                "ECOREGION_ID": [7],
                "ECOREGION_NAME_EN": ["Fixture ecoregion"],
                "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
            },
            crs="EPSG:4326",
        )

        joined = spatial_join_ecoregions(filtered, ecoregions)

        self.assertEqual(joined["gbifID"].tolist(), ["inside"])
        self.assertEqual(joined.iloc[0]["ecoregion_id"], 7)

    def test_aggregation_collapses_to_one_row_per_plant_ecoregion(self):
        rows = occurrence_df(
            occurrence_row(
                gbifID="1",
                taxonKey="100",
                basisOfRecord="HUMAN_OBSERVATION",
                coordinateUncertaintyInMeters="10",
                year="2019",
                datasetKey="a",
            ),
            occurrence_row(
                gbifID="2",
                taxonKey="100",
                basisOfRecord="PRESERVED_SPECIMEN",
                coordinateUncertaintyInMeters="30",
                year="2021",
                datasetKey="b",
            ),
            occurrence_row(
                gbifID="3",
                taxonKey="100",
                basisOfRecord="HUMAN_OBSERVATION",
                coordinateUncertaintyInMeters="50",
                year="2022",
                datasetKey="b",
            ),
        )
        rows["usageKey"] = "100"
        rows["input_name"] = "Plant one"
        rows["ecoregion_id"] = [1, 1, 2]
        rows["ecoregion_name"] = ["A", "A", "B"]

        aggregated = aggregate_plant_ecoregions(rows)

        self.assertEqual(len(aggregated), 2)
        first = aggregated[aggregated["ecoregion_id"].eq(1)].iloc[0]
        second = aggregated[aggregated["ecoregion_id"].eq(2)].iloc[0]
        self.assertEqual(first["occurrence_count"], 2)
        self.assertEqual(first["human_observation_count"], 1)
        self.assertEqual(first["preserved_specimen_count"], 1)
        self.assertEqual(first["coordinate_uncertainty_min_m"], 10)
        self.assertEqual(first["coordinate_uncertainty_median_m"], 20)
        self.assertEqual(first["coordinate_uncertainty_max_m"], 30)
        self.assertEqual(first["first_year"], 2019)
        self.assertEqual(first["last_year"], 2021)
        self.assertEqual(first["dataset_count"], 2)
        self.assertEqual(second["occurrence_count"], 1)

    def test_smoke_pipeline_over_tiny_occurrence_zip(self):
        tmp = Path(self._testMethodName + ".zip")
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))
        with zipfile.ZipFile(tmp, "w") as archive:
            archive.writestr(
                OCCURRENCE_MEMBER,
                occurrence_df(
                    occurrence_row(gbifID="1", taxonKey="100", decimalLatitude="0.5", decimalLongitude="0.5"),
                    occurrence_row(gbifID="2", taxonKey="100", decimalLatitude="10", decimalLongitude="10"),
                ).to_csv(sep="\t", index=False),
            )

        plants = pd.DataFrame([{"usageKey": "100", "input_name": "Plant one"}])
        ecoregions = gpd.GeoDataFrame(
            {
                "ECOREGION_ID": [7],
                "ECOREGION_NAME_EN": ["Fixture ecoregion"],
                "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
            },
            crs="EPSG:4326",
        )

        streamed = pd.concat(
            [filter_occurrences(chunk) for chunk in stream_occurrence_chunks(tmp, chunksize=1)],
            ignore_index=True,
        )
        matched = match_occurrences_to_plants(streamed, plants)
        joined = spatial_join_ecoregions(matched, ecoregions)
        output = aggregate_plant_ecoregions(joined)

        self.assertEqual(len(output), 1)
        self.assertEqual(output.iloc[0]["usageKey"], "100")
        self.assertEqual(output.iloc[0]["ecoregion_id"], 7)
        self.assertEqual(output.iloc[0]["occurrence_count"], 1)

    def test_matched_occurrence_build_logs_chunk_progress(self):
        tmp = Path(self._testMethodName + ".zip")
        plants_path = Path(self._testMethodName + ".csv")
        output_path = Path(self._testMethodName + ".parquet")
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))
        self.addCleanup(lambda: plants_path.unlink(missing_ok=True))
        self.addCleanup(lambda: output_path.unlink(missing_ok=True))
        with zipfile.ZipFile(tmp, "w") as archive:
            archive.writestr(
                OCCURRENCE_MEMBER,
                occurrence_df(
                    occurrence_row(gbifID="1", taxonKey="100"),
                    occurrence_row(gbifID="2", taxonKey="999"),
                ).to_csv(sep="\t", index=False),
            )
        pd.DataFrame([{"usageKey": "100", "input_name": "Plant one"}]).to_csv(
            plants_path, index=False
        )

        with patch.object(pd.DataFrame, "to_parquet"), self.assertLogs(
            "etl.gbif_ecoregions", level="INFO"
        ) as logs:
            matched = build_matched_occurrence_parquet(
                tmp, plants_path, output_path, chunksize=1, limit=1
            )

        self.assertEqual(matched["gbifID"].tolist(), ["1"])
        self.assertTrue(any("chunk=1" in line for line in logs.output))
        self.assertTrue(any("cumulative_matched_rows=1" in line for line in logs.output))

    def test_run_pipeline_logs_total_matched_before_spatial_join(self):
        tmp = Path(self._testMethodName + ".zip")
        plants_path = Path(self._testMethodName + ".csv")
        output_dir = Path(self._testMethodName)
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))
        self.addCleanup(lambda: plants_path.unlink(missing_ok=True))
        self.addCleanup(lambda: (output_dir / "matched.parquet").unlink(missing_ok=True))
        self.addCleanup(lambda: output_dir.rmdir() if output_dir.exists() else None)
        with zipfile.ZipFile(tmp, "w") as archive:
            archive.writestr(
                OCCURRENCE_MEMBER,
                occurrence_df(occurrence_row(gbifID="1", taxonKey="100")).to_csv(
                    sep="\t", index=False
                ),
            )
        pd.DataFrame([{"usageKey": "100", "input_name": "Plant one"}]).to_csv(
            plants_path, index=False
        )

        with patch.object(pd.DataFrame, "to_parquet"), patch(
            "etl.gbif_ecoregions.build_plant_ecoregion_csv_from_parquet",
            return_value=pd.DataFrame([{"usageKey": "100", "ecoregion_id": 7}]),
        ), self.assertLogs("etl.gbif_ecoregions", level="INFO") as logs:
            output = run_pipeline(
                zip_path=tmp,
                plants_csv_path=plants_path,
                ecoregions_geojson_path="ecoregions.geojson",
                output_dir=output_dir,
                matched_occurrences_filename="matched.parquet",
                plant_ecoregions_filename="plant_ecoregions.csv",
                chunksize=10,
                limit=1,
            )

        self.assertEqual(len(output), 1)
        self.assertTrue(
            any("matched occurrence total before spatial join rows=1" in line for line in logs.output)
        )

    def test_parquet_spatial_stage_aggregates_batches_without_full_join(self):
        output_path = Path(self._testMethodName + ".csv")
        self.addCleanup(lambda: output_path.unlink(missing_ok=True))
        ecoregions = gpd.GeoDataFrame(
            {
                "ECOREGION_ID": [7],
                "ECOREGION_NAME_EN": ["Fixture ecoregion"],
                "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
            },
            crs="EPSG:4326",
        )
        chunks = [
            occurrence_df(
                occurrence_row(
                    gbifID="1",
                    taxonKey="100",
                    decimalLatitude="0.25",
                    decimalLongitude="0.25",
                    coordinateUncertaintyInMeters="10",
                    basisOfRecord="HUMAN_OBSERVATION",
                    year="2019",
                    datasetKey="a",
                )
            ).assign(usageKey="100", input_name="Plant one"),
            occurrence_df(
                occurrence_row(
                    gbifID="2",
                    taxonKey="100",
                    decimalLatitude="0.75",
                    decimalLongitude="0.75",
                    coordinateUncertaintyInMeters="30",
                    basisOfRecord="PRESERVED_SPECIMEN",
                    year="2021",
                    datasetKey="b",
                )
            ).assign(usageKey="100", input_name="Plant one"),
        ]

        with patch("etl.gbif_ecoregions.gpd.read_file", return_value=ecoregions), patch(
            "etl.gbif_ecoregions._existing_parquet_columns",
            return_value=["gbifID", "decimalLatitude", "decimalLongitude"],
        ), patch("etl.gbif_ecoregions.stream_parquet_chunks", return_value=iter(chunks)):
            output = build_plant_ecoregion_csv_from_parquet(
                "matched.parquet", "ecoregions.geojson", output_path, chunksize=1
            )

        self.assertEqual(len(output), 1)
        row = output.iloc[0]
        self.assertEqual(row["occurrence_count"], 2)
        self.assertEqual(row["human_observation_count"], 1)
        self.assertEqual(row["preserved_specimen_count"], 1)
        self.assertEqual(row["coordinate_uncertainty_median_m"], 20)
        self.assertEqual(row["first_year"], 2019)
        self.assertEqual(row["last_year"], 2021)
        self.assertEqual(row["dataset_count"], 2)


if __name__ == "__main__":
    unittest.main()
