---
name: images-etl
description: Run, inspect, rerun, and merge native-plant-finder image ETL outputs from GBIF and Wikimedia Commons. Use when working on plant image coverage, plant_images app-data buckets, GBIF image API runs, retry-only image reruns, manual_review.csv, qa_report.json, Wikimedia Commons fallback candidates, or merging fallback images into datasets/app_data/plant_images.
---

# Images ETL

## Overview

Use this skill to reason about and operate the native plant image pipeline without corrupting the app-data contract. The production image output is a bucketed static index under `datasets/app_data/plant_images`; GBIF is the primary source and Wikimedia Commons is the preferred fallback for usageKeys that still have no accepted GBIF image.

## Start Here

Work from the repo root. Run `git status --short` before editing or merging outputs and preserve unrelated user changes.

Final image artifacts are:

- `datasets/app_data/plant_images/manifest.json`
- `datasets/app_data/plant_images/buckets/*.json`
- `datasets/app_data/plant_images/qa_report.json`
- `datasets/app_data/plant_images/manual_review.csv`

Do not write raw GBIF responses, downloaded DWCA zips, candidate caches, or intermediate occurrence/media files into `datasets/app_data/plant_images`. Use `$env:TEMP` for smoke outputs, retry outputs, candidate CSVs, backups, and inspection reports.

## Source Strategy

Use sources in this order:

1. GBIF API mode: primary production path. It respects the existing ETL gates for taxon match, open license, occurrence status, GBIF issues, specimen detection, URL validation, and dimensions.
2. GBIF retry-only reruns: use after a full run leaves `gbif_api_transient_failure` or `transient_image_url_failure` rows. Rerun only those usageKeys to a Temp output, then merge accepted records back.
3. Wikimedia Commons via Wikidata `P18`: first fallback for usageKeys still missing after GBIF. It is high-confidence because it maps taxon name `P225` to a Commons image `P18`.
4. Broader Wikimedia Commons search: optional, manual-review-heavy fallback when `P18` misses. Use conservative title/name matching and do not auto-merge without review.
5. LBJ or other sites: use only as links or permissioned/manual sources unless per-image reuse rights are clear.

Keep excluding `HIGHERRANK` problem keys by default using `datasets/problems_cleaned.csv`. Use `--include-problem-keys` only when explicitly requested.

## Run GBIF

Smoke run:

```powershell
python -m etl.gbif_images_cli --plants datasets/gbif_species_match_cleaned.csv --problems datasets/problems_cleaned.csv --limit-usage-keys 100 --limit-per-taxon 20 --delay-between-taxa 1.0 --delay-between-url-checks 0.25 --output-dir "$env:TEMP\gbif-images-api-smoke-100" --log-level INFO
```

Full run:

```powershell
python -m etl.gbif_images_cli --plants datasets/gbif_species_match_cleaned.csv --problems datasets/problems_cleaned.csv --limit-per-taxon 20 --delay-between-taxa 1.0 --delay-between-url-checks 0.25 --output-dir datasets/app_data/plant_images --log-level INFO
```

Prefer single-line PowerShell commands for this ETL. Backtick continuations can silently break if there is trailing whitespace and may cause `--output-dir` to be omitted, writing to the default production path.

## Inspect Outputs

Read `qa_report.json` first. Reconstruct accepted usageKeys from `buckets/*.json`; do not infer them from `manual_review.csv`.

Interpret `manual_review.csv` as follows:

- Rows with `slot=primaryImage` or `slot=secondaryImage` are already accepted app images. `manualReviewReason=unknown_dimensions` usually means GBIF omitted dimensions, not that the image failed.
- Rows with `rejectionReason` are rejected candidate images or transient failure records.
- Common rejected reasons: `disallowed_or_missing_license`, `likely_specimen_image`, `non_image_media`, `major_gbif_issue`, `not_present`, `gbif_api_transient_failure`, `transient_image_url_failure`.

When producing inspection CSVs, write them to `$env:TEMP` and include plant names by joining against `datasets/gbif_species_match_cleaned.csv`.

## Retry GBIF Failures

Create a retry-only CSV from a missing/manual-review classification file:

```powershell
Import-Csv "$env:TEMP\gbif-images-missing-manual-review-classification.csv" |
  Where-Object { $_.manualDecision -eq "retry_before_deciding" } |
  Select-Object usageKey |
  Export-Csv "$env:TEMP\gbif-images-retryable-usage-keys.csv" -NoTypeInformation
```

Run retries to a fresh Temp directory:

```powershell
$out = Join-Path $env:TEMP ("gbif-images-retryable-rerun-" + (Get-Date -Format "yyyyMMddHHmmss"))
python -m etl.gbif_images_cli --plants "$env:TEMP\gbif-images-retryable-usage-keys.csv" --limit-per-taxon 20 --delay-between-taxa 1.0 --delay-between-url-checks 0.25 --output-dir "$out" --log-level INFO
```

Never run a retry subset directly into `datasets/app_data/plant_images`; it will overwrite the full index with only the subset.

## Find Wikimedia Commons Fallbacks

Use Wikimedia Commons only for usageKeys still missing after GBIF and GBIF retries. Start from a remaining-missing CSV in Temp.

Preferred query path:

- Query Wikidata SPARQL for taxon names: `?taxon wdt:P225 ?taxonName; wdt:P18 ?image`.
- Convert `Special:FilePath/...` image URLs to Commons `File:` titles.
- Fetch Commons `imageinfo` with `iiprop=url|size|mime|extmetadata`.
- Accept only open licenses compatible with the app policy: `CC0`, `Public Domain`, `CC BY`, `CC BY-SA`. Treat `No restrictions` as public-domain-like only after metadata review.
- Reject or hold for review candidates whose title or metadata suggests `herbarium`, `specimen`, `pressed`, `sheet`, or `scan`.

Write these Temp review files:

- all Commons candidates
- best candidate per usageKey
- no-open-match list
- skipped likely-specimen list
- summary JSON

Do not merge broader Commons text-search results automatically unless the user explicitly accepts the manual-review risk.

## Merge Back

Before any merge into `datasets/app_data/plant_images`, make a full Temp backup:

```powershell
Copy-Item datasets/app_data/plant_images "$env:TEMP\plant_images_backup_before_merge_$(Get-Date -Format yyyyMMddHHmmss)" -Recurse
```

Merge rules:

- Add only usageKeys that are still absent from the target bucket index, unless deliberately replacing an existing image.
- Compute bucket as `usageKey % 64` and write to `buckets/{bucket}.json`.
- Preserve the bucket record contract: `usageKey`, `primaryImage`, `secondaryImage`.
- GBIF records use `source=gbif`; Commons records use `source=wikimedia_commons`, `publisher=Wikimedia Commons`, `gbifId=null`.
- For Commons fallbacks, add one `primaryImage` and leave `secondaryImage=null` unless there is a reviewed reason to add more.
- Strip tracking query strings from Commons `imageUrl` and `thumbnailUrl` before merging.
- Append accepted fallback rows to `manual_review.csv` with `manualReviewReason=commons_fallback`.
- Append skipped/rejected fallback rows to `manual_review.csv` with an appropriate `rejectionReason` only when useful for audit.

After merging:

1. Regenerate `manifest.json` from actual bucket counts.
2. Regenerate `qa_report.json` from bucket records and `manual_review.csv`.
3. Recompute the remaining-missing CSV by comparing checked usageKeys to bucket keys.
4. Verify `manifest` counts match bucket file lengths.
5. Report backup path, source path, merged key count, remaining missing count, and changed final artifacts.

## Validation

Run focused validation for code changes:

```powershell
python -m unittest tests.test_gbif_images tests.test_gbif_images_cli
python -m unittest discover tests
```

For data-only merges, validate by reading the JSON/CSV artifacts rather than rerunning the full ETL:

- `qa_report.json` has consistent checked/accepted/missing counts.
- `sum(manifest.buckets[].plantCount)` equals the number of usageKeys across all bucket JSONs.
- `manual_review.csv` remains parseable by pandas.
- No raw API responses or candidate caches were written into `datasets/app_data/plant_images`.
