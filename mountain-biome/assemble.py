"""Gather the baked Vanehold Pass assets into one folder the page can load (web/assets by default).

usage: python assemble.py --assets OUT_DIR --terrain SEED=TERRAIN_DIR [--terrain SEED=DIR ...]
                          [--walker DIR_WITH_body.json_and_hair.json] [--furniture FUR_DIR] [--dest web/assets]

Each --terrain is one seeded town and its pass (terrain.py --seed SEED --out DIR); the first is the page's default.
They land in assets/seeds/<seed>/ beside the shared models, and assets/seeds.json lists them.
"""
import argparse
import glob
import json
import os
import shutil

ap = argparse.ArgumentParser()
ap.add_argument('--assets', required=True)
ap.add_argument('--terrain', required=True, action='append', help='SEED=DIR (or just DIR, seed vanehold)')
ap.add_argument('--walker', default='')
ap.add_argument('--furniture', default='', help='folder of fur_<name>.json from blender/retexture.py')
ap.add_argument('--dest', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'assets'))
a = ap.parse_args()
os.makedirs(a.dest, exist_ok=True)
# what each building was baked with: its door, hearth smoke and furniture marks
buildings = {}
for m in glob.glob(os.path.join(a.assets, '*.meta.json')):
    meta = json.load(open(m))
    name = meta['name']
    mk = meta.get('markers', {})
    if 'door' in mk:
        buildings[name] = {k: mk[k] for k in ('door', 'smoke', 'furniture', 'hearth') if k in mk}
    shutil.copy(os.path.join(a.assets, name + '.json'), os.path.join(a.dest, name + '.json'))
seeds = []
for spec in a.terrain:
    seed, d = spec.split('=', 1) if '=' in spec else ('vanehold', spec)
    sd = os.path.join(a.dest, 'seeds', seed)
    os.makedirs(sd, exist_ok=True)
    T = json.load(open(os.path.join(d, 'terrain.json')))
    T['seed'] = seed
    T['buildings'] = buildings
    # older names the page still reads
    T['doors'] = {k[len('house_'):]: v['door'] for k, v in buildings.items() if k.startswith('house_')}
    T['furniture'] = {k[len('house_'):]: v.get('furniture', []) for k, v in buildings.items() if k.startswith('house_')}
    json.dump(T, open(os.path.join(sd, 'terrain.json'), 'w'))
    for f in ('ground.png', 'light.jpg'):
        shutil.copy(os.path.join(d, f), os.path.join(sd, f))
    tn = T['layout'].get('town', {})
    seeds.append({'seed': seed, 'size': tn.get('size', ''), 'houses': len(T['layout']['houses'])})
json.dump(seeds, open(os.path.join(a.dest, 'seeds.json'), 'w'))
for f in glob.glob(os.path.join(a.furniture, 'fur_*.json')) if a.furniture else []:
    shutil.copy(f, os.path.join(a.dest, os.path.basename(f)))
for f in ('body.json', 'hair.json'):
    if a.walker and os.path.exists(os.path.join(a.walker, f)):
        shutil.copy(os.path.join(a.walker, f), os.path.join(a.dest, f))
for root, _, files in os.walk(a.dest):
    for f in sorted(files):
        p = os.path.join(root, f)
        print(f'{os.path.getsize(p) / 1e6:7.2f} MB  {os.path.relpath(p, a.dest)}')
