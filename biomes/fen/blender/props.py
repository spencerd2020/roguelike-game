"""Fen props: boardwalk, lantern post, dugout, peat footings and a cut-bank, eel trap.

The boardwalk is split-log treads laid across two stringers on paired piles, a 4 m segment the page chains along a
path. Peat is cut from the bank in terraces and set to dry in small leaning footings, the fen's fuel and its walls.
"""
import math
from mathutils import Matrix, Vector
import kit
from kit import box, beam, cyl, lathe, tube

DECK = 0.45   # boardwalk tread top above the water


def P(r, a, z):
    return Vector((r * math.cos(a), r * math.sin(a), z))


def boardwalk(seed, variant):
    rng = kit.stream(seed, 'boardwalk:' + variant)
    R = kit.Rec()
    L, W = 4.0, 1.25
    for x in (-L / 2 + 0.25, L / 2 - 0.25):
        for y in (-W / 2 + 0.06, W / 2 - 0.06):
            top = DECK - 0.1 + (rng.uniform(0.0, 0.5) if (variant == 'rail' and y > 0) else rng.uniform(-0.02, 0.08))
            cyl(R, f'pile:{x}:{y}', 'timber', (x + rng.uniform(-0.03, 0.03), y, -1.0), (x, y, top), 0.075, 0.068, segs=8, e=0.012)
        beam(R, f'bearer:{x}', 'timber', (x, -W / 2 - 0.05, DECK - 0.2), (x, W / 2 + 0.05, DECK - 0.2), 0.12, 0.1, e=0.015)
    for y in (-W / 2 + 0.2, W / 2 - 0.2):
        beam(R, f'stringer:{y}', 'timber', (-L / 2, y, DECK - 0.11), (L / 2, y, DECK - 0.11), 0.13, 0.11, e=0.015)
    x = -L / 2 + 0.01
    k = 0
    while x < L / 2 - 0.05:
        w = rng.uniform(0.16, 0.22)
        r = w / 2
        y0, y1 = -W / 2 + rng.uniform(0, 0.06), W / 2 - rng.uniform(0, 0.06)
        # hewn split-log treads: flat tops, heavy chamfers, each a little skewed
        M = Matrix.Translation((x + r, (y0 + y1) / 2, DECK - 0.04)) @ Matrix.Rotation(rng.uniform(-0.04, 0.04), 4, 'Z') @ Matrix.Rotation(rng.uniform(-0.015, 0.015), 4, 'Y')
        box(R, f'tread:{k}', 'deck', M, (w, y1 - y0, 0.1), e=0.03, g=(0, 1, 0))
        x += w + 0.012
        k += 1
    if variant == 'rail':
        for xx in (-L / 2 + 0.25, L / 2 - 0.25):
            pass
        beam(R, 'rail', 'timber', (-L / 2, W / 2 - 0.06, DECK + 0.78), (L / 2, W / 2 - 0.06, DECK + 0.78), 0.08, 0.08, e=0.012)
        for xx in (-L / 2 + 0.25, 0.0, L / 2 - 0.25):
            cyl(R, f'rail_post:{xx}', 'timber', (xx, W / 2 - 0.06, DECK - 0.1), (xx, W / 2 - 0.06, DECK + 0.84), 0.055, segs=7, e=0.01)
    return R, dict(length=L, width=W, deck=DECK), None


def lantern_post(seed):
    rng = kit.stream(seed, 'lantern')
    R = kit.Rec()
    cyl(R, 'post', 'timber', (0, 0, -0.9), (0, 0, 2.6), 0.08, 0.065, segs=8, e=0.012)
    beam(R, 'arm', 'timber', (0, 0, 2.45), (0.62, 0, 2.5), 0.07, 0.07, e=0.01)
    beam(R, 'brace', 'timber', (0, 0, 2.0), (0.42, 0, 2.45), 0.05, 0.05, e=0.008)
    lc = Vector((0.56, 0, 2.08))
    lathe(R, 'glass', 'glass', [(0.0001, -0.13), (0.09, -0.12), (0.11, 0.0), (0.09, 0.12), (0.0001, 0.13)], 10, M=Matrix.Translation(lc), close_top=False)
    for i in range(6):
        a = i * math.pi / 3
        cyl(R, f'cage:{i}', 'wicker', lc + P(0.12, a, -0.16), lc + P(0.12, a, 0.16), 0.012, segs=4)
    lathe(R, 'cap', 'wicker', [(0.16, 0.16), (0.05, 0.27), (0.0001, 0.28)], 10, M=Matrix.Translation(lc), close_top=False)
    lathe(R, 'base', 'wicker', [(0.0001, -0.19), (0.15, -0.17), (0.15, -0.14)], 10, M=Matrix.Translation(lc), close_top=False)
    cyl(R, 'hang', 'rope', lc + Vector((0, 0, 0.27)), (0.56, 0, 2.47), 0.01, segs=4)
    # a twist of dried sedge tied under the arm, a fen ward against the mist
    for k in range(9):
        a = k * 0.7
        tube(R, f'ward:{k}', 'sedge', [Vector((0.25, 0, 2.38)), Vector((0.25, 0, 2.38)) + P(0.06, a, -0.25), Vector((0.25, 0, 2.38)) + P(0.09, a, -0.5)],
             [0.012, 0.01, 0.004], segs=3, cap1=False)
    cyl(R, 'ward_tie', 'rope', (0.25, 0, 2.33), (0.25, 0, 2.38), 0.03, segs=8)
    return R, dict(light=list(lc)), None


def dugout(seed):
    rng = kit.stream(seed, 'dugout')
    R = kit.Rec()
    L = 4.6
    n = 15
    # a hollowed log: outer hull and inner hull meet at the gunwale
    bm = R.bm
    rings_o, rings_i = [], []
    for i in range(n):
        t = i / (n - 1)
        x = -L / 2 + L * t
        w = 0.36 * math.sin(math.pi * min(1, 0.06 + t * 0.88)) ** 0.6 + 0.03
        d = 0.32 * math.sin(math.pi * min(1, 0.05 + t * 0.9)) ** 0.4 + 0.03
        zg = 0.32 + 0.12 * (abs(t - 0.5) * 2) ** 3
        ro, ri = [], []
        for k in range(11):
            a = math.pi * k / 10
            ro.append(bm.verts.new((x, -math.cos(a) * w, zg - math.sin(a) * d)))
            ri.append(bm.verts.new((x, -math.cos(a) * (w - 0.05), zg - math.sin(a) * (d - 0.05) + 0.0)))
        rings_o.append(ro)
        rings_i.append(ri)
    faces = []
    for i in range(n - 1):
        for k in range(10):
            faces.append(bm.faces.new((rings_o[i][k], rings_o[i + 1][k], rings_o[i + 1][k + 1], rings_o[i][k + 1])))
            faces.append(bm.faces.new((rings_i[i][k + 1], rings_i[i + 1][k + 1], rings_i[i + 1][k], rings_i[i][k])))
        for k in (0, 10):
            a, b = (rings_o, rings_i) if k == 0 else (rings_i, rings_o)
            faces.append(bm.faces.new((a[i][k], a[i + 1][k], b[i + 1][k], b[i][k])))
    for i in (0, n - 1):
        ring = rings_o[i] + list(reversed(rings_i[i]))
        faces.append(bm.faces.new(ring if i else list(reversed(ring))))
    R.tag(faces, 'hull', 'wood', (1, 0, 0))
    beam(R, 'paddle_shaft', 'wood', (-0.6, 0.05, 0.2), (1.0, -0.1, 0.36), 0.04, 0.04, e=0.008)
    box(R, 'paddle_blade', 'wood', Matrix.Translation((1.25, -0.12, 0.38)) @ Matrix.Rotation(0.1, 4, 'Z'), (0.5, 0.16, 0.025), e=0.008)
    return R, dict(), None


def peat_bank(seed):
    """A cut bank: three stepped terraces of peat with spade-cut faces, and footings of drying peats on the top."""
    rng = kit.stream(seed, 'peatbank')
    R = kit.Rec()
    W = 6.0
    steps = [(0.0, 0.0, 1.0), (1.0, 0.45, 1.2), (2.2, 0.9, 2.6)]   # (y0, z top-offset, depth)
    for i, (y0, zt, d) in enumerate(steps):
        zt0 = 0.2 + zt
        # the cut face: rows of spade-width slabs, each a slightly different depth, so the face reads as cut by hand
        nx = int(W / 0.32)
        for k in range(nx):
            x = -W / 2 + (k + 0.5) * W / nx
            dd = rng.uniform(-0.03, 0.03)
            box(R, f'cut:{i}:{k}', 'peat', Matrix.Translation((x, y0 + d / 2 + dd, zt0 / 2 - 0.15)), (W / nx - 0.01, d, zt0 + 0.3), e=0.02, g=(0, 0, 1))
        # sedge and sphagnum skin on top of the highest bank only
        if i == len(steps) - 1:
            box(R, 'turf', 'sphag', Matrix.Translation((0, y0 + d / 2, zt0 + 0.04)), (W + 0.04, d + 0.04, 0.1), e=0.03)
    # footings: four peats leaning together, a fifth across the top
    for f in range(7):
        cx, cy = rng.uniform(-2.4, 2.4), rng.uniform(2.6, 4.4)
        z0 = 0.2 + 0.9 + 0.09
        a0 = rng.uniform(0, 6.28)
        for j in range(4):
            a = a0 + j * math.pi / 2
            c = Vector((cx, cy, z0)) + P(0.13, a, 0.18)
            M = Matrix.Translation(c) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Rotation(-0.35, 4, 'Y')
            box(R, f'footing:{f}:{j}', 'peat', M, (0.12, 0.2, 0.38), e=0.025, g=(0, 0, 1))
        box(R, f'footing_top:{f}', 'peat', Matrix.Translation((cx, cy, z0 + 0.42)) @ Matrix.Rotation(a0, 4, 'Z'), (0.36, 0.18, 0.11), e=0.025)
    # the turf spade, stuck in the bank
    beam(R, 'spade_shaft', 'wood', (1.6, 1.25, 0.65 + 0.2), (1.75, 1.35, 1.95), 0.045, 0.045, e=0.008)
    box(R, 'spade_blade', 'iron', Matrix.Translation((1.58, 1.24, 0.55)) @ Matrix.Rotation(0.1, 4, 'X'), (0.2, 0.025, 0.32), e=0.004)
    box(R, 'spade_wing', 'iron', Matrix.Translation((1.66, 1.24, 0.6)) @ Matrix.Rotation(0.1, 4, 'X'), (0.025, 0.12, 0.26), e=0.003)
    return R, dict(top=1.1), None


def eel_trap(seed):
    R = kit.Rec()
    # a woven cone, lashed to a stake, laid in the shallows
    lathe(R, 'trap', 'wicker', [(0.24, 0.0), (0.22, 0.4), (0.15, 0.9), (0.04, 1.25), (0.0001, 1.27)], 16,
          M=Matrix.Translation((0, 0, 0.18)) @ Matrix.Rotation(math.pi / 2 - 0.12, 4, 'Y'), close_top=False, close_bottom=False)
    lathe(R, 'mouth', 'wicker', [(0.24, 0.0), (0.12, 0.25), (0.11, 0.25)], 16,
          M=Matrix.Translation((0, 0, 0.18)) @ Matrix.Rotation(math.pi / 2 - 0.12, 4, 'Y'), close_top=False, close_bottom=False)
    cyl(R, 'stake', 'timber', (0.1, 0.32, -0.6), (0.12, 0.3, 1.0), 0.04, segs=7, e=0.008)
    cyl(R, 'lash', 'rope', (0.12, 0.3, 0.35), (0.3, 0.05, 0.25), 0.012, segs=4)
    return R, dict(), None


def peat_rack(seed):
    """A peat-drying rack: two leaning trestles carry three poles, and cut peats are laid across them in rows to dry in
    the wind, the fuel of every hearth in the fen. Racks stand on the bank, where the peat is cut."""
    rng = kit.stream(seed, 'peat_rack')
    R = kit.Rec()
    L = 2.6
    for i, x in enumerate((-L / 2 + 0.15, L / 2 - 0.15)):
        for side in (-1, 1):
            cyl(R, f'leg:{i}:{side}', 'timber', (x + rng.uniform(-0.03, 0.03), side * 0.55, -0.15), (x, side * 0.12, 1.25), 0.05, 0.045,
                segs=7, e=0.01)
        cyl(R, f'brace:{i}', 'timber', (x, -0.42, 0.45), (x, 0.42, 0.45), 0.03, segs=6, e=0.006)
        cyl(R, f'lash:{i}', 'rope', (x - 0.06, 0, 1.18), (x + 0.06, 0, 1.18), 0.06, segs=6)
    for k, (y, z) in enumerate(((-0.34, 0.75), (0.0, 1.22), (0.34, 0.75))):
        cyl(R, f'pole:{k}', 'timber', (-L / 2 - 0.12, y, z), (L / 2 + 0.12, y, z + rng.uniform(-0.02, 0.02)), 0.035, segs=7, e=0.006)
    # peats laid across the low poles, two to a bay, a few gaps where they have been taken
    for k, (y, z) in enumerate(((-0.34, 0.75), (0.34, 0.75))):
        x = -L / 2 + 0.25
        j = 0
        while x < L / 2 - 0.2:
            if rng.random() < 0.85:
                M = Matrix.Translation((x, y, z + 0.075)) @ Matrix.Rotation(rng.uniform(-0.1, 0.1), 4, 'Z') @ \
                    Matrix.Rotation(rng.uniform(-0.08, 0.08), 4, 'X')
                box(R, f'peat:{k}:{j}', 'peat', M, (0.12, 0.3, 0.1), e=0.022, g=(0, 0, 1))
            x += rng.uniform(0.15, 0.19)
            j += 1
    # a few drying on the ground below, stood on end in pairs
    for j in range(4):
        x = rng.uniform(-1.0, 1.0)
        a = rng.uniform(0, math.pi)
        for d in (-1, 1):
            M = Matrix.Translation((x + d * 0.06 * math.cos(a), d * 0.06 * math.sin(a), 0.17)) @ Matrix.Rotation(a, 4, 'Z') @ \
                Matrix.Rotation(d * 0.25, 4, 'X')
            box(R, f'ground_peat:{j}:{d}', 'peat', M, (0.12, 0.1, 0.32), e=0.022, g=(0, 0, 1))
    return R, dict(length=L), None


def dock(seed):
    """A mooring stage: a square deck on piles where boardwalks meet and dugouts tie up, with bollards at the corners."""
    rng = kit.stream(seed, 'dock')
    R = kit.Rec()
    W = 3.2
    top = DECK - 0.04
    for x in (-W / 2 + 0.2, 0, W / 2 - 0.2):
        for y in (-W / 2 + 0.2, 0, W / 2 - 0.2):
            cyl(R, f'pile:{x}:{y}', 'timber', (x + rng.uniform(-0.03, 0.03), y, -1.0), (x, y, top - 0.12), 0.08, 0.072, segs=8, e=0.012)
    for y in (-W / 2 + 0.2, 0, W / 2 - 0.2):
        box(R, f'bearer:{y}', 'timber', Matrix.Translation((0, y, top - 0.17)), (W, 0.14, 0.1), e=0.015, g=(1, 0, 0))
    n = 13
    for k in range(n):
        x = -W / 2 + (k + 0.5) * W / n
        box(R, f'tread:{k}', 'deck', Matrix.Translation((x, 0, top - 0.06)) @ Matrix.Rotation(rng.uniform(-0.01, 0.01), 4, 'Z'),
            (W / n - 0.02, W + rng.uniform(-0.05, 0.05), 0.08), e=0.012, g=(0, 1, 0))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(R, f'bollard:{sx}:{sy}', 'timber', (sx * (W / 2 - 0.12), sy * (W / 2 - 0.12), top - 0.1),
                (sx * (W / 2 - 0.12), sy * (W / 2 - 0.12), top + 0.55), 0.07, 0.06, segs=8, e=0.012)
            cyl(R, f'rope:{sx}:{sy}', 'rope', (sx * (W / 2 - 0.12) - 0.08, sy * (W / 2 - 0.12), top + 0.4),
                (sx * (W / 2 - 0.12) + 0.08, sy * (W / 2 - 0.12), top + 0.4), 0.085, segs=7)
    return R, dict(width=W, top=top), None


ASSETS = {
    'boardwalk': dict(fn=lambda: boardwalk('ambermere', 'plain'), size=1024),
    'boardwalk_rail': dict(fn=lambda: boardwalk('ambermere', 'rail'), size=1024),
    'lantern_post': dict(fn=lambda: lantern_post('ambermere'), size=1024),
    'dugout': dict(fn=lambda: dugout('ambermere'), size=1024),
    'peat_bank': dict(fn=lambda: peat_bank('ambermere'), size=2048, cfg=dict(ground=0.2)),
    'eel_trap': dict(fn=lambda: eel_trap('ambermere'), size=512),
    'peat_rack': dict(fn=lambda: peat_rack('ambermere'), size=1024),
    'dock': dict(fn=lambda: dock('ambermere'), size=1024),
}
