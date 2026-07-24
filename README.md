# Description

A tool to help everyday people find plants native to their region that can be planted on their property.

# Architecture / Tech Stack

## Overview

- Python (ETL, web scraper)
- ReactJS (client side)
- GitHub Pages (hosting)
- JSON files (data storage, can be changed to SQLite if JSON proves too cumbersome)

## UX / Client Side

- User enters their postal code or city, which the server maps to an ecoregion via internal module
- User can optionally enter filters for the soil type, soil depth, sun exposure, moisture level of their planting area, what growth habit they want to plant (flower, herb, tree, grass, etc)
- User can optionally have different flows for if they plan to put these in pots or in the ground
- Once the data is entered, the page just returns a paginated list of plants that work for their region and preferences

## Data Sources
- VASCAN for taxonomic information about Canadian native plants, including scientific names, vernacular names, province-level categorization of native habitats, taxonomic growth habits (shrub/herb/tree)
- GBIF API for taxon keys (aka usageKey), occurrence information for each plant included in the VASCAN data
- Lady Bird Johnson for gardening traits and characteristics (growth habit, mature height, soil moisture, soil type, link to lbj page for further detail, etc - needs to be scraped, LBJ has no exposed API)
- Environment Canada ecoregion polygons - spatial join target

The dataset for this app is built by getting the VASCAN information and cleaning it. Then that is joined with GBIF species match data to incude the taxonKey (and also find any problems, i.e rows that don't have specific taxa in the GBIF db, which are filtered out and kept for manual review in a separate csv).

The occurrence data is to be joined with the cleaned taxonomic data, and ecoregions.json can be used to get the ecoregions each plant belongs to. Any plants that don't have data should be manually filled in.

The LBJ scraped data is to be added to the dataset via a join, to make the final enriched data.

### GBIF ecoregion occurrence ETL

The GBIF ecoregion ETL streams the downloaded GBIF occurrence zip, filters valid
Canadian presence records, matches them to `gbif_species_match_cleaned.csv`, and
spatially joins occurrence points to Environment Canada ecoregions.

The CLI logs progress after each chunk, including raw rows read, filtered rows,
matched rows, and cumulative matched rows. It also logs total matched occurrences
before the spatial join, so large runs do not look stalled.

Useful options:

- `--chunksize 100000`: number of raw occurrence rows streamed per chunk.
- `--limit 100`: cap raw occurrence rows for quick testing.
- `--matched-occurrences-filename`: override the Parquet output filename.
- `--plant-ecoregions-filename`: override the CSV output filename.
- `--skip-matching`: skip the matching phase and use the existing Parquet files to join.

### App data ETL

The app data ETL builds static JSON files for the GitHub Pages client. It
prejoins `plant_ecoregions.csv` with both LBJ trait CSVs so the React app can
fetch one ecoregion file without doing runtime joins.

## Lady Bird Johnson traits scraper

The LBJ scraper enriches the cleaned GBIF species-match CSV with gardening
traits from Lady Bird Johnson. It is sequential, resumable, and intended to be
run as an ETL batch job.

Re-running the scraper with the same `--output-dir` resumes automatically. It
loads `lbj_raw.jsonl`, skips completed `usageKey` values, processes only new
rows, and regenerates the two CSV outputs from the checkpoint.

The checkpoint file is the offset. Use the same
`--output-dir` each time; changing it starts a separate scrape.

Matching policy:

- Search by vernacular name first, then fall back to canonical name.
- Accept direct LBJ redirects.
- Accept exact scientific-name matches.
- Accept explicit LBJ synonym matches.
- Send ambiguous, unmatched, failed, or non-verified rows to `lbj_review.csv`.
- Do not infer missing traits; unknown trait categories are preserved and logged.

## Client app

The GitHub Pages client lives in `client/`. It is a static React + Vite app
that fetches prebuilt JSON from `client/public/data`.

Prepare client data after app data exists:

```powershell
python -m etl.client_data_cli
```

Run the client locally:

```powershell
cd client
npm install
npm run dev
```

Build and test:

```powershell
cd client
npm run test
npm run build
```

The v1 client uses Nominatim only on explicit location form submission, limits
lookups to Canada, keeps lookups in browser memory only, and fetches one
ecoregion plant JSON file per selected region.
