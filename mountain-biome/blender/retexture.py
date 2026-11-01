"""Retexture the shared household furniture for Vanehold Pass, without remodelling it.

Spencer's rule (1 Nov 2026): house interiors use the game's shared furniture models; a biome may retexture them to its
flavour but never change the mesh. This reads each shared .glb untouched (mesh, UVs and node kept byte for byte) and
repaints only its textures: every texel is sorted into a material by hue (timber, iron, straw and wool, red cloth, blue
cloth, brass, flame) and its brightness is carried onto the matching Vanehold palette ramp, then the ramp-constrained
error diffusion picks the swatch. Timber becomes the smoke-darkened honey larch of the house interiors, cloth the madder
and woad of the village, iron our blue-black iron. The painted light of the original stays.

usage: python retexture.py --src /mnt/project-files/props/glb --out OUT bed table bench ...
Writes OUT/fur_<name>.json (self-contained glTF, the page loads these) and OUT/fur_<name>.glb (for the light bake).
"""
import argparse
import base64
import colorsys
import ctypes
import io
import json
import os
import struct

import numpy as np
from PIL import Image

import paint as P

# brass has no ramp in the house palette; the furniture needs one
P.RAMPS.setdefault('brass', ['#3b2a12', '#5a4119', '#7d5d24', '#a07c33', '#c29d4a', '#dcbd6c'])
P.RNAMES = list(P.RAMPS)
P.RID = {k: i for i, k in enumerate(P.RNAMES)}
P.RLEN = np.array([len(P.RAMPS[k]) for k in P.RNAMES], np.int32)
P.RMAX = P.RLEN.max()
P.RTAB = np.zeros((len(P.RNAMES), P.RMAX, 3), np.uint8)
for _i, _k in enumerate(P.RNAMES):
    for _j, _hx in enumerate(P.RAMPS[_k]):
        P.RTAB[_i, _j] = P._hex(_hx)


def _lum(c):
    return c[..., 0] * 0.3 + c[..., 1] * 0.59 + c[..., 2] * 0.11


def classify(rgb):
    """rgb float 0..1 (H, W, 3) -> ramp id per texel and the source brightness."""
    hsv = np.vectorize(colorsys.rgb_to_hsv, otypes=[float, float, float])
    h, s, v = hsv(rgb[..., 0], rgb[..., 1], rgb[..., 2])
    hd = h * 360
    L = _lum(rgb)
    R = np.full(L.shape, P.RID['honey'], np.int32)                    # timber by default
    grey = s < 0.16
    R[grey] = P.RID['iron']
    R[grey & (L > 0.45)] = P.RID['wool']                              # pale linen, candle wax
    straw = (s >= 0.16) & (s < 0.5) & (hd > 30) & (hd < 65) & (L > 0.42)
    R[straw] = P.RID['wool']
    R[(L < 0.1) & (s < 0.35)] = P.RID['iron']                         # near-black: hue is noise there
    red = (s >= 0.45) & (L > 0.12) & ((hd < 16) | (hd > 330))
    R[red] = P.RID['madder']
    blue = (s >= 0.18) & (hd > 180) & (hd < 280)
    R[blue] = P.RID['woad']
    green = (s >= 0.2) & (hd >= 65) & (hd <= 180)
    R[green] = P.RID['lichen']
    brass = (s >= 0.45) & (hd > 32) & (hd < 60) & (L > 0.3) & (L < 0.75)
    R[brass] = P.RID['brass']
    flame = (L > 0.75) & (s > 0.3) & (hd > 20) & (hd < 60)
    R[flame] = P.RID['ember']
    return R, L


# how bright the top of each ramp is in the source's terms: source brightness / ref = place on the ramp
REF = {'honey': 0.5, 'iron': 0.42, 'wool': 0.95, 'madder': 0.6, 'woad': 0.6, 'lichen': 0.6, 'brass': 0.8, 'ember': 1.0}


def recolour(img, seed=0):
    a = np.asarray(img.convert('RGBA')).astype(np.float32) / 255
    rgb, alpha = a[..., :3], a[..., 3]
    R, L = classify(rgb)
    tt = np.zeros(L.shape, np.float32)
    for k, ref in REF.items():
        m = R == P.RID[k]
        tt[m] = np.clip(L[m] / ref, 0, 1) ** 0.9
    n = P.RLEN[R].astype(np.int32)
    tval = np.ascontiguousarray((tt * (n - 1)).astype(np.float32))
    o = np.zeros(L.shape, np.int32)
    h, w = L.shape
    P._dither().diffuse(tval.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), np.ascontiguousarray(n).ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
                        o.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), w, h, ctypes.c_float(0.8))
    out = P.RTAB[R, np.clip(o, 0, P.RMAX - 1)]
    black = L < 0.012                                   # padding and unlit emit texels stay black
    out[black] = 0
    return out, alpha


def indexed_png(rgb):
    cols, inv = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True)
    q = Image.fromarray(inv.reshape(rgb.shape[:2]).astype(np.uint8), 'P')
    q.putpalette(cols.astype(np.uint8).ravel().tolist())
    bio = io.BytesIO()
    q.save(bio, 'PNG', optimize=True)
    return bio.getvalue()


def read_glb(path):
    b = open(path, 'rb').read()
    n = struct.unpack_from('<I', b, 12)[0]
    j = json.loads(b[20:20 + n])
    off = 20 + n
    bl = struct.unpack_from('<I', b, off)[0]
    binc = b[off + 8: off + 8 + bl]
    views = [binc[v.get('byteOffset', 0): v.get('byteOffset', 0) + v['byteLength']] for v in j['bufferViews']]
    return j, views


def pack(j, views):
    data = bytearray()
    for v, d in zip(j['bufferViews'], views):
        while len(data) % 4:
            data.append(0)
        v['byteOffset'] = len(data)
        v['byteLength'] = len(d)
        data += d
    while len(data) % 4:
        data.append(0)
    j['buffers'] = [{'byteLength': len(data)}]
    return bytes(data)


def write_glb(j, data, path):
    js = json.dumps(j, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    out = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(data))
    out += struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(data), 0x004E4942) + data
    open(path, 'wb').write(out)


def retexture(src, out_dir, name):
    j, views = read_glb(os.path.join(src, name + '.glb'))
    mesh_bytes = sum(len(views[j['accessors'][a]['bufferView']]) for m in j['meshes'] for p in m['primitives']
                     for a in list(p['attributes'].values()) + [p['indices']])
    for img in j.get('images', []):
        im = Image.open(io.BytesIO(views[img['bufferView']]))
        rgb, _ = recolour(im)
        views[img['bufferView']] = indexed_png(rgb)
        img['mimeType'] = 'image/png'
    j['samplers'] = [{'magFilter': 9728, 'minFilter': 9984}]   # crisp pixels, like every Vanehold atlas
    for t in j.get('textures', []):
        t['sampler'] = 0
    j['meshes'][0]['name'] = name
    j['nodes'][j['scenes'][0]['nodes'][0]]['name'] = 'fur_' + name
    data = pack(j, views)
    write_glb(json.loads(json.dumps(j)), data, os.path.join(out_dir, f'fur_{name}.glb'))
    j['buffers'][0]['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(data).decode()
    json.dump(j, open(os.path.join(out_dir, f'fur_{name}.json'), 'w'), separators=(',', ':'))
    return mesh_bytes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='/mnt/project-files/props/glb')
    ap.add_argument('--out', required=True)
    ap.add_argument('names', nargs='+')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for nm in a.names:
        retexture(a.src, a.out, nm)
        print(f'[retexture] {nm}', flush=True)


if __name__ == '__main__':
    main()
