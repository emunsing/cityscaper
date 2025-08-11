import click
import logging
import bpy
import sys
import os
import csv
import json
import zipfile
from cityscaper.blender_building import (TransverseMercator, make_uv_mat, create_building_mesh,
                                         get_roof_texture_path, get_wall_texture_path,
                                         apply_materials_and_uvs)


EXPORT_FORMATS = ['dae', 'usdz']

@click.group()
def cli():
    pass


def get_parcel_centroids(parcel_coords):
    lons, lats = zip(*parcel_coords)
    centroid_lat = sum(lats) / len(lats)
    centroid_lon = sum(lons) / len(lons)
    return centroid_lon, centroid_lat


def get_parcel_xy(parcel_coords, centroid_lon, centroid_lat):
    proj = TransverseMercator(lat=centroid_lat, lon=centroid_lon, k=1.0)

    centroid_x, centroid_y, _ = proj.fromGeographic(lat=centroid_lat, lon=centroid_lon)
    raw_xy = [proj.fromGeographic(lat=lat, lon=lon)[:2] for lon, lat in parcel_coords]

    parcel_xy = [(x - centroid_x, y - centroid_y) for (x, y) in raw_xy]
    return parcel_xy


def create_file_for_xy_building(parcel_xy, height_meters, building_name, export_dir,
                                ground_z=0,
                                apply_materials=False,
                                export_format='dae'):
    assert export_format.lower() in EXPORT_FORMATS, "Unsupported export format: %s" % export_format

    obj = create_building_mesh(
        parcel_xy=parcel_xy,
        height_meters=height_meters,
        ground_z=ground_z,
        building_name=building_name
    )

    if apply_materials:
        wall_material = get_wall_texture_path(height= height_meters * 3.28)  # Convert meters to feet
        roof_material = get_roof_texture_path()
        apply_materials_and_uvs(obj, wall_texture_path=wall_material, roof_texture_path=roof_material)

    bpy.context.collection.objects.link(obj)

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0

    # 3. Make this object the only selected/active one
    for o in scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    # 4. Apply transforms (if needed; here just to be safe)
    bpy.ops.object.transform_apply(location=False,
                                   rotation=False,
                                   scale=False)

    os.makedirs(export_dir, exist_ok=True)

    if export_format.lower() == 'dae':
        export_path = os.path.join(export_dir, f"{building_name}.dae")
        # bpy.ops.export_scene.collada(
        #     filepath=export_path,
        #     use_selection=True,  # only exports your building
        #     apply_modifiers=True,  # bake any modifiers
        #     axis_forward='Y',  # Blender X→E, Y→N → ARKit expects Y forward
        #     axis_up='Z'  # Z up in both Blender and ARKit
        # )
        bpy.ops.wm.collada_export(
            filepath=export_path,
            selected=True,  # only export the active/selected object
            apply_modifiers=True,  # bake in any modifiers
            export_global_forward_selection='Y',  # use Blender’s Y axis as “forward”
            export_global_up_selection='Z',  # use Blender’s Z axis as “up”
            apply_global_orientation=True,  # actually apply that axis rotation
            triangulate=True,  # optional, Collada likes triangles
            use_texture_copies=True  # include your textures if any
        )

    elif export_format.lower() == 'usdz':
        export_path = os.path.join(export_dir, f"{building_name}.usdz")
        bpy.ops.wm.usd_export(
            filepath=export_path,
            filter_usd=True,  # enable USD export
            selected_objects_only=True,  # only export your building
            visible_objects_only=True,  # skip hidden objects
            use_instancing=True,  # share duplicated geometry
            export_meshes=True,  # include meshes
            export_materials=True,  # include materials
            export_normals=True,  # include normals
            triangulate_meshes=True,  # optional: USD likes triangles
            convert_scene_units='METERS',  # bake units as meters
            meters_per_unit=1,  # 1 BU = 1 meter
            convert_orientation=True,  # apply axis remap
            export_global_forward_selection='Y',  # Blender +Y → file +Z (north)
            export_global_up_selection='Z'  # Blender +Z → file +Y (up)
        )
    else:
        raise ValueError(f"Unsupported export format: {export_format}")


def clear_scene():
    # delete all mesh objects
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    # also purge orphan data
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)

@cli.command()
@click.option("--input-dir",  required=True,
              type=click.Path(exists=True, file_okay=False),
              help="Folder containing .dae files to convert")
@click.option("--export-dir", required=True,
              type=click.Path(file_okay=False),
              help="Where to write the .usdz files")
@click.option("--export-format", default="{fname}.usdz",
              help="Python format string for output filename; use {fname} for basename")
def dae_to_usd(input_dir, export_dir, export_format):
    os.makedirs(export_dir, exist_ok=True)

    dae_files = sorted(
        f for f in os.listdir(input_dir)
        if f.lower().endswith(".dae")
    )
    if not dae_files:
        click.echo("No .dae files found in %s" % input_dir)
        return

    for dae in dae_files:
        fname = os.path.splitext(dae)[0]
        dae_path = os.path.join(input_dir, dae)
        usdz_name = export_format.format(fname=fname)
        usdz_path = os.path.join(export_dir, usdz_name)

        click.echo(f"Converting {dae} → {usdz_name}")

        # 1) Clear any existing objects
        clear_scene()

        # 2) Import the COLLADA file
        bpy.ops.wm.collada_import(
            filepath=dae_path,
            filter_collada=True,
            filter_folder=True,
            filter_blender=False
        )

        # 3) Select all imported objects
        for obj in bpy.context.scene.objects:
            obj.select_set(False)
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        # The import operator should auto-select; to be safe:
        for obj in bpy.context.scene.objects:
            if obj.type in {"MESH", "EMPTY", "ARMATURE"}:
                obj.select_set(True)

        # 4) Export to USDZ with your settings
        bpy.ops.wm.usd_export(
            filepath=usdz_path,
            filter_usd=True,
            selected_objects_only=True,
            visible_objects_only=True,
            use_instancing=True,
            export_meshes=True,
            export_materials=True,
            export_normals=True,
            triangulate_meshes=True,
            convert_scene_units='METERS',
            meters_per_unit=1,
            convert_orientation=True,
            export_global_forward_selection='Y',
            export_global_up_selection='Z'
        )


@cli.command()
@click.argument('csv_path', type=click.Path(exists=True, dir_okay=False))
@click.option('--geometry_file', type=click.Path(exists=True, dir_okay=False), default=os.path.expanduser("~/src/cityscaper/data/sf_map_unfiltered.json"))
@click.option('--building_prefix', default='building', help='Prefix for building names')
@click.option('--export_dir', type=click.Path(), default=os.path.expanduser("~/Desktop/arkit_buildings"), help='Directory to export DAE files')
@click.option('--raise_err', is_flag=True, help='Raise error on failure to generate a building')
@click.option('--apply_materials', is_flag=True, help='Apply materials to the generated buildings')
@click.option('--export_format', default='dae', type=click.Choice(EXPORT_FORMATS, case_sensitive=False), help='Export format for the buildings')
def buildings_from_csv( csv_path, geometry_file, building_prefix, export_dir, raise_err, apply_materials, export_format):
    """
    For each row in the CSV, generate a building file.
    All files will be written to the export_dir, with names like {building_prefix}_{mapblklot}_{index}.{export_format}
    Local coordinate systems are used for each building; centroids are stored in an exported JSON file.
    """

    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    with open(csv_path, newline="") as f:
        parcel_specs = list(csv.DictReader(f))

    building_centroids = buildings_from_list(
        parcel_specs=parcel_specs,
        geom_data=geom_data,
        building_prefix=building_prefix,
        export_dir=export_dir,
        raise_err=raise_err,
        apply_materials=apply_materials,
        export_format=export_format
    )

    with open(os.path.join(export_dir, f'{building_prefix}_centroids.json'), 'w') as f:
        json.dump(building_centroids, f, indent=4)

    print("Done generating buildings")


def buildings_from_list(parcel_specs, geom_data, building_prefix='building', export_dir=None,
                            raise_err=False, apply_materials=False, export_format='dae'):
    successful_buildings, total_parcels = 0, len(parcel_specs)
    building_centroids = {}

    for i, row in enumerate(parcel_specs):
        lot = row["mapblklot"]
        print(f"Processing parcel {i+1}/{total_parcels}: {lot}")

        try:
            height = float(row["height"])
            parcel_bounds = geom_data[lot]
            for j, polygon in enumerate(parcel_bounds):
                building_name = f"{building_prefix}_{lot}_{j+1}"

                centroid_lon, centroid_lat = get_parcel_centroids(polygon)
                building_centroids[building_name] = (centroid_lon, centroid_lat)
                parcel_xy = get_parcel_xy(polygon, centroid_lon, centroid_lat)

                create_file_for_xy_building(
                    parcel_xy=parcel_xy,
                    height_meters=height * 0.3048,  # Convert feet to meters
                    building_name=building_name,
                    export_dir=export_dir,
                    apply_materials=apply_materials,
                    export_format=export_format
                )
        except Exception as e:
            print(f"Error generating building for {lot} geom {j}: {e}", file=sys.stderr)
            if raise_err:
                raise e
            else:
                continue

    return building_centroids


def kmz_from_list(parcel_specs, geom_data, building_prefix='building', export_dir=None,
                     raise_err=False):
    """
    Generate KMZ files from a list of parcel specifications.
    
    This function creates a KMZ file containing all the DAE building models
    properly positioned at their accurate latitude/longitude coordinates for
    import into Google Earth.
    
    The function:
    1. Generates individual DAE files for each building using local coordinate systems
    2. Creates a KML file that references these DAE models at their correct lat/lon positions
    3. Packages everything into a KMZ file (ZIP format) for easy import into Google Earth
    4. Includes fallback polygon representations in case 3D models don't load
    
    Args:
        parcel_specs: List of parcel specification dictionaries with 'mapblklot' and 'height' keys
        geom_data: Dictionary mapping mapblklot to list of parcel geometry polygons
        building_prefix: Prefix for building names (default: 'building')
        export_dir: Directory to export files (defaults to current directory)
        raise_err: Whether to raise exceptions on errors (default: False)
        apply_materials: Whether to apply materials to buildings (default: False)
        
    Returns:
        Dictionary mapping building names to (longitude, latitude) centroid coordinates
        
    Example:
        # Generate KMZ from CSV data
        with open('parcels.csv', 'r') as f:
            parcel_specs = list(csv.DictReader(f))
        with open('geometry.json', 'r') as f:
            geom_data = json.load(f)
            
        centroids = kmz_from_list(
            parcel_specs=parcel_specs,
            geom_data=geom_data,
            building_prefix='my_buildings',
            export_dir='./output'
        )
        
        # This creates: ./output/my_buildings_buildings.kmz
    """
    
    if export_dir is None:
        export_dir = os.getcwd()
    
    # First, generate all the DAE files and get their centroids
    building_centroids = buildings_from_list(
        parcel_specs=parcel_specs,
        geom_data=geom_data,
        building_prefix=building_prefix,
        export_dir=export_dir,
        raise_err=raise_err,
        apply_materials=True,
        export_format='dae'
    )
    
    # Create the KML content for 3D models
    kml_content = create_kml_for_3d_models(building_centroids, building_prefix, export_dir, geom_data, parcel_specs)
    
    # Create the KMZ file
    kmz_path = os.path.join(export_dir, f"{building_prefix}_buildings.kmz")
    create_kmz_file(kmz_path, kml_content, export_dir, building_centroids, building_prefix)
    
    print(f"KMZ file created: {kmz_path}")
    return building_centroids


def create_kml_for_3d_models(building_centroids, building_prefix, export_dir, geom_data=None, parcel_specs=None):
    """
    Create KML content for 3D model placemarks.
    
    Args:
        building_centroids: Dictionary mapping building names to (lon, lat) coordinates
        building_prefix: Prefix for building names
        export_dir: Directory containing DAE files
        geom_data: Optional geometry data for fallback polygon representation
        parcel_specs: Optional parcel specifications for height data
        
    Returns:
        String containing the KML content
    """
    kml_header = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" 
     xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <name>3D Buildings</name>
    <description>Generated 3D building models</description>
    <Style id="buildingStyle">
      <PolyStyle>
        <color>cc0000ff</color>
        <outline>0</outline>
      </PolyStyle>
    </Style>
    <Style id="fallbackStyle">
      <PolyStyle>
        <color>ccff0000</color>
        <outline>1</outline>
        <outlineColor>ff000000</outlineColor>
      </PolyStyle>
    </Style>
"""
    
    kml_footer = """  </Document>
</kml>"""
    
    placemarks = []
    
    for building_name, (centroid_lon, centroid_lat) in building_centroids.items():
        # Create a placemark for each building
        dae_filename = f"{building_name}.dae"
        dae_path_in_kmz = f"{dae_filename}"
        
        # Extract lot and polygon index from building name
        # Format: {building_prefix}_{lot}_{index}
        parts = building_name.split('_')
        if len(parts) >= 3:
            lot = parts[1]
            poly_index = int(parts[2]) - 1  # Convert back to 0-based index
        else:
            lot = None
            poly_index = 0
        
        # Create the main 3D model placemark
        placemark = f"""    <Placemark>
      <name>{building_name}</name>
      <description>3D Building Model</description>
      <styleUrl>#buildingStyle</styleUrl>
      <Model>
        <altitudeMode>relativeToGround</altitudeMode>
        <Location>
          <longitude>{centroid_lon:.8f}</longitude>
          <latitude>{centroid_lat:.8f}</latitude>
          <altitude>0</altitude>
        </Location>
        <Orientation>
          <heading>0</heading>
          <tilt>0</tilt>
          <roll>0</roll>
        </Orientation>
        <Scale>
          <x>1</x>
          <y>1</y>
          <z>1</z>
        </Scale>
        <Link>
          <href>{dae_path_in_kmz}</href>
        </Link>
      </Model>
    </Placemark>"""
        
        placemarks.append(placemark)
        
#         # Add fallback polygon representation if geometry data is available
#         if geom_data and lot and lot in geom_data and poly_index < len(geom_data[lot]):
#             polygon = geom_data[lot][poly_index]
#             height = 0
#             if parcel_specs:
#                 for spec in parcel_specs:
#                     if spec.get("mapblklot") == lot:
#                         height = float(spec.get("height", 0)) * 0.3048  # Convert feet to meters
#                         break
#
#             # Create coordinate string for polygon
#             coord_strings = []
#             for lat, lon in polygon:
#                 coord_strings.append(f"              {lon},{lat},{height}")
#             coord_string = "\n".join(coord_strings)
#
#             fallback_placemark = f"""    <Placemark>
#       <name>{building_name}_fallback</name>
#       <description>Fallback polygon representation</description>
#       <styleUrl>#fallbackStyle</styleUrl>
#       <Polygon>
#         <extrude>1</extrude>
#         <altitudeMode>relativeToGround</altitudeMode>
#         <outerBoundaryIs>
#           <LinearRing>
#             <coordinates>
# {coord_string}
#             </coordinates>
#           </LinearRing>
#         </outerBoundaryIs>
#       </Polygon>
#     </Placemark>"""
#
#             placemarks.append(fallback_placemark)
    
    return kml_header + "\n".join(placemarks) + kml_footer


def create_kmz_file(kmz_path, kml_content, export_dir, building_centroids, building_prefix):
    """
    Create a KMZ file containing the KML and all files from the export directory.
    
    Args:
        kmz_path: Path where to save the KMZ file
        kml_content: KML content as string
        export_dir: Directory containing DAE files and textures
        building_centroids: Dictionary mapping building names to coordinates
        building_prefix: Prefix for building names
    """
    # First, collect all files we want to include (excluding the KMZ file itself)
    files_to_include = []
    
    # Use glob to get a snapshot of files without recursive walking
    import glob
    
    # Get all files in the export directory (non-recursive)
    for file_path in glob.glob(os.path.join(export_dir, "*")):
        if os.path.isfile(file_path):
            # Skip the KMZ file we're about to create
            if os.path.basename(file_path) == os.path.basename(kmz_path):
                continue
            files_to_include.append(file_path)
    
    # Also get files in any subdirectories (like texture subdirs)
    for file_path in glob.glob(os.path.join(export_dir, "**", "*"), recursive=True):
        if os.path.isfile(file_path):
            # Skip the KMZ file we're about to create
            if os.path.basename(file_path) == os.path.basename(kmz_path):
                continue
            if file_path not in files_to_include:  # Avoid duplicates
                files_to_include.append(file_path)
    
    print(f"Found {len(files_to_include)} files to include in KMZ")
    
    with zipfile.ZipFile(kmz_path, 'w', zipfile.ZIP_DEFLATED) as kmz:
        # Add the main KML file
        kmz.writestr('doc.kml', kml_content)
        
        # Add all collected files to the KMZ
        for file_path in files_to_include:
            # Calculate the relative path within the KMZ
            rel_path = os.path.relpath(file_path, export_dir)
            
            # For DAE files, put them in the models/ subdirectory
            if file_path.lower().endswith('.dae'):
                kmz_path_in_archive = f"{os.path.basename(file_path)}"
            else:
                # For other files (textures, etc.), maintain their relative structure
                kmz_path_in_archive = rel_path
            
            # Add the file to the KMZ
            kmz.write(file_path, kmz_path_in_archive)
            print(f"Added to KMZ: {kmz_path_in_archive}")


@cli.command()
@click.argument('csv_path', type=click.Path(exists=True, dir_okay=False))
@click.option('--geometry_file', type=click.Path(exists=True, dir_okay=False), default=os.path.expanduser("~/src/cityscaper/data/sf_map_unfiltered.json"))
@click.option('--building_prefix', default='building', help='Prefix for building names')
@click.option('--export_dir', type=click.Path(), default=os.path.expanduser("~/Desktop/arkit_buildings"), help='Directory to export KMZ file')
@click.option('--raise_err', is_flag=True, help='Raise error on failure to generate a building')
@click.option('--apply_materials', is_flag=True, help='Apply materials to the generated buildings')
def kmz_from_csv(csv_path, geometry_file, building_prefix, export_dir, raise_err, apply_materials):
    """
    Generate a KMZ file from CSV data containing building specifications.
    Creates a KMZ file with 3D building models properly positioned at their
    accurate latitude/longitude coordinates for import into Google Earth.
    """

    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    with open(csv_path, newline="") as f:
        parcel_specs = list(csv.DictReader(f))

    kmz_from_list(
        parcel_specs=parcel_specs,
        geom_data=geom_data,
        building_prefix=building_prefix,
        export_dir=export_dir,
        raise_err=raise_err,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli()
