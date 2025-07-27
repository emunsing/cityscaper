# Notes

[Blender Python docs](https://docs.blender.org/api/current/)

This utilizes the Blender-OpenStreetMap integration [demonstrated in this Youtube tutorial](https://www.youtube.com/watch?v=JC9IYCF-IAE&ab_channel=CGGeek)

Blender-OSM sets the default axes to the center of the tile.  The location is accessible through `scene = bpy.context.scene; lat0, lon0 = scene["lat"], scene["lon"]`

Data is pulled through R like 
```
setwd("~/src/rezoner")
df <- readRDS("five_rezonings.rds")  # This has the GeoJSON info we need
target_parce = df[df$mapblklot=="0875013",]
coords <- st_coordinates(target_parcel$geometry)
format(coords[,1:2], digits=7, nsmall=8)  # NOTE: You *Must* export with high resolution to avoid skew or inaccurate boundaries
```
**~6 signficant digits must be exported to get 1-foot resolution at 37deg latitude**

The lat/lon are transformed by Blender **via a custom TransverseMercator implementation** not by a standard PythonProjection.  Using the custom implementation is the best way to pull external lat/lon data into Blender.

Material textures require scaling to the appropriate size.

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

  
# Workflow in R

App.R:
- Load heights and modify df 
- compute expected_units_if_dev
- run `predict()` to get `predictions.16` as rezoning pdev and 
- 

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

