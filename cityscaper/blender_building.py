"""
Blender building generation module.

This module provides functions to generate 3D buildings in Blender based on
parcel coordinates and height specifications.
"""

import csv
import sys
import bpy
import bmesh
import json
import math
import mathutils
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

project_root = Path.home() / "src/cityscaper"

short_wall_textures_dir = project_root / "textures/walls_short"
wall_textures_dir = project_root / "textures/walls"
high_wall_textures_dir = project_root / "textures/walls_high"
roof_textures_dir = project_root / "textures/roofs"

short_wall_textures = sorted([f.name for f in short_wall_textures_dir.iterdir() 
                              if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png'}])

wall_textures = sorted([f.name for f in wall_textures_dir.iterdir() 
                              if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png'}])

high_wall_textures = sorted([f.name for f in high_wall_textures_dir.iterdir() 
                              if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png'}])

roof_textures = sorted([f.name for f in roof_textures_dir.iterdir() 
                              if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png'}])

print(f"Loaded {len(short_wall_textures)} short wall textures: {short_wall_textures}")
print(f"Loaded {len(wall_textures)} regular wall textures: {wall_textures}")
print(f"Loaded {len(high_wall_textures)} high wall textures: {high_wall_textures}")
print(f"Loaded {len(roof_textures)} roof textures: {roof_textures}")

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


def make_red_material(name: str) -> bpy.types.Material:
    """
    Create a solid red material for placeholder buildings.
    
    Args:
        name: Name for the material
        
    Returns:
        Blender material with solid red color
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    links = nt.links

    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    
    # Set solid red color
    bsdf.inputs["Base Color"].default_value = (1.0, 0.0, 0.0, 1.0)
    
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


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
    tex.image = bpy.data.images.load(img_path)
    tex.extension = 'REPEAT'
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")

    links.new(texco.outputs["UV"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def make_animated_material(name: str, img_path: str, transition_frame: int) -> bpy.types.Material:
    """
    Create a material that transitions from red to textured at a specific frame.
    
    Args:
        name: Name for the material
        img_path: Path to the texture image file
        transition_frame: Frame at which to transition from red to textured
        
    Returns:
        Blender material with animated color transition
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    links = nt.links

    # Create nodes
    texco = nt.nodes.new("ShaderNodeTexCoord")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(img_path)
    tex.extension = 'REPEAT'
    
    # Color mix node for blending red and texture
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.blend_type = 'MIX'
    
    # Red color input (try different input names for different Blender versions)
    try:
        mix.inputs["Color1"].default_value = (1.0, 0.0, 0.0, 1.0)
        color1_input = "Color1"
        color2_input = "Color2"
    except KeyError:
        # Newer Blender versions use "A" and "B"
        mix.inputs["A"].default_value = (1.0, 0.0, 0.0, 1.0)
        color1_input = "A"
        color2_input = "B"
    
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")

    # Connect nodes
    links.new(texco.outputs["UV"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], mix.inputs[color2_input])
    links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    
    # Animate the mix factor (try different factor input names)
    try:
        fac_input = "Fac"
        mix.inputs[fac_input].default_value = 0.0  # Start with red (factor = 0)
    except KeyError:
        # Newer Blender versions use "Factor"
        fac_input = "Factor"
        mix.inputs[fac_input].default_value = 0.0
    
    mix.inputs[fac_input].keyframe_insert(data_path="default_value", frame=transition_frame - 1)
    
    mix.inputs[fac_input].default_value = 1.0  # End with texture (factor = 1)
    mix.inputs[fac_input].keyframe_insert(data_path="default_value", frame=transition_frame + 15)  # 0.5 second transition at 30fps
    
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
                        ground_z: float=0.0,
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
    # Create or get a dedicated collection for buildings
    buildings_collection = bpy.data.collections.get("Generated Buildings")
    if buildings_collection is None:
        buildings_collection = bpy.data.collections.new("Generated Buildings")
        bpy.context.scene.collection.children.link(buildings_collection)
    
    mesh = bpy.data.meshes.new(f"{building_name}Mesh")
    obj = bpy.data.objects.new(building_name, mesh)
    buildings_collection.objects.link(obj)

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

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    bm.to_mesh(mesh)
    bm.free()
    
    return obj


def apply_materials_and_uvs(obj: bpy.types.Object, 
                           wall_texture_path: str,
                           roof_texture_path: str,
                           transition_frame: Optional[int] = None) -> None:
    """
    Apply materials and UV mapping to a building object.
    
    Args:
        obj: Building object to apply materials to
        wall_texture_path: Full path to wall texture file
        roof_texture_path: Full path to roof texture file
        transition_frame: Frame to transition from red to textured (None for static materials)
    """
    # Paths are already complete
    
    # Create materials based on whether animation is requested
    if transition_frame is not None:
        wall_mat = make_animated_material(f"AnimWallMat_{obj.name}", wall_texture_path, transition_frame)
        roof_mat = make_animated_material(f"AnimRoofMat_{obj.name}", roof_texture_path, transition_frame)
    else:
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
    roof_u = width_m / 3
    roof_v = depth_m / 3

    # Create UV layer if needed
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")

    # Select only our building object and make it active
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
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
        p.material_index = 1 if abs(wn.z) > 0.7 else 0

    obj.data.update()


def generate_building(parcel_coords: List[List[float]],
                     height_feet: float,
                     building_name: str = "Building",
                     wall_texture_path: str = None,
                     roof_texture_path: str = None,
                     scene_lat: Optional[float] = None,
                     scene_lon: Optional[float] = None,
                     transition_frame: Optional[int] = None) -> bpy.types.Object:
    """
    Generate a complete building in Blender from parcel coordinates and height.
    
    This is the main function for creating buildings. It handles coordinate
    projection, ground elevation sampling, mesh creation, and material application.
    
    Args:
        parcel_coords: List of (lat, lon) tuples defining parcel boundary
        height_feet: Building height in feet
        building_name: Name for the building object
        wall_texture_path: Full path to wall texture file (defaults to first wall texture if None)
        roof_texture_path: Full path to roof texture file (defaults to first roof texture if None)
        scene_lat: Scene center latitude (uses scene data if None)
        scene_lon: Scene center longitude (uses scene data if None)
        transition_frame: Frame to transition from red to textured (None for static materials)
        
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
    
    # Use default textures if none provided
    if wall_texture_path is None:
        wall_texture_path = str(wall_textures_dir / wall_textures[0]) if wall_textures else str(wall_textures_dir / "wall_24_38m_x24_85.jpeg")
    if roof_texture_path is None:
        roof_texture_path = str(roof_textures_dir / roof_textures[0]) if roof_textures else str(roof_textures_dir / "tiles_066m_1m.jpg")
    
    # Apply materials and UVs
    apply_materials_and_uvs(obj, wall_texture_path, roof_texture_path, transition_frame)
    
    return obj 


def group_parcels_by_year(parcel_specs: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """
    Group parcel specifications by development year.
    
    Args:
        parcel_specs: List of parcel dictionaries with 'development_study_year' field
        
    Returns:
        Dictionary mapping year to list of parcels for that year
    """
    parcels_by_year = {}
    for parcel in parcel_specs:
        year = int(parcel.get('development_study_year', 0))
        if year not in parcels_by_year:
            parcels_by_year[year] = []
        parcels_by_year[year].append(parcel)
    return parcels_by_year


def generate_multiple_buildings(geom_data: dict[str, List[List[List[float]]]],
                                parcel_specs: list[dict[str, Any]],
                                building_prefix: str = "Building",
                                raise_err=True) -> None:
    """
    Generate multiple buildings from geometry data and parcel specifications.
    
    Args:
        geom_data: dictionary of geometry keyed by mapblklot
        parcel_specs: list of parcel spec dictionaries; must contain 'mapblklot' and 'height'
        building_prefix: Prefix for building object names
        raise_err: Whether to raise exceptions or continue on errors
    """
    successful_buildings, total_parcels = 0, len(parcel_specs)
    short_wall_index = 0
    wall_index = 0
    high_wall_index = 0
    roof_index = 0

    for i, row in enumerate(parcel_specs):
        lot = row["mapblklot"]
        print(f"Processing parcel {i+1}/{total_parcels}: {lot}")

        try:
            height = float(row["height"])
            parcel_bounds = geom_data[lot]
            for j, polygon in enumerate(parcel_bounds):
                # Get current textures with full paths
                if height < 100:
                    wall_filename = short_wall_textures[short_wall_index % len(short_wall_textures)]
                    wall_texture_path = str(short_wall_textures_dir / wall_filename)
                    short_wall_index += 1
                    print(f"Building {lot} height {height}: Using SHORT texture {wall_filename}")
                elif height > 150:
                    wall_filename = high_wall_textures[high_wall_index % len(high_wall_textures)]
                    wall_texture_path = str(high_wall_textures_dir / wall_filename)
                    high_wall_index += 1
                    print(f"Building {lot} height {height}: Using HIGH texture {wall_filename}")
                else:
                    wall_filename = wall_textures[wall_index % len(wall_textures)]
                    wall_texture_path = str(wall_textures_dir / wall_filename)
                    wall_index += 1
                    print(f"Building {lot} height {height}: Using REGULAR texture {wall_filename}")
                
                roof_filename = roof_textures[roof_index % len(roof_textures)]
                roof_texture_path = str(roof_textures_dir / roof_filename)
                roof_index += 1
                
                building_name = f"{building_prefix}_{lot}_{j+1}"
                generate_building(polygon, height, building_name, wall_texture_path, roof_texture_path)
                successful_buildings += 1
                print(f"Successfully generated building for {lot} geom {j+1} with height {height} ft")
            
        except Exception as e:
            print(f"Error generating building for {lot} geom {j}: {e}", file=sys.stderr)
            if raise_err:
                raise e
            else:
                continue
    print(f"Building generation complete: {successful_buildings}/{total_parcels} buildings created")


def generate_animated_buildings(geom_data: dict[str, List[List[List[float]]]],
                                parcel_specs: list[dict[str, Any]],
                                building_prefix: str = "Building",
                                frames_per_year: int = 30,
                                raise_err=True) -> None:
    """
    Generate animated buildings that appear over time based on development year.
    
    Args:
        geom_data: dictionary of geometry keyed by mapblklot
        parcel_specs: list of parcel spec dictionaries with 'development_study_year' field
        building_prefix: Prefix for building object names
        frames_per_year: Number of frames per development year (30 = 1 second at 30fps)
        raise_err: Whether to raise exceptions or continue on errors
    """
    # Group parcels by development year
    parcels_by_year = group_parcels_by_year(parcel_specs)
    max_year = max(parcels_by_year.keys()) if parcels_by_year else 0
    
    # Set scene frame range
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = (max_year + 1) * frames_per_year
    
    print(f"Setting up animation for {max_year + 1} years ({bpy.context.scene.frame_end} frames)")
    
    successful_buildings = 0
    short_wall_index = 0
    wall_index = 0
    high_wall_index = 0
    roof_index = 0
    
    # Process each year
    for year in sorted(parcels_by_year.keys()):
        year_parcels = parcels_by_year[year]
        year_start_frame = year * frames_per_year + 30
        
        print(f"Processing year {year}: {len(year_parcels)} parcels appearing over frames {year_start_frame}-{year_start_frame + frames_per_year}")
        
        for i, row in enumerate(year_parcels):
            # Distribute buildings evenly throughout the year
            if len(year_parcels) > 1:
                appear_frame = year_start_frame + int((i / (len(year_parcels) - 1)) * frames_per_year)
            else:
                appear_frame = year_start_frame
            lot = row["mapblklot"]
            
            try:
                height = float(row["height"])
                if lot not in geom_data:
                    print(f"Warning: No geometry found for {lot}")
                    continue
                    
                parcel_bounds = geom_data[lot]
                for j, polygon in enumerate(parcel_bounds):
                    # Get current textures with full paths
                    if height < 100:
                        wall_filename = short_wall_textures[short_wall_index % len(short_wall_textures)]
                        wall_texture_path = str(short_wall_textures_dir / wall_filename)
                        short_wall_index += 1
                    elif height > 180:
                        wall_filename = high_wall_textures[high_wall_index % len(high_wall_textures)]
                        wall_texture_path = str(high_wall_textures_dir / wall_filename)
                        high_wall_index += 1
                    else:
                        wall_filename = wall_textures[wall_index % len(wall_textures)]
                        wall_texture_path = str(wall_textures_dir / wall_filename)
                        wall_index += 1
                    
                    roof_filename = roof_textures[roof_index % len(roof_textures)]
                    roof_texture_path = str(roof_textures_dir / roof_filename)
                    roof_index += 1
                    
                    # Create building with material transition animation
                    building_name = f"{building_prefix}_Y{year}_{lot}_{j+1}"
                    transition_frame = appear_frame + 15  # 0.5 seconds after appearance at 30fps
                    obj = generate_building(polygon, height, building_name, wall_texture_path, roof_texture_path, transition_frame=transition_frame)
                    
                    # Set up visibility animation (building appears, then transitions)
                    # Hidden before this year
                    obj.hide_viewport = True
                    obj.hide_render = True
                    obj.keyframe_insert(data_path="hide_viewport", frame=appear_frame - 1)
                    obj.keyframe_insert(data_path="hide_render", frame=appear_frame - 1)
                    
                    # Visible from this year onwards (red block appears first)
                    obj.hide_viewport = False
                    obj.hide_render = False
                    obj.keyframe_insert(data_path="hide_viewport", frame=appear_frame)
                    obj.keyframe_insert(data_path="hide_render", frame=appear_frame)
                    
                    successful_buildings += 1
                    print(f"Created animated building for {lot} (year {year}, appears frame {appear_frame}, transitions frame {transition_frame})")
                
            except Exception as e:
                print(f"Error generating building for {lot}: {e}", file=sys.stderr)
                if raise_err:
                    raise e
                else:
                    continue
    
    print(f"Animation generation complete: {successful_buildings} buildings created over {max_year + 1} years")


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
    geometry_file = project_root / "data/sf_map_unfiltered.json"
    csv_path = project_root / "data/rezoning_output.csv"
    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    with open(csv_path, newline="") as f:
        parcels = list(csv.DictReader(f))
    
    # Limit to first 3 entries for performance
    parcels = parcels[:3]

    generate_multiple_buildings(
        geom_data=geom_data,
        parcel_specs=parcels,
        building_prefix="Building"
    )


def run_animated_sample():
    # animation test
    geometry_file = project_root / "data/sf_map_unfiltered.json"
    csv_path = project_root / "data/rezoning_output.csv"
    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    with open(csv_path, newline="") as f:
        parcels = list(csv.DictReader(f))
    
    # Limit to first 20 entries to see animation across multiple years
    # parcels = parcels[:20]

    generate_animated_buildings(
        geom_data=geom_data,
        parcel_specs=parcels,
        building_prefix="AnimatedBuilding",
        frames_per_year=30  
    )


def run_transition_test():
    # Test the red-to-textured transition with a single building
    generate_building(
        DUBOCE_NORTHEAST_CORNER_BOUNDS[0], 
        85, 
        "TransitionTestBuilding", 
        transition_frame=30  # Transition at frame 30 (1 second at 30fps)
    )


if __name__ == "__main__":
    run_animated_sample()
