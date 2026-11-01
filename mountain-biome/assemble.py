"""Gather the baked Vanehold Pass assets into one folder the page can load (web/assets by default).

usage: python assemble.py --assets OUT_DIR --terrain TERRAIN_DIR [--walker DIR_WITH_body.json_and_hair.json] [--furniture FUR_DIR] [--dest web/assets]
"""
import argparse
import glob
import json
import os
import shutil

ap = argparse.ArgumentParser()
ap.add_argument('--assets', required=True)
ap.add_argument('--terrain', required=True)
ap.add_argument('--walker', default='')
ap.add_argument('--furniture', default='', help='folder of fur_<name>.json from blender/retexture.py')
ap.add_argument('--dest', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'assets'))
a = ap.parse_args()
os.makedirs(a.dest, exist_ok=True)
T = json.load(open(os.path.join(a.terrain, 'terrain.json')))
doors, furniture = {}, {}
for m in glob.glob(os.path.join(a.assets, '*.meta.json')):
    meta = json.load(open(m))
    name = meta['name']
    if name.startswith('house_') and 'door' in meta.get('markers', {}):
        doors[name[len('house_'):]] = meta['markers']['door']
        furniture[name[len('house_'):]] = meta['markers'].get('furniture', [])
    shutil.copy(os.path.join(a.assets, name + '.json'), os.path.join(a.dest, name + '.json'))
T['doors'] = doors
T['furniture'] = furniture
for f in glob.glob(os.path.join(a.furniture, 'fur_*.json')) if a.furniture else []:
    shutil.copy(f, os.path.join(a.dest, os.path.basename(f)))
json.dump(T, open(os.path.join(a.dest, 'terrain.json'), 'w'))
for f in ('ground.png', 'light.jpg'):
    shutil.copy(os.path.join(a.terrain, f), os.path.join(a.dest, f))
for f in ('body.json', 'hair.json'):
    if a.walker and os.path.exists(os.path.join(a.walker, f)):
        shutil.copy(os.path.join(a.walker, f), os.path.join(a.dest, f))
for f in sorted(os.listdir(a.dest)):
    print(f'{os.path.getsize(os.path.join(a.dest, f)) / 1e6:7.2f} MB  {f}')
