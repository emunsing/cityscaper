import bpy, bmesh, math, mathutils


class TransverseMercator:
    radius = 6378137.

    def __init__(self, **kwargs):
        # setting default values
        self.lat = 0.  # in degrees
        self.lon = 0.  # in degrees
        self.k = 1.  # scale factor

        for attr in kwargs:
            setattr(self, attr, kwargs[attr])
        self.latInRadians = math.radians(self.lat)

    def fromGeographic(self, lat, lon):
        lat = math.radians(lat)
        lon = math.radians(lon - self.lon)
        B = math.sin(lon) * math.cos(lat)
        x = 0.5 * self.k * self.radius * math.log((1. + B) / (1. - B))
        y = self.k * self.radius * (math.atan(math.tan(lat) / math.cos(lon)) - self.latInRadians)
        return (x, y, 0.)

    def toGeographic(self, x, y):
        x = x / (self.k * self.radius)
        y = y / (self.k * self.radius)
        D = y + self.latInRadians
        lon = math.atan(math.sinh(x) / math.cos(D))
        lat = math.asin(math.sin(D) / math.cosh(x))

        lon = self.lon + math.degrees(lon)
        lat = math.degrees(lat)
        return (lat, lon)

def dist_pt_seg_2d(p, a, b):
    vx, vy = b.x - a.x, b.y - a.y
    wx, wy = p.x - a.x, p.y - a.y
    denom = vx * vx + vy * vy
    if denom == 0:
        return math.hypot(wx, wy)
    t = max(0, min(1, (wx * vx + wy * vy) / denom))
    qx, qy = a.x + vx * t, a.y + vy * t
    return math.hypot(p.x - qx, p.y - qy)

def make_uv_mat(name, img_path):
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

# ─────────────────────────────────────────────────────────────────────────────
# 0) Building parameters: (lat, lon) geojson and height in feet
# ─────────────────────────────────────────────────────────────────────────────
parcel_ll = [
    (-122.43128652, 37.77000042),
    (-122.43125537, 37.76984584),
    (-122.43156286, 37.76980688),
    (-122.43159400, 37.76996146),
]
parcel_height = 85


# ─────────────────────────────────────────────────────────────────────────────
# 1) Set up projection (must match your BLOSM import)
# ─────────────────────────────────────────────────────────────────────────────
scene = bpy.context.scene
lat0, lon0 = scene["lat"], scene["lon"]
proj = TransverseMercator(lat=lat0, lon=lon0, k=1.0)

# ─────────────────────────────────────────────────────────────────────────────
# 2) Define your parcel corners (lon, lat) from R
# ─────────────────────────────────────────────────────────────────────────────

# project to Blender units (X, Y)
parcel_xy = [proj.fromGeographic(lat=lat, lon=lon)[:2] for lon, lat in parcel_ll]

# ─────────────────────────────────────────────────────────────────────────────
# 3) Sample ground Z: lowest tile-mesh vertex within 3 m of parcel boundary
# ─────────────────────────────────────────────────────────────────────────────
# build 2D boundary segments
edges = []
for i in range(len(parcel_xy)):
    a = mathutils.Vector(parcel_xy[i])
    b = mathutils.Vector(parcel_xy[(i + 1) % len(parcel_xy)])
    edges.append((a, b))

tile = bpy.data.objects["Google 3D Tiles"]
M = tile.matrix_world
min_z = float('inf')
for v in tile.data.vertices:
    w = M @ v.co
    p2 = mathutils.Vector((w.x, w.y))
    d = min(dist_pt_seg_2d(p2, a, b) for a, b in edges)
    if d <= 3.0:
        min_z = min(min_z, w.z)

if min_z == float('inf'):
    raise RuntimeError("No ground vert found within 3 m")

# ─────────────────────────────────────────────────────────────────────────────
# 4) Build & extrude the Building mesh
# ─────────────────────────────────────────────────────────────────────────────
h_bu = parcel_height * 0.3048  # 85 ft → ~25.9 m → Blender units

mesh = bpy.data.meshes.new("BuildingMesh")
obj = bpy.data.objects.new("Building", mesh)
bpy.context.collection.objects.link(obj)

bm = bmesh.new()
verts = [bm.verts.new((x, y, min_z)) for x, y in parcel_xy]
face = bm.faces.new(verts)
bm.faces.ensure_lookup_table()
bm.normal_update()

res = bmesh.ops.extrude_face_region(bm, geom=[face])
bm.verts.ensure_lookup_table()
for e in res["geom"]:
    if isinstance(e, bmesh.types.BMVert):
        e.co.z += h_bu

bm.to_mesh(mesh)
bm.free()


# ─────────────────────────────────────────────────────────────────────────────
# 5) Create Box-projection materials
# ─────────────────────────────────────────────────────────────────────────────

wall_mat = make_uv_mat("WallMaterial", "wall_24_38m_x24_85.jpeg")
roof_mat = make_uv_mat("RoofMaterial", "tiles_066m_1m.jpg")

obj.data.materials.clear()
obj.data.materials.append(wall_mat)  # slot 0
obj.data.materials.append(roof_mat)  # slot 1

# 6) Compute repeats from real dims ---------------------------------------
# 1 BU = 1 m in BLOSM
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

# bpy.ops.object.mode_set(mode='EDIT')

if not obj.data.uv_layers:
    obj.data.uv_layers.new(name="UVMap")

bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
# bpy.ops.uv.smart_project(island_margin=0.01, correct_aspect=True) # Smart‐Project ensures every face gets a UV island filling [0..1]×[0..1]
bpy.ops.uv.cube_project(cube_size=1.0, correct_aspect=True, scale_to_bounds=True)
bpy.ops.object.mode_set(mode='OBJECT')

uv_data = obj.data.uv_layers.active.data
wall_ids = {p.index for p in obj.data.polygons
            if abs((p.normal @ obj.matrix_world.to_3x3()).z) < 0.2}
roof_ids = {p.index for p in obj.data.polygons
            if abs((p.normal @ obj.matrix_world.to_3x3()).z) > 0.9}


# helper to scale a set of polygons
def scale_islands(face_ids, u_repeat, v_repeat):
    for poly in obj.data.polygons:
        if poly.index in face_ids:
            for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                uv = uv_data[li].uv
                uv.x *= u_repeat
                uv.y *= v_repeat


scale_islands(wall_ids, wall_u, wall_v)
scale_islands(roof_ids, roof_u, roof_v)

for p in obj.data.polygons:
    wn = (p.normal @ obj.matrix_world.to_3x3()).normalized()
    p.material_index = 1 if abs(wn.z) > 0.9 else 0

obj.data.update()