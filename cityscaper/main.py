"""
Pre-processing data before Blender
"""
import os
import json
from cityscaper.constants import DATA_DIR, OUTPUT_DIR, EXPORT_FIELDS, REZONING_CODES
from cityscaper.utils import geojson_rds_to_json, geojson_to_parcel_bounds, resolve_path
from cityscaper.modeling import pdev_model
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
    clean_geom = geojson_to_parcel_bounds(geom_json)
    os.makedirs(output_fname, exist_ok=True)
    with open(output_fname, 'w') as outfile:
        json.dump(clean_geom, outfile)
    logger.info(f"GeoJSON data from {input_fname} successfully saved to {output_fname}")


@cli.command()
@click.argument('geom_select', type=float, nargs=4)
@click.option('--simulation_years', default=10, type=int, help='Number of years to simulate development')
@click.option('--random_seed', default=None, type=int, help='Random seed for reproducibility')
@click.option('--pdev_metric', default='pdev_1yr', type=str, help='Metric to use for probability of development')
@click.option('--rezoning_scenario', default='baseline', type=click.Choice(REZONING_CODES.keys()), help='Rezoning scenario to use')
@click.option('--override_csv', default=None, type=click.Path(exists=True, dir_okay=False), help='CSV file with overrides for specific lots')
@click.option('--output_fname', default='rezoning_output.csv', type=click.Path(dir_okay=False), help='Output filename for the development simulation results')
def model(geom_select,
              simulation_years,
              random_seed,
              pdev_metric,
              rezoning_scenario,
              override_csv,
              output_fname):
     """
     Create a CSV of sites which are developed, and the years when they are developed, based on a parcel-by-year simulation.
     NOTE: Because of likely negative latitude values, need to put geom_select at the end of the options and separated by `--` like `$ model <options> -- -122 49 -121.5 49.5`

     Example command line:
        main.py model --output_fname ~/Desktop/rezoning_output.csv -- -122.43270 37.76874 -122.43060 37.77047

     """
     # assert len(geom_string.split(',')) == 4, "geom_string must contain exactly four comma-separated values"
     # geom_select = tuple(map(float, geom_string.split(',')))
     developed_site_data = pdev_model(geom_select, simulation_years, random_seed,
                                      pdev_metric, rezoning_scenario, override_csv)

     resolved_fname = resolve_path(output_fname, default_parent=OUTPUT_DIR)
     developed_site_data[EXPORT_FIELDS].to_csv(resolved_fname)
     logger.info("Development simulation results saved to %s", resolved_fname)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli()