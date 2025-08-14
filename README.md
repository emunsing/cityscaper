# Notes

## Entry points:

Python data processing:
- main.py: 
  - Parse sf_map.RDS file to parcel lat/lon dict, like `$ python main.py model --output_fname ~/Desktop/rezoning_output.csv -- -122.43270 37.76874 -122.43060 37.77047` 
  - Run pdev simulation for a geometry, like `$ python main.py model --output_fname ~/Desktop/rezoning_output.csv -- -122.43270 37.76874 -122.43060 37.77047`
  - Create kml of the raw geometry, like `$ python main.py build-kml ~/Desktop/rezoning_frontier.csv ~/frontier_redevelopment.kml`

Creating USDZ files for Apple ARKit:
  - Create simple DAE files and convert them to USDZ files for use with Apple ARKit: `$ python arkit.py build-dae-from-csv ~/Desktop/rezoning_frontier.csv  --raise_err  --apply_materials`
  - Convert DAE files to USDZ files: `$ python arkit.py dae-to-usd --input-dir ~/Desktop//buildings2 --export-dir ~/Desktop/buildings2_out --export-format "building_{fname}_1.usdz"`

Blender scripting:
- blender_building.py:  Runs from within Blender in the scripting pane:
   - run_sample_building: single-building integration test
   - run_sample_multiple_buildings: Multi-building integration test
- blender_cli.py: NOT TESTED
   - Intended for combined blender+python command line scripting, like `$ blender --background --python blender_cli.py -- --input_geom <path/to/geometry.json> --input_parcels <path/to/developed_parcel_height.csv>`

Blender animation:

## Blender Python Scripting

### Blender Python scripting
- [Blender Python docs](https://docs.blender.org/api/current/)
- Runs with Blender's bundled Python, *not* your environment.  To install packages,
  - `/path/to/blender/4.0/python/bin/python3.10 -m ensurepip`
  - `/path/to/blender/4.0/python/bin/python3.10 -m pip install pandas`

Data we need as a starting point:
- Lat/lon coordinates for lot
- Lot coverage
- expected height
- Year built

From that information, we then derive:
- The "front" of the building: identify based on longest street-facing side. If multiple sides (i.e. rear alley), use the side facing the widest street.
- Building footprint: should be a function of lot coverage and size
- building form: 3-dimensional shape and facade elements, step backs, patios based on objective design standards
- Building textures: Walls and other elements

### Blender-OSM specifics
This utilizes the Blender-OpenStreetMap integration [demonstrated in this Youtube tutorial](https://www.youtube.com/watch?v=JC9IYCF-IAE&ab_channel=CGGeek)

Workflow:
- Install Blender-OSM add-on; set up GMaps API key and download folder in add-on settings 
- "N" from layout view to bring up Properties tabs, including Blosm tab
- Select lat/lon bounding box or paste
- Select "3D Tiles" under import selector, with "Source: Google" and desired level of detail
- Click "Import" and wait for import to complete


Blender-OSM sets the default axes to the center of the tile.  The location is accessible through `scene = bpy.context.scene; lat0, lon0 = scene["lat"], scene["lon"]`

The lat/lon are transformed by Blender OSM **via a custom TransverseMercator implementation** not by a standard PythonProjection.  Using the custom implementation is the best way to pull external lat/lon data into Blender.

Material textures require scaling to the appropriate size.

## Data from R 

Key data we care about:
- ACRES - lot size
- mapblklot
- geometry (geojson)
- ENVELOPE_1000 : allowable floor space in square feet
- ex_height2024: no-change heights
- pdev_baseline_1yr: no-change development probability
- pdev_skyscraper_1yr: Development probability if 245-ft heights were allowed everywhere
- M4_ZONING - Fall 2023 rezoning
- M5_ZONING - Feb 2024 rezoning
- M6_ZONING - April 2025 Family Rezoning
- M6_height - April 2025 Family Rezoning height limit
- ZONING - selected zoning for a chosen scenario, used by app.R
- height: final height for a chosen scenario, used by app.R
- lot_coverage_discount: portion of lot covered
- ground_floor: square feet of ground floor space

There are two core means of storing data:
1. Tabular data with scalar or string values, by mapblocklot and rezoning:
  - This is generally passed as `df` and reference version is stored in "five_rezonings_nongeo.RDS" and then manipulated in `app.R`
  - Because of different computation paths, if a blocklot is handled differently for different rezonings we may have multiple rows for a single mapblocklot. Need to filter for non-null rezoning info.
1. Geojson data, which is stored in a `geometry` column in "five_rezonings.rds" but stripped out in preprocessing.R and stored in `sf_map.RDS` as a JSON

Data can be pulled through R like the below, for raw data without zoning-specific `pdev` values:
```
setwd("~/src/rezoner")
df <- readRDS("five_rezonings.rds")  # This has the GeoJSON info we need
target_parcel = df[df$mapblklot=="0875013",]
coords <- st_coordinates(target_parcel$geometry)
format(coords[,1:2], digits=7, nsmall=8)  # NOTE: You *Must* export with high resolution to avoid skew or inaccurate boundaries
```
**~6 significant digits must be exported to get 1-foot resolution at 37deg latitude**

Data can also be exported from App.R with all the scenario-specific values, by putting a save_rds command at the end of `update_df_()` i.e. [around line 380 in commit e7caaae here](https://github.com/sdamerdji/rezoner/blob/5d5f3bf0dffe7dc0dd00e95436605740895072f5/rezoner/app.R#L378C3-L380C3). **This approach is used to create the `rezoning_<scenario>_output.RDS` files used by the cityscaper repo**, by placing `saveRDS(df, file.path(paste('/Users/eric/Desktop/rezoning',scenario,'output.RDS', sep = '_')))` in line 380. 


### Rezonings:
- current/baseline: "business as usual" -> ex_height2024 for heights,
- Fall 2023 - "D" - M4_ZONING
- Feb 2024 - "E" - M5_ZONING
- April 2025 Family Rezoning - "F" - M6_ZONING
  - df[!is.na(df$M6_ZONING) & (is.na(df$M6_height) | df$M6_height < 65) & (df$is_corner | df$ACRES > (8000 / 43560)), 'M6_ZONING'] <- "65' Height Allowed"
- "skyscraper" - scenario where 245-ft height limits are used everywhere
  - expected_units_skyscraper_if_dev is based on a uniform 245-ft height limit 
  - pdev_skyscraper_1yr comes from predicting development based on expected_units_skyscraper_if_dev with 245-ft heights

### Builder's Remedy
- stack_sdbl = True
- sdbl <- 1 + .4 * .6
- df$expected_units_if_dev <- pmin(df$expected_units_if_dev, df$builders_remedy_du_acre * df$ACRES, na.rm=T)
      df <- df %>% mutate(
        Envelope_1000 = if_else(expected_units_if_dev > 5, Envelope_1000 * sdbl, Envelope_1000),
        Upzone_Ratio = if_else(existing_sqft > 0, Envelope_1000 / existing_sqft, 0),
        expected_units_if_dev = if_else(expected_units_if_dev > 5, expected_units_if_dev * sdbl, expected_units_if_dev)
      )

### Relevant files:

'five_rezonings_processed.RDS'
- ACRES
- mapblklot
- geometry (geojson)
- ENVELOPE_1000 : allowable floor space in square feet
- pdev_baseline_1yr: no-change development probability
- ex_height2024: no-change heights
- expected_units_baseline_if_dev: no-change development units

preprocessing.R:
- ACRES * 43560 : square feet of base lot
- ground_floor = (ACRES * 43560) * lot_coverage_discount
- building_efficiency_discount <- .8 : global assumption for the file
- n_floors_residential
- expected_built_envelope: total square feet expected. Note that for large-lot or >8 stories this is 


- Identify blocks you want to include
- Get the current proposed zoning (incl corner lot bonuses)
- Get Pdev

# Reference data
TODO: turn this into enums / yaml

Google Maps squares from Blosm selector
- Duboce Park: 
  - GMaps selector: `-122.43270,37.76874,-122.43060,37.77047`
  - assessor blocks: 
- Duboce Triangle along Market: 
  - GMaps selector: `-122.43765,37.76040,-122.42448,37.77096`
  - assessor blocks: `["3539", "3538", "3538", "3537", "3537", "3536", "3536", "0874", "0875", "0866", "0865", "0864", "0863", "0867", "0867", "0868", "0868", "0869", "1260", "1260", "3540", "3540", "3541", "3541", "3561", "3560", "3561", "3562", "3542", "2611", "2612", "2613", "2614", "2622", "2623", "2648", "2647", "3582", "3563", "3564", "3559", "3558", "3543", "3544", "3535", "3534", "3534", "3501", "0872", "0873" ]`
- Geary between 2nd and 5th (actually California to Balboa, Arguello to 9th):
  - Gmaps selector: `-122.46824,37.77676,-122.45776,37.78519`
- Eureka Valley:
  - Gmaps selector: `-122.44248,37.75446,-122.42174,37.77131`
  - Centered at 
- Marina / Cow hollow:
  - Gmaps selector: `-122.45102,37.79131,-122.40198,37.81284`
  - Centered at
- Frontier Tower
  - Gmaps selector: `-122.42006,37.77483,-122.41333,37.77926`
  - Centered at -122.416695,37.777045
# Questions for Salim