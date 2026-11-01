"""Vanehold Pass terrain: heightfield, layout, painted ground, and a Cycles light bake with every building, tree and
rock standing in it (so houses darken the turf round their feet and the crag shades the tarn).

usage: python terrain.py --assets ASSET_DIR --out DIR [--seed vanehold] [--size 4096] [--light 2048] [--nobake]
Writes DIR/terrain.json (heights, zones, layout), DIR/ground.png (painted albedo, top-down), DIR/light.jpg (baked light).

Map: 260 m square, x east, y north (Blender). The meadow shelf with the village sits in the middle; a range of banded
peaks closes the north, a glacial tarn lies east, a gorge with a stream cuts the west (a rope bridge crosses it), the
lookout tower stands on a terraced crag to the south-east, and the land falls away south to a sea of cloud.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'assets'))

SIZE_M = 260.0
N = 521                       # 0.5 m grid
STEP = SIZE_M / (N - 1)
WATER = 8.0
SHELF = 14.0
VILLAGE = (-8.0, 2.0)
TARN = (60.0, 26.0, 24.0)
CRAG = (26.0, -44.0)
BRIDGE_Y = -8.0
SNOW = 52.0


def sm(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _h2(ix, iy, seed):
    h = (ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263 + seed * 1442695041) & 0xffffffff
    h = ((h ^ (h >> 13)) * 1274126177) & 0xffffffff
    return ((h ^ (h >> 16)) & 0xffffffff) / 4294967295.0


def vn2(x, y, f, seed):
    qx, qy = x * f, y * f
    ix, iy = np.floor(qx), np.floor(qy)
    tx, ty = qx - ix, qy - iy
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a = _h2(ix, iy, seed); b = _h2(ix + 1, iy, seed); c = _h2(ix, iy + 1, seed); d = _h2(ix + 1, iy + 1, seed)
    return (a + (b - a) * tx + (c - a) * ty + (a - b - c + d) * tx * ty) * 2 - 1


def fbm2(x, y, f, seed, oct=5, gain=0.5):
    v, a, tot = 0, 1.0, 0
    for o in range(oct):
        v = v + a * vn2(x, y, f * 2 ** o, seed + 17 * o)
        tot += a
        a *= gain
    return v / tot


def gorge_x(y):
    return -58.0 + 6.0 * np.sin(y / 31.0) + 3.0 * np.sin(y / 13.0 + 1.0)


def path_points():
    """The walking path: across the bridge, through the village, round the tarn shore, to the crag stairs and back."""
    return [(-48.5, BRIDGE_Y), (-36, -6), (-24, -2), VILLAGE, (6, 4), (20, 8), (34, 9), (40, -2), (36, -16), (30, -28),
            (CRAG[0], -33.5)]


def dist_poly(x, y, pts):
    d = np.full(x.shape, 1e9)
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        vx, vy = bx - ax, by - ay
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        d = np.minimum(d, np.hypot(x - ax - t * vx, y - ay - t * vy))
    return d


def heights(seed):
    lin = np.linspace(-SIZE_M / 2, SIZE_M / 2, N)
    X, Y = np.meshgrid(lin, lin)          # row = y, col = x
    s = 11
    # rolling base: the shelf, rising west and north, falling south
    h = SHELF + fbm2(X, Y, 1 / 40, s, 4) * 2.2 + fbm2(X, Y, 1 / 9, s + 1, 3) * 0.35
    h += sm(-80, -125, X) * 26 * (0.6 + 0.4 * fbm2(X, Y, 1 / 30, s + 2, 3))
    south = sm(-55, -128, Y)
    h -= south * (48 + fbm2(X, Y, 1 / 25, s + 3, 3) * 10)
    # the northern range: ridged peaks, terraced into strata ledges
    ridge = 1 - np.abs(fbm2(X * 0.7, Y * 0.35, 1 / 42, s + 4, 5))
    peaks = 22 + 95 * ridge ** 2.4 + fbm2(X, Y, 1 / 18, s + 5, 4) * 9 + np.maximum(fbm2(X, Y, 1 / 60, s + 10, 3), 0) * 40
    mt = sm(52, 125, Y + fbm2(X, Y, 1 / 35, s + 6, 3) * 18)
    hm = h + mt * peaks
    # strata ledges: dipping a little to the east, uneven in height, strongest on the steep middle slopes
    dip = hm + X * 0.08 + fbm2(X, Y, 1 / 30, s + 11, 3) * 3.0
    step = 5.0
    frac = (dip / step) % 1
    terr = hm - frac * step + step * sm(0.5, 1.0, frac)
    k = sm(22, 36, hm) * (0.35 + 0.35 * sm(-0.2, 0.4, fbm2(X, Y, 1 / 25, s + 12, 3)))
    h = hm + (terr - hm) * k
    # the crag under the tower: a terraced knoll with a flat top
    dc = np.hypot(X - CRAG[0], (Y - CRAG[1]) * 1.15)
    crag = 13.0 * sm(15, 5.5, dc + fbm2(X, Y, 1 / 6, s + 7, 3) * 2.0)
    cs = 2.6
    crag_t = np.floor(crag / cs) * cs + cs * sm(0.6, 1.0, (crag / cs) % 1)
    h += np.where(dc < 5.6, 13.0, crag_t)
    # the tarn: a basin with a scree fan from the north
    dt = np.hypot(X - TARN[0], (Y - TARN[1]) * 1.2) + fbm2(X, Y, 1 / 14, s + 8, 3) * 5
    h = np.where(dt < TARN[2] + 10, h - (h - (WATER - 5.5 * sm(TARN[2] + 2, 2, dt) + 1.5)) * sm(TARN[2] + 10, TARN[2] - 2, dt), h)
    # the gorge: steep walls, a narrow floor falling gently south
    gx = gorge_x(Y)
    dg = np.abs(X - gx)
    floor = 1.5 - (Y + 130) * 0.0 + Y * 0.06
    carve = sm(8.0, 2.4, dg + fbm2(X, Y, 1 / 7, s + 9, 3) * 0.9)
    wall = np.floor(carve * 6) / 6 * 0.25 + carve * 0.75      # stepped strata in the gorge walls
    h = h + (floor - h) * wall * sm(-125, -100, Y) * sm(75, 40, Y)
    # the path is a gentle groove; building pads are flat
    dp = dist_poly(X, Y, path_points())
    h -= sm(1.6, 0.0, dp) * 0.12
    return X, Y, h, dp


def flatten(X, Y, h, pads):
    for (px, py, r, z) in pads:
        d = np.hypot(X - px, Y - py)
        k = sm(r + 3.5, r, d)
        h[:] = h + (z - h) * k
    return h


def ground_at(h, x, y):
    fx = (x + SIZE_M / 2) / STEP
    fy = (y + SIZE_M / 2) / STEP
    i, j = int(np.clip(fy, 0, N - 2)), int(np.clip(fx, 0, N - 2))
    ty, tx = fy - i, fx - j
    return float(h[i, j] * (1 - tx) * (1 - ty) + h[i, j + 1] * tx * (1 - ty) + h[i + 1, j] * (1 - tx) * ty + h[i + 1, j + 1] * tx * ty)


def layout(seed, X, Y, h, dp):
    rng = np.random.default_rng(__import__('zlib').crc32(seed.encode()))
    L = {'houses': [], 'tower': None, 'pines': [], 'props': [], 'bridge': None}
    pads = []
    vx, vy = VILLAGE
    variants = ['brannoch', 'tessaly', 'orrow']
    ring = [(-150, 15.5), (-108, 14.0), (-62, 15.0), (-12, 16.0), (40, 15.0), (85, 16.5)]
    for i, (a, rr) in enumerate(ring):
        ar = math.radians(a + rng.uniform(-6, 6))
        px, py = vx + math.cos(ar) * rr, vy + math.sin(ar) * rr
        # face the square: the door (local -y) points at the centre
        face = math.atan2(vy - py, vx - px)
        rot = face + math.pi / 2
        z = SHELF + 0.4 * math.sin(i)
        L['houses'].append({'variant': variants[i % 3], 'x': px, 'y': py, 'rot': rot, 'z': z})
        pads.append((px, py, 5.6, z))
    pads.append((vx, vy, 7.0, SHELF))     # the square
    L['tower'] = {'x': CRAG[0], 'y': CRAG[1], 'rot': math.radians(rng.uniform(-10, 10)), 'z': None}
    # bridge ends on shelves either side of the gorge
    gxb = float(gorge_x(np.array([BRIDGE_Y]))[0])
    L['bridge'] = {'x': gxb, 'y': BRIDGE_Y, 'z': None}
    pads += [(gxb - 10.5, BRIDGE_Y, 2.5, SHELF + 2.0), (gxb + 10.5, BRIDGE_Y, 2.5, SHELF + 0.6)]
    h = flatten(X, Y, h, pads)
    L['bridge']['z'] = (ground_at(h, gxb - 10.5, BRIDGE_Y) + ground_at(h, gxb + 10.5, BRIDGE_Y)) / 2
    L['tower']['z'] = ground_at(h, CRAG[0], CRAG[1])
    # props on the ground
    def gz(x, y):
        return ground_at(h, x, y)

    def slope(x, y):
        return abs(gz(x + 1, y) - gz(x - 1, y)) / 2 + abs(gz(x, y + 1) - gz(x, y - 1)) / 2
    taken = [(hh['x'], hh['y'], 7.5) for hh in L['houses']] + [(vx, vy, 7.5), (CRAG[0], CRAG[1], 9), (gxb, BRIDGE_Y, 14), (gxb + 12, BRIDGE_Y - 14, 6)]

    def free(x, y, r):
        if float(dist_poly(np.array([x]), np.array([y]), path_points())[0]) < r + 1.4:
            return False
        return all(math.hypot(x - a, y - b) > r + c for a, b, c in taken)
    # pines: on the shelf edges and lower slopes, in loose groves
    groves = [(-30, 26), (14, 30), (-36, -26), (-6, -30), (44, -40), (-72, 18), (-74, -34), (30, 44), (8, -58), (78, -8)]
    for gx0, gy0 in groves:
        for k in range(int(rng.integers(4, 9))):
            x, y = gx0 + rng.normal(0, 7), gy0 + rng.normal(0, 7)
            z = gz(x, y)
            if z < WATER + 1 or z > 44 or slope(x, y) > 0.7 or abs(x - float(gorge_x(np.array([y]))[0])) < 10 or not free(x, y, 2.5):
                continue
            L['pines'].append({'variant': ['cirr', 'hask', 'ollum'][int(rng.integers(3))], 'x': x, 'y': y, 'z': z - 0.15,
                               'rot': float(rng.uniform(0, 6.28)), 's': float(rng.uniform(0.8, 1.2))})
            taken.append((x, y, 2.5))
    # boulders everywhere but the paths, more on scree
    for k in range(260):
        x, y = rng.uniform(-120, 120), rng.uniform(-110, 100)
        z = gz(x, y)
        sl = slope(x, y)
        if z < WATER - 0.5 or sl > 1.6 or not free(x, y, 2.0):
            continue
        if sl < 0.25 and rng.random() < 0.6:
            continue
        b = int(rng.integers(4))
        L['props'].append({'kind': f'boulder{b}', 'x': x, 'y': y, 'z': z - 0.3, 'rot': float(rng.uniform(0, 6.28)),
                           's': float(rng.uniform(0.6, 1.5))})
        taken.append((x, y, 1.5))
    # cairns along the path, quartz near the cliffs, wind posts round the village, a trough on the square
    pp = path_points()
    for i, (ax, ay) in enumerate(pp[1:-1]):
        if i % 2 == 0:
            continue
        bx, by = pp[i + 2]
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy)
        x, y = ax - dy / ln * 2.4, ay + dx / ln * 2.4
        L['props'].append({'kind': 'cairn', 'x': x, 'y': y, 'z': gz(x, y) - 0.05, 'rot': float(rng.uniform(0, 6)), 's': 1.0})
    for k in range(40):
        x, y = rng.uniform(-110, 110), rng.uniform(30, 90)
        z = gz(x, y)
        if z > SNOW - 4 or slope(x, y) > 1.2 or not free(x, y, 1.5):
            continue
        L['props'].append({'kind': 'quartz', 'x': x, 'y': y, 'z': z - 0.2, 'rot': float(rng.uniform(0, 6)), 's': float(rng.uniform(0.8, 1.6))})
        taken.append((x, y, 1.5))
    for a in (20, 140, 260):
        ar = math.radians(a)
        x, y = vx + math.cos(ar) * 7.6, vy + math.sin(ar) * 7.6
        L['props'].append({'kind': 'windpost', 'x': x, 'y': y, 'z': gz(x, y) - 0.1, 'rot': float(rng.uniform(0, 6)), 's': 1.0})
    L['props'].append({'kind': 'trough', 'x': vx + 2.5, 'y': vy - 2.2, 'z': SHELF, 'rot': 0.4, 's': 1.0})
    # field walls south of the village
    for k in range(9):
        x, y = -26 + k * 4.0 + rng.uniform(-0.2, 0.2), -14 - 0.6 * k + rng.uniform(-0.3, 0.3)
        L['props'].append({'kind': 'drywall', 'x': x, 'y': y, 'z': gz(x, y) - 0.06, 'rot': -math.atan2(0.6, 4.0), 's': 1.0})
    L['stairs'] = []
    return h, L


def crag_stairs(h, L):
    """Stair flights up the crag's north face, each starting where the last ends."""
    x = CRAG[0]
    y = -32.5
    z = ground_at(h, x, y)
    top = L['tower']['z']
    out = []
    while z < top - 0.3:
        out.append({'kind': 'stairs', 'x': x, 'y': y, 'z': z - 0.02, 'rot': math.pi, 's': 1.0})
        y -= 7 * 0.36
        z += 1.4
    # cut the crag face so the flights sit in a notch
    return out


ZONES = {'meadow': 1, 'scree': 2, 'cliff': 3, 'snow': 4, 'path': 5, 'shore': 6, 'water': 7, 'square': 8, 'gorge': 9}


def zones(X, Y, h, dp):
    gy, gx = np.gradient(h, STEP)
    slope = np.hypot(gx, gy)
    z = np.full(h.shape, ZONES['meadow'], np.uint8)
    n = fbm2(X, Y, 1 / 6, 51, 3)
    z[slope + n * 0.15 > 0.55] = ZONES['scree']
    z[slope > 1.05] = ZONES['cliff']
    z[(h + fbm2(X, Y, 1 / 12, 53, 3) * 6 > SNOW) & (slope < 1.3)] = ZONES['snow']
    near = np.hypot(X - TARN[0], (Y - TARN[1]) * 1.2) < TARN[2] + 12
    z[near & (h < WATER + 1.2) & (h > WATER - 0.4)] = ZONES['shore']
    z[near & (h <= WATER - 0.4)] = ZONES['water']
    gxx = gorge_x(Y)
    z[(np.abs(X - gxx) < 3.0) & (h < 8) & (Y < 70)] = ZONES['gorge']
    z[(dp < 1.25 + n * 0.3) & (slope < 0.9)] = ZONES['path']
    z[np.hypot(X - VILLAGE[0], Y - VILLAGE[1]) < 6.6] = ZONES['square']
    return z, slope


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--assets', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--seed', default='vanehold')
    ap.add_argument('--size', type=int, default=4096)
    ap.add_argument('--light', type=int, default=2048)
    ap.add_argument('--samples', type=int, default=32)
    ap.add_argument('--nobake', action='store_true')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    X, Y, h, dp = heights(a.seed)
    h, L = layout(a.seed, X, Y, h, dp)
    L['stairs'] = crag_stairs(h, L)
    zmap, slope = zones(X, Y, h, dp)
    print(f'[terrain] heights {h.min():.1f}..{h.max():.1f} m, {len(L["houses"])} houses, {len(L["pines"])} pines, '
          f'{len(L["props"])} props, {time.time() - t0:.1f}s', flush=True)
    import ground_paint
    ground_paint.paint(a.out, X, Y, h, zmap, slope, dp, a.size)
    import base64
    q = np.clip(np.round((h + 80.0) * 200.0), 0, 65535).astype(np.uint16)   # 5 mm steps from -80 m
    meta = {'size_m': SIZE_M, 'n': N, 'water': WATER, 'snow': SNOW, 'h_off': -80.0, 'h_scale': 1 / 200.0,
            'heights': base64.b64encode(q.tobytes()).decode(), 'zones': base64.b64encode(zmap.tobytes()).decode(),
            'layout': L, 'path': path_points(), 'gorge': [[float(gorge_x(np.array([y]))[0]), y] for y in range(-130, 131, 5)]}
    json.dump(meta, open(os.path.join(a.out, 'terrain.json'), 'w'))
    np.save(os.path.join(a.out, 'heights.npy'), h.astype(np.float32))
    print(f'[terrain] painted, {time.time() - t0:.1f}s', flush=True)
    if not a.nobake:
        import terrain_bake
        terrain_bake.bake(a.out, a.assets, h, L, a.light, a.samples)
    print(f'[terrain] done {time.time() - t0:.1f}s', flush=True)


if __name__ == '__main__':
    main()
