"""Fen roundhouses: peat-block walls on a wattle-ringed crannog, a bark-shingle cone with an open smoke hole.

The inside is built from the same pieces as the outside, so every opening matches: the door and windows are real holes
through the full thickness of the wall, the smoke hole over the hearth is the open crown of the roof (with a raised cap
on posts, seen from outside), and in the tall house the upper windows light the sleeping loft. The furniture
is the game's shared set, not modelled here: the builder only records where each piece stands (meta `furniture`),
where the openings make sense: the bed away from the door draught, the fuel stack by the door, the table under a
window, the hearth under the smoke hole. The page places and recolours them.

Variants (seeded):  small  one room, one window          medium  two windows, table and stools, cooking tripod
                    tall   loft over the back half with a ladder, upper windows, the bed upstairs, a chest below
Z up, the water line at z = 0, the door faces -Y.
"""
import math
from mathutils import Matrix, Vector
import kit
from kit import box, beam, cyl, lathe, tube

VARIANTS = {
    'small':  dict(Rw=2.3, T=0.48, Hw=1.95, windows=[(20, 'low')], table=False, loft=False, tripod=False, chest=False),
    'medium': dict(Rw=2.85, T=0.5, Hw=2.15, windows=[(15, 'low'), (155, 'low')], table=True, loft=False, tripod=True, chest=False),
    'tall':   dict(Rw=3.35, T=0.52, Hw=3.35, windows=[(10, 'low'), (170, 'low'), (62, 'high'), (118, 'high')], table=True,
                   loft=True, tripod=True, chest=True),
}
PITCH = math.radians(47)
ZD = 0.58          # deck top above the water


def P(r, a, z):
    return Vector((r * math.cos(a), r * math.sin(a), z))


def peat_block(R, part, a0, a1, r0, r1, z0, z1, e):
    bm = R.bm
    vs = []
    for z in (z0, z1):
        for (r, a) in ((r0, a0), (r1, a0), (r1, a1), (r0, a1)):
            vs.append(bm.verts.new(P(r, a, z)))
    q = lambda *i: bm.faces.new([vs[k] for k in i])
    faces = [q(3, 2, 1, 0), q(4, 5, 6, 7), q(0, 1, 5, 4), q(1, 2, 6, 5), q(2, 3, 7, 6), q(3, 0, 4, 7)]
    verts = kit._chamfer(R, vs, e)
    R.tag(kit.Rec.faces_of(verts), part, 'peat', P(1, (a0 + a1) / 2 + math.pi / 2, 0))


def build(variant='medium', seed='fen'):
    V = VARIANTS[variant]
    rng = kit.stream(seed, 'house:' + variant)
    R = kit.Rec()
    Rw, T, Hw = V['Rw'], V['T'], V['Hw']
    Ro, Rm = Rw + T, Rw + T / 2
    Rd = Ro + 1.25
    door_a = -math.pi / 2
    # ---------------------------------------------------------------- the crannog: wattle ring, piles, fill, deck
    n_piles = int(2 * math.pi * Rd / 0.46)
    tops = []
    for i in range(n_piles):
        a = 2 * math.pi * i / n_piles + rng.uniform(-0.01, 0.01)
        top = ZD + rng.uniform(0.05, 0.42) if rng.random() < 0.8 else ZD - 0.05
        r0 = rng.uniform(0.065, 0.09)
        lean = rng.uniform(-0.04, 0.04)
        cyl(R, f'pile:{i}', 'timber', P(Rd, a, -0.9), P(Rd + lean, a + lean * 0.1, top), r0, r0 * 0.92, segs=7, e=0.012)
        tops.append(a)
    for k in range(9):                            # woven rods, in front of one pile and behind the next
        z = -0.25 + k * 0.088
        m = n_piles * 2
        for i in range(m):                        # one short rod per half-span, so each is its own atlas island
            a0, a1 = 2 * math.pi * i / m, 2 * math.pi * (i + 1.15) / m
            o0 = 0.07 if (i + k) % 2 else -0.07
            o1 = -o0
            tube(R, f'wattle:{k}:{i}', 'wicker', [P(Rd + o0, a0, z), P(Rd + (o0 + o1) / 2, (a0 + a1) / 2, z + 0.005), P(Rd + o1, a1, z)],
                 [0.022, 0.022, 0.022], segs=5)
    for q in range(8):
        kit.revolve(R, f'fill:{q}', 'peat', [(0.01, ZD - 0.4), (Rd - 0.02, ZD - 0.4), (Rd - 0.02, ZD - 0.16), (0.01, ZD - 0.16)], q * math.pi / 4, (q + 1) * math.pi / 4, 6, Matrix())
    # deck boards, split logs side by side; they run under the wall, so the floor inside is the same deck
    y = -Rd + 0.05
    bi = 0
    while y < Rd - 0.1:
        w = rng.uniform(0.2, 0.26)
        yc = y + w / 2
        half = math.sqrt(max(0.0, (Rd - 0.12) ** 2 - yc ** 2))
        if half > 0.3:
            x0, x1 = -half + rng.uniform(0, 0.08), half - rng.uniform(0, 0.08)
            M = Matrix.Translation(((x0 + x1) / 2, yc, ZD - 0.045)) @ Matrix.Rotation(rng.uniform(-0.006, 0.006), 4, 'X')
            box(R, f'board:{bi}', 'deck', M, (x1 - x0, w - 0.018, 0.09), e=0.02, g=(1, 0, 0))
        bi += 1
        y += w
    # a step-down landing in front of the door, where the boardwalk ties on
    for k in range(3):
        yy = -Rd - 0.15 - k * 0.25
        box(R, f'landing:{k}', 'deck', Matrix.Translation((0, yy, ZD - 0.06 - k * 0.0)), (1.5, 0.23, 0.09), e=0.02, g=(1, 0, 0))
    for sx in (-0.62, 0.62):
        cyl(R, f'landing_post:{sx}', 'timber', (sx, -Rd - 0.6, -0.8), (sx, -Rd - 0.6, ZD - 0.1), 0.07, segs=7, e=0.01)
        beam(R, f'landing_bearer:{sx}', 'timber', (sx, -Rd + 0.1, ZD - 0.14), (sx, -Rd - 0.75, ZD - 0.14), 0.1, 0.1, e=0.015)

    # ---------------------------------------------------------------- openings
    openings = [dict(a=door_a, w=1.0, z0=0.0, z1=1.92, kind='door')]
    for (deg, lvl) in V['windows']:
        a = math.radians(deg)
        if lvl == 'low':
            openings.append(dict(a=a, w=0.62, z0=0.98, z1=1.52, kind='window'))
        else:
            openings.append(dict(a=a, w=0.52, z0=2.62, z1=3.04, kind='window'))
    LINT = 0.2   # lintel depth above every opening
    # ---------------------------------------------------------------- peat-block wall, running bond, openings cut
    ch = 0.255
    courses = int(round(Hw / ch))
    ch = Hw / courses
    blen = 0.56
    for c in range(courses):
        z0, z1 = ZD + c * ch, ZD + (c + 1) * ch
        n = max(8, int(round(2 * math.pi * Rm / blen)))
        da = 2 * math.pi / n
        off = (c % 2) * da / 2 + rng.uniform(-0.02, 0.02)
        cut = []
        for o in openings:
            if z1 > ZD + o['z0'] + 0.001 and z0 < ZD + o['z1'] + LINT - 0.001:
                h = (o['w'] / 2) / Rm
                cut.append((o['a'] - h, o['a'] + h))
        for b in range(n):
            a0, a1 = off + b * da, off + (b + 1) * da
            segs = [(a0, a1)]
            for (c0, c1) in cut:
                nxt = []
                for (s0, s1) in segs:
                    for k in (-1, 0, 1):              # openings may straddle the angle wrap
                        q0, q1 = c0 + 2 * math.pi * k, c1 + 2 * math.pi * k
                        if q1 <= s0 or q0 >= s1:
                            continue
                        break
                    else:
                        nxt.append((s0, s1))
                        continue
                    if q0 > s0:
                        nxt.append((s0, q0))
                    if q1 < s1:
                        nxt.append((q1, s1))
                segs = nxt
            for (s0, s1) in segs:
                if (s1 - s0) * Rm < 0.1:
                    continue
                g = 0.004 / Rm
                jr = rng.uniform(-0.012, 0.012)
                sink = rng.uniform(0, 0.012)
                peat_block(R, f'peat:{c}:{b}:{s0:.3f}', s0 + g, s1 - g, Rw + jr, Ro + jr, z0 + 0.003, z1 - sink, 0.035)
    # ---------------------------------------------------------------- frames: jambs, lintels, sills, door, shutters
    for i, o in enumerate(openings):
        a, h = o['a'], (o['w'] / 2) / Rm
        tdir = Vector((-math.sin(a), math.cos(a), 0))
        rdir = Vector((math.cos(a), math.sin(a), 0))
        zb, zt = ZD + o['z0'], ZD + o['z1']
        for s, aa in ((-1, a - h), (1, a + h)):
            c0 = P(Rm, aa, 0) - tdir * s * 0.07
            M = Matrix.Translation((c0.x, c0.y, (zb + zt) / 2)) @ Matrix.Rotation(aa, 4, 'Z')
            box(R, f'jamb:{i}:{s}', 'timber', M, (T + 0.04, 0.14, zt - zb), e=0.018, g=(0, 0, 1))
        cl = P(Rm, a, zt + LINT / 2)
        M = Matrix.Translation(cl) @ Matrix.Rotation(a, 4, 'Z')
        box(R, f'lintel:{i}', 'paint' if o['kind'] == 'door' else 'timber', M, (T + 0.08, o['w'] + 0.6, LINT), e=0.025, g=tdir)
        if o['kind'] == 'window':
            cs = P(Rm + 0.06, a, zb - 0.05)
            box(R, f'sill:{i}', 'timber', Matrix.Translation(cs) @ Matrix.Rotation(a, 4, 'Z'), (T + 0.2, o['w'] + 0.3, 0.1), e=0.02, g=tdir)
            # the shutter stands open against the outside wall, hinged on the jamb
            hinge = P(Ro + 0.03, a + h, 0) + tdir * 0.06
            sc = hinge + tdir * (o['w'] / 2) + rdir * 0.04
            M = Matrix.Translation((sc.x, sc.y, (zb + zt) / 2)) @ Matrix.Rotation(a, 4, 'Z')
            for k in range(3):
                pw = o['w'] / 3
                cc = Matrix.Translation((0, -o['w'] / 2 + pw * (k + 0.5), 0))
                box(R, f'shutter:{i}:{k}', 'timber', M @ cc, (0.04, pw - 0.01, zt - zb - 0.02), e=0.008, g=(0, 0, 1))
            box(R, f'shutter_ledge:{i}', 'timber', M @ Matrix.Translation((0.035, 0, 0)), (0.03, o['w'] - 0.04, 0.08), e=0.008, g=tdir)
        else:
            box(R, 'threshold', 'timber', Matrix.Translation(P(Rm, a, ZD + 0.03)) @ Matrix.Rotation(a, 4, 'Z'), (T + 0.1, o['w'] + 0.1, 0.07), e=0.02, g=tdir)
            # plank door, swung open into the room against the wall on its hinge side
            hinge = P(Rw - 0.05, a - h, 0)
            t2 = Vector((-math.sin(a - h), math.cos(a - h), 0))
            ddir = (-t2 + Vector((math.cos(a - h), math.sin(a - h), 0)) * -0.22).normalized()
            nrm = Vector((-ddir.y, ddir.x, 0))
            if nrm.dot(-Vector((hinge.x, hinge.y, 0))) < 0:
                nrm = -nrm
            dw = o['w'] - 0.04
            ang = math.atan2(ddir.y, ddir.x)
            for k in range(4):
                pc = hinge + ddir * (dw / 4 * (k + 0.5)) + nrm * 0.03
                M = Matrix.Translation((pc.x, pc.y, ZD + 0.04 + (zt - zb - 0.08) / 2)) @ Matrix.Rotation(ang, 4, 'Z')
                box(R, f'door:{k}', 'timber', M, (dw / 4 - 0.008, 0.045, zt - zb - 0.08), e=0.008, g=(0, 0, 1))
            for k, zz in enumerate((0.35, 1.5)):
                pc = hinge + ddir * (dw / 2) + nrm * 0.075
                M = Matrix.Translation((pc.x, pc.y, ZD + zz)) @ Matrix.Rotation(ang, 4, 'Z')
                box(R, f'door_ledge:{k}', 'timber', M, (dw - 0.06, 0.035, 0.12), e=0.01, g=ddir)
                pc2 = hinge + ddir * 0.28 - nrm * 0.005
                M = Matrix.Translation((pc2.x, pc2.y, ZD + zz)) @ Matrix.Rotation(ang, 4, 'Z')
                box(R, f'hinge:{k}', 'iron', M, (0.5, 0.012, 0.05), e=0.003, g=ddir)
    # ---------------------------------------------------------------- wall head, rafters, laths, shingles, smoke hole
    zt = ZD + Hw
    tp = math.tan(PITCH)
    Re = Ro + 0.6
    zof = lambda r: zt + 0.07 + (Ro - r) * tp      # underside line of the rafters
    for q in range(16):
        kit.revolve(R, f'wallhead:{q}', 'clay', [(Rw, zt), (Ro + 0.015, zt), (Ro + 0.015, zof(Ro + 0.015) - 0.02), (Rw, zof(Rw) - 0.02)],
                    q * math.pi / 8, (q + 1) * math.pi / 8, 4, Matrix())
    rc = 0.33
    zap = zof(rc)
    nr = 18 if Rw < 3 else 22
    rr = 0.065
    for i in range(nr):
        a = 2 * math.pi * i / nr + rng.uniform(-0.015, 0.015)
        p0 = P(Re, a, zof(Re) + rr)
        p1 = P(rc + 0.02, a, zap + rr)
        cyl(R, f'rafter:{i}', 'timber', p0, p1, rr, rr * 0.8, segs=7, e=0.01)
    for i in range(12):
        cyl(R, f'crown:{i}', 'timber', P(rc, 2 * math.pi * (i - 0.1) / 12, zap + 0.05), P(rc, 2 * math.pi * (i + 1.1) / 12, zap + 0.05), 0.07, segs=7)
    slope = 1 / math.cos(PITCH)
    s_len = (Re - rc) * slope
    lath_s = 0.4
    nl = int(s_len / lath_s)
    for k in range(nl):
        r = Re - 0.15 - k * lath_s / slope
        z = zof(r) + 2 * rr + 0.02
        for i in range(nr):
            cyl(R, f'lath:{k}:{i}', 'timber', P(r, 2 * math.pi * (i - 0.08) / nr, z), P(r, 2 * math.pi * (i + 1.08) / nr, z), 0.022, segs=5)
    # bark shingles in overlapping courses, butt ends tipped up a few degrees, lichen where the sky reaches
    course = 0.2
    sh_l = 0.46
    k = 0
    s = 0.0
    while True:
        r = Re + 0.05 - s / slope
        if r < rc + 0.32:
            break
        z = zof(r) + 2 * rr + 0.055 + k * 0.0015
        circ = 2 * math.pi * r
        n = max(10, int(circ / 0.3))
        ph = (k % 2) * 0.5 + rng.uniform(-0.1, 0.1)
        for j in range(n):
            a = 2 * math.pi * (j + ph) / n
            w = circ / n + 0.03
            downhill = Vector((math.cos(a) * math.cos(PITCH), math.sin(a) * math.cos(PITCH), -math.sin(PITCH)))
            tilt = math.radians(rng.uniform(2, 6))
            c0 = P(r, a, z) - downhill * (-sh_l / 2 + 0.02)
            M = Matrix.Translation(c0) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Rotation(PITCH - tilt, 4, 'Y') \
                @ Matrix.Rotation(rng.uniform(-0.04, 0.04), 4, 'X')
            box(R, f'shingle:{k}:{j}', 'shingle', M, (sh_l, w, 0.022), e=0.006, g=-downhill)
        k += 1
        s += course
    # the smoke cap: a small shingled cone on four posts, high enough that smoke leaves and rain does not
    zc = zap + 0.55
    for i in range(4):
        a = math.pi / 4 + i * math.pi / 2
        cyl(R, f'cap_post:{i}', 'timber', P(rc - 0.02, a, zap + 0.05), P(rc - 0.04, a, zc), 0.035, segs=6, e=0.006)
    lathe(R, 'cap', 'shingle', [(0.72, zc - 0.06), (0.72, zc), (0.05, zc + 0.5), (0.0001, zc + 0.5)], 20, close_top=False)
    # ---------------------------------------------------------------- inside
    hx, hy = (0.0, -0.55) if V['loft'] else (0.0, 0.0)
    lathe(R, 'hearth_bed', 'clay', [(0.8, ZD), (0.82, ZD + 0.08), (0.76, ZD + 0.13), (0.0001, ZD + 0.13)], 28,
          M=Matrix.Translation((hx, hy, 0)), close_top=False)
    ns = 10
    for i in range(ns):
        a = 2 * math.pi * i / ns + rng.uniform(-0.1, 0.1)
        sr = rng.uniform(0.12, 0.17)
        c0 = Vector((hx, hy, 0)) + P(0.66, a, ZD + 0.1)
        wob = lambda aa, zz, s0=rng.random() * 9: 1 + 0.18 * math.sin(aa * 3 + s0) * math.cos(zz * 7 + s0)
        lathe(R, f'hstone:{i}', 'stone', [(sr * 0.75, -0.02), (sr, 0.05), (sr * 0.9, 0.12), (sr * 0.45, 0.17), (0.0001, 0.18)], 9,
              M=Matrix.Translation(c0) @ Matrix.Rotation(a, 4, 'Z'), wob=wob, close_top=False)
    for i in range(12):
        a, rr2 = rng.uniform(0, 2 * math.pi), math.sqrt(rng.random()) * 0.38
        c0 = Vector((hx, hy, ZD + 0.14)) + P(rr2, a, 0)
        sz = rng.uniform(0.035, 0.07)
        lathe(R, f'ember:{i}', 'ember', [(sz, 0), (sz * 0.8, sz * 0.6), (0.0001, sz * 0.8)], 6, M=Matrix.Translation(c0), close_top=False)
    for i in range(3):
        a = i * 2 * math.pi / 3 + 0.3
        p0 = Vector((hx, hy, ZD + 0.17)) + P(0.42, a, 0)
        p1 = Vector((hx, hy, ZD + 0.24)) + P(0.05, a + 0.2, 0)
        cyl(R, f'log:{i}', 'soot', p0, p1, 0.06, 0.05, segs=7, e=0.01)
    hearth_light = Vector((hx, hy, ZD + 0.45))
    if V['tripod']:
        top = Vector((hx, hy, ZD + 1.75))
        for i in range(3):
            a = 2 * math.pi * i / 3 + 0.5
            cyl(R, f'tripod:{i}', 'timber', Vector((hx, hy, ZD)) + P(1.0, a, 0), top + P(0.05, a, 0.1), 0.035, 0.03, segs=6, e=0.006)
        cyl(R, 'chain', 'iron', top, Vector((hx, hy, ZD + 0.88)), 0.012, segs=5)
    # Furniture and furnishings are the shared set (props thread), placed by the page and recoloured for the fen there.
    # Only what belongs to the building is modelled here: hearth, tripod, loft and ladder, the peat fuel stack.
    furniture = []

    def put(name, pos, front):
        furniture.append(dict(name=name, pos=[round(float(v), 4) for v in pos], front=[round(float(front[0]), 4), round(float(front[1]), 4)]))

    def wall(name, adeg, depth, z=ZD, width=0.0):
        a = math.radians(adeg)
        sag = Rw - math.sqrt(max(0.0, Rw ** 2 - (width / 2) ** 2))
        r = Rw - 0.05 - depth / 2 - sag
        put(name, (r * math.cos(a), r * math.sin(a), z), (-math.cos(a), -math.sin(a)))
        return a, r

    if V['tripod']:
        put('cauldron', (hx, hy, ZD + 0.46), (0, -1))
    else:
        put('kettle', (hx + 0.26, hy - 0.08, ZD + 0.13), (-1, 0.3))
    if V['loft']:
        zl = ZD + 2.22
        y0 = 0.72
        yy = y0
        j = 0
        while yy < Rw:
            half = math.sqrt(max(0, Rw ** 2 - yy ** 2)) + 0.2
            beam(R, f'joist:{j}', 'wood', (-half, yy, zl - 0.09), (half, yy, zl - 0.09), 0.12, 0.16, e=0.015)
            yy += 0.62
            j += 1
        yy = y0 - 0.06
        k = 0
        xs = -Rw
        while xs < Rw:
            w = rng.uniform(0.2, 0.25)
            xc = xs + w / 2
            ymax = math.sqrt(max(0, (Rw - 0.03) ** 2 - xc ** 2))
            if ymax > y0 + 0.2:
                box(R, f'loftboard:{k}', 'wood', Matrix.Translation((xc, (y0 - 0.05 + ymax) / 2, zl + 0.02)), (w - 0.012, ymax - y0 + 0.05, 0.05), e=0.01, g=(0, 1, 0))
            xs += w
            k += 1
        # the ladder leans from the floor to the loft's front beam
        for sx in (-0.24, 0.24):
            beam(R, f'ladder_rail:{sx}', 'wood', (0.95 + sx, -0.15, ZD), (0.95 + sx, y0 - 0.05, zl + 0.75), 0.07, 0.05, e=0.01)
        n_r = 9
        for i in range(1, n_r):
            t = i / n_r
            yy = -0.15 + (y0 - 0.05 + 0.15) * t
            zz = ZD + (zl + 0.75 - ZD) * t
            cyl(R, f'rung:{i}', 'wood', (0.95 - 0.27, yy, zz), (0.95 + 0.27, yy, zz), 0.022, segs=6)
        put('bed', (0.0, Rw - 1.0, zl + 0.045), (1, 0))
        put('hanging_herbs', (-1.4, y0 + 0.62, zl - 0.17), (0, -1))
        put('hanging_herbs', (1.7, y0 + 1.24, zl - 0.17), (0.3, -1))
        put('hanging_herbs', (-0.4, y0 + 1.86, zl - 0.17), (-0.2, -1))
        # a low post rail along the loft edge
        for i, xx in enumerate((-2.2, -1.1, 0.35, 2.2)):
            yy = y0 + 0.04
            if abs(xx) > math.sqrt(max(0, Rw ** 2 - yy ** 2)) - 0.1:
                continue
            box(R, f'loft_post:{i}', 'wood', Matrix.Translation((xx, yy, zl + 0.45)), (0.08, 0.08, 0.86), e=0.01, g=(0, 0, 1))
        hx2 = math.sqrt(Rw ** 2 - (y0 + 0.04) ** 2) - 0.05
        beam(R, 'loft_rail_l', 'wood', (-hx2, y0 + 0.04, zl + 0.88), (0.5, y0 + 0.04, zl + 0.88), 0.07, 0.07, e=0.01)
        beam(R, 'loft_rail_r', 'wood', (1.45, y0 + 0.04, zl + 0.88), (hx2, y0 + 0.04, zl + 0.88), 0.07, 0.07, e=0.01)
    else:
        a = math.radians(92)
        # the bed's long side to the wall: the corners of a 2 m bed must clear the curve
        rb = math.sqrt((Rw - 0.07) ** 2 - 1.005 ** 2) - 0.475
        put('bed', (rb * math.cos(a), rb * math.sin(a), ZD), (-math.sin(a), math.cos(a)))
    wall('shelf', 205, 0.366, width=0.93)
    put('jug', P(Rw - 0.32, math.radians(205) + 0.12, ZD + 0.9), (0, 1))
    put('plate_stack', P(Rw - 0.32, math.radians(205) - 0.15, ZD + 1.3), (0, 1))
    # fuel: a neat stack of dry peats just inside the door, on the side the door does not swing to
    fa = door_a + math.radians(38)
    for row in range(3):
        for k in range(4 - row):
            for d in range(2):
                pc = P(Rw - 0.22 - d * 0.24, fa + (k - (3 - row) / 2) * 0.115, ZD + 0.08 + row * 0.15)
                M = Matrix.Translation(pc) @ Matrix.Rotation(fa + math.pi / 2 + rng.uniform(-0.08, 0.08), 4, 'Z')
                box(R, f'fuel:{row}:{k}:{d}', 'peat', M, (0.3, 0.2, 0.14), e=0.025)
    if V['table']:
        ta = math.radians(V['windows'][0][0])
        tc = P(Rw - 0.85, ta, ZD)
        inward = Vector((-math.cos(ta), -math.sin(ta), 0))
        tang = Vector((-math.sin(ta), math.cos(ta), 0))
        put('table', tc, inward)
        put('pewter_plate', tc + tang * 0.3 + inward * 0.12 + Vector((0, 0, 0.76)), inward)
        put('jug', tc - tang * 0.35 + Vector((0, 0, 0.76)), inward)
        for sx in (-0.35, 0.4):
            put('stool', tc + inward * 0.62 + tang * sx, inward)
    if V['chest']:
        wall('chest', 140, 0.524, width=0.84)
        wall('drawers', 230, 0.51, width=0.93)
        put('rug_round', P(2.15, math.radians(92), ZD + 0.002), (0, 1))
    elif V['table']:
        wall('cupboard', 238, 0.5, width=1.0)
    else:
        put('stool', P(1.35, math.radians(20), ZD), (-1, 0))
        wall('firewood_stack', 160, 0.5, width=0.6)
    # lantern post by the door, outside, so the threshold is lit at night
    lp = P(Ro + 0.55, door_a + 0.42, 0)
    cyl(R, 'lpost', 'timber', (lp.x, lp.y, ZD - 0.05), (lp.x, lp.y, ZD + 2.3), 0.065, 0.055, segs=8, e=0.01)
    arm = P(Ro + 0.55, door_a + 0.42, 0) + (P(1, door_a, 0) * 0.0) + Vector((0.42, 0, 0))
    beam(R, 'larm', 'timber', (lp.x, lp.y, ZD + 2.2), (lp.x + 0.45, lp.y - 0.05, ZD + 2.2), 0.06, 0.06, e=0.008)
    lc = Vector((lp.x + 0.4, lp.y - 0.05, ZD + 1.88))
    lathe(R, 'lantern_glass', 'glass', [(0.0001, -0.12), (0.08, -0.11), (0.1, 0.0), (0.08, 0.11), (0.0001, 0.12)], 10, M=Matrix.Translation(lc), close_top=False)
    for i in range(6):
        a = i * math.pi / 3
        cyl(R, f'lcage:{i}', 'wicker', lc + P(0.11, a, -0.15), lc + P(0.11, a, 0.15), 0.012, segs=4)
    lathe(R, 'lcap', 'wicker', [(0.15, 0.15), (0.05, 0.25), (0.0001, 0.26)], 10, M=Matrix.Translation(lc), close_top=False)
    lathe(R, 'lbase', 'wicker', [(0.0001, -0.18), (0.14, -0.16), (0.14, -0.13)], 10, M=Matrix.Translation(lc), close_top=False)
    cyl(R, 'lhang', 'rope', lc + Vector((0, 0, 0.25)), (lp.x + 0.4, lp.y - 0.05, ZD + 2.17), 0.01, segs=4)
    meta = dict(variant=variant, Rw=Rw, Ro=Ro, Rd=Rd, deck=ZD, wall=Hw, apex=zc + 0.5, door=[0, -Rd - 0.65, ZD - 0.06],
                hearth=[hx, hy, ZD + 0.4], lantern=list(lc), loft=(ZD + 2.22) if V['loft'] else None,
                windows=[[o['a'], o['z0'], o['z1']] for o in openings if o['kind'] == 'window'], furniture=furniture)
    meta['views'] = [((0.3, -Rw + 0.5, ZD + 1.6), (0.2, Rw, ZD + 1.0)), ((-0.6, Rw - 0.7, ZD + (3.0 if V['loft'] else 1.5)), (0.3, -Rw, ZD + 0.8))]
    return R, meta, hearth_light
