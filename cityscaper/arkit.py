import click
import logging
import bpy
import sys
import os
import csv
import json
from cityscaper.blender_building import TransverseMercator, make_uv_mat, create_building_mesh, apply_materials_and_uvs

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


def create_dae_for_xy_building(parcel_xy, height_meters, building_name, export_dir,
                                   ground_z=0,
                                   apply_materials=False):
    obj = create_building_mesh(
        parcel_xy=parcel_xy,
        height_meters=height_meters,
        ground_z=ground_z,
        building_name=building_name
    )

    if apply_materials:
        apply_materials_and_uvs(obj)

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
    export_path = os.path.join(export_dir, f"{building_name}.dae")

    # bpy.ops.export_scene.collada(
    #     filepath=export_path,
    #     use_selection=True,  # only exports your building
    #     apply_modifiers=True,  # bake any modifiers
    #     axis_forward='Y',  # Blender X→E, Y→N → ARKit expects Y forward
    #     axis_up='Z'  # Z up in both Blender and ARKit
    # )
    # bpy.ops.wm.collada_export(
    #     filepath=export_path,
    #     selected=True,  # only export the active/selected object
    #     apply_modifiers=True,  # bake in any modifiers
    #     export_global_forward_selection='Y',  # use Blender’s Y axis as “forward”
    #     export_global_up_selection='Z',  # use Blender’s Z axis as “up”
    #     apply_global_orientation=True,  # actually apply that axis rotation
    #     triangulate=True,  # optional, Collada likes triangles
    #     use_texture_copies=True  # include your textures if any
    # )
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


@cli.command()
@click.argument('csv_path', type=click.Path(exists=True, dir_okay=False))
@click.option('--geometry_file', type=click.Path(exists=True, dir_okay=False), default=os.path.expanduser("~/src/cityscaper/data/sf_map_unfiltered.json"))
@click.option('--building_prefix', default='building', help='Prefix for building names')
@click.option('--export_dir', type=click.Path(), default=os.path.expanduser("~/Desktop/arkit_buildings"), help='Directory to export DAE files')
@click.option('--raise_err', is_flag=True, help='Raise error on failure to generate a building')
@click.option('--apply_materials', is_flag=True, help='Apply materials to the generated buildings')
def build_dae_from_csv( csv_path, geometry_file, building_prefix, export_dir, raise_err, apply_materials):

    with open(geometry_file, "r") as f:
        geom_data = json.load(f)

    with open(csv_path, newline="") as f:
        parcel_specs = list(csv.DictReader(f))

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

                create_dae_for_xy_building(
                    parcel_xy=parcel_xy,
                    height_meters=height * 0.3048,  # Convert feet to meters
                    building_name=building_name,
                    export_dir=export_dir,
                    apply_materials=apply_materials
                )
        except Exception as e:
            print(f"Error generating building for {lot} geom {j}: {e}", file=sys.stderr)
            if raise_err:
                raise e
            else:
                continue

    with open(os.path.join(export_dir, 'building_centroids.json'), 'w') as f:
        json.dump(building_centroids, f, indent=4)

    print("Done generating buildings")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli()