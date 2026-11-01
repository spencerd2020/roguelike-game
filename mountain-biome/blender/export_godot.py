"""Export Vanehold Pass for the Godot game (spencerd2020/trading-game, assets/mountain/).

- The baked models as .glb with each atlas swapped for an exact indexed-colour PNG (every texel is a swatch, about half
  the size); meshes untouched.
- vanehold_plans.json: one room plan per house variant in the format HouseDresser.dress() reads (house-local glTF
  coordinates, y up): the shared furniture by id at the marks the house was baked with, the hearth fire and the lamps,
  the floor, hearth and door spots for loose things, and the room size. The furniture is never in the house mesh.
  The moot hall gets one too (its three hearth fires), and each plan has the chimney top for the smoke.
- The town kit (retaining walls, aqueduct, cistern, crane, hoist, chopping blocks, wall stairs, quarry blocks).
- seeds/<seed>/terrain.json, ground.png and light.jpg for each town seed, as the web page uses them; seeds.json lists them.

usage: python blender/export_godot.py --assets OUT --terrain vanehold=DIR [--terrain skarrow=DIR ...] --dest .../trading-game/assets/mountain
"""
import argparse
import io
import json
import os
import shutil
import sys

import bpy  # noqa: F401  (bpy first: it makes bmesh and mathutils importable)
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, 'assets')]
import hall  # noqa: E402
import house  # noqa: E402
from retexture import pack, read_glb, write_glb  # noqa: E402

SEEDS = ('brannoch', 'tessaly', 'orrow')
HALLS = ('moothall',)


def g(x, y, z):
    """Blender (z up) -> glTF (y up)."""
    return [round(x, 4), round(z, 4), round(-y, 4)]


def plan(seed, mod=house):
    _, K, ctx = mod.build(seed)
    K.bm.free()
    M = K.markers
    furn = [[f['kind'], *g(f['x'], f['y'], f['z']), round(f['rot'], 4)] for f in ctx['furniture']]
    lights = [['fire', *g(*hz)] for hz in M.get('hearths', [M['hearth']])]
    for f in ctx['furniture']:
        if f['kind'] == 'lantern':
            lights.append(['lamp', *g(f['x'], f['y'], f['z'] + 0.17)])
        if f['kind'] == 'candlestick':
            lights.append(['candle', *g(f['x'], f['y'], f['z'] + 0.3)])
    slots = [[s[0], *g(s[1], s[2], s[3]), s[4], s[5], s[6]] for s in M['slots']]
    R = M['room']
    return {'furn': furn, 'lights': lights, 'slots': slots, 'cols': [],
            'room': [round(max(R['L'], R['W']) / 2 - R['t'], 3), round(R['L'] / R['W'], 3), round(R['zt'] - R['zf'], 3), [round(R['zf'], 3)]],
            'door': g(*M['door']), 'smoke': g(*M['smoke']), 'inner': [round(R['L'] / 2 - R['t'], 3), round(R['W'] / 2 - R['t'], 3)]}


def indexed_glb(src, dst):
    j, views = read_glb(src)
    for img in j.get('images', []):
        a = np.asarray(Image.open(io.BytesIO(views[img['bufferView']])).convert('RGB'))
        cols, inv = np.unique(a.reshape(-1, 3), axis=0, return_inverse=True)
        if len(cols) > 256:
            continue
        q = Image.fromarray(inv.reshape(a.shape[:2]).astype(np.uint8), 'P')
        q.putpalette(cols.astype(np.uint8).ravel().tolist())
        bio = io.BytesIO()
        q.save(bio, 'PNG', optimize=True)
        views[img['bufferView']] = bio.getvalue()
        img['mimeType'] = 'image/png'
    data = pack(j, views)
    write_glb(j, data, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--assets', required=True)
    ap.add_argument('--terrain', required=True, action='append', help='SEED=DIR, once per town seed; the first is the default')
    ap.add_argument('--dest', required=True)
    a = ap.parse_args()
    os.makedirs(a.dest, exist_ok=True)
    names = [f'house_{s}' for s in SEEDS] + [f'hall_{s}' for s in HALLS] + ['townkit', 'tower_windwatch', 'props', 'pine_cirr', 'pine_hask', 'pine_ollum']
    for n in names:
        out = 'vanehold_props' if n == 'props' else n
        indexed_glb(os.path.join(a.assets, n + '.glb'), os.path.join(a.dest, out + '.glb'))
        print(f'[godot] {out}.glb {os.path.getsize(os.path.join(a.dest, out + ".glb")) / 1e6:.2f} MB', flush=True)
    plans = {s: plan(s) for s in SEEDS}
    plans.update({s: plan(s, hall) for s in HALLS})
    json.dump(plans, open(os.path.join(a.dest, 'vanehold_plans.json'), 'w'), indent=1)
    seeds = []
    for spec in a.terrain:
        seed, d = spec.split('=', 1) if '=' in spec else ('vanehold', spec)
        sd = os.path.join(a.dest, 'seeds', seed)
        os.makedirs(sd, exist_ok=True)
        for f in ('terrain.json', 'ground.png', 'light.jpg'):
            shutil.copy(os.path.join(d, f), os.path.join(sd, f))
        seeds.append(seed)
    json.dump(seeds, open(os.path.join(a.dest, 'seeds.json'), 'w'))
    print('[godot] plans and terrain written', flush=True)


if __name__ == '__main__':
    main()
