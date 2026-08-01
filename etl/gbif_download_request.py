import json
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

from etl.functions import filter_corrupted_rows, load_dataset

RAW_FILE_PATH = 'datasets/vascan_data_raw.txt'
GBIF_SPECIES_MATCH_FILE_PATH = 'datasets/gbif_species_match.csv'
GBIF_SPECIES_MATCH_CLEANED_FILE_PATH = 'datasets/gbif_species_match_cleaned.csv'
CLEANED_PROBLEMS_FILE_PATH = 'datasets/problems_cleaned.csv'
GBIF_DOWNLOAD_REQ_TEMPLATE = 'gbif_download_request.json'

def get_gbif_taxon_key(sci_name: str):
    url = "https://api.gbif.org/v2/species/match"
    
    params = {
        "scientificName": sci_name,
        "kingdom": "Plantae",
    }
    
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    
    data: dict = resp.json()
    usage: dict = data.get("usage", {})
    diagnostics: dict = data.get("diagnostics", {})
    is_synonym: bool = data.get("synonym", False)
    
    result = {
        "input_name": sci_name,
        "usageKey": usage.get("key"),
        "matchType": diagnostics.get("matchType"),
        "confidence": diagnostics.get("confidence"),
        "status": usage.get("status"),
        "canonicalName": usage.get("canonicalName")
    }
    
    if is_synonym:
        accepted = data.get("acceptedUsage")
        if not accepted:
            result["needs_review"] = True
            result["review_reason"] = "synonym=True but no acceptedUsage present — verify raw response"
            return result
        
        key_source = accepted
    else:
        key_source = usage
    
    result["resolved_key"] = key_source.get("key")
    result["resolved_rank"] = key_source.get("rank")

    if result["resolved_rank"] != "SPECIES":
        result["needs_review"] = True
        result["review_reason"] = f"resolved rank is {result['resolved_rank']}, not SPECIES"

    return result

def get_df_from_raw_dataset():
    df = load_dataset(RAW_FILE_PATH)
    target_provinces = ["Ontario", "Quebec", "Alberta", "British Columbia"]
    native_mask = (df[target_provinces] == "Native").any(axis=1)
    filtered = df[native_mask].copy()
    
    return filtered
    
def create_gbif_species_match_csv(input_df: pd.DataFrame, sci_name_column: str, output_file_path: str):
    results = []
    i = 0
    total = len(input_df)

    for name in input_df[sci_name_column]:
        results.append(get_gbif_taxon_key(name))
        time.sleep(0.1) # be polite to the API
        i += 1
        percent_completed = (i / total) * 100
        
        if percent_completed != float(0) and percent_completed % 2 == 0:
            print(f"{percent_completed}% completed")

    resolved_df = pd.DataFrame(results)
    
    resolved_df.to_csv(output_file_path, index=False)

def find_problems_in_species_match():
    resolved_df = pd.read_csv(GBIF_SPECIES_MATCH_CLEANED_FILE_PATH)

    problems = resolved_df[
        (resolved_df["matchType"] != "EXACT") |
        (resolved_df["usageKey"].isna())
    ]
    problems.to_csv('problems.csv', index=False)

def format_download_request(
    taxon_key_df: pd.DataFrame,
    *,
    template_path: str = GBIF_DOWNLOAD_REQ_TEMPLATE,
    taxon_key_column: str = "usageKey",
):
    with open(template_path, 'r') as f:
        request = json.load(f)
    
    taxon_keys = set(taxon_key_df[taxon_key_column].astype(int).tolist())
    print(f"{len(taxon_keys)} unique taxon keys, from {len(taxon_key_df)} clean species rows")
    
    if len(taxon_keys) != len(taxon_key_df):
        key_counts = taxon_key_df[taxon_key_column].value_counts()
        duplicated_keys = key_counts[key_counts > 1]

        dupes = taxon_key_df[taxon_key_df[taxon_key_column].isin(duplicated_keys.index)].sort_values(taxon_key_column)
        dupe_columns = [
            column
            for column in ("input_name", taxon_key_column, "matchType", "status")
            if column in dupes.columns
        ]
        print(dupes[dupe_columns])
    
    request['predicate']['predicates'][0]['values'] = [str(k) for k in taxon_keys]
    return request


def send_download_request(formatted_request: dict):
    resp = requests.post(
        "https://api.gbif.org/v1/occurrence/download/request",
        json=formatted_request,
        auth=(os.getenv("GBIF_USER"), os.getenv("GBIF_PWD"))
    )
    resp.raise_for_status()
    download_key = resp.text.strip()
    print(f"Download queued: {download_key}")


def add_vernacular_names_to_gbif():
    # Load vascan data - only filter corrupted rows on scientific name column
    # (French vernacular names have mojibake but we only need English names)
    vascan_df = pd.read_csv(RAW_FILE_PATH, sep='\t', encoding='utf-8')
    vascan_df = filter_corrupted_rows(vascan_df, columns=['Scientific name'])
    vascan_df = vascan_df[['Scientific name', 'Vernacular en']].drop_duplicates(subset=['Scientific name'])

    # Strip whitespace from both columns for matching
    vascan_df['Scientific name'] = vascan_df['Scientific name'].str.strip()

    # Load gbif data and apply filter_corrupted_rows
    gbif_df = pd.read_csv(GBIF_SPECIES_MATCH_CLEANED_FILE_PATH)
    gbif_df = filter_corrupted_rows(gbif_df)

    # Drop vernacularName column if it exists (to re-merge)
    if 'vernacularName' in gbif_df.columns:
        gbif_df = gbif_df.drop(columns=['vernacularName'])

    gbif_df['input_name'] = gbif_df['input_name'].str.strip()

    # Create a lookup dictionary for faster matching
    vernacular_lookup = dict(zip(vascan_df['Scientific name'], vascan_df['Vernacular en']))

    gbif_df['vernacularName'] = gbif_df['input_name'].map(vernacular_lookup)
    gbif_df.to_csv(GBIF_SPECIES_MATCH_CLEANED_FILE_PATH, index=False)

    matched_count = gbif_df['vernacularName'].notna().sum()
    print(f"Added vernacular names to {matched_count}/{len(gbif_df)} rows")

def pull_completed_gbif_download(download_key: str):
    url = f"https://api.gbif.org/v1/occurrence/download/request/{download_key}"
    
    with requests.get(url, stream=True) as response:
        # Ensure the request succeeded
        response.raise_for_status()

        with open("datasets/downloaded_occurrence_data.bin", "wb") as file:
            # Step 3: Stream the content in blocks (e.g., 8192 bytes)
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # Filter out keep-alive new chunks
                    file.write(chunk)
    
     
def main():
    # add_vernacular_names_to_gbif()

    # gbif_df = pd.read_csv(GBIF_SPECIES_MATCH_CLEANED_FILE_PATH)
    # gbif_df = filter_corrupted_rows(gbif_df)
    # problems_df = pd.read_csv(CLEANED_PROBLEMS_FILE_PATH)

    # # Remove rows from gbif_df where scientificName matches those in problems_df
    # problem_names = set(problems_df['input_name'])
    # gbif_df = gbif_df[~gbif_df['input_name'].isin(problem_names)]

    # formatted_request = format_download_request(gbif_df)
    
    # load_dotenv()
    # send_download_request(formatted_request)
    
    download_key = ""
    pull_completed_gbif_download(download_key)
    
    

if __name__ == '__main__':
    main()

        
