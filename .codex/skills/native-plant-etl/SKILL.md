---
name: native-plant-etl
description: Run and maintain the native-plant-finder ETL and scraper pipeline. Use when working on GBIF ecoregion ETL, Lady Bird Johnson trait scraping, app-ready JSON generation, shared dataset column contracts, ETL tests, or requests to regenerate or validate native plant datasets.
---

# Native Plant ETL

## Start Here

Work from the repository root. Inspect `git status --short` before changing files and preserve unrelated user changes.

Use `dataset_columns.py` as the source of truth for CSV and app-data field names used across `etl/` and `scraper/`. Add or rename shared fields there first, then update callers. Keep imports at the top of Python files and reuse `etl.functions.normalize_key` for `usageKey` normalization. Shared CSV and JSON field names live in `dataset_columns.py`. Update that file
first when changing data contracts used across `etl/` and `scraper/`.

Do not regenerate ignored dataset outputs unless the user explicitly asks. Changes to ETL logic should usually be validated with tests and small fixtures instead.

## Pipeline Commands

Install dependencies when needed:

```powershell
pip install -r requirements.txt
```

Run the GBIF ecoregion ETL smoke test:

```powershell
python -m etl.gbif_ecoregions_cli `
  --zip datasets/0026180-260623161305970.zip `
  --plants datasets/gbif_species_match_cleaned.csv `
  --ecoregions datasets/ecoregions.geojson `
  --output-dir datasets/derived `
  --limit 100 `
  --log-level INFO
```

Run the full GBIF ecoregion ETL by removing `--limit`. If matching already completed and only the spatial join needs rerunning, use:

```powershell
python -m etl.gbif_ecoregions_cli `
  --ecoregions datasets/ecoregions.geojson `
  --output-dir datasets/derived `
  --skip-matching `
  --log-level INFO
```

Run the Lady Bird Johnson scraper:

```powershell
python -m scraper.lady_bird_johnson `
  --input datasets/gbif_species_match_cleaned.csv `
  --output-dir datasets/lbj `
  --delay 1 `
  --timeout 20 `
  --retries 3 `
  --log-level INFO
```

For resumable batches, add `--limit 100` and reuse the same `--output-dir`.

Run app-data generation only when requested:

```powershell
python -m etl.app_data_cli `
  --plant-ecoregions datasets/derived/plant_ecoregions.csv `
  --lbj-traits datasets/lbj/lbj_traits.csv `
  --lbj-traits datasets/lbj_rerun/lbj_traits.csv `
  --recommendation-categories curation/recommendation_categories.csv `
  --output-dir datasets/app_data `
  --log-level INFO
```

Later `--lbj-traits` files win on duplicate `usageKey`, so the default command prefers `datasets/lbj_rerun/lbj_traits.csv` over `datasets/lbj/lbj_traits.csv`.

## Data Contracts

GBIF ecoregion ETL writes `datasets/derived/plant_ecoregions.csv`.

LBJ scraper writes `lbj_raw.jsonl`, `lbj_traits.csv`, and `lbj_review.csv` under its output directory. It resumes from `lbj_raw.jsonl`; no manual offset is needed.

App-data ETL writes `datasets/app_data/manifest.json` and `datasets/app_data/ecoregions/{ecoregionId}.json`. App JSON uses camelCase fields, pipe-delimited traits as arrays, missing scalar values as `null`, missing multi-value traits as empty arrays, and decimal values rounded to two places.

## Verification

Run focused tests for touched areas, then the full offline suite:

```powershell
python -m unittest tests.test_app_data
python -m unittest discover tests
```

Use the live scraper fixture before a large scrape when changing matching or parsing behavior:

```text
scraper/fixtures/live_sample.csv
scraper/fixtures/live_sample_expected_lbj_ids.json
```
