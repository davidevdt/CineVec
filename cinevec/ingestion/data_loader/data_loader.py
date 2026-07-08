"""
This module is based on the code in notebooks/data_download.ipynb, which was used to download and preprocess the TMDB-style dataset. 
"""

import pandas as pd 
import numpy as np 
from typing import Optional
from box import ConfigBox

from cinevec.utils.file_utils import path_exists, create_path
from cinevec.logging import logger


def download_data(config: ConfigBox) -> pd.DataFrame: 
    """
    Download the TMDB-style dataset from the specified URL in the config file.
    """
    data_url = config.data_url
    df = pd.read_csv(data_url)

    if len(df): 
        logger.info(f"Downloaded {len(df)} rows from {data_url}") 

    return df 



def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and preprocess the TMDB-style dataset.
    """
    VOTE_FLOOR_M = np.median(df.vote_count) # median vote count across all movies
    C = np.mean(df.vote_average) # average rating across all movies

    def calc_weighted_rating(row): 
        vote_count = row['vote_count'] 
        vote_avg = row['vote_average'] 
        return np.round((vote_count / (vote_count + VOTE_FLOOR_M)) * vote_avg + (VOTE_FLOOR_M / (vote_count + VOTE_FLOOR_M)) * C, 3)

    df_clean = df.assign(
    title=df.title.str.strip(),
    language=df.original_language.str.strip(),
    year=df.release_date.str.split('-').str[0].astype(int), 
    genres=df.genre.str.split('|').apply(lambda x: [g.strip() for g in x] if isinstance(x, list) else []),
    plot=df.overview.str.strip(),
    vote_count=df.vote_count.apply(lambda x: int(float(x))), 
    rating=df.vote_average.apply(lambda x: float(x) if pd.notnull(x) else None), 
    weighted_rating=df.apply(calc_weighted_rating, axis=1)
    )[[
        'id', 'title', 'year', 'genres', 'language', 'rating', 'vote_count', 'weighted_rating', 'plot'
    ]]

    return df_clean


def store_df(df: pd.DataFrame, path: str) -> None:
    """
    Store the cleaned DataFrame to a CSV file at the specified path.
    """
    df.to_csv(path, index=False)
    logger.info(f"Stored cleaned DataFrame to {path}")



def load_and_store_data(config: ConfigBox, sample_n: Optional[int] = None) -> pd.DataFrame:
    """
    Load the TMDB-style dataset, clean it, and store it to a CSV file.
    If the cleaned data file already exists, load it instead of downloading and cleaning again.
    """
    output_path = config.data_df_path

    if path_exists(output_path):
        logger.info(f"Data file already exists at {output_path}. Loading it instead of downloading.")
        df_clean = pd.read_csv(output_path)
        if sample_n and sample_n < len(df_clean):
            df_clean = df_clean.sample(n=sample_n, random_state=42, replace=False)
        return df_clean

    df = download_data(config)
    df_clean = clean_data(df)

    if sample_n and sample_n < len(df_clean):
        df_clean = df_clean.sample(n=sample_n, random_state=42, replace=False)
    
    create_path(output_path)  # Ensure path exists
    store_df(df_clean, output_path)

    return df_clean
