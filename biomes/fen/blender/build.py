"""Build, bake, paint and export fen assets.

usage: python build.py OUTDIR --only house_small,tree_a [--size 2048] [--samples 32] [--geom] [--repaint]
  --geom     stop after modelling and render a quick preview (no bake)
  --repaint  reuse OUTDIR/<name>_bake.npz and OUTDIR/<name>.blend, only paint and export
"""
import argparse, json, math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bpy
from mathutils import Vector
import kit, painter

ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('--only', default='')
ap.add_argument('--size', type=int, default=0)
ap.add_argument('--samples', type=int, default=32)
ap.add_argument('--seed', default='ambermere')
ap.add_argument('--geom', action='store_true')
ap.add_argument('--repaint', action='store_true')
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)


def reg():
    import house, flora, props
    A = {}
    for v in ('small', 'medium', 'tall'):
        A['house_' + v] = dict(fn=lambda v=v: house.build(v, args.seed), size=4096, cfg=dict(soot=True, ground=0.0, house=True),
                               house=True, split=('shingle', 'lath', 'rafter', 'crown', 'cap', 'wallhead'))
    A.update(flora.ASSETS)
    A.update(props.ASSETS)
    return A


def preview(objs, path, size=800, inside=None):
    """Cycles preview coloured by material slot (no GL here)."""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 24
    sc.cycles.use_denoising = False
    sc.render.resolution_x = sc.render.resolution_y = size
    kit.sky_world()
    mat = bpy.data.materials.new('slotcol')
    mat.use_nodes = True
    nt = mat.node_tree
    at = nt.nodes.new('ShaderNodeAttribute')
    at.attribute_name = 'slot'
    mul = nt.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    mul.inputs[1].default_value = 0.137
    fr = nt.nodes.new('ShaderNodeMath')
    fr.operation = 'FRACT'
    hsv = nt.nodes.new('ShaderNodeCombineColor')
    hsv.mode = 'HSV'
    hsv.inputs[1].default_value = 0.45
    hsv.inputs[2].default_value = 0.8
    nt.links.new(at.outputs['Fac'], mul.inputs[0])
    nt.links.new(mul.outputs[0], fr.inputs[0])
    nt.links.new(fr.outputs[0], hsv.inputs[0])
    nt.links.new(hsv.outputs[0], nt.nodes['Principled BSDF'].inputs['Base Color'])
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(mat)
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    ctr, rad = (lo + hi) / 2, (hi - lo).length / 2
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    sc.collection.objects.link(cam)
    sc.camera = cam
    shots = [('', ctr + Vector((0.55, -1.6, 0.75)).normalized() * rad * 2.0, ctr)]
    if inside:
        shots += [(f'_in{i}', Vector(p), Vector(t)) for i, (p, t) in enumerate(inside)]
    for suf, loc, tgt in shots:
        cam.location = loc
        cam.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler()
        cam.data.lens = 40 if not suf else 18
        sc.render.filepath = path.replace('.png', suf + '.png')
        if suf:
            sc.cycles.samples = 16
            sc.render.resolution_x = sc.render.resolution_y = 520
        bpy.ops.render.render(write_still=True)


def run(name, spec):
    t0 = time.time()
    base = os.path.join(args.out, name)
    size = args.size or spec.get('size', 2048)
    cfg = dict(spec.get('cfg', {}))
    if args.repaint:
        bpy.ops.wm.open_mainfile(filepath=base + '.blend')
        ob = bpy.data.objects[name]
        cards = [o for o in bpy.data.objects if o.name.startswith(name + '_cards')]
        bk = dict(np.load(base + '_bake.npz'))
        meta = json.load(open(base + '.json'))
    else:
        kit.clear_scene()
        res = spec['fn']()
        R, meta, extra = res if len(res) == 3 else (*res, None)
        ob = kit.to_object(R, name)
        cards = []
        if isinstance(extra, dict) and extra.get('cards'):
            cards = [extra['cards'](name)]
        meta['tris'] = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        meta['parts'] = len(R.parts)
        meta['centres'] = R.centres
        print(name, 'triangles', meta['tris'], 'parts', len(R.parts))
        if args.geom:
            preview([ob] + cards, base + '_geom.png', inside=meta.get('views'))
            return
        kit.unwrap(ob, margin=3.0 / size * 2)
        kit.sky_world()
        for co in cards:      # crowns shade the wood under them by half, not fully
            cm = bpy.data.materials.new('card_bake')
            cm.use_nodes = True
            nt = cm.node_tree
            nt.nodes.clear()
            o_ = nt.nodes.new('ShaderNodeOutputMaterial')
            mx = nt.nodes.new('ShaderNodeMixShader')
            mx.inputs[0].default_value = 0.5
            nt.links.new(nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0], mx.inputs[1])
            nt.links.new(nt.nodes.new('ShaderNodeBsdfDiffuse').outputs[0], mx.inputs[2])
            nt.links.new(mx.outputs[0], o_.inputs['Surface'])
            co.data.materials.append(cm)
        hearths = [(tuple(extra), 260.0)] if spec.get('house') and extra is not None else ()
        tb = time.time()
        bk = kit.bake(ob, size, samples=args.samples, hearths=hearths, light_size=size)
        print(name, 'bake', round(time.time() - tb, 1), 's')
        np.savez_compressed(base + '_bake.npz', **bk)
        json.dump(meta, open(base + '.json', 'w'))
        bpy.ops.wm.save_as_mainfile(filepath=base + '.blend')
    if spec.get('house'):
        cfg.update(hx=meta['hearth'][0], hy=meta['hearth'][1], rin=meta['Rw'] + 0.05, soot_z0=meta['deck'] + 1.4,
                   soot_z1=meta['apex'] - 0.4)
    cfg['centres'] = meta.get('centres', [])
    img = painter.paint(bk, cfg)
    painter.save_png(img, base + '_atlas.png')
    for o in cards:
        if spec.get('card_png'):
            spec['card_png'](base + '_cards.png')
    objs = kit.finish(ob, base + '_atlas.png', split=spec.get('split'))
    if cards and spec.get('card_finish'):
        spec['card_finish'](cards[0], base + '_cards.png')
    kit.export_glb(base + '.glb', objs + cards)
    sw = {'atlas': base + '_atlas.png'}
    if cards:
        sw['cards'] = base + '_cards.png'
    kit.glb_swap_images(base + '.glb', sw)
    print(name, 'done', round(time.time() - t0, 1), 's', os.path.getsize(base + '.glb') // 1024, 'KB')


A = reg()
names = [n for n in args.only.split(',') if n] or list(A)
for n in names:
    run(n, A[n])
