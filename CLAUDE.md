# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Cityscaper is a Python-based tool for generating 3D building visualizations in Blender based on San Francisco zoning and development probability data. The project combines data processing, probabilistic modeling, and 3D visualization to simulate urban development scenarios.

## Development Setup

- Uses Poetry for dependency management
- Requires Python 3.11 (specifically for Blender Python compatibility)
- Install dependencies: `poetry install`
- Install dev dependencies: `poetry install --with dev`

## Key Commands

### Data Processing and Modeling
```bash
# Generate development simulation for a geographic area
python cityscaper/main.py model --output_fname output.csv -- -122.43270 37.76874 -122.43060 37.77047

# Get site data without simulation
python cityscaper/main.py site-data --output_fname sites.csv -- -122.43270 37.76874 -122.43060 37.77047

# Parse GeoJSON RDS files to JSON
python cityscaper/main.py parse-geojson-rds input.RDS output.json

# Build KML from CSV and geometry
python cityscaper/main.py build-kml input.csv output.kml

# Build GeoJSON from CSV and geometry
python cityscaper/main.py build-geojson input.csv output.geojson
```

### Testing and Code Quality
```bash
# Run tests
pytest

# Format code
black .
```

### Jupyter Development
```bash
# Start Jupyter for data exploration
jupyter notebook
```

## Architecture

### Core Modules
- `main.py`: CLI entry point with Click commands for data processing and modeling
- `modeling.py`: Probabilistic development simulation using pdev (probability of development) models
- `geom.py`: Geographic coordinate processing and KML generation  
- `blender_building.py`: Blender integration for 3D building generation
- `blender_cli.py`: Command-line interface for Blender scripting (experimental)
- `utils.py`: Utilities for file handling and data conversion
- `constants.py`: Configuration constants including data paths and rezoning codes

### Data Flow
1. **Input**: RDS files from R containing San Francisco parcel data with zoning scenarios
2. **Processing**: Geographic selection, development probability calculation, yearly simulation
3. **Output**: CSV files with development predictions, KML for visualization, or 3D Blender scenes

### Key Data Files
- `sf_map.RDS`/`sf_map.json`: Complete SF parcel geometry data
- `five_rezonings*.RDS`: Parcel data with multiple zoning scenarios
- `rezoning_*_output.RDS`: Processed scenario-specific development data

## Blender Integration

### Running Blender Scripts
- Execute `blender_building.py` functions directly in Blender's scripting pane
- Use `run_sample_building()` for single building tests
- Use `run_sample_multiple_buildings()` for multi-building integration tests
- Use `run_animated_sample()` for full animation with red-to-textured building transitions
- Use `run_transition_test()` for testing single building material transitions

### Building Animation Features
- **Red Block Transitions**: Buildings appear as solid red blocks and transition to textured materials after 0.5 seconds
- **Animated Materials**: Uses Blender Mix nodes with keyframe animation for smooth color-to-texture transitions
- **Timeline Integration**: Buildings appear based on development year with staggered timing within each year
- **Blender Version Compatibility**: Handles both old (`Color1`/`Color2`/`Fac`) and new (`A`/`B`/`Factor`) Mix node input names

### Blender-OSM Workflow
1. Install Blender-OSM add-on with Google Maps API key
2. Import 3D tiles for geographic area using lat/lon bounding box
3. Access scene coordinates via `bpy.context.scene["lat"]` and `bpy.context.scene["lon"]`
4. Use custom TransverseMercator projection for coordinate conversion

## Rezoning Scenarios

Available scenarios in `REZONING_CODES`:
- `baseline`: Current zoning (business as usual)
- `fall_2023`: Fall 2023 rezoning proposal
- `apr_2025`: April 2025 Family Rezoning proposal  
- `builders_remedy`: Builder's Remedy scenario with density bonuses

## Geographic Coordinate Format

Always use high precision coordinates (6+ significant digits) for 1-foot resolution at SF latitude. Example bounding boxes are provided in README for common SF neighborhoods like Duboce Triangle.