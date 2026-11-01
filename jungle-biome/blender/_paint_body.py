

HOUSES = ('stilthouse', 'longhouse', 'granary', 'shrine', 'waterwheel')


def _u(p, n):
    """The horizontal coordinate along a surface: x on faces that look along y, y on faces that look along x."""
    return np.where(np.abs(n[:, 0]) > np.abs(n[:, 1]), p[:, 1], p[:, 0])


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
    floor = info.get('floor', 0.0)
    Hw = info.get('Hw', 2.5)
    house = asset in HOUSES
    slot, tone, valid, ao, lig, bay = (x.reshape(-1) for x in (slot, tone, valid, ao, lig, bay))
    pos, nrm, out = pos.reshape(-1, 3), nrm.reshape(-1, 3), out.reshape(-1, 3)
    W2 = info.get('W', 6) / 2
    D2 = info.get('D', 4.6) / 2
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
            ramp = RAMPS[name]
            alt, alt_name, alt_lift = None, None, 0.0
            inside = (np.abs(p[:, 0]) < W2 - 0.02) & (np.abs(p[:, 1]) < D2 - 0.02) & (p[:, 2] > floor) if house else np.zeros(len(p), bool)
            if name == 'weave':
                # twill-woven split bamboo: strips 3.5 cm wide crossing at 45 degrees, two over and two under, each strip
                # rounded (lit middle, dark edges), the gaps between them dark
                u = _u(p, n)
                z = p[:, 2]
                if asset == 'waterwheel':
                    z = p[:, 0] * 0.7 + p[:, 2] * 0.7
                w = 0.035
                d1 = (u + z) / w
                d2 = (u - z) / w
                i1, f1 = np.floor(d1), d1 - np.floor(d1)
                i2, f2 = np.floor(d2), d2 - np.floor(d2)
                over = ((i1 + i2) % 4) < 2
                f = np.where(over, f1, f2)
                strip = np.where(over, i1, i2)
                round_ = np.sin(np.pi * f) ** 0.6
                v = 0.32 + round_ * 0.38 + (_hash(strip.astype(np.int64), 0, 3, 5) - 0.5) * 0.18 + t
                v -= sm(0.12, 0.0, f) * 0.25 + sm(0.88, 1.0, f) * 0.25
                v += fbm(p * 1.5, 3, 11) * 0.1
                if house:
                    # smoke darkens the inside from head height up, rain and splash the outside low down
                    soot = sm(floor + 1.2, floor + Hw + 0.6, p[:, 2]) * inside * (0.6 + 0.3 * fbm(p * 0.9, 3, 12))
                    v -= soot * 0.45
                    v -= sm(floor + 0.5, floor, p[:, 2]) * (~inside) * 0.12
                    # panels repaired with fresh, paler strips
                    alt = (fbm(p * 0.7, 2, 13) > 0.42) & ~inside
                    alt_name, alt_lift = 'dry', 0.15
            elif name == 'thatch':
                # palm-leaf thatch in courses: each course's lower edge is a lit lip over a shadow, the leaf ribs run down
                # the slope, the lowest courses carry moss, and the underside is sooted from the hearth
                u = _u(p, n)
                z = p[:, 2]
                course = (z / 0.17 + fbm(p * 0.6, 2, 31) * 0.3) % 1
                rib = fbm(np.stack([u * 46, u * 46, z * 1.6], 1), 3, 32)
                bundle = fbm(np.stack([u * 3, u * 3, z * 0.6], 1), 2, 34)
                under = n[:, 2] < -0.25
                v = 0.5 + rib * 0.34 + bundle * 0.12 + t
                v += sm(0.6, 1.0, course) * 0.14 - sm(0.28, 0.0, course) * 0.32
                v -= sm(0.2, 0.6, fbm(p * 0.35, 3, 33)) * 0.12
                if house:
                    ze = info.get('eave', floor + 1.8)
                    zr = info.get('ridge', ze + 3)
                    v = np.where(under, 0.3 + rib * 0.2 - sm(ze, zr, z) * 0.15 + t, v)
                    alt = (~under) & (z < ze + (zr - ze) * 0.35) & (fbm(p * 0.9, 3, 35) + fbm(p * 5, 2, 36) * 0.3 > 0.25)
                    alt_name, alt_lift = 'moss', -0.05
            elif name == 'wood':
                g = fbm(np.stack([p[:, 0] * 5, p[:, 1] * 5, p[:, 2] * 0.5], 1), 4, 41)
                v = 0.48 + g * 0.25 + np.sin(p[:, 0] * 23 + p[:, 1] * 19 + g * 7) * 0.06 + t * 1.5
                if house:
                    v -= sm(0.6, 0.0, p[:, 2]) * 0.2          # mud splash at the foot of the posts
                    v -= sm(floor + 1.4, floor + Hw + 1, p[:, 2]) * inside * 0.2
                if asset == 'shrine':
                    v += 0.08
            elif name == 'plank':
                # boards along x, each its own tone, dark seams, grain along the board, a worn path from the door
                along_y = asset == 'waterwheel'
                bw = 0.19
                bi = np.floor(p[:, 1] / bw + 0.5 * (np.abs(n[:, 2]) < 0.5) * 0)
                fy = p[:, 1] / bw - np.floor(p[:, 1] / bw)
                gr = fbm(np.stack([p[:, 0] * 1.2, bi * 7.0, p[:, 1] * 30], 1), 4, 51)
                v = 0.5 + gr * 0.2 + (_hash(bi.astype(np.int64), 0, 1, 7) - 0.5) * 0.22 + t
                v -= (sm(0.07, 0.0, fy) + sm(0.93, 1.0, fy)) * 0.35 * (np.abs(n[:, 2]) > 0.5)
                # board ends every 1.6 to 2.4 m, staggered
                ends = ((p[:, 0] + _hash(bi.astype(np.int64), 3, 1, 8) * 2.0) % 2.1) < 0.025
                v -= ends * 0.3
                if house:
                    v += sm(1.5, 0.0, np.abs(p[:, 1] - info.get('markers', {}).get('door', [0, 0])[1] * 0)) * 0.0
                    v -= sm(1.5, 0.3, np.hypot(p[:, 0] - info.get('markers', {}).get('hearth', [0, 0, 0])[0], p[:, 1])) * 0.15
            elif name == 'bamboo':
                # culms: nodes as dark rings with a pale waxy band under them, fine streaks along the culm
                s = p[:, 0] + p[:, 1] + p[:, 2]
                if asset == 'bamboo':
                    s = p[:, 2] + fbm(p * 0.3, 1, 61) * 0.1
                period = 0.32 if house else 0.38
                f = (s / period) % 1
                node = sm(0.05, 0.0, np.abs(f - 0.5) - 0.44) if False else sm(0.035, 0.0, np.minimum(f, 1 - f))
                wax = sm(0.0, 0.08, f) * sm(0.2, 0.08, f)
                streak = fbm(np.stack([ang * 9, ang * 9, p[:, 2] * 0.4], 1), 3, 62) if asset == 'bamboo' else fbm(p * 7, 2, 62)
                v = 0.55 + streak * 0.18 + wax * 0.12 - node * 0.45 + t * 1.5
                if asset == 'bamboo':
                    v -= sm(2.0, 0.0, p[:, 2]) * 0.15
                    alt = (fbm(p * 0.8, 2, 63) > 0.3) & (p[:, 2] < 4)     # some old culms have dried to straw
                    alt_name, alt_lift = 'dry', 0.1
                else:
                    alt = np.ones(len(p), bool)                           # cut bamboo in a house has dried to straw
                    alt_name, alt_lift = 'weave', 0.0
                    v -= sm(floor + 1.3, floor + Hw + 2, p[:, 2]) * inside * 0.35
            elif name == 'stone':
                f1, f2, cid = cells(p * 0.8, 71)
                g = fbm(p * 0.6, 4, 72)
                pit = sm(0.1, 0.02, cells(p * 5, 73)[0])
                v = 0.55 + g * 0.18 + (cid - 0.5) * 0.06 - pit * 0.12 + t
                if asset == 'karst':
                    # black algae streaks and rust-orange stains run down the sheer faces; faint bedding lines; the
                    # overhangs are dark and wet; moss and ferns take every upward face
                    streak = fbm(np.stack([ang * 14, ang * 14, p[:, 2] * 0.035], 1), 4, 74)
                    v -= sm(0.05, 0.45, streak) * 0.45
                    rust = sm(0.25, 0.55, fbm(np.stack([ang * 6, ang * 6, p[:, 2] * 0.05], 1), 3, 75)) * (np.abs(n[:, 2]) < 0.6)
                    v -= sm(0.03, 0.0, np.abs(((p[:, 2] / 1.3 + g * 0.6) % 1) - 0.5) - 0.47) * 0.12
                    v += np.clip(n[:, 2], 0, 1) * 0.12 - np.clip(-n[:, 2], 0, 1) * 0.25
                    alt = (n[:, 2] > 0.45 - fbm(p * 0.5, 2, 76) * 0.3) | (rust > 0.5)
                    alt_name = 'moss'
                    alt_rust = rust > 0.5
                elif asset == 'boulders':
                    v -= sm(0.3, 0.0, p[:, 2]) * 0.15                    # wet foot
                    alt = (n[:, 2] > 0.55) & (fbm(p * 2, 3, 77) > -0.1)
                    alt_name = 'moss'
                else:
                    v -= sm(0.5, 0.0, p[:, 2]) * 0.1
            elif name == 'moss':
                v = 0.45 + fbm(p * 4, 4, 81) * 0.3 + fbm(p * 18, 2, 82) * 0.12 + np.clip(n[:, 2], 0, 1) * 0.1 + t
            elif name == 'bark':
                if asset == 'banyan':
                    flute = np.abs(np.sin(ang * 11 + fbm(p * 0.4, 2, 91) * 4))
                    v = 0.5 + (flute - 0.5) * 0.3 + fbm(p * 2, 3, 92) * 0.15 + t
                else:
                    # smooth pale bark with rings of lenticels, scaling plates low down, and pale lichen blotches
                    v = 0.56 + fbm(np.stack([ang * 3, ang * 3, p[:, 2] * 0.25], 1), 4, 93) * 0.2 + t
                    v -= sm(0.08, 0.0, np.abs(((p[:, 2] / 0.55) % 1) - 0.5) - 0.42) * 0.08
                    v -= sm(3.0, 0.0, p[:, 2]) * 0.18
                alt = fbm(p * 1.1, 3, 94) + fbm(p * 6, 2, 95) * 0.3 > 0.42
                alt_name, alt_lift = 'stone', 0.25
                v -= np.clip(-n[:, 2], 0, 1) * 0.12
            elif name in ('leaf', 'frond'):
                g = fbm(p * 1.6, 3, 101)
                fine = fbm(p * 9, 2, 102)
                v = 0.45 + g * 0.16 + fine * 0.1 + t * 2.0
                v += np.clip(n[:, 2], 0, 1) * 0.12 - np.clip(-n[:, 2], 0, 1) * 0.18
                if name == 'frond':
                    # parallel veins across the blade (banana), and yellowed tips and edges on older leaves
                    v += np.sin((p[:, 0] * 0.7 + p[:, 1] * 0.7 + p[:, 2]) * 70) * 0.04
                    alt = (fbm(p * 1.3, 2, 103) > 0.35) & (asset != 'treefern')
                    alt_name, alt_lift = 'dry', 0.1
                else:
                    # new growth: a few bright flushes of young leaves on the crowns' tops
                    alt = (fbm(p * 0.5, 2, 104) > 0.45) & (n[:, 2] > 0.2)
                    alt_name, alt_lift = 'frond', 0.05
            elif name == 'clay':
                v = 0.5 + fbm(p * 6, 3, 111) * 0.18 + t
                v -= sm(0.6, 0.1, np.hypot(p[:, 0] - info.get('markers', {}).get('hearth', [0, 0, 0])[0], p[:, 1])) * 0.25
            elif name == 'cloth':
                stripe = np.floor(p[:, 2] * 22) % 6
                v = 0.5 + (stripe == 0) * 0.4 - (stripe == 3) * 0.2 + t
            elif name == 'rope':
                v = 0.5 + np.sin((p[:, 0] + p[:, 1] + p[:, 2]) * 80) * 0.12 + fbm(p * 6, 2, 121) * 0.1 + t
            elif name == 'lacquer':
                v = 0.6 + fbm(p * 3, 3, 131) * 0.15 + t - sm(0.2, 0.6, fbm(p * 1.5, 3, 132)) * 0.2
            elif name == 'ash':
                v = 0.45 + fbm(p * 14, 3, 141) * 0.3
            elif name == 'root':
                v = 0.5 + fbm(np.stack([p[:, 0] * 9, p[:, 1] * 9, p[:, 2] * 1.0], 1), 3, 151) * 0.3 + t
                alt = (fbm(p * 0.8, 2, 152) > 0.35) & (n[:, 2] > -0.2)
                alt_name, alt_lift = 'moss', 0.0
            elif name == 'dry':
                v = 0.5 + fbm(p * 5, 3, 161) * 0.22 + np.sin((p[:, 0] + p[:, 1]) * 60) * 0.04 + t
            else:
                v = np.full(len(p), 0.8)
            light = 0.5 * lt + 0.5 * a
            val = np.clip(v * 0.62 + (light - 0.55) * 0.6 + 0.19, 0, 1)
            if name == 'cloth':
                madder = tone[m] > 0
                lo = np.where(madder, 3, 0)
                k = np.clip(np.round(lo + 0.6 + val * 1.8 + bay[m] * 0.5), lo, lo + 2).astype(int)
                k = np.where(val > 0.8, 6, k)
            else:
                k = np.clip(np.round(val * (len(ramp) - 1) + bay[m] * 0.5), 0, len(ramp) - 1).astype(int)
            col = ramp[k]
            if alt is not None and alt.any():
                r2 = RAMPS[alt_name]
                k2 = np.clip(np.round(np.clip(val + alt_lift, 0, 1) * (len(r2) - 1) + bay[m] * 0.5), 0, len(r2) - 1).astype(int)
                col = np.where(alt[:, None], r2[k2], col)
                if name == 'stone' and asset == 'karst':
                    r3 = RAMPS['clay']
                    k3 = np.clip(np.round((val * 0.8 + 0.2) * (len(r3) - 1) + bay[m] * 0.5), 0, len(r3) - 1).astype(int)
                    col = np.where(alt_rust[:, None], r3[k3], col)
            out[m] = col
    out[~valid] = RAMPS['wood'][2]
    return out.reshape(S, S, 3)
