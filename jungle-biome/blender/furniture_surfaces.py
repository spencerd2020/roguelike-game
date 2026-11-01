"""Measure the shared furniture for the page: the surfaces props can stand on (table tops, every shelf board) and the
solid boxes the walker and the loose props collide with. Rays are cast straight down through each model; every upward
face a ray meets is a surface, and heights that repeat across the footprint are boards.

usage: python furniture_surfaces.py <props glb dir> <out json>      (three.js axes: y up, the front faces +z)
"""
import sys, json, os
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

src, out = sys.argv[sys.argv.index('--') + 1:][:2] if '--' in sys.argv else sys.argv[1:3]
IDS = ['bed', 'table', 'side_table', 'chair', 'stool', 'bench', 'shelf', 'bookshelf', 'cupboard', 'wardrobe', 'drawers', 'desk',
       'peg_rack', 'bottle_rack', 'chest', 'trunk', 'barrel', 'keg', 'crate', 'crate_open', 'strongbox', 'firewood_stack', 'wash_tub']
OPEN = {'shelf', 'bookshelf', 'bottle_rack', 'desk'}
res = {}
for fid in IDS:
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    p = os.path.join(src, fid + '.glb')
    if not os.path.exists(p):
        continue
    bpy.ops.import_scene.gltf(filepath=p)
    tris, verts = [], []
    for o in bpy.data.objects:
        if o.type != 'MESH':
            continue
        me = o.data
        mw = o.matrix_world
        base = len(verts)
        verts += [mw @ v.co for v in me.vertices]
        me.calc_loop_triangles()
        tris += [tuple(base + i for i in t.vertices) for t in me.loop_triangles]
    bvh = BVHTree.FromPolygons(verts, tris)
    mn = Vector([min(v[i] for v in verts) for i in range(3)])
    mx = Vector([max(v[i] for v in verts) for i in range(3)])
    # Blender axes here: x width, y depth (front at -y), z up
    levels = {}
    nx, ny = 9, 5
    for i in range(nx):
        for j in range(ny):
            x = mn.x + (mx.x - mn.x) * (i + 0.5) / nx
            y = mn.y + (mx.y - mn.y) * (j + 0.5) / ny
            z = mx.z + 0.5
            while True:
                hit = bvh.ray_cast(Vector((x, y, z)), Vector((0, 0, -1)), 5)
                if hit[0] is None:
                    break
                loc, nrm = hit[0], hit[1]
                if nrm.z > 0.8 and loc.z > mn.z + 0.15:
                    key = round(loc.z / 0.03)
                    levels.setdefault(key, []).append((x, y, loc.z))
                z = loc.z - 0.004
    surfaces = []
    for key, pts in sorted(levels.items()):
        if len(pts) < 6:          # a board covers a good part of the footprint, a rim or knob does not
            continue
        xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
        w = max(xs) - min(xs) + (mx.x - mn.x) / nx * 0.6
        d = max(ys) - min(ys) + (mx.y - mn.y) / ny * 0.6
        z = max(zs)
        # merge with a level just under it (a top board's two faces)
        if surfaces and abs(surfaces[-1]['y'] - z) < 0.06:
            surfaces[-1]['y'] = max(surfaces[-1]['y'], z)
            continue
        surfaces.append({'y': round(z - mn.z, 3), 'cx': round((max(xs) + min(xs)) / 2, 3), 'cz': round(-(max(ys) + min(ys)) / 2, 3),
                         'w': round(w, 3), 'd': round(d, 3)})
    W, D, H = mx.x - mn.x, mx.y - mn.y, mx.z - mn.z
    cx, cy = (mx.x + mn.x) / 2, (mx.y + mn.y) / 2
    # boxes: three.js [cx, cy, cz, sx, sy, sz] relative to the model origin with the base at y = 0
    if fid in OPEN:
        boxes = [[cx - W / 2 + 0.02, H / 2, -cy, 0.04, H, D], [cx + W / 2 - 0.02, H / 2, -cy, 0.04, H, D],
                 [cx, H / 2, -(mx.y - 0.02), W, H, 0.04]]                       # two sides and the back (+y is the back)
        for s in surfaces:
            boxes.append([s['cx'], s['y'] - 0.015, s['cz'], s['w'], 0.03, s['d']])
        if fid == 'desk':
            top = max((s for s in surfaces if s['y'] < 0.9), key=lambda s: s['y'], default=None)
            if top:
                boxes = [[cx, top['y'] / 2, -cy, W, top['y'], D]] + [b for b in boxes[3:] if b[1] > top['y']]
    else:
        boxes = [[cx, H / 2, -cy, W, H, D]]
    res[fid] = {'size': [round(W, 3), round(H, 3), round(D, 3)], 'origin_off': [round(-cx, 3), round(-mn.z, 3), round(cy, 3)],
                'surfaces': surfaces, 'boxes': [[round(v, 3) for v in b] for b in boxes]}
    print(fid, len(surfaces), [s['y'] for s in surfaces])
json.dump(res, open(out, 'w'), indent=1)
