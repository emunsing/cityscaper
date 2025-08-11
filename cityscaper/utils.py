import os
import pyreadr
import json
import pathlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from cityscaper.constants import DATA_DIR, OUTPUT_DIR


def read_rds_to_df(fname: os.PathLike, index_cols: str|list):
    if isinstance(index_cols, str):
        index_cols = [index_cols]
    archive = pyreadr.read_r(fname)
    assert len(archive.keys()) == 1, "Multiple objects returned!"
    return archive[list(archive.keys())[0]].set_index(index_cols)


def resolve_path(fname, default_parent=OUTPUT_DIR):
    resolved_path = pathlib.Path(fname).expanduser().resolve()
    if len(resolved_path.parents)==1:
        # Assume that we don't actually want to put something in root, so instead put it under the default_parent)
        resolved_path = pathlib.Path(default_parent).expanduser().resolve() / fname
    return resolved_path


def sorted_columns(df):
    return sorted(df.columns, key=lambda col: col.lower())


def latlon_filter(df, west, south, east, north):
    return df[(west <= df['lng']) & (df['lng'] <= east) & (south <= df['lat']) & (df['lat'] <= north)]


def geojson_rds_to_json(fname):
    # Load geometry data
    # Use this like: mapblklot_to_geom = {obj['properties']['mapblklot']: obj['geometry']['coordinates'] for obj in geom_json['features']}
    geom_reader = pyreadr.read_r(fname)
    geom_json = json.loads(geom_reader[None]['data'][0])
    assert len(geom_json['features']) > 0, "No features found in the geometry data!"
    obj0 = geom_json['features'][0]
    assert 'properties' in obj0, "No properties found in the geometry data!"
    assert 'geometry' in obj0, "No geometry found in the geometry data!"
    return geom_json


def geojson_to_parcel_bound_latlon(geojson:dict) -> dict:
    return {f['properties']['mapblklot']: f['geometry']['coordinates'] for f in geojson['features']}
