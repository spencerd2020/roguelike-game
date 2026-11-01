"""Retexture the shared household props for the savanna, without touching their shapes.

Every shared prop keeps its own mesh, UVs and painted relief. Only the colours change: each texel of the base-colour
sheet is sorted into a family by hue (warm wood or fired clay, cool dye, madder red, green, straw yellow, neutral) and
moved onto the matching savanna ramp at the same lightness, with the same 4x4 ordered dither the kit's painter uses.
The glow (emissive) sheet is kept as it is.

usage: python retex_props.py SRC_DIR OUT_DIR [names...]      (SRC_DIR holds the shared <name>.glb files)
"""
import io, json, struct, sys, os, colorsys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
from savanna_paint import RAMPS as KR

hexrgb = lambda h: [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
R = {k: np.asarray(v, np.float32) for k, v in KR.items()}
# sun-bleached acacia: the kit's wood ramp, carried up two steps for planed furniture boards
R['acacia'] = np.concatenate([KR['wood'], np.asarray([hexrgb('#b08656'), hexrgb('#c6a06c')], np.float32)])
R['straw'] = np.concatenate([np.asarray([hexrgb('#1f170c'), hexrgb('#2c2110')], np.float32), KR['thatch']])   # weave shadows
R['indigo'] = KR['cloth'][[0, 1, 2, 6]]
R['madder'] = np.concatenate([np.asarray([hexrgb('#2e1712'), hexrgb('#4a2016'), hexrgb('#6a2c1e')], np.float32), KR['cloth'][[3, 4, 5, 6]]])  # dyed darks first

# per prop: which savanna ramp each colour family goes to
WOOD = dict(warm='acacia', cool='indigo', red='madder', green='leaf', yellow='grain', neutral='stone')
CLAY = dict(warm='clay', cool='indigo', red='clay', green='pod', yellow='grain', neutral='lime')
CLOTH = dict(warm='madder', cool='indigo', red='madder', green='indigo', yellow='grain', neutral='lime')
PROPS = {
    'bed': WOOD, 'bench': WOOD, 'stool': WOOD, 'table': WOOD, 'shelf': WOOD, 'chest': WOOD, 'peg_rack': WOOD,
    'firewood_stack': dict(WOOD, warm='wood', neutral='bark'), 'wooden_bowl': WOOD,
    'storage_jar': CLAY, 'urn': CLAY, 'jug': CLAY, 'clay_cup': CLAY,
    'cauldron': dict(WOOD, neutral='ash'),
    'bed_blanket': CLOTH, 'bed_pillow': CLOTH, 'rug_round': CLOTH, 'wall_hanging': CLOTH,
    'sack': dict(CLOTH, warm='rope', neutral='rope', yellow='grain'), 'basket': dict(WOOD, warm='straw', yellow='straw'),
    'hanging_herbs': dict(WOOD, warm='rope', green='leaf', yellow='grain'),
}
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) + 0.5) / 16 - 0.5
lum = lambda c: c @ np.array([0.299, 0.587, 0.114], np.float32)


def remap(rgb, fam):
    H, W, _ = rgb.shape
    flat = rgb.reshape(-1, 3)
    mx, mn = flat.max(1), flat.min(1)
    s = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
    r, g, b = flat.T
    d = np.maximum(mx - mn, 1e-5)
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    L = lum(flat)
    kind = np.full(len(flat), 'neutral', object)
    col = s > 0.16
    kind[col & ((h < 14) | (h >= 330)) & (s > 0.45)] = 'red'
    kind[col & (h >= 14) & (h < 42)] = 'warm'
    kind[col & ((h < 14) | (h >= 330)) & (s <= 0.45)] = 'warm'
    kind[col & (h >= 42) & (h < 68)] = 'yellow'
    kind[col & (h >= 68) & (h < 170)] = 'green'
    kind[col & (h >= 170) & (h < 330)] = 'cool'
    bay = np.tile(BAYER, (H // 4 + 1, W // 4 + 1))[:H, :W].ravel()
    out = np.zeros_like(flat)
    for k in ('neutral', 'red', 'warm', 'yellow', 'green', 'cool'):
        m = kind == k
        if not m.any():
            continue
        ramp = R[fam[k]]
        rl = lum(ramp)
        # place each texel on the ramp by lightness: fractional index between the two swatches around it, then dither
        x = np.interp(L[m], rl, np.arange(len(ramp), dtype=np.float32))
        idx = np.clip(np.round(x + bay[m] * 0.9), 0, len(ramp) - 1).astype(int)
        out[m] = ramp[idx]
    return out.reshape(H, W, 3)


def read_glb(path):
    b = open(path, 'rb').read()
    off, js, bin_ = 12, None, b''
    while off < len(b):
        ln, typ = struct.unpack_from('<II', b, off)
        if typ == 0x4E4F534A: js = json.loads(b[off + 8: off + 8 + ln])
        elif typ == 0x004E4942: bin_ = b[off + 8: off + 8 + ln]
        off += 8 + ln
    return js, bin_


def write_glb(path, js, views):
    """views: the bytes of each bufferView, in order. Packs them into one buffer, 4-byte aligned."""
    blob = bytearray()
    for i, v in enumerate(views):
        while len(blob) % 4: blob += b'\0'
        js['bufferViews'][i]['byteOffset'] = len(blob)
        js['bufferViews'][i]['byteLength'] = len(v)
        blob += v
    while len(blob) % 4: blob += b'\0'
    js['buffers'] = [{'byteLength': len(blob)}]
    j = json.dumps(js, separators=(',', ':')).encode()
    while len(j) % 4: j += b' '
    out = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(j) + 8 + len(blob)) + struct.pack('<II', len(j), 0x4E4F534A) + j \
        + struct.pack('<II', len(blob), 0x004E4942) + bytes(blob)
    open(path, 'wb').write(out)


def retex(src, dst, name):
    js, bin_ = read_glb(src)
    views = [bin_[v.get('byteOffset', 0): v.get('byteOffset', 0) + v['byteLength']] for v in js['bufferViews']]
    done = set()
    for mat in js['materials']:
        t = mat.get('pbrMetallicRoughness', {}).get('baseColorTexture')
        if not t: continue
        img = js['images'][js['textures'][t['index']]['source']]
        if id(img) in done: continue
        done.add(id(img))
        im = Image.open(io.BytesIO(views[img['bufferView']])).convert('RGB')
        rgb = np.asarray(im, np.float32) / 255
        new = (remap(rgb, PROPS[name]) * 255 + 0.5).astype(np.uint8)
        bio = io.BytesIO(); Image.fromarray(new).save(bio, 'PNG', optimize=True)
        views[img['bufferView']] = bio.getvalue()
        img['mimeType'] = 'image/png'
        Image.fromarray(np.concatenate([(rgb * 255).astype(np.uint8), new], 1)).save(dst[:-4] + '_compare.png')
    js.setdefault('asset', {})['extras'] = {'retexture': 'savanna palette remap of the shared prop; mesh and UVs unchanged'}
    write_glb(dst, js, views)


if __name__ == '__main__':
    src, out = sys.argv[1], sys.argv[2]
    names = sys.argv[3:] or list(PROPS)
    os.makedirs(out, exist_ok=True)
    for n in names:
        retex(os.path.join(src, n + '.glb'), os.path.join(out, n + '.glb'), n)
        print('retextured', n, os.path.getsize(os.path.join(out, n + '.glb')))
