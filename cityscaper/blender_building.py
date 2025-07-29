"""
Blender building generation module.

This module provides functions to generate 3D buildings in Blender based on
parcel coordinates and height specifications.
"""
import os
import csv
import sys
import bpy
import bmesh
import json
import math
import mathutils
from typing import List, Tuple, Optional, Dict, Any


class TransverseMercator:
    """
    Transverse Mercator projection for converting geographic coordinates to Blender units.
    
    This class handles the conversion between latitude/longitude coordinates
    and Blender's coordinate system for accurate building placement.
    """
    
    radius = 6378137.

    def __init__(self, **kwargs):
        """Initialize the projection with center coordinates and scale factor."""
        # Default values
        self.lat = 0.  # in degrees
        self.lon = 0.  # in degrees
        self.k = 1.  # scale factor

        for attr in kwargs:
            setattr(self, attr, kwargs[attr])
        self.latInRadians = math.radians(self.lat)

    def fromGeographic(self, lat: float, lon: float) -> Tuple[float, float, float]:
        """
        Convert geographic coordinates to Blender units.
        
        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            
        Returns:
            Tuple of (x, y, z) coordinates in Blender units
        """
        lat = math.radians(lat)
        lon = math.radians(lon - self.lon)
        B = math.sin(lon) * math.cos(lat)
        x = 0.5 * self.k * self.radius * math.log((1. + B) / (1. - B))
        y = self.k * self.radius * (math.atan(math.tan(lat) / math.cos(lon)) - self.latInRadians)
        return (x, y, 0.)

    def toGeographic(self, x: float, y: float) -> Tuple[float, float]:
        """
        Convert Blender units back to geographic coordinates.
        
        Args:
            x: X coordinate in Blender units
            y: Y coordinate in Blender units
            
        Returns:
            Tuple of (lat, lon) in degrees
        """
        x = x / (self.k * self.radius)
        y = y / (self.k * self.radius)
        D = y + self.latInRadians
        lon = math.atan(math.sinh(x) / math.cos(D))
        lat = math.asin(math.sin(D) / math.cosh(x))

        lon = self.lon + math.degrees(lon)
        lat = math.degrees(lat)
        return (lat, lon)


def dist_pt_seg_2d(p: mathutils.Vector, a: mathutils.Vector, b: mathutils.Vector) -> float:
    """
    Calculate the distance from a point to a line segment in 2D.
    
    Args:
        p: Point to measure distance from
        a: Start point of line segment
        b: End point of line segment
        
    Returns:
        Distance from point to line segment
    """
    vx, vy = b.x - a.x, b.y - a.y
    wx, wy = p.x - a.x, p.y - a.y
    denom = vx * vx + vy * vy
    if denom == 0:
        return math.hypot(wx, wy)
    t = max(0, min(1, (wx * vx + wy * vy) / denom))
    qx, qy = a.x + vx * t, a.y + vy * t
    return math.hypot(p.x - qx, p.y - qy)


def make_uv_mat(name: str, img_path: str) -> bpy.types.Material:
    """
    Create a material with UV texture mapping.
    
    Args:
        name: Name for the material
        img_path: Path to the texture image file
        
    Returns:
        Blender material with UV texture mapping
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    links = nt.links

    texco = nt.nodes.new("ShaderNodeTexCoord")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(bpy.path.abspath(f"//{img_path}"))
    tex.extension = 'REPEAT'
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")

    links.new(texco.outputs["UV"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def get_ground_elevation(parcel_xy: List[Tuple[float, float]], 
                        tile_object_name: str = "Google 3D Tiles",
                        search_radius: float = 3.0) -> float:
    """
    Find the ground elevation for a parcel by sampling nearby tile vertices.
    
    Args:
        parcel_xy: List of (x, y) coordinates defining the parcel boundary
        tile_object_name: Name of the tile mesh object in Blender
        search_radius: Maximum distance to search for ground vertices (in meters)
        
    Returns:
        Ground elevation (Z coordinate) in Blender units
        
    Raises:
        RuntimeError: If no ground vertices found within search radius
    """
    # Build 2D boundary segments
    edges = []
    for i in range(len(parcel_xy)):
        a = mathutils.Vector(parcel_xy[i])
        b = mathutils.Vector(parcel_xy[(i + 1) % len(parcel_xy)])
        edges.append((a, b))

    tile = bpy.data.objects[tile_object_name]
    M = tile.matrix_world
    min_z = float('inf')
    
    for v in tile.data.vertices:
        w = M @ v.co
        p2 = mathutils.Vector((w.x, w.y))
        d = min(dist_pt_seg_2d(p2, a, b) for a, b in edges)
        if d <= search_radius:
            min_z = min(min_z, w.z)

    if min_z == float('inf'):
        raise RuntimeError(f"No ground vertices found within {search_radius}m of parcel boundary")
    
    return min_z


def create_building_mesh(parcel_xy: List[Tuple[float, float]], 
                        height_meters: float,
                        ground_z: float,
                        building_name: str = "Building") -> bpy.types.Object:
    """
    Create a building mesh by extruding the parcel footprint.
    
    Args:
        parcel_xy: List of (x, y) coordinates defining the parcel boundary
        height_meters: Building height in meters
        ground_z: Ground elevation (Z coordinate)
        building_name: Name for the building object
        
    Returns:
        Blender object containing the building mesh
    """
    mesh = bpy.data.meshes.new(f"{building_name}Mesh")
    obj = bpy.data.objects.new(building_name, mesh)
    bpy.context.collection.objects.link(obj)

    bm = bmesh.new()
    verts = [bm.verts.new((x, y, ground_z)) for x, y in parcel_xy]
    face = bm.faces.new(verts)
    bm.faces.ensure_lookup_table()
    bm.normal_update()

    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    bm.verts.ensure_lookup_table()
    for e in res["geom"]:
        if isinstance(e, bmesh.types.BMVert):
            e.co.z += height_meters

    bm.to_mesh(mesh)
    bm.free()
    
    return obj


def apply_materials_and_uvs(obj: bpy.types.Object,
                           wall_texture_path: str = "wall_24_38m_x24_85.jpeg",
                           roof_texture_path: str = "tiles_066m_1m.jpg") -> None:
    """
    Apply materials and UV mapping to a building object.
    
    Args:
        obj: Building object to apply materials to
        wall_texture_path: Path to wall texture image
        roof_texture_path: Path to roof texture image
    """
    # Create materials
    wall_mat = make_uv_mat("WallMaterial", wall_texture_path)
    roof_mat = make_uv_mat("RoofMaterial", roof_texture_path)

    obj.data.materials.clear()
    obj.data.materials.append(wall_mat)  # slot 0
    obj.data.materials.append(roof_mat)  # slot 1

    # Calculate texture repeats based on building dimensions
    bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    xs = [v.x for v in bb]
    ys = [v.y for v in bb]
    zs = [v.z for v in bb]
    width_m = max(xs) - min(xs)
    depth_m = max(ys) - min(ys)
    height_m = max(zs) - min(zs)

    wall_u = width_m / 24.85
    wall_v = height_m / 24.38
    roof_u = width_m / 0.66
    roof_v = depth_m / 1.0

    # Create UV layer if needed
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")

    # Apply cube projection
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=1.0, correct_aspect=True, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode='OBJECT')

    # Scale UV islands based on material
    uv_data = obj.data.uv_layers.active.data
    wall_ids = {p.index for p in obj.data.polygons
                if abs((p.normal @ obj.matrix_world.to_3x3()).z) < 0.2}
    roof_ids = {p.index for p in obj.data.polygons
                if abs((p.normal @ obj.matrix_world.to_3x3()).z) > 0.9}

    def scale_islands(face_ids, u_repeat, v_repeat):
        for poly in obj.data.polygons:
            if poly.index in face_ids:
                for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    uv = uv_data[li].uv
                    uv.x *= u_repeat
                    uv.y *= v_repeat

    scale_islands(wall_ids, wall_u, wall_v)
    scale_islands(roof_ids, roof_u, roof_v)

    # Assign materials based on face normals
    for p in obj.data.polygons:
        wn = (p.normal @ obj.matrix_world.to_3x3()).normalized()
        p.material_index = 1 if abs(wn.z) > 0.9 else 0

    obj.data.update()


def generate_building(parcel_coords: List[List[float]],
                     height_feet: float,
                     building_name: str = "Building",
                     scene_lat: Optional[float] = None,
                     scene_lon: Optional[float] = None) -> bpy.types.Object:
    """
    Generate a complete building in Blender from parcel coordinates and height.
    
    This is the main function for creating buildings. It handles coordinate
    projection, ground elevation sampling, mesh creation, and material application.
    
    Args:
        parcel_coords: List of (lat, lon) tuples defining parcel boundary
        height_feet: Building height in feet
        building_name: Name for the building object
        scene_lat: Scene center latitude (uses scene data if None)
        scene_lon: Scene center longitude (uses scene data if None)
        
    Returns:
        Blender object containing the generated building
        
    Raises:
        RuntimeError: If ground elevation cannot be determined
    """
    # Get scene projection parameters
    scene = bpy.context.scene
    if scene_lat is None:
        scene_lat = scene["lat"]
    if scene_lon is None:
        scene_lon = scene["lon"]
    
    # Set up projection
    proj = TransverseMercator(lat=scene_lat, lon=scene_lon, k=1.0)
    
    # Project coordinates to Blender units
    parcel_xy = [proj.fromGeographic(lat=lat, lon=lon)[:2] for lon, lat in parcel_coords]
    
    # Get ground elevation
    ground_z = get_ground_elevation(parcel_xy)
    
    # Convert height to meters
    height_meters = height_feet * 0.3048
    
    # Create building mesh
    obj = create_building_mesh(parcel_xy, height_meters, ground_z, building_name)
    
    # Apply materials and UVs
    apply_materials_and_uvs(obj)
    
    return obj 


def generate_multiple_buildings(geom_data: dict[str, List[List[List[float]]]],
                                parcel_specs: list[dict[str, Any]],
                                building_prefix: str = "Building",
                                raise_err=True) -> None:
    """
    Args:
        geom_data: dictionary of geometry keyed by mapblklot
        parcel_specs: list of parcel spec dictionaries; must contain 'mapblklot' and 'height'
        building_prefix: Prefix for building object names
    """
    successful_buildings, total_parcels = 0, len(parcel_specs)

    for i, row in enumerate(parcel_specs):
        lot = row["mapblklot"]
        print(f"Processing parcel {i+1}/{total_parcels}: {lot}")

        try:
            height = float(row["height"])
            parcel_bounds = geom_data[lot]
            for j, polygon in enumerate(parcel_bounds):
                building_name = f"{building_prefix}_{lot}_{j+1}"
                generate_building(polygon, height, building_name)
                successful_buildings += 1
                print(f"Successfully generated building for {lot} geom {j+1} with height {height} ft")
            
        except Exception as e:
            print(f"Error generating building for {lot} geom {j}: {e}", file=sys.stderr)
            if raise_err:
                raise e
            else:
                continue
    print(f"Building generation complete: {successful_buildings}/{total_parcels} buildings created")

# NOTE: Some properties have multiple discontiguous polygons
DUBOCE_NORTHEAST_CORNER_BOUNDS = [[
    (-122.43128652, 37.77000042),
    (-122.43125537, 37.76984584),
    (-122.43156286, 37.76980688),
    (-122.43159400, 37.76996146),
    ]]
DUBOCE_SOUTH_INTERIOR_BOUNDS = [[
    [-122.431917, 37.768911],
    [-122.431943, 37.769185],
    [-122.431861, 37.769191],
    [-122.431834, 37.768916],
    [-122.431917, 37.768911]
]]

def run_sample_building():
    # Integration test
    generate_building(DUBOCE_NORTHEAST_CORNER_BOUNDS[0], 85)

def run_sample_multiple_buildings():
    # integration test
    geom = {"3538095": DUBOCE_SOUTH_INTERIOR_BOUNDS,
            "0875013": DUBOCE_NORTHEAST_CORNER_BOUNDS}

    parcels = [
        {"mapblklot": "3538095", "height": 85},
        {"mapblklot": "0875013", "height": 85},
    ]
    generate_multiple_buildings(geom_data=geom,
                                parcel_specs=parcels,
                                )

def run_sample_from_files():
    # integration test / cli alternative
    geometry_file = os.path.expanduser("~/src/cityscaper/data/sf_map_unfiltered.json")
    csv_path = os.path.expanduser("~/Desktop/rezoning_output.csv")
    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    with open(csv_path, newline="") as f:
        parcels = list(csv.DictReader(f))

    generate_multiple_buildings(
        geom_data=geom_data,
        parcel_specs=parcels,
        building_prefix="Building"
    )


if __name__ == "__main__":
    run_sample_from_files()
