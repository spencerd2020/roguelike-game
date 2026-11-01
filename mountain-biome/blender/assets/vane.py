"""Vanehold building grammar: coursed banded-stone walls, steep slate roofs on a real timber frame, wind wheels.

Shared by the house and the lookout tower. Coordinates: Blender, Z up, the front (door) wall faces -Y, feet on z = 0.
Every opening is snapped to the stone courses, so jambs, sills and lintels sit on real joints.
"""
import math
import zlib

from mathutils import Matrix, Vector

from mkit import V, frame

STRATA = (0, 0, 1, 0, 2, 0, 1, 1, 0, 2)   # slate, rose, cream bands, read up the wall


def courses(rng, z0, H, lo=0.18, hi=0.31):
    out, z = [], z0
    while z < z0 + H - 1e-6:
        h = rng.uniform(lo, hi)
        if z + h > z0 + H - 0.12:
            h = z0 + H - z
        out.append((z, h))
        z += h
    return out


def snap(cs, z):
    """The course joint nearest z."""
    tops = [c[0] for c in cs] + [cs[-1][0] + cs[-1][1]]
    return min(tops, key=lambda t: abs(t - z))


def band_of(rng, ci, base):
    """Stratum of course ci: bands of two to four courses, read like the strata of the mountain."""
    k, n, i = base, 0, 0
    while True:
        n += 2 + (zlib.crc32(f'{base}:{i}'.encode()) % 3)
        if ci < n:
            return STRATA[(base + i) % len(STRATA)]
        i += 1


def rect_walls(K, rng, ctx, L, W, t, cs, openings, z0, quoin_k=2, e=0.028, name='wall'):
    """Four walls of a rectangle (outer size L x W, thickness t) laid in courses. openings: {wall: [(u0, u1, za, zb)]}
    with u along the wall (x for front/back, y for left/right). Returns lintel spans for the frame builder."""
    strat = ctx.setdefault('strat', {})
    base = rng.randrange(10)
    lintels = []
    walls = {
        'front': (lambda u, h, l, zc: ((u, -W / 2 + t / 2, zc), (l, t, h))),
        'back': (lambda u, h, l, zc: ((u, W / 2 - t / 2, zc), (l, t, h))),
        'left': (lambda u, h, l, zc: ((-L / 2 + t / 2, u, zc), (t, l, h))),
        'right': (lambda u, h, l, zc: ((L / 2 - t / 2, u, zc), (t, l, h))),
    }
    done_lintel = set()
    for ci, (zc, h) in enumerate(cs):
        bk = band_of(rng, ci, base)
        for wn, place in walls.items():
            fb = wn in ('front', 'back')
            full = (ci % 2 == 0) == fb
            half = (L if fb else W) / 2
            span = (-half, half) if full else (-half + t, half - t)
            cuts = []
            for oi, (u0, u1, za, zb) in enumerate(openings.get(wn, [])):
                if zc < zb - 1e-6 and zc + h > za + 1e-6:
                    cuts.append((u0, u1))
                elif abs(zc - zb) < 1e-6 and (wn, oi) not in done_lintel:
                    lu0, lu1 = u0 - 0.24, u1 + 0.24
                    cuts.append((lu0, lu1))
                    lintels.append((wn, lu0, lu1, zc, h))
                    done_lintel.add((wn, oi))
            segs, a = [], span[0]
            for c0, c1 in sorted(cuts):
                if c0 > a + 1e-6:
                    segs.append((a, min(c0, span[1])))
                a = max(a, c1)
            if a < span[1] - 1e-6:
                segs.append((a, span[1]))
            for s0, s1 in segs:
                u = s0
                while u < s1 - 1e-6:
                    l = rng.uniform(0.34, 0.82)
                    corner = full and (abs(u - span[0]) < 1e-6 or abs(s1 - span[1]) < 1e-6 and s1 - u < 1.2)
                    if corner and abs(u - span[0]) < 1e-6:
                        l = max(l, t + rng.uniform(0.25, 0.4))
                    if s1 - (u + l) < 0.26:
                        l = s1 - u
                    c, size = place(u + l / 2, h, l, zc + h / 2)
                    pid = K.box(c, size, slot='stone', name=f'{name}:{wn}:{ci}', e=min(e, h * 0.2))
                    q = abs(u - span[0]) < 1e-6 and full or abs(u + l - span[1]) < 1e-6 and full
                    k = quoin_k if q else (bk if rng.random() > 0.06 else rng.choice((0, 1, 2)))
                    strat[pid] = k
                    u += l
    return lintels


def lintel_beams(K, rng, L, W, t, lintels):
    for wn, u0, u1, zc, h in lintels:
        if wn == 'front':
            K.beam((u0, -W / 2 + t / 2, zc + h / 2), (u1, -W / 2 + t / 2, zc + h / 2), t, h, 'wood', 'lintel', 0.02)
        elif wn == 'back':
            K.beam((u0, W / 2 - t / 2, zc + h / 2), (u1, W / 2 - t / 2, zc + h / 2), t, h, 'wood', 'lintel', 0.02)
        elif wn == 'left':
            K.beam((-L / 2 + t / 2, u0, zc + h / 2), (-L / 2 + t / 2, u1, zc + h / 2), h, t, 'wood', 'lintel', 0.02)
        else:
            K.beam((L / 2 - t / 2, u0, zc + h / 2), (L / 2 - t / 2, u1, zc + h / 2), h, t, 'wood', 'lintel', 0.02)


def wall_frame(L, W, t, wn):
    """Origin on the wall's centre line at u = 0, unit vectors (along u, outward)."""
    if wn == 'front':
        return V(0, -W / 2 + t / 2, 0), V(1, 0, 0), V(0, -1, 0)
    if wn == 'back':
        return V(0, W / 2 - t / 2, 0), V(1, 0, 0), V(0, 1, 0)
    if wn == 'left':
        return V(-L / 2 + t / 2, 0, 0), V(0, 1, 0), V(-1, 0, 0)
    return V(L / 2 - t / 2, 0, 0), V(0, 1, 0), V(1, 0, 0)


def window(K, rng, L, W, t, wn, u0, u1, za, zb, shutters=True):
    o, ua, out = wall_frame(L, W, t, wn)
    uc = (u0 + u1) / 2
    w = u1 - u0
    ctr = o + ua * uc
    R = Matrix((ua, out, V(0, 0, 1))).transposed()
    # stone sill, proud of the wall outside
    K.box(ctr + out * 0.05 + V(0, 0, za + 0.035), (w, t + 0.1, 0.07), R, 'stone', 'sill', 0.012)
    fw = 0.075
    fz0 = za + 0.07
    mid = ctr + out * 0.06
    # frame: two jambs and a head, then a cross bar; the pane sits in it
    K.box(mid + ua * (-w / 2 + fw / 2) + V(0, 0, (fz0 + zb) / 2), (fw, 0.12, zb - fz0), R, 'wood', 'wframe', 0.008)
    K.box(mid + ua * (w / 2 - fw / 2) + V(0, 0, (fz0 + zb) / 2), (fw, 0.12, zb - fz0), R, 'wood', 'wframe', 0.008)
    K.box(mid + V(0, 0, zb - fw / 2), (w - 2 * fw, 0.12, fw), R, 'wood', 'wframe', 0.008)
    K.box(mid + V(0, 0, fz0 + fw / 2), (w - 2 * fw, 0.12, fw), R, 'wood', 'wframe', 0.008)
    K.box(mid + V(0, 0, (fz0 + zb) / 2), (w - 2 * fw, 0.05, 0.04), R, 'wood', 'wbar', 0.006)
    K.box(mid + V(0, 0, (fz0 + zb) / 2), (0.04, 0.05, zb - fz0 - 2 * fw), R, 'wood', 'wbar', 0.006)
    K.box(mid - out * 0.015 + V(0, 0, (fz0 + zb) / 2), (w - 2 * fw, 0.012, zb - fz0 - 2 * fw), R, 'mica', 'pane')
    if shutters:   # two board leaves swung open flat against the wall outside
        face = ctr + out * (t / 2 + 0.03)
        hgt = zb - fz0 - 0.02
        for side in (-1, 1):
            pid = K.part('shutter')
            leaf = w / 2 + 0.02
            n = 3
            for i in range(n):
                cu = side * (w / 2 + 0.02 + leaf * (i + 0.5) / n)
                K.box(face + ua * cu + V(0, 0, fz0 + 0.01 + hgt / 2), (leaf / n - 0.008, 0.035, hgt), R, 'wood',
                      'shutter', 0.006, axis=(0, 0, 1), part=pid)
            for zz in (fz0 + 0.12, zb - 0.14):
                K.box(face + out * 0.025 + ua * (side * (w / 2 + 0.02 + leaf / 2)) + V(0, 0, zz), (leaf, 0.015, 0.05), R,
                      'iron', 'strap', 0.003)


def door(K, rng, L, W, t, wn, u0, u1, za, zb, swing=70.0, hinge=-1):
    """Frame, threshold stone and a plank door standing open into the room."""
    o, ua, out = wall_frame(L, W, t, wn)
    uc = (u0 + u1) / 2
    w = u1 - u0
    ctr = o + ua * uc
    R = Matrix((ua, out, V(0, 0, 1))).transposed()
    K.box(ctr + out * 0.06 + V(0, 0, za + 0.04), (w + 0.1, t + 0.12, 0.08), R, 'stone', 'threshold', 0.015)
    fw = 0.12
    zf = za + 0.08
    for s in (-1, 1):
        K.box(ctr + ua * (s * (w / 2 - fw / 2)) + V(0, 0, (zf + zb) / 2), (fw, t * 0.62, zb - zf), R, 'wood', 'jamb', 0.015)
    K.box(ctr + V(0, 0, zb - 0.06), (w - 2 * fw, t * 0.62, 0.12), R, 'wood', 'head', 0.015)
    # the leaf: vertical planks, two ledges and a brace inside, iron straps outside; hinged on one jamb, open inwards
    lw = w - 2 * fw - 0.02
    lh = zb - 0.12 - zf - 0.02
    hp = ctr + ua * (hinge * (lw / 2)) - out * (t * 0.31 - 0.03)
    ang = math.radians(swing) * (-hinge)
    Rl = Matrix.Rotation(ang, 3, 'Z') @ R
    ua2 = Rl.col[0]
    n2 = Rl.col[1]
    pid = K.part('door')
    n = 5
    for i in range(n):
        cu = -hinge * (lw * (i + 0.5) / n)
        K.box(hp + ua2 * cu + V(0, 0, zf + 0.01 + lh / 2), (lw / n - 0.006, 0.045, lh), Rl, 'wood', 'door', 0.006,
              axis=(0, 0, 1), part=pid)
    for zz in (zf + 0.3, zf + lh - 0.3):
        K.box(hp + ua2 * (-hinge * lw / 2) - n2 * 0.045 + V(0, 0, zz), (lw - 0.08, 0.045, 0.12), Rl, 'wood', 'ledge', 0.008)
        K.box(hp + ua2 * (-hinge * lw / 2) + n2 * 0.03 + V(0, 0, zz), (lw - 0.02, 0.015, 0.05), Rl, 'iron', 'strap', 0.003)
    a = hp + ua2 * (-hinge * 0.12) - n2 * 0.045 + V(0, 0, zf + 0.42)
    b = hp + ua2 * (-hinge * (lw - 0.12)) - n2 * 0.045 + V(0, 0, zf + lh - 0.42)
    K.beam(a, b, 0.1, 0.04, 'wood', 'brace', 0.006, roll=0)
    K.prism(hp + ua2 * (-hinge * (lw - 0.1)) + n2 * 0.06 + V(0, 0, zf + lh * 0.48), n2, 0.02, 0.04, 0.04, 'iron', 'ring', 8)


class Roof:
    """A steep double-pitched roof on a timber frame. Surfaces in one frame:
    rafter centre line z_c(y), sarking top s_top(y); slope vectors per side."""

    def __init__(self, L, W, zt, pitch_deg, ov=0.5, vg=0.36, rd=0.14):
        self.L, self.W, self.zt = L, W, zt
        self.p = math.radians(pitch_deg)
        self.tp = math.tan(self.p)
        self.ov, self.vg, self.rd = ov, vg, rd
        self.Hw = W / 2

    def zc(self, y):
        return self.zt + 0.14 + 0.09 + (self.Hw - abs(y)) * self.tp

    def under(self, y):   # rafter underside
        return self.zc(y) - (self.rd / 2) / math.cos(self.p)

    def top(self, y):     # sarking top
        return self.zc(y) + (self.rd / 2) / math.cos(self.p) + 0.025 / math.cos(self.p)

    def side(self, s):
        """s = -1 front, +1 back: (u along the ridge, v up the slope, n out of the roof, eave point at x = 0)."""
        c, sn = math.cos(self.p), math.sin(self.p)
        if s < 0:
            u, v = V(1, 0, 0), V(0, c, sn)
        else:
            u, v = V(-1, 0, 0), V(0, -c, sn)
        n = u.cross(v)
        ye = s * (self.Hw + self.ov)
        return u, v, n, V(0, ye, self.top(ye))

    def slope_len(self):
        return (self.Hw + self.ov) / math.cos(self.p)


def roof_frame(K, rng, R, t, holes=(), ties=None):
    """Wall plates, tie beams, rafters, ridge. holes: x ranges a chimney passes through (no rafter there)."""
    L, W, zt = R.L, R.W, R.zt
    for s in (-1, 1):
        K.beam((-L / 2, s * (W / 2 - t / 2), zt + 0.07), (L / 2, s * (W / 2 - t / 2), zt + 0.07), 0.2, 0.14, 'wood',
               'plate', 0.015, roll=math.pi / 2)
    xs = ties if ties is not None else [-L / 2 + t + 0.25 + i * (L - 2 * t - 0.5) / max(1, round((L - 2 * t) / 1.7) - 1)
                                        for i in range(max(2, round((L - 2 * t) / 1.7)))]
    for x in xs:
        K.beam((x, -W / 2 + 0.06, zt + 0.23), (x, W / 2 - 0.06, zt + 0.23), 0.16, 0.18, 'wood', 'tie', 0.015)
    n = max(4, round((L + 2 * R.vg) / 0.62))
    for i in range(n + 1):
        x = -L / 2 - R.vg + 0.06 + i * (L + 2 * R.vg - 0.12) / n
        if any(h0 - 0.08 < x < h1 + 0.08 for h0, h1 in holes):
            continue
        for s in (-1, 1):
            ye = s * (R.Hw + R.ov)
            K.beam((x, ye, R.zc(ye)), (x, s * 0.07, R.zc(s * 0.07)), 0.11, R.rd, 'wood', f'rafter', 0.012)
    x1 = min([h0 for h0, h1 in holes] + [L / 2 + R.vg])
    K.beam((-L / 2 - R.vg, 0, R.zc(0) - 0.02), (x1, 0, R.zc(0) - 0.02), 0.14, 0.24, 'wood', 'ridge', 0.015, roll=math.pi / 2)
    if holes:
        x0 = max(h1 for h0, h1 in holes)
        if x0 < L / 2 + R.vg - 0.1:
            K.beam((x0, 0, R.zc(0) - 0.02), (L / 2 + R.vg, 0, R.zc(0) - 0.02), 0.14, 0.24, 'wood', 'ridge', 0.015,
                   roll=math.pi / 2)


def _clip_spans(a, b, holes):
    out, cur = [], a
    for h0, h1 in sorted(holes):
        if h1 <= cur or h0 >= b:
            continue
        if h0 > cur:
            out.append((cur, h0))
        cur = max(cur, h1)
    if cur < b:
        out.append((cur, b))
    return [(p, q) for p, q in out if q - p > 0.05]


def roof_cover(K, rng, R, holes=(), hole_s=99.0):
    """Sarking boards and slate shingles. holes: x ranges cut out near the ridge (slope distance > hole_s)."""
    L = R.L
    sl = R.slope_len()
    x0, x1 = -L / 2 - R.vg, L / 2 + R.vg
    for s in (-1, 1):
        u, v, n, E = R.side(s)
        Rm = Matrix((u, v, n)).transposed()
        # sarking: boards along the ridge, laid up the slope
        d = 0.0
        while d < sl - 0.02:
            bw = min(rng.uniform(0.17, 0.24), sl - d)
            hs = holes if d + bw > hole_s else ()
            for a, b in _clip_spans(x0, x1, hs):
                xa, xb = (a, b)
                c = V((xa + xb) / 2, E.y, E.z) + v * (d + bw / 2) - n * 0.0125
                K.box(c, (xb - xa, bw - 0.004, 0.025), Rm, 'wood', 'sark', 0.004, axis=(1, 0, 0))
            d += bw
        # shingles: rows from the eave, each tilted so its butt rides on the row below
        exp, ln, th = 0.2, 0.44, 0.022
        dl = math.atan(2.4 * th / ln)
        vv = v * math.cos(dl) - n * math.sin(dl)
        nn = n * math.cos(dl) + v * math.sin(dl)
        Rs = Matrix((u, vv, nn)).transposed()
        row, d = 0, -0.06
        while d < sl - 0.12:
            x = x0 - (rng.uniform(0.0, 0.16) if row % 2 else 0.0)
            ln_r = min(ln, sl - d + 0.02)
            while x < x1 - 0.05:
                w = rng.uniform(0.22, 0.34)
                xa, xb = max(x, x0 - 0.02), min(x + w, x1 + 0.02)
                x += w
                if xb - xa < 0.08:
                    continue
                cx = (xa + xb) / 2
                if d + ln_r > hole_s and any(h0 - 0.05 < cx < h1 + 0.05 or h0 < xa < h1 or h0 < xb < h1 for h0, h1 in holes):
                    continue
                cx_s = -cx if s > 0 else cx       # u points -x on the back side
                butt = E + u * cx_s + v * d + n * (2.4 * th)
                c = butt + vv * (ln_r / 2) + nn * (th / 2)
                jit = Matrix.Rotation(rng.uniform(-0.04, 0.04), 3, nn)
                K.box(c, (xb - xa - 0.008, ln_r, th), jit @ Rs, 'shingle', 'shingle', 0.004, axis=v)
            d += exp
            row += 1
    # ridge roll: short capping pieces along the apex
    x = x0
    zr = R.top(0) + 0.07
    while x < x1 - 0.05:
        l = min(rng.uniform(0.38, 0.52), x1 - x)
        if not any(h0 - 0.05 < x + l / 2 < h1 + 0.05 for h0, h1 in holes):
            K.prism(V(x + 0.005, 0, zr), V(1, 0, 0), l - 0.01, 0.13, 0.13, 'shingle', 'ridgecap', 6, spin=math.pi / 6)
        x += l


def gable_boards(K, rng, R, t, s, skip=()):
    """Vertical board infill of the gable at x = s * (L/2 - t/2), from the wall top to the rafters."""
    L, W, zt = R.L, R.W, R.zt
    x = s * (L / 2 - t / 2)
    y = -W / 2 + 0.02
    while y < W / 2 - 0.04:
        bw = min(rng.uniform(0.18, 0.26), W / 2 - 0.02 - y)
        y0, y1 = y, y + bw - 0.006
        y += bw
        if any(a < (y0 + y1) / 2 < b for a, b in skip):
            continue
        pts = [V(x, y0, zt), V(x, y1, zt), V(x, y1, R.under(y1) - 0.01)]
        if y0 < 0 < y1:
            pts.append(V(x, 0, R.under(0) - 0.01))
        pts.append(V(x, y0, R.under(y0) - 0.01))
        K.slab([p - V(0.03, 0, 0) for p in pts], 0.06, 'wood', 'gable', 0.006, up=(1, 0, 0), axis=(0, 0, 1))


def wind_wheel(K, rng, hub, axis, r=1.35, blades=6, inside=0.0):
    """A sailed wind wheel on an axle along `axis` (unit, pointing out of the wall). Built in its own node."""
    K.use_node('rotor')
    ax = Vector(axis).normalized()
    a0 = hub - ax * (0.55 + inside)
    K.prism(a0, ax, 0.65 + inside, 0.07, 0.07, 'wood', 'axle', 8)
    K.prism(hub - ax * 0.12, ax, 0.24, 0.17, 0.17, 'wood', 'hubwheel', 10)
    K.prism(hub + ax * 0.12, ax, 0.06, 0.09, 0.05, 'iron', 'cap', 8)
    up = V(0, 0, 1)
    side = ax.cross(up).normalized()
    for i in range(blades):
        a = 2 * math.pi * i / blades
        d = side * math.cos(a) + up * math.sin(a)
        K.beam(hub + d * 0.12, hub + d * r, 0.07, 0.05, 'wood', 'spoke', 0.008, roll=0)
        # the sail: a cloth panel lashed along the trailing side of the spoke, pitched into the wind
        perp = ax.cross(d).normalized()
        pitch = Matrix.Rotation(math.radians(18), 3, d)
        Rm = Matrix((d, perp, d.cross(perp))).transposed()
        c = hub + d * (r * 0.58 + 0.08) + perp * 0.2
        K.box(c, (r * 0.78, 0.36, 0.012), pitch @ Rm, 'sail', f'sail', 0.002, axis=d)
        K.beam(hub + d * (r * 0.19 + 0.08) + perp * 0.38, hub + d * r + perp * 0.38, 0.025, 0.025, 'wood', 'batten', 0.004)
    # rim: a ring of short beams tying the spoke tips
    for i in range(blades):
        a, b = 2 * math.pi * i / blades, 2 * math.pi * (i + 1) / blades
        pa = hub + (side * math.cos(a) + up * math.sin(a)) * (r * 0.98)
        pb = hub + (side * math.cos(b) + up * math.sin(b)) * (r * 0.98)
        K.beam(pa, pb, 0.045, 0.045, 'wood', 'rim', 0.006)
    if inside > 0:   # the drive wheel on the inner end of the axle, inside the loft
        K.prism(a0 + ax * 0.1, ax, 0.08, 0.42, 0.42, 'wood', 'drivewheel', 14)
        for i in range(14):
            a = 2 * math.pi * i / 14
            d = side * math.cos(a) + up * math.sin(a)
            K.box(a0 + ax * 0.14 + d * 0.45, (0.05, 0.05, 0.06), frame(d), 'wood', 'cog', 0.006)
    K.use_node('body')
