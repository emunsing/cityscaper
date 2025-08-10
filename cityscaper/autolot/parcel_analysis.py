from cityscaper.autolot.utils import build_contiguous_line_string, get_first_to_final_angle
import shapely
import numpy as np
import geopandas as gpd
from shapely.geometry import LineString, Polygon
import itertools
from cityscaper.autolot.utils import perpendicular_line
from cityscaper.autolot.utils import MIN_FRONT_LENGTH
import pandas as pd
from cityscaper.autolot.utils import get_nearest_parcels
from shapely.ops import nearest_points
from shapely.geometry import Point
from shapely.ops import split as shapely_split
from loguru import logger
import traceback
from dataclasses import dataclass

def get_front_point(front_group_rec, use_shortest_line=False, min_segment_length = 3):
    front_line_string = build_contiguous_line_string(front_group_rec)
    angle_between_ends = get_first_to_final_angle(front_line_string)
    if (angle_between_ends < np.pi / 3.0):
        use_shortest_line = False
        logger.info("Overriding use_shortest_line to False because angle between ends is too small to warrant it")
    if use_shortest_line:

        best_candidate = None
        for line, _ in front_group_rec.iterrows():
            if line.length < min_segment_length:
                continue
            if best_candidate is None:
                best_candidate = line
            elif line.length < best_candidate.length:
                best_candidate = line
        if best_candidate is None:
            return get_front_point(front_group_rec, use_shortest_line=False, min_segment_length=min_segment_length)
        front_midpoint = shapely.line_interpolate_point(best_candidate, 0.5 * best_candidate.length)
    else:
        
        front_midpoint = shapely.line_interpolate_point(front_line_string, 0.5 * front_line_string.length)
    return front_midpoint


def parcel_adjacency(prop_rec):
    # Add a column to the boundary properties dataframe to indicate what the boundary segment is adjacent to
    prop_rec["adj"] = "parcel"
    # Identify the boundary segments that are not primarily abutting another parcel
    possible_front_mask = prop_rec["segment_group"] == True
    # Label them as fronts to start with
    prop_rec.loc[possible_front_mask, "adj"] = "front"
    # Identify the boundary segments groups that are not considered the front
    possible_fronts_df = prop_rec.loc[possible_front_mask].copy()
    possible_fronts_df["lengths"] = possible_fronts_df.index.map(lambda x: x.length)
    group_lengths = possible_fronts_df.groupby("group_id")["lengths"].sum()
    # Choose the possible front group that is closest to the street as the front
    viable_groups = group_lengths[group_lengths > MIN_FRONT_LENGTH].index
    if len(viable_groups) == 0:
        viable_groups = possible_fronts_df["group_id"].unique()
    front_group = possible_fronts_df[possible_fronts_df["group_id"].isin(viable_groups)].groupby("group_id")["dist_from_street"].mean().idxmin()
    if prop_rec.loc[possible_front_mask, "group_id"].nunique() > 1:
        non_front_groups_mask = possible_fronts_df["group_id"] != front_group
        prop_rec.loc[non_front_groups_mask & possible_front_mask, "adj"] = "other"
    # Get the segments for that group
    front_group_rec = prop_rec.loc[prop_rec["group_id"] == front_group]
    return prop_rec, front_group_rec



def get_boundary_props(parcel_ser, blockid, street_buffer=None, cut_off_prop=0.5) -> pd.DataFrame:
    nearest_parcels = get_nearest_parcels(parcel_ser, blockid, 25)
    union_nearest =  nearest_parcels.geometry.union_all()
    target_parcel = parcel_ser.loc[blockid]

    mitered_out = target_parcel.buffer(1, join_style='mitre', cap_style='square')
    prop_rec = {}
    initial_segment_group = None
    current_segment_group = None
    group_id = -1
    for start_coord, end_coord in itertools.pairwise(mitered_out.exterior.coords):
        ext_line = LineString([start_coord, end_coord])
        original_start, _ = nearest_points(target_parcel, Point(start_coord))
        original_end, _ = nearest_points(target_parcel, Point(end_coord))
        
        original_ext_line = LineString([original_start, original_end])
        entry = {
            "prop_in_neighbor_parcels":ext_line.intersection(union_nearest).length  / ext_line.length,
            "raw_length":original_ext_line.length,
        }
        segment_group = (entry["prop_in_neighbor_parcels"] < cut_off_prop)
        if current_segment_group != segment_group:
            group_id += 1
            current_segment_group = segment_group
        if initial_segment_group is None:
            initial_segment_group = segment_group
        entry["group_id"] = group_id
        entry["segment_group"] = segment_group

        if street_buffer is not None:
            entry["dist_from_street"] = ext_line.distance(street_buffer)
        if original_ext_line in prop_rec:
            logger.warning("duplicate line")
        prop_rec[original_ext_line] = pd.Series(entry)
    if current_segment_group == initial_segment_group:
        map_to_0 = group_id
    else:
        map_to_0 = 0

    prop_rec = pd.DataFrame(prop_rec).T
    prop_rec.loc[prop_rec["group_id"] == map_to_0, "group_id"] = 0
    return prop_rec


@dataclass
class ParcelAnalysisResult:
    prop_rec: pd.DataFrame
    front_midpoint: Point
    rear_point: Point
    envelope_rear_setback: LineString
    target_parcel_envelope: Polygon
    front_group_rec: pd.DataFrame
    foot_print_double_buff: Polygon

def get_sides_df(parcel_ser, blockid, street_buffer=None, use_shortest_line=False):
    # Extract the target parcel from the parcel series
    target_parcel = parcel_ser.loc[blockid]
    # Get the boundary properties of the target parcel (one row for each boundary segment)
    prop_rec = get_boundary_props(parcel_ser, blockid, street_buffer=street_buffer)
    # Augment with adjacency information and segment groups
    prop_rec, front_group_rec = parcel_adjacency(prop_rec)
    
    try:
        # Find its midpoint (lots of options in here)
        front_midpoint = get_front_point(front_group_rec, use_shortest_line=use_shortest_line)
    except Exception as e:
        err_str = traceback.format_exc()
        logger.error(f"{blockid} failed with error: {err_str}")
        target_parcel = target_parcel.buffer(0).simplify(0.25)

        # Get the boundary properties of the target parcel (one row for each boundary segment)
        prop_rec = get_boundary_props(parcel_ser, blockid, street_buffer=street_buffer)
        # Augment with adjacency information and segment groups
        prop_rec, front_group_rec = parcel_adjacency(prop_rec)
        try:
            front_midpoint = get_front_point(front_group_rec, use_shortest_line=use_shortest_line)
        except Exception as e:
            err_str = traceback.format_exc()
            logger.error(f"{blockid} failed with error: {err_str}")
            front_midpoint = None
            return ParcelAnalysisResult(
                prop_rec=None,
                front_midpoint=None,
                rear_point=None,
                envelope_rear_setback=None,
                target_parcel_envelope=None,
                front_group_rec=None,
                foot_print_double_buff=target_parcel.buffer(20).oriented_envelope)
    # TODO: handle multi-polygon parcels
    assert len(target_parcel.geoms) == 1, "Multi-polygon parcels are not supported"
    parcel_ex = target_parcel.geoms[0].exterior
    front_point_dist_from_start = parcel_ex.project(front_midpoint)
    parcel_ex_length = parcel_ex.length
    # TODO: why is this not working? getting odd rear points for 1307001B for instance
    # A and B are mostly busted. Really just use C... the point furthest from the front
    # though even that doesn't work very well.
    rear_point_dist_from_start = 0.5 * parcel_ex_length + front_point_dist_from_start
    rear_pointa = shapely.line_interpolate_point(parcel_ex, rear_point_dist_from_start)
    rear_point_dist_from_start = 0.5 * parcel_ex_length - front_point_dist_from_start
    rear_pointb = shapely.line_interpolate_point(parcel_ex, rear_point_dist_from_start)
    all_points = shapely.MultiPoint(list(parcel_ex.segmentize(1).coords)[:-1])
    all_points_ser = gpd.GeoSeries(all_points.geoms)
    all_points_dist_ser = all_points_ser.distance(front_midpoint)
    rear_pointc_idx = all_points_dist_ser.idxmax()
    rear_pointc = all_points_ser.iloc[rear_pointc_idx]
    rpa_dist = shapely.distance(front_midpoint, rear_pointa)
    rpb_dist = shapely.distance(front_midpoint, rear_pointb)
    rpc_dist = shapely.distance(front_midpoint, rear_pointc)
    if rpa_dist < rpb_dist:
        rear_point = rear_pointb
    else:
        rear_point = rear_pointa
    if rpc_dist > max(rpa_dist, rpb_dist):
        rear_point = rear_pointc
    # Here we use the rear point to find a first pass at a rear setback, though we only use it
    # if the better approach fails.
    try:
        rear_setback = perpendicular_line(front_midpoint, rear_point, length_multiplier=10, center_fraction=0.75)
    except Exception as e:
        err_str = traceback.format_exc()
        logger.error(f"{blockid} failed with error: {err_str}")
        rear_setback = None
    # Better approach: use a bounding envelope, choose the lines closest to and
    # farthest from the front, and draw a line between them.
    assert len(target_parcel.geoms) == 1, "Multi-polygon parcels are not supported"
    target_parcel_envelope = target_parcel.geoms[0].oriented_envelope
    front_line = None
    front_line_dist = np.inf
    rear_line = None
    rear_line_dist = -np.inf
    for coords_pair in itertools.pairwise(target_parcel_envelope.exterior.coords):
        line = LineString(coords_pair)
        front_dist = shapely.distance(line, front_midpoint)
        rear_dist = shapely.distance(line, front_midpoint)

        if front_dist < front_line_dist:
            front_line = line
            front_line_dist = front_dist
        if rear_dist > rear_line_dist:
            rear_line = line
            rear_line_dist = rear_dist
    # actually fix the rear based on the front
    
    for coord_start, coord_end in itertools.pairwise(target_parcel_envelope.exterior.coords):
        if coord_start not in front_line.coords and coord_end not in front_line.coords:
            rear_line = LineString([coord_start, coord_end])
            break
    # Find the midpoints of the front and back, create a line between them
    # If that fails, fall back
    envelope_front_midpoint = front_line.interpolate(0.5, normalized=True)
    envelope_rear_point = rear_line.interpolate(0.5, normalized=True)
    try:
        envelope_rear_setback = perpendicular_line(envelope_front_midpoint, envelope_rear_point, length_multiplier=10, center_fraction=0.75) #.intersection(target_parcel)
    except Exception as e:
        err_str = traceback.format_exc()
        logger.error(f"{blockid} failed with error: {err_str}")
        envelope_rear_setback = rear_setback

    # Split the lot along that line. 
    all_cuts = shapely_split(target_parcel, envelope_rear_setback)
    foot_print = None
    foot_print_dist = np.inf
    # Iterate through the new polygons, find the one that is closest to the front midpoint
    for cut in all_cuts.geoms:
        front_dist = shapely.distance(cut, front_midpoint)
        if front_dist < foot_print_dist:
            foot_print = cut
            foot_print_dist = front_dist
    if foot_print is None:
        logger.error(f"{blockid} failed to find a footprint")
        return prop_rec, front_midpoint, rear_point, envelope_rear_setback, target_parcel_envelope
    # Soften any overly narrow protuberances
    MIN_PROTUBERANCE_WIDTH = 3
    foot_print_double_buff = foot_print.buffer(-MIN_PROTUBERANCE_WIDTH, join_style=2).buffer(MIN_PROTUBERANCE_WIDTH, join_style=2).intersection(foot_print)

    par = ParcelAnalysisResult(
        prop_rec=prop_rec,
        front_midpoint=front_midpoint,
        rear_point=rear_point,
        envelope_rear_setback=envelope_rear_setback,
        target_parcel_envelope=target_parcel_envelope,
        front_group_rec=front_group_rec,
        foot_print_double_buff=foot_print_double_buff,
    )
    return par