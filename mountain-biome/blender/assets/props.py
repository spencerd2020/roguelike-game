"""Vanehold field kit, one bake for many small things. Each prop is its own exported node, its pivot at its foot:
banded boulders (four shapes), a waymark cairn, a quartz cluster, a wind post with a streamer, a drystone wall run,
a stone stair flight, a spring trough, and the rope bridge across the gorge.
Props stand 7 m apart while baking so they do not shade each other."""
import math

from mathutils import Matrix, Vector

import vane
from mkit import Kit, V, frame, stream

SLOTS = ['rock', 'stone', 'wood', 'plank', 'rope', 'quartz', 'iron', 'sail', 'pennant']
BRIDGE_SPAN = 18.0


def build(seed):
    K = Kit(SLOTS)
    ctx = {'ao_dist': 1.5, 'pivots': {}, 'strat': {}}
    spot = [0]

    def place(name):
        x = (spot[0] % 5) * 7.0
        y = (spot[0] // 5) * 7.0
        spot[0] += 1
        if spot[0] > 1:
            K.use_node(name)
        ctx['pivots'][name] = (x, y, 0.0)
        return V(x, y, 0)

    r = stream(seed, 'props')
    # boulders: faceted, banded by the mountain's own strata (painted by height)
    for i, (rad, sq) in enumerate(((1.6, (1.2, 0.9, 0.7)), (1.0, (1.0, 1.1, 0.85)), (2.4, (1.3, 1.0, 0.55)), (0.7, (1, 1, 0.8)))):
        o = place(f'boulder{i}')
        K.rock(o + V(0, 0, rad * sq[2] * 0.55), rad, r, 'rock', f'boulder{i}', 2, sq, 0.3)
        if i == 2:   # a split block beside the big one
            K.rock(o + V(rad * 1.2, 0.3, 0.35), 0.6, r, 'rock', 'chip', 1, (1.2, 0.8, 0.7), 0.25)
    # waymark cairn: flat slabs stacked, the top one stood on end
    o = place('cairn')
    z = 0.0
    for i in range(9):
        rr = 0.62 * (1 - i / 11) + r.uniform(-0.05, 0.05)
        h = r.uniform(0.12, 0.2)
        sides = r.randint(5, 7)
        a0 = r.uniform(0, 6.28)
        off = V(r.uniform(-0.04, 0.04), r.uniform(-0.04, 0.04), 0)
        pts = [o + off + V(math.cos(a0 + 2 * math.pi * k / sides) * rr * r.uniform(0.85, 1.1),
                           math.sin(a0 + 2 * math.pi * k / sides) * rr * r.uniform(0.85, 1.1), z) for k in range(sides)]
        K.slab(pts, h, 'stone', 'cairnstone', 0.02)
        ctx['strat'][len(K.parts) - 1] = (i + r.randrange(2)) % 3
        z += h
    K.box(o + V(0, 0, z + 0.32), (0.32, 0.12, 0.64), Matrix.Rotation(r.uniform(-0.1, 0.1), 3, 'Y'), 'stone', 'cairntop', 0.02)
    ctx['strat'][len(K.parts) - 1] = 2
    # quartz cluster: hexagonal points from a cracked rock
    o = place('quartz')
    K.rock(o + V(0, 0, 0.2), 0.75, r, 'rock', 'qbase', 1, (1.2, 1.0, 0.5), 0.3)
    for i in range(11):
        a = r.uniform(0, 2 * math.pi)
        tilt = r.uniform(0.0, 0.7)
        d = V(math.cos(a) * math.sin(tilt), math.sin(a) * math.sin(tilt), math.cos(tilt))
        ln = r.uniform(0.5, 1.5) * (1.2 - tilt * 0.5)
        rad = r.uniform(0.08, 0.17)
        b = o + V(math.cos(a), math.sin(a), 0) * r.uniform(0, 0.35) + V(0, 0, 0.3)
        K.prism(b, d, ln * 0.8, rad, rad, 'quartz', 'qshaft', 6, spin=r.uniform(0, 1))
        K.prism(b + d * ln * 0.8, d, ln * 0.25, rad, 0.0, 'quartz', 'qtip', 6, spin=r.uniform(0, 1))
    # wind post: a tall pole with three cloth streamers (the streamers are their own node so they can flutter)
    o = place('windpost')
    K.rock(o + V(0, 0, 0.15), 0.45, r, 'rock', 'postfoot', 1, (1, 1, 0.5), 0.25)
    K.prism(o, V(0, 0, 1), 5.2, 0.09, 0.06, 'wood', 'pole', 7)
    K.beam(o + V(-0.6, 0, 4.7), o + V(0.6, 0, 4.7), 0.07, 0.07, 'wood', 'crossbar', 0.01)
    K.use_node('streamers')
    for i, x in enumerate((-0.55, 0.0, 0.55)):
        K.box(o + V(x, -0.75, 4.55), (0.2, 1.5, 0.01), None, 'pennant', 'streamer', 0.0, axis=(0, 1, 0))
    K.use_node('windpost')
    ctx['pivots']['streamers'] = tuple(o + V(0, 0, 4.7))
    # drystone wall run: 4 m, two faces of flat stones with through-stones and a cope of stones on edge
    o = place('drywall')
    z = 0.0
    for ci in range(6):
        h = r.uniform(0.13, 0.2)
        w = 0.7 - ci * 0.05
        x = -2.0 + (r.uniform(0, 0.25) if ci % 2 else 0)
        while x < 2.0 - 0.05:
            l = min(r.uniform(0.25, 0.5), 2.0 - x)
            K.box(o + V(x + l / 2, 0, z + h / 2), (l - 0.01, w, h), Matrix.Rotation(r.uniform(-0.04, 0.04), 3, 'Z'), 'stone', 'drystone',
                  0.025)
            ctx['strat'][len(K.parts) - 1] = r.choice((0, 0, 1, 2))
            x += l
        z += h
    x = -2.0
    while x < 1.95:
        l = r.uniform(0.09, 0.14)
        K.box(o + V(x + l / 2, 0, z + 0.17), (l - 0.01, 0.42, 0.34), Matrix.Rotation(r.uniform(-0.15, 0.15), 3, 'Y'), 'stone', 'cope', 0.02)
        ctx['strat'][len(K.parts) - 1] = 0
        x += l
    # stair flight: 7 big treads up 1.4 m, with cheek stones
    o = place('stairs')
    for i in range(7):
        K.box(o + V(0, i * 0.36 + 0.18, i * 0.2 + 0.1), (1.6 + r.uniform(-0.1, 0.1), 0.42, 0.2), None, 'stone', 'tread', 0.025)
        ctx['strat'][len(K.parts) - 1] = 2 if i % 3 else 1
        for s in (-1, 1):
            K.box(o + V(s * 1.0, i * 0.36 + 0.18, i * 0.2 + 0.2), (0.35, 0.36, 0.4), None, 'stone', 'cheek', 0.03)
            ctx['strat'][len(K.parts) - 1] = 0
    # spring trough: a hollowed stone basin fed by a wooden spout
    o = place('trough')
    for s in (-1, 1):
        K.box(o + V(0, s * 0.33, 0.35), (1.8, 0.14, 0.7), None, 'stone', 'troughside', 0.025)
        K.box(o + V(s * 0.83, 0, 0.35), (0.14, 0.52, 0.7), None, 'stone', 'troughend', 0.025)
    K.box(o + V(0, 0, 0.1), (1.52, 0.52, 0.2), None, 'stone', 'troughbed', 0.02)
    K.box(o + V(-1.1, 0, 0.6), (0.3, 0.5, 1.2), None, 'stone', 'spoutstone', 0.03)
    K.beam(o + V(-1.0, 0, 1.0), o + V(-0.55, 0, 0.88), 0.1, 0.08, 'wood', 'spout', 0.01)
    # the rope bridge: plank deck on two ropes, hand ropes, posts at each end
    o = place('bridge')
    span = BRIDGE_SPAN
    sag = 0.9
    n = 60

    def deck(k):
        return o + V(0, -span / 2 + span * k, -sag * 4 * k * (1 - k))
    for s in (-1, 1):
        for end in (0, 1):
            pz = o + V(s * 0.75, -span / 2 + span * end + (-0.4 if end == 0 else 0.4), 0)
            K.prism(pz - V(0, 0, 0.6), V(0, 0, 1), 2.0, 0.12, 0.1, 'wood', 'bpost', 8)
            K.prism(pz + V(0, 0, 1.38), V(0, 0, 1), 0.08, 0.13, 0.13, 'iron', 'postcap', 8)
        K.tube([deck(i / 20) + V(s * 0.55, 0, -0.06) for i in range(21)], 0.03, 'rope', 'footrope', 5)
        K.tube([deck(i / 20) + V(s * 0.75, 0, 1.0 + sag * 0.55 * 4 * (i / 20) * (1 - i / 20)) for i in range(21)], 0.03, 'rope', 'handrope', 5)
        for i in range(1, 20):
            p = deck(i / 20)
            K.tube([p + V(s * 0.55, 0, -0.04), p + V(s * 0.75, 0, 1.0 + sag * 0.55 * 4 * (i / 20) * (1 - i / 20))], 0.012, 'rope', 'hanger', 4)
    for i in range(n):
        k = (i + 0.5) / n
        p = deck(k)
        d = deck(min(1, k + 0.01)) - deck(max(0, k - 0.01))
        ang = math.atan2(d.z, d.y)
        K.box(p, (1.2 + r.uniform(-0.06, 0.06), span / n - 0.045, 0.05), Matrix.Rotation(ang, 3, 'X') @ Matrix.Rotation(r.uniform(-0.03, 0.03), 3, 'Z'),
              'plank', 'bplank', 0.006, axis=(1, 0, 0))
    ctx['footprint'] = None
    return 'props', K, ctx
