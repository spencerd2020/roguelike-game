"""Retexture the shared props (props thread) for the jungle: same models, same UVs, new paint.

Every texel of a prop's sheet is sorted by what it shows and moved onto a jungle ramp by its lightness, then dithered
onto the ramp's swatches, so the props read as painted in the same palette as the stilt houses:
  wood (browns)          -> honey bamboo and rattan for the light boards, dark ironwood for the frames
  red cloth              -> madder red          blue cloth -> indigo          undyed cloth -> hemp
  iron, glass, potions, food, coins: kept as they are (they are the same things in every biome)
The geometry is never touched: only the image inside each glb is replaced.

usage: python retexture_props.py <props/glb dir> <props.json> <out dir>
"""
import io, json, os, struct, sys
import numpy as np
from PIL import Image

src, info_path, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
INFO = json.load(open(info_path))
REMAP_GROUPS = {'furniture', 'furnishings', 'storage'}
KEEP_EXTRA = {'basket', 'sack', 'broom', 'hanging_herbs', 'firewood_stack'}      # already plant-made: a lighter touch

hexrgb = lambda h: [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
R = lambda cs: np.array([hexrgb(c) for c in cs], np.float32)
TEAK = R(['#1a130f', '#271c15', '#3a2a1d', '#4f3925', '#67492c', '#80603a', '#a07c48', '#bf9a5c', '#d6b675', '#e6cf96'])
MADDER = R(['#2a0c0a', '#4a1410', '#6b1d16', '#8e2a1d', '#b03c25', '#cf6036', '#e3a05a'])
INDIGO = R(['#0d1022', '#151c3a', '#1f2a52', '#2c3c6e', '#3f5389', '#6077a3', '#9fb0c8'])
HEMP = R(['#3b3324', '#574c36', '#776a4c', '#978964', '#b5a87f', '#cfc39b', '#e5dcbc'])
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16 - 0.5)


def remap(img, light_touch=False):
    a = np.asarray(img.convert('RGBA')).astype(np.float32) / 255.0
    rgb, alpha = a[..., :3], a[..., 3:]
    mx, mn = rgb.max(-1), rgb.min(-1)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    sat = np.where(mx > 1e-3, (mx - mn) / np.maximum(mx, 1e-3), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    d = np.maximum(mx - mn, 1e-5)
    hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    H, W = lum.shape
    yy, xx = np.mgrid[0:H, 0:W]
    bay = BAYER[yy & 3, xx & 3]
    # stretch the sheet's own lightness so a dark prop still uses the whole ramp
    lo, hi = np.percentile(lum, 3), np.percentile(lum, 97)
    v = np.clip((lum - lo) / max(hi - lo, 1e-3), 0, 1)
    out = rgb.copy()

    def put(mask, ramp, vv, lift=0.0):
        k = np.clip(np.round(np.clip(vv + lift, 0, 1) * (len(ramp) - 1) + bay * 0.6), 0, len(ramp) - 1).astype(int)
        out[mask] = ramp[k][mask]

    brown = (hue >= 8) & (hue <= 55) & (sat > 0.18) & (sat < 0.85)
    red = ((hue < 8) | (hue > 330)) & (sat > 0.35)
    blue = (hue > 190) & (hue < 270) & (sat > 0.2)
    undyed = (sat <= 0.18) & (lum > 0.35)
    if light_touch:
        put(brown, TEAK, v * 0.85 + 0.12)
    else:
        put(brown, TEAK, v * 0.95 + 0.08)
        put(red, MADDER, v)
        put(blue, INDIGO, v)
        put(undyed & ~brown, HEMP, v)
    res = np.concatenate([out, alpha], -1)
    return Image.fromarray((np.clip(res, 0, 1) * 255).astype(np.uint8), 'RGBA')


def rewrite(path, dst, light_touch):
    data = open(path, 'rb').read()
    jl = struct.unpack('<I', data[12:16])[0]
    j = json.loads(data[20:20 + jl])
    bin_off = 20 + jl + 8
    bl = struct.unpack('<I', data[20 + jl:24 + jl])[0]
    binb = data[bin_off:bin_off + bl]
    views = [binb[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']] for v in j['bufferViews']]
    for im in j.get('images', []):
        bv = im['bufferView']
        pil = Image.open(io.BytesIO(views[bv]))
        has_alpha = pil.mode in ('RGBA', 'LA') or 'transparency' in pil.info
        new = remap(pil, light_touch)
        buf = io.BytesIO()
        (new if has_alpha else new.convert('RGB')).save(buf, 'PNG', optimize=True)
        views[bv] = buf.getvalue()
        im['mimeType'] = 'image/png'
    blob = b''
    for i, v in enumerate(views):
        while len(blob) % 4:
            blob += b'\0'
        j['bufferViews'][i]['byteOffset'] = len(blob)
        j['bufferViews'][i]['byteLength'] = len(v)
        blob += v
    while len(blob) % 4:
        blob += b'\0'
    j['buffers'][0]['byteLength'] = len(blob)
    js = json.dumps(j, separators=(',', ':')).encode()
    while len(js) % 4:
        js += b' '
    total = 12 + 8 + len(js) + 8 + len(blob)
    with open(dst, 'wb') as f:
        f.write(struct.pack('<4sII', b'glTF', 2, total))
        f.write(struct.pack('<I4s', len(js), b'JSON') + js)
        f.write(struct.pack('<I4s', len(blob), b'BIN\0') + blob)


n = 0
for pid, meta in INFO.items():
    p = os.path.join(src, pid + '.glb')
    if not os.path.exists(p):
        continue
    dst = os.path.join(out, pid + '.glb')
    if meta['group'] in REMAP_GROUPS or pid in KEEP_EXTRA:
        rewrite(p, dst, pid in KEEP_EXTRA)
        n += 1
    else:
        open(dst, 'wb').write(open(p, 'rb').read())
print('retextured', n, 'of', len(INFO))
