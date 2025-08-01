import os
import csv
import json

def kml_from_latlon(parcel_specs, geom_data)-> str:

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
    for i, row in enumerate(parcel_specs):
        lot = row["mapblklot"]
        try:
            height = float(row["height"])
            parcel_bounds = geom_data[lot]
            for j, polygon in enumerate(parcel_bounds):
                building_name = f"{lot}_{j+1}"
                vertex_strings = []
                for lat, lng in polygon:
                    vertex_strings.append(f"              {lat},{lng},{height*0.3048}")
                coordinate_string="\n".join(vertex_strings)
                building_string = template.format(mapblklot=lot,
                                                  coordinate_string=coordinate_string,
                                                  height=height*0.3048
                                                 )
                buildings.append(building_string)
        except KeyError as e:
            continue

    kml = header + "\n".join(buildings) + footer
    return kml
