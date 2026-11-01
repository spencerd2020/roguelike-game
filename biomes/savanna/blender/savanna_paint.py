"""Painter for the savanna kit: turns per-texel bake data into palette pixels.

Layers, in order, per texel: slot ramp, per-part tone, the slot's own pattern (lifts, weave, grain, granite speckle...),
wear from occlusion and height, the painted top light (sky bake), then an ordered dither onto the ramp's swatches.
Only palette swatches come out, so the sheet reads as painted, not photographed.
"""
import zlib
import numpy as np

RAMPS = {
    'clay':  ['#4f2418', '#6b321f', '#8a4428', '#a55733', '#bd6d40', '#d18a55', '#dfa672'],
    'lime':  ['#6f6658', '#968c7b', '#b8ae9a', '#d2c9b4', '#e4ddca', '#f1ece0'],
    'thatch': ['#3b2c16', '#5a4521', '#7b612e', '#9b7d3b', '#b9984a', '#d2b25f', '#e3c97d'],
    'wood':  ['#24180f', '#382517', '#4f3520', '#68472b', '#835c38', '#9d7449'],
    'stone': ['#3f3734', '#584d48', '#72665e', '#8c7f75', '#a6988c', '#bfb2a4', '#d4c9bc'],
    'bark':  ['#2c2724', '#433b35', '#5c524a', '#776b5f', '#928575', '#aa9d8a'],
    'leaf':  ['#26301c', '#374326', '#4b5830', '#606e39', '#7a8644', '#95a052'],
    'pod':   ['#5a2a10', '#7d3c16', '#a3521c', '#c76f26', '#e09440'],
    'cloth': ['#22263d', '#323a5a', '#47517a', '#8a3a28', '#b0532f', '#d47b45', '#e7c08a'],
    'grain': ['#6e5222', '#8f6e2f', '#b08a3a', '#cba650', '#e0c26c', '#efda98'],
    'ash':   ['#2b2826', '#45403c', '#615a54', '#7c746c', '#968d84'],
    'floor': ['#3e2419', '#523022', '#673e2b', '#7b4d34', '#8f5e40'],
    'rope':  ['#3e2f1b', '#5b4628', '#7a6037', '#987b48', '#b4975c'],
    'ember': ['#ff8a2a'],
}
hexrgb = lambda h: [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
RAMPS = {k: np.array([hexrgb(c) for c in v], np.float32) for k, v in RAMPS.items()}
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16 - 0.5)


def _hash(ix, iy, iz, s):
    h = (ix * 374761393 + iy * 668265263 + iz * 1442695041 + s * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def noise3(p, s=0):
    """Value noise in 3D, -1..1. p: (n, 3)."""
    fl = np.floor(p)
    f = p - fl
    f = f * f * (3 - 2 * f)
    i = fl.astype(np.int64)
    out = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                out = out + w * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, s)
    return out * 2 - 1


def fbm(p, oct=4, s=0):
    v, a, t = 0, 0.5, 0
    for o in range(oct):
        v = v + a * noise3(p * (2 ** o), s + o * 31)
        t += a
        a *= 0.5
    return v / t


def cells(p, s=0):
    """Distance to the nearest and second nearest feature point (3D worley, 27 cells)."""
    fl = np.floor(p).astype(np.int64)
    f1 = np.full(len(p), 9.0, np.float32)
    f2 = np.full(len(p), 9.0, np.float32)
    idc = np.zeros(len(p), np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = fl + np.array([dx, dy, dz])
                fp = c + np.stack([_hash(c[:, 0], c[:, 1], c[:, 2], s + k) for k in (1, 2, 3)], 1)
                d = np.linalg.norm(fp - p, axis=1)
                hid = _hash(c[:, 0], c[:, 1], c[:, 2], s + 9)
                closer = d < f1
                f2 = np.where(closer, f1, np.minimum(f2, d))
                idc = np.where(closer, hid, idc)
                f1 = np.where(closer, d, f1)
    return f1, f2, idc


sm = lambda a, b, x: np.clip((x - a) / (b - a), 0, 1) ** 2 * (3 - 2 * np.clip((x - a) / (b - a), 0, 1))


def paint_atlas(E, P, N, A, L, SLOTS, asset, seed, info):
    S = E.shape[0]
    slot = np.clip((E[..., 0] * 32 - 0.5).round().astype(np.int32), 0, len(SLOTS) - 1)
    tone = E[..., 1] * 2 - 1
    valid = (np.abs(N[..., :3] * 2 - 1).sum(-1) > 0.3)
    pos = P[..., :3]
    nrm = N[..., :3] * 2 - 1
    ao = A[..., 0]
    lig = np.clip(L[..., 0] / max(np.percentile(L[..., 0][valid], 98), 1e-3), 0, 1.2)
    out = np.zeros((S, S, 3), np.float32)
    yy, xx = np.mgrid[0:S, 0:S]
    bay = BAYER[yy & 3, xx & 3]
    del yy, xx
    R = info.get('R', 3.0)
    floor = info.get('floor', 0.0)
    H = info.get('H', 2.4)
    # flat views, painted in chunks so a 4K sheet fits in memory
    slot, tone, valid, ao, lig, bay = (x.reshape(-1) for x in (slot, tone, valid, ao, lig, bay))
    pos, nrm, out = pos.reshape(-1, 3), nrm.reshape(-1, 3), out.reshape(-1, 3)
    for si, name in enumerate(SLOTS):
        allm = np.flatnonzero((slot == si) & valid)
        for m in np.array_split(allm, len(allm) // 1000000 + 1):
            if len(m) == 0:
                continue
            p = pos[m].astype(np.float64)
            n = nrm[m]
            t = tone[m] * 0.08
            a = ao[m]
            lt = lig[m]
            rr = np.hypot(p[:, 0], p[:, 1])
            ang = np.arctan2(p[:, 1], p[:, 0])
            outward = (n[:, 0] * p[:, 0] + n[:, 1] * p[:, 1]) / np.maximum(rr, 1e-3)
            ramp = RAMPS[name]
            alt = None                                  # optional second ramp chosen per texel
            if name == 'clay':
                g = fbm(p * 1.6, 4, 11)
                fine = fbm(p * 9, 2, 12)
                v = 0.5 + g * 0.22 + fine * 0.08 + t
                if asset in ('house', 'greathouse', 'granary'):
                    # rammed-earth lifts: thin dark seams every 0.42 m, a little wavy
                    z = p[:, 2] - floor + fbm(p * 0.8, 2, 13) * 0.04
                    seam = sm(0.035, 0.0, np.abs(((z / 0.42) % 1) - 0.5) * 0.42 - 0.17)
                    v -= seam * 0.25
                    # rain streaks run down from the wall head
                    streak = sm(0.3, 0.8, fbm(np.stack([ang * 6, ang * 6, p[:, 2] * 0.4], 1), 3, 14)) * sm(floor + H, floor + 0.6, p[:, 2])
                    v -= streak * 0.12 * (outward > 0.2)
                    # splash: darker, redder footing zone near the ground
                    v -= sm(floor + 0.45, floor, p[:, 2]) * 0.12
                if asset == 'mound':
                    flutes = np.abs(np.sin(ang * 4.5 + p[:, 2] * 0.6 + g * 2))
                    v += (flutes - 0.5) * 0.2 - sm(0.5, -0.2, p[:, 2]) * 0.1
                    pores = sm(0.12, 0.05, cells(p * 6, 15)[0])
                    v -= pores * 0.25
            elif name == 'lime':
                g = fbm(p * 2.2, 4, 21)
                v = 0.62 + g * 0.12 + t * 0.5
                # soot: a hearth darkens the dome inside towards the oculus, and the wall above head height
                if asset in ('house', 'greathouse'):
                    soot = sm(floor + 1.7, floor + H + 1.4, p[:, 2]) * (0.55 + 0.25 * fbm(p * 1.2, 3, 22))
                    v -= soot * 0.75
                    # the wall's lower metre is a clay dado: switch ramp below a wavy line, inside only
                    dado = p[:, 2] < floor + 0.9 + fbm(np.stack([ang * 5, ang * 5, p[:, 2] * 0], 1), 2, 23) * 0.05
                    alt = dado & (rr > R - 0.6) & (p[:, 2] > floor + 0.02)
                # chipped lime shows the clay under it near edges and low down
                chip = sm(0.35, 0.6, fbm(p * 5, 3, 24)) * sm(floor + 0.9, floor, p[:, 2])
                v -= chip * 0.3
            elif name == 'thatch':
                # bundles laid in overlapping courses down the slope: strands run along the radius (long streaks), each course's
                # lower edge is a lit lip over the shadowed top of the next one, and bundle ends break the edge
                sw = rr * ang
                bundle = fbm(np.stack([sw * 2.2, sw * 2.2, rr * 0.3], 1), 2, 34)
                course = (rr / 0.38 + bundle * 0.25) % 1
                strand = fbm(np.stack([sw * 34, sw * 34, rr * 1.2], 1), 3, 32)
                under = n[:, 2] < -0.2
                v = 0.5 + strand * 0.42 + bundle * 0.12 + t
                v += sm(0.55, 1.0, course) * 0.16 - sm(0.3, 0.0, course) * 0.3
                v = np.where(under, 0.32 + strand * 0.25 + t, v)        # the underside is shaded and older
                weath = sm(0.1, 0.5, fbm(p * 0.6, 3, 33)) * (~under)
                v -= weath * 0.14
                alt = (fbm(p * 0.9, 3, 35) > 0.35) & ~under              # patches of newer, paler bundles from a repair
            elif name == 'wood':
                ax = np.where(np.abs(n[:, 2]) > 0.7, 0, 1)
                g = fbm(np.stack([p[:, 0] * 6, p[:, 1] * 6, p[:, 2] * 0.6], 1), 4, 41)
                rings = np.sin((p[:, 0] * 31 + p[:, 1] * 23 + g * 6))
                v = 0.48 + g * 0.22 + rings * 0.06 + t * 1.5
                v -= sm(0.4, 0.0, p[:, 2] - floor) * 0.15
            elif name == 'stone':
                # dressed blocks on the house footings; on the outcrop only a few long sheet joints, not a paving
                f1, f2, cid = cells(p * (0.32 if asset in ('kopje', 'boulders') else 1.1), 51)
                joint = sm(0.07, 0.015, f2 - f1)
                if asset in ('kopje', 'boulders'):
                    joint = joint * sm(0.05, 0.35, fbm(p * 0.5, 2, 58))
                g = fbm(p * 2.0, 4, 52)
                speck = fbm(p * 22, 2, 53)
                v = 0.52 + g * 0.16 + (cid - 0.5) * 0.12 + speck * 0.12 + t - joint * 0.3
                # exfoliation: pale shells peeling off the rounded tops
                if asset in ('kopje', 'boulders'):
                    shell = sm(0.1, 0.4, fbm(p * 0.45, 3, 54)) * np.clip(n[:, 2], 0, 1)
                    v += shell * 0.14
                    # dark seep stains run down from the tops
                    seep = sm(0.35, 0.75, fbm(np.stack([p[:, 0] * 1.4, p[:, 1] * 1.4, p[:, 2] * 0.15], 1), 3, 55)) * (np.abs(n[:, 2]) < 0.6)
                    v -= seep * 0.22
                    # orange lichen on the shaded flanks
                    lich = (fbm(p * 1.3, 4, 56) + fbm(p * 7, 2, 57) * 0.3 > 0.42) & (n[:, 2] > -0.3) & (joint < 0.3)
                    alt = lich
            elif name == 'bark':
                fiss = np.abs(fbm(np.stack([ang * 3.2, ang * 3.2, p[:, 2] * 0.35], 1) if asset == 'bottle'
                              else np.stack([p[:, 0] * 4, p[:, 1] * 4, p[:, 2] * 0.5], 1), 4, 61))
                v = 0.5 + (0.25 - fiss) * 0.9 + t + fbm(p * 8, 2, 62) * 0.08
                if asset == 'bottle':
                    # smooth grey skin with horizontal stretch scars and an elephant-wrinkle band at the base
                    v = 0.58 + fbm(p * 1.4, 3, 63) * 0.15 - sm(0.06, 0.0, np.abs(np.sin(p[:, 2] * 7 + fbm(p, 2, 64) * 3))) * 0.12 + t
                    v -= sm(1.2, 0.0, p[:, 2]) * np.abs(np.sin(p[:, 2] * 18)) * 0.15
            elif name == 'leaf':
                g = fbm(p * 2.6, 3, 71)
                clump = sm(-0.1, 0.4, fbm(p * 7, 2, 72))
                v = 0.42 + g * 0.18 + clump * 0.18 + t * 1.5
                v += np.clip(n[:, 2], 0, 1) * 0.12                # sun-bleached tops
                v -= np.clip(-n[:, 2], 0, 1) * 0.25               # dark undersides
                # dry season: some leaves have turned
                alt = (fbm(p * 1.1, 3, 73) > 0.38) & (np.abs(g) < 0.5)
            elif name == 'cloth':
                # woven mats: bands of indigo or madder (per part), a pale stripe every few bands, a fine weave
                stripe = (np.floor((p[:, 0] * 0.7 + p[:, 1] * 0.7) * 7) % 5)
                weave = np.sin(p[:, 0] * 160) * np.sin(p[:, 1] * 160) * 0.08
                madder = tone[m] > 0
                v = 0.55 + weave + t + (stripe == 0) * 0.35 - (stripe == 2) * 0.2
            elif name == 'grain':
                gr = cells(p * 30, 81)[0]
                v = 0.55 + sm(0.3, 0.05, gr) * 0.3 + fbm(p * 4, 2, 82) * 0.1
            elif name == 'pod':
                v = 0.5 + fbm(p * 5, 3, 91) * 0.25 + t * 2
            elif name == 'ash':
                v = 0.4 + fbm(p * 12, 3, 101) * 0.3 - sm(0.3, 0.0, rr) * 0.25
            elif name == 'floor':
                # packed earth, swept in arcs, darker round the hearth and worn pale on the path from the door
                sweep = np.sin(rr * 9 + fbm(p * 1.5, 2, 111) * 3) * 0.05
                v = 0.55 + fbm(p * 3, 4, 112) * 0.14 + sweep - sm(1.2, 0.3, rr) * 0.2
                da = np.radians(info.get('door_angle_deg', 90))
                path = sm(0.6, 0.0, np.abs(np.sin(ang - da)) * rr) * (np.cos(ang - da) > 0)
                v += path * 0.15
            elif name == 'rope':
                twist = np.sin((p[:, 0] + p[:, 1] + p[:, 2]) * 70) * 0.12
                v = 0.5 + twist + fbm(p * 6, 2, 121) * 0.1 + t
            else:
                v = np.full(len(p), 0.8)
            # wear from occlusion (cavities collect dust and shade) and the painted top light
            light = 0.5 * lt + 0.5 * a
            val = np.clip(v * 0.62 + (light - 0.55) * 0.55 + 0.19, 0, 1)
            if name == 'cloth':
                # indigo swatches 0..2 (+ the pale 6), madder 3..5: pick a sub-ramp per part, pale stripe from the top swatch
                lo = np.where(madder, 3, 0)
                k = np.clip(np.round(lo + 0.6 + val * 1.8 + bay[m] * 0.5), lo, lo + 2).astype(int)
                k = np.where(val > 0.82, 6, k)
            else:
                k = np.clip(np.round(val * (len(ramp) - 1) + bay[m] * 0.5), 0, len(ramp) - 1).astype(int)
            col = ramp[k]
            if alt is not None and alt.any():
                if name == 'lime':
                    r2 = RAMPS['clay']
                    k2 = np.clip(np.round((val * 0.8 + 0.1) * (len(r2) - 1) + bay[m] * 0.5), 0, len(r2) - 1).astype(int)
                elif name == 'stone':
                    r2 = RAMPS['pod']
                    k2 = np.clip(np.round((val * 0.8 + 0.2) * (len(r2) - 1) + bay[m] * 0.5), 0, len(r2) - 1).astype(int)
                elif name == 'thatch':
                    r2 = RAMPS['grain']
                    k2 = np.clip(np.round((val * 0.9 + 0.05) * (len(r2) - 1) + bay[m] * 0.5), 0, len(r2) - 1).astype(int)
                else:
                    r2 = RAMPS['thatch']
                    k2 = np.clip(np.round((val * 0.9 + 0.05) * (len(r2) - 1) + bay[m] * 0.5), 0, len(r2) - 1).astype(int)
                col = np.where(alt[:, None], r2[k2], col)
            if name in ('house', 'greathouse'):
                pass
            out[m] = col
            # lime wash on the outside of the house: a frieze round the wall head and a frame round the door
            if name == 'clay' and asset in ('house', 'greathouse'):
                z = p[:, 2]
                top = floor + H
                band = (z > top - 0.42) & (z < top - 0.06) & (outward > 0.3) & (rr > R - 0.05)
                # a row of clay-coloured triangles left unwashed in the band (the house's own mark, seeded per house)
                nteeth = 18 + (zlib.crc32(seed.encode()) % 7) * 2
                u = (ang / (2 * np.pi) * nteeth) % 1
                zz = (z - (top - 0.42)) / 0.36
                tooth = zz < (1 - np.abs(u * 2 - 1)) * 0.75
                wash = band & ~tooth
                da = np.radians(info.get('door_angle_deg', 90))
                dd = np.abs(np.angle(np.exp(1j * (ang - da)))) * rr
                frame = (dd < 0.95) & (dd > 0.42) & (z < floor + 2.2) & (outward > 0.3) & (rr > R - 0.05)
                wash |= frame
                if wash.any():
                    lr = RAMPS['lime']
                    kl = np.clip(np.round((val * 0.5 + 0.45) * (len(lr) - 1) + bay[m] * 0.5), 0, len(lr) - 1).astype(int)
                    c2 = out[m]
                    c2[wash] = lr[kl[wash]]
                    out[m] = c2
        # texels that fall outside every island: the clay colour, so a seam shows clay, never black
    out[~valid] = RAMPS['clay'][2]
    out = out.reshape(S, S, 3)
    # a byte image stores what it is given, so the swatch values go in unchanged
    return out
