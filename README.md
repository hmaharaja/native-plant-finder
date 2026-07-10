# Description

A tool to help everyday people find plants native to their region that can be planted on their property.

# Architecture / Tech Stack

## Overview

- Python (ETL, web scraper)
- ReactJS (client side)
- GitHub Pages (hosting)
- JSON files (data storage, can be changed to SQLite if JSON proves too cumbersome)

## Data Sources
- VASCAN for taxonomic information about Canadian native plants, including scientific names, vernacular names, province-level categorization of native habitats, taxonomic growth habits (shrub/herb/tree)
- GBIF API for taxon keys (aka usageKey), occurrence information for each plant included in the VASCAN data
- Lady Bird Johnson for gardening traits and characteristics (growth habit, mature height, soil moisture, soil type, link to lbj page for further detail, etc - needs to be scraped, LBJ has no exposed API)
- Environment Canada ecoregion polygons - spatial join target

The dataset for this app is built by getting the VASCAN information and cleaning it. Then that is joined with GBIF species match data to incude the taxonKey (and also find any problems, i.e rows that don't have specific taxa in the GBIF db, which are filtered out and kept for manual review in a separate csv).

The occurrence data is to be joined with the cleaned taxonomic data, and ecoregions.json can be used to get the ecoregions each plant belongs to. Any plants that don't have data should be manually filled in.

The LBJ scraped data is to be added to the dataset via a join, to make the final enriched data.

## Lady Bird Johnson traits scraper

Run the sequential, resumable scraper from the repository root:

```powershell
python -m scraper.lady_bird_johnson `
  --input datasets/gbif_species_match_cleaned.csv `
  --output-dir datasets/lbj
```

It writes an append-only `lbj_raw.jsonl` checkpoint plus regenerated
`lbj_traits.csv` and `lbj_review.csv` files. Re-running the command skips every
`usageKey` already present in the checkpoint. Useful sampling and network
options are `--limit 15`, `--delay 1`, `--timeout 20`, and `--retries 3`.
Missing, ambiguous, and permanently failed rows are retained for review rather
than matched fuzzily.

Run the offline scraper tests with:

```powershell
python -m unittest discover -s tests -v
```

## UX / Client Side

- User enters their postal code or city, which the server maps to an ecoregion via internal module
- User can optionally enter filters for the soil type, soil depth, sun exposure, moisture level of their planting area, what growth habit they want to plant (flower, herb, tree, grass, etc)
- User can optionally have different flows for if they plan to put these in pots or in the ground
- Once the data is entered, the page just returns a paginated list of plants that work for their region and preferences

## MVP

- User enters their location and gets back a paginated list of plants showing the common name, scientific name, growth traits, and a link to more details


# Future Extensions
- Support USA by adding USDA plants via another ETL pipeline
