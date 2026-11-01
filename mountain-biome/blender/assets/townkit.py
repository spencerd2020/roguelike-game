"""Vanehold town kit: the pieces a seeded mountain town is put together from, one bake, each its own node with its pivot
at its foot (the generator in town.py places them). Spaced 9 m apart while baking so they do not shade each other.

- rwall: a 4 m run of terrace retaining wall, 4.2 m high (one tier), banded coursed stone with a slight batter, a coping
  kerb, a stepped stone buttress and iron tie plates. Its foundation runs 1.2 m below the lower ground, so a wall on
  uneven ground never floats (local x along the wall, the face looks down -y, the terrace top is at z = TIER behind it).
- aqueduct: one 4 m span of the meltwater channel, a timber flume with water on a coursed pier 10 m tall; the pier is
  sunk as deep as it needs (pivot at the top of the pier cap).
- cistern: the stone tank the aqueduct fills, at the head of the main stair.
- crane: the quarry crane: a braced mast, a jib, a pulley, a windlass and a cut block in a rope sling.
- hoist: the tier lift: two posts and a head beam with a pulley wheel standing on the upper terrace's edge, the rope down
  to a plank platform and a counterweight of stones (pivot at the foot of the wall it serves, x along the wall).
- chop: a wood-chopping station: a stump with the axe in it, split billets, chips and a log pile.
- wstair: one solid stair flight (7 treads, up 1.4 m along +y) with masonry under it, for stairs that run along a wall.
- blocks: cut stone from the quarry stacked on timber skids.
"""
import math

from mathutils import Matrix, Vector

from mkit import Kit, V, stream

SLOTS = ['stone', 'rock', 'wood', 'plank', 'rope', 'iron', 'water']
TIER = 4.2
FOUND = 1.2


def build(seed):
    K = Kit(SLOTS)
    ctx = {'ao_dist': 1.6, 'pivots': {}, 'strat': {}}
    spot = [0]

    def place(name):
        x = (spot[0] % 4) * 9.0
        y = (spot[0] // 4) * 12.0
        spot[0] += 1
        if spot[0] > 1:
            K.use_node(name)
        ctx['pivots'][name] = (x, y, 0.0)
        return V(x, y, 0)

    r = stream(seed, 'townkit')

    def strat(k):
        ctx['strat'][len(K.parts) - 1] = k

    # ---------- the retaining wall: 4 m, one tier high, battered face, coping, a buttress, tie plates ----------
    o = place('townkit')
    z = -FOUND
    ci = 0
    while z < TIER - 0.05:
        h = min(r.uniform(0.26, 0.38), TIER - z)
        band = (int((z + FOUND) / 1.1) + ci // 3) % 3
        batter = 0.06 * (TIER - z) / (TIER + FOUND)     # the face leans back into the hill
        x = -2.0 - (r.uniform(0, 0.4) if ci % 2 else 0.0)
        while x < 2.0 - 1e-6:
            l = r.uniform(0.55, 1.2)
            xa, xb = max(x, -2.0), min(x + l, 2.0)
            if xb - xa > 0.12:
                d = r.uniform(0.0, 0.025)
                K.box(o + V((xa + xb) / 2, 0.35 - batter * 3 + d, z + h / 2), (xb - xa - 0.014, 0.7, h - 0.014),
                      Matrix.Rotation(r.uniform(-0.01, 0.01), 3, 'Z'), 'stone', 'course', 0.03, axis=(1, 0, 0))
                strat(band if r.random() > 0.08 else r.randrange(3))
            x += l
        z += h
        ci += 1
    x = -2.0
    while x < 2.0 - 1e-6:            # coping slabs, a little proud, a kerb at the terrace edge
        l = min(r.uniform(0.6, 1.1), 2.0 - x)
        K.box(o + V(x + l / 2, 0.36, TIER + 0.09), (l - 0.012, 0.84, 0.18), None, 'stone', 'coping', 0.03, axis=(1, 0, 0))
        strat(2)
        x += l
    for k, (w, dep, z0, z1) in enumerate(((0.75, 0.75, -FOUND, 1.4), (0.62, 0.52, 1.4, 2.8), (0.5, 0.3, 2.8, TIER - 0.2))):
        zz = z0
        while zz < z1 - 1e-6:            # the buttress: three stepped stages of the same coursing
            h = min(r.uniform(0.28, 0.36), z1 - zz)
            K.box(o + V(0, -dep / 2 + 0.02, zz + h / 2), (w, dep, h - 0.012), None, 'stone', 'buttress', 0.03, axis=(0, 0, 1))
            strat(k % 3)
            zz += h
        K.box(o + V(0, -dep / 2 + 0.02, z1 + 0.05), (w + 0.06, dep + 0.06, 0.1), Matrix.Rotation(-0.25, 3, 'X'), 'stone',
              'weathering', 0.02)
        strat(2)
    for sx in (-1.25, 1.25):             # iron tie plates where the rods through the wall are anchored
        p = o + V(sx, -0.02 - 0.03, 2.0)
        K.box(p, (0.42, 0.04, 0.08), None, 'iron', 'tieplate', 0.006)
        K.box(p, (0.08, 0.04, 0.42), None, 'iron', 'tieplate', 0.006)
        K.prism(p + V(0, -0.02, 0), V(0, -1, 0), 0.06, 0.04, 0.03, 'iron', 'tienut', 6)

    # ---------- the aqueduct span: a pier and a flume with water ----------
    o = place('aqueduct')
    PIER = 10.0
    z = -PIER
    pi_ = 0
    while z < -0.35:
        h = min(r.uniform(0.3, 0.42), -0.35 - z)
        w = 0.8 + 0.25 * max(0.0, (-z - 6.0) / 4.0)
        K.box(o + V(0, 0, z + h / 2), (w, w, h - 0.012), Matrix.Rotation(r.uniform(-0.02, 0.02), 3, 'Z'), 'stone', 'pier', 0.03)
        strat((pi_ // 3) % 3)
        z += h
        pi_ += 1
    K.box(o + V(0, 0, -0.2), (1.15, 1.0, 0.3), None, 'stone', 'piercap', 0.03)
    strat(2)
    for s in (-1, 1):                     # struts from the pier to the flume
        K.beam(o + V(s * 0.35, 0, -0.5), o + V(s * 1.4, 0, 0.0), 0.1, 0.1, 'wood', 'strut', 0.01)
    K.box(o + V(0, 0, 0.05), (4.0, 0.62, 0.08), None, 'plank', 'flumebed', 0.008, axis=(1, 0, 0))
    for s in (-1, 1):
        K.box(o + V(0, s * 0.28, 0.24), (4.0, 0.06, 0.32), None, 'plank', 'flumeside', 0.008, axis=(1, 0, 0))
    for x in (-1.6, -0.5, 0.5, 1.6):
        K.box(o + V(x, 0, 0.42), (0.08, 0.68, 0.06), None, 'wood', 'flumetie', 0.008)
        for s in (-1, 1):
            K.box(o + V(x, s * 0.33, 0.22), (0.08, 0.05, 0.38), None, 'wood', 'flumepost', 0.006)
    K.box(o + V(0, 0, 0.21), (3.98, 0.48, 0.02), None, 'water', 'flow', 0.0, axis=(1, 0, 0))

    # ---------- the cistern ----------
    o = place('cistern')
    cl, cw, ch = 2.8, 1.9, 1.0
    for s in (-1, 1):
        K.box(o + V(0, s * (cw / 2 - 0.13), ch / 2), (cl, 0.26, ch), None, 'stone', 'tankside', 0.03, axis=(1, 0, 0))
        strat(0 if s < 0 else 1)
        K.box(o + V(s * (cl / 2 - 0.13), 0, ch / 2), (0.26, cw - 0.5, ch), None, 'stone', 'tankend', 0.03, axis=(0, 1, 0))
        strat(2)
    K.box(o + V(0, 0, 0.1), (cl - 0.5, cw - 0.5, 0.2), None, 'stone', 'tankbed', 0.02)
    K.box(o + V(0, 0, ch - 0.18), (cl - 0.52, cw - 0.52, 0.02), None, 'water', 'pool', 0.0)
    K.box(o + V(-cl / 2 - 0.25, 0, ch + 0.3), (0.5, 0.6, ch + 0.6 + 0.3), None, 'stone', 'spoutpost', 0.03)
    strat(1)
    K.beam(o + V(-cl / 2 - 0.1, 0, ch + 0.45), o + V(-cl / 2 + 0.4, 0, ch + 0.3), 0.12, 0.1, 'wood', 'spout', 0.01)

    # ---------- the quarry crane ----------
    o = place('crane')
    K.rock(o + V(0, 0, 0.2), 0.7, r, 'rock', 'cranefoot', 1, (1.2, 1.2, 0.45), 0.2)
    K.prism(o, V(0, 0, 1), 6.2, 0.16, 0.13, 'wood', 'mast', 8)
    for a in (0.0, 2.1, 4.2):
        d = V(math.cos(a), math.sin(a), 0)
        K.beam(o + d * 1.8, o + V(0, 0, 3.6), 0.11, 0.11, 'wood', 'brace', 0.012)
        K.rock(o + d * 1.8 + V(0, 0, 0.1), 0.25, r, 'rock', 'bracefoot', 1, (1, 1, 0.6), 0.25)
    jt = o + V(0, 0, 5.4)
    je = o + V(4.2, 0, 6.6)
    K.beam(jt + V(-0.6, 0, -0.2), je, 0.14, 0.12, 'wood', 'jib', 0.012)
    K.beam(o + V(0, 0, 6.2), je + V(-0.3, 0, 0), 0.06, 0.06, 'wood', 'stay', 0.008)
    K.prism(je + V(0, -0.1, -0.15), V(0, 1, 0), 0.2, 0.22, 0.22, 'wood', 'pulley', 10)
    blk = je + V(0, 0, -4.4)
    K.tube([je + V(0, 0, -0.35), blk + V(0, 0, 0.55)], 0.022, 'rope', 'hoistrope', 5)
    K.tube([je + V(-0.1, 0, -0.1), jt + V(0.2, 0, -0.3), o + V(0.45, 0, 1.0)], 0.02, 'rope', 'haul', 5)
    K.box(blk, (0.9, 0.6, 0.55), Matrix.Rotation(0.1, 3, 'Z'), 'stone', 'cutblock', 0.02)
    strat(1)
    for s in (-1, 1):
        K.tube([blk + V(s * 0.3, -0.31, -0.28), blk + V(s * 0.3, -0.31, 0.28), blk + V(0, 0, 0.55),
                blk + V(s * 0.3, 0.31, 0.28), blk + V(s * 0.3, 0.31, -0.28)], 0.018, 'rope', 'sling', 4)
    w0 = o + V(0.6, 0, 0.0)              # the windlass
    for s in (-1, 1):
        K.box(w0 + V(0.3, s * 0.45, 0.45), (0.12, 0.12, 0.9), None, 'wood', 'windpost', 0.01)
    K.prism(w0 + V(0.3, -0.5, 0.85), V(0, 1, 0), 1.0, 0.16, 0.16, 'wood', 'drum', 10)
    K.beam(w0 + V(0.3, 0.55, 0.85), w0 + V(0.3, 0.7, 0.85), 0.04, 0.04, 'iron', 'axle', 0.004)
    K.beam(w0 + V(0.3, 0.7, 0.85), w0 + V(0.3, 0.7, 0.45), 0.05, 0.05, 'iron', 'crank', 0.004)

    # ---------- the tier hoist ----------
    o = place('hoist')
    for s in (-1, 1):
        K.prism(o + V(s * 0.85, 0.5, -0.5), V(0, 0, 1), TIER + 2.6, 0.13, 0.11, 'wood', 'hpost', 8)
        K.beam(o + V(s * 0.85, 0.5, TIER + 0.5), o + V(s * 0.85, 1.6, TIER), 0.08, 0.08, 'wood', 'hbrace', 0.01)
    K.beam(o + V(-1.05, 0.5, TIER + 2.0), o + V(1.05, 0.5, TIER + 2.0), 0.2, 0.18, 'wood', 'headbeam', 0.015, roll=math.pi / 2)
    wheel = o + V(0.0, 0.0, TIER + 1.75)
    K.prism(wheel + V(0, -0.06, 0), V(0, 1, 0), 0.12, 0.42, 0.42, 'wood', 'hwheel', 12)
    K.beam(o + V(0, 0.5, TIER + 2.0), wheel + V(0, 0, 0.3), 0.06, 0.06, 'iron', 'hanger', 0.004)
    plat = o + V(-0.42, -0.85, 0.35)
    K.box(plat, (1.2, 1.1, 0.08), None, 'plank', 'platform', 0.008, axis=(1, 0, 0))
    for sx in (-1, 1):
        for sy in (-1, 1):
            K.tube([plat + V(sx * 0.55, sy * 0.5, 0.04), wheel + V(-0.42, -0.4, -1.2)], 0.012, 'rope', 'bridle', 4)
    K.tube([wheel + V(-0.42, -0.4, -1.2), wheel + V(-0.42, 0, 0)], 0.02, 'rope', 'liftrope', 5)
    cw_ = o + V(0.42, -0.4, TIER - 0.4)
    K.tube([wheel + V(0.42, 0, 0), cw_ + V(0, 0, 0.35)], 0.02, 'rope', 'cwrope', 5)
    K.box(cw_, (0.5, 0.4, 0.6), None, 'stone', 'counterweight', 0.03)
    strat(0)
    K.box(plat + V(0.2, 0.1, 0.25), (0.5, 0.4, 0.4), Matrix.Rotation(0.2, 3, 'Z'), 'plank', 'liftcrate', 0.01, axis=(1, 0, 0))

    # ---------- the wood-chopping station ----------
    o = place('chop')
    K.prism(o, V(0, 0, 1), 0.5, 0.36, 0.33, 'wood', 'stump', 11)
    K.beam(o + V(0.05, 0.02, 0.48), o + V(0.35, 0.3, 0.98), 0.04, 0.03, 'wood', 'axehandle', 0.006)
    K.box(o + V(0.03, 0.0, 0.48), (0.2, 0.025, 0.12), Matrix.Rotation(0.78, 3, 'Z'), 'iron', 'axehead', 0.004)
    for i in range(7):
        a = r.uniform(0, 6.28)
        p = o + V(math.cos(a), math.sin(a), 0) * r.uniform(0.6, 1.2)
        K.prism(p + V(0, 0, 0.07), V(math.cos(a + 1.3), math.sin(a + 1.3), 0.05), 0.42, 0.07, 0.07, 'wood', 'billet', 4,
                spin=r.uniform(0, 1))
    for i in range(10):
        a = r.uniform(0, 6.28)
        p = o + V(math.cos(a), math.sin(a), 0) * r.uniform(0.3, 0.9)
        K.box(p + V(0, 0, 0.01), (r.uniform(0.06, 0.12), 0.04, 0.02), Matrix.Rotation(a, 3, 'Z'), 'plank', 'chip', 0.0)
    for row in range(4):
        for i in range(6 - (row % 2)):
            y = 1.6 + i * 0.3 + (0.15 if row % 2 else 0)
            rr = r.uniform(0.11, 0.14)
            K.prism(o + V(-0.8, y, 0.12 + row * 0.23), V(1, r.uniform(-0.04, 0.04), 0), 1.6, rr, rr, 'wood', 'log', 7, spin=r.uniform(0, 1))
    for s in (-1, 1):
        K.box(o + V(-0.8 + s * 0.85, 2.3, 0.5), (0.1, 0.1, 1.0), None, 'wood', 'logstake', 0.01)

    # ---------- a wall stair: one solid flight of 7 treads up 1.4 m, built against a terrace wall ----------
    o = place('wstair')
    for i in range(7):
        top = i * 0.2 + 0.2
        K.box(o + V(0, i * 0.36 + 0.18, top - 0.1), (1.5 + r.uniform(-0.04, 0.04), 0.42, 0.2), None, 'stone', 'tread', 0.025)
        strat(2 if i % 3 else 1)
        zz = -FOUND
        while zz < top - 0.2 - 1e-6:          # the solid riser block under each tread
            h = min(r.uniform(0.3, 0.42), top - 0.2 - zz)
            K.box(o + V(0, i * 0.36 + 0.18, zz + h / 2), (1.42, 0.36, h - 0.01), None, 'stone', 'stairfill', 0.02)
            strat(((i + int(zz * 3)) // 2) % 3)
            zz += h
    K.box(o + V(-0.82, 1.26, 0.85), (0.16, 2.52, 0.12), Matrix.Rotation(-math.atan2(1.4, 2.52), 3, 'X'), 'stone', 'parapet', 0.02)

    # ---------- cut blocks on skids ----------
    o = place('blocks')
    for s in (-1, 1):
        K.box(o + V(0, s * 0.55, 0.06), (2.6, 0.16, 0.12), None, 'wood', 'skid', 0.01, axis=(1, 0, 0))
    for i, (x, y, z, sx, sy, sz) in enumerate(((-0.75, 0, 0.12, 1.1, 1.3, 0.6), (0.5, 0, 0.12, 1.2, 1.25, 0.65),
                                                 (-0.2, 0.05, 0.75, 1.0, 1.1, 0.5))):
        K.box(o + V(x, y, z + sz / 2), (sx, sy, sz), Matrix.Rotation(r.uniform(-0.06, 0.06), 3, 'Z'), 'stone', 'cut', 0.02)
        strat(i % 3)
    for i in range(6):
        a = r.uniform(0, 6.28)
        K.rock(o + V(math.cos(a), math.sin(a), 0) * r.uniform(1.6, 2.2) + V(0, 0, 0.1), r.uniform(0.15, 0.3), r, 'rock',
               'spall', 1, (1.3, 1.0, 0.5), 0.3)
    ctx['footprint'] = None
    return 'townkit', K, ctx
