"""
Pre-processing data before Blender
"""
import os
import shutil
import csv
import json
from cityscaper.constants import DATA_DIR, OUTPUT_DIR, EXPORT_FIELDS, REZONING_CODES
from cityscaper.utils import geojson_rds_to_json, geojson_to_parcel_bound_latlon, resolve_path
from cityscaper.modeling import pdev_model, get_site_data
from cityscaper.geom import kml_from_parcel_table, gser_to_json_dict, kml_from_latlon
from cityscaper.autolot.autolot import group_lots_by_geometry, geojson_to_parcel_bound_polygon, get_parcel_bounds_ser, get_footprints
from cityscaper.arkit import kmz_from_list
from shapely.geometry import Polygon
import click
import logging

logger = logging.getLogger(__name__)


@click.group()
def cli():
    pass


@cli.command()
@click.argument('input_fname', type=click.Path(exists=True, dir_okay=False))
@click.argument('output_fname', type=click.Path(dir_okay=False))
def parse_geojson_rds(input_fname: os.PathLike, output_fname: os.PathLike):
    input_fname = resolve_path(input_fname, default_parent=DATA_DIR)
    output_fname = resolve_path(output_fname, default_parent=OUTPUT_DIR)
    geom_json = geojson_rds_to_json(input_fname)
    clean_geom = geojson_to_parcel_bound_latlon(geom_json)
    os.makedirs(output_fname.parent, exist_ok=True)
    with open(output_fname, 'w') as outfile:
        json.dump(clean_geom, outfile)
    logger.info(f"GeoJSON data from {input_fname} successfully saved to {output_fname}")

@cli.command()
@click.argument('csv_path', type=click.Path(exists=True, dir_okay=False))
@click.argument('output_fname', type=click.Path(dir_okay=False))
@click.option ('--geometry_file', type=click.Path(exists=True, dir_okay=False), default=DATA_DIR / 'sf_map_unfiltered.json',)
def build_kml(
        csv_path,
        output_fname,
        geometry_file,
):
    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    with open(csv_path, newline="") as f:
        parcel_specs = list(csv.DictReader(f))

    kml = kml_from_parcel_table(parcel_specs=parcel_specs,
                                geom_data=geom_data,)

    resolved_fname = resolve_path(output_fname, default_parent=OUTPUT_DIR)
    with open(resolved_fname, 'w') as kml_file:
        kml_file.write(kml)


@cli.command()
@click.argument('geom_select', type=float, nargs=4)
@click.option('--random_seed', default=None, type=int, help='Random seed for reproducibility')
@click.option('--rezoning_scenario', default='baseline', type=click.Choice(REZONING_CODES.keys()), help='Rezoning scenario to use')
@click.option('--override_csv', default=None, type=click.Path(exists=True, dir_okay=False), help='CSV file with overrides for specific lots')
@click.option('--output_fname', default='rezoning_output.csv', type=click.Path(dir_okay=False), help='Output filename for the development simulation results')
@click.option('--all-fields', is_flag=True, help='Export only the fields specified in EXPORT_FIELDS')
def site_data(geom_select,
              random_seed,
              rezoning_scenario,
              override_csv,
              output_fname,
              all_fields):
    development_candidates = get_site_data(
        geom_select=geom_select,
        rezoning_scenario=rezoning_scenario,
        override_csv=override_csv,
        random_seed=random_seed,
    )
    resolved_fname = resolve_path(output_fname, default_parent=OUTPUT_DIR)

    if not all_fields:
        development_candidates = development_candidates[EXPORT_FIELDS]
    development_candidates = development_candidates.sort_values(by='mapblklot')

    if '.csv' in output_fname:
        development_candidates.to_csv(resolved_fname, index=True, index_label='mapblklot')

    if '.pqt' in output_fname or '.parquet' in output_fname:
        development_candidates.to_parquet(resolved_fname, index=True, index_label='mapblklot')



@cli.command()
@click.argument('geom_select', type=float, nargs=4)
@click.option('--simulation_years', default=10, type=int, help='Number of years to simulate development')
@click.option('--random_seed', default=None, type=int, help='Random seed for reproducibility')
@click.option('--pdev_metric', default='pdev_1yr', type=str, help='Metric to use for probability of development')
@click.option('--pdev_multiplier', default=1.0, type=float, help='Multiplier to correct BlueSky model to actual city probability/yield')
@click.option('--rezoning_scenario', default='baseline', type=click.Choice(REZONING_CODES.keys()), help='Rezoning scenario to use')
@click.option('--override_csv', default=None, type=click.Path(exists=True, dir_okay=False), help='CSV file with overrides for specific lots')
@click.option('--exclude_csv', default=None, type=click.Path(exists=True, dir_okay=False), help='CSV file with lots to exclude in "mapblklot" column')
@click.option('--output_fname', default='rezoning_output.csv', type=click.Path(dir_okay=False), help='Output filename for the development simulation results')
def model(geom_select,
          simulation_years,
          random_seed,
          pdev_metric,
          pdev_multiplier,
          rezoning_scenario,
          override_csv,
          exclude_csv,
          output_fname):
     """
     Create a CSV of sites which are developed, and the years when they are developed, based on a parcel-by-year simulation.
     NOTE: Because of likely negative latitude values, need to put geom_select at the end of the options and separated by `--` like `$ model <options> -- -122 49 -121.5 49.5`

     Example command line:
        main.py model --output_fname ~/Desktop/rezoning_output.csv -- -122.43270 37.76874 -122.43060 37.77047

     """
     # assert len(geom_string.split(',')) == 4, "geom_string must contain exactly four comma-separated values"
     # geom_select = tuple(map(float, geom_string.split(',')))
     developed_site_data = pdev_model(geom_select=geom_select,
                                      simulation_years=simulation_years,
                                      random_seed=random_seed,
                                      pdev_metric=pdev_metric,
                                      pdev_correction_factor=pdev_multiplier,
                                      rezoning_scenario=rezoning_scenario,
                                      override_csv=override_csv,
                                      exclude_csv=exclude_csv,)


     resolved_fname = resolve_path(output_fname, default_parent=OUTPUT_DIR)
     developed_site_data[EXPORT_FIELDS + ['development_study_year']].sort_values(by='development_study_year').to_csv(resolved_fname, index=True, index_label='mapblklot')
     logger.info("Development simulation results saved to %s", resolved_fname)


@cli.command()
@click.argument('geom_select', type=float, nargs=4)
@click.option('--simulation_years', default=10, type=int, help='Number of years to simulate development')
@click.option('--random_seed', default=None, type=int, help='Random seed for reproducibility')
@click.option('--geometry_file', type=click.Path(exists=True, dir_okay=False), default=os.path.expanduser("~/src/cityscaper/data/sf_map_unfiltered.json"))
@click.option('--pdev_metric', default='pdev_1yr', type=str, help='Metric to use for probability of development')
@click.option('--pdev_multiplier', default=1.0, type=float, help='Multiplier to correct BlueSky model to actual city probability/yield')
@click.option('--rezoning_scenario', default='baseline', type=click.Choice(REZONING_CODES.keys()), help='Rezoning scenario to use')
@click.option('--override_csv', default=None, type=click.Path(exists=True, dir_okay=False), help='CSV file with overrides for specific lots')
@click.option('--exclude_csv', default=None, type=click.Path(exists=True, dir_okay=False), help='CSV file with lots to exclude in "mapblklot" column')
@click.option('--export_dir', type=click.Path(), default=os.path.expanduser("~/Desktop/arkit_buildings"), help='Directory to export KMZ file')
@click.option('--overwrite', is_flag=True, help='Remove all existing files in export directory')
@click.option('--raise_err', is_flag=True, help='Raise error on failure to generate a building')
@click.option('--lot_bound_kml_path', type=click.Path(dir_okay=False), default=None, help='Output KML file for additional visualization')
@click.option('--building_prefix', default='building', help='Prefix for building names')
def full_pipe(geom_select,
          simulation_years,
          random_seed,
          pdev_metric,
          pdev_multiplier,
          rezoning_scenario,
          override_csv,
          exclude_csv,
            geometry_file,
          export_dir,
              raise_err,
              lot_bound_kml_path,
              building_prefix,
              overwrite):


    developed_site_data = pdev_model(geom_select=geom_select,
                                     simulation_years=simulation_years,
                                     random_seed=random_seed,
                                     pdev_metric=pdev_metric,
                                     pdev_correction_factor=pdev_multiplier,
                                     rezoning_scenario=rezoning_scenario,
                                     override_csv=override_csv,
                                     exclude_csv=exclude_csv, )

    logger.info("Done with PDev simulation")

    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    geom_data_polygons = {k: (Polygon(el) for el in v) for k, v in geom_data.items()}
    parcel_bounds_gser = get_parcel_bounds_ser(geom_data_polygons)
    developed_sites_without_geometry = developed_site_data.index.difference(parcel_bounds_gser.index)
    if len(developed_sites_without_geometry) > 0:
        logger.warning(f"Some developed sites do not have geometry: {', '.join(developed_sites_without_geometry)}")
        developed_site_data = developed_site_data.drop(developed_sites_without_geometry)

    logger.info("Done with Geometry formatting")

    additive_fields = ['expected_units', 'expected_units_if_dev', 'expected_units_baseline','expected_units_skyscraper', 'expected_built_envelope', 'ACRES', 'expected_units_skyscraper_if_dev', 'ground_floor', ]

    merged_site_data, merged_parcel_gser = group_lots_by_geometry(parcel_data=developed_site_data,
                                                                  parcel_bounds_ser=parcel_bounds_gser,
                                                                  groupby="development_study_year",
                                                                  tolerance_m=1.0,
                                                                  fields_to_sum=additive_fields,
                                                                  )

    logger.info("Done merging lots")
    # TODO: Refactor to get rid of record-list approach, forced by Blender's limited python support
    parcel_specs = merged_site_data.reset_index().to_dict(orient='records')

    if os.path.exists(export_dir) and overwrite:
        shutil.rmtree(export_dir)
    os.makedirs(export_dir, exist_ok=True)
    merged_site_data.to_csv(os.path.join(export_dir, 'site_data.csv'), index=True, index_label='mapblklot')

    footprints = get_footprints(parcel_bounds_ser=merged_parcel_gser,
                                lots=merged_site_data.index,
                                )
    logger.info("Done generating lot footprints")
    geom_data_dict = gser_to_json_dict(footprints)

    if lot_bound_kml_path:
        lot_bound_kml_path = resolve_path(lot_bound_kml_path, default_parent=OUTPUT_DIR)
        kml_data = kml_from_parcel_table(parcel_table=parcel_specs,
                                         geom_data=geom_data_dict)
        with open(lot_bound_kml_path, 'w') as kml_file:
            kml_file.write(kml_data)

    kmz_from_list(
        parcel_specs=parcel_specs,
        geom_data=geom_data,
        building_prefix=building_prefix,
        export_dir=export_dir,
        raise_err=raise_err,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli()