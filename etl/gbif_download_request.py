import json
import pprint
import time

import pandas as pd
import requests

from etl.functions import load_dataset

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

def format_download_request(taxon_key_df: pd.DataFrame):
    with open(GBIF_DOWNLOAD_REQ_TEMPLATE, 'r') as f:
        request = json.load(f)
    
    taxon_keys = set(taxon_key_df['usageKey'].astype(int).tolist())
    print(f"{len(taxon_keys)} unique taxon keys, from {len(taxon_key_df)} clean species rows")
    
    request['predicate']['predicates'][0]['values'] = [str(k) for k in taxon_keys]
    return request
    

def main():
    df = pd.read_csv(GBIF_SPECIES_MATCH_CLEANED_FILE_PATH)
    print(format_download_request(df))
    

if __name__ == '__main__':
    main()

        