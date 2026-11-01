"""Bake the Vanehold ground's light with everything standing on it (Cycles, Blender 5.x).
Imports the baked asset models, places them from the layout, bakes AO and sky-plus-sun diffuse light onto a top-down
UV of the terrain, and writes light.jpg (R light, G occlusion)."""
import math
import os
import time

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector
from PIL import Image

import bake as B
from terrain import N, SIZE_M


def terrain_object(h):
    lin = np.linspace(-SIZE_M / 2, SIZE_M / 2, N)
    X, Y = np.meshgrid(lin, lin)
    verts = np.stack([X.ravel(), Y.ravel(), h.ravel()], 1).astype(np.float32)
    i = np.arange(N - 1)
    a = (i[:, None] * N + i[None, :]).ravel()
    quads = np.stack([a, a + 1, a + N + 1, a + N], 1)
    me = bpy.data.meshes.new('ground')
    me.vertices.add(len(verts))
    me.vertices.foreach_set('co', verts.ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set('vertex_index', quads.ravel().astype(np.int32))
    me.polygons.add(len(quads))
    me.polygons.foreach_set('loop_start', np.arange(0, quads.size, 4, dtype=np.int32))
    me.polygons.foreach_set('loop_total', np.full(len(quads), 4, np.int32))
    me.update(calc_edges=True)
    uv = me.uv_layers.new(name='uv')
    co = verts[quads.ravel()]
    uvs = np.stack([(co[:, 0] + SIZE_M / 2) / SIZE_M, (co[:, 1] + SIZE_M / 2) / SIZE_M], 1)
    uv.data.foreach_set('uv', uvs.astype(np.float32).ravel())
    ob = bpy.data.objects.new('ground', me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def import_asset(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        o.hide_render = True        # templates; instances are linked copies
    return {o.name: o for o in new}


def instance(src, x, y, z, rot, s=1.0, with_children=True):
    o = src.copy()
    bpy.context.scene.collection.objects.link(o)
    o.parent = None
    o.hide_render = False
    o.matrix_world = Matrix.Translation((x, y, z)) @ Matrix.Rotation(rot, 4, 'Z') @ Matrix.Scale(s, 4)
    if with_children:
        for c in src.children:
            cc = c.copy()
            bpy.context.scene.collection.objects.link(cc)
            cc.hide_render = False
            cc.parent = o
            cc.matrix_parent_inverse = Matrix.Identity(4)
            cc.matrix_basis = c.matrix_basis.copy()
    return o


def bake(out, assets, h, L, size, samples):
    t0 = time.time()
    g = terrain_object(h)
    lib = {}
    for hv in {x['variant'] for x in L['houses']}:
        lib['house_' + hv] = import_asset(os.path.join(assets, f'house_{hv}.glb'))
    lib['tower'] = import_asset(os.path.join(assets, 'tower_windwatch.glb'))
    for pv in {x['variant'] for x in L['pines']}:
        lib['pine_' + pv] = import_asset(os.path.join(assets, f'pine_{pv}.glb'))
    lib['props'] = import_asset(os.path.join(assets, 'props.glb'))

    def root(d, name):
        o = d.get(name)
        if o is None:
            o = [v for v in d.values() if v.parent is None and v.type == 'MESH'][0]
        return o
    for x in L['houses']:
        instance(root(lib['house_' + x['variant']], 'house_' + x['variant']), x['x'], x['y'], x['z'], x['rot'])
    tw = L['tower']
    instance(root(lib['tower'], 'tower_windwatch'), tw['x'], tw['y'], tw['z'], tw['rot'])
    for x in L['pines']:
        instance(root(lib['pine_' + x['variant']], 'pine_' + x['variant']), x['x'], x['y'], x['z'], x['rot'], x['s'])
    pr = lib['props']
    for x in L['props'] + L['stairs']:
        k = 'props' if x['kind'] == 'boulder0' else x['kind']
        src = pr.get(k)
        if src is None:
            continue
        instance(src, x['x'], x['y'], x['z'], x['rot'], x['s'], with_children=(k == 'windpost'))
    b = L['bridge']
    instance(pr['bridge'], b['x'], b['y'], b['z'], math.pi / 2, 1.0, False)
    print(f'[tbake] scene ready {time.time() - t0:.1f}s', flush=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.render.bake.margin = 2
    B.sky_world(sun_dir=(0.35, -0.45, 1.0), sun=3.0)
    sc.world.light_settings.distance = 6.0
    mat = bpy.data.materials.new('ground_bake')
    g.data.materials.append(mat)
    res = {}
    for kind in ('ao', 'light'):
        img = bpy.data.images.new('tb_' + kind, size, size, float_buffer=True)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        o = nt.nodes.new('ShaderNodeOutputMaterial')
        d = nt.nodes.new('ShaderNodeBsdfDiffuse')
        d.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1)
        nt.links.new(d.outputs[0], o.inputs['Surface'])
        tx = nt.nodes.new('ShaderNodeTexImage')
        tx.image = img
        nt.nodes.active = tx
        B.select_only(g)
        t = time.time()
        if kind == 'ao':
            sc.cycles.samples = samples
            bpy.ops.object.bake(type='AO')
        else:
            sc.cycles.samples = samples
            bpy.ops.object.bake(type='DIFFUSE', pass_filter={'DIRECT', 'INDIRECT'})
        a = np.empty(size * size * 4, np.float32)
        img.pixels.foreach_get(a)
        res[kind] = a.reshape(size, size, 4)
        print(f'[tbake] {kind} {time.time() - t:.1f}s', flush=True)
    L_ = res['light'][..., :3] @ np.array([0.3, 0.59, 0.11], np.float32)
    ref = np.percentile(L_, 97)
    l8 = np.clip((L_ / ref) ** 0.8, 0, 1) * 255
    ao8 = np.clip(res['ao'][..., 0], 0, 1) * 255
    rgb = np.stack([l8, ao8, np.zeros_like(l8)], -1).astype(np.uint8)
    Image.fromarray(rgb[::-1]).save(os.path.join(out, 'light.jpg'), quality=90)
    print(f'[tbake] wrote light.jpg {time.time() - t0:.1f}s', flush=True)
