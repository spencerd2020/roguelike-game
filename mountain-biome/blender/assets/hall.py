"""Vanehold hearth hall: the town's communal longhouse. A long, low room (the tie beams sit low to keep the heat in) round
a great central hearth whose stone hood stands on four piers and rises through the ridge as one big stack, so the smoke
of the whole town's evenings goes up the middle of the roof. Banded coursed stone, a steep slate roof on a timber frame,
the same wind wheel on the west gable as the houses.

Inside: a flagstone floor, the long hearth with its curb, embers and logs, and the shared household furniture placed by
name (trestle tables and benches either side of the fire, kegs and barrels, a cupboard and shelves, lanterns): the
furniture is never part of this mesh (retexture.py, HouseDresser in the game). Seeded like the houses.
"""
import math

from mathutils import Vector

import vane
from mkit import Kit, V, stream

SLOTS = ['stone', 'flag', 'mortar', 'wood', 'plank', 'shingle', 'iron', 'sail', 'bedding', 'rope', 'mica', 'ember']
GLOW = ('mica', 'ember')


def build(seed):
    K = Kit(SLOTS, GLOW)
    g = stream(seed, 'size')
    L = round(g.uniform(13.0, 14.2), 2)
    W = round(g.uniform(7.0, 7.6), 2)
    t = 0.55
    zp = 0.36
    H = round(g.uniform(2.45, 2.6), 2)          # low walls: the heat stays under the tie beams
    pitch = g.uniform(50, 55)
    zt = zp + H
    ctx = {'moss_z': zp + 0.7, 'ao_dist': 1.6, 'strat': {}}
    # ---------- plinth ----------
    P = stream(seed, 'plinth')
    m = 0.5
    K.box((0, 0, zp / 2 - 0.02), (L + 2 * m - 0.1, W + 2 * m - 0.1, zp - 0.04), slot='mortar', name='footing')
    y = -W / 2 - m
    while y < W / 2 + m - 1e-6:
        d = min(P.uniform(0.5, 0.9), W / 2 + m - y)
        x = -L / 2 - m - P.uniform(0, 0.4)
        while x < L / 2 + m - 1e-6:
            w = P.uniform(0.6, 1.2)
            xa, xb = max(x, -L / 2 - m), min(x + w, L / 2 + m)
            if xb - xa > 0.1:
                K.box(((xa + xb) / 2, y + d / 2, zp - 0.02), (xb - xa - 0.012, d - 0.012, 0.04), slot='flag', name='flag', e=0.01)
            x += w
        y += d
    # ---------- walls: the door in the middle of the long front, small deep windows ----------
    C = stream(seed, 'courses')
    cs = vane.courses(C, zp, H)
    O = stream(seed, 'openings')
    dw = 1.25
    du = O.uniform(-0.6, 0.6)
    door_top = vane.snap(cs, zp + 2.05)
    if door_top < zp + 1.95:
        door_top = min([c[0] + c[1] for c in cs if c[0] + c[1] >= zp + 1.95] or [zp + H - 0.3])
    sill = vane.snap(cs, zp + 1.05)
    wtop = min(vane.snap(cs, sill + 0.62), cs[-2][0])
    openings = {'front': [(du - dw / 2, du + dw / 2, zp, door_top)]}
    for wx in (-L / 2 + t + 1.6, L / 2 - t - 1.6):
        openings['front'].append((wx - 0.28, wx + 0.28, sill, wtop))
    openings['back'] = [(b - 0.28, b + 0.28, sill, wtop) for b in (-L / 4, L / 4)]
    openings['right'] = [(-0.25, 0.25, sill, wtop)]
    lintels = vane.rect_walls(K, C, ctx, L, W, t, cs, openings, zp)
    vane.lintel_beams(K, C, L, W, t, lintels)
    vane.door(K, O, L, W, t, 'front', du - dw / 2, du + dw / 2, zp, door_top, swing=O.uniform(66, 82), hinge=-1)
    for wn, ops in openings.items():
        for (u0, u1, za, zb) in ops:
            if wn == 'front' and u0 < du < u1:
                continue
            vane.window(K, O, L, W, t, wn, u0, u1, za, zb, shutters=True)
    for i, (dz, dy) in enumerate(((zp - 0.12, 0.38), (zp - 0.24, 0.76))):
        K.box((du, -W / 2 - m - dy / 2, dz / 2), (dw + 0.8, 0.38, dz), slot='stone', name='step', e=0.02)
        ctx['strat'][len(K.parts) - 1] = 2
    # ---------- the roof, with the great stack through the middle of the ridge ----------
    R = vane.Roof(L, W, zt, pitch)
    cw, cy = 0.62, 0.62
    chim = (-cw, cw)
    T = stream(seed, 'roof')
    n_ties = 6
    ties = [-L / 2 + t + 0.6 + i * (L - 2 * t - 1.2) / (n_ties - 1) for i in range(n_ties)]
    ties = [x for x in ties if abs(x) > cw + 0.5]
    vane.roof_frame(K, T, R, t, holes=[chim], ties=ties)
    vane.gable_boards(K, T, R, t, -1)
    vane.gable_boards(K, T, R, t, 1)
    K.use_node('roof')
    hole_s = (R.Hw + R.ov - cy - 0.05) / math.cos(R.p)
    vane.roof_cover(K, T, R, holes=[(chim[0] - 0.03, chim[1] + 0.03)], hole_s=hole_s)
    K.use_node('body')
    # ---------- the great hearth: a long stone trough with a curb, a hood on four piers ----------
    Hh = stream(seed, 'hearth')
    hl, hw = 3.2, 1.3
    K.box((0, 0, zp + 0.06), (hl + 0.5, hw + 0.5, 0.12), slot='stone', name='hearthbed', e=0.02)
    ctx['strat'][len(K.parts) - 1] = 0
    for s in (-1, 1):
        K.box((0, s * (hw / 2 + 0.1), zp + 0.2), (hl + 0.4, 0.22, 0.28), slot='stone', name='curb', e=0.02)
        ctx['strat'][len(K.parts) - 1] = 2
        K.box((s * (hl / 2 + 0.1), 0, zp + 0.2), (0.22, hw - 0.02, 0.28), slot='stone', name='curb', e=0.02)
        ctx['strat'][len(K.parts) - 1] = 2
    for i in range(9):
        a = Hh.uniform(-0.5, 0.5)
        K.prism((-hl / 2 + 0.35 + i * (hl - 0.7) / 8, Hh.uniform(-0.3, 0.3), zp + 0.2), V(math.cos(a) * 0.3, math.sin(a) + 0.2, 0.08),
                0.7, 0.07, 0.065, 'wood', 'log', 7)
    for k in range(3):
        K.rock((-hl / 3 + k * hl / 3, 0, zp + 0.15), 0.3, Hh, 'ember', 'embers', 1, (1.8, 1.6, 0.3), 0.2)
    for k in range(3):
        K.light((-hl / 3 + k * hl / 3, 0, zp + 0.6), (1.0, 0.55, 0.25), 300, 0.3)
    piers = [(sx * (hl / 2 + 0.2), sy * (hw / 2 + 0.4)) for sx in (-1, 1) for sy in (-1, 1)]
    zh = zp + 1.95
    for (px, py) in piers:
        z = zp + 0.12
        pi_ = 0
        while z < zh - 1e-6:
            h = min(Hh.uniform(0.24, 0.32), zh - z)
            K.box((px, py, z + h / 2), (0.42, 0.42, h), slot='stone', name=f'pier:{pi_}', e=0.02)
            ctx['strat'][len(K.parts) - 1] = vane.STRATA[(pi_ // 2 + 1) % 10]
            z += h
            pi_ += 1
    for s in (-1, 1):
        K.beam((-hl / 2 - 0.45, s * (hw / 2 + 0.4), zh + 0.11), (hl / 2 + 0.45, s * (hw / 2 + 0.4), zh + 0.11), 0.24, 0.22, 'wood',
               'hoodbeam', 0.02)
    z = zh + 0.22
    hi = 0
    top_hood = zt + 0.5
    while z < top_hood:
        h = Hh.uniform(0.22, 0.3)
        k = min(1.0, (z - zh) / (top_hood - zh))
        lx = hl + 0.9 - (hl + 0.9 - 2 * cw) * k ** 0.8
        ly = hw + 1.1 - (hw + 1.1 - 2 * cy) * k ** 0.8
        # a hollow hood: four walls of stone that narrow into the stack
        th = 0.2
        for s in (-1, 1):
            K.box((0, s * (ly / 2 - th / 2), z + h / 2), (lx, th, h), slot='stone', name=f'hood:{hi}', e=0.02)
            ctx['strat'][len(K.parts) - 1] = vane.STRATA[(hi // 2 + 3) % 10]
            K.box((s * (lx / 2 - th / 2), 0, z + h / 2), (th, ly - 2 * th, h), slot='stone', name=f'hood:{hi}', e=0.02)
            ctx['strat'][len(K.parts) - 1] = vane.STRATA[(hi // 2 + 3) % 10]
        z += h
        hi += 1
    # the stack from the hood through the ridge
    top = R.top(0) + 1.2
    si = 0
    while z < top:
        h = min(Hh.uniform(0.22, 0.3), top - z)
        jx, jy = Hh.uniform(-0.012, 0.012), Hh.uniform(-0.012, 0.012)
        K.box((jx, jy, z + h / 2), (2 * cw, 2 * cy, h), slot='stone', name=f'stack:{si}', e=0.022)
        ctx['strat'][len(K.parts) - 1] = vane.STRATA[(si // 2 + 5) % 10]
        z += h
        si += 1
    K.box((0, 0, top + 0.05), (2 * cw + 0.18, 2 * cy + 0.18, 0.1), slot='stone', name='capstone', e=0.02)
    for sx in (-1, 1):
        for sy in (-1, 1):
            K.box((sx * 0.28, sy * 0.28, top + 0.18), (0.3, 0.3, 0.16), slot='stone', name='pot', e=0.02)
    # ---------- floor ----------
    F = stream(seed, 'floor')
    x0, x1, y0, y1 = -L / 2 + t, L / 2 - t, -W / 2 + t, W / 2 - t
    yy = y0
    while yy < y1 - 1e-6:
        d = min(F.uniform(0.45, 0.8), y1 - yy)
        if y1 - (yy + d) < 0.25:
            d = y1 - yy
        xx = x0 - F.uniform(0, 0.5)
        while xx < x1 - 1e-6:
            w = F.uniform(0.5, 1.0)
            xa, xb = max(xx, x0), min(xx + w, x1)
            if x1 - xb < 0.2:
                xb = x1
            if xb - xa > 0.08 and not (abs((xa + xb) / 2) < hl / 2 + 0.3 and abs(yy + d / 2) < hw / 2 + 0.3):
                K.box(((xa + xb) / 2, yy + d / 2, zp + 0.02), (xb - xa - 0.014, d - 0.014, 0.04), slot='flag', name='floor', e=0.008)
            xx = xb if xb == x1 else xx + w
        yy += d
    zf = zp + 0.04
    # ---------- the shared furniture, by name (never part of this mesh) ----------
    Fu = stream(seed, 'furniture')
    fur = []

    def put(kind, x, y, z, rot=0.0):
        fur.append({'kind': kind, 'x': round(x, 4), 'y': round(y, 4), 'z': round(z, 4), 'rot': round(rot, 4)})
    yi = W / 2 - t
    for sx in (-1, 1):
        tx = sx * (hl / 2 + 2.15)
        for sy in (-1, 1):
            ty = sy * (yi - 0.95)
            put('table', tx, ty, zf)
            put('bench', tx, ty + 0.64, zf, math.pi)
            put('bench', tx, ty - 0.64, zf)
            put('candlestick', tx + Fu.uniform(-0.4, 0.4), ty + Fu.uniform(-0.15, 0.15), zf + 0.76, Fu.uniform(0, 6.28))
    xe = L / 2 - t
    put('keg', xe - 0.45, yi - 0.5, zf, -math.pi / 2)
    put('barrel', xe - 0.4, yi - 1.35, zf, Fu.uniform(0, 6.28))
    put('barrel', xe - 0.4, -yi + 0.45, zf, Fu.uniform(0, 6.28))
    put('cupboard', xe - 0.3, -0.2, zf, -math.pi / 2)
    put('shelf', -L / 2 + t + 0.2, 1.0, zf, math.pi / 2)
    put('shelf', -L / 2 + t + 0.2, -1.0, zf, math.pi / 2)
    lamps = []
    for sx in (-1, 1):
        lx = min(ties, key=lambda x: abs(x - sx * (hl / 2 + 2.15)))
        K.tube([(lx, 0, zt + 0.14), (lx, 0, zt - 0.5)], 0.012, 'iron', 'chain', 5)
        put('lantern', lx, 0, zt - 0.84)
        K.light((lx, 0, zt - 0.7), (1.0, 0.72, 0.42), 70, 0.1)
        lamps.append((lx, 0, zt - 0.67))
    # outside: benches by the door
    put('bench', du - 1.7, -W / 2 - 0.32, zp)
    put('bench', du + 1.7, -W / 2 - 0.32, zp)
    ctx['furniture'] = fur
    # ---------- the wind wheel on the west gable ----------
    Ou = stream(seed, 'outside')
    hub = V(-L / 2 - 0.55, 0, R.zc(0) - 1.0)
    vane.wind_wheel(K, Ou, hub, V(-1, 0, 0), r=min(1.6, (hub.z - zt) + 0.75), inside=0.0)
    K.markers['rotor'] = tuple(hub)
    K.markers['door'] = (du, -W / 2, zp)
    K.markers['smoke'] = (0.0, 0.0, top + 0.3)
    K.markers['hearth'] = (0.0, 0.0, zp + 0.35)
    K.markers['hearths'] = [(-hl / 3 + k * hl / 3, 0.0, zp + 0.35) for k in range(3)]
    K.markers['room'] = {'L': L, 'W': W, 't': t, 'zf': zf, 'zt': zt}
    K.markers['slots'] = [
        ['hearth', 0.0, -(hw / 2 + 0.1), zp + 0.34, 0.0, 1.2, 0.18],
        ['hearth', 0.0, hw / 2 + 0.1, zp + 0.34, math.pi, 1.2, 0.18],
        ['floor', -L / 2 + t + 0.6, yi - 0.6, zf, 0.0, 0.9, 0.9],
        ['floor', -L / 2 + t + 0.6, -yi + 0.6, zf, 0.0, 0.9, 0.9],
        ['door', du + 1.0, -W / 2 + t + 0.4, zf, 0.0, 0.5, 0.4],
    ]
    K.markers['furniture'] = fur
    ctx['pivots'] = {'rotor': tuple(hub)}
    ctx['footprint'] = [L + 2 * m, W + 2 * m]

    import numpy as np

    def outside(Pp, Nn):
        ins = (np.abs(Pp[:, 0]) < L / 2 - t + 0.06) & (np.abs(Pp[:, 1]) < W / 2 - t + 0.06) & (Pp[:, 2] > zp - 0.05)
        ins &= Pp[:, 2] < zt + 0.23 + (R.Hw - np.abs(Pp[:, 1])) * R.tp
        return ~ins
    ctx['outside'] = outside
    return f'hall_{seed}', K, ctx
