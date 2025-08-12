import click
import fiona
import geopandas as gpd
from typing import Optional
from shapely.geometry import MultiPolygon, Polygon
from tqdm import tqdm
import traceback
from cityscaper.utils import geojson_rds_to_json
from cityscaper.autolot.parcel_analysis import get_sides_df, ParcelAnalysisResult
import pandas as pd
import networkx as nx

import cityscaper.autolot.streets as streets

import logging

logger = logging.getLogger(__name__)


def geojson_to_parcel_bound_polygon(geojson:dict) -> dict:
    return {f['properties']['mapblklot']: (Polygon(el) for el in f['geometry']['coordinates']) for f in geojson['features']}

def raw_json_to_parcel_bound_polygons(geom_data:dict):
    return {k: (Polygon(el) for el in v) for k, v in geom_data.items()}


def get_parcel_bounds_ser(polygon_dict:dict) -> gpd.GeoSeries:
    parcel_bounds_dict = {}
    for kk, vv in polygon_dict.items():
        try:
            parcel_bounds_dict[kk] = MultiPolygon(vv)
        except Exception as e:
            logger.info(f"Skipping construction of GeoSeries entry {kk} on error: {e}")
    parcel_bounds_ser = gpd.GeoSeries(parcel_bounds_dict)
    return parcel_bounds_ser.set_crs("EPSG:4326", allow_override=True).to_crs("EPSG:3857")

def get_sides_df_with_hard_coverage_limit(parcel_bounds_ser: gpd.GeoSeries,
                                          street_buffer: gpd.GeoSeries,
                                          blockid:str,
                                          coverage_target:float =0.75,
                                          max_iters=10,
                                          street_edges:Optional[gpd.GeoDataFrame]=None) -> ParcelAnalysisResult:
    """
    Create a function which uses binary searches to find the appropriate value of `coverage` to yield a footprint which covers the
    parcel's raw area within a tolerance of `coverage_tol`.

    Key steps:
    alpha=0.5
    - Compute parcel_area from parcel_bounds_ser[blockid]
    - initialize alpha = coverage_target
    - initialize coverage_err = 1.0
    - while coverage_err > coverage_tol:
        - Create a draft footprint `get_sides_df(parcel_bounds_ser, blockid, street_buffer=street_buffer, lot_coverage=alpha)`
        - Compute footprint_area
        - coverage_err = coverage_target - (footprint_area / parcel_area)

    """
    current_coverage_ratio = 1.0
    alpha = coverage_target
    update_factor = 0.95
    n_attempts = 0
    while current_coverage_ratio > coverage_target and n_attempts < max_iters:
        n_attempts += 1
        logger.debug(f"Attempt {n_attempts}: Trying coverage ratio {alpha}")
        sides_df = get_sides_df(parcel_bounds_ser, blockid, street_buffer=street_buffer, lot_coverage=alpha, street_edges=street_edges)
        footprint_area = sides_df.foot_print_double_buff.area
        parcel_area = parcel_bounds_ser[blockid].area
        current_coverage_ratio = footprint_area / parcel_area
        alpha *= update_factor
    return sides_df

def get_footprints_with_hard_coverage_limits(parcel_bounds_ser: gpd.GeoSeries, lots_and_coverage_limits: dict[str, float]) -> gpd.GeoSeries:
    street_edges = streets.get_street_edges(parcel_bounds_ser)
    # street_buffer = streets.get_street_buffer(parcel_bounds_ser)

    out_rec = {}
    for blockid, coverage_allowance in tqdm(lots_and_coverage_limits.items()):
        logger.debug(f"Processing {blockid=}")
        try:
            out_rec[blockid] = get_sides_df_with_hard_coverage_limit(parcel_bounds_ser=parcel_bounds_ser,
                                                                     street_buffer=street_buffer,
                                                                     blockid=blockid,
                                                                     coverage_target=coverage_allowance,
                                                                     street_edges=street_edges
                                                                     )
        except Exception as e:
            err_str = traceback.format_exc()
            logger.error(f"{blockid} failed with error: {err_str}")
            continue
        logger.info(f"{blockid} Footprint generation succeeded")

    out_ser = gpd.GeoSeries({kk: vv.foot_print_double_buff for kk, vv in out_rec.items()}).set_crs("EPSG:3857")
    out_ser = out_ser.to_crs("EPSG:4326")
    return out_ser


def get_footprints(parcel_bounds_ser: gpd.GeoSeries, lots: list[str], street_edges=Optional[gpd.GeoDataFrame]=None) -> gpd.GeoSeries:
    street_buffer = streets.get_street_buffer(parcel_bounds_ser)

    out_rec = {}
    for blockid in tqdm(lots):
        logger.debug(f"Processing {blockid=}")
        try:
            out_rec[blockid] = get_sides_df(parcel_bounds_ser, blockid, street_buffer=street_buffer, street_edges=street_edges)
        except Exception as e:
            err_str = traceback.format_exc()
            logger.error(f"{blockid} failed with error: {err_str}")
            continue
        logger.info(f"{blockid} Footprint generation succeeded")

    out_ser = gpd.GeoSeries({kk: vv.foot_print_double_buff for kk, vv in out_rec.items()}).set_crs("EPSG:3857")
    out_ser = out_ser.to_crs("EPSG:4326")
    return out_ser


@click.group()
def cli():
    pass


@cli.command()
@click.argument('sf_map_rds_path', type=click.Path(exists=True, dir_okay=False))
@click.argument('output_file', type=click.Path(dir_okay=False))
@click.argument('lots', type=str, nargs=-1)
def footprint_kml(sf_map_rds_path, output_file, lots):
    """
    Run the autolot analysis on the given shapefile map and lots.

    :param sf_map_rds_path: Path to the RDS file containing the shapefile map.
    :param lots: List of lots to analyze.
    """
    # Read the geometry data from the RDS file

    geoj = geojson_rds_to_json(sf_map_rds_path)
    parcel_bounds_ser = get_parcel_bounds_ser(geoj)  # GeoPandas Series, indexed by mapblklot

    lots = [lot.strip() for lot in lots if lot.strip()]
    if not lots:
        logger.error("No lots provided for analysis.")
        return

    footprints = get_footprints(parcel_bounds_ser, lots)
    footprints.to_file(output_file, driver="KML")

def group_lots_by_geometry(parcel_data: pd.DataFrame, parcel_bounds_ser: gpd.GeoSeries, groupby: str, tolerance_m:float = 1.0, fields_to_sum: list[str] | None = None) -> tuple[pd.DataFrame, gpd.GeoSeries]:
    """
    Group lots by their geometry if their edges are within tolerance_m of each other. Return an updated parcel_data DataFrame and parcel_bounds_ser in which a single merged lot takes the place of the original lots. The merged lot should have the mapblklot of the largest lot in the group.

    :param parcel_data: DataFrame containing lot data.
    :param parcel_bounds_ser: GeoSeries containing parcel geometries.
    :param groupby: Column name to group by.
    :param tolerance_m: Tolerance in meters for grouping lots by geometry.
    :return: Tuple of (updated DataFrame, updated GeoSeries) with grouped lots.
    """
    from shapely.ops import unary_union
    from shapely.geometry import Polygon, MultiPolygon
    import numpy as np

    strict_multipolygon = np.all(parcel_bounds_ser.apply(lambda x: isinstance(x, MultiPolygon)))

    # Ensure we're working with the same coordinate system
    if parcel_bounds_ser.crs != "EPSG:3857":
        parcel_bounds_ser = parcel_bounds_ser.to_crs("EPSG:3857")

    # Group parcels by the specified column
    grouped_parcels = parcel_data.groupby(groupby)
    
    merged_parcels = {}
    merged_geometries = {}
    parcels_to_remove = []
    
    for group_name, group_df in grouped_parcels:
        logger.info(f"Processing group: {group_name} with {len(group_df)} parcels")
        
        # Get the parcels in this group
        group_lots = group_df.index.values.tolist()
        group_geometries = parcel_bounds_ser[group_lots].copy()
        
        if len(group_lots) == 1:
            # Single parcel, no merging needed
            lot_id = group_lots[0]
            merged_parcels[lot_id] = group_df.iloc[0]
            merged_geometries[lot_id] = group_geometries.iloc[0]
            continue
        
        # Find connected components of parcels, which may be singletons
        connected_groups = find_connected_parcels(group_geometries, tolerance_m)

        for component in connected_groups:
            if len(component) == 1:
                # Single parcel in component
                lot_id = component[0]
                merged_parcels[lot_id] = group_df.loc[lot_id]
                merged_geometries[lot_id] = group_geometries[lot_id]
            else:
                # Multiple parcels to merge
                component_geometries = group_geometries[component]
                
                # Merge geometries using unary_union
                merged_geometry = unary_union(component_geometries.values)
                
                # Find the largest parcel in the component to use as the representative
                areas = component_geometries.area
                largest_lot = areas.idxmax()
                subsumed_lots = [lot for lot in component if lot != largest_lot]
                parcels_to_remove.extend(subsumed_lots)
                
                # Update the geometry to the merged one
                merged_parcels[largest_lot] = group_df.loc[largest_lot].copy()
                if fields_to_sum:
                    for field in fields_to_sum:
                        merged_parcels[largest_lot][field] = group_df.loc[component, field].sum()
                if strict_multipolygon and not isinstance(merged_geometry, MultiPolygon):
                    merged_geometry = MultiPolygon([merged_geometry])
                merged_geometries[largest_lot] = merged_geometry
                
                logger.info(f"Merged {len(component)} parcels into {largest_lot}")
    
    assert len(merged_parcels) == len(merged_geometries), "Merged DataFrame and geometries do not match in length"
    assert len(merged_parcels) + len(parcels_to_remove) == len(parcel_data), "Merged parcels and parcels to remove do not match original length"
    assert len(set(parcels_to_remove) & set(merged_geometries.keys())) == 0, "Parcels_to_remove and merged_geometries overlap"

    merged_df = pd.DataFrame.from_dict(merged_parcels, orient='index')
    merged_df.index.name = parcel_data.index.name

    updated_parcel_bounds = parcel_bounds_ser.copy()
    for lot_id, geometry in merged_geometries.items():
        updated_parcel_bounds[lot_id] = geometry
    updated_parcel_bounds = updated_parcel_bounds.drop(parcels_to_remove)
    return merged_df, updated_parcel_bounds


def find_connected_parcels(geometries: gpd.GeoSeries, tolerance_m: float) -> list[list[str]]:
    """
    Find groups of parcels that are connected (share boundaries or are within tolerance).
    
    :param geometries: GeoSeries of parcel geometries
    :param tolerance_m: Tolerance in meters for considering parcels connected
    :return: List of lists, where each inner list contains the mapblklot IDs of connected parcels
    """
    from shapely.geometry import box
    import networkx as nx
    
    # Create a graph to track connections
    G = nx.Graph()
    
    # Add all parcels as nodes
    for lot_id in geometries.index:
        G.add_node(lot_id)
    
    # Check for connections between all pairs of parcels
    lot_ids = list(geometries.index)
    for i, lot1 in enumerate(lot_ids):
        geom1 = geometries[lot1]
        
        for lot2 in lot_ids[i+1:]:
            geom2 = geometries[lot2]
            
            # Check if parcels are connected
            if parcels_are_connected(geom1, geom2, tolerance_m):
                G.add_edge(lot1, lot2)
    
    # Find connected components
    connected_components = list(nx.connected_components(G))
    
    return [list(component) for component in connected_components]


def parcels_are_connected(geom1, geom2, tolerance_m: float) -> bool:
    """
    Check if two parcels are connected (share boundaries or are within tolerance).
    
    :param geom1: First parcel geometry
    :param geom2: Second parcel geometry
    :param tolerance_m: Tolerance in meters
    :return: True if parcels are connected
    """
    # Check if geometries intersect or are within tolerance
    if geom1.intersects(geom2):
        return True
    
    # Check if they're within tolerance distance
    if geom1.distance(geom2) <= tolerance_m:
        return True
    
    # Check if they share boundaries (have common edges)
    if geom1.touches(geom2):
        return True
    
    return False


@cli.command()
@click.argument('input_geom', type=click.Path(exists=True, dir_okay=False))
@click.argument('output_geom', type=click.Path(dir_okay=False))
@click.argument('input_lots', type=click.Path(exists=True, dir_okay=False))
@click.argument('output_lots', type=click.Path(dir_okay=False))
@click.option('--groupby', default='year', help='Column name to group by for merging parcels')
@click.option('--tolerance-m', default=1.0, type=float, help='Tolerance in meters for grouping parcels')
def footprints_for_blender(input_geom, output_geom, input_lots, output_lots, groupby='year', tolerance_m=1.0):
    """
    Read an `input_lots` csv as a dataframe into `lot_data`, and `input_geom` as a geojson .json file.

    If 'groupby' is specified, apply group_lots_by_geometry to merge neighboring parcels.

    Pass the resulting geometries to get_footprints.

    Save the resulting footprints to `output_geom` as a json file, and the lot data to `output_lots` as a CSV file.
    """
    import json
    
    # Read input data
    logger.info(f"Reading lot data from {input_lots}")
    lot_data = pd.read_csv(input_lots)
    
    logger.info(f"Reading geometry data from {input_geom}")
    with open(input_geom, 'r') as f:
        geojson_data = json.load(f)
    
    # Convert to GeoSeries
    parcel_bounds_ser = get_parcel_bounds_ser(geojson_data)
    
    # Apply grouping if specified
    if groupby and groupby in lot_data.columns:
        logger.info(f"Grouping parcels by {groupby} with tolerance {tolerance_m}m")
        lot_data, parcel_bounds_ser = group_lots_by_geometry(
            lot_data, parcel_bounds_ser, groupby, tolerance_m
        )
        logger.info(f"After grouping: {len(lot_data)} parcels remaining")
    
    # Get footprints
    logger.info("Generating footprints")
    lots = lot_data['mapblklot'].tolist()
    footprints = get_footprints(parcel_bounds_ser, lots)
    
    # Save outputs
    logger.info(f"Saving footprints to {output_geom}")
    footprints.to_file(output_geom, driver="GeoJSON")
    
    logger.info(f"Saving lot data to {output_lots}")
    lot_data.to_csv(output_lots, index=False)
    
    logger.info("Footprint generation complete!")
