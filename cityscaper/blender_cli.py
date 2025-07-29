
import sys
import os
import argparse
import json
import csv
from pathlib import Path
from typing import Dict, List, Tuple, Any

script_dir = Path(__file__).parent.parent

# Add to Python path if not already there
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))
    print(f"Added {script_dir} to Python path")
from cityscaper.blender_building import generate_multiple_buildings


def process_parcel_csv(csv_path: str, required_columns: List[str]|None=None) -> List[Dict[str, Any]]:
    """
    Process a CSV file to a list of dictionaries for each row
    """
    required_columns = required_columns or {'mapblklot', 'height'}
    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            
            # Validate required columns
            required_columns = {'mapblklot', 'height'}
            if not required_columns.issubset(set(reader.fieldnames or [])):
                missing = required_columns - set(reader.fieldnames or [])
                raise ValueError(f"Missing required columns: {missing}")
            
            return list(reader)
    except FileNotFoundError:
        raise FileNotFoundError(f"Parcel file not found: {csv_path}")


def generate_buildings_from_files(geometry_file: str,
                       parcels_file: str,
                       building_prefix: str = "Building") -> None:
    """
    Generate buildings from geometry and parcel files.

    This is the main function that processes the input files and generates
    buildings for each parcel in the CSV file.

    Args:
        geometry_file: Path to JSON file with geometry data
        parcels_file: Path to CSV file with parcel data
        building_prefix: Prefix for building object names

    Raises:
        Various exceptions for file I/O, data validation, and building generation errors
    """
    # Load data
    print(f"Loading geometry data from {geometry_file}")
    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    print(f"Loading parcel data from {parcels_file}")
    parcels = process_parcel_csv(parcels_file)

    generate_multiple_buildings(
        geom_data=geom_data,
        parcel_specs=parcels,
        building_prefix=building_prefix
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate buildings for parcels based on input CSV and JSON geometries"
    )
    parser.add_argument(
        "input_geom",
        help="Path to JSON file mapping mapblklot → GeoJSON coordinate arrays",
    )
    parser.add_argument(
        "input_parcels",
        help="Path to CSV file with columns ['mapblklot','height']",
    )
    parser.add_argument(
        "--building-prefix",
        default="Building",
        help="Prefix for building object names (default: Building)"
    )
    
    args = parser.parse_args()
    
    try:
        generate_buildings_from_files(
            args.input_geom,
            args.input_parcels,
            args.building_prefix
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main() 