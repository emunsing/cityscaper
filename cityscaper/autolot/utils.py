import itertools
import math
from dataclasses import dataclass
import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from shapely.ops import split as shapely_split


MIN_FRONT_LENGTH = 3.0

@dataclass
class LLNode:
    line: LineString
    next: "LLNode" = None
    prev: "LLNode" = None


def build_contiguous_line_string(group_rec):
    point_lookup = {}
    for line, _ in group_rec.iterrows():
        start_point, end_point = line.coords[0], line.coords[-1]
        this_node = LLNode(line=line)
        if not start_point in point_lookup:
            point_lookup[start_point] = this_node
        else:
            prev_node = point_lookup.pop(start_point)
            prev_node.next = this_node
            this_node.prev = prev_node

        if not end_point in point_lookup:
            point_lookup[end_point] = this_node
        else:
            prev_node = point_lookup.pop(end_point)
            prev_node.next = this_node
            this_node.prev = prev_node

    prev_node = this_node
    max_count = 100
    count = 0
    while prev_node is not None and count < max_count:
        count += 1
        this_node = prev_node
        prev_node = prev_node.prev

    if count == max_count:
        for line, row in group_rec.iterrows():
            print(line)
            print(row)
        raise ValueError("Failed to build contiguous line string. overrun chain construction")

    start_node = this_node
    line_list = [start_node.line]

    count = 0
    while this_node.next is not None and count < max_count:
        count += 1
        this_node = this_node.next
        line_list.append(this_node.line)
    if count == max_count:
        for line, row in group_rec.iterrows():
            print(line)
            print(row)
        raise ValueError("Failed to build contiguous line string. overrun origin search")

    coords_list = [line_list[0].coords[0]]
    for line in line_list:
        coords_list.append(line.coords[-1])

    return LineString(coords_list)


def get_nearest_parcels(parcel_ser, blockid, n_nearest=25):
    target_parcel = parcel_ser.loc[blockid]
    parcel_dists = parcel_ser.distance(target_parcel)
    nearest = parcel_dists.nsmallest(n_nearest)
    nearest_parcels = parcel_ser.loc[nearest.index]
    return nearest_parcels


def perpendicular_line(
    a: Point, b: Point, length_multiplier=10, center_fraction=0.75
) -> LineString:
    # Coordinates
    ax, ay = a.x, a.y
    bx, by = b.x, b.y

    # Vector from a to b
    dx = bx - ax
    dy = by - ay
    dist = math.hypot(dx, dy)

    if dist == 0:
        raise ValueError("Points a and b must be distinct")

    # Midpoint at 75% from a to b
    cx = ax + dx * center_fraction
    cy = ay + dy * center_fraction

    # Unit vector perpendicular to (dx, dy)
    perp_dx = -dy / dist
    perp_dy = dx / dist

    # Half length of desired line
    half_len = (dist * length_multiplier) / 2

    # Endpoints of perpendicular line
    p1 = (cx + perp_dx * half_len, cy + perp_dy * half_len)
    p2 = (cx - perp_dx * half_len, cy - perp_dy * half_len)

    return LineString([p1, p2])



padded_norm = lambda u: (np.linalg.norm(np.array(u)) + 1e-6)


def get_angle(first_leg, last_leg):
    return np.arccos(
        np.dot(first_leg, last_leg) / (padded_norm(first_leg) * padded_norm(last_leg))
    )


def get_first_to_final_angle(contiguous_line_string):
    first_leg = np.array(contiguous_line_string.coords[1]) - np.array(
        contiguous_line_string.coords[0]
    )
    last_leg = np.array(contiguous_line_string.coords[-1]) - np.array(
        contiguous_line_string.coords[-2]
    )
    return get_angle(first_leg, last_leg)
