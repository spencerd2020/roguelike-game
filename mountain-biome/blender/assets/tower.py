"""Vanehold lookout tower: a square tower of banded coursed stone with three floors inside, ladders up through hatches,
slit windows that light each floor, a timber watch gallery jettied out on struts, a pyramid slate roof and a signal bell.
Floor joists sit in the walls at the heights the outside slits suggest, so inside and outside agree.
"""
import math

import numpy as np
from mathutils import Matrix, Vector

import vane
from mkit import Kit, V, stream

SLOTS = ['stone', 'flag', 'mortar', 'wood', 'plank', 'shingle', 'iron', 'rope', 'mica', 'ember']
GLOW = ('mica', 'ember')


def ladder(K, x, y0, z0, z1, lean, along=(1, 0)):
    ax, ay = along
    for s in (-1, 1):
        K.beam((x - ay * s * 0.22, y0 + ax * s * 0.22, z0), (x - ay * s * 0.22 + ax * lean, y0 + ax * s * 0.22 + ay * lean, z1),
               0.07, 0.06, 'wood', 'rail', 0.01)
    n = int((z1 - z0) / 0.3)
    for i in range(1, n):
        k = i / n
        p = V(x + ax * lean * k, y0 + ay * lean * k, z0 + (z1 - z0) * k)
        K.prism(p - V(-ay, ax, 0) * 0.24, V(-ay, ax, 0), 0.48, 0.022, 0.022, 'wood', 'rung', 6)


def floor(K, rng, S, t, z, hole):
    """Joists across the tower set into the walls, boards on top, a hatch hole (x0, x1, y0, y1)."""
    i0 = -S / 2 + t
    n = 4
    for i in range(n):
        y = i0 + 0.3 + i * (S - 2 * t - 0.6) / (n - 1)
        K.beam((-S / 2 + t - 0.15, y, z - 0.11), (S / 2 - t + 0.15, y, z - 0.11), 0.16, 0.2, 'wood', 'joist', 0.015)
    x = i0
    while x < S / 2 - t - 1e-6:
        bw = min(rng.uniform(0.18, 0.26), S / 2 - t - x)
        segs = [(i0, S / 2 - t)]
        if hole[0] < x + bw / 2 < hole[1]:
            segs = [(i0, hole[2]), (hole[3], S / 2 - t)]
        for a, b in segs:
            if b - a > 0.05:
                K.box((x + bw / 2, (a + b) / 2, z + 0.02), (bw - 0.006, b - a, 0.04), slot='plank', name='floorboard',
                      e=0.005, axis=(0, 1, 0))
        x += bw
    # hatch trim
    x0, x1, y0, y1 = hole
    for yy in (y0 - 0.04, y1 + 0.04):
        K.box(((x0 + x1) / 2, yy, z + 0.05), (x1 - x0 + 0.16, 0.08, 0.06), slot='wood', name='hatchtrim', e=0.008, axis=(1, 0, 0))


def build(seed):
    K = Kit(SLOTS, GLOW)
    g = stream(seed, 'size')
    S = round(g.uniform(4.2, 4.8), 2)
    t = 0.6
    zp = 0.25
    H = round(g.uniform(7.6, 8.4), 2)
    zt = zp + H
    ctx = {'moss_z': zp + 0.8, 'ao_dist': 1.5}
    # footing: a battered plinth course
    K.box((0, 0, zp / 2), (S + 0.5, S + 0.5, zp), slot='stone', name='footing', e=0.04)
    ctx.setdefault('strat', {})[len(K.parts) - 1] = 0
    C = stream(seed, 'courses')
    cs = vane.courses(C, zp, H, 0.22, 0.36)
    f1 = vane.snap(cs, zp + 2.9)
    f2 = vane.snap(cs, zp + 5.6)
    door_top = vane.snap(cs, zp + 2.0)
    O = stream(seed, 'openings')
    openings = {'front': [(-0.48, 0.48, zp, door_top)]}

    def slit(z0, z1, u=0.0):
        return (u - 0.14, u + 0.14, vane.snap(cs, z0), vane.snap(cs, z1))
    openings['left'] = [slit(zp + 1.0, zp + 2.1, O.uniform(-0.6, 0.6)), slit(f1 + 0.9, f1 + 2.0)]
    openings['right'] = [slit(f1 + 0.9, f1 + 2.0, O.uniform(-0.6, 0.6)), slit(f2 + 0.8, f2 + 1.8)]
    openings['back'] = [slit(zp + 1.0, zp + 2.1, O.uniform(-0.8, 0.8)), slit(f2 + 0.8, f2 + 1.8, O.uniform(-0.5, 0.5))]
    openings['front'].append(slit(f1 + 0.9, f1 + 2.0, O.uniform(-0.5, 0.5)))
    lintels = vane.rect_walls(K, C, ctx, S, S, t, cs, openings, zp, e=0.032, name='twall')
    for wn, u0, u1, zc, h in lintels:   # stone lintels on slits, timber over the door
        o, ua, out = vane.wall_frame(S, S, t, wn)
        R = Matrix((ua, out, V(0, 0, 1))).transposed()
        if wn == 'front' and u1 - u0 > 1.0:
            K.box(o + ua * ((u0 + u1) / 2) + V(0, 0, zc + h / 2), (u1 - u0, t, h), R, 'wood', 'lintel', 0.02)
        else:
            K.box(o + ua * ((u0 + u1) / 2) + V(0, 0, zc + h / 2), (u1 - u0, t, h), R, 'stone', 'slintel', 0.03)
            ctx['strat'][len(K.parts) - 1] = 2
    vane.door(K, O, S, S, t, 'front', -0.48, 0.48, zp, door_top, swing=O.uniform(55, 75), hinge=1)
    for wn, ops in openings.items():
        for (u0, u1, za, zb) in ops:
            if u1 - u0 > 0.5:
                continue
            o, ua, out = vane.wall_frame(S, S, t, wn)
            R = Matrix((ua, out, V(0, 0, 1))).transposed()
            K.box(o + ua * ((u0 + u1) / 2) + out * 0.04 + V(0, 0, za + 0.035), (u1 - u0, t + 0.08, 0.07), R, 'stone', 'sill', 0.012)
            K.box(o + ua * ((u0 + u1) / 2) - out * (t / 2 - 0.08) + V(0, 0, (za + zb) / 2 + 0.035), (u1 - u0, 0.02, zb - za - 0.07), R,
                  'mica', 'pane')
    # ---------- inside: flags, two timber floors, ladders through hatches ----------
    F = stream(seed, 'floor')
    i0 = -S / 2 + t
    yy = i0
    while yy < S / 2 - t - 1e-6:
        d = min(F.uniform(0.45, 0.75), S / 2 - t - yy)
        xx = i0 - F.uniform(0, 0.4)
        while xx < S / 2 - t - 1e-6:
            w = F.uniform(0.5, 0.9)
            xa, xb = max(xx, i0), min(xx + w, S / 2 - t)
            if xb - xa > 0.08:
                K.box(((xa + xb) / 2, yy + d / 2, zp + 0.02), (xb - xa - 0.014, d - 0.014, 0.04), slot='flag', name='tfloor', e=0.008)
            xx += w
        yy += d
    h1 = (i0 + 0.15, i0 + 0.85, -0.35, 0.35)            # hatch on the left side of floor 1
    h2 = (S / 2 - t - 0.85, S / 2 - t - 0.15, -0.35, 0.35)   # right side of floor 2
    floor(K, F, S, t, f1, h1)
    floor(K, F, S, t, f2, h2)
    ladder(K, h1[0] + 0.35 + 1.0, 0.0, zp + 0.04, f1 + 0.6, -1.0)
    ladder(K, h2[0] + 0.35 - 1.0, 0.0, f1 + 0.04, f2 + 0.6, 1.0)
    # a chest and a weapon-less rack on the ground floor (bare), a bench up top
    K.box((S / 2 - t - 0.35, S / 2 - t - 0.55, zp + 0.29), (0.6, 1.0, 0.5), slot='plank', name='chest', e=0.015, axis=(0, 1, 0))
    K.box((S / 2 - t - 0.35, S / 2 - t - 0.55, zp + 0.57), (0.64, 1.04, 0.06), slot='plank', name='chestlid', e=0.012, axis=(0, 1, 0))
    K.box((-S / 2 + t + 0.2, S / 2 - t - 0.9, f1 + 0.48), (0.32, 1.4, 0.05), slot='plank', name='bench', e=0.008, axis=(0, 1, 0))
    for s in (-1, 1):
        K.box((-S / 2 + t + 0.2, S / 2 - t - 0.9 + s * 0.55, f1 + 0.25), (0.28, 0.07, 0.44), slot='wood', name='benchleg', e=0.008)
    K.box((0.4, -S / 2 + t + 0.3, zp + 1.8), (0.07, 0.4, 0.4), slot='iron', name='bracket', e=0.006)
    K.box((0.4, -S / 2 + t + 0.42, zp + 1.95), (0.16, 0.16, 0.2), slot='mica', name='lamp')
    K.light((0.4, -S / 2 + t + 0.42, zp + 1.95), (1.0, 0.7, 0.4), 60, 0.1)
    K.light((0, 0, f1 + 1.6), (1.0, 0.72, 0.45), 25, 0.2)
    # ---------- the gallery: joists cantilevered out over the wall top on struts, boards, posts, a parapet ----------
    G = stream(seed, 'gallery')
    jet = 0.75
    zg = zt + 0.24
    Sg = S + 2 * jet
    for i in range(6):
        y = -Sg / 2 + 0.15 + i * (Sg - 0.3) / 5
        K.beam((-Sg / 2, y, zt + 0.1), (Sg / 2, y, zt + 0.1), 0.16, 0.2, 'wood', 'gjoist', 0.015)
    for wn in ('front', 'back', 'left', 'right'):
        o, ua, out = vane.wall_frame(S, S, t, wn)
        for u in (-S / 2 + 0.6, 0.0, S / 2 - 0.6):
            base = V(0, 0, 0) + out * (S / 2) + ua * u + V(0, 0, zt - 1.3)
            K.box(base + out * 0.12, (0.2, 0.2, 0.22), Matrix((ua, out, V(0, 0, 1))).transposed(), 'stone', 'corbel', 0.03)
            ctx['strat'][len(K.parts) - 1] = 2
            K.beam(base + out * 0.18 + V(0, 0, 0.1), base + out * (jet - 0.05) + V(0, 0, 1.3), 0.12, 0.12, 'wood', 'strut', 0.012)
    x = -Sg / 2
    while x < Sg / 2 - 1e-6:
        bw = min(G.uniform(0.18, 0.26), Sg / 2 - x)
        segs = [(-Sg / 2, Sg / 2)]
        if -0.45 < x + bw / 2 < 0.45:
            segs = [(-Sg / 2, -0.4), (0.4, Sg / 2)]   # the hatch up from floor 2
        for a, b in segs:
            K.box((x + bw / 2, (a + b) / 2, zg), (bw - 0.006, b - a, 0.05), slot='plank', name='gboard', e=0.005, axis=(0, 1, 0))
        x += bw
    # ladder from floor 2 up through the gallery hatch
    lx = 0.0
    for s in (-1, 1):
        K.beam((lx + s * 0.22, -1.0, f2 + 0.04), (lx + s * 0.22, -0.1, zg + 0.7), 0.07, 0.06, 'wood', 'rail', 0.01)
    n = int((zg + 0.7 - f2) / 0.3)
    for i in range(1, n):
        k = i / n
        K.prism(V(lx - 0.24, -1.0 + 0.9 * k, f2 + 0.04 + (zg + 0.66 - f2) * k), V(1, 0, 0), 0.48, 0.022, 0.022, 'wood', 'rung', 6)
    # posts and parapet
    zr = zg + 2.1
    posts = []
    for i in range(5):
        u = -Sg / 2 + 0.08 + i * (Sg - 0.16) / 4
        posts += [(u, -Sg / 2 + 0.08), (u, Sg / 2 - 0.08)]
        if 0 < i < 4:
            posts += [(-Sg / 2 + 0.08, u), (Sg / 2 - 0.08, u)]
    for (px, py) in posts:
        K.box((px, py, (zg + zr) / 2), (0.14, 0.14, zr - zg), slot='wood', name='gpost', e=0.015, axis=(0, 0, 1))
    for wn in ('front', 'back', 'left', 'right'):
        o, ua, out = vane.wall_frame(Sg, Sg, 0.16, wn)
        R = Matrix((ua, out, V(0, 0, 1))).transposed()
        u = -Sg / 2 + 0.15
        while u < Sg / 2 - 0.16:
            bw = min(G.uniform(0.16, 0.22), Sg / 2 - 0.15 - u)
            K.box(o + ua * (u + bw / 2) + V(0, 0, zg + 0.5), (bw - 0.008, 0.04, 0.9), R, 'wood', 'parapet', 0.006, axis=(0, 0, 1))
            u += bw
        K.box(o + V(0, 0, zg + 1.0), (Sg - 0.1, 0.12, 0.08), R, 'wood', 'rail', 0.01)
        K.box(o + V(0, 0, zr - 0.08), (Sg, 0.16, 0.16), R, 'wood', 'gplate', 0.015)
    # the bell on a yoke between two posts
    K.beam((-0.9, 0.9, zr - 0.5), (0.9, 0.9, zr - 0.5), 0.14, 0.16, 'wood', 'yoke', 0.015)
    K.prism(V(0, 0.9, zr - 1.32), V(0, 0, 1), 0.72, 0.36, 0.2, 'iron', 'bell', 16, e=0.0)
    K.prism(V(0, 0.9, zr - 1.4), V(0, 0, 1), 0.08, 0.4, 0.37, 'iron', 'lip', 16)
    K.tube([(0.05, 0.9, zr - 0.7), (0.4, 0.6, zg + 0.9), (0.7, 0.2, zg + 0.2)], 0.015, 'rope', 'bellrope', 5)
    # ---------- pyramid roof ----------
    K.use_node('roof')
    T = stream(seed, 'roof')
    ov = 0.45
    half = Sg / 2 + ov
    pitch = math.radians(T.uniform(50, 56))
    rise = half * math.tan(pitch)
    apex = V(0, 0, zr + rise)
    sl = half / math.cos(pitch)
    for wn in ('front', 'right', 'back', 'left'):
        o, ua, out = vane.wall_frame(2 * half, 2 * half, 0, wn)
        c, sn = math.cos(pitch), math.sin(pitch)
        v = (-out * c + V(0, 0, sn)).normalized()
        n = ua.cross(v)
        if n.z < 0:
            ua = -ua
            n = -n
        eave = out * half + V(0, 0, zr)
        exp, ln, th = 0.2, 0.44, 0.022
        dl = math.atan(2.4 * th / ln)
        vv = v * math.cos(dl) - n * math.sin(dl)
        nn = n * math.cos(dl) + v * math.sin(dl)
        Rs = Matrix((ua, vv, nn)).transposed()
        Rb = Matrix((ua, v, n)).transposed()
        d = 0.0
        while d < sl - 0.02:   # sarking, trimmed to the hip lines
            bw = min(T.uniform(0.17, 0.24), sl - d)
            wdt = 2 * half * (1 - (d + bw / 2) / sl)
            K.box(eave + v * (d + bw / 2) - n * 0.0125, (max(wdt, 0.05), bw - 0.004, 0.025), Rb, 'wood', 'sark', 0.004, axis=ua)
            d += bw
        d, row = -0.06, 0
        while d < sl - 0.25:
            wrow = 2 * half * (1 - max(d, 0) / sl)
            x = -wrow / 2 - (T.uniform(0, 0.15) if row % 2 else 0)
            while x < wrow / 2 - 0.05:
                w = T.uniform(0.22, 0.34)
                xa, xb = max(x, -wrow / 2), min(x + w, wrow / 2)
                x += w
                if xb - xa < 0.08:
                    continue
                butt = eave + ua * ((xa + xb) / 2) + v * d + n * (2.4 * th)
                K.box(butt + vv * (ln / 2) + nn * (th / 2), (xb - xa - 0.008, ln, th),
                      Matrix.Rotation(T.uniform(-0.04, 0.04), 3, nn) @ Rs, 'shingle', 'shingle', 0.004, axis=v)
            d += exp
            row += 1
        # hip roll along the corner
        corner = out * half + ua * half + V(0, 0, zr)
        K.prism(corner + (apex - corner).normalized() * 0.05 + V(0, 0, 0.06), apex - corner, (apex - corner).length - 0.1, 0.09, 0.09,
                'shingle', 'hip', 6)
    K.prism(apex - V(0, 0, 0.3), V(0, 0, 1), 0.5, 0.16, 0.05, 'iron', 'finial', 8)
    K.prism(apex, V(0, 0, 1), 1.6, 0.03, 0.025, 'iron', 'vanepole', 6)
    K.box(apex + V(0.32, 0, 1.35), (0.6, 0.02, 0.24), slot='iron', name='vaneflag', e=0.004)
    K.use_node('body')
    # roof frame (stays when the roof is cut away): hip rafters
    for sx in (-1, 1):
        for sy in (-1, 1):
            K.beam(V(sx * (half - 0.05), sy * (half - 0.05), zr - 0.1), apex - V(0, 0, 0.3), 0.14, 0.16, 'wood', 'hiprafter', 0.015)
    ctx['footprint'] = [Sg + 2 * ov, Sg + 2 * ov]
    K.markers['door'] = (0, -S / 2, zp)

    def outside(Pp, Nn):
        ins = (np.abs(Pp[:, 0]) < S / 2 - t + 0.06) & (np.abs(Pp[:, 1]) < S / 2 - t + 0.06) & (Pp[:, 2] < zt + 0.05)
        return ~ins
    ctx['outside'] = outside
    return f'tower_{seed}', K, ctx
