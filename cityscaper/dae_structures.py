"""
DAE Structure placement module.

This module provides functions to import DAE (Collada) files and place them
as complex 3D structures across the map based on coordinate data.
"""

import csv
import sys
import bpy
import json
import math
import mathutils
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

project_root = Path.home() / "src/cityscaper"
dae_file_path = project_root / "data" / "Dubace Triangle_Test_02.dae" 


class TransverseMercator:
    """
    Transverse Mercator projection for converting geographic coordinates to Blender units.
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


def import_dae_structure(dae_path: str, structure_name: str = "ImportedStructure") -> bpy.types.Object:
    """
    Import a DAE file and return the main object.
    
    Args:
        dae_path: Path to the DAE file
        structure_name: Name to give the imported structure
        
    Returns:
        Main imported object
    """
    # Store current objects to identify new imports
    objects_before = set(bpy.context.scene.objects)
    
    # Import DAE file
    bpy.ops.wm.collada_import(filepath=dae_path)
    
    # Find newly imported objects
    objects_after = set(bpy.context.scene.objects)
    new_objects = objects_after - objects_before
    
    if not new_objects:
        raise RuntimeError(f"No objects imported from {dae_path}")
    
    # Create a collection for the structure
    collection_name = f"{structure_name}_Collection"
    structure_collection = bpy.data.collections.get(collection_name)
    if structure_collection is None:
        structure_collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(structure_collection)
    
    # Move all new objects to the collection and find the main object
    main_object = None
    for obj in new_objects:
        # Skip cameras and other non-mesh objects
        if obj.type != 'MESH':
            continue
            
        # Remove from default collection
        if obj.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(obj)
        # Add to structure collection
        structure_collection.objects.link(obj)
        
        # Consider the largest mesh object as main
        if main_object is None or len(obj.data.vertices) > len(main_object.data.vertices):
            main_object = obj
    
    if main_object:
        main_object.name = structure_name
    
    return main_object


def place_dae_structure(dae_path: str,
                       coordinates: List[float],
                       structure_name: str = "Structure",
                       height_offset: float = 0.0,
                       scale: float = 1.0,
                       rotation_z: float = 0.0,
                       scene_lat: Optional[float] = None,
                       scene_lon: Optional[float] = None) -> bpy.types.Object:
    """
    Import and place a DAE structure at specific coordinates.
    
    Args:
        dae_path: Path to the DAE file
        coordinates: [lon, lat] coordinates for placement
        structure_name: Name for the structure
        height_offset: Z offset from ground level
        scale: Scale factor for the structure
        rotation_z: Rotation around Z axis (degrees)
        scene_lat: Scene center latitude (uses scene data if None)
        scene_lon: Scene center longitude (uses scene data if None)
        
    Returns:
        Placed structure object
    """
    # Get scene projection parameters
    scene = bpy.context.scene
    if scene_lat is None:
        scene_lat = scene.get("lat", 37.7749)  # Default to SF center
    if scene_lon is None:
        scene_lon = scene.get("lon", -122.4194)  # Default to SF center
    
    print(f"Using projection center: ({scene_lon}, {scene_lat})")
    
    # Set up projection
    proj = TransverseMercator(lat=scene_lat, lon=scene_lon, k=1.0)
    
    # Convert coordinates to Blender units
    lon, lat = coordinates
    x, y, z = proj.fromGeographic(lat=lat, lon=lon)
    
    print(f"Geographic coordinates: ({lon}, {lat})")
    print(f"Projected Blender coordinates: ({x:.2f}, {y:.2f}, {z:.2f})")
    
    # Import the DAE structure
    structure_obj = import_dae_structure(dae_path, structure_name)
    
    # Position the structure
    structure_obj.location = (x, y, z + height_offset + 50)  # Add 50 units height
    print(f"Set object location to: {structure_obj.location}")
    structure_obj.scale = (50, 50, 50)  # Scale up 50x to make it visible
    structure_obj.rotation_euler = (0, 0, math.radians(rotation_z))
    
    # Make sure all objects in the collection are visible
    collection_name = f"{structure_name}_Collection"
    structure_collection = bpy.data.collections.get(collection_name)
    if structure_collection:
        for obj in structure_collection.objects:
            obj.hide_viewport = False
            obj.hide_render = False
            print(f"Made object {obj.name} visible")
    
    print(f"Placed structure '{structure_name}' at ({x:.2f}, {y:.2f}, {z + height_offset:.2f})")
    
    return structure_obj


def place_multiple_dae_structures(dae_path: str,
                                 location_specs: List[Dict[str, Any]],
                                 structure_prefix: str = "Structure") -> None:
    """
    Place multiple DAE structures at different locations.
    
    Args:
        dae_path: Path to the DAE file
        location_specs: List of location dictionaries with keys like:
                       - coordinates: [lon, lat]
                       - height_offset: float (optional)
                       - scale: float (optional)  
                       - rotation_z: float (optional)
        structure_prefix: Prefix for structure names
    """
    successful_placements = 0
    
    for i, spec in enumerate(location_specs):
        try:
            coordinates = spec["coordinates"]
            height_offset = spec.get("height_offset", 0.0)
            scale = spec.get("scale", 1.0)
            rotation_z = spec.get("rotation_z", 0.0)
            
            structure_name = f"{structure_prefix}_{i+1}"
            
            place_dae_structure(
                dae_path=dae_path,
                coordinates=coordinates,
                structure_name=structure_name,
                height_offset=height_offset,
                scale=scale,
                rotation_z=rotation_z
            )
            
            successful_placements += 1
            print(f"Successfully placed structure {i+1}/{len(location_specs)}")
            
        except Exception as e:
            print(f"Error placing structure {i+1}: {e}", file=sys.stderr)
            continue
    
    print(f"Placement complete: {successful_placements}/{len(location_specs)} structures placed")


def place_building_from_geom_data():
    """
    Place the building from the DAE file at its real coordinates using geometry data.
    """
    # Load the geometry data
    geometry_file = project_root / "data" / "sf_map_unfiltered.json"
    with open(geometry_file, "r") as f:
        geom_data = json.load(f)
    
    # The building in the DAE file
    mapblklot = "3542007"
    
    if mapblklot not in geom_data:
        print(f"Error: No geometry found for parcel {mapblklot}")
        return
    
    # Get the parcel coordinates (first polygon if multiple)
    parcel_coords = geom_data[mapblklot][0]  # [[lon, lat], [lon, lat], ...]
    
    # Calculate center point of the parcel
    lons = [coord[0] for coord in parcel_coords]
    lats = [coord[1] for coord in parcel_coords]
    center_lon = sum(lons) / len(lons)
    center_lat = sum(lats) / len(lats)
    
    print(f"Placing building {mapblklot} at center coordinates: ({center_lon:.6f}, {center_lat:.6f})")
    
    # Place the DAE structure at the parcel center
    place_dae_structure(
        dae_path=str(dae_file_path),
        coordinates=[center_lon, center_lat],
        structure_name=f"Building_{mapblklot}",
        height_offset=0.0,
        scale=1.0,
        rotation_z=0.0
    )


# Example usage
def run_sample_dae_placement():
    """
    Sample function to test DAE structure placement.
    """
    # Sample coordinates in San Francisco
    test_locations = [
        {
            "coordinates": [-122.4194, 37.7749],  # SF center
            "height_offset": 0.0,
            "scale": 1.0,
            "rotation_z": 0.0
        },
        {
            "coordinates": [-122.4094, 37.7849],  # Slightly northeast
            "height_offset": 5.0,
            "scale": 1.2,
            "rotation_z": 45.0
        }
    ]
    
    place_multiple_dae_structures(
        dae_path=str(dae_file_path),
        location_specs=test_locations,
        structure_prefix="TestStructure"
    )


if __name__ == "__main__":
    place_building_from_geom_data()