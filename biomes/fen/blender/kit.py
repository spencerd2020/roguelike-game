"""Modelling and bake kit for the Ambermere Fen assets (bpy 5.x as a Python module).

The process follows the hand-built asset pipeline the studio already uses, rebuilt for this game:

  generator (bmesh)  ->  closed, chamfered solids, every primitive tagged with a part id, a material slot and a grain
                         direction (face attributes)
  UV                 ->  every face gets atlas space (smart projection, fixed margin)
  bake (Cycles CPU)  ->  per texel: position, true normal, grain direction, part id + slot, sky light (an overcast dome
                         with a high sun, so the light comes from above and an asset can stand at any yaw), crevice
                         occlusion, and for houses the hearth's own light
  paint (numpy)      ->  painter.py turns those fields into palette pixels (fields in model space, so nothing breaks at
                         a UV seam), with per-part tone, per-material wear, and ordered dither through palette ramps
  export             ->  one glb per asset: the atlas surface, a glow surface (embers, lamp glass), an alpha-cut card
                         surface for foliage; flat (faceted) normals
"""
import math, random, zlib
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector

SLOTS = ['peat', 'timber', 'bark', 'stone', 'shingle', 'deck', 'fleece', 'paint', 'clay', 'iron', 'rope', 'wicker',
         'ember', 'glass', 'moss', 'sphag', 'pad', 'flower', 'pitcher', 'sundew', 'cloth', 'soot', 'lichen', 'wood',
         'sedge', 'hide']
SI = {s: i for i, s in enumerate(SLOTS)}
GLOW = {'ember', 'glass'}          # flat glowing surfaces (not lit by the painter's light, emissive in the page)


def stream(seed, stage):
    """One random stream per stage, hashed from the seed and the stage name."""
    return random.Random(zlib.crc32(f'{seed}/{stage}'.encode()))


class Rec:
    """A bmesh plus, per face, its part id, slot and grain direction."""

    def __init__(self):
        self.bm = bmesh.new()
        L = self.bm.faces.layers
        self.lp, self.ls = L.int.new('pid'), L.int.new('slot')
        self.lg = [L.float.new('gx'), L.float.new('gy'), L.float.new('gz')]
        self.parts = []
        self.pidx = {}
        self.centres = []
        self.markers = {}

    def tag(self, faces, part, slot, g):
        if part not in self.pidx:
            self.pidx[part] = len(self.parts)
            self.parts.append(part)
            vs = {v for f in faces for v in f.verts}
            c = sum((v.co for v in vs), Vector()) / max(1, len(vs))
            self.centres.append(tuple(c))
        pid = self.pidx[part]
        g = Vector(g).normalized() if Vector(g).length > 1e-9 else Vector((0, 0, 1))
        for f in faces:
            f[self.lp] = pid
            f[self.ls] = SI[slot]
            for k in range(3):
                f[self.lg[k]] = g[k]

    @staticmethod
    def faces_of(verts):
        return list({f for v in verts for f in v.link_faces})


def _chamfer(R, verts, e):
    if e <= 0:
        return verts
    edges = list({ed for v in verts for ed in v.link_edges})
    res = bmesh.ops.bevel(R.bm, geom=list(verts) + edges, offset=e, offset_type='OFFSET', segments=1, affect='EDGES',
                          profile=0.5, clamp_overlap=True)
    return list({v for f in res['faces'] for v in f.verts} | set(v for v in verts if v.is_valid))


def frame(p0, p1, roll=0.0):
    """Matrix whose Z runs from p0 to p1 (length kept separately), X rolled about it."""
    p0, p1 = Vector(p0), Vector(p1)
    d = (p1 - p0)
    z = d.normalized()
    up = Vector((0, 0, 1)) if abs(z.z) < 0.95 else Vector((1, 0, 0))
    x = up.cross(z).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    return Matrix.Translation(p0) @ m @ Matrix.Rotation(roll, 4, 'Z')


def box(R, part, slot, M, size, e=0.0, g=None):
    """A chamfered box of size (x, y, z) centred at M's origin in M's axes. Grain runs along the longest side."""
    sx, sy, sz = size
    m = M @ Matrix.Diagonal(Vector((sx, sy, sz, 1)))
    res = bmesh.ops.create_cube(R.bm, size=1.0, matrix=m)
    verts = _chamfer(R, res['verts'], min(e, 0.45 * min(size)))
    if g is None:
        k = max(range(3), key=lambda i: size[i])
        g = M.to_3x3() @ Vector([1 if i == k else 0 for i in range(3)])
    R.tag(R.faces_of(verts), part, slot, g)
    return verts


def beam(R, part, slot, p0, p1, w, d, e=0.0, roll=0.0, ext=0.0):
    p0, p1 = Vector(p0), Vector(p1)
    L = (p1 - p0).length + 2 * ext
    M = frame(p0, p1, roll) @ Matrix.Translation((0, 0, (p1 - p0).length / 2))
    return box(R, part, slot, M, (w, d, L), e, g=(p1 - p0))


def cyl(R, part, slot, p0, p1, r0, r1=None, segs=8, e=0.0, roll=0.0, caps=True):
    p0, p1 = Vector(p0), Vector(p1)
    r1 = r0 if r1 is None else r1
    L = (p1 - p0).length
    M = frame(p0, p1, roll) @ Matrix.Translation((0, 0, L / 2))
    res = bmesh.ops.create_cone(R.bm, cap_ends=caps, cap_tris=False, segments=segs, radius1=r0, radius2=r1, depth=L, matrix=M)
    verts = res['verts']
    if e > 0:
        verts = _chamfer(R, [v for v in verts], min(e, 0.3 * min(r0, r1 if r1 > 0 else r0)))
    R.tag(R.faces_of(verts), part, slot, p1 - p0)
    return verts


def lathe(R, part, slot, prof, segs, M=Matrix(), close_top=True, close_bottom=True, g=(0, 0, 1), phase=0.0, wob=None):
    """Revolve a profile [(r, z), ...] about M's Z. wob(a, z) -> radius multiplier."""
    rings = []
    bm = R.bm
    for (r, z) in prof:
        ring = []
        for i in range(segs):
            a = phase + 2 * math.pi * i / segs
            k = wob(a, z) if wob else 1.0
            ring.append(bm.verts.new(M @ Vector((r * k * math.cos(a), r * k * math.sin(a), z))))
        rings.append(ring)
    faces = []
    for j in range(len(rings) - 1):
        A, B = rings[j], rings[j + 1]
        for i in range(segs):
            faces.append(bm.faces.new((A[i], A[(i + 1) % segs], B[(i + 1) % segs], B[i])))
    if close_bottom and prof[0][0] > 1e-6:
        faces.append(bm.faces.new(list(reversed(rings[0]))))
    if close_top and prof[-1][0] > 1e-6:
        faces.append(bm.faces.new(rings[-1]))
    R.tag(faces, part, slot, M.to_3x3() @ Vector(g))
    return faces


def revolve(R, part, slot, prof, a0, a1, segs, M, g=(0, 0, 1)):
    """Revolve a closed profile [(r, z)] from angle a0 to a1 and cap both ends (a solid wedge of a ring)."""
    bm = R.bm
    rings = []
    for i in range(segs + 1):
        a = a0 + (a1 - a0) * i / segs
        rings.append([bm.verts.new(M @ Vector((r * math.cos(a), r * math.sin(a), z))) for (r, z) in prof])
    faces = []
    m = len(prof)
    for i in range(segs):
        A, B = rings[i], rings[i + 1]
        for j in range(m):
            faces.append(bm.faces.new((A[j], B[j], B[(j + 1) % m], A[(j + 1) % m])))
    faces.append(bm.faces.new(rings[0]))
    faces.append(bm.faces.new(list(reversed(rings[-1]))))
    R.tag(faces, part, slot, M.to_3x3() @ Vector(g))
    return faces


def rmf(points):
    """Rotation-minimising frames along a polyline: (tangent, normal, binormal) per point."""
    P = [Vector(p) for p in points]
    T = []
    for i in range(len(P)):
        a, b = P[max(i - 1, 0)], P[min(i + 1, len(P) - 1)]
        T.append((b - a).normalized())
    up = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = [up.cross(T[0]).normalized()]
    for i in range(1, len(P)):
        n = N[-1] - T[i] * N[-1].dot(T[i])
        N.append(n.normalized() if n.length > 1e-6 else N[-1])
    return T, N, [T[i].cross(N[i]) for i in range(len(P))]


def tube(R, part, slot, points, radii, segs=8, cap0=True, cap1=True, lobe=None, jag=0.0, rng=None):
    """A swept tube; lobe(world_angle, t) -> radius multiplier (flutes and buttresses). jag ragged-breaks the far end."""
    bm = R.bm
    T, N, B = rmf(points)
    rings = []
    n = len(points)
    for i, p in enumerate(points):
        ring = []
        t = i / max(1, n - 1)
        for k in range(segs):
            a = 2 * math.pi * k / segs
            d = N[i] * math.cos(a) + B[i] * math.sin(a)
            wa = math.atan2(d.y, d.x)
            m = lobe(wa, t) if lobe else 1.0
            q = Vector(p) + d * radii[i] * m
            if i == n - 1 and jag and rng:
                q += T[i] * rng.uniform(0, jag)
            ring.append(bm.verts.new(q))
        rings.append(ring)
    faces = []
    for j in range(n - 1):
        A, Bq = rings[j], rings[j + 1]
        for k in range(segs):
            faces.append(bm.faces.new((A[k], A[(k + 1) % segs], Bq[(k + 1) % segs], Bq[k])))
    if cap0:
        faces.append(bm.faces.new(list(reversed(rings[0]))))
    if cap1:
        faces.append(bm.faces.new(rings[-1]))
    R.tag(faces, part, slot, Vector(points[-1]) - Vector(points[0]))
    return faces


def slab(R, part, slot, outline, z0, z1, g=(1, 0, 0)):
    """An extruded closed polygon (outline in XY, counter-clockwise)."""
    bm = R.bm
    lo = [bm.verts.new((x, y, z0)) for x, y in outline]
    hi = [bm.verts.new((x, y, z1)) for x, y in outline]
    faces = [bm.faces.new(list(reversed(lo))), bm.faces.new(hi)]
    n = len(outline)
    for i in range(n):
        faces.append(bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i])))
    R.tag(faces, part, slot, g)
    return faces


# ---------------------------------------------------------------- object, UV, bake

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def to_object(R, name):
    bmesh.ops.remove_doubles(R.bm, verts=R.bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(name)
    R.bm.to_mesh(me)
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob['parts'] = R.parts
    return ob


def select_only(ob):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def hidden_faces(ob, gap=0.03, gap_down=0.09):
    """Faces pressed against another surface (block ends, bed joints, board undersides): they get no atlas area."""
    from mathutils.bvhtree import BVHTree
    import bmesh as _bm
    bm = _bm.new()
    bm.from_mesh(ob.data)
    tree = BVHTree.FromBMesh(bm)
    hid = np.zeros(len(bm.faces), bool)
    for f in bm.faces:
        n = f.normal
        if n.length < 0.5 or f.calc_area() < 1e-6:
            continue
        c = f.calc_center_median()
        d = gap_down if n.z < -0.8 else gap
        loc, nn, idx, dist = tree.ray_cast(c + n * 0.0015, n, d)
        if loc is not None:
            # a second ray from a corner-ward point, so a face only half covered stays in the atlas
            ok = True
            for v in f.verts[:4]:
                q = c.lerp(v.co, 0.7) + n * 0.0015
                l2, _, _, _ = tree.ray_cast(q, n, d)
                if l2 is None:
                    ok = False
                    break
            hid[f.index] = ok
    bm.free()
    return hid


def unwrap(ob, margin=0.0025, angle=55, hide=True):
    hid = hidden_faces(ob) if hide else np.zeros(len(ob.data.polygons), bool)
    ob.data.polygons.foreach_set('select', ~hid)
    select_only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.data.polygons.foreach_set('select', ~hid)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0, correct_aspect=True,
                             scale_to_bounds=False)
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.data.polygons.foreach_set('select', ~hid)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.uv.pack_islands(margin=margin, margin_method='FRACTION', rotate=True, shape_method='CONCAVE')
    except Exception as ex:
        print('pack_islands failed:', ex)
    bpy.ops.object.mode_set(mode='OBJECT')
    # hidden faces all collapse onto one texel in the corner (painted dark peat, never seen)
    uv = ob.data.uv_layers.active.data
    loops = np.zeros(len(ob.data.polygons) * 2, np.int32)
    st = np.zeros(len(ob.data.polygons), np.int32)
    ct = np.zeros(len(ob.data.polygons), np.int32)
    ob.data.polygons.foreach_get('loop_start', st)
    ob.data.polygons.foreach_get('loop_total', ct)
    uvs = np.zeros(len(uv) * 2, np.float32)
    uv.foreach_get('uv', uvs)
    uvs = uvs.reshape(-1, 2)
    for i in np.nonzero(hid)[0]:
        uvs[st[i]:st[i] + ct[i]] = (0.9995, 0.9995)
    uv.foreach_set('uv', uvs.reshape(-1))
    print(ob.name, 'hidden faces', int(hid.sum()), 'of', len(hid))
    return hid


def _bake_material(ob, img):
    mat = bpy.data.materials.new(ob.name + '_bake')
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    out = N('ShaderNodeOutputMaterial')
    emit = N('ShaderNodeEmission')
    diff = N('ShaderNodeBsdfDiffuse')
    diff.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1)
    geo = N('ShaderNodeNewGeometry')
    att = {k: N('ShaderNodeAttribute') for k in ('pid', 'slot', 'gx', 'gy', 'gz')}
    for k, a in att.items():
        a.attribute_name = k
        a.attribute_type = 'GEOMETRY'
    cid = N('ShaderNodeCombineXYZ')
    cg = N('ShaderNodeCombineXYZ')
    nt.links.new(att['pid'].outputs['Fac'], cid.inputs[0])
    nt.links.new(att['slot'].outputs['Fac'], cid.inputs[1])
    for i, k in enumerate(('gx', 'gy', 'gz')):
        nt.links.new(att[k].outputs['Fac'], cg.inputs[i])
    tex = N('ShaderNodeTexImage')
    tex.image = img
    nt.nodes.active = tex
    src = {'pos': geo.outputs['Position'], 'nrm': geo.outputs['True Normal'], 'gdir': cg.outputs['Vector'],
           'pid': cid.outputs['Vector']}
    ob.data.materials.clear()
    ob.data.materials.append(mat)

    def use(kind):
        for l in list(out.inputs['Surface'].links):
            nt.links.remove(l)
        for l in list(emit.inputs['Color'].links):
            nt.links.remove(l)
        if kind in src:
            nt.links.new(src[kind], emit.inputs['Color'])
            nt.links.new(emit.outputs['Emission'], out.inputs['Surface'])
        else:
            nt.links.new(diff.outputs['BSDF'], out.inputs['Surface'])
    return use


def sky_world(strength=1.0, sun=3.0, ground=0.12):
    """An overcast dome brighter at the zenith, and a high sun: light from above, no strong azimuth."""
    w = bpy.data.worlds.new('sky')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (ground, ground, ground, 1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (strength, strength, strength, 1)
    e = ramp.color_ramp.elements.new(0.52)
    e.color = (0.55 * strength, 0.55 * strength, 0.55 * strength, 1)
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
    if sun > 0:
        sd = bpy.data.lights.new('sun', 'SUN')
        sd.energy = sun
        sd.angle = math.radians(25)
        so = bpy.data.objects.new('sun', sd)
        so.rotation_euler = (math.radians(18), math.radians(8), 0)
        bpy.context.scene.collection.objects.link(so)
        return so
    return None


def bake(ob, size, samples=40, ao_dist=0.12, hearths=(), occluders=(), light_size=None):
    """Bake every field the painter needs into float arrays (size x size, row 0 at the bottom)."""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.use_denoising = False
    sc.render.bake.margin = 6
    sc.render.bake.use_clear = True
    img = bpy.data.images.new(ob.name + '_bk', size, size, float_buffer=True, alpha=False)
    img.colorspace_settings.name = 'Non-Color'
    ls = light_size or size
    img2 = bpy.data.images.new(ob.name + '_bkl', ls, ls, float_buffer=True, alpha=False)
    img2.colorspace_settings.name = 'Non-Color'
    use = _bake_material(ob, img)
    tex = [n for n in ob.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE'][0]
    out = {}

    def run(kind, btype, samp, **kw):
        # light-type fields are smooth: bake them at light_size and scale up, the fine fields at full size
        im = img if btype == 'EMIT' else img2
        tex.image = im
        s = im.size[0]
        use(kind)
        sc.cycles.samples = samp
        sc.render.bake.margin = 6 if s == size else 4
        select_only(ob)
        bpy.ops.object.bake(type=btype, **kw)
        buf = np.zeros(s * s * 4, np.float32)
        im.pixels.foreach_get(buf)
        a = buf.reshape(s, s, 4)[:, :, :3].copy()
        if s != size:
            a = upsample(a, size // s)
        out[kind] = a

    for kind in ('pos', 'nrm', 'gdir', 'pid'):
        run(kind, 'EMIT', 1)
    # coverage: texels that belong to a face (bake margin bleeds values out, so mark coverage with a fresh emit)
    run('light', 'DIFFUSE', samples, pass_filter={'DIRECT', 'INDIRECT'})
    sc.world.light_settings.distance = ao_dist
    run('ao', 'AO', max(16, samples // 2))
    if hearths:
        hs = []
        for o in sc.objects:
            if o.type == 'LIGHT':
                o.hide_render = True
        saved = sc.world
        black = bpy.data.worlds.new('black')
        black.color = (0, 0, 0)
        sc.world = black
        for (p, energy) in hearths:
            ld = bpy.data.lights.new('hearth', 'POINT')
            ld.energy = energy
            ld.shadow_soft_size = 0.35
            lo = bpy.data.objects.new('hearth', ld)
            lo.location = p
            sc.collection.objects.link(lo)
            hs.append(lo)
        run('warm', 'DIFFUSE', samples, pass_filter={'DIRECT', 'INDIRECT'})
        for lo in hs:
            bpy.data.objects.remove(lo)
        sc.world = saved
        for o in sc.objects:
            if o.type == 'LIGHT':
                o.hide_render = False
    else:
        out['warm'] = np.zeros_like(out['light'])
    # coverage mask from a UV raster, not from the margin-bled bakes
    out['mask'] = uv_mask(ob, size)
    return out


def upsample(a, f):
    """Bilinear upscale by an integer factor (texel centres aligned)."""
    s = a.shape[0]
    x = (np.arange(s * f) + 0.5) / f - 0.5
    x0 = np.clip(np.floor(x).astype(int), 0, s - 1)
    x1 = np.clip(x0 + 1, 0, s - 1)
    t = np.clip(x - x0, 0, 1)
    rows = a[x0] * (1 - t)[:, None, None] + a[x1] * t[:, None, None]
    return rows[:, x0] * (1 - t)[None, :, None] + rows[:, x1] * t[None, :, None]


def uv_mask(ob, size):
    """1 where a texel centre lies inside a UV triangle (numpy raster)."""
    me = ob.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    n = len(me.loop_triangles)
    tri = np.zeros((n, 3, 2), np.float32)
    lt = np.zeros(n * 3, np.int32)
    me.loop_triangles.foreach_get('loops', lt)
    uvs = np.zeros(len(uv) * 2, np.float32)
    uv.foreach_get('uv', uvs)
    uvs = uvs.reshape(-1, 2)
    tri = uvs[lt.reshape(-1, 3)] * size - 0.5
    mask = np.zeros((size, size), np.uint8)
    for t in tri:
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        X, Y = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        (ax, ay), (bx, by), (cx, cy) = t
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / d
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / d
        l3 = 1 - l1 - l2
        e = -0.6 / max(abs(d), 1e-9) ** 0.5   # a hair of slack so thin slivers still own their texels
        inside = (l1 >= e) & (l2 >= e) & (l3 >= e)
        mask[Y[inside], X[inside]] = 1
    return mask


def finish(ob, atlas_png, glow_slots=GLOW, card_png=None, split=None):
    """Swap the bake material for the painted atlas; glow faces get their own flat emissive surface."""
    img = bpy.data.images.load(atlas_png)
    img.colorspace_settings.name = 'sRGB'

    def tex_mat(name, emissive=False, alpha=False):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = nt.nodes.get('Principled BSDF')
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img
        t.interpolation = 'Closest'
        nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
        bsdf.inputs['Roughness'].default_value = 0.9
        if emissive:
            nt.links.new(t.outputs['Color'], bsdf.inputs['Emission Color'])
            bsdf.inputs['Emission Strength'].default_value = 1.0
        return m

    ob.data.materials.clear()
    ob.data.materials.append(tex_mat(ob.name + '_atlas'))
    ob.data.materials.append(tex_mat(ob.name + '_glow', emissive=True))
    slot = np.zeros(len(ob.data.polygons), np.int32)
    ob.data.attributes['slot'].data.foreach_get('value', slot)
    gl = np.isin(slot, [SI[s] for s in glow_slots]).astype(np.int32)
    ob.data.polygons.foreach_set('material_index', gl)
    out = [ob]
    if split:
        pid = np.zeros(len(ob.data.polygons), np.int32)
        ob.data.attributes['pid'].data.foreach_get('value', pid)
        names = list(ob['parts'])
        sel = np.array([any(names[p].startswith(s) for s in split) for p in pid])
        ob2 = ob.copy()
        ob2.data = ob.data.copy()
        ob2.name = ob.name + '_roof'
        bpy.context.scene.collection.objects.link(ob2)
        for o, keep in ((ob, ~sel), (ob2, sel)):
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(~keep)[0]], context='FACES')
            bm.to_mesh(o.data)
            bm.free()
        out.append(ob2)
    for o in out:
        for k in ('pid', 'slot', 'gx', 'gy', 'gz'):
            a = o.data.attributes.get(k)
            if a:
                o.data.attributes.remove(a)
    return out


def glb_swap_images(path, swaps):
    """Replace embedded images (matched by name substring) with the bytes of our own PNGs, keeping indexed PNGs indexed."""
    import json, struct
    data = open(path, 'rb').read()
    jlen = struct.unpack_from('<I', data, 12)[0]
    js = json.loads(data[20:20 + jlen])
    bin_off = 20 + jlen
    blen = struct.unpack_from('<I', data, bin_off)[0]
    binb = data[bin_off + 8:bin_off + 8 + blen]
    views = [binb[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']] for v in js['bufferViews']]
    for im in js.get('images', []):
        for key, png in swaps.items():
            if key in im.get('name', '') and 'bufferView' in im:
                views[im['bufferView']] = open(png, 'rb').read()
                im['mimeType'] = 'image/png'
    out = bytearray()
    for i, v in enumerate(views):
        while len(out) % 4:
            out += b'\0'
        js['bufferViews'][i]['byteOffset'] = len(out)
        js['bufferViews'][i]['byteLength'] = len(v)
        out += v
    while len(out) % 4:
        out += b'\0'
    js['buffers'][0]['byteLength'] = len(out)
    jb = json.dumps(js, separators=(',', ':')).encode()
    while len(jb) % 4:
        jb += b' '
    total = 12 + 8 + len(jb) + 8 + len(out)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))
        f.write(struct.pack('<II', len(jb), 0x4E4F534A))
        f.write(jb)
        f.write(struct.pack('<II', len(out), 0x004E4942))
        f.write(out)


def export_glb(path, objs):
    for o in bpy.context.scene.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_apply=True,
                              export_yup=True, export_extras=True, export_normals=False, export_materials='EXPORT')
