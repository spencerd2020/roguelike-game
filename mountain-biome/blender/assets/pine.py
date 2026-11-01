"""Cloud pine: a tall high-country conifer with a bare, leaning trunk and its needles held in flat, layered pads, like
clouds stacked on a stick. The pads are faceted, dark beneath and fresh on top. Seeded: lean, height, tiers, pads."""
import math

from mathutils import Vector

from mkit import Kit, V, stream

SLOTS = ['bark', 'needle', 'stone']


def build(seed):
    K = Kit(SLOTS)
    r = stream(seed, 'tree')
    Ht = r.uniform(8.5, 12.5)
    lean = V(r.uniform(-0.12, 0.12), r.uniform(-0.12, 0.12), 1).normalized()
    bend = V(r.uniform(-0.6, 0.6), r.uniform(-0.6, 0.6), 0)
    n = 12

    def trunk_at(k):
        return lean * (Ht * k) + bend * (math.sin(k * math.pi * 0.9) * 0.8)
    pts = [trunk_at(i / n) + V(0, 0, -0.25 if i == 0 else 0) for i in range(n + 1)]
    rb = r.uniform(0.26, 0.34)
    K.tube(pts, [rb * (1.25 if i == 0 else 1.0) * (1 - 0.82 * (i / n) ** 0.9) + 0.02 for i in range(n + 1)], 'bark', 'trunk', 9)
    # root flare
    for i in range(5):
        a = 2 * math.pi * i / 5 + r.uniform(-0.3, 0.3)
        d = V(math.cos(a), math.sin(a), 0)
        K.tube([d * 0.1 + V(0, 0, 0.45), d * 0.55 + V(0, 0, 0.12), d * 1.0 + V(0, 0, -0.08)], [0.16, 0.11, 0.05], 'bark', 'root', 6)
    # tiers of branches, each ending in a flat pad of needles
    tiers = r.randint(4, 6)
    z0 = r.uniform(0.38, 0.48)
    for ti in range(tiers):
        k = z0 + (0.93 - z0) * ti / (tiers - 1)
        base = trunk_at(k)
        nb = r.randint(2, 4) if ti < tiers - 1 else 1
        reach = (1 - k) * r.uniform(3.6, 4.6) + 0.6
        for bi in range(nb):
            a = r.uniform(0, 2 * math.pi) if bi == 0 else a + 2 * math.pi / nb + r.uniform(-0.5, 0.5)
            d = V(math.cos(a), math.sin(a), 0)
            if ti == tiers - 1:
                tip = base + V(0, 0, 0.5)
            else:
                tip = base + d * reach + V(0, 0, r.uniform(0.2, 0.9))
                mid = base + d * reach * 0.5 + V(0, 0, r.uniform(0.3, 0.6))
                K.tube([base, mid, tip], [0.11 * (1 - k) + 0.05, 0.07, 0.04], 'bark', 'branch', 6)
            pr = (reach * 0.62 + 0.6) if ti < tiers - 1 else r.uniform(1.0, 1.4)
            # the pad: a big flat cloud plus two or three smaller lobes
            K.rock(tip + V(0, 0, 0.22), pr, r, 'needle', 'pad', 2, (1.0, 1.0, 0.3), 0.22)
            for li in range(r.randint(2, 3)):
                aa = r.uniform(0, 2 * math.pi)
                off = V(math.cos(aa), math.sin(aa), 0) * pr * r.uniform(0.45, 0.75)
                K.rock(tip + off + V(0, 0, r.uniform(0.15, 0.45)), pr * r.uniform(0.45, 0.65), r, 'needle', 'lobe', 2,
                       (1.0, 1.0, 0.36), 0.2)
    # a few stones round the foot
    for i in range(r.randint(2, 4)):
        a = r.uniform(0, 2 * math.pi)
        K.rock(V(math.cos(a), math.sin(a), 0) * r.uniform(0.9, 1.6) + V(0, 0, 0.05), r.uniform(0.18, 0.35), r, 'stone', 'footstone', 1,
               (1, 1, 0.6), 0.3)
    ctx = {'ao_dist': 2.0, 'footprint': [3, 3]}
    return f'pine_{seed}', K, ctx
