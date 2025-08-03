import osmnx as ox
import geopandas as gpd
from shapely.geometry import Polygon

def get_street_edges(parcels:gpd.GeoSeries):
    minx, miny, maxx, maxy = parcels.to_crs(epsg=4326).total_bounds
    bbox = (minx, miny, maxx, maxy)

    # Download the street network within this bounding box
    G = ox.graph_from_bbox(bbox, network_type='drive')
    edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
    edges = edges.to_crs(epsg=3857)
    return edges

def get_street_buffer(parcels:gpd.GeoSeries, buffer_size:float=1.0) -> Polygon:
    # Compute bounding box in correct order: (left, bottom, right, top)
    edges = get_street_edges(parcels)
    # Buffer the streets to catch near misses (small tolerance)
    street_buffer = edges.buffer(buffer_size).union_all() # 1 meter buffer
    return street_buffer
