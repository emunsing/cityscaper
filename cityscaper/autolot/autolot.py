import click
import fiona
import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon
from tqdm import tqdm
import traceback
from cityscaper.utils import geojson_rds_to_json
from cityscaper.autolot.parcel_analysis import get_sides_df, ParcelAnalysisResult
import pandas as pd

import cityscaper.autolot.streets as streets

import logging

logger = logging.getLogger(__name__)



def geojson_to_parcel_bound_polygon(geojson:dict) -> dict:
    return {f['properties']['mapblklot']: (Polygon(el) for el in f['geometry']['coordinates']) for f in geojson['features']}


def get_parcel_bounds_ser(geoj:dict) -> gpd.GeoSeries:
    parcel_bounds_raw = geojson_to_parcel_bound_polygon(geoj)
    parcel_bounds_dict = {}
    for kk, vv in parcel_bounds_raw.items():
        try:
            parcel_bounds_dict[kk] = MultiPolygon(vv)
        except Exception as e:
            print(kk, e)
    parcel_bounds_ser = gpd.GeoSeries(parcel_bounds_dict)
    return parcel_bounds_ser.set_crs("EPSG:4326", allow_override=True).to_crs("EPSG:3857")

def get_sides_with_coverage(parcel_bounds_ser: gpd.GeoSeries, street_buffer: gpd.GeoSeries, blockid:str,
                            coverage_target:float =0.75, coverage_tol:float =0.05) -> ParcelAnalysisResult:
    """
    Create a function which uses binary searches to find the appropriate value of `coverage` to yield a footprint which covers the
    parcel's raw area within a tolerance of `coverage_tol`.

    Key steps:
    - Compute parcel_area from parcel_bounds_ser[blockid]
    - initialize alpha = coverage_target
    - initialize coverage_err = 1.0
    - while coverage_err > coverage_tol:
        - Create a draft footprint `get_sides_df(parcel_bounds_ser, blockid, street_buffer=street_buffer, lot_coverage=alpha)`
        - Compute footprint_area
        - coverage_err = coverage_target - (footprint_area / parcel_area)
        - if coverage_err < 0,  decrease alpha.  if coverage_err > 0, increase alpha. This can be done in a binary search manner.
    """
    pass



def get_footprints(parcel_bounds_ser: gpd.GeoSeries, lots: list[str]) -> gpd.GeoSeries:
    street_buffer = streets.get_street_buffer(parcel_bounds_ser)

    out_rec = {}
    for blockid in tqdm(lots):
        logger.debug(f"Processing {blockid=}")
        try:
            out_rec[blockid] = get_sides_df(parcel_bounds_ser, blockid, street_buffer=street_buffer)
        except Exception as e:
            err_str = traceback.format_exc()
            logger.error(f"{blockid} failed with error: {err_str}")
            continue
        logger.success(f"{blockid=} succeeded")

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

def group_lots_by_geometry(parcel_data: pd.DataFrame, parcel_bounds_ser: gpd.GeoSeries, groupby: str, tolerance_m:float = 1.0) -> tuple[pd.DataFrame, gpd.GeoSeries]:
    """
    Group lots by their geometry if their edges are within tolerance_m of each other, and return a DataFrame with the grouped lots.

    :param parcel_data: DataFrame containing lot data.
    :param parcel_bounds_ser: GeoSeries containing parcel geometries.
    :param groupby: Column name to group by.
    :param tolerance_m: Tolerance in meters for grouping lots by geometry.
    :return: DataFrame with grouped lots.
    """


@cli.command()
def footprints_for_blender(input_geom, output_geom, input_lots, output_lots, groupby='year'):
    """
    Read an `input_lots` csv as a dataframe into `lot_data`, and `input_geom` as a geojson .json file.

    if 'groupby' is specified, apply group_lots_by_geometry

    Pass the resulting geometries to get_footprints

    Save the resulting footprints to `output_geom` as a json file, and the lot data to `output_lots` as a CSV file.
    """
