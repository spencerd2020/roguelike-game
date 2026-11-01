"""Vanehold wind-wheel house: banded coursed stone, a steep slate roof on a timber frame, a sailed wind wheel on the
west gable that turns a drive wheel in the loft, and a furnished room that matches the outside.

Inside: flagstone floor, a stone hearth and hood against the east gable whose stack rises through the ridge, a loft on the
tie beams with a ladder. The furniture is the game's shared household set (bed, table, benches, chest, stool, shelves,
lantern, candlestick), placed here and retextured by retexture.py, never remodelled.
Seeded: size, pitch, door and window positions, courses and every stone, board and shingle.
"""
import math

import numpy as np
from mathutils import Matrix, Vector

import vane
from mkit import Kit, V, stream

SLOTS = ['stone', 'flag', 'mortar', 'wood', 'plank', 'shingle', 'iron', 'sail', 'bedding', 'rope', 'mica', 'ember']
GLOW = ('mica', 'ember')


def build(seed):
    K = Kit(SLOTS, GLOW)
    g = stream(seed, 'size')
    L = round(g.uniform(6.6, 8.0), 2)
    W = round(g.uniform(5.0, 5.7), 2)
    t = 0.5
    zp = 0.32
    H = round(g.uniform(2.55, 2.85), 2)
    pitch = g.uniform(46, 53)
    zt = zp + H
    ctx = {'moss_z': zp + 0.7, 'ao_dist': 1.4}
    # ---------- plinth: a platform of big flags on a footing ----------
    P = stream(seed, 'plinth')
    m = 0.45
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
    # front steps down from the door
    # ---------- walls ----------
    C = stream(seed, 'courses')
    cs = vane.courses(C, zp, H)
    O = stream(seed, 'openings')
    dw = 1.02
    du = O.uniform(-L / 2 + t + 0.9, -0.3)
    door_top = vane.snap(cs, zp + 2.0)
    if door_top < zp + 1.9:
        door_top = min([c[0] + c[1] for c in cs if c[0] + c[1] >= zp + 1.9] or [zp + H - 0.3])
    sill = vane.snap(cs, zp + 0.95)
    wtop = vane.snap(cs, sill + 0.78)
    wtop = min(wtop, cs[-2][0])
    openings = {'front': [(du - dw / 2, du + dw / 2, zp, door_top)]}
    wx = O.uniform(du + 1.5, L / 2 - t - 1.1)
    openings['front'].append((wx - 0.32, wx + 0.32, sill, wtop))
    bx = [O.uniform(-L / 2 + t + 2.4, -0.4), O.uniform(0.6, L / 2 - t - 1.8)]
    openings['back'] = [(b - 0.3, b + 0.3, sill, wtop) for b in bx]
    ly = O.uniform(-0.6, 0.6)
    openings['left'] = [(ly - 0.28, ly + 0.28, sill, wtop)]
    lintels = vane.rect_walls(K, C, ctx, L, W, t, cs, openings, zp)
    vane.lintel_beams(K, C, L, W, t, lintels)
    vane.door(K, O, L, W, t, 'front', du - dw / 2, du + dw / 2, zp, door_top, swing=O.uniform(62, 80), hinge=-1)
    for wn, ops in openings.items():
        for (u0, u1, za, zb) in ops:
            if wn == 'front' and u0 < du < u1:
                continue
            vane.window(K, O, L, W, t, wn, u0, u1, za, zb, shutters=wn != 'left')
    # steps: two stone treads in front of the door
    for i, (dz, dy) in enumerate(((zp - 0.11, 0.35), (zp - 0.22, 0.7))):
        K.box((du, -W / 2 - m - dy / 2 + 0.17 * 0, dz / 2), (dw + 0.5 - i * 0.0, 0.36, dz), slot='stone', name='step', e=0.02)
        ctx.setdefault('strat', {})[len(K.parts) - 1] = 2
    # ---------- the roof ----------
    R = vane.Roof(L, W, zt, pitch)
    chim = (L / 2 - t - 0.06, L / 2 + 0.04)          # the stack, in x, standing on the east gable wall
    cy = 0.46
    T = stream(seed, 'roof')
    loft_x = -L / 2 + t + 2.15
    ties = [loft_x] + [loft_x + (i + 1) * (L / 2 - t - 0.9 - loft_x) / 2 for i in range(2)]
    vane.roof_frame(K, T, R, t, holes=[chim], ties=ties)
    vane.gable_boards(K, T, R, t, -1)
    vane.gable_boards(K, T, R, t, 1, skip=[(-cy - 0.02, cy + 0.02)])
    K.use_node('roof')
    hole_s = (R.Hw + R.ov - cy - 0.05) / math.cos(R.p)
    vane.roof_cover(K, T, R, holes=[(chim[0] - 0.03, chim[1] + 0.03)], hole_s=hole_s)
    K.use_node('body')
    # ---------- hearth, hood and stack (east gable) ----------
    Hh = stream(seed, 'hearth')
    xi = L / 2 - t                         # inner face of the east wall
    K.box((xi - 0.42, 0, zp + 0.1), (0.84, 1.5, 0.2), slot='stone', name='hearthstone', e=0.02)
    for s in (-1, 1):   # cheeks
        K.box((xi - 0.3, s * 0.58, zp + 0.2 + 0.47), (0.6, 0.3, 0.94), slot='stone', name='cheek', e=0.02)
    K.beam((xi - 0.58, -0.78, zp + 1.22), (xi - 0.58, 0.78, zp + 1.22), 0.18, 0.2, 'wood', 'mantel', 0.02)
    z = zp + 1.32
    hi = 0
    while z < zt + 0.4:   # the hood narrows as it rises into the stack
        h = Hh.uniform(0.2, 0.28)
        k = min(1.0, (z - zp - 1.32) / (zt + 0.4 - zp - 1.32))
        dep = 0.62 - 0.32 * k
        wid = 1.5 - 0.6 * k
        K.box((xi - dep / 2, 0, z + h / 2), (dep, wid, h), slot='stone', name=f'hood:{hi}', e=0.022)
        ctx['strat'][len(K.parts) - 1] = vane.STRATA[(hi // 2 + 3) % 10]
        z += h
        hi += 1
    # back of the firebox: soot-dark stone set into the wall face
    K.box((xi - 0.02, 0, zp + 0.2 + 0.47), (0.04, 0.86, 0.94), slot='stone', name='fireback', e=0.0)
    # fire: logs and embers
    for i in range(3):
        a = Hh.uniform(-0.4, 0.4)
        K.prism((xi - 0.35 - 0.25 * math.cos(a), -0.3 + i * 0.3, zp + 0.27), V(math.cos(a), math.sin(a) * 0.3, 0.12),
                0.55, 0.06, 0.055, 'wood', 'log', 7)
    K.rock((xi - 0.36, 0.0, zp + 0.22), 0.16, Hh, 'ember', 'embers', 1, (1.6, 2.2, 0.35), 0.2)
    K.light((xi - 0.4, 0, zp + 0.55), (1.0, 0.55, 0.25), 260, 0.25)
    ctx['hearth'] = (xi - 0.35, 0.0, zp + 0.3)
    # the stack outside, from the wall top through the ridge
    z = zt
    top = R.top(0) + 1.0
    si = 0
    while z < top:
        h = min(Hh.uniform(0.22, 0.3), top - z)
        jx, jy = Hh.uniform(-0.012, 0.012), Hh.uniform(-0.012, 0.012)
        K.box(((chim[0] + chim[1]) / 2 + jx, jy, z + h / 2), (chim[1] - chim[0], 2 * cy, h), slot='stone', name=f'stack:{si}', e=0.022)
        ctx['strat'][len(K.parts) - 1] = vane.STRATA[(si // 2 + 5) % 10]
        z += h
        si += 1
    K.box(((chim[0] + chim[1]) / 2, 0, top + 0.05), (chim[1] - chim[0] + 0.16, 2 * cy + 0.16, 0.1), slot='stone', name='capstone', e=0.02)
    for s in (-1, 1):
        K.box(((chim[0] + chim[1]) / 2, s * 0.2, top + 0.17), (0.3, 0.16, 0.14), slot='stone', name='pot', e=0.02)
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
            if xb - xa > 0.08:
                K.box(((xa + xb) / 2, yy + d / 2, zp + 0.02), (xb - xa - 0.014, d - 0.014, 0.04), slot='flag', name='floor', e=0.008)
            xx = xb if xb == x1 else xx + w
        yy += d
    zf = zp + 0.04
    # ---------- loft on the tie beams over the west end, a ladder up to it ----------
    zl = zt + 0.32
    yl = R.Hw - (zl + 0.05 - R.under(R.Hw)) / R.tp - 0.04
    yl = min(yl, W / 2 - t + 0.4)
    K.beam((-L / 2 + t + 0.08, -yl, zt + 0.23), (-L / 2 + t + 0.08, yl, zt + 0.23), 0.16, 0.18, 'wood', 'ledger', 0.015)
    yy = -yl
    while yy < yl - 1e-6:
        bw = min(F.uniform(0.18, 0.26), yl - yy)
        K.box(((-L / 2 + t + loft_x + 0.08) / 2, yy + bw / 2, zl + 0.02), (loft_x + 0.08 - (-L / 2 + t), bw - 0.006, 0.04),
              slot='plank', name='loftboard', e=0.005, axis=(1, 0, 0))
        yy += bw
    lx = loft_x + 0.55
    ly0 = W / 2 - t - 0.32
    for s in (-1, 1):
        K.beam((lx, ly0 + s * 0.22, zf), (loft_x + 0.05, ly0 + s * 0.22, zl + 0.75), 0.07, 0.06, 'wood', 'rail', 0.01)
    nr = 8
    for i in range(1, nr):
        k = i / nr
        p = V(lx + (loft_x + 0.05 - lx) * k, ly0, zf + (zl + 0.75 - zf) * k)
        K.prism(p + V(0, -0.24, 0), V(0, 1, 0), 0.48, 0.022, 0.022, 'wood', 'rung', 6)
    # ---------- furniture: the game's shared household pieces, placed, never remodelled ----------
    # (Spencer, 1 Nov 2026: interiors use our furniture, retextured for the biome by retexture.py). Each entry is a
    # shared model by name, its base centre on the floor and a turn about the vertical; the models' fronts face -y.
    Fu = stream(seed, 'furniture')
    fur = []

    def put(kind, x, y, z, rot=0.0):
        fur.append({'kind': kind, 'x': round(x, 4), 'y': round(y, 4), 'z': round(z, 4), 'rot': round(rot, 4)})
    # plank bed under the loft, along the back wall
    put('bed', -L / 2 + t + 1.08, W / 2 - t - 0.52, zf, math.pi / 2)
    # trestle table and two benches, the middle of the room, a candlestick on the table
    tx, ty = (loft_x + 0.35 + xi - 0.9) / 2 + Fu.uniform(-0.08, 0.08), Fu.uniform(-0.3, -0.1)
    put('table', tx, ty, zf)
    put('bench', tx, ty + 0.64, zf, math.pi)
    put('bench', tx, ty - 0.64, zf)
    put('candlestick', tx + Fu.uniform(0.15, 0.4), ty + Fu.uniform(-0.15, 0.15), zf + 0.76, Fu.uniform(0, 6.28))
    # banded chest by the hearth on the back wall, a stool by the fire
    cxx = Fu.uniform(min(0.9, L / 2 - t - 1.55), L / 2 - t - 1.55)
    put('chest', cxx, W / 2 - t - 0.3, zf)
    put('stool', xi - 1.2, -0.95, zf, Fu.uniform(0, 6.28))
    # open shelves against the front wall, right of the window
    sx0 = wx + 0.55
    if sx0 + 0.95 < L / 2 - t - 0.85:
        put('shelf', sx0 + 0.48, -W / 2 + t + 0.2, zf, math.pi)
    # horn lantern on a chain from the middle tie beam
    lxp = ties[1]
    K.tube([(lxp, ty, zt + 0.14), (lxp, ty, zt - 0.62)], 0.012, 'iron', 'chain', 5)
    put('lantern', lxp, ty, zt - 0.96)
    K.light((lxp, ty, zt - 0.82), (1.0, 0.72, 0.42), 70, 0.1)
    # ---------- outside: a bench by the door and a log stack on the west wall ----------
    Ou = stream(seed, 'outside')
    bxp = du + 1.25 if du + 1.9 < wx - 0.4 else du - 1.3
    put('bench', bxp, -W / 2 - 0.3, zp)
    ctx['furniture'] = fur
    K.markers['furniture'] = fur
    for row in range(5):
        for i in range(7 - (row % 2)):
            yy = -1.3 + i * 0.37 + (0.18 if row % 2 else 0)
            r = Ou.uniform(0.08, 0.11)
            K.prism((-L / 2 - 0.05, yy, zp + 0.1 + row * 0.19), V(-1, Ou.uniform(-0.05, 0.05), 0), 0.42, r, r, 'wood', 'log', 7, spin=Ou.uniform(0, 1))
    # ---------- the wind wheel on the west gable, driving a wheel in the loft ----------
    hub = V(-L / 2 - 0.55, 0, R.zc(0) - 1.0)
    vane.wind_wheel(K, Ou, hub, V(-1, 0, 0), r=min(1.45, (hub.z - zt) + 0.75), inside=0.95)
    K.markers['rotor'] = tuple(hub)
    K.markers['door'] = (du, -W / 2, zp)
    K.markers['smoke'] = ((chim[0] + chim[1]) / 2, 0.0, top + 0.3)
    # for the game port's room plan: where the fire burns, the hearthstone ledge, and spare floor for loose things
    K.markers['hearth'] = (xi - 0.35, 0.0, zp + 0.38)
    K.markers['room'] = {'L': L, 'W': W, 't': t, 'zf': zf, 'zt': zt}
    K.markers['slots'] = [
        ['hearth', xi - 0.7, -0.62, zp + 0.2, 0.0, 0.3, 0.3],
        ['floor', -L / 2 + t + 0.45, -W / 2 + t + 0.45, zf, 0.0, 0.7, 0.7],
        ['floor', xi - 0.5, W / 2 - t - 1.2, zf, 0.0, 0.6, 0.6],
        ['door', du + 0.75, -W / 2 + t + 0.35, zf, 0.0, 0.5, 0.4],
    ]
    ctx['pivots'] = {'rotor': tuple(hub)}
    ctx['footprint'] = [L + 2 * m, W + 2 * m]

    # inside the room = inside the inner wall faces and under the roof
    def outside(Pp, Nn):
        ins = (np.abs(Pp[:, 0]) < L / 2 - t + 0.06) & (np.abs(Pp[:, 1]) < W / 2 - t + 0.06) & (Pp[:, 2] > zp - 0.05)
        ins &= Pp[:, 2] < zt + 0.23 + (R.Hw - np.abs(Pp[:, 1])) * R.tp
        return ~ins
    ctx['outside'] = outside
    return f'house_{seed}', K, ctx
