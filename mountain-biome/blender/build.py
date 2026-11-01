"""Build one Vanehold Pass asset: generate, cull, unwrap, bake, paint, export.

usage: python build.py <asset> --seed S --out DIR [--size 4096] [--samples 48] [--repaint]
Outputs DIR/<name>.json (glTF, embedded), DIR/<name>_atlas.png, DIR/<name>_bake.npz, DIR/<name>.meta.json.
<asset> is a module in assets/ with build(seed) -> (name, Kit, ctx dict).
"""
import argparse
import importlib
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'assets'))

import bpy  # noqa: E402  (bpy first: it makes bmesh and mathutils importable)
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import bake  # noqa: E402
import paint  # noqa: E402


def export(obj, kit, rgb, path_png, out_path, pivots):
    from PIL import Image
    Image.fromarray(rgb[::-1]).save(path_png, optimize=True)
    img = bpy.data.images.load(path_png)
    img.name = os.path.basename(path_png)
    atlas = bpy.data.materials.new('atlas')
    atlas.use_nodes = True
    nt = atlas.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    tex.interpolation = 'Closest'
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 1.0
    mats, remap = [atlas], {}
    for si, s in enumerate(kit.slots):
        if s in kit.glow:
            g = bpy.data.materials.new('glow_' + s)
            g.use_nodes = True
            b = g.node_tree.nodes.get('Principled BSDF')
            col = paint.RTAB[paint.RID['ember' if s == 'ember' else 'mica'], 0] / 255.0
            b.inputs['Base Color'].default_value = (*col, 1)
            b.inputs['Emission Color'].default_value = (*col, 1)
            b.inputs['Emission Strength'].default_value = 1.0
            remap[si] = len(mats)
            mats.append(g)
        else:
            remap[si] = 0
    me = obj.data
    idx = [remap[p.material_index] for p in me.polygons]
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    for p, i in zip(me.polygons, idx):
        p.material_index = i
    # split the separate nodes (cutaway roof, rotor) off the body, keeping their UVs on the shared atlas
    objs = [obj]
    attr = me.attributes.get('node')
    if attr is not None and len(kit.nodes) > 1:
        nodes = np.zeros(len(me.polygons), np.int32)
        attr.data.foreach_get('value', nodes)
        for ni in range(1, len(kit.nodes)):
            if not (nodes == ni).any():
                continue
            me2 = me.copy()
            o2 = bpy.data.objects.new(kit.nodes[ni], me2)
            bpy.context.scene.collection.objects.link(o2)
            bm = bmesh.new()
            bm.from_mesh(me2)
            lay = bm.faces.layers.int.get('node')
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] != ni], context='FACES')
            bm.to_mesh(me2)
            bm.free()
            piv = pivots.get(kit.nodes[ni])
            if piv is not None:
                me2.transform(__import__('mathutils').Matrix.Translation(-Vector(piv)))
                o2.location = piv
            o2.parent = obj
            objs.append(o2)
        bm = bmesh.new()
        bm.from_mesh(me)
        lay = bm.faces.layers.int.get('node')
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] != 0], context='FACES')
        bm.to_mesh(me)
        bm.free()
    # keep only what the viewer needs
    for o in objs:
        for nm in ('part', 'ax', 'ay', 'az', 'node'):
            a = o.data.attributes.get(nm)
            if a is not None:
                o.data.attributes.remove(a)
    for o in bpy.context.scene.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=out_path, export_format='GLB', use_selection=True, export_yup=True,
                              export_normals=True, export_texcoords=True, export_materials='EXPORT',
                              export_image_format='AUTO', export_extras=True, export_apply=False)


def _quantize(j, views):
    """KHR_mesh_quantization: positions and UVs as normalised 16-bit, normals dropped (the page shades flat from
    screen-space derivatives). Each mesh moves to a child node carrying the dequantising scale and offset, so the
    parent's own children (a roof, a rotor) keep their transforms. About a third of the float size."""
    acc = j['accessors']

    def read(ai):
        a = acc[ai]
        n = {'VEC3': 3, 'VEC2': 2, 'SCALAR': 1}[a['type']]
        return np.frombuffer(views[a['bufferView']], np.float32, a['count'] * n, a.get('byteOffset', 0)).reshape(a['count'], n)

    def add(arr, ctype, typ, normalized=True, mn=None, mx=None):
        views.append(arr.tobytes())
        j['bufferViews'].append({'buffer': 0, 'byteLength': 0})
        a = {'bufferView': len(j['bufferViews']) - 1, 'componentType': ctype, 'count': len(arr), 'type': typ, 'normalized': normalized}
        if mn is not None:
            a['min'], a['max'] = mn, mx
        acc.append(a)
        return len(acc) - 1
    done = {}
    for ni, node in enumerate(list(j['nodes'])):
        if 'mesh' not in node:
            continue
        mi = node.pop('mesh')
        if mi not in done:
            lo, hi = np.full(3, 1e9), np.full(3, -1e9)
            for p in j['meshes'][mi]['primitives']:
                P = read(p['attributes']['POSITION'])
                lo, hi = np.minimum(lo, P.min(0)), np.maximum(hi, P.max(0))
            rng = np.maximum(hi - lo, 1e-6)
            for p in j['meshes'][mi]['primitives']:
                at = p['attributes']
                P = read(at['POSITION'])
                q = np.round((P - lo) / rng * 65535).astype(np.uint16)
                at['POSITION'] = add(q, 5123, 'VEC3', True, [int(v) for v in q.min(0)], [int(v) for v in q.max(0)])
                if 'TEXCOORD_0' in at:
                    uv = np.clip(read(at['TEXCOORD_0']), 0, 1)
                    at['TEXCOORD_0'] = add(np.round(uv * 65535).astype(np.uint16), 5123, 'VEC2', True)
                at.pop('NORMAL', None)
            done[mi] = (lo, rng)
        lo, rng = done[mi]
        j['nodes'].append({'name': node.get('name', 'mesh') + '_q', 'mesh': mi,
                           'translation': [float(v) for v in lo], 'scale': [float(v) for v in rng]})
        node.setdefault('children', []).append(len(j['nodes']) - 1)
    j.setdefault('extensionsUsed', []).append('KHR_mesh_quantization')
    j.setdefault('extensionsRequired', []).append('KHR_mesh_quantization')
    # drop the accessors and views nothing points at any more
    ref = set()
    for m in j['meshes']:
        for p in m['primitives']:
            ref |= set(p['attributes'].values())
            if 'indices' in p:
                ref.add(p['indices'])
    used = {acc[i]['bufferView'] for i in ref} | {im['bufferView'] for im in j.get('images', []) if 'bufferView' in im}
    keep = [i for i in range(len(views)) if i in used]
    remap = {o: n for n, o in enumerate(keep)}
    keep_acc = []
    amap = {}
    for i, a in enumerate(acc):
        if i in ref:
            amap[i] = len(keep_acc)
            a['bufferView'] = remap[a['bufferView']]
            keep_acc.append(a)
    for m in j['meshes']:
        for p in m['primitives']:
            p['attributes'] = {k: amap[v] for k, v in p['attributes'].items()}
            if 'indices' in p:
                p['indices'] = amap[p['indices']]
    for im in j.get('images', []):
        if 'bufferView' in im:
            im['bufferView'] = remap[im['bufferView']]
    j['accessors'] = keep_acc
    j['bufferViews'] = [j['bufferViews'][i] for i in keep]
    views[:] = [views[i] for i in keep]


def glb_to_json(glb, out, atlas_png=None):
    """GLB -> one self-contained glTF JSON (the artifact host serves .json, not .glb). The atlas image is swapped for
    an indexed-colour PNG of the same pixels: every texel is a palette swatch, so nothing is lost and it is half the size."""
    import base64
    import io
    import struct
    from PIL import Image
    b = open(glb, 'rb').read()
    n = struct.unpack_from('<I', b, 12)[0]
    j = json.loads(b[20:20 + n])
    off = 20 + n
    bl = struct.unpack_from('<I', b, off)[0]
    binc = b[off + 8: off + 8 + bl]
    views = [binc[v.get('byteOffset', 0): v.get('byteOffset', 0) + v['byteLength']] for v in j['bufferViews']]
    if atlas_png:
        a = np.asarray(Image.open(atlas_png).convert('RGB'))
        cols, inv = np.unique(a.reshape(-1, 3), axis=0, return_inverse=True)
        if len(cols) <= 256:          # exact: build the palette from the swatches actually used
            q = Image.fromarray(inv.reshape(a.shape[:2]).astype(np.uint8), 'P')
            q.putpalette(cols.astype(np.uint8).ravel().tolist())
        else:
            q = Image.fromarray(a)
        bio = io.BytesIO()
        q.save(bio, 'PNG', optimize=True)
        for img in j.get('images', []):
            if 'bufferView' in img and img.get('name', '').endswith('_atlas') or 'atlas' in img.get('name', ''):
                views[img['bufferView']] = bio.getvalue()
                img['mimeType'] = 'image/png'
    _quantize(j, views)
    data = bytearray()
    for v, d in zip(j['bufferViews'], views):
        while len(data) % 4:
            data.append(0)
        v['byteOffset'] = len(data)
        v['byteLength'] = len(d)
        data += d
    j['buffers'][0]['byteLength'] = len(data)
    j['buffers'][0]['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(bytes(data)).decode()
    json.dump(j, open(out, 'w'), separators=(',', ':'))


def place_furniture(fur, src):
    """Stand the retextured shared furniture in the scene so the room's bake sees it (shadow, occlusion, bounce).
    It is not part of the baked mesh: the page places the same models at the same marks."""
    from mathutils import Matrix
    made, lib = [], {}
    for f in fur:
        if f['kind'] not in lib:
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=os.path.join(src, f"fur_{f['kind']}.glb"))
            lib[f['kind']] = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
            for o in lib[f['kind']]:
                o.hide_render = True
        for o in lib[f['kind']]:
            c = o.copy()
            bpy.context.scene.collection.objects.link(c)
            c.parent = None
            c.hide_render = False
            c.matrix_world = Matrix.Translation((f['x'], f['y'], f['z'])) @ Matrix.Rotation(f['rot'], 4, 'Z') @ o.matrix_world
            made.append(c)
    print(f'[build] furniture placed: {len(made)} pieces', flush=True)
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('asset')
    ap.add_argument('--seed', default='vanehold')
    ap.add_argument('--out', required=True)
    ap.add_argument('--size', type=int, default=2048)
    ap.add_argument('--samples', type=int, default=48)
    ap.add_argument('--repaint', action='store_true', help='reuse the saved bake, paint only')
    ap.add_argument('--geom', action='store_true', help='stop after the geometry (prints the triangle count)')
    ap.add_argument('--furniture', default='', help='folder of fur_<name>.glb from retexture.py (houses)')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.environ.setdefault('MB_TMP', a.out)
    t0 = time.time()
    mod = importlib.import_module(a.asset)
    npz = os.path.join(a.out, a.asset + '_' + a.seed + '_bake.npz')
    blend = npz.replace('_bake.npz', '_baked.blend')
    if a.repaint and os.path.exists(npz) and os.path.exists(blend):
        bpy.ops.wm.open_mainfile(filepath=blend)
        name, kit, ctx = mod.build(a.seed)        # deterministic: same slots, parts and paint context
        kit.bm.free()
        obj = bpy.data.objects[name]
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        B = {k: v.astype(np.float32) if v.dtype == np.float16 else v for k, v in dict(np.load(npz)).items()}
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        name, kit, ctx = mod.build(a.seed)
        obj = kit.to_object(name)
        bake.cull_hidden(obj)
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        print(f'[build] {name}: {tris} triangles, {len(kit.parts)} parts, {time.time() - t0:.1f}s', flush=True)
        if a.geom:
            return
        bake.unwrap(obj, a.size)
        if ctx.get('furniture'):
            if not a.furniture:
                raise SystemExit('this asset places shared furniture: pass --furniture DIR (run retexture.py first)')
            place_furniture(ctx['furniture'], a.furniture)
        B = bake.bake_all(obj, a.size, kit.slots, kit.glow, kit.lights, a.samples, ctx.get('ao_dist', 1.2))
        np.savez_compressed(npz, **{k: (v.astype(np.float16) if v.dtype == np.float32 and k not in ('pos', 'id') else v)
                                    for k, v in B.items()})
        bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    t = time.time()
    rgb, ref = paint.paint(B, a.size, kit.slots, kit.glow, ctx)
    print(f'[build] paint {time.time() - t:.1f}s', flush=True)
    png = os.path.join(a.out, name + '_atlas.png')
    glb = os.path.join(a.out, name + '.glb')
    export(obj, kit, rgb, png, glb, ctx.get('pivots', {}))
    glb_to_json(glb, os.path.join(a.out, name + '.json'), png)
    meta = {'name': name, 'seed': a.seed, 'tris': tris, 'parts': len(kit.parts), 'size': a.size,
            'nodes': kit.nodes, 'markers': kit.markers, 'footprint': ctx.get('footprint'),
            'seconds': round(time.time() - t0, 1)}
    json.dump(meta, open(os.path.join(a.out, name + '.meta.json'), 'w'), indent=1)
    print('[build] done', json.dumps(meta), flush=True)


if __name__ == '__main__':
    main()
