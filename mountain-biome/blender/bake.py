"""Unwrap, cull and bake per-texel data with Cycles (Blender 5.x).

Passes, all into float images on one unique atlas:
  pos   world position          nrm   true (faceted) normal
  id    part id, slot, edge     axis  grain axis of the part
  ao    Cycles ambient occlusion
  light diffuse light from a sky that is bright overhead, a high sun and the asset's own lamps (hearths, windows)
Faces nothing can see (stacked block contacts, undersides on the ground) are deleted before the unwrap so they take no
atlas area.
"""
import math
import time

import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

POS_OFF, POS_SCALE = 200.0, 400.0


def log(*a):
    print('[bake]', *a, flush=True)


def cull_hidden(obj, gap=0.004, ground=0.004):
    """Delete faces nothing can see: pressed fully against another face, fully inside another solid, or face-down on
    the ground. A face is tested at its centre and at each corner pulled 15% towards the centre; all must agree, so a
    face that is only partly covered stays (deleting it would open a hole)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    kill = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        if n.z < -0.95 and c.z < ground:
            kill.append(f)
            continue
        if f.calc_area() < 1e-7:
            kill.append(f)
            continue
        pts = [c] + [v.co.lerp(c, 0.15) for v in f.verts]
        hidden = True
        for p in pts:
            loc, hn, idx, dist = tree.ray_cast(p + n * 1e-4, n, 3.0)
            if loc is None or idx == f.index:
                hidden = False
                break
            if dist <= gap or (n.z < -0.3 and dist < 0.07 and hn.dot(n) < 0):   # pressed against a neighbour
                continue
            if hn.dot(n) > 0.2:        # the ray leaves a solid we are inside
                continue
            hidden = False
            break
        if hidden:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context='FACES_ONLY')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(me)
    bm.free()
    log(f'culled {len(kill)} hidden faces, {len(me.polygons)} left')


def select_only(obj):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def unwrap(obj, size, pad=2, fill=0.97):
    """One island per face at one texel density for the whole asset, laid in the face's own plane with u along the
    part's grain, rounded to whole pixels and shelf-packed. The density is the largest that fits the atlas."""
    t = time.time()
    me = obj.data
    nf = len(me.polygons)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    ax = np.zeros((nf, 3), np.float32)
    for k, nm in enumerate(('ax', 'ay', 'az')):
        a = me.attributes.get(nm)
        if a is not None:
            tmp = np.empty(nf, np.float32)
            a.data.foreach_get('value', tmp)
            ax[:, k] = tmp
    nrm = np.empty(nf * 3, np.float32)
    me.polygons.foreach_get('normal', nrm)
    nrm = nrm.reshape(-1, 3)
    ls = np.empty(nf, np.int32)
    me.polygons.foreach_get('loop_start', ls)
    lt = np.empty(nf, np.int32)
    me.polygons.foreach_get('loop_total', lt)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get('vertex_index', lv)
    part = np.zeros(nf, np.float32)
    pa = me.attributes.get('part')
    if pa is not None:
        pa.data.foreach_get('value', part)
    # a frame per face from its part's grain axis: A, and two directions across it
    A = ax / np.maximum(np.linalg.norm(ax, axis=1, keepdims=True), 1e-9)
    ref = np.where(np.abs(A[:, 2:3]) < 0.9, np.array([[0, 0, 1]], np.float32), np.array([[1, 0, 0]], np.float32))
    Bv = np.cross(ref, A); Bv /= np.maximum(np.linalg.norm(Bv, axis=1, keepdims=True), 1e-9)
    Cv = np.cross(A, Bv)
    dots = np.stack([np.sum(nrm * A, 1), np.sum(nrm * Bv, 1), np.sum(nrm * Cv, 1)], 1)
    k = np.argmax(np.abs(dots), 1)
    sgn = np.sign(dots[np.arange(nf), k])
    key = np.round(part).astype(np.int64) * 8 + k * 2 + (sgn > 0)
    # islands: connected faces sharing part and snapped direction
    le = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get('edge_index', le)
    fid = np.repeat(np.arange(nf), lt)
    o = np.argsort(le, kind='stable')
    e_s, f_s = le[o], fid[o]
    same = (e_s[1:] == e_s[:-1]) & (key[f_s[1:]] == key[f_s[:-1]])
    par = np.arange(nf)

    def find(x):
        r = x
        while par[r] != r:
            r = par[r]
        while par[x] != r:
            par[x], x = r, par[x]
        return r
    for f1, f2 in zip(f_s[:-1][same], f_s[1:][same]):
        r1, r2 = find(f1), find(f2)
        if r1 != r2:
            par[r2] = r1
    root = np.array([find(i) for i in range(nf)])
    isl, inv = np.unique(root, return_inverse=True)
    ni = len(isl)
    # island frame: projection along the snapped direction, u along the grain (or across it on end faces)
    rf = isl
    d = np.where(k[rf, None] == 0, A[rf], np.where(k[rf, None] == 1, Bv[rf], Cv[rf])) * sgn[rf, None]
    uu = np.where(k[rf, None] == 0, Bv[rf], A[rf])
    vv = np.cross(d, uu)
    P = co[lv]
    li = inv[fid]
    pu = np.sum(P * uu[li], 1)
    pv = np.sum(P * vv[li], 1)
    umin = np.full(ni, 1e9, np.float32); np.minimum.at(umin, li, pu)
    vmin = np.full(ni, 1e9, np.float32); np.minimum.at(vmin, li, pv)
    umax = np.full(ni, -1e9, np.float32); np.maximum.at(umax, li, pu)
    vmax = np.full(ni, -1e9, np.float32); np.maximum.at(vmax, li, pv)
    nf_faces = nf
    nf = ni
    W, H = umax - umin, vmax - vmin
    area = float(np.sum(W * H))
    dens = math.sqrt(fill * size * size / max(area, 1e-9))
    while True:
        rw = np.ceil(W * dens).astype(np.int64) + 2 * pad
        rh = np.ceil(H * dens).astype(np.int64) + 2 * pad
        order = np.argsort(-rh, kind='stable')
        ox = np.zeros(nf, np.int64); oy = np.zeros(nf, np.int64)
        x = y = shelf = 0
        ok = True
        for i in order:
            if x + rw[i] > size:
                y += shelf; x = 0; shelf = 0
            if rw[i] > size or y + rh[i] > size:
                ok = False
                break
            ox[i], oy[i] = x, y
            x += rw[i]
            shelf = max(shelf, rh[i])
        if ok:
            break
        dens *= 0.97
    uvx = (ox[li] + pad + (pu - umin[li]) * dens) / size
    uvy = (oy[li] + pad + (pv - vmin[li]) * dens) / size
    uv = me.uv_layers.new(name='atlas') if not me.uv_layers else me.uv_layers[0]
    uv.data.foreach_set('uv', np.stack([uvx, uvy], 1).astype(np.float32).ravel())
    obj['texel_density'] = dens
    log(f'unwrap {nf_faces} faces in {nf} islands at {dens:.0f} px/m, {time.time() - t:.1f}s')
    return dens


def _nodes(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    return nt, out


def _emit(nt, out, sock):
    em = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(sock, em.inputs['Color'])
    nt.links.new(em.outputs[0], out.inputs['Surface'])


def _affine(nt, sock, scale, off):
    """sock * scale + off, per component."""
    a = nt.nodes.new('ShaderNodeVectorMath')
    a.operation = 'MULTIPLY_ADD'
    nt.links.new(sock, a.inputs[0])
    a.inputs[1].default_value = scale
    a.inputs[2].default_value = off
    return a.outputs[0]


def setup_pass(obj, kind, img, slots, glow, kit_lights=None):
    for si, mat in enumerate(obj.data.materials):
        nt, out = _nodes(mat)
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        if kind == 'pos':
            s = 1.0 / POS_SCALE
            _emit(nt, out, _affine(nt, geo.outputs['Position'], (s, s, s), (POS_OFF * s,) * 3))
        elif kind == 'nrm':
            _emit(nt, out, _affine(nt, geo.outputs['True Normal'], (0.5, 0.5, 0.5), (0.5, 0.5, 0.5)))
        elif kind == 'axis':
            comb = nt.nodes.new('ShaderNodeCombineXYZ')
            for k, nme in enumerate(('ax', 'ay', 'az')):
                at = nt.nodes.new('ShaderNodeAttribute')
                at.attribute_type = 'GEOMETRY'
                at.attribute_name = nme
                nt.links.new(at.outputs['Fac'], comb.inputs[k])
            _emit(nt, out, _affine(nt, comb.outputs[0], (0.5, 0.5, 0.5), (0.5, 0.5, 0.5)))
        elif kind == 'id':
            at = nt.nodes.new('ShaderNodeAttribute')
            at.attribute_type = 'GEOMETRY'
            at.attribute_name = 'part'
            pm = nt.nodes.new('ShaderNodeMath')
            pm.operation = 'MULTIPLY'
            nt.links.new(at.outputs['Fac'], pm.inputs[0])
            pm.inputs[1].default_value = 1.0 / 65536.0
            bev = nt.nodes.new('ShaderNodeBevel')
            bev.samples = 8
            bev.inputs['Radius'].default_value = 0.02
            dot = nt.nodes.new('ShaderNodeVectorMath')
            dot.operation = 'DOT_PRODUCT'
            nt.links.new(bev.outputs[0], dot.inputs[0])
            nt.links.new(geo.outputs['True Normal'], dot.inputs[1])
            edge = nt.nodes.new('ShaderNodeMath')
            edge.operation = 'SUBTRACT'
            edge.inputs[0].default_value = 1.0
            nt.links.new(dot.outputs['Value'], edge.inputs[1])
            comb = nt.nodes.new('ShaderNodeCombineXYZ')
            nt.links.new(pm.outputs[0], comb.inputs[0])
            comb.inputs[1].default_value = (si + 0.5) / 64.0
            nt.links.new(edge.outputs[0], comb.inputs[2])
            _emit(nt, out, comb.outputs[0])
        elif kind == 'light':
            if slots[si] in glow:
                em = nt.nodes.new('ShaderNodeEmission')
                em.inputs['Color'].default_value = (1.0, 0.6, 0.28, 1)
                em.inputs['Strength'].default_value = 6.0
                nt.links.new(em.outputs[0], out.inputs['Surface'])
            else:
                d = nt.nodes.new('ShaderNodeBsdfDiffuse')
                d.inputs['Color'].default_value = (0.55, 0.55, 0.55, 1)
                nt.links.new(d.outputs[0], out.inputs['Surface'])
        else:   # ao: any surface will do
            d = nt.nodes.new('ShaderNodeBsdfDiffuse')
            nt.links.new(d.outputs[0], out.inputs['Surface'])
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        nt.nodes.active = tex


def sky_world(sun_dir=(0.25, -0.35, 1.0), sun=3.2):
    """A sky bright overhead and dim at the horizon, plus a high sun: light from above, the look the painter wants."""
    w = bpy.data.worlds.get('bake_sky') or bpy.data.worlds.new('bake_sky')
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.10, 0.10, 0.11, 1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.95, 0.98, 1.05, 1)
    mp = nt.nodes.new('ShaderNodeMapRange')
    mp.inputs['From Min'].default_value = -0.3
    mp.inputs['From Max'].default_value = 1.0
    nt.links.new(sep.outputs['Z'], mp.inputs['Value'])
    nt.links.new(mp.outputs[0], ramp.inputs[0])
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = 1.0
    nt.links.new(ramp.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    bpy.context.scene.world = w
    w.light_settings.distance = 1.2
    if 'bake_sun' not in bpy.data.objects:
        ld = bpy.data.lights.new('bake_sun', 'SUN')
        ld.energy = sun
        ld.angle = math.radians(25)
        so = bpy.data.objects.new('bake_sun', ld)
        bpy.context.scene.collection.objects.link(so)
        d = Vector(sun_dir).normalized()
        so.rotation_euler = Vector((0, 0, 1)).rotation_difference(d).to_euler()


def add_lamps(kit_lights):
    made = []
    for i, (p, col, watts, r) in enumerate(kit_lights or []):
        ld = bpy.data.lights.new(f'bake_lamp{i}', 'POINT')
        ld.energy = watts
        ld.color = col
        ld.shadow_soft_size = r
        lo = bpy.data.objects.new(f'bake_lamp{i}', ld)
        lo.location = p
        bpy.context.scene.collection.objects.link(lo)
        made.append(lo)
    return made


def bake_all(obj, size, slots, glow, kit_lights=None, samples=48, ao_dist=1.2, extra=()):
    """Bake every pass; returns a dict of HxWxC float arrays (row 0 = v 0) and the valid-texel mask.
    extra: other objects in the scene that cast light and shadow but are not baked (neighbours, ground)."""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.render.bake.margin = 4
    sc.render.bake.use_clear = True
    sky_world()
    bpy.context.scene.world.light_settings.distance = ao_dist
    lamps = add_lamps(kit_lights)
    select_only(obj)
    out = {}
    for kind in ('pos', 'nrm', 'id', 'axis', 'ao', 'light'):
        img = bpy.data.images.new('bake_' + kind, size, size, alpha=True, float_buffer=True)
        img.generated_color = (0, 0, 0, 0)
        setup_pass(obj, kind, img, slots, glow, kit_lights)
        t = time.time()
        if kind in ('pos', 'nrm', 'axis'):
            sc.cycles.samples = 1
            bpy.ops.object.bake(type='EMIT')
        elif kind == 'id':
            sc.cycles.samples = 4
            bpy.ops.object.bake(type='EMIT')
        elif kind == 'ao':
            sc.cycles.samples = max(16, samples // 2)
            bpy.ops.object.bake(type='AO')
        else:
            sc.cycles.samples = samples
            bpy.ops.object.bake(type='DIFFUSE', pass_filter={'DIRECT', 'INDIRECT'})
        a = np.empty(size * size * 4, np.float32)
        img.pixels.foreach_get(a)
        out[kind] = a.reshape(size, size, 4)
        log(f'{kind} {time.time() - t:.1f}s')
        bpy.data.images.remove(img)
    for lo in lamps:
        bpy.data.objects.remove(lo)
    # mask: texels the emit bake wrote (slot channel is never 0 there)
    out['mask'] = out['id'][..., 1] > (0.25 / 64.0)
    return out
