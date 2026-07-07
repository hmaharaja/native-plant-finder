import re

import pandas as pd
import requests


def filter_corrupted_rows(df: pd.DataFrame, columns=None):
    """Remove rows with UTF-8 mojibake (e.g., Ã— for ×)."""
    if columns is None:
        columns = df.select_dtypes(include=['object']).columns.tolist()
    corrupted = re.compile(r'Ã')
    mask = pd.Series([True] * len(df), index=df.index)
    for col in columns:
        if col in df.columns:
            mask &= ~df[col].astype(str).apply(lambda x: bool(corrupted.search(x)))
    return df[mask]


def load_dataset(file_path: str):
    df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
    return filter_corrupted_rows(df)


def retrieve_ecoregions_geojson_file():
    url = "https://agriculture.canada.ca/atlas/data_donnees/nationalEcologicalFramework/data_donnees/geoJSON/er/nef_ca_ter_ecoregion_v2_2.geojson"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    with open("ecoregions.geojson", "wb") as f:
        f.write(resp.content)