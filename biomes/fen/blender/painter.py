"""Paint an asset's atlas from its bake (numpy only, runs in or outside Blender).

Fields per texel: pos, nrm, gdir (grain), pid + slot, light (sky dome + high sun, from above), ao (crevices), warm
(hearth light, houses only). Every pattern is a field in model space, so it runs straight across UV seams. Each texel
ends as one swatch of the fen palette, picked by ordered dither through a dark-to-light ramp.
"""
import numpy as np

# ------------------------------------------------------------------ the fen palette (original to this game)
PAL = {
    'peat_black': '#1e1611', 'peat_dark': '#2e2118', 'peat': '#43301f', 'peat_mid': '#5a4128', 'peat_dry': '#75583a', 'peat_crust': '#8f7350',
    'tim_dark': '#2b2622', 'tim': '#474038', 'tim_mid': '#665d52', 'tim_silver': '#88837a', 'tim_pale': '#aba79d',
    'wood_dark': '#2e1f17', 'wood': '#4a3222', 'wood_mid': '#664630', 'wood_lit': '#866043', 'wood_glow': '#a67e57',
    'bark_ink': '#24211f', 'bark_grey': '#5b5651', 'bark_chalk': '#a39e94', 'bark_pale': '#cbc5b7', 'bark_white': '#e4dfd1',
    'shg_dark': '#26211d', 'shg': '#3d3630', 'shg_mid': '#574e45', 'shg_lit': '#71675b', 'shg_pale': '#8b8174',
    'st_dark': '#323438', 'st': '#53565a', 'st_mid': '#73767a', 'st_lit': '#97999a', 'st_pale': '#b8b7b1',
    'lich_rust': '#b0602c', 'lich_ochre': '#cc943c', 'lich_pale': '#c4c995', 'lich_grey': '#9aa48a',
    'sph_red': '#6a2a1e', 'sph_rust': '#91401f', 'sph_ochre': '#b5762e', 'sph_gold': '#cfa247', 'sph_lime': '#a2ab48', 'sph_green': '#677a35',
    'moss_dark': '#2f3a1c', 'moss': '#4d5d27', 'moss_lit': '#748431',
    'hum_red': '#583222', 'hum_rust': '#7a4a2c', 'hum_ochre': '#9c6c38', 'hum_gold': '#bb9150', 'hum_green': '#47502a', 'hum_olive': '#626b35', 'hum_lime': '#858a43',
    'sed_dark': '#47461f', 'sed': '#716f35', 'sed_gold': '#a3994a', 'sed_pale': '#cbc078',
    'pad_dark': '#21331c', 'pad': '#3a5629', 'pad_mid': '#587a37', 'pad_lit': '#84a049', 'pad_red': '#7e2b28', 'pad_wine': '#4e1a1e',
    'fl_white': '#f0ede4', 'fl_blush': '#e8c6c0', 'fl_pink': '#cf8a90', 'fl_rose': '#a8505e', 'fl_gold': '#e6c25a',
    'pit_dark': '#43131a', 'pit': '#712026', 'pit_mid': '#9c352d', 'pit_vein': '#c86538', 'pit_lime': '#b2ae55', 'pit_pale': '#d8d094',
    'dew_red': '#a82828', 'dew_glint': '#f2e2ca',
    'wool_dark': '#6f6452', 'wool': '#9f927a', 'wool_lit': '#c9bda3', 'wool_pale': '#e3dbc7',
    'woad_dark': '#1d2533', 'woad': '#2c3f58', 'woad_mid': '#475f7c', 'woad_pale': '#7489a2',
    'och_dark': '#6e4a22', 'och': '#a07434', 'och_lit': '#c99a52',
    'clay_dark': '#4a392c', 'clay': '#735e48', 'clay_mid': '#988264', 'clay_lit': '#baa886',
    'iron_dark': '#1c1c1e', 'iron': '#38383b', 'iron_mid': '#535356', 'iron_rust': '#6a3a23',
    'em_dark': '#621a0a', 'em': '#c0421a', 'em_hot': '#ee8a2c', 'em_core': '#ffd47e',
    'lamp': '#f0b04e', 'lamp_core': '#ffe7a2',
    'soot': '#131010', 'soot_brown': '#221a15',
    'rope_dark': '#47371f', 'rope': '#776140', 'rope_lit': '#a3895a',
    'wick_dark': '#47321b', 'wick': '#77582f', 'wick_lit': '#a58148', 'wick_pale': '#c6a669',
    'hide_dark': '#46301f', 'hide': '#765232', 'hide_lit': '#a2784e',
}
RGB = {k: np.array([int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16)], np.uint8) for k, v in PAL.items()}

RAMPS = {
    'peat': ['peat_black', 'peat_dark', 'peat', 'peat_mid', 'peat_dry', 'peat_crust'],
    'timber': ['tim_dark', 'tim', 'tim_mid', 'tim_silver', 'tim_pale'],
    'wood': ['wood_dark', 'wood', 'wood_mid', 'wood_lit', 'wood_glow'],
    'bark': ['bark_ink', 'bark_grey', 'bark_chalk', 'bark_pale', 'bark_white'],
    'shingle': ['shg_dark', 'shg', 'shg_mid', 'shg_lit', 'shg_pale'],
    'stone': ['st_dark', 'st', 'st_mid', 'st_lit', 'st_pale'],
    'lichen': ['sph_rust', 'lich_rust', 'lich_ochre', 'lich_pale'],
    'lichen_grey': ['shg', 'moss', 'lich_grey', 'lich_pale'],
    'sphag': ['hum_red', 'hum_rust', 'hum_ochre', 'hum_gold'],
    'sphag_g': ['moss_dark', 'hum_green', 'hum_olive', 'hum_lime'],
    'moss': ['moss_dark', 'moss', 'moss_lit', 'hum_lime'],
    'sedge': ['sed_dark', 'sed', 'sed_gold', 'sed_pale'],
    'pad': ['pad_dark', 'pad', 'pad_mid', 'pad_lit'],
    'pad_under': ['pad_wine', 'pad_red', 'fl_rose'],
    'flower': ['fl_rose', 'fl_pink', 'fl_blush', 'fl_white'],
    'pitcher': ['pit_dark', 'pit', 'pit_mid', 'pit_vein'],
    'pitcher_base': ['pad_dark', 'pad', 'pit_lime', 'pit_pale'],
    'sundew': ['pit_dark', 'dew_red', 'pit_vein', 'dew_glint'],
    'wool': ['wool_dark', 'wool', 'wool_lit', 'wool_pale'],
    'woad': ['woad_dark', 'woad', 'woad_mid', 'woad_pale'],
    'ochre': ['och_dark', 'och', 'och_lit'],
    'clay': ['clay_dark', 'clay', 'clay_mid', 'clay_lit'],
    'iron': ['iron_dark', 'iron', 'iron_mid'],
    'rust': ['iron_dark', 'iron_rust', 'hide'],
    'ember': ['em_dark', 'em', 'em_hot', 'em_core'],
    'lamp': ['em_hot', 'lamp', 'lamp_core'],
    'soot': ['soot', 'soot_brown', 'peat_black', 'peat_dark'],
    'rope': ['rope_dark', 'rope', 'rope_lit'],
    'wicker': ['wick_dark', 'wick', 'wick_lit', 'wick_pale'],
    'hide': ['hide_dark', 'hide', 'hide_lit'],
}
RA = {k: np.stack([RGB[c] for c in v]) for k, v in RAMPS.items()}

SLOTS = ['peat', 'timber', 'bark', 'stone', 'shingle', 'deck', 'fleece', 'paint', 'clay', 'iron', 'rope', 'wicker',
         'ember', 'glass', 'moss', 'sphag', 'pad', 'flower', 'pitcher', 'sundew', 'cloth', 'soot', 'lichen', 'wood',
         'sedge', 'hide']

BAYER8 = (np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                    [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                    [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]]) + 0.5) / 64 - 0.5


# ------------------------------------------------------------------ noise (vectorised, 3D value noise)
def _h(ix, iy, iz, s):
    h = (ix * 374761393 + iy * 668265263 + iz * 2147483647 + s * 1442695041) & 0xffffffff
    h = ((h ^ (h >> 13)) * 1274126177) & 0xffffffff
    return ((h ^ (h >> 16)) & 0xffffff) / float(0xffffff)


def vnoise(x, y, z, s=0):
    xi, yi, zi = np.floor(x), np.floor(y), np.floor(z)
    fx, fy, fz = x - xi, y - yi, z - zi
    fx, fy, fz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    xi, yi, zi = xi.astype(np.int64), yi.astype(np.int64), zi.astype(np.int64)
    acc = 0
    for dx in (0, 1):
        wx = fx if dx else 1 - fx
        for dy in (0, 1):
            wy = fy if dy else 1 - fy
            for dz in (0, 1):
                wz = fz if dz else 1 - fz
                acc = acc + _h(xi + dx, yi + dy, zi + dz, s) * wx * wy * wz
    return acc * 2 - 1


def fbm(x, y, z, octaves=4, s=0):
    v, a, f, t = 0, 0.5, 1.0, 0
    for o in range(octaves):
        v = v + a * vnoise(x * f, y * f, z * f, s + o * 31)
        t += a
        a *= 0.5
        f *= 2.03
    return v / t


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def part_rand(pid, s):
    return _h(pid.astype(np.int64), np.int64(s), np.int64(7), 3)


# ------------------------------------------------------------------ painting
class Ctx:
    def __init__(self, bk, cfg):
        self.cfg = cfg
        m = bk['mask'] > 0
        self.P = bk['pos'].reshape(-1, 3)
        N = bk['nrm'].reshape(-1, 3)
        self.N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-6)
        G = bk['gdir'].reshape(-1, 3)
        self.G = G / np.maximum(np.linalg.norm(G, axis=1, keepdims=True), 1e-6)
        self.pid = np.round(bk['pid'][:, :, 0]).astype(np.int64).reshape(-1)
        self.slot = np.round(bk['pid'][:, :, 1]).astype(np.int64).reshape(-1)
        L = bk['light'].mean(axis=2).reshape(-1)
        mm = m.reshape(-1)
        ref = np.percentile(L[mm], 97) if mm.any() else 1
        self.L = np.clip(L / max(ref, 1e-3), 0, 1.3)
        self.ao = bk['ao'].mean(axis=2).reshape(-1)
        W = bk['warm'].mean(axis=2).reshape(-1)
        wref = cfg.get('warm_ref') or (np.percentile(W[mm], 99.5) if mm.any() and W.max() > 0 else 1)
        self.W = np.clip(W / max(wref, 1e-4), 0, 1.5)
        S = bk['mask'].shape[0]
        yy, xx = np.mgrid[0:S, 0:S]
        self.bay = BAYER8[yy % 8, xx % 8].reshape(-1)
        self.bay2 = BAYER8[(yy * 3 + 5) % 8, (xx * 5 + 2) % 8].reshape(-1)
        self.S = S

    def C(self):
        """Across-grain direction on the surface."""
        c = np.cross(self.N, self.G)
        return c / np.maximum(np.linalg.norm(c, axis=1, keepdims=True), 1e-6)


def light_term(c, idx, kw=0.55):
    """Light from above, painted in: sky light, crevice occlusion and the hearth's warmth."""
    L, ao, W = c.L[idx], c.ao[idx], c.W[idx]
    lit = 0.18 + 0.82 * np.sqrt(np.clip(L, 0, 1.2))
    lit = lit * (0.62 + 0.38 * ao) + 0.28 * np.clip(W, 0, 1.2)
    return np.clip(lit, 0, 1.25), kw


def quant(ramp, t, bay):
    n = len(ramp)
    k = np.clip(np.floor(t * (n - 1) + 0.5 + bay * 0.9), 0, n - 1).astype(np.int64)
    return ramp[k]


def mixramp(out, idx, sel, rampA, rampB, t, bay):
    """Per texel choose ramp A or B (sel = probability of B, ordered dither), then quantise."""
    use_b = sel > (bay * 0.999 + 0.5)
    a, b = idx[~use_b], idx[use_b]
    out[a] = quant(RA[rampA], t[~use_b], bay[~use_b])
    out[b] = quant(RA[rampB], t[use_b], bay[use_b])


def paint(bk, cfg=None):
    cfg = cfg or {}
    c = Ctx(bk, cfg)
    S = c.S
    out = np.zeros((S * S, 3), np.uint8)
    out[:] = RGB['peat_dark']
    P, N = c.P, c.N
    z0 = cfg.get('ground', 0.0)
    soot_on = cfg.get('soot', False)
    for si, name in enumerate(SLOTS):
        idx = np.nonzero(c.slot == si)[0]
        if len(idx) == 0:
            continue
        p, n, g = P[idx], N[idx], c.G[idx]
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        pid = c.pid[idx]
        pr = part_rand(pid, 11) - 0.5
        lit, kw = light_term(c, idx)
        bay, bay2 = c.bay[idx], c.bay2[idx]
        along = (p * g).sum(1)
        # across the grain: the angle round the part's own axis, so the pattern runs on unbroken from face to face
        cen = np.asarray(cfg.get('centres') or [[0, 0, 0]], np.float64)
        pc = cen[np.clip(pid, 0, len(cen) - 1)]
        d = p - pc
        ref = np.where(np.abs(g[:, :1]) < 0.9, np.array([[1.0, 0, 0]]), np.array([[0, 1.0, 0]]))
        U = np.cross(g, ref)
        U /= np.maximum(np.linalg.norm(U, axis=1, keepdims=True), 1e-6)
        Vv = np.cross(g, U)
        rad_ = np.hypot((d * U).sum(1), (d * Vv).sum(1))
        across = np.arctan2((d * Vv).sum(1), (d * U).sum(1)) * np.clip(np.median(rad_) if len(rad_) else 0.2, 0.05, 0.4)
        sky = np.clip(c.L[idx], 0, 1)
        up = n[:, 2]
        soot = np.zeros(len(idx))
        if soot_on:
            r = np.hypot(x - cfg.get('hx', 0), y - cfg.get('hy', 0))
            inside = r < cfg.get('rin', 3.0)
            soot = inside * smooth(cfg.get('soot_z0', 1.6), cfg.get('soot_z1', 3.6), z) * (1 - smooth(0.25, 0.55, sky)) * 0.7

        def t_of(v, kwi=kw):
            return np.clip(v * (1 - kwi) + lit * kwi - soot * 0.55, 0, 1)

        if name == 'peat':
            strata = fbm(x * 3, y * 3, z * 16, 3, 5)
            fib = fbm(x * 22, y * 22, z * 70, 2, 9)
            speck = smooth(0.55, 0.75, fbm(x * 40, y * 40, z * 40, 2, 13))
            wet = smooth(z0 + 0.6, z0 + 0.1, z)
            v = 0.42 + pr * 0.3 + strata * 0.16 + fib * 0.1 + speck * 0.22 - wet * 0.18
            v += (up > 0.6) * sky * 0.15
            t = t_of(v)
            mossy = (up > 0.55) * sky * smooth(0.0, 0.35, fbm(x * 2.5, y * 2.5, z * 2.5, 3, 17) + 0.1)
            out[idx] = quant(RA['peat'], t, bay)
            mixramp(out, idx, mossy * 1.6 - 0.2, 'peat', 'sphag_g', t, bay2)
        elif name in ('timber', 'deck', 'wood'):
            gr = fbm(across * 34, along * 2.2, pid * 0.37, 3, 21)
            check = smooth(0.06, 0.0, np.abs(np.sin(across * 9 + fbm(along * 0.9, across, pid * 1.0, 2, 23) * 3.2))) * \
                smooth(0.1, 0.5, fbm(along * 1.4, across * 3, pid * 0.7, 2, 25))
            knot = smooth(0.82, 0.92, fbm(along * 3, across * 6, pid * 0.3, 2, 27))
            v = 0.44 + pr * 0.35 + gr * 0.2 - check * 0.45 - knot * 0.3
            if name == 'deck':      # green slime creeps in where the light is low, worn grey on top
                slime = smooth(0.1, 0.45, fbm(x * 3, y * 3, z * 3, 3, 29)) * smooth(0.5, 0.15, c.L[idx])
                v -= slime * 0.15
            t = t_of(v)
            # outside, rain and sun silver the wood; indoors it stays brown and warms by the fire
            silver = 0.55 + 0.5 * sky if not cfg.get('house') else smooth(0.3, 0.7, sky) - c.W[idx] * 0.6
            if 'rin' in cfg:     # houses: everything outside the wall weathers silver, everything inside stays brown
                rr_ = np.hypot(x - cfg.get('hx', 0), y - cfg.get('hy', 0))
                silver = np.where(np.hypot(x, y) > cfg['rin'] + 0.02, 0.75 + 0.35 * smooth(0.2, 0.6, sky), -0.4)
            if name == 'wood':
                silver = silver * 0.25 - 0.3
            mixramp(out, idx, silver, 'wood', 'timber', t, bay2)
            if soot_on:
                s_idx = soot > (bay * 0.999 + 0.5) + 0.25
                out[idx[s_idx]] = quant(RA['soot'], t[s_idx], bay[s_idx])
        elif name == 'bark':
            # tallow bark: chalky, with black lenticel dashes across the trunk and dark fissures at the foot
            dash = smooth(0.62, 0.72, fbm(across * 5, along * 55, pid * 0.1, 2, 31))
            fis = smooth(0.0, 0.12, np.abs(fbm(across * 9, along * 0.8, pid * 0.1, 3, 33)))
            foot = smooth(z0 + 2.2, z0 + 0.3, z)
            v = 0.62 + pr * 0.1 + fbm(x * 4, y * 4, z * 2, 3, 35) * 0.12 - dash * 0.55 - (1 - fis) * foot * 0.55 - foot * 0.12
            t = t_of(v, 0.5)
            out[idx] = quant(RA['bark'], t, bay)
            mossy = smooth(z0 + 1.1, z0 + 0.2, z) * smooth(-0.1, 0.3, fbm(x * 3, y * 3, z * 3, 3, 37))
            mixramp(out, idx, mossy * 1.4 + (up > 0.5) * sky * 0.3, 'bark', 'sphag', t, bay2)
        elif name == 'shingle':
            streak = fbm(across * 30, along * 3, pid * 0.5, 2, 41)
            v = 0.42 + pr * 0.45 + streak * 0.18
            t = t_of(v, 0.5)
            out[idx] = quant(RA['shingle'], t, bay)
            crust = smooth(0.32, 0.5, fbm(x * 2.4, y * 2.4, z * 2.4, 4, 43) + fbm(x * 22, y * 22, z * 22, 2, 45) * 0.3)
            crust = crust * (up > 0.2) * sky
            mixramp(out, idx, crust * 1.1, 'shingle', 'lichen_grey', t, bay2)
            rust = smooth(0.62, 0.72, fbm(x * 5, y * 5, z * 5, 3, 49)) * (up > 0.2) * sky
            r_idx = np.nonzero(rust > (bay2 * 0.999 + 0.5))[0]
            out[idx[r_idx]] = quant(RA['lichen'], t[r_idx], bay[r_idx])
            if soot_on:
                s_idx = soot > (bay * 0.999 + 0.5) + 0.2
                out[idx[s_idx]] = quant(RA['soot'], t[s_idx], bay[s_idx])
        elif name == 'stone':
            sp = fbm(x * 30, y * 30, z * 30, 2, 51)
            v = 0.48 + pr * 0.25 + fbm(x * 3, y * 3, z * 3, 4, 53) * 0.2 + sp * 0.12
            t = t_of(v)
            out[idx] = quant(RA['stone'], t, bay)
            lm = smooth(0.1, 0.35, fbm(x * 2.2, y * 2.2, z * 2.2, 4, 55) + fbm(x * 20, y * 20, z * 20, 2, 57) * 0.3) * smooth(0.0, 0.6, up) * sky
            mixramp(out, idx, lm * 1.5, 'stone', 'lichen', t, bay2)
            if soot_on:
                hs = smooth(0.0, 1.0, c.W[idx]) * 0.5 + soot
                s_idx = hs > (bay * 0.999 + 0.5) + 0.35
                out[idx[s_idx]] = quant(RA['soot'], t[s_idx], bay[s_idx])
        elif name == 'fleece':
            tuft = fbm(x * 24, y * 24, z * 24, 3, 61)
            v = 0.55 + tuft * 0.3 + pr * 0.2
            out[idx] = quant(RA['wool'], t_of(v, 0.6), bay)
        elif name == 'cloth':
            stripe = (np.floor(along * 6) % 4 == 0)
            weave = np.sin(along * 400) * np.sin(across * 400) * 0.06
            v = 0.5 + weave + pr * 0.1
            t = t_of(v, 0.6)
            out[idx] = quant(RA['woad'], t, bay)
            s = np.nonzero(stripe)[0]
            out[idx[s]] = quant(RA['ochre'], t[s], bay[s])
        elif name == 'paint':
            # a painted, carved lintel: woad ground with an ochre river band, chipped and faded where weather hits
            zig = np.abs(((along * 2.6) % 1.0) - 0.5) * 0.16 - 0.04
            band = np.abs(across - zig - np.round((across - zig) / 0.5) * 0.5) < 0.022
            dots = (np.hypot(((along * 2.6) % 1.0) - 0.5, (across % 0.25) - 0.125) < 0.03)
            chip = smooth(0.45, 0.6, fbm(along * 14, across * 14, pid * 0.4, 3, 71)) * smooth(0.2, 0.8, sky)
            v = 0.55 + fbm(along * 30, across * 30, pid * 0.4, 2, 73) * 0.12
            t = t_of(v, 0.5)
            out[idx] = quant(RA['woad'], t, bay)
            b = np.nonzero(band | dots)[0]
            out[idx[b]] = quant(RA['ochre'], t[b], bay[b])
            ch = np.nonzero(chip > bay2 + 0.5)[0]
            out[idx[ch]] = quant(RA['timber'], t[ch] * 0.9, bay[ch])
        elif name == 'clay':
            crack = smooth(0.04, 0.0, np.abs(fbm(x * 6, y * 6, z * 6, 3, 81)))
            v = 0.5 + pr * 0.2 + fbm(x * 12, y * 12, z * 12, 2, 83) * 0.15 - crack * 0.4
            t = t_of(v)
            out[idx] = quant(RA['clay'], t, bay)
            hs = smooth(0.2, 1.0, c.W[idx]) * 0.6 * (up > 0.5)
            s_idx = hs > (bay2 * 0.999 + 0.5)
            out[idx[s_idx]] = quant(RA['soot'], t[s_idx], bay[s_idx])
        elif name == 'iron':
            v = 0.45 + fbm(x * 20, y * 20, z * 20, 2, 91) * 0.25
            t = t_of(v, 0.5)
            out[idx] = quant(RA['iron'], t, bay)
            rr = smooth(0.2, 0.5, fbm(x * 9, y * 9, z * 9, 3, 93)) * sky
            mixramp(out, idx, rr, 'iron', 'rust', t, bay2)
        elif name in ('rope', 'wicker'):
            tw = np.sin(along * 60 + across * 40) * 0.5 + 0.5
            if name == 'wicker':
                wv = np.sin(along * 26) * np.sin(across * 26)
                tw = 0.5 + 0.5 * np.sign(wv) * np.abs(np.sin(across * 26 + (wv > 0) * 1.57))
            v = 0.4 + tw * 0.35 + pr * 0.2
            out[idx] = quant(RA[name], t_of(v, 0.5), bay)
        elif name in ('ember', 'glass'):
            if name == 'ember':
                v = 0.55 + fbm(x * 30, y * 30, z * 30, 2, 101) * 0.5 + smooth(0.0, 0.08, z - cfg.get('ember_z', 0)) * 0.0
                out[idx] = quant(RA['ember'], np.clip(v, 0, 1), bay)
            else:
                v = 0.6 + fbm(x * 12, y * 12, z * 12, 2, 103) * 0.3
                out[idx] = quant(RA['lamp'], np.clip(v, 0, 1), bay)
        elif name == 'soot':
            v = 0.3 + fbm(x * 20, y * 20, z * 20, 2, 105) * 0.3 + c.W[idx] * 0.2
            out[idx] = quant(RA['soot'], t_of(v, 0.4), bay)
            ash = smooth(0.4, 0.6, fbm(x * 30, y * 30, z * 30, 2, 107)) * (up > 0.5)
            a = np.nonzero(ash > bay2 + 0.5)[0]
            out[idx[a]] = quant(RA['stone'], np.full(len(a), 0.75), bay[a])
        elif name in ('moss', 'sphag'):
            n1 = fbm(x * 6, y * 6, z * 6, 4, 111)
            hum = fbm(x * 40, y * 40, z * 40, 2, 113)
            v = 0.5 + n1 * 0.3 + hum * 0.2
            t = t_of(v, 0.5)
            if name == 'moss':
                out[idx] = quant(RA['moss'], t, bay)
            else:
                sel = smooth(-0.15, 0.25, fbm(x * 1.3 + 3, y * 1.3, z * 1.3, 3, 115))
                mixramp(out, idx, sel, 'sphag', 'sphag_g', t, bay2)
        elif name == 'pad':
            vein = smooth(0.06, 0.0, np.abs(np.sin(np.arctan2(y - _pc(cfg, pid, 1), x - _pc(cfg, pid, 0)) * 11)))
            rr = np.hypot(x - _pc(cfg, pid, 0), y - _pc(cfg, pid, 1))
            v = 0.5 + pr * 0.25 + fbm(x * 8, y * 8, z * 8, 3, 121) * 0.2 - vein * 0.25 * (rr > 0.06)
            t = t_of(v, 0.5)
            under = (up < 0.25)
            out[idx] = quant(RA['pad'], t, bay)
            u = np.nonzero(under)[0]
            out[idx[u]] = quant(RA['pad_under'], t[u], bay[u])
            blot = smooth(0.35, 0.55, fbm(x * 5, y * 5, z, 3, 123)) * (~under)
            mixramp(out, idx, blot * 0.9, 'pad', 'pad_under', t, bay2)
        elif name == 'flower':
            v = 0.45 + smooth(0, 1, (z - cfg.get('fl_z', 0)) / max(cfg.get('fl_h', 1), 1e-3)) * 0.0 + pr * 0.3 + fbm(x * 30, y * 30, z * 30, 2, 131) * 0.15
            tip = cfg.get('fl_tip', 0.0)
            t = t_of(v + 0.25, 0.45)
            out[idx] = quant(RA['flower'], t, bay)
        elif name == 'pitcher':
            vein = smooth(0.15, 0.0, np.abs(fbm(across * 18, along * 3, pid * 0.3, 3, 141)))
            base = smooth(cfg.get('pit_z1', 0.45), cfg.get('pit_z0', 0.1), z)
            v = 0.45 + pr * 0.2 + vein * 0.4
            t = t_of(v, 0.5)
            out[idx] = quant(RA['pitcher'], t, bay)
            mixramp(out, idx, base * 1.3 - vein * 0.5, 'pitcher', 'pitcher_base', t, bay2)
        elif name == 'sundew':
            v = 0.4 + pr * 0.3 + smooth(0.6, 0.8, fbm(x * 60, y * 60, z * 60, 1, 151)) * 0.6
            out[idx] = quant(RA['sundew'], t_of(v, 0.4), bay)
        elif name == 'lichen':
            v = 0.5 + fbm(x * 20, y * 20, z * 20, 2, 161) * 0.3
            out[idx] = quant(RA['lichen'], t_of(v), bay)
        elif name == 'sedge':
            v = 0.5 + pr * 0.4 + fbm(across * 40, along * 2, pid * 0.2, 2, 171) * 0.2
            out[idx] = quant(RA['sedge'], t_of(v, 0.5), bay)
        elif name == 'hide':
            v = 0.5 + fbm(x * 10, y * 10, z * 10, 3, 181) * 0.25 + pr * 0.2
            out[idx] = quant(RA['hide'], t_of(v, 0.5), bay)
    img = out.reshape(S, S, 3)[::-1]          # bake rows run bottom-up; PNG rows top-down
    return np.ascontiguousarray(img)


def _pc(cfg, pid, k):
    """Centre of a part (the kit records every part's centroid)."""
    cs = cfg.get('centres')
    if cs is None or len(cs) == 0:
        return 0.0
    arr = np.asarray(cs, np.float64)[:, k]
    return arr[np.clip(pid, 0, len(arr) - 1)]


def save_png(img, path):
    """Palette pixels only, so the atlas saves as an indexed PNG (about a third of the RGB size)."""
    from PIL import Image
    im = Image.fromarray(img, 'RGB')
    n = len(im.getcolors(1 << 20) or [])
    if n <= 256:
        im = im.convert('P', palette=Image.ADAPTIVE, colors=256)
    im.save(path, optimize=True)
