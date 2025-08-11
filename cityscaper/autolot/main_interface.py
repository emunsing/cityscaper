import geopandas as gpd
import pandas as pd
from typing import List, Dict

from shapely import MultiPolygon
from cityscaper.utils import  geojson_rds_to_json
from cityscaper.autolot.utils import geojson_to_parcel_bounds
from cityscaper.constants import DATA_DIR
from cityscaper.autolot.streets import get_street_buffer
from cityscaper.autolot.parcel_analysis import get_sides_df
from loguru import logger
from shapely.geometry import Polygon
from pathlib import Path


def _setup_data_and_streets(block_ids: List[str],
parcel_data_path: Path = DATA_DIR / "sf_map_unfiltered.RDS",
street_buffer_size: float = 1) -> tuple[gpd.GeoSeries, Polygon]:
    """
    Shared setup function that loads parcel data and street maps.
    
    Args:
        block_ids: List of block IDs to process
        
    Returns:
        Tuple of (parcel_series, street_buffer) where parcel_series maps block IDs to geometries
        and street_buffer is the buffered street network, both in meters (EPSG:3857)
    """
    # Load the unfiltered geometry data
    raw_geom_geojson = geojson_rds_to_json(parcel_data_path)
    clean_geom = geojson_to_parcel_bounds(raw_geom_geojson)
    # print(clean_geom)
    clean_geom_mp: Dict[str, Polygon] = {}
    for kk, vv in clean_geom.items():
        try:
            clean_geom_mp[kk] = MultiPolygon(vv)
        except Exception as e:
            logger.info(f"Skipping {kk} because {e}")
            continue
    
    # Create GeoSeries from the geometry data
    parcel_series = gpd.GeoSeries(clean_geom_mp).set_crs("EPSG:4326", allow_override=True).to_crs("EPSG:3857")
    
    # Filter to only the requested block IDs
    print(parcel_series.head())
    parcel_series = parcel_series.loc[block_ids]
    
    # Load street data and create buffer
    street_buffer = get_street_buffer(parcel_series, buffer_size=street_buffer_size)
    
    return parcel_series, street_buffer


def get_front_facades(block_ids: List[str]) -> gpd.GeoSeries:
    """
    Get front facades (linestrings) for the given block IDs.
    
    Args:
        block_ids: List of block IDs (strings) to get front facades for
        
    Returns:
        GeoSeries mapping block IDs to front facade linestrings in lat/lon (EPSG:4326)
    """
    parcel_series, street_buffer = _setup_data_and_streets(block_ids)
    
    front_facades = {}
    
    for block_id in block_ids:
        try:
            # Get the parcel analysis result
            analysis_result = get_sides_df(parcel_series, block_id, street_buffer=street_buffer)
            
            if analysis_result.front_group_rec is not None:
                # Build the contiguous linestring from the front group
                from cityscaper.autolot.utils import build_contiguous_line_string
                front_facade = build_contiguous_line_string(analysis_result.front_group_rec)
                front_facades[block_id] = front_facade
            else:
                logger.warning(f"Could not determine front facade for block {block_id}")
                front_facades[block_id] = None
                
        except Exception as e:
            logger.error(f"Error processing block {block_id}: {e}")
            front_facades[block_id] = None
    
    # Filter out None values and create GeoSeries
    valid_facades = {k: v for k, v in front_facades.items() if v is not None}
    if valid_facades:
        return gpd.GeoSeries(valid_facades).set_crs("EPSG:3857").to_crs("EPSG:4326")
    else:
        return gpd.GeoSeries(dtype='geometry')


def get_building_footprints(block_ids: List[str]) -> gpd.GeoSeries:
    """
    Get building footprints (polygons) for the given block IDs.
    
    Args:
        block_ids: List of block IDs (strings) to get building footprints for
        
    Returns:
        GeoSeries mapping block IDs to building footprint polygons in lat/lon (EPSG:4326)
    """
    parcel_series, street_buffer = _setup_data_and_streets(block_ids)
    
    building_footprints = {}
    
    for block_id in block_ids:
        try:
            # Get the parcel analysis result
            analysis_result = get_sides_df(parcel_series, block_id, street_buffer=street_buffer)
            
            if analysis_result.foot_print_double_buff is not None:
                building_footprints[block_id] = analysis_result.foot_print_double_buff
            else:
                logger.warning(f"Could not determine building footprint for block {block_id}")
                building_footprints[block_id] = None
                
        except Exception as e:
            logger.error(f"Error processing block {block_id}: {e}")
            building_footprints[block_id] = None
    
    # Filter out None values and create GeoSeries
    valid_footprints = {k: v for k, v in building_footprints.items() if v is not None}
    if valid_footprints:
        return gpd.GeoSeries(valid_footprints).set_crs("EPSG:3857").to_crs("EPSG:4326")
    else:
        return gpd.GeoSeries(dtype='geometry')
