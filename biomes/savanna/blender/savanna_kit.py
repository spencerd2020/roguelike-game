"""Seeded savanna kit for the Ochre Reach biome (run with Blender's Python: bpy 5.x).

Process (the same stages as Khadrel's hand-built pipeline, written fresh for this game):
  1. build   closed faceted solids in bmesh, every face tagged with a material slot, a part id and a node group
  2. unwrap  one unique atlas per asset (every face its own island, uniform texel density)
  3. bake    Cycles bakes per texel: slot + part (emit), world position, world normal, ambient occlusion and sky light
  4. paint   numpy turns the bake into palette pixels: per-part tone, slot pattern, wear, painted top light, ordered dither
  5. export  one glb per asset, nodes split by group (shell / dome / roof) so a viewer can lift the roof off

Every asset comes from one seed, so the same seed always builds the same model.

usage: python savanna_kit.py --asset house --seed hearth-1 --out out/ [--size 2048] [--render] [--samples 24]
assets: house, greathouse, granary, pavilion, thorn, bottle, kopje, mound, boulders
"""
import argparse, math, os, random, sys, time, zlib, json
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector

ap = argparse.ArgumentParser()
ap.add_argument('--asset', default='house')
ap.add_argument('--seed', default='hearth-1')
ap.add_argument('--out', default='out')
ap.add_argument("--size", type=int, default=2048)
ap.add_argument('--samples', type=int, default=24)
ap.add_argument('--render', action='store_true')
ap.add_argument('--geom', action='store_true', help='stop after building; render a clay preview only')
args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
os.makedirs(args.out, exist_ok=True)
NAME = f'{args.asset}_{args.seed}'


def stream(stage):
    """One random stream per stage, hashed from the asset, the seed and the stage name."""
    return random.Random(zlib.crc32(f'{args.asset}/{args.seed}/{stage}'.encode()))


# ---------------------------------------------------------------------------------------------------------------- build
SLOTS = ['clay', 'lime', 'thatch', 'wood', 'stone', 'bark', 'leaf', 'pod', 'cloth', 'grain', 'ash', 'floor', 'rope', 'ember']
SI = {s: i for i, s in enumerate(SLOTS)}
FLAT = {'ember'}  # glow slots stay a flat material, out of the atlas
bm = bmesh.new()
L_SLOT = bm.faces.layers.int.new('slot')
L_PART = bm.faces.layers.int.new('part')
L_GRP = bm.faces.layers.int.new('grp')
L_FIX = bm.faces.layers.int.new('fixed')   # faces wound by hand (open wall shells): normals are not recalculated
GROUPS = ['shell']
CUR = {'grp': 0, 'part': 0}
PARTS = {}  # part id -> name


def group(name):
    if name not in GROUPS:
        GROUPS.append(name)
    CUR['grp'] = GROUPS.index(name)


def part(name):
    CUR['part'] += 1
    PARTS[CUR['part']] = name
    return CUR['part']


def tag(faces, slot):
    for f in faces:
        f[L_SLOT] = SI[slot]
        f[L_PART] = CUR['part']
        f[L_GRP] = CUR['grp']
        f.smooth = False


def faces_of(verts):
    return list({f for v in verts for f in v.link_faces})


def quad(a, b, c, d, slot, fixed=False):
    vs = [bm.verts.new(p) for p in (a, b, c, d)]
    f = bm.faces.new(vs)
    tag([f], slot)
    f[L_FIX] = int(fixed)
    return f


def solid_rings(rings, slot, cap0=True, cap1=True):
    """Skin consecutive rings of equal length (lists of Vectors) into a closed or open tube."""
    vr = [[bm.verts.new(p) for p in r] for r in rings]
    fs = []
    n = len(rings[0])
    for a, b in zip(vr, vr[1:]):
        for i in range(n):
            j = (i + 1) % n
            fs.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    if cap0:
        fs.append(bm.faces.new(list(reversed(vr[0]))))
    if cap1:
        fs.append(bm.faces.new(vr[-1]))
    tag(fs, slot)
    return vr, fs


def lathe(profile, segs, slot, center=(0, 0, 0), phase=0.0, cap0=True, cap1=True, wob=None):
    """Revolve [(r, z), ...] around a vertical axis. Faceted, closed by caps unless told otherwise."""
    cx, cy, cz = center
    rings = []
    for k, (r, z) in enumerate(profile):
        ring = []
        for i in range(segs):
            a = phase + 2 * math.pi * i / segs
            rr = max(r, 0.002) * (1 + (wob(k, i) if wob else 0))
            ring.append(Vector((cx + rr * math.cos(a), cy + rr * math.sin(a), cz + z)))
        rings.append(ring)
    return solid_rings(rings, slot, cap0 and profile[0][0] > 0.003, cap1 and profile[-1][0] > 0.003)


def box(center, size, slot, rot=0.0, tilt=None):
    m = Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot, 4, 'Z')
    if tilt is not None:
        m = m @ tilt
    m = m @ Matrix.Diagonal(Vector((*size, 1)))
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    tag(faces_of(res['verts']), slot)
    return res


def aim(direction):
    return Vector((0, 0, 1)).rotation_difference(Vector(direction).normalized()).to_matrix().to_4x4()


def tube(points, radii, slot, segs=6, cap0=True, cap1=True, spin=0.0):
    """A tapered tube along a polyline with rotation-minimising frames (no twist on vertical runs)."""
    pts = [Vector(p) for p in points]
    t0 = (pts[1] - pts[0]).normalized()
    ref = Vector((1, 0, 0)) if abs(t0.x) < 0.9 else Vector((0, 1, 0))
    nrm = t0.cross(ref).normalized()
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            t = t0
        elif i == len(pts) - 1:
            t = (pts[i] - pts[i - 1]).normalized()
        else:
            t = ((pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()).normalized()
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        ring = []
        for k in range(segs):
            a = spin + 2 * math.pi * k / segs
            ring.append(p + (nrm * math.cos(a) + bi * math.sin(a)) * max(radii[i], 0.003))
        rings.append(ring)
    return solid_rings(rings, slot, cap0, cap1)


def blob(center, radii, slot, rng, subdiv=2, rough=0.18, flat_bottom=None):
    """A faceted lump: an icosphere pushed about by low noise, scaled to radii."""
    res = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
    off = [rng.uniform(-50, 50) for _ in range(3)]
    for v in res['verts']:
        d = v.co.normalized()
        n = (math.sin(d.x * 2.3 + off[0]) * math.sin(d.y * 2.9 + off[1]) * math.sin(d.z * 2.1 + off[2])
             + 0.5 * math.sin(d.x * 5.1 + off[1]) * math.sin(d.y * 4.7 + off[2]))
        k = 1 + rough * n
        v.co = Vector((d.x * radii[0] * k, d.y * radii[1] * k, d.z * radii[2] * k)) + Vector(center)
        if flat_bottom is not None and v.co.z < flat_bottom:
            v.co.z = flat_bottom
    tag(faces_of(res['verts']), slot)
    return res


# ----------------------------------------------------------------------------------------------------- the house family
# A sun-hat house: a round drum of rammed red earth on a granite footing, closed by a clay dome with a smoke oculus over
# the hearth, and shaded by a broad woven parasol that floats on poles above the dome. The gap between dome and parasol
# lets the smoke out and the wind through. A short vaulted porch keeps the sun out of the doorway. Inside, the rooms are
# exactly what the outside implies: the wall thickness shows in every opening, the oculus sits over the hearth, the bench
# follows the wall, and the window grilles are the same pieces seen from both sides.

def ring_pt(r, a, z):
    return Vector((r * math.cos(a), r * math.sin(a), z))


def drum_wall(R, T, z0, z1, segs, openings, slot_out='clay', slot_in='lime', lift=0.0):
    """A thick round wall built per segment column. openings: {segment index: [(zlo, zhi), ...] gaps}.
    Each solid interval is a block; a block's side face is only built where the neighbouring column is open (the reveal
    of a door or window), so no coincident faces sit inside the wall to show as seams."""
    Ri = R - T
    da = 2 * math.pi / segs

    def solids_of(i):
        gaps = sorted(openings.get(i % segs, []))
        out, z = [], z0
        for lo, hi in gaps:
            if lo > z:
                out.append((z, lo))
            z = max(z, hi)
        if z < z1:
            out.append((z, z1))
        return out

    def open_parts(i, lo, hi):
        """Sub-intervals of [lo, hi] where column i has no wall."""
        parts, z = [], lo
        for a, b in solids_of(i):
            if b <= z or a >= hi:
                continue
            if a > z:
                parts.append((z, min(a, hi)))
            z = max(z, b)
        if z < hi:
            parts.append((z, hi))
        return [(a, b) for a, b in parts if b - a > 1e-4]

    for i in range(segs):
        a0, a1 = i * da, (i + 1) * da
        for lo, hi in solids_of(i):
            o0, o1, i0, i1 = ring_pt(R, a0, lo), ring_pt(R, a1, lo), ring_pt(Ri, a0, lo), ring_pt(Ri, a1, lo)
            O0, O1, I0, I1 = ring_pt(R, a0, hi), ring_pt(R, a1, hi), ring_pt(Ri, a0, hi), ring_pt(Ri, a1, hi)
            quad(o0, o1, O1, O0, slot_out, True)            # outside face
            quad(i1, i0, I0, I1, slot_in, True)             # inside face
            if hi < z1 - 1e-4 or True:
                quad(O0, O1, I1, I0, slot_out, True)        # top (sill or wall head)
            if lo > z0 + 1e-4:
                quad(i0, i1, o1, o0, slot_out, True)        # soffit over an opening
            for (pa, pb) in open_parts(i - 1, lo, hi):    # reveal on the a0 side
                quad(ring_pt(Ri, a0, pa), ring_pt(R, a0, pa), ring_pt(R, a0, pb), ring_pt(Ri, a0, pb), slot_out, True)
            for (pa, pb) in open_parts(i + 1, lo, hi):    # reveal on the a1 side
                quad(ring_pt(R, a1, pa), ring_pt(Ri, a1, pa), ring_pt(Ri, a1, pb), ring_pt(R, a1, pb), slot_out, True)


def dome(R_out, R_in, z0, h_out, h_in, oculus, segs, slot_out='clay', slot_in='lime', rings=7):
    """A clay dome shell from the wall head up to an oculus. Outer and inner surfaces plus the oculus rim."""
    def prof(R, h):
        out = []
        for k in range(rings + 1):
            t = k / rings
            r = oculus + (R - oculus) * math.cos(t * math.pi / 2) ** 0.85
            z = z0 + h * math.sin(t * math.pi / 2) ** 1.1
            out.append((r, z))
        return out
    po, pi = prof(R_out, h_out), prof(R_in, h_in)
    ring = lambda r, z: [ring_pt(r, 2 * math.pi * i / segs, z) for i in range(segs)]
    _, fo = solid_rings([ring(r, z) for r, z in po], slot_out, cap0=False, cap1=False)
    _, fi = solid_rings([ring(r, z) for r, z in reversed(pi)], slot_in, cap0=False, cap1=False)
    # oculus lip: from the outer top ring down to the inner top ring
    r_o, z_o = po[-1]
    r_i, z_i = pi[-1]
    solid_rings([ring(r_o, z_o), ring(r_i * 0.98, z_o - 0.02), ring(r_i, z_i)], slot_out, cap0=False, cap1=False)
    # the base ledge where the dome meets the wall head is covered by the wall top
    return po, pi


def thatch_parasol(R, z_rim, z_peak, segs, rng, thick=0.16, fringe=0.22, r_in=0.0, crown=None):
    """A broad woven roof with a ragged fringe and a visible underside. With r_in > 0 it is an open ring rising to an inner
    rim at z_peak, and a small crown cap floats above the hole on short posts: the smoke from the oculus leaves through
    the stacked gaps. The whole roof reads as a stacked hat from far off."""
    part('parasol')
    rings_top, rings_bot = [], []
    steps = 7
    r_end = r_in if r_in > 0 else 0.12
    for k in range(steps + 1):
        t = k / steps
        r = R * (1 - t) + r_end * t
        # a slight upward flare at the rim, then straight to the inner rim
        z = z_rim + (z_peak - z_rim) * (t ** 0.85)
        rings_top.append([ring_pt(r, 2 * math.pi * i / segs, z + thick) for i in range(segs)])
        rings_bot.append([ring_pt(r * 0.995, 2 * math.pi * i / segs, z) for i in range(segs)])
    edge_top = [ring_pt(R + 0.05, 2 * math.pi * i / segs, z_rim + thick * 0.4 - (fringe if i % 2 else fringe * 0.45)
                        - rng.uniform(0, 0.06)) for i in range(segs)]
    if r_in > 0:
        solid_rings([edge_top] + rings_top + list(reversed(rings_bot)) + [edge_top], 'thatch', cap0=False, cap1=False)
        # the inner rim is bound with a rope coil
        part('parasol-binding')
        lathe([(r_in + 0.02, z_peak - 0.04), (r_in - 0.06, z_peak + 0.06), (r_in - 0.02, z_peak + thick + 0.08), (r_in + 0.12, z_peak + thick + 0.04)],
              segs, 'rope', cap0=False, cap1=False)
    else:
        solid_rings([edge_top] + rings_top, 'thatch', cap0=False, cap1=True)
        solid_rings(list(reversed(rings_bot)) + [edge_top], 'thatch', cap0=True, cap1=False)
    if crown:
        cr, cz0, cz1, nposts = crown
        for k in range(nposts):
            a = 2 * math.pi * k / nposts + 0.3
            part(f'crown-post:{k}')
            tube([ring_pt(r_in - 0.05, a, z_peak), ring_pt(r_in - 0.05, a, cz0 + 0.05)], [0.05, 0.045], 'wood', segs=5)
        part('crown')
        cs = max(12, segs // 2)
        ct = [[ring_pt(cr * (1 - t) + 0.06 * t, 2 * math.pi * i / cs, cz0 + 0.1 + (cz1 - cz0) * t) for i in range(cs)] for t in (0, 0.5, 1)]
        cb = [ring_pt(cr * 0.97, 2 * math.pi * i / cs, cz0) for i in range(cs)]
        ce = [ring_pt(cr + 0.04, 2 * math.pi * i / cs, cz0 - (0.16 if i % 2 else 0.07)) for i in range(cs)]
        solid_rings([ce] + ct, 'thatch', cap0=False, cap1=True)
        solid_rings([cb, ce], 'thatch', cap0=True, cap1=False)
        part('crown-knot')
        lathe([(0.2, cz1 + 0.02), (0.15, cz1 + 0.25), (0.05, cz1 + 0.42), (0.02, cz1 + 0.5)], 10, 'rope')
    else:
        part('parasol-knot')
        lathe([(0.32, z_peak + thick - 0.05), (0.26, z_peak + thick + 0.25), (0.14, z_peak + thick + 0.42), (0.04, z_peak + thick + 0.5)],
              10, 'rope')


def jar(c, h, r, rng, slot='clay', lid=False):
    part('jar')
    prof = [(r * 0.5, 0), (r * 0.92, h * 0.18), (r, h * 0.45), (r * 0.8, h * 0.78), (r * 0.42, h * 0.9), (r * 0.48, h)]
    lathe(prof, 14, slot, center=c, cap1=True)
    if lid:
        lathe([(r * 0.5, h), (r * 0.46, h + 0.05), (0.03, h + 0.07)], 14, 'wood', center=c)


def hearth(c, rng):
    part('hearth-stones')
    n = 9
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.1, 0.1)
        rr = 0.42
        blob((c[0] + rr * math.cos(a), c[1] + rr * math.sin(a), c[2] + 0.06), (0.13, 0.11, 0.1), 'stone', rng, subdiv=1, rough=0.2,
             flat_bottom=c[2])
    part('hearth-ash')
    lathe([(0.36, 0.0), (0.33, 0.035), (0.05, 0.05)], 12, 'ash', center=c)
    part('embers')
    for i in range(5):
        a = rng.uniform(0, 6.28)
        rr = rng.uniform(0, 0.18)
        blob((c[0] + rr * math.cos(a), c[1] + rr * math.sin(a), c[2] + 0.05), (0.07, 0.05, 0.035), 'ember', rng, subdiv=1, rough=0.25)
    part('firewood')
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.4
        p0 = Vector((c[0] + 0.3 * math.cos(a), c[1] + 0.3 * math.sin(a), c[2] + 0.04))
        p1 = Vector((c[0] + 0.03 * math.cos(a), c[1] + 0.03 * math.sin(a), c[2] + 0.16))
        tube([p0, p1], [0.035, 0.03], 'wood', segs=5)


def stool(c, rng, rot=0.0):
    part('stool')
    lathe([(0.17, 0.0), (0.1, 0.06), (0.07, 0.22), (0.17, 0.3), (0.19, 0.34), (0.001, 0.35)], 10, 'wood', center=c, phase=rot)


def house(variant='hearth'):
    rng = stream('form')
    big = variant == 'great'
    R = (4.6 if big else 3.4) + rng.uniform(-0.2, 0.25)
    T = 0.38 if big else 0.34
    H = (2.7 if big else 2.35) + rng.uniform(-0.1, 0.1)
    Z0 = 0.3                       # floor level, on top of the footing
    segs = 36 if big else 28
    da = 2 * math.pi / segs
    door_i = segs // 4             # the door faces +Y (local), segment centred on 90 degrees
    door_i -= 1 if (segs // 4) * da + da / 2 > math.pi / 2 + 1e-6 else 0
    door_a = (door_i + 0.5) * da
    door_h = 1.95
    # windows: seeded, never in the door's neighbours, never behind the bench (opposite the door)
    nwin = (5 if big else 3) + rng.randint(0, 1)
    cand = [i for i in range(segs) if min((i - door_i) % segs, (door_i - i) % segs) > 2
            and min((i - (door_i + segs // 2)) % segs, ((door_i + segs // 2) - i) % segs) > (4 if big else 3)]
    rng.shuffle(cand)
    wins = []
    for i in cand:
        if all(min((i - w) % segs, (w - i) % segs) > 2 for w in wins):
            wins.append(i)
        if len(wins) == nwin:
            break
    sill, head = Z0 + 1.15, Z0 + 1.75
    openings = {door_i: [(Z0 - 0.01, Z0 + door_h)]}
    for w in wins:
        openings[w] = [(sill, head)]
    info = {'R': R, 'T': T, 'H': H, 'floor': Z0, 'door_angle_deg': round(math.degrees(door_a), 2), 'windows': len(wins)}

    group('shell')
    # granite footing: a ring of dressed blocks, a little proud of the wall
    part('footing')
    lathe([(R + 0.16, -0.25), (R + 0.16, Z0 - 0.02), (R + 0.06, Z0 + 0.02), (R - T - 0.02, Z0 + 0.02), (R - T - 0.02, -0.25)], segs,
          'stone', cap0=False, cap1=False)
    # floor: packed earth, with a raised clay rim at the wall
    part('floor')
    lathe([(R - T + 0.01, Z0 + 0.012), (0.001, Z0 + 0.012)], segs, 'floor', cap0=False, cap1=False)
    # the drum wall in two lifts (rammed earth goes up in lifts; the painter marks them)
    part('wall')
    drum_wall(R, T, Z0, Z0 + H, segs, openings)
    # door: a short vaulted porch, its walls the same thickness as the drum, lime-framed
    part('porch')
    px, py = math.cos(door_a), math.sin(door_a)
    tang = Vector((-py, px, 0))
    out = Vector((px, py, 0))
    w = 2 * R * math.sin(da / 2)              # opening width at the outer face
    depth = 0.65
    base = out * (R - 0.05)
    for side in (-1, 1):
        cpos = base + out * depth / 2 + tang * side * (w / 2 + 0.14)
        box((cpos.x, cpos.y, Z0 + door_h / 2 + 0.05), (0.28, depth, door_h + 0.1), 'clay', rot=door_a - math.pi / 2)
    # porch vault: a half-barrel over the passage
    arc = 9
    for k in range(arc):
        t0, t1 = math.pi * k / arc, math.pi * (k + 1) / arc
        for (ra, rb, sl) in ((w / 2 + 0.28, w / 2 + 0.28, 'clay'),):
            pass
    vault_o, vault_i = [], []
    for k in range(arc + 1):
        t = math.pi * k / arc
        vault_o.append((math.cos(t) * (w / 2 + 0.28), math.sin(t) * 0.55 + 0.1))
        vault_i.append((math.cos(t) * (w / 2), math.sin(t) * 0.4))
    zc = Z0 + door_h - 0.12
    for prof, sl, flip in ((vault_o, 'clay', False), (vault_i, 'lime', True)):
        ra = [base + tang * x + Vector((0, 0, zc + y)) for x, y in prof]
        rb = [p + out * depth for p in ra]
        for k in range(arc):
            if flip:
                quad(ra[k], rb[k], rb[k + 1], ra[k + 1], sl)
            else:
                quad(ra[k + 1], rb[k + 1], rb[k], ra[k], sl)
    # front face of the vault (the arch ring), lime-washed
    fr_o = [base + out * depth + tang * x + Vector((0, 0, zc + y)) for x, y in vault_o]
    fr_i = [base + out * depth + tang * x + Vector((0, 0, zc + y)) for x, y in vault_i]
    for k in range(arc):
        quad(fr_o[k], fr_o[k + 1], fr_i[k + 1], fr_i[k], 'lime')
    # threshold stone
    part('threshold')
    tp = base + out * (depth * 0.5)
    box((tp.x, tp.y, Z0 - 0.03), (w + 0.2, depth + 0.4, 0.12), 'stone', rot=door_a - math.pi / 2)
    # a woven door screen rolled up under the lintel
    part('door-roll')
    rp = base + out * (depth - 0.08)
    tube([rp - tang * (w / 2 - 0.05) + Vector((0, 0, Z0 + door_h - 0.25)), rp + tang * (w / 2 - 0.05) + Vector((0, 0, Z0 + door_h - 0.25))],
         [0.07, 0.07], 'rope', segs=8)
    # window grilles: a lattice of thin wood bars set in the middle of the wall thickness, seen from both sides
    for wi in wins:
        part(f'grille:{wi}')
        a = (wi + 0.5) * da
        c = ring_pt(R - T / 2, a, (sill + head) / 2)
        tg = Vector((-math.sin(a), math.cos(a), 0))
        ww = 2 * (R - T / 2) * math.sin(da / 2)
        for k in (-1, 0, 1):
            p = c + tg * (k * ww / 3.2)
            tube([p - Vector((0, 0, (head - sill) / 2 + 0.02)), p + Vector((0, 0, (head - sill) / 2 + 0.02))], [0.022, 0.022], 'wood', segs=4)
        for k in (-1, 1):
            p = c + Vector((0, 0, k * (head - sill) / 4.5))
            tube([p - tg * (ww / 2 + 0.02), p + tg * (ww / 2 + 0.02)], [0.02, 0.02], 'wood', segs=4)
    # buttresses that carry the parasol poles: clay lumps against the wall, a pole socket in each
    npoles = 8 if big else 6
    pole_a = [door_a + math.pi / npoles + 2 * math.pi * k / npoles for k in range(npoles)]
    dome_h_out = (1.9 if big else 1.55)
    top = Z0 + H
    Rp = R + (1.7 if big else 1.45)
    z_rim = top + 0.72
    r_in = 1.25 if big else 1.1
    z_in = top + dome_h_out + 0.62
    under = lambda r: z_rim + (z_in - z_rim) * ((Rp - r) / (Rp - r_in)) ** (1 / 0.85)   # underside height at radius r
    r_pole = Rp - 0.6
    for k, a in enumerate(pole_a):
        part(f'buttress:{k}')
        bc = ring_pt(R + 0.18, a, 0)
        lathe([(0.34, -0.1), (0.34, Z0 + 0.4), (0.26, Z0 + 0.9), (0.2, Z0 + 1.15), (0.001, Z0 + 1.2)], 8, 'clay', center=tuple(bc),
              phase=a)
    group('roof')
    z_beam = under(r_pole) - 0.08
    for k, a in enumerate(pole_a):
        part(f'pole:{k}')
        p0 = ring_pt(R + 0.2, a, Z0 + 1.1)
        p1 = ring_pt(r_pole, a, z_beam - 0.1)
        tube([p0, (p0 + p1) / 2, p1], [0.085, 0.075, 0.065], 'wood', segs=6, spin=a)
        tg = Vector((-math.sin(a), math.cos(a), 0))
        for s in (-1, 1):            # a forked head cradles the ring beam
            tube([p1, p1 + tg * 0.16 * s + Vector((0, 0, 0.16))], [0.05, 0.035], 'wood', segs=5)
    part('ring-beam')
    rb = [ring_pt(r_pole, 2 * math.pi * i / 24, z_beam) for i in range(25)]
    tube(rb, [0.065] * 25, 'wood', segs=5)
    # rafters under the parasol, radiating from the rim to the inner ring (seen from below, through the gap)
    for k in range(npoles * 2):
        a = 2 * math.pi * k / (npoles * 2) + 0.1
        part(f'rafter:{k}')
        p0 = ring_pt(Rp - 0.2, a, under(Rp - 0.2) - 0.04)
        p1 = ring_pt(r_in + 0.05, a, under(r_in + 0.05) - 0.04)
        tube([p0, p1], [0.04, 0.035], 'wood', segs=4)
    crown_r = r_in + 0.7
    thatch_parasol(Rp, z_rim, z_in, 32 if big else 26, rng, r_in=r_in, crown=(crown_r, z_in + 0.62, z_in + 1.35, 4))
    info['roof'] = {'Rp': round(Rp, 2), 'gap_at_wall': round(under(R) - top, 2)}
    group('dome')
    part('dome')
    dome(R + 0.02, R - T, top, dome_h_out, dome_h_out - 0.22, 0.42 if big else 0.36, segs)
    # a raised clay lip round the oculus keeps rain off the hearth
    part('oculus-lip')
    lathe([(0.36 if not big else 0.42, top + dome_h_out - 0.04), (0.5 if not big else 0.56, top + dome_h_out - 0.02),
           (0.47 if not big else 0.53, top + dome_h_out + 0.16), (0.38 if not big else 0.44, top + dome_h_out + 0.18)], segs, 'clay',
          cap0=False, cap1=False)
    # a lime band painted round the wall head is done by the painter; here a clay coping ring sits at the wall top
    part('coping')
    lathe([(R + 0.06, top - 0.08), (R + 0.09, top - 0.02), (R + 0.04, top + 0.06)], segs, 'clay', cap0=False, cap1=False)

    # ---------------------------------------------------------------------------------------- furnishing the room
    group('shell')
    inner = R - T
    back = door_a + math.pi
    rngf = stream('furnish')
    hearth((0, 0, Z0 + 0.012), rngf)
    # The room is furnished with the studio's shared household props (retextured for the savanna by retex_props.py, never
    # remodelled). The generator only decides where each one stands; the viewer and the previews place the shared models.
    # Prop axes, as the shared kit builds them: front faces glTF +Z, i.e. Blender -Y; a wall piece's back is its -Z side.
    span = math.radians(110 if not big else 130)      # the stretch of wall opposite the door that windows keep clear of
    furn = []

    def put(prop, r, a, z=Z0 + 0.012, yaw=None, tang=0.0, **kw):
        p = ring_pt(r, a, z)
        if tang:
            p = p + Vector((-math.sin(a), math.cos(a), 0)) * tang
        furn.append(dict(prop=prop, pos=[round(p.x, 3), round(p.y, 3), round(p.z, 3)],
                         yaw=round(a - math.pi / 2 if yaw is None else yaw, 4), **kw))

    def wall(prop, a, depth, z=Z0 + 0.012, **kw):
        """Against the curved wall, facing the hearth. depth: the piece's front-to-back size; the chord's sag is allowed."""
        put(prop, inner - depth / 2 - 0.05, a, z, **kw)

    # sleeping: plank beds along the back wall, head to one side, blanket and bolster on each
    beds = [back] if not big else [back - math.radians(17), back + math.radians(17)]
    for k, ba in enumerate(beds):
        rb = inner - 0.475 - 0.2
        hy = ba if (k % 2 == 0) else ba + math.pi      # headboard (local -Y) points along the wall, alternating
        put('bed', rb, ba, yaw=hy)
        sgn = 1 if k % 2 == 0 else -1
        put('bed_blanket', rb, ba, Z0 + 0.012 + 0.42, yaw=hy, tang=0.2 * sgn)
        put('bed_pillow', rb, ba, Z0 + 0.012 + 0.42, yaw=hy, tang=-0.72 * sgn)
    put('rug_round', 1.35 if not big else 1.75, back, yaw=back + rngf.uniform(0, 1))
    # storage stands in a group on one side of the door: lidded crocks, a painted urn, grain sacks and a basket
    side = 1 if rngf.random() < 0.5 else -1
    ja = door_a + side * math.radians(62 + rngf.uniform(-6, 6))
    kinds = ['storage_jar', 'urn', 'storage_jar', 'sack'] + (['urn', 'sack', 'basket'] if big else ['basket'])
    for k, kind in enumerate(kinds):
        a = ja + side * k * (0.2 if not big else 0.15)
        rr = inner - 0.3 - (0.22 if k % 2 else 0)
        put(kind, rr, a, yaw=rngf.uniform(0, 6.283))
    # the other side of the door: a banded chest for cloth and the household's goods, firewood by the hearth side
    ca = door_a - side * math.radians(58)
    wall('chest', ca, 0.524)
    put('firewood_stack', inner - 0.35, door_a - side * math.radians(84), yaw=ca + rngf.uniform(-0.3, 0.3))
    # a peg rack on the wall at shoulder height, herbs drying from it
    pa = back + side * math.radians(38 if not big else 48)
    wall('peg_rack', pa, 0.172, z=Z0 + 1.3)
    for t in (-0.3, 0.1):
        put('hanging_herbs', inner - 0.16, pa, Z0 + 1.3 + 0.24, yaw=pa - math.pi / 2 + rngf.uniform(-0.4, 0.4), tang=t)
    # by the fire: a stool and the cook pot
    put('stool', 1.0, door_a + side * 0.9, yaw=rngf.uniform(0, 6.283))
    put('cauldron', 0.86, door_a - side * 0.75, yaw=rngf.uniform(0, 6.283))
    put('wooden_bowl', 0.95, door_a - side * 0.45, yaw=rngf.uniform(0, 6.283))
    if big:
        # the great house also feeds guests: a trestle table with a bench, open shelves of crockery, a hanging over the beds
        ta = back - side * math.radians(75)
        put('table', inner - 1.0, ta)
        put('bench', inner - 1.0 - 0.62, ta)
        put('jug', inner - 1.0, ta, Z0 + 0.012 + 0.76, tang=0.35)
        put('clay_cup', inner - 1.0 + 0.1, ta, Z0 + 0.012 + 0.76, tang=-0.1)
        put('clay_cup', inner - 1.0 - 0.12, ta, Z0 + 0.012 + 0.76, tang=-0.42)
        put('stool', 1.15, door_a - side * 1.15, yaw=rngf.uniform(0, 6.283))
        wall('shelf', back - side * math.radians(46), 0.365)
        wall('wall_hanging', back, 0.04, z=Z0 + 2.2)
    info['furniture'] = furn
    info['bench_span_deg'] = round(math.degrees(span))
    info['markers'] = {'hearth': [0, 0, Z0 + 0.1], 'door': [round(c, 3) for c in (out * (R + depth))[:2]] + [Z0],
                       'eye': [round(c, 3) for c in (out * (R - 0.9))[:2]] + [Z0 + 1.6]}
    return info


def granary():
    """A grain store on stone stilts: drum, conical hat, a hatch high up reached by a ladder. Inside: the grain heap."""
    rng = stream('form')
    R, T = 1.25 + rng.uniform(-0.1, 0.1), 0.16
    z0 = 0.9
    H = 2.1
    segs = 18
    group('shell')
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        part(f'stilt:{k}')
        c = ring_pt(R * 0.62, a, 0)
        blob((c.x, c.y, 0.25), (0.3, 0.3, 0.32), 'stone', rng, subdiv=1, rough=0.12, flat_bottom=-0.1)
        blob((c.x, c.y, 0.66), (0.24, 0.24, 0.22), 'stone', rng, subdiv=1, rough=0.12)
    part('deck')
    lathe([(R + 0.08, z0 - 0.12), (R + 0.12, z0), (0.001, z0)], segs, 'wood', cap0=True, cap1=False)
    hatch_i = segs // 4
    part('wall')
    drum_wall(R, T, z0, z0 + H, segs, {hatch_i: [(z0 + 1.15, z0 + 1.85)]}, slot_out='clay', slot_in='clay')
    part('floor')
    lathe([(R - T + 0.005, z0 + 0.01), (0.001, z0 + 0.01)], segs, 'floor', cap0=False, cap1=False)
    part('grain')
    lathe([(R - T - 0.01, z0 + 0.012), (R - T - 0.02, z0 + 0.5), (0.7, z0 + 0.8), (0.2, z0 + 0.98), (0.001, z0 + 1.0)], segs, 'grain',
          cap0=False, cap1=False)
    group('roof')
    part('hat')
    lathe([(R + 0.5, z0 + H - 0.12), (R + 0.55, z0 + H + 0.02), (0.05, z0 + H + 1.5), (0.001, z0 + H + 1.55)], segs, 'thatch',
          cap0=True, cap1=False)
    part('hat-knot')
    lathe([(0.16, z0 + H + 1.38), (0.12, z0 + H + 1.6), (0.03, z0 + H + 1.72)], 8, 'rope')
    group('shell')
    part('ladder')
    a = (hatch_i + 0.5) * 2 * math.pi / segs
    out = Vector((math.cos(a), math.sin(a), 0))
    tg = Vector((-out.y, out.x, 0))
    foot = out * (R + 0.95)
    topp = out * (R + 0.05) + Vector((0, 0, z0 + 1.2))
    for s in (-1, 1):
        tube([foot + tg * 0.2 * s, topp + tg * 0.2 * s], [0.035, 0.03], 'wood', segs=5)
    for k in range(1, 7):
        t = k / 7
        p = foot.lerp(topp, t)
        tube([p - tg * 0.22, p + tg * 0.22], [0.02, 0.02], 'wood', segs=4)
    return {'R': R, 'floor': z0, 'hatch': [round(x, 3) for x in (out * R)[:2]] + [z0 + 1.15]}


def pavilion():
    """The meeting shade: the house's parasol on a ring of carved posts over a round granite floor with a seat ring."""
    rng = stream('form')
    R = 4.2
    group('shell')
    part('floor')
    lathe([(R + 0.3, -0.2), (R + 0.3, 0.18), (R + 0.2, 0.25), (0.001, 0.25)], 30, 'stone', cap0=False, cap1=False)
    part('seat-ring')
    # a ring bench with two openings, so the shade can be walked into from the village paths on either side
    drum_wall(R - 0.15, 0.45, 0.25, 0.62, 30, {k: [(0.2, 0.7)] for k in (4, 5, 16, 17)}, slot_out='clay', slot_in='clay')
    group('roof')
    n = 7
    for k in range(n):
        a = 2 * math.pi * k / n + math.pi / n     # posts stand between the bench openings
        part(f'post:{k}')
        p0 = ring_pt(R - 0.35, a, 0.62)
        p1 = ring_pt(R - 0.35, a, 3.4)
        tube([p0, p1], [0.13, 0.11], 'wood', segs=8, spin=a)
        for zz in (1.4, 2.4):
            part(f'band:{k}')
            lathe([(0.135, zz), (0.15, zz + 0.04), (0.135, zz + 0.1)], 8, 'rope', center=(p0.x, p0.y, 0), cap0=False, cap1=False)
    part('ring-beam')
    rb = [ring_pt(R - 0.35, 2 * math.pi * i / 28, 3.45) for i in range(29)]
    tube(rb, [0.09] * 29, 'wood', segs=5)
    thatch_parasol(R + 1.6, 3.3, 5.6, 30, rng)
    return {'R': R}


# ------------------------------------------------------------------------------------------------------------- the land
def thorn_tree():
    """Parasol thorn: a leaning trunk that forks into a few long limbs, each ending in a broad flat tier of foliage pads.
    Seed pods hang in clusters under the tiers. Original form: the tiers are plates stacked like a broken stair."""
    rng = stream('form')
    group('shell')
    lean = Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), 1)).normalized()
    h0 = rng.uniform(2.2, 3.0)
    part('trunk')
    trunk = [Vector((0, 0, -0.3)), Vector((0, 0, 0.4)), lean * (h0 * 0.55), lean * h0]
    tube(trunk, [0.32, 0.26, 0.2, 0.17], 'bark', segs=8)
    # root flare
    for k in range(4):
        a = k * math.pi / 2 + rng.uniform(-0.3, 0.3)
        part('root')
        tube([Vector((0, 0, 0.5)), Vector((0.55 * math.cos(a), 0.55 * math.sin(a), 0.05)), Vector((0.9 * math.cos(a), 0.9 * math.sin(a), -0.15))],
             [0.15, 0.09, 0.04], 'bark', segs=5)
    tips = []

    def limb(p, d, length, r, depth):
        n = 4
        pts = [p]
        for i in range(n):
            d = (d + Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), rng.uniform(-0.05, 0.1)))).normalized()
            pts.append(pts[-1] + d * length / n)
        part('limb')
        tube(pts, [r * (1 - 0.55 * i / n) for i in range(n + 1)], 'bark', segs=6 if depth == 0 else 5)
        if depth < 2:
            k = 2 if depth == 0 else rng.randint(1, 2)
            for j in range(k):
                a = rng.uniform(0, 6.28)
                nd = (d + Vector((math.cos(a), math.sin(a), 0)) * rng.uniform(0.5, 0.9) + Vector((0, 0, 0.35))).normalized()
                limb(pts[-1], nd, length * rng.uniform(0.55, 0.75), r * 0.5, depth + 1)
        else:
            tips.append(pts[-1])
    nl = rng.randint(3, 4)
    for i in range(nl):
        a = 2 * math.pi * i / nl + rng.uniform(-0.4, 0.4)
        d = (Vector((math.cos(a), math.sin(a), 0)) * rng.uniform(0.7, 1.0) + Vector((0, 0, 0.9))).normalized()
        limb(lean * h0, d, rng.uniform(2.0, 2.8), 0.13, 0)
    top = max(t.z for t in tips)
    # foliage: flat pads round each tip, in tiers, faceted
    for t in tips:
        part('pad')
        z = t.z + rng.uniform(0.05, 0.25)
        for k in range(rng.randint(2, 3)):
            off = Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(-0.1, 0.25)))
            rr = rng.uniform(1.0, 1.6)
            blob(tuple(t + off + Vector((0, 0, 0.15))), (rr, rr * rng.uniform(0.8, 1.1), rng.uniform(0.22, 0.32)), 'leaf', rng, subdiv=2,
                 rough=0.22)
        # pods hang under the pad
        if rng.random() < 0.7:
            for k in range(rng.randint(3, 6)):
                part('pod')
                p = t + Vector((rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), -0.05))
                tube([p, p + Vector((rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), -rng.uniform(0.25, 0.4)))], [0.035, 0.05], 'pod', segs=4)
    return {'height': round(top + 0.5, 2), 'tips': len(tips)}


def bottle_tree():
    """Bottle tree: a swollen, ribbed water-storing trunk with a crown of stubby arms, sparse leaf tufts and gourd fruit."""
    rng = stream('form')
    group('shell')
    H = rng.uniform(5.5, 7.0)
    Rb = rng.uniform(1.0, 1.35)
    ribs = 11
    part('trunk')
    prof = [(Rb * 1.25, -0.3), (Rb * 1.15, 0.2), (Rb * 1.05, H * 0.15), (Rb, H * 0.35), (Rb * 0.92, H * 0.55), (Rb * 0.72, H * 0.75),
            (Rb * 0.5, H * 0.88), (Rb * 0.42, H)]
    lathe(prof, ribs * 2, 'bark', wob=lambda k, i: (0.07 if i % 2 else -0.05) * (1 if k < 7 else 0.5))
    crown = []
    na = rng.randint(6, 8)
    for i in range(na):
        a = 2 * math.pi * i / na + rng.uniform(-0.2, 0.2)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(0.6, 1.2))).normalized()
        p0 = Vector((math.cos(a) * Rb * 0.3, math.sin(a) * Rb * 0.3, H - 0.1))
        pts = [p0]
        L = rng.uniform(1.4, 2.4)
        for k in range(3):
            d = (d + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0.15))).normalized()
            pts.append(pts[-1] + d * L / 3)
        part('arm')
        tube(pts, [0.26, 0.18, 0.12, 0.07], 'bark', segs=6)
        crown.append(pts[-1])
        # twigs
        for k in range(2):
            a2 = rng.uniform(0, 6.28)
            tp = pts[-1] + Vector((math.cos(a2) * 0.5, math.sin(a2) * 0.5, rng.uniform(0.2, 0.5)))
            part('twig')
            tube([pts[-1], tp], [0.06, 0.03], 'bark', segs=4)
            part('tuft')
            blob(tuple(tp + Vector((0, 0, 0.1))), (0.55, 0.55, 0.35), 'leaf', rng, subdiv=1, rough=0.3)
        if rng.random() < 0.8:
            part('fruit')
            fp = pts[2] + Vector((0, 0, -0.1))
            tube([fp, fp + Vector((0, 0, -0.45))], [0.01, 0.01], 'rope', segs=3)
            lathe([(0.03, 0.0), (0.13, 0.12), (0.12, 0.3), (0.02, 0.38)], 8, 'pod', center=(fp.x, fp.y, fp.z - 0.83))
    return {'height': round(H + 2, 2)}


def kopje():
    """A granite outcrop: big rounded boulders stacked on a low dome of bedrock, split by joints, one balanced on top."""
    rng = stream('form')
    group('shell')
    part('bedrock')
    blob((0, 0, -1.2), (11, 8.5, 3.0), 'stone', rng, subdiv=3, rough=0.12)
    rocks = []
    for i in range(rng.randint(9, 13)):
        a = rng.uniform(0, 6.28)
        d = rng.uniform(0, 6.5)
        r = rng.uniform(1.6, 3.6) * (1.2 - d / 12)
        c = Vector((d * math.cos(a), d * math.sin(a) * 0.8, 1.3 + r * 0.55 - d * 0.18))
        rocks.append((c, r))
        part(f'boulder:{i}')
        blob(tuple(c), (r * rng.uniform(0.9, 1.3), r * rng.uniform(0.8, 1.1), r * rng.uniform(0.62, 0.8)), 'stone', rng, subdiv=3, rough=0.14)
    c, r = max(rocks, key=lambda x: x[0].z + x[1] * 0.7)
    part('balanced')
    br = rng.uniform(1.8, 2.3)
    blob(tuple(c + Vector((0.3, -0.2, r * 0.7 + br * 0.8))), (br * 1.25, br, br * 0.85), 'stone', rng, subdiv=3, rough=0.12)
    top = c.z + r * 0.7 + br * 1.7
    return {'height': round(top, 2)}


def mound():
    """Clay chimney mound: a cluster of fluted red-earth spires grown up from a broad base, as a colony builds them."""
    rng = stream('form')
    group('shell')
    part('base')
    blob((0, 0, 0.0), (1.4, 1.2, 0.8), 'clay', rng, subdiv=2, rough=0.2, flat_bottom=-0.3)
    n = rng.randint(2, 4)
    tops = []
    for i in range(n):
        a = rng.uniform(0, 6.28)
        d = 0 if i == 0 else rng.uniform(0.4, 0.8)
        h = rng.uniform(3.0, 4.8) if i == 0 else rng.uniform(1.4, 3.0)
        c = (d * math.cos(a), d * math.sin(a), 0.2)
        r = rng.uniform(0.55, 0.8) if i == 0 else rng.uniform(0.3, 0.5)
        part(f'spire:{i}')
        k = 9
        prof = [(r * (1 - (t / k) ** 1.3) + 0.04, h * t / k) for t in range(k + 1)]
        lathe(prof, 9, 'clay', center=c, wob=lambda kk, ii: 0.1 * math.sin(ii * 2.1 + kk * 1.7) + (0.08 if ii % 3 == 0 else 0))
        tops.append(h)
    return {'height': round(max(tops) + 0.2, 2)}


def boulders():
    """Loose granite boulders for the grass: five sizes in one model, laid out on a line, the viewer splits them by node."""
    rng = stream('form')
    for i in range(5):
        group(f'b{i}')
        part(f'b{i}')
        r = 0.35 + i * 0.32
        blob((i * 4.0, 0, r * 0.35), (r * rng.uniform(1.0, 1.4), r, r * rng.uniform(0.6, 0.8)), 'stone', rng, subdiv=2, rough=0.16,
             flat_bottom=-0.1)
    return {}


BUILDERS = {'house': lambda: house('hearth'), 'greathouse': lambda: house('great'), 'granary': granary, 'pavilion': pavilion,
            'thorn': thorn_tree, 'bottle': bottle_tree, 'kopje': kopje, 'mound': mound, 'boulders': boulders}
t0 = time.time()
INFO = BUILDERS[args.asset]()
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
bmesh.ops.recalc_face_normals(bm, faces=[f for f in bm.faces if not f[L_FIX]])
print(f'[{NAME}] built {len(bm.faces)} faces in {time.time() - t0:.1f}s')

# ------------------------------------------------------------------------------------------------------- mesh + scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
mesh = bpy.data.meshes.new(NAME)
bm.to_mesh(mesh)
obj = bpy.data.objects.new(NAME, mesh)
bpy.context.scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
mesh.polygons.foreach_set('use_smooth', [False] * len(mesh.polygons))

slot_arr = np.zeros(len(mesh.polygons), np.int32)
part_arr = np.zeros(len(mesh.polygons), np.int32)
grp_arr = np.zeros(len(mesh.polygons), np.int32)
mesh.attributes['slot'].data.foreach_get('value', slot_arr)
mesh.attributes['part'].data.foreach_get('value', part_arr)
mesh.attributes['grp'].data.foreach_get('value', grp_arr)

# id colour per face corner: R = slot, G = per-part tone hash, B = flat flag. Read by the emit bake.
ph = np.array([(zlib.crc32(f'{args.seed}/{p}'.encode()) % 997) / 997.0 for p in range(max(part_arr) + 1)], np.float32)
col = mesh.color_attributes.new('idc', 'FLOAT_COLOR', 'CORNER')
loop_face = np.zeros(len(mesh.loops), np.int32)
for poly in mesh.polygons:
    loop_face[poly.loop_start:poly.loop_start + poly.loop_total] = poly.index
cdat = np.zeros((len(mesh.loops), 4), np.float32)
cdat[:, 0] = (slot_arr[loop_face] + 0.5) / 32.0
cdat[:, 1] = ph[part_arr[loop_face]]
cdat[:, 3] = 1
col.data.foreach_set('color', cdat.ravel())

ntri = sum(len(p.vertices) - 2 for p in mesh.polygons)
INFO.update({'asset': args.asset, 'seed': args.seed, 'tris': ntri, 'groups': GROUPS,
             'bounds': [[round(min(v.co[i] for v in mesh.vertices), 2) for i in range(3)],
                        [round(max(v.co[i] for v in mesh.vertices), 2) for i in range(3)]]})

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = args.samples
world = bpy.data.worlds.new('sky')
scene.world = world
world.use_nodes = True


def set_sky(strength, colr=(0.75, 0.82, 0.95, 1)):
    bg = world.node_tree.nodes['Background']
    bg.inputs[0].default_value = colr
    bg.inputs[1].default_value = strength


# ------------------------------------------------------------------------------------------------------------- unwrap
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(50), island_margin=0.0035, area_weight=0.0, correct_aspect=True,
                         scale_to_bounds=False)
bpy.ops.object.mode_set(mode='OBJECT')
uv_area = 0.0
uvl = mesh.uv_layers.active.data
area3 = sum(p.area for p in mesh.polygons)


def img(name, float_=True):
    im = bpy.data.images.new(name, args.size, args.size, alpha=False, float_buffer=float_)
    im.colorspace_settings.name = 'Non-Color'
    return im


def bake_mat(nodes_fn):
    m = bpy.data.materials.new('bake')
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    outn = nt.nodes.new('ShaderNodeOutputMaterial')
    nodes_fn(nt, outn)
    tex = nt.nodes.new('ShaderNodeTexImage')
    nt.nodes.active = tex
    return m, tex


def bake(kind, image, **kw):
    mat, tex = BAKE_MAT
    tex.image = image
    t = time.time()
    bpy.ops.object.bake(type=kind, margin=6, margin_type='EXTEND', use_clear=True, **kw)
    print(f'[{NAME}] bake {kind} {time.time() - t:.1f}s')
    px = np.array(image.pixels[:], np.float32).reshape(args.size, args.size, 4)
    return px


def emit_nodes(nt, outn):
    a = nt.nodes.new('ShaderNodeAttribute')
    a.attribute_name = 'idc'
    e = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(a.outputs['Color'], e.inputs['Color'])
    d = nt.nodes.new('ShaderNodeBsdfDiffuse')
    d.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1)
    mix = nt.nodes.new('ShaderNodeAddShader')
    nt.links.new(e.outputs[0], mix.inputs[0])
    nt.links.new(d.outputs[0], mix.inputs[1])
    nt.links.new(mix.outputs[0], outn.inputs['Surface'])


if not args.geom:
    BAKE_MAT = bake_mat(emit_nodes)
    obj.data.materials.clear()
    obj.data.materials.append(BAKE_MAT[0])
    S = args.size
    tb = time.time()
    scene.cycles.samples = 1
    E = bake('EMIT', img('emit'))
    P = bake('POSITION', img('pos'))
    N = bake('NORMAL', img('nrm'), normal_space='OBJECT', normal_r='POS_X', normal_g='POS_Y', normal_b='POS_Z')
    scene.cycles.samples = args.samples
    world.light_settings.distance = 3.0
    A = bake('AO', img('ao'))
    # sky light lit from above: a bright overcast dome plus a high sun, white surfaces, so the bake holds the sheltering only
    set_sky(1.0, (1, 1, 1, 1))
    sun = bpy.data.lights.new('sun', 'SUN')
    sun.energy = 2.2
    sun.angle = math.radians(12)
    so = bpy.data.objects.new('sun', sun)
    so.rotation_euler = (math.radians(28), math.radians(10), math.radians(35))
    scene.collection.objects.link(so)
    scene.cycles.max_bounces = 2
    Lgt = bake('DIFFUSE', img('light'), pass_filter={'DIRECT', 'INDIRECT'})
    print(f'[{NAME}] all bakes {time.time() - tb:.1f}s')
    bpy.data.objects.remove(so)

    # --------------------------------------------------------------------------------------------------------- paint
    from savanna_paint import paint_atlas
    rgb = paint_atlas(E, P, N, A, Lgt, SLOTS, args.asset, args.seed, INFO)
    atlas = bpy.data.images.new(NAME + '_atlas', S, S, alpha=False)
    flat = np.concatenate([rgb, np.ones(rgb.shape[:2] + (1,), np.float32)], axis=2)
    atlas.pixels.foreach_set(flat.ravel())
    atlas.filepath_raw = os.path.join(args.out, NAME + '_atlas.png')
    atlas.file_format = 'PNG'
    atlas.save()

    # --------------------------------------------------------------------------------------------- export materials
    obj.data.materials.clear()
    m_atl = bpy.data.materials.new('atlas')
    m_atl.use_nodes = True
    bsdf = m_atl.node_tree.nodes['Principled BSDF']
    t_n = m_atl.node_tree.nodes.new('ShaderNodeTexImage')
    t_n.image = atlas
    t_n.interpolation = 'Closest'
    m_atl.node_tree.links.new(t_n.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.95
    m_emb = bpy.data.materials.new('ember')
    m_emb.use_nodes = True
    b2 = m_emb.node_tree.nodes['Principled BSDF']
    b2.inputs['Base Color'].default_value = (1.0, 0.45, 0.12, 1)
    b2.inputs['Emission Color'].default_value = (1.0, 0.45, 0.12, 1)
    b2.inputs['Emission Strength'].default_value = 3.0
    obj.data.materials.append(m_atl)
    obj.data.materials.append(m_emb)
    mi = np.where(np.isin(slot_arr, [SI[s] for s in FLAT]), 1, 0).astype(np.int32)
    mesh.polygons.foreach_set('material_index', mi)

# ------------------------------------------------------------------------------------------- split by group, export
mesh.attributes.remove(mesh.attributes['slot'])
mesh.attributes.remove(mesh.attributes['part'])
mesh.attributes.remove(mesh.attributes['fixed'])
objs = []
for gi, gname in enumerate(GROUPS):
    sel = grp_arr == gi
    if not sel.any():
        continue
    o = obj.copy()
    o.data = obj.data.copy()
    o.name = gname
    bpy.context.scene.collection.objects.link(o)
    bm2 = bmesh.new()
    bm2.from_mesh(o.data)
    bm2.faces.ensure_lookup_table()
    bmesh.ops.delete(bm2, geom=[f for f in bm2.faces if not sel[f.index]], context='FACES')
    bm2.to_mesh(o.data)
    bm2.free()
    if 'grp' in o.data.attributes:
        o.data.attributes.remove(o.data.attributes['grp'])
    if 'idc' in o.data.color_attributes:
        o.data.color_attributes.remove(o.data.color_attributes['idc'])
    objs.append(o)
bpy.data.objects.remove(obj)
for o in bpy.data.objects:
    o.select_set(o.name in GROUPS)
glb = os.path.join(args.out, NAME + '.glb')
if not args.geom:
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_image_format='JPEG',
                              export_jpeg_quality=90, export_apply=False, export_attributes=False, export_normals=True,
                              export_texcoords=True, export_vertex_color='NONE')
    INFO['glb_bytes'] = os.path.getsize(glb)
with open(os.path.join(args.out, NAME + '.json'), 'w') as f:
    json.dump(INFO, f, indent=1)
print(f'[{NAME}] {json.dumps(INFO)}')

# ------------------------------------------------------------------------------------------------------------ render
if args.render:
    import render_preview
    render_preview.render(scene, objs, os.path.join(args.out, NAME), INFO, clay=args.geom,
                          props_dir=os.environ.get('SAVANNA_PROPS', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'props', 'out')))
print(f'[{NAME}] done in {time.time() - t0:.1f}s')
