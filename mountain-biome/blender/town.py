"""Seeded mountain towns for Vanehold Pass: terraces cut into the slope, built the way an alpine town has to be.

The three questions, answered for this biome:
- Threat: cold, wind and the steepness itself. Steep slate roofs shed snow, low rooms round a fire keep the heat, every
  house backs into the hillside out of the wind, and stone walls hold the ground up.
- Resources: banded slate and stone everywhere, larch only for frames, iron for ties and fittings. Nothing else is
  used: the town is quarried from the hill it stands on.
- Food and water: terraced fields on the lower tiers, meltwater brought down from the snow in a flume on stone piers to
  a cistern at the head of the main stair.

What the generator builds, all from one seed (tiers, widths, house mix and every placement):
- tiers: 3 to 5 level terraces stepping up the slope, each a straight run of retaining wall (one or two storeys of the
  4.2 m kit wall, its foundation sunk below the lower ground, so nothing floats). The land is cut and filled to the
  tiers; past the town's ends it blends back into the hill.
- houses on every tier, backed against the next wall up and facing the valley; the communal hearth hall on the widest
  tier; the watchtower at the top end of the highest tier, overlooking the valley.
- stairs: solid flights along the wall faces, switching direction from tier to tier, so the main way up zigzags;
  a hoist on one wall for hauling loads between tiers.
- water: an aqueduct from a spring in the snow above the town, falling gently on stone piers to the cistern.
- industry: a quarry cut into the hill at one end of the town (the cut face shows the strata), with a crane and cut
  blocks; wood-chopping stations by the houses; fields on the lower tiers' open ends.
- streets: a flagged walk along the foot of every wall; stone stairs, never gravel.

Output: the edited heightfield, a zone override map (fields, streets, quarry), and layout entries for terrain.py.
"""
import math

import numpy as np

TIER = 4.2
RWALL = 4.0
ZF = {'field': 10, 'street': 11, 'quarry': 12}


def sm(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


class Town:
    def __init__(self, seed, ground_at):
        import zlib
        self.rng = np.random.default_rng(zlib.crc32(('town:' + seed).encode()))
        r = self.rng
        self.size = ['hamlet', 'village', 'town'][int(r.integers(3))]
        ntier = {'hamlet': 3, 'village': 4, 'town': 5}[self.size]
        self.wide = {'hamlet': 0.8, 'village': 1.0, 'town': 1.2}[self.size]
        # the site: on the foot of the northern range, where the slope begins
        self.cx = float(r.uniform(-48, 14))
        # walk up from the shelf to where the ground starts to climb
        y = 44.0
        while ground_at(self.cx, y) < 15.5 and y < 70:
            y += 0.5
        self.cy = y
        # the uphill direction: the ground's gradient there, rounded so the town faces the valley
        e = 3.0
        gx = ground_at(self.cx + e, self.cy + 6) - ground_at(self.cx - e, self.cy + 6)
        gy = ground_at(self.cx, self.cy + 6 + e) - ground_at(self.cx, self.cy + 6 - e)
        a = math.atan2(gy, gx)
        a = max(math.radians(65), min(math.radians(115), a)) + math.radians(r.uniform(-6, 6))
        self.vdir = np.array([math.cos(a), math.sin(a)])         # uphill
        self.udir = np.array([self.vdir[1], -self.vdir[0]])      # along the contour (east-ish)
        self.z0 = ground_at(self.cx, self.cy)
        # tiers: depth along the slope, rise (one or two wall storeys), half width along the contour
        self.tiers = []
        v = 0.0
        z = self.z0
        widest = int(r.integers(1, ntier - 1)) if ntier > 2 else 1
        for k in range(ntier):
            depth = 14.5 if k == widest else float(r.uniform(9.5, 12.0))
            half = (float(r.uniform(24, 31)) * (1.0 - 0.07 * k) + (5 if k == widest else 0)) * self.wide
            off = float(r.uniform(-4, 4))
            if k > 0:
                # the rise follows the hill: two storeys where the natural slope is steep
                p = self.at(off, v + depth * 0.5)
                nat = ground_at(*p)
                rise = TIER * (2 if nat - z > TIER * 1.6 else 1)
                z += rise
            else:
                rise = 0.0
            self.tiers.append({'k': k, 'v0': v, 'v1': v + depth, 'z': z, 'rise': rise, 'half': half, 'off': off,
                               'hall': k == widest})
            v += depth
        # the quarry at one end; the aqueduct comes down near the other
        self.quarry_side = float(r.choice([-1, 1]))
        narrow = min(t['off'] + t['half'] if self.quarry_side < 0 else -(t['off'] - t['half']) for t in self.tiers)
        self.aq_u = -self.quarry_side * (narrow - float(r.uniform(3.0, 5.0)))

    def at(self, u, v):
        p = np.array([self.cx, self.cy]) + self.udir * u + self.vdir * v
        return float(p[0]), float(p[1])

    def uv(self, X, Y):
        dx, dy = X - self.cx, Y - self.cy
        return dx * self.udir[0] + dy * self.udir[1], dx * self.vdir[0] + dy * self.vdir[1]

    def rot_facing_down(self):
        """House rotation so its door (local -y) faces downhill (-v)."""
        return math.atan2(self.vdir[1], self.vdir[0]) - math.pi / 2

    # ---------- the ground ----------
    def carve(self, X, Y, h):
        U, Vv = self.uv(X, Y)
        tgt = np.full(h.shape, np.nan)
        w = np.zeros(h.shape)
        zone = np.zeros(h.shape, np.uint8)
        for t in self.tiers:
            uc = U - t['off']
            inside = (Vv >= t['v0']) & (Vv < t['v1'] + (6.0 if t is self.tiers[-1] else 0.0))
            tgt = np.where(inside, t['z'], tgt)
            wk = sm(t['half'] + 7.0, t['half'], np.abs(uc))
            w = np.where(inside, wk, w)
            # the street: a flagged walk along the top of the wall below, in front of the houses
            street = inside & (Vv < t['v0'] + 2.3) & (np.abs(uc) < t['half'] - 0.5)
            zone[street] = ZF['street']
            # fields on the lower tiers' open ends
            if t['k'] == 0:
                fld = inside & (np.abs(uc) > t['half'] * 0.55) & (np.abs(uc) < t['half'] - 1.0) & (Vv < t['v1'] - 2.6) & (Vv > t['v0'] + 1.2)
                zone[fld] = ZF['field']
        # in front of the first tier the ground eases down to the shelf
        front = Vv < 0
        t0 = self.tiers[0]
        w = np.where(front, sm(-8, 0, Vv) * sm(t0['half'] + 7, t0['half'], np.abs(U - t0['off'])), w)
        tgt = np.where(front, t0['z'], tgt)
        # behind the top tier the hill comes back over 6 m
        top = self.tiers[-1]
        back = Vv >= top['v1']
        w = np.where(back, w * sm(top['v1'] + 6, top['v1'], Vv), w)
        # the quarry: a level bench cut into the hill beside the second tier, its face left raw
        q = self.tiers[min(1, len(self.tiers) - 1)]
        qu = self.quarry_side * (q['half'] + 9.0) + q['off']
        qd = np.maximum(np.abs(U - qu) - 6.0, 0)
        qin = (np.abs(U - qu) < 6.0) & (Vv > q['v0']) & (Vv < q['v1'] + 4)
        qw = sm(4.0, 0.0, qd) * (Vv > q['v0'] - 3) * sm(q['v1'] + 7, q['v1'] + 4, Vv)
        cut = qw > w
        tgt = np.where(cut, q['z'], tgt)
        w = np.where(cut, qw, w)
        zone[qin] = ZF['quarry']
        self.quarry = (qu, (q['v0'] + q['v1']) / 2 + 1.5, q['z'])
        tgt = np.where(np.isnan(tgt), h, tgt)
        h2 = h + (tgt - h) * w
        # only cut the hill down where a tier is lower than the ground, and fill where it is higher: both, so h2 stands
        return h2, zone

    # ---------- the layout ----------
    def layout(self, ground_at):
        r = self.rng
        L = {'houses': [], 'halls': [], 'props': [], 'town_stairs': [], 'smoke': [], 'tower': None}
        rot = self.rot_facing_down()
        ang = math.atan2(self.udir[1], self.udir[0])            # the direction of the contour, for wall pieces
        house_sizes = {'brannoch': (8.13, 6.4), 'tessaly': (7.76, 6.52), 'orrow': (7.71, 6.16)}   # footprints with the plinth
        variants = list(house_sizes)
        taken = []
        # retaining walls along the front of every tier above the first
        for t in self.tiers[1:]:
            n = int(math.ceil((2 * t['half']) / RWALL))
            for i in range(n):          # whole 4 m runs, overlapping a little where the length does not divide
                u = t['off'] - t['half'] + RWALL / 2 + i * (2 * t['half'] - RWALL) / max(1, n - 1)
                x, y = self.at(u, t['v0'])
                for s in range(int(round(t['rise'] / TIER))):
                    L['props'].append({'kind': 'rwall', 'x': x, 'y': y, 'z': t['z'] - t['rise'] + s * TIER,
                                       'rot': ang, 's': 1.0})
        # the main stair: solid flights along each wall face near alternate ends of the town, so the way up zigzags
        # across the whole slope from tier to tier
        side = -self.quarry_side
        for t in self.tiers[1:]:
            lo = self.tiers[t['k'] - 1]
            flights = int(round(t['rise'] / 1.4))
            run = flights * 2.52
            edge = min(lo['off'] + lo['half'], t['off'] + t['half']) if side > 0 else max(lo['off'] - lo['half'], t['off'] - t['half'])
            u0 = edge - side * (run + 3.0)          # the foot of the stair, climbing outward toward the edge
            for f in range(flights):
                x, y = self.at(u0 + side * f * 2.52, t['v0'] - 0.95)
                d = self.udir * side
                L['town_stairs'].append({'kind': 'wstair', 'x': x, 'y': y, 'z': t['z'] - t['rise'] + f * 1.4,
                                         'rot': math.atan2(d[1], d[0]) - math.pi / 2, 's': 1.0})
            mid = u0 + side * run / 2
            taken.append((t['k'] - 1, mid, run / 2 + 1.5))     # the flights stand on the lower tier's back strip
            taken.append((t['k'], u0 + side * run, 2.0))        # and arrive at the upper tier's street
            side = -side
        for t in self.tiers:
            taken.append((t['k'], self.aq_u, 2.5))
        # the hall on the widest tier, beside the stair head
        for t in self.tiers:
            if t['hall']:
                hu = t['off'] + float(r.uniform(-0.25, 0.25)) * t['half']
                hv = t['v1'] - 0.9 - 3.8
                x, y = self.at(hu, hv)
                L['halls'].append({'variant': 'moothall', 'x': x, 'y': y, 'z': t['z'], 'rot': rot})
                taken.append((t['k'], hu, 7.8))
        # the watchtower at the top tier's far end
        top = self.tiers[-1]
        tu = top['off'] + (top['half'] - 4.0) * (1 if self.quarry_side < 0 else -1)
        x, y = self.at(tu, (top['v0'] + top['v1']) / 2)
        L['tower'] = {'x': x, 'y': y, 'z': top['z'], 'rot': rot}
        taken.append((top['k'], tu, 5.0))
        # houses on every tier: backed against the next wall, doors to the valley
        for t in self.tiers:
            u = t['off'] - t['half'] + 1.5
            back = t['v1'] - 0.95
            while u < t['off'] + t['half'] - 1.5:
                var = variants[int(r.integers(len(variants)))]
                Lh, Wh = house_sizes[var]
                uc = u + Lh / 2
                if uc + Lh / 2 > t['off'] + t['half'] - 1.0:
                    break
                if t['k'] == 0 and abs(uc - t['off']) > t['half'] * 0.55:     # the fields
                    u += 3.0
                    continue
                if any(k == t['k'] and abs(uc - cu) < Lh / 2 + cr + 0.8 for k, cu, cr in taken):
                    u += 1.5
                    continue
                if t['v1'] - t['v0'] < Wh + 3.0:
                    break
                x, y = self.at(uc, back - Wh / 2)
                L['houses'].append({'variant': var, 'x': x, 'y': y, 'z': t['z'], 'rot': rot + float(r.uniform(-0.03, 0.03))})
                taken.append((t['k'], uc, Lh / 2))
                # a chopping station on the house's west side every other house
                if r.random() < 0.55:
                    cx, cy = self.at(uc - Lh / 2 - 1.2, back - Wh / 2 - 1.0)
                    L['props'].append({'kind': 'chop', 'x': cx, 'y': cy, 'z': t['z'], 'rot': float(r.uniform(0, 6.28)), 's': 1.0})
                u = uc + Lh / 2 + float(r.uniform(1.1, 2.6))
        # the hoist on one wall, away from the stair
        hk = self.tiers[int(r.integers(1, len(self.tiers)))]
        hu = hk['off'] + float(r.uniform(-0.7, 0.7)) * hk['half']
        x, y = self.at(hu, hk['v0'] - 0.1)
        L['props'].append({'kind': 'hoist', 'x': x, 'y': y, 'z': hk['z'] - hk['rise'], 'rot': ang, 's': 1.0})
        # the aqueduct: from a spring in the snow above the town down to the cistern on the hall's tier
        ct = next(t for t in self.tiers if t['hall'])
        cv = ct['v0'] + 2.4
        cx, cy = self.at(self.aq_u, cv)
        L['props'].append({'kind': 'cistern', 'x': cx, 'y': cy, 'z': ct['z'], 'rot': ang, 's': 1.0})
        sv = top['v1'] + 26.0
        sx, sy = self.at(self.aq_u, sv)
        zs = ground_at(sx, sy) + 0.5
        zc = ct['z'] + 1.35
        n = int((sv - cv - 1.6) / 4.0)
        for i in range(n):
            vv = cv + 1.6 + 2.0 + i * 4.0
            fz = zc + (zs - zc) * (vv - cv) / (sv - cv)
            x, y = self.at(self.aq_u, vv)
            g = ground_at(x, y)
            fz = max(fz, g + 0.6)
            L['props'].append({'kind': 'aqueduct', 'x': x, 'y': y, 'z': fz - 0.45,
                               'rot': math.atan2(self.vdir[1], self.vdir[0]), 's': 1.0})
        # the quarry: a crane at the cut face and blocks on the floor
        qu, qv, qz = self.quarry
        x, y = self.at(qu, qv + 2.5)
        L['props'].append({'kind': 'crane', 'x': x, 'y': y, 'z': qz, 'rot': math.atan2(-self.vdir[1], -self.vdir[0]), 's': 1.0})
        for k in range(int(r.integers(2, 4))):
            x, y = self.at(qu + float(r.uniform(-4, 4)), qv - float(r.uniform(1, 4)))
            L['props'].append({'kind': 'blocks', 'x': x, 'y': y, 'z': qz, 'rot': float(r.uniform(0, 6.28)), 's': 1.0})
        # where the town is, for pines and boulders to keep clear of
        lo = self.tiers[0]
        L['town'] = {'cx': self.cx, 'cy': self.cy, 'u': list(self.udir), 'v': list(self.vdir), 'size': self.size,
                     'tiers': [{k: t[k] for k in ('v0', 'v1', 'z', 'rise', 'half', 'off')} for t in self.tiers],
                     'base': list(self.at(lo['off'], -4.0)), 'quarry': list(self.quarry)}
        return L

    def covers(self, x, y, pad=4.0):
        U, Vv = self.uv(np.array(x), np.array(y))
        U, Vv = float(U), float(Vv)
        for t in self.tiers:
            if t['v0'] - pad <= Vv < t['v1'] + pad and abs(U - t['off']) < t['half'] + pad + 7:
                return True
        qu, qv, _ = self.quarry
        return abs(U - qu) < 10 + pad and abs(Vv - qv) < 10 + pad or Vv < 0 and Vv > -10 and abs(U) < 30
