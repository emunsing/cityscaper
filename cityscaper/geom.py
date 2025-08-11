import os
import csv
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon

def kml_from_latlon(parcel_geom: dict[str, list[list[list[float]]]],
                    parcel_heights: dict[str, float] | None = None
                    )-> str:
    """
    Generate KML from latitude and longitude coordinates of parcels.
    :param parcel_bounds: dictionary of parcel geometries, list[list[lat, lng]]
    :param parcel_heights: optional, in meters
    :return:
    """
    parcel_heights = parcel_heights or {}

    header = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2" 
         xmlns:gx="http://www.google.com/kml/ext/2.2">
      <Document>
    """

    template = """    <Placemark>
          <name>{mapblklot}</name>
          <description>{height}</description>
          <Polygon>
            <extrude>1</extrude>
            <altitudeMode>relativeToGround</altitudeMode>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>
    {coordinate_string}
                </coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
          <Style>
            <PolyStyle>
              <color>cc0000ff</color> <!-- Red with 80% opacity -->
            </PolyStyle>
          </Style>
        </Placemark>"""

    footer="""  </Document>
    </kml>"""

    buildings = []
    for lot, parcel_bounds in parcel_geom.items():
        height = float(parcel_heights.get(lot, 0.0))
        for j, polygon in enumerate(parcel_bounds):
            building_name = f"{lot}_{j+1}"
            vertex_strings = []
            for lat, lng in polygon:
                vertex_strings.append(f"              {lat},{lng},{height}")
            coordinate_string="\n".join(vertex_strings)
            building_string = template.format(mapblklot=lot,
                                              coordinate_string=coordinate_string,
                                              height=height
                                             )
            buildings.append(building_string)
    kml = header + "\n".join(buildings) + footer
    return kml

def kml_from_parcel_table(parcel_table: list[dict[str, float | str]],
                             geom_data: dict[str, list[list[list[float]]]]) -> str:
    """
    Extract latitude and longitude coordinates from a parcel table, and a dictionary of simple geometry data
    :param parcel_table: Desired output parcel information, as dictionaries with keys 'mapblklot' and 'developed_height', i.e. created like csv.dictreader
    :param geom_data: Dictionary mapping 'mapblklot' to list of [lat, lng] coordinates. This may be a much larger set of parcels.
    """

    selected_parcel_geoms = {}
    selected_parcel_heights_meters = {}
    for i, row in enumerate(parcel_table):
        lot = row["mapblklot"]
        try:
            selected_parcel_heights_meters[lot] = float(row.get("developed_height",0.0)) * 0.3048
            selected_parcel_geoms[lot] = geom_data[lot]
        except KeyError as e:
            print("KeyError: ", e)
            continue

    if len([h for h in selected_parcel_heights_meters.values() if h > 0]) == 0:
        selected_parcel_heights_meters = None

    return kml_from_latlon(parcel_geom=selected_parcel_geoms,
                           parcel_heights=selected_parcel_heights_meters)


def gser_to_json_dict(gser: gpd.GeoSeries) -> dict[str, list[list[list[float]]]]:
    parcel_latlons = {}
    for lot, mp in gser.items():
        if isinstance(mp, MultiPolygon):
            if len(mp.geoms) > 1:
                print(f"Multi-polygon parcels are not supported: {lot}")
                continue
            polygon = mp.geoms[0]
        else:
            polygon = mp
        vertex_pairs = []
        for lat, lng in polygon.exterior.coords:
            vertex_pairs.append([lat, lng])
        parcel_latlons[str(lot)] = [vertex_pairs]
    return parcel_latlons


def kml_from_shapely_polygons(parcel_spec_gser: gpd.GeoSeries)-> str:
    parcel_latlons = gser_to_json_dict(parcel_spec_gser)
    return kml_from_latlon(parcel_geom=parcel_latlons)
