"""Palette painter for Vanehold Pass: per-texel bake data in, palette pixels out.

Every texel's colour is a swatch from one of the ramps below. A material painter turns the texel's part, grain, position,
normal, occlusion and edge into a tone, the baked light (sky overhead, high sun, the asset's own lamps) is painted into the
same tone, and ramp-constrained error diffusion picks the swatch. The palette is this game's own; it shares nothing with
Khadrel's palette sheet.
"""
import ctypes
import os
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _hex(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


# dark to light, every ramp checked by eye for an even step in lightness
RAMPS = {
    # banded mountain stone: three strata
    'slate':   ['#202226', '#2d3036', '#3b3f46', '#4b5058', '#5d636b', '#737980', '#8c9197'],
    'rose':    ['#33272a', '#4a3739', '#61494a', '#795c5a', '#91716c', '#a9877f', '#bfa096'],
    'cream':   ['#4a4034', '#655846', '#81725a', '#9d8d6f', '#b8a888', '#cfc2a2', '#e2d8bd'],
    'soot':    ['#141416', '#1e1e21', '#2a292c', '#38363a', '#48454a'],
    'mortar':  ['#2a2826', '#3d3a36', '#55504a', '#6d675f'],
    # timber: high-country larch, silvered outside and honey-dark where hands and smoke reach
    'larch':   ['#231c18', '#342922', '#47392e', '#5c4b3d', '#736251', '#8c7b68', '#a59683', '#bdb2a1'],
    'honey':   ['#241912', '#36261b', '#4a3525', '#5e4531', '#74583f', '#8a6c50', '#a08465'],
    'shingle': ['#16181e', '#1f232b', '#2a2f39', '#363c48', '#444b59', '#55606f'],
    'iron':    ['#151416', '#211f22', '#2f2c30', '#423e42', '#57524f'],
    'rust':    ['#3b1e12', '#57301a', '#744424', '#8f5a30'],
    # growth
    'lichen':  ['#6e4416', '#94591a', '#b8721f', '#d4912e', '#e6b04b'],
    'palelich': ['#54604f', '#6f7c66', '#8b9880', '#a9b39b'],
    'moss':    ['#262a14', '#363b1b', '#4a5023', '#5f662d', '#787f3b'],
    # cloth and rope
    'wool':    ['#4a4239', '#655a4d', '#827562', '#9f927b', '#bbae95', '#d4c9b1', '#e7dfcb'],
    'madder':  ['#3d1514', '#561d1b', '#712823', '#8c372c', '#a64b37', '#bd6446'],
    'woad':    ['#141c2c', '#1d2a40', '#293a56', '#384d6c', '#4b6283'],
    'rope':    ['#3a2f22', '#54452f', '#6e5c3e', '#8a7550', '#a59066'],
    # stone of the high ground
    'quartz':  ['#5d5870', '#7a7590', '#9a95ae', '#bcb8cc', '#dad8e6', '#f1f0f6'],
    'bark':    ['#1f1512', '#2e1f19', '#3f2b22', '#53392c', '#684a39', '#7f5d48'],
    'needle':  ['#0f1d1b', '#152824', '#1c342e', '#25423a', '#305247', '#3e6455', '#507763'],
    'snow':    ['#8494ab', '#a1afc3', '#bfcad9', '#d9e1ea', '#eef2f6'],
    'ember':   ['#ffcf7a'],
    'mica':    ['#f2c27a'],
}
RNAMES = list(RAMPS)
RID = {k: i for i, k in enumerate(RNAMES)}
RLEN = np.array([len(RAMPS[k]) for k in RNAMES], np.int32)
RMAX = RLEN.max()
RTAB = np.zeros((len(RNAMES), RMAX, 3), np.uint8)
for i, k in enumerate(RNAMES):
    for j, h in enumerate(RAMPS[k]):
        RTAB[i, j] = _hex(h)


# ---------------- noise ----------------
def _hash(ix, iy, iz, seed):
    h = (ix.astype(np.uint32) * np.uint32(0x8da6b343)) ^ (iy.astype(np.uint32) * np.uint32(0xd8163841)) \
        ^ (iz.astype(np.uint32) * np.uint32(0xcb1ab31f)) ^ np.uint32(seed * 0x9e3779b1 & 0xffffffff)
    h ^= h >> np.uint32(15)
    h *= np.uint32(0x2c1b3c6d)
    h ^= h >> np.uint32(12)
    h *= np.uint32(0x297a2d39)
    h ^= h >> np.uint32(15)
    return h.astype(np.float32) / np.float32(4294967295.0)


def vnoise(P, f, seed):
    """Value noise in -1..1 at points P (N x 3), frequency f per metre."""
    q = P * f
    i = np.floor(q)
    t = q - i
    t = t * t * (3 - 2 * t)
    i = i.astype(np.int64)
    out = np.zeros(len(P), np.float32)
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                w = (t[:, 0] if dx else 1 - t[:, 0]) * (t[:, 1] if dy else 1 - t[:, 1]) * (t[:, 2] if dz else 1 - t[:, 2])
                out += w * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out * 2 - 1


def fbm(P, f, seed, oct=4):
    v, a, tot = np.zeros(len(P), np.float32), 1.0, 0.0
    for o in range(oct):
        v += a * vnoise(P, f * (2 ** o), seed + o * 31)
        tot += a
        a *= 0.5
    return v / tot


def phash(part, seed):
    """Stable 0..1 random per part id."""
    p = part.astype(np.uint32)
    return _hash(p, p * np.uint32(3) + np.uint32(1), np.zeros_like(p), seed)


def sm(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def rg(mask, P, seed, f=40.0, amt=0.25):
    """Break a soft mask's rim with fine noise so patches do not read as blobs."""
    return np.clip(mask + vnoise(P, f, seed) * amt, 0, 1)


# ---------------- per-texel context ----------------
class Tex:
    """Flat arrays over the texels of one material."""

    def __init__(self, D, sel, ctx):
        self.P = D['P'][sel]
        self.N = D['N'][sel]
        self.A = D['A'][sel]
        self.part = D['part'][sel]
        self.edge = D['edge'][sel]
        self.ao = D['ao'][sel]
        self.l = D['l'][sel]
        self.n = len(self.P)
        self.ctx = ctx
        # grain frame: along the part's axis, and across it on the face
        a = self.A
        self.along = np.einsum('ij,ij->i', self.P, a)
        cr = np.cross(self.N, a)
        self.across = np.einsum('ij,ij->i', self.P, cr)
        self.endgrain = np.abs(np.einsum('ij,ij->i', self.N, a)) > 0.7
        self.up = self.N[:, 2]
        self.ph = phash(self.part, 7)
        self.ph2 = phash(self.part, 13)

    def out(self):
        self.r = np.full(self.n, RID['slate'], np.int32)
        self.t = np.full(self.n, 0.5, np.float32)
        return self


def outside(T):
    f = T.ctx.get('outside')
    return f(T.P, T.N) if f else np.ones(T.n, bool)


def lit(base, T, w=0.68, edge=0.16, cav=0.18):
    """Paint the light into a tone: base 0..1 (the material), the baked light, a lighter worn edge, dark cavities."""
    t = base * (1 - w) + T.l * w + np.clip(T.edge * 3.0, 0, 1) * edge - (1 - T.ao) * cav
    return np.clip(t, 0, 1)


def put(T, m, ramp, t):
    T.r[m] = RID[ramp]
    T.t[m] = t[m] if np.ndim(t) else t


# ---------------- material painters ----------------
def p_stone(T, banded=True):
    """Coursed banded stone: each block a stratum (slate, rose or cream), bedding lines inside, chisel speckle,
    orange and pale lichen on exposed faces outside, moss low in the joints, soot above the hearth."""
    T.out()
    P = T.P
    if banded and 'strat' in T.ctx:
        lut = np.full(int(T.part.max()) + 1, -1, np.int64)
        for pid, k in T.ctx['strat'].items():
            if pid < len(lut):
                lut[pid] = k
        strat = lut[T.part]
        k = (T.ph * 100).astype(int) % 10
        strat = np.where(strat >= 0, strat, np.where(k < 6, 0, np.where(k < 8, 1, 2)))
    elif banded:
        k = (T.ph * 100).astype(int) % 10
        strat = np.where(k < 5, 0, np.where(k < 8, 1, 2))      # slate, rose, cream
    else:
        z = P[:, 2] + fbm(P, 0.15, 3, 2) * 1.6
        b = np.floor(z / 0.9).astype(int) % 7
        strat = np.choose(np.clip(b, 0, 6), [0, 0, 1, 0, 2, 1, 0])
    bed = 0.5 + 0.5 * np.sin(P[:, 2] * 38 + fbm(P, 2.0, 5, 3) * 3.0 + T.ph * 20)
    speck = vnoise(P, 45, 9)
    mott = fbm(P, 3.0, 11, 3)
    base = 0.48 + (T.ph2 - 0.5) * 0.3 + bed * 0.1 + mott * 0.13 + speck * 0.04
    t = lit(base, T, edge=0.08)
    for i, nm in enumerate(('slate', 'rose', 'cream')):
        put(T, strat == i, nm, t)
    out = outside(T)
    exp = out & (T.ao > 0.75)
    lich = rg(sm(0.35, 0.6, fbm(P, 1.6, 21, 4)) * sm(-0.3, 0.6, T.up + 0.3), P, 22) * exp
    lm = (lich > 0.55) & (vnoise(P, 22, 23) > -0.2)
    put(T, lm, 'lichen', np.clip(lit(0.55 + speck * 0.2, T, 0.5), 0, 1))
    pl = exp & (sm(0.45, 0.7, fbm(P, 2.3, 25, 3)) > 0.6) & (vnoise(P, 9, 26) > 0.1) & ~lm
    put(T, pl, 'palelich', lit(0.5 + speck * 0.2, T, 0.5))
    moss = out & (T.ao < 0.72) & (P[:, 2] < T.ctx.get('moss_z', 1.2)) & (fbm(P, 4, 27, 3) > -0.1)
    put(T, moss, 'moss', lit(0.4 + mott * 0.3, T, 0.5))
    if 'hearth' in T.ctx:
        h = np.array(T.ctx['hearth'])
        d = P - h
        r = np.hypot(d[:, 0], d[:, 1])
        sootk = (~out) & (d[:, 2] > -0.3) & (d[:, 2] < 3.4)
        sootk = sootk * sm(1.25 + d[:, 2] * 0.3, 0.5, r) * sm(3.4, 0.8, d[:, 2])
        sootk = rg(sootk, P, 29, 14, 0.35)
        put(T, sootk > 0.72, 'soot', lit(0.45 + mott * 0.3, T, 0.5))
        dim = (sootk > 0.4) & (sootk <= 0.72)
        T.t[dim] = np.clip(T.t[dim] - 0.25, 0, 1)
    return T


def p_mortar(T):
    T.out()
    put(T, np.ones(T.n, bool), 'mortar', lit(0.4 + fbm(T.P, 9, 31, 2) * 0.3, T, 0.6))
    return T


def p_flag(T):
    """Floor flagstones: worn smooth in the middle of the room, darker at the walls."""
    T.out()
    P = T.P
    k = (T.ph * 100).astype(int) % 6
    mott = fbm(P, 2.5, 41, 3)
    base = 0.45 + (T.ph2 - 0.5) * 0.3 + mott * 0.18 + vnoise(P, 50, 43) * 0.05
    t = lit(base, T, 0.6, edge=0.22)
    put(T, k < 3, 'slate', t)
    put(T, (k >= 3) & (k < 5), 'cream', t)
    put(T, k == 5, 'rose', t)
    return T


def p_wood(T, ramp='larch', weather=True):
    """Boards and beams: grain along each part, end grain darker, each part its own tone, silvered outside."""
    T.out()
    P = T.P
    warp = fbm(P, 1.2, 51 + int(ramp == 'honey'), 3)
    grain = 0.5 + 0.5 * np.sin(T.across * 95 + warp * 6 + T.ph * 40 + np.sin(T.along * 2.1 + T.ph * 9) * 2)
    streak = fbm(np.stack([T.across * 30, T.along * 1.5, T.ph * 50], 1), 1.0, 53, 3)
    knot = sm(0.82, 0.92, vnoise(np.stack([T.across * 6, T.along * 2.0, T.ph * 80], 1), 1.0, 55))
    base = 0.5 + (T.ph2 - 0.5) * 0.35 + grain * 0.16 + streak * 0.14 - knot * 0.35
    base = np.where(T.endgrain, base - 0.18 + 0.1 * np.sin(np.hypot(T.across, T.along) * 120), base)
    t = lit(base, T, 0.6, edge=0.18)
    put(T, np.ones(T.n, bool), ramp, t)
    if weather:
        out = outside(T)
        lich = out & (T.up > 0.3) & (T.ao > 0.8) & (fbm(P, 3.0, 57, 3) > 0.42)
        put(T, lich, 'palelich', lit(0.45 + grain * 0.2, T, 0.5))
        inside = ~out
        put(T, inside, 'honey', lit(base - 0.05, T, 0.6, edge=0.2))
    return T


def p_shingle(T):
    """Slate shingles: each its own tone, a pale split edge, orange lichen rosettes, moss where they overlap."""
    T.out()
    P = T.P
    mott = fbm(P, 4, 61, 3)
    base = 0.45 + (T.ph - 0.5) * 0.45 + mott * 0.12 + vnoise(P, 45, 63) * 0.07
    t = lit(base, T, 0.58, edge=0.3)
    put(T, np.ones(T.n, bool), 'shingle', t)
    exp = (T.up > 0.2) & (T.ao > 0.7)
    ros = rg(sm(0.5, 0.75, fbm(P, 2.2, 65, 4)), P, 66, 30, 0.35) > 0.6
    put(T, exp & ros & (T.ph2 > 0.55), 'lichen', lit(0.55 + mott * 0.3, T, 0.45))
    put(T, exp & (fbm(P, 3.1, 67, 3) > 0.62) & ~ros, 'palelich', lit(0.4 + mott * 0.3, T, 0.45))
    put(T, (T.ao < 0.45) & (T.up > 0.3) & (fbm(P, 5, 68, 2) > 0.2), 'moss', lit(0.35 + mott * 0.3, T, 0.45))
    put(T, T.up < -0.3, 'larch', lit(0.35 + mott * 0.2, T, 0.5))   # undersides read as the sarking boards
    return T


def p_iron(T):
    T.out()
    P = T.P
    base = 0.45 + fbm(P, 12, 71, 2) * 0.2
    put(T, np.ones(T.n, bool), 'iron', lit(base, T, 0.55, edge=0.35))
    put(T, (T.ao < 0.75) & (fbm(P, 8, 73, 3) > -0.05), 'rust', lit(0.5 + fbm(P, 20, 74, 2) * 0.3, T, 0.5))
    return T


def p_cloth(T, ramp='wool', stripe='madder'):
    T.out()
    P = T.P
    weave = 0.5 + 0.25 * np.sin(T.along * 260) * np.sin(T.across * 260)
    fade = fbm(P, 1.5, 81, 3)
    base = 0.55 + fade * 0.15 + weave * 0.08 + (T.ph - 0.5) * 0.15
    t = lit(base, T, 0.55, edge=0.05, cav=0.25)
    put(T, np.ones(T.n, bool), ramp, t)
    if stripe:
        band = (np.floor(T.along * 2.2 + T.ph * 3) % 3 == 0) & (T.ph2 > 0.3)
        put(T, band, stripe, lit(0.5 + fade * 0.2 + weave * 0.08, T, 0.5, edge=0.05, cav=0.25))
    return T


def p_rope(T):
    T.out()
    tw = 0.5 + 0.5 * np.sin(T.along * 160 + T.across * 160)
    put(T, np.ones(T.n, bool), 'rope', lit(0.4 + tw * 0.3 + fbm(T.P, 6, 91, 2) * 0.1, T, 0.5, edge=0.05))
    return T


def p_bark(T):
    """Plated bark: plates stretched along the trunk, dark furrows between them."""
    T.out()
    P = T.P
    q = np.stack([T.across * 9, T.along * 2.2, T.ph * 9], 1)
    plate = fbm(q, 1.0, 101, 3)
    furrow = sm(0.12, 0.0, np.abs(vnoise(q * np.array([1.6, 0.5, 1.0]), 1.0, 103)))
    base = 0.55 + plate * 0.25 - furrow * 0.4
    put(T, np.ones(T.n, bool), 'bark', lit(base, T, 0.55, edge=0.15, cav=0.25))
    put(T, (T.up > 0.2) & (fbm(P, 3.0, 105, 3) > 0.35), 'palelich', lit(0.45 + plate * 0.2, T, 0.5))
    return T


def p_needle(T):
    """Cloud-pine pads: dark beneath, a lighter fringe at the rim, fresh tips on top."""
    T.out()
    P = T.P
    tuft = fbm(P, 9, 111, 3)
    tip = sm(0.2, 0.9, T.up) * 0.25
    base = 0.45 + tuft * 0.25 + tip + np.clip(T.edge * 3, 0, 1) * 0.2 + (T.ph - 0.5) * 0.2
    put(T, np.ones(T.n, bool), 'needle', lit(base, T, 0.6, edge=0.1, cav=0.3))
    return T


def p_quartz(T):
    T.out()
    P = T.P
    vein = 0.5 + 0.5 * np.sin(T.along * 30 + fbm(P, 3, 121, 3) * 4)
    base = 0.5 + vein * 0.18 + (T.ph - 0.5) * 0.3
    put(T, np.ones(T.n, bool), 'quartz', lit(base, T, 0.5, edge=0.45, cav=0.15))
    return T


def p_water(T):
    """Running water in a flume or standing in a cistern: woad blue, lighter where it catches the sky."""
    T.out()
    P = T.P
    ripple = fbm(P, 6, 131, 3)
    put(T, np.ones(T.n, bool), 'woad', lit(0.62 + ripple * 0.18, T, 0.4, edge=0.3, cav=0.05))
    return T


def p_rock(T):
    return p_stone(T, banded=False)


PAINTERS = {
    'stone': p_stone, 'quoin': p_stone, 'rock': p_rock, 'hearth': p_stone, 'mortar': p_mortar, 'flag': p_flag,
    'wood': p_wood, 'plank': lambda T: p_wood(T, 'honey', False), 'shingle': p_shingle, 'iron': p_iron,
    'cloth': p_cloth, 'bedding': lambda T: p_cloth(T, 'wool', 'woad'), 'sail': lambda T: p_cloth(T, 'wool', 'madder'),
    'rope': p_rope, 'pennant': lambda T: p_cloth(T, 'madder', 'woad'), 'bark': p_bark, 'needle': p_needle, 'quartz': p_quartz,
    'water': p_water,
}


# ---------------- the paint ----------------
_lib = None


def _dither():
    global _lib
    if _lib is None:
        so = os.path.join(os.environ.get('MB_TMP', '/tmp'), 'mb_dither.so')
        if not os.path.exists(so):
            subprocess.check_call(['cc', '-O2', '-shared', '-fPIC', os.path.join(HERE, 'dither.c'), '-o', so])
        _lib = ctypes.CDLL(so)
    return _lib


def unpack(B, size):
    from bake import POS_OFF, POS_SCALE
    m = B['mask']
    D = {'mask': m}
    D['P'] = B['pos'][..., :3][m] * POS_SCALE - POS_OFF
    N = B['nrm'][..., :3][m] * 2 - 1
    D['N'] = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-6)
    A = B['axis'][..., :3][m] * 2 - 1
    D['A'] = A / np.maximum(np.linalg.norm(A, axis=1, keepdims=True), 1e-6)
    D['part'] = np.round(B['id'][..., 0][m] * 65536).astype(np.int64)
    D['slot'] = np.floor(B['id'][..., 1][m] * 64).astype(np.int64)
    D['edge'] = np.clip(B['id'][..., 2][m], 0, 1)
    D['ao'] = np.clip(B['ao'][..., 0][m], 0, 1)
    L = B['light'][..., :3][m] @ np.array([0.3, 0.59, 0.11], np.float32)
    D['L'] = L
    return D


def paint(B, size, slots, glow, ctx=None, light_ref=None, gamma=0.75):
    """Returns (rgb uint8 HxWx3 with row 0 = v 0, light reference used)."""
    ctx = ctx or {}
    D = unpack(B, size)
    m = D['mask']
    painted = np.array([s not in glow for s in slots])
    sel_atlas = painted[np.clip(D['slot'], 0, len(slots) - 1)]
    ref = light_ref or float(np.percentile(D['L'][sel_atlas], 96))
    D['l'] = np.clip(D['L'] / ref, 0, 1.25) ** gamma
    D['l'] = np.clip(D['l'], 0, 1)
    rid = np.full(len(D['P']), -1, np.int32)
    tt = np.zeros(len(D['P']), np.float32)
    for si, s in enumerate(slots):
        sel = D['slot'] == si
        if not sel.any():
            continue
        if s in glow:
            rid[sel] = RID['ember' if s == 'ember' else 'mica']
            continue
        T = Tex(D, sel, ctx)
        PAINTERS.get(s, p_stone)(T)
        rid[sel] = T.r
        tt[sel] = T.t
    # error diffusion over the whole atlas
    R = np.full((size, size), -1, np.int32)
    R[m] = rid
    n = np.where(R >= 0, RLEN[np.clip(R, 0, None)], 0).astype(np.int32)
    Tt = np.zeros((size, size), np.float32)
    Tt[m] = tt * (RLEN[np.clip(rid, 0, None)] - 1)
    out = np.zeros((size, size), np.int32)
    lib = _dither()
    lib.diffuse(Tt.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), n.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
                out.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), size, size, ctypes.c_float(0.85))
    rgb = np.zeros((size, size, 3), np.uint8)
    ok = R >= 0
    rgb[ok] = RTAB[R[ok], np.clip(out[ok], 0, RMAX - 1)]
    # fill the empty atlas area with the mean so mip or bleed never shows black
    rgb[~ok] = rgb[ok].mean(0).astype(np.uint8) if ok.any() else 0
    return rgb, ref
