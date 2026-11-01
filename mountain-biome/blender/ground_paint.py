"""Paint the Vanehold ground: one top-down albedo over the whole map, palette swatches only, micro relief lit from
above (the light map adds the big shapes), ramp-constrained error diffusion. Steep cliff faces are left to the
page's strata shader, which reads them side-on; here they get the strata colour by height so the top view agrees."""
import ctypes
import os

import numpy as np
from PIL import Image

import paint as P
from terrain import SIZE_M, N, STEP, WATER, SNOW, ZONES, VILLAGE, fbm2, vn2, sm

GROUND_RAMPS = {
    'grass':  ['#2b2d18', '#3b3e20', '#4e5129', '#626532', '#787a3c', '#8f8f47', '#a6a356'],
    'turf':   ['#1d2716', '#29361d', '#374725', '#46592d', '#566c36'],
    'dirt':   ['#352d24', '#483d30', '#5c4f3e', '#72624d', '#88775f', '#9d8c72'],
    'lakebed': ['#16323a', '#1e4650', '#285c66', '#35727a', '#4a8a8e'],
    'bloom':  ['#3e2c56', '#5a437a', '#7a609e', '#9c84bd'],
    'gold':   ['#7a5b1c', '#a07a26', '#c49c36', '#ddbc55'],
}
for k, v in GROUND_RAMPS.items():
    P.RAMPS[k] = v
# rebuild the tables with the ground ramps added
P.RNAMES = list(P.RAMPS)
P.RID = {k: i for i, k in enumerate(P.RNAMES)}
P.RLEN = np.array([len(P.RAMPS[k]) for k in P.RNAMES], np.int32)
P.RMAX = P.RLEN.max()
P.RTAB = np.zeros((len(P.RNAMES), P.RMAX, 3), np.uint8)
for i, k in enumerate(P.RNAMES):
    for j, hx in enumerate(P.RAMPS[k]):
        P.RTAB[i, j] = P._hex(hx)


def bilinear(A, fx, fy):
    fx = np.clip(fx, 0, N - 1.001)
    fy = np.clip(fy, 0, N - 1.001)
    j, i = fx.astype(np.int64), fy.astype(np.int64)
    tx, ty = fx - j, fy - i
    return (A[i, j] * (1 - tx) * (1 - ty) + A[i, j + 1] * tx * (1 - ty) + A[i + 1, j] * (1 - tx) * ty + A[i + 1, j + 1] * tx * ty)


def relief(hf, x, y, e=0.03):
    """Light from above-left on a small height field: 0.5 flat, up to 1 facing the light."""
    dx = hf(x + e, y) - hf(x - e, y)
    dy = hf(x, y + e) - hf(x, y - e)
    return np.clip(0.5 + (-dx * 0.7 + dy * 0.7) * 6.0, 0, 1)


def paint(out, X, Y, h, zmap, slope, dp, S):
    rid = np.zeros((S, S), np.int32)
    tt = np.zeros((S, S), np.float32)
    rows = 256
    for r0 in range(0, S, rows):
        r1 = min(S, r0 + rows)
        jj, ii = np.meshgrid(np.arange(S), np.arange(r0, r1))
        x = -SIZE_M / 2 + (jj + 0.5) * SIZE_M / S
        y = -SIZE_M / 2 + (ii + 0.5) * SIZE_M / S
        fx, fy = (x + SIZE_M / 2) / STEP, (y + SIZE_M / 2) / STEP
        hh = bilinear(h, fx, fy)
        sl = bilinear(slope, fx, fy)
        jit = vn2(x, y, 1.3, 71) * 0.7
        zi = np.clip(np.round(fy + jit), 0, N - 1).astype(np.int64)
        zj = np.clip(np.round(fx + vn2(x, y, 1.3, 73) * 0.7), 0, N - 1).astype(np.int64)
        z = zmap[zi, zj]
        dpp = bilinear(dp, fx, fy)
        R = np.full(x.shape, P.RID['grass'], np.int32)
        T = np.full(x.shape, 0.5, np.float32)
        # meadow: tufts of gold turf, greener in hollows and by water, flowers in drifts
        tuft = lambda a, b: vn2(a, b, 7.0, 81) * 0.6 + vn2(a, b, 19.0, 82) * 0.4
        rl = relief(tuft, x, y, 0.02)
        patch = fbm2(x, y, 1 / 9, 83, 4)
        green = (patch < -0.15) | (hh < WATER + 3) & (patch < 0.2)
        T = 0.35 + rl * 0.4 + patch * 0.15
        R[:] = np.where(green, P.RID['turf'], P.RID['grass'])
        drift = fbm2(x, y, 1 / 7, 85, 3)
        dot = vn2(x, y, 26.0, 87)
        fl = (drift > 0.25) & (dot > 0.55) & (z == ZONES['meadow'])
        R[fl] = P.RID['bloom']
        T[fl] = 0.4 + (dot[fl] - 0.55) * 1.2
        fl2 = (drift < -0.3) & (dot > 0.68) & (z == ZONES['meadow'])
        R[fl2] = P.RID['gold']
        T[fl2] = 0.6
        # scree and cliffs: stones with lit tops, the colour of the stratum at that height
        band = np.floor((hh + fbm2(x, y, 1 / 20, 89, 3) * 3) / 4.2).astype(np.int64) % 7
        strat = np.choose(band, [P.RID['slate'], P.RID['slate'], P.RID['rose'], P.RID['slate'], P.RID['cream'], P.RID['rose'], P.RID['slate']])
        stones = lambda a, b: np.maximum(vn2(a, b, 3.2, 91), vn2(a, b, 6.5, 92) * 0.8)
        srl = relief(stones, x, y, 0.03)
        st = (z == ZONES['scree']) | (z == ZONES['cliff']) | (z == ZONES['gorge'])
        R[st] = strat[st]
        T[st] = (0.25 + srl * 0.6 + vn2(x, y, 40, 93) * 0.06)[st]
        lichen = st & (fbm2(x, y, 1 / 3, 95, 3) > 0.3) & (vn2(x, y, 3.0, 96) > 0.55) & (z != ZONES['gorge'])
        R[lichen] = P.RID['lichen']
        T[lichen] = 0.4
        gz = z == ZONES['gorge']
        T[gz] = T[gz] * 0.6
        # snow: drifts with blue hollows and wind-scoured stone showing through
        sn = z == ZONES['snow']
        snow_t = 0.55 + relief(lambda a, b: fbm2(a, b, 0.8, 97, 3), x, y, 0.1) * 0.4 + vn2(x, y, 30, 98) * 0.05
        scour = sn & (vn2(x, y, 2.2, 99) + (hh - SNOW) * -0.02 > 0.62)
        R[sn] = P.RID['snow']
        T[sn] = snow_t[sn]
        R[scour] = strat[scour]
        T[scour] = 0.4
        # shore pebbles and the lakebed
        sh = z == ZONES['shore']
        pr = relief(lambda a, b: vn2(a, b, 9.0, 101), x, y, 0.015)
        R[sh] = np.where(vn2(x, y, 5, 103)[sh] > 0, P.RID['cream'], P.RID['slate'])
        T[sh] = (0.3 + pr * 0.55)[sh]
        wt = z == ZONES['water']
        R[wt] = P.RID['lakebed']
        T[wt] = np.clip(0.75 - (WATER - hh[wt]) * 0.12 + vn2(x, y, 3, 105)[wt] * 0.1, 0, 1)
        # path: trodden earth with set stones
        pa = z == ZONES['path']
        R[pa] = P.RID['dirt']
        T[pa] = (0.4 + relief(lambda a, b: vn2(a, b, 5.0, 107), x, y, 0.03) * 0.3 + vn2(x, y, 30, 108) * 0.06)[pa]
        edge = pa & (dpp > 0.9)
        R[edge & (patch > 0)] = P.RID['grass']
        setst = pa & (vn2(x, y, 2.4, 109) > 0.5)
        R[setst] = P.RID['cream']
        T[setst] = (0.3 + relief(lambda a, b: vn2(a, b, 2.4, 109), x, y, 0.03) * 0.5)[setst]
        # the square: flagstones
        sq = z == ZONES['square']
        cx, cy = (x - VILLAGE[0]) / 0.85, (y - VILLAGE[1]) / 0.6
        row = np.floor(cy)
        cx = cx + (row % 2) * 0.5
        fxx, fyy = cx - np.floor(cx), cy - row
        joint = (np.minimum(fxx, 1 - fxx) < 0.05) | (np.minimum(fyy, 1 - fyy) < 0.07)
        cell = P._hash(np.floor(cx).astype(np.int64), row.astype(np.int64), np.zeros_like(row, dtype=np.int64), 111)
        R[sq] = np.where(cell[sq] > 0.7, P.RID['rose'], np.where(cell[sq] > 0.35, P.RID['cream'], P.RID['slate']))
        T[sq] = (0.45 + (cell - 0.5) * 0.3 + vn2(x, y, 25, 112) * 0.06)[sq]
        jm = sq & joint
        R[jm] = P.RID['mortar']
        T[jm] = 0.2
        rid[r0:r1] = R
        tt[r0:r1] = np.clip(T, 0, 1)
    n = P.RLEN[rid].astype(np.int32)
    tval = (tt * (n - 1)).astype(np.float32)
    o = np.zeros((S, S), np.int32)
    lib = P._dither()
    lib.diffuse(tval.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), n.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
                o.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), S, S, ctypes.c_float(0.8))
    rgb = P.RTAB[rid, np.clip(o, 0, P.RMAX - 1)]
    a = np.ascontiguousarray(rgb[::-1])                     # row 0 = north
    cols, inv = np.unique(a.reshape(-1, 3), axis=0, return_inverse=True)
    if len(cols) <= 256:   # indexed colour: every pixel is a palette swatch
        im = Image.fromarray(inv.reshape(a.shape[:2]).astype(np.uint8), 'P')
        im.putpalette(cols.astype(np.uint8).ravel().tolist())
    else:
        im = Image.fromarray(a)
    im.save(os.path.join(out, 'ground.png'), optimize=True)
    print('[ground] painted', flush=True)
