"""Seeded jungle kit for the Mistfang Karst biome (run with Blender's Python: bpy 5.x).

The same stages as Khadrel's hand-built pipeline, written fresh for this game:
  1. build   closed faceted solids in bmesh, every face tagged with a material slot, a part id and a node group
  2. unwrap  one unique atlas per asset (uniform texel density)
  3. bake    Cycles bakes per texel: slot + part (emit), world position, world normal, ambient occlusion and sky light
  4. paint   numpy turns the bake into palette pixels (jungle_paint.py): per-part tone, slot pattern, wear, top light, dither
  5. export  one glb per asset, nodes split by group (shell / roof / wheel) so a viewer can lift the roof off,
             plus <name>.json: sizes, markers, colliders and the room plan (where the shared furniture stands)

Every asset comes from one seed, so the same seed always builds the same model.

usage: python jungle_kit.py --asset stilthouse --seed sky-1 --out out/ [--size 2048] [--render] [--samples 16]
assets: stilthouse, longhouse, granary, shrine, waterwheel, emergent, banyan, bamboo, banana, taro, treefern, karst, boulders
"""
import argparse, math, os, random, sys, time, zlib, json
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector

ap = argparse.ArgumentParser()
ap.add_argument('--asset', default='stilthouse')
ap.add_argument('--seed', default='sky-1')
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
SLOTS = ['weave', 'thatch', 'wood', 'plank', 'bamboo', 'stone', 'moss', 'bark', 'leaf', 'frond', 'clay', 'cloth', 'rope',
         'lacquer', 'ash', 'root', 'dry', 'ember']
SI = {s: i for i, s in enumerate(SLOTS)}
FLAT = {'ember'}  # glow slots stay a flat material, out of the atlas
bm = bmesh.new()
L_SLOT = bm.faces.layers.int.new('slot')
L_PART = bm.faces.layers.int.new('part')
L_GRP = bm.faces.layers.int.new('grp')
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


def quad(a, b, c, d, slot):
    vs = [bm.verts.new(p) for p in (a, b, c, d)]
    f = bm.faces.new(vs)
    tag([f], slot)
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



# ------------------------------------------------------------------------------------------------- more build helpers
COLS = []      # solid boxes for the page's physics, in three.js coordinates: [cx, cy, cz, sx, sy, sz, yaw, tilt]
SURF = []      # surfaces the page fills with loose props: [type, cx, cy, cz, yaw, width, depth]


def to3(v):
    return [round(v[0], 3), round(v[2], 3), round(-v[1], 3)]


def collide(center, size, rot=0.0, tilt=0.0):
    """Record a solid box (Blender centre and size, turned rot about Z, then tilted about its own X)."""
    c = to3(center)
    COLS.append(c + [round(size[0], 3), round(size[2], 3), round(size[1], 3), round(rot, 4), round(tilt, 4)])


def sbox(center, size, slot, rot=0.0, solid=True):
    """A box that is drawn and, unless told otherwise, solid for the walker."""
    box(center, size, slot, rot)
    if solid:
        collide(center, size, rot)


def surface(kind, center, w, d, rot=0.0):
    SURF.append([kind] + to3(center) + [round(rot, 4), round(w, 3), round(d, 3)])


def slab(poly, thick, slot, down=None):
    """A planar polygon given a thickness: the polygon is the top face, the copy is pushed along -normal (or `down`)."""
    pts = [Vector(p) for p in poly]
    n = (pts[1] - pts[0]).cross(pts[2] - pts[0]).normalized()
    off = (Vector(down).normalized() if down is not None else -n) * thick
    top = [bm.verts.new(p) for p in pts]
    bot = [bm.verts.new(p + off) for p in pts]
    fs = [bm.faces.new(top), bm.faces.new(list(reversed(bot)))]
    k = len(pts)
    for i in range(k):
        j = (i + 1) % k
        fs.append(bm.faces.new((top[j], top[i], bot[i], bot[j])))
    tag(fs, slot)
    return fs


def post(x, y, z0, z1, r, rng, slot='wood', segs=7, lean=0.0):
    pts = [Vector((x, y, z0)), Vector((x + lean * 0.5, y, (z0 + z1) / 2)), Vector((x + lean, y, z1))]
    return tube(pts, [r * 1.06, r, r * 0.94], slot, segs=segs, spin=rng.uniform(0, 1))


def leaf_quad(base, direction, length, width, up, slot, fold=0.25, droop=0.0):
    """A lance-shaped leaf: base, two shoulders and the tip, folded along its midrib (two triangles each side)."""
    d = Vector(direction).normalized()
    side = d.cross(Vector(up)).normalized()
    if side.length < 1e-4:
        side = Vector((1, 0, 0))
    nrm = side.cross(d).normalized()
    b = Vector(base)
    mid = b + d * length * 0.45 + nrm * width * fold
    tip = b + d * length + Vector((0, 0, -droop * length))
    l = b + d * length * 0.42 + side * width * 0.5
    r = b + d * length * 0.42 - side * width * 0.5
    vb, vm, vt, vl, vr = (bm.verts.new(p) for p in (b, mid, tip, l, r))
    fs = [bm.faces.new((vb, vl, vm)), bm.faces.new((vl, vt, vm)), bm.faces.new((vb, vm, vr)), bm.faces.new((vm, vt, vr))]
    tag(fs, slot)
    return fs


def strip_leaf(base, direction, length, width, rng, slot, segs=8, arch=0.35, tear=0.0, twist=0.0, heart=0.0):
    """A long blade (banana, taro, frond): a midrib curve with two halves, each segment its own quad so tears can open."""
    d = Vector(direction).normalized()
    hz = Vector((d.x, d.y, 0))
    hz = hz.normalized() if hz.length > 1e-4 else Vector((1, 0, 0))
    side = hz.cross(Vector((0, 0, 1))).normalized()
    pts, wid = [], []
    for i in range(segs + 1):
        t = i / segs
        # the midrib rises along `direction` and bends down with the leaf's weight
        p = Vector(base) + d * length * t + Vector((0, 0, -arch * length * t * t))
        pts.append(p)
        if heart > 0:
            w = width * (math.sin(math.pi * min(1, t * 1.15)) ** 0.7 if t > 0.02 else 0.15) * (1 - t * 0.35)
        else:
            w = width * math.sin(math.pi * min(1.0, 0.08 + t * 0.95)) ** 0.6
        wid.append(max(w, 0.01))
    fs = []
    for sgn in (1, -1):
        for i in range(segs):
            a, b2 = pts[i], pts[i + 1]
            tw = twist * (i / segs) * sgn
            cup = Vector((0, 0, 0.08 * width))
            sa = side * sgn * wid[i] * 0.5 + Vector((0, 0, tw))
            sb = side * sgn * wid[i + 1] * 0.5 + Vector((0, 0, tw))
            torn = tear > 0 and i > 1 and rng.random() < tear
            sag = Vector((0, 0, -0.18 * wid[i])) if torn else Vector((0, 0, 0))
            gap = d * (0.012 * length if torn else 0)
            q = [a + gap, b2 - gap, b2 + sb + cup + sag, a + sa + cup + sag]
            vs = [bm.verts.new(p) for p in q]
            fs.append(bm.faces.new(vs if sgn > 0 else list(reversed(vs))))
    if heart > 0:
        # the two lobes of a heart leaf hang back past the petiole
        for sgn in (1, -1):
            lob = [pts[0], pts[0] + side * sgn * width * 0.42 - d * width * 0.45 + Vector((0, 0, -0.1 * width)), pts[1] + side * sgn * wid[1] * 0.5]
            vs = [bm.verts.new(p) for p in lob]
            fs.append(bm.faces.new(vs if sgn > 0 else list(reversed(vs))))
    tag(fs, slot)
    return pts


def sag_curve(a, b, sag, n=8, wob=0.0, rng=None):
    a, b = Vector(a), Vector(b)
    out = []
    for i in range(n + 1):
        t = i / n
        p = a.lerp(b, t) + Vector((0, 0, -sag * 4 * t * (1 - t)))
        if wob and rng and 0 < i < n:
            p += Vector((rng.uniform(-wob, wob), rng.uniform(-wob, wob), 0))
        out.append(p)
    return out


def bezier(p0, p1, p2, n):
    p0, p1, p2 = Vector(p0), Vector(p1), Vector(p2)
    return [(1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t * t * p2 for t in (i / n for i in range(n + 1))]


def leaf_mass(center, radii, rng, n_leaf=40, slot='leaf', subdiv=2, leaf_len=0.7):
    """A crown clump: a faceted core with lance leaves standing out of its skin, so the edge reads as leaves, not a ball."""
    blob(center, radii, slot, rng, subdiv=subdiv, rough=0.28)
    c = Vector(center)
    for _ in range(n_leaf):
        z = rng.uniform(-0.55, 1.0)
        a = rng.uniform(0, 2 * math.pi)
        r = math.sqrt(max(0.0, 1 - z * z))
        dirn = Vector((r * math.cos(a), r * math.sin(a), z))
        base = c + Vector((dirn.x * radii[0] * 0.86, dirn.y * radii[1] * 0.86, dirn.z * radii[2] * 0.86))
        out = (dirn + Vector((0, 0, -0.35))).normalized()
        leaf_quad(base, out, leaf_len * rng.uniform(0.75, 1.3), leaf_len * 0.32, (0, 0, 1), slot, fold=0.18, droop=0.25)


# ------------------------------------------------------------------------------------------------------ the stilt house
# A house raised on hardwood posts above the wet season and the snakes: a woven bamboo room on a plank floor, a tall hip
# roof of palm-leaf thatch that comes down low, with smoke vents (gablets) under the ridge at both ends and carved horns
# crossing over them. The door is at one end, under the roof, onto a covered porch, and a stair runs down to the ground.
# Inside, a clay hearth box sits in the floor with a smoke rack hanging over it; the smoke leaves by the gablets. The
# furniture is the shared set (props thread), placed by a room planner that keeps the door path and the hearth clear.

FURN = {   # the shared furniture: footprint along the wall, depth out from the wall, height (props.json, Blender axes)
    'bed': (2.01, 0.95, 0.85), 'table': (1.5, 0.8, 0.76), 'side_table': (0.5, 0.5, 0.68), 'chair': (0.46, 0.44, 0.95),
    'stool': (0.36, 0.36, 0.46), 'bench': (1.4, 0.32, 0.48), 'shelf': (0.93, 0.365, 1.6), 'bookshelf': (1.06, 0.35, 2.0),
    'cupboard': (1.03, 0.509, 0.9), 'wardrobe': (1.18, 0.63, 2.02), 'drawers': (0.93, 0.509, 1.0), 'desk': (1.1, 0.6, 1.02),
    'peg_rack': (1.0, 0.172, 0.33), 'bottle_rack': (0.6, 0.315, 0.62), 'chest': (0.9, 0.55, 0.6), 'trunk': (1.0, 0.6, 0.6),
}
TALL = {'shelf', 'bookshelf', 'wardrobe'}


def plan_room(rng, x0, x1, y0, y1, fz, door, windows, keep_clear, wants):
    """Stand furniture along the inside of the walls. door / windows: (wall, t0, t1) spans; keep_clear: boxes
    (x0, y0, x1, y1). Each piece stands with its back to a wall, facing the room. Returns [(id, x, y, rot), ...]."""
    walls = {   # name: (start, along, inward normal, length)
        'S': (Vector((x0, y0, fz)), Vector((1, 0, 0)), Vector((0, 1, 0)), x1 - x0),
        'N': (Vector((x1, y1, fz)), Vector((-1, 0, 0)), Vector((0, -1, 0)), x1 - x0),
        'W': (Vector((x0, y1, fz)), Vector((0, -1, 0)), Vector((1, 0, 0)), y1 - y0),
        'E': (Vector((x1, y0, fz)), Vector((0, 1, 0)), Vector((-1, 0, 0)), y1 - y0),
    }
    placed, boxes = [], [tuple(b) for b in keep_clear]

    def free(bx):
        for b in boxes:
            if bx[0] < b[2] and bx[2] > b[0] and bx[1] < b[3] and bx[3] > b[1]:
                return False
        return True

    for fid in wants:
        L, Dp, Ht = FURN[fid]
        if fid == 'bed':
            L, Dp = Dp, L          # a bed stands head to the wall
        tries = []
        for wname, (s, al, nin, wl) in walls.items():
            for k in range(40):
                t = rng.uniform(0.05, wl - L - 0.05) if wl - L > 0.1 else None
                if t is None:
                    break
                tries.append((wname, t))
        rng.shuffle(tries)
        for wname, t in tries:
            s, al, nin, wl = walls[wname]
            # doors block every piece; windows block tall pieces only
            bad = False
            for (wn, a, b) in door:
                if wn == wname and t < b + 0.25 and t + L > a - 0.25:
                    bad = True
            if fid in TALL:
                for (wn, a, b) in windows:
                    if wn == wname and t < b + 0.1 and t + L > a - 0.1:
                        bad = True
            if bad:
                continue
            c = s + al * (t + L / 2) + nin * (Dp / 2 + 0.04)
            hx = abs(al.x) * L / 2 + abs(nin.x) * Dp / 2
            hy = abs(al.y) * L / 2 + abs(nin.y) * Dp / 2
            bx = (c.x - hx - 0.04, c.y - hy - 0.04, c.x + hx + 0.04, c.y + hy + 0.04)
            if not free(bx):
                continue
            # the furniture's front faces Blender -Y (three.js +Z): turn it so the front looks along the inward normal
            rot = math.atan2(nin.y, nin.x) - math.atan2(-1, 0)
            if fid == 'bed':
                rot = math.atan2(nin.y, nin.x) - math.atan2(1, 0)   # the bed's head is at Blender +Y
            placed.append((fid, c.x, c.y, rot))
            boxes.append(bx)
            break
    return placed


def roof_planes(xe0, xe1, Ye, ze, s, gdrop):
    """Hip roof with gablets: eave rectangle x xe0..xe1, y -Ye..Ye at height ze, every plane at slope s; the hips stop
    `gdrop` under the ridge where an upright vent triangle (gablet) lets the smoke out."""
    zr = ze + Ye * s
    zg = zr - gdrop
    yg = gdrop / s
    xg0 = xe0 + (zg - ze) / s
    xg1 = xe1 - (zg - ze) / s
    front = [(xe0, -Ye, ze), (xe1, -Ye, ze), (xg1, -yg, zg), (xg1, 0, zr), (xg0, 0, zr), (xg0, -yg, zg)]
    back = [(xe1, Ye, ze), (xe0, Ye, ze), (xg0, yg, zg), (xg0, 0, zr), (xg1, 0, zr), (xg1, yg, zg)]
    end0 = [(xe0, Ye, ze), (xe0, -Ye, ze), (xg0, -yg, zg), (xg0, yg, zg)]
    end1 = [(xe1, -Ye, ze), (xe1, Ye, ze), (xg1, yg, zg), (xg1, -yg, zg)]
    return dict(zr=zr, zg=zg, yg=yg, xg0=xg0, xg1=xg1, faces=[front, back, end0, end1])


def roof_z(x, y, xe0, xe1, Ye, ze, s):
    """Height of the roof's outer skin over (x, y)."""
    return ze + s * min(Ye - abs(y), x - xe0, xe1 - x)


def wall_run(a, b, z0, z1, T, openings, slot, rng, solid=True):
    """A straight wall from a to b (Blender xy), z0..z1, thickness T, with rectangular openings (t0, t1, sill, head),
    t measured from a. Built as boxes, so every opening shows the wall's full thickness."""
    a, b = Vector((a[0], a[1], 0)), Vector((b[0], b[1], 0))
    L = (b - a).length
    al = (b - a).normalized()
    rot = math.atan2(al.y, al.x)
    cuts = sorted(openings)
    t = 0.0
    pieces = []
    for (t0, t1, sill, head) in cuts:
        if t0 > t:
            pieces.append((t, t0, z0, z1))
        if sill > 0.001:
            pieces.append((t0, t1, z0, z0 + sill))
        if z0 + head < z1:
            pieces.append((t0, t1, z0 + head, z1))
        t = t1
    if t < L:
        pieces.append((t, L, z0, z1))
    for (u0, u1, h0, h1) in pieces:
        if u1 - u0 < 0.01 or h1 - h0 < 0.01:
            continue
        c = a + al * ((u0 + u1) / 2)
        sbox((c.x, c.y, (h0 + h1) / 2), (u1 - u0, T, h1 - h0), slot, rot, solid)
    # every opening gets a timber frame flush with both faces
    for (t0, t1, sill, head) in cuts:
        for u in (t0, t1):
            c = a + al * u
            box((c.x, c.y, z0 + (sill + head) / 2), (0.07, T + 0.04, head - sill), 'wood', rot)
        c = a + al * ((t0 + t1) / 2)
        box((c.x, c.y, z0 + head + 0.035), (t1 - t0 + 0.14, T + 0.04, 0.07), 'wood', rot)
        if sill > 0.001:
            box((c.x, c.y, z0 + sill - 0.03), (t1 - t0 + 0.14, T + 0.08, 0.06), 'wood', rot)


def stilthouse(variant='house'):
    rng = stream('shape')
    great = variant == 'great'
    W = rng.uniform(11.5, 13.0) if great else rng.uniform(6.2, 7.6)      # room length (x)
    D = rng.uniform(5.0, 5.6) if great else rng.uniform(4.4, 5.0)        # room depth (y)
    Fz = rng.uniform(1.95, 2.25)                                         # floor height
    Vd = rng.uniform(1.5, 1.9)                                           # porch depth, at the -x end
    ov = 0.7
    s = rng.uniform(1.15, 1.32)                                          # roof slope
    ze = Fz + 1.78                                                       # eave height all round
    Hw = (ze + ov * s) - Fz                                              # side walls meet the roof's underside
    T = 0.07
    xr0, xr1 = -W / 2, W / 2
    yr0, yr1 = -D / 2, D / 2
    # posts: a grid on the room's edge, plus the porch's outer pair
    nx = 5 if great else 3
    pxs = [xr0 + (W) * i / (nx) for i in range(nx + 1)]
    group('shell')
    part('footings')
    for x in pxs + [xr0 - Vd]:
        for y in (yr0, yr1):
            blob((x, y, 0.06), (0.32, 0.3, 0.2), 'stone', rng, subdiv=1, rough=0.2, flat_bottom=-0.15)
    part('posts')
    for x in pxs:
        for y in (yr0, yr1):
            post(x, y, 0.15, Fz + Hw + 0.05, 0.13, rng)
            collide((x, y, (Fz) / 2), (0.26, 0.26, Fz))
    for y in (yr0, yr1):
        post(xr0 - Vd, y, 0.15, ze - 0.05, 0.11, rng)
        collide((xr0 - Vd, y, Fz / 2), (0.22, 0.22, Fz))
    # under-floor middle posts and cross braces
    for x in pxs[1:-1] if len(pxs) > 2 else []:
        post(x, 0, 0.1, Fz - 0.12, 0.1, rng)
    part('braces')
    for i in range(len(pxs) - 1):
        for y in (yr0, yr1):
            a, b = Vector((pxs[i], y, 0.35)), Vector((pxs[i + 1], y, Fz - 0.25))
            if i % 2:
                a.z, b.z = b.z, a.z
            tube([a, b], [0.045, 0.045], 'bamboo', segs=5)
    # floor: beams on the posts, joists across, a plank deck
    part('beams')
    for y in (yr0, yr1):
        box((0, y, Fz - 0.2), (W + 0.6, 0.16, 0.18), 'wood')
    for x in pxs:
        box((x, 0, Fz - 0.08), (0.12, D + 0.5, 0.1), 'wood')
    part('floor')
    sbox((0, 0, Fz), (W + 0.04, D + 0.04, 0.07), 'plank')
    # the porch: one step down, plank deck, a rail on its two open sides, the stair down the front
    part('porch')
    pz = Fz - 0.16
    sbox((xr0 - Vd / 2, 0, pz), (Vd, D, 0.07), 'plank')
    box((xr0 - Vd / 2, yr0, pz - 0.14), (Vd + 0.3, 0.14, 0.16), 'wood')
    box((xr0 - Vd / 2, yr1, pz - 0.14), (Vd + 0.3, 0.14, 0.16), 'wood')
    sbox((xr0 - 0.03, 0, Fz - 0.08), (0.08, D, 0.16), 'wood')      # the step up into the room is the sill beam
    stair_w = 1.0
    stair_y = yr0 + 0.25 + stair_w / 2 + rng.uniform(0, 0.5)
    rail_h = 0.9
    part('rail')
    xo = xr0 - Vd
    # rail along the open end (x = xo) with a gap for the stair? the stair comes off the front edge, so the end rail is whole
    for (a, b) in [((xo, yr0), (xo, yr1)), ((xo, yr1), (xr0, yr1))]:
        A, B = Vector((a[0], a[1], pz + rail_h)), Vector((b[0], b[1], pz + rail_h))
        tube([A, B], [0.045, 0.045], 'bamboo', segs=6)
        n = int((B - A).length / 0.32)
        for k in range(1, n):
            q = A.lerp(B, k / n)
            tube([Vector((q.x, q.y, pz + 0.03)), q], [0.025, 0.025], 'bamboo', segs=5)
        c = (A + B) / 2
        L = (B - A).length
        collide((c.x, c.y, pz + rail_h / 2 + 0.03), (L if abs(B.x - A.x) > 0.1 else 0.1, L if abs(B.y - A.y) > 0.1 else 0.1, rail_h))
    # front rail with the stair gap
    A, B = Vector((xo, yr0, pz + rail_h)), Vector((xr0, yr0, pz + rail_h))
    g0, g1 = xo + 0.15, xo + 0.15 + stair_w
    for (u0, u1) in ((xo, g0), (g1, xr0)):
        if u1 - u0 < 0.1:
            continue
        tube([Vector((u0, yr0, pz + rail_h)), Vector((u1, yr0, pz + rail_h))], [0.045, 0.045], 'bamboo', segs=6)
        for k in range(1, max(2, int((u1 - u0) / 0.32))):
            q = u0 + (u1 - u0) * k / max(2, int((u1 - u0) / 0.32))
            tube([Vector((q, yr0, pz + 0.03)), Vector((q, yr0, pz + rail_h))], [0.025, 0.025], 'bamboo', segs=5)
        collide(((u0 + u1) / 2, yr0, pz + rail_h / 2), (u1 - u0, 0.1, rail_h))
    # the stair: two stringers, open treads, down along -y from the porch's front edge
    part('stair')
    rise = pz + 0.035
    nst = max(6, round(rise / 0.2))
    run = rise / math.tan(math.radians(36))
    sx = (g0 + g1) / 2
    y_top = yr0 - 0.05
    y_bot = y_top - run
    for xs in (g0 + 0.05, g1 - 0.05):
        tube([Vector((xs, y_top, pz)), Vector((xs, y_bot, 0.0))], [0.06, 0.06], 'wood', segs=6)
    for k in range(1, nst):
        t = k / nst
        box((sx, y_top - run * t + 0.02, pz - rise * t + 0.02), (stair_w - 0.04, 0.26, 0.05), 'plank')
    tilt = math.atan2(rise, run)
    # the walker climbs a smooth ramp laid over the treads
    collide((sx, (y_top + y_bot) / 2, rise / 2 - 0.06), (stair_w, math.hypot(run, rise) + 0.1, 0.08), 0.0, tilt)
    for xs in (g0, g1):
        tube([Vector((xs, y_top, pz + rail_h)), Vector((xs, y_bot + 0.15, rail_h * 0.95))], [0.035, 0.035], 'bamboo', segs=5)
        tube([Vector((xs, y_bot + 0.15, 0.0)), Vector((xs, y_bot + 0.15, rail_h * 0.95))], [0.03, 0.03], 'bamboo', segs=5)
    # walls: the door is in the porch end (x = xr0), windows on the long sides and the far end
    part('walls')
    dw = 1.0
    door_c = rng.uniform(-0.4, 0.4) * (D / 2 - 0.9)
    doors = [('W', D / 2 - door_c - dw / 2, D / 2 - door_c + dw / 2)]
    nwin = (4 if great else 2)
    wins_S, wins_N = [], []
    for k in range(nwin):
        c = xr0 + W * (k + 0.5) / nwin + rng.uniform(-0.3, 0.3)
        ww = rng.uniform(0.75, 0.95)
        wins_S.append((c - xr0 - ww / 2, c - xr0 + ww / 2))
        c2 = xr0 + W * (k + 0.5) / nwin + rng.uniform(-0.3, 0.3)
        wins_N.append((xr1 - c2 - ww / 2, xr1 - c2 + ww / 2))
    win_E = [(D / 2 - 0.45, D / 2 + 0.45)]
    sill, head = 0.78, 1.62
    wall_run((xr0, yr0), (xr1, yr0), Fz + 0.035, Fz + Hw, T, [(a, b, sill, head) for a, b in wins_S], 'weave', rng)
    wall_run((xr1, yr1), (xr0, yr1), Fz + 0.035, Fz + Hw, T, [(a, b, sill, head) for a, b in wins_N], 'weave', rng)
    wall_run((xr1, yr0), (xr1, yr1), Fz + 0.035, Fz + Hw, T, [(a, b, sill, head) for a, b in win_E], 'weave', rng)
    wall_run((xr0, yr1), (xr0, yr0), Fz + 0.035, Fz + Hw, T, [(doors[0][1], doors[0][2], 0.0, 1.95)], 'weave', rng)
    # gable panels above the end walls, up to the roof's underside (the hip planes leave a tall triangle at the porch end)
    xe0, xe1 = xr0 - Vd - ov, xr1 + ov
    Ye = D / 2 + ov
    RP = roof_planes(xe0, xe1, Ye, ze, s, rng.uniform(0.9, 1.15))
    rt = 0.26
    for xw in (xr0, xr1):
        top = Fz + Hw
        pts = []
        for k in range(13):
            y = yr0 + D * k / 12
            pts.append((y, roof_z(xw, y, xe0, xe1, Ye, ze, s) - rt * 1.25))
        if max(z for _, z in pts) > top + 0.15:
            poly = [(xw, yr1, top)] + [(xw, y, max(z, top)) for (y, z) in reversed(pts)] + [(xw, yr0, top)]
            poly = [p for i, p in enumerate(poly) if i == 0 or (Vector(p) - Vector(poly[i - 1])).length > 0.01]
            # a fan of quads (the outline is not convex everywhere): one strip per column
            for k in range(12):
                (y0_, z0_), (y1_, z1_) = pts[k], pts[k + 1]
                if max(z0_, z1_) <= top + 0.02:
                    continue
                q = [(xw - T / 2, y0_, top), (xw - T / 2, y1_, top), (xw - T / 2, y1_, max(z1_, top)), (xw - T / 2, y0_, max(z0_, top))]
                slab(q, T, 'weave', down=(1, 0, 0))
    # wall plates on the side walls, tie beams across the room
    part('plates')
    for y in (yr0, yr1):
        box((0, y, Fz + Hw - 0.06), (W + 0.3, 0.16, 0.14), 'wood')
    for x in pxs:
        box((x, 0, Fz + Hw - 0.02), (0.14, D + 0.3, 0.14), 'wood')
    # shutters: woven flaps hinged at the head, propped open outwards on a stick
    part('shutters')
    for side, wins in (('S', wins_S), ('N', wins_N)):
        for (a, b) in wins:
            if side == 'S':
                x0_, x1_, y = xr0 + a, xr0 + b, yr0 - T / 2
                out = -1
            else:
                x0_, x1_, y = xr1 - b, xr1 - a, yr1 + T / 2
                out = 1
            hz = Fz + 0.035 + head + 0.07
            L = head - sill + 0.08
            ang = math.radians(rng.uniform(48, 62))
            pa = (x0_ - 0.04, y, hz)
            pb = (x1_ + 0.04, y, hz)
            dy, dz = out * L * math.sin(ang), -L * math.cos(ang)
            slab([pa, pb, (pb[0], y + dy, hz + dz), (pa[0], y + dy, hz + dz)], 0.035, 'weave')
            tube([Vector(((x0_ + x1_) / 2, y, Fz + 0.035 + sill)), Vector(((x0_ + x1_) / 2, y + dy * 0.95, hz + dz * 0.95))], [0.018, 0.018], 'bamboo', segs=4)
    # the door leaf, swung open against the porch side of the end wall
    part('door')
    dy0 = D / 2 - door_c - dw / 2
    yy = yr1 - dy0
    slab([(xr0 - 0.05, yy, Fz + 0.04), (xr0 - 0.05, yy, Fz + 1.92), (xr0 - 0.05 - 0.04, yy + 0.06, Fz + 1.92), (xr0 - 0.09, yy + 0.06, Fz + 0.04)], 0.0, 'plank') if False else None
    box((xr0 - 0.09, yy + dw / 2 + 0.06, Fz + 0.98), (0.05, dw - 0.06, 1.88), 'plank')
    # ---------------------------------------------------------------------------------------------- inside: the hearth
    part('hearth')
    hx = (xr0 + xr1) / 2 + (rng.uniform(-0.3, 0.6) if not great else 0)
    hearths = [hx] if not great else [xr0 + W * 0.3, xr0 + W * 0.72]
    for hxx in hearths:
        hs = 1.05
        for (cx, cy, sx_, sy_) in ((hxx, -hs / 2, hs + 0.1, 0.1), (hxx, hs / 2, hs + 0.1, 0.1), (hxx - hs / 2, 0, 0.1, hs), (hxx + hs / 2, 0, 0.1, hs)):
            sbox((cx, cy, Fz + 0.11), (sx_, sy_, 0.16), 'wood')
        box((hxx, 0, Fz + 0.09), (hs - 0.04, hs - 0.04, 0.12), 'clay')
        collide((hxx, 0, Fz + 0.09), (hs, hs, 0.14))
        part('ash')
        blob((hxx, 0, Fz + 0.15), (0.32, 0.28, 0.06), 'ash', rng, subdiv=2, rough=0.25)
        for k in range(3):
            a = k * 2 * math.pi / 3 + rng.uniform(-0.2, 0.2)
            blob((hxx + 0.27 * math.cos(a), 0.27 * math.sin(a), Fz + 0.2), (0.1, 0.09, 0.09), 'stone', rng, subdiv=1, rough=0.2)
        part('embers')
        for k in range(6):
            blob((hxx + rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12), Fz + 0.18), (0.05, 0.035, 0.025), 'ember', rng, subdiv=1, rough=0.3)
        part('logs')
        for k in range(3):
            a = k * 2 * math.pi / 3 + 0.5
            tube([Vector((hxx + 0.45 * math.cos(a), 0.45 * math.sin(a), Fz + 0.19)), Vector((hxx + 0.06 * math.cos(a), 0.06 * math.sin(a), Fz + 0.17))], [0.045, 0.04], 'wood', segs=6)
        surface('hearth', (hxx + 0.3, -0.3, Fz + 0.17), 0.3, 0.3)
        # the smoke rack: a bamboo grid hung on four cords from the tie beams, blackened by the smoke
        part('rack')
        rz_ = Fz + 1.95
        for k in range(6):
            u = -0.65 + 1.3 * k / 5
            tube([Vector((hxx + u, -0.65, rz_)), Vector((hxx + u, 0.65, rz_))], [0.022, 0.022], 'bamboo', segs=5)
            tube([Vector((hxx - 0.68, u, rz_ + 0.04)), Vector((hxx + 0.68, u, rz_ + 0.04))], [0.022, 0.022], 'bamboo', segs=5)
        for (cx, cy) in ((-0.62, -0.62), (0.62, -0.62), (0.62, 0.62), (-0.62, 0.62)):
            tube([Vector((hxx + cx, cy, rz_)), Vector((hxx + cx * 0.8, cy * 1.0, Fz + Hw + 0.6))], [0.01, 0.01], 'rope', segs=4)
        # bundles of maize and chillies drying on the rack
        part('drying')
        for k in range(5):
            c = Vector((hxx + rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rz_ + 0.09))
            blob(c, (0.16, 0.06, 0.05), rng.choice(['dry', 'lacquer']), rng, subdiv=1, rough=0.2)
    # ------------------------------------------------------------------------------------------------------ the roof
    group('roof')
    part('thatch')
    for poly in RP['faces']:
        slab(poly, rt, 'thatch')
    # a ragged eave fringe: the leaf ends of the lowest course hang below the eave
    part('fringe')
    eave = [(xe0, -Ye), (xe1, -Ye), (xe1, Ye), (xe0, Ye)]
    for i in range(4):
        (ax, ay), (bx_, by) = eave[i], eave[(i + 1) % 4]
        L = math.hypot(bx_ - ax, by - ay)
        n = int(L / 0.11)
        al = Vector(((bx_ - ax) / L, (by - ay) / L, 0))
        outn = Vector((al.y, -al.x, 0))
        for row in range(2):
            for k in range(n):
                u0 = L * (k + 0.5 * row) / n - 0.04
                u1 = u0 + L / n * rng.uniform(1.2, 1.9)
                u0, u1 = max(u0, 0), min(u1, L)
                if u1 - u0 < 0.03:
                    continue
                p0 = Vector((ax, ay, ze)) + al * u0 - outn * (0.15 + 0.1 * row) + Vector((0, 0, 0.15 * s * (1 + row) * 0.7))
                p1 = Vector((ax, ay, ze)) + al * u1 - outn * (0.15 + 0.1 * row) + Vector((0, 0, 0.15 * s * (1 + row) * 0.7))
                drop = rng.uniform(0.1, 0.34)
                pm = (p0 + p1) / 2 + al * rng.uniform(-0.04, 0.04) + outn * (0.2 + 0.05 * row) + Vector((0, 0, -drop - rt * 0.4))
                vs = [bm.verts.new(p) for p in (p0, p1, pm)]
                tag([bm.faces.new(vs)], 'thatch')
    # battens: bamboo poles lashed across the thatch to hold it down in the monsoon wind
    part('battens')
    for frac in (0.3, 0.62):
        zz = ze + (RP['zr'] - ze) * frac
        for sy in (-1, 1):
            y = sy * (Ye - (zz - ze) / s)
            xa = xe0 + (zz - ze) / s + 0.2
            xb = xe1 - (zz - ze) / s - 0.2
            tube([Vector((xa, y, zz + 0.06)), Vector((xb, y, zz + 0.06))], [0.06, 0.06], 'bamboo', segs=6)
        for sx_, xx in ((-1, xe0 + (zz - ze) / s), (1, xe1 - (zz - ze) / s)):
            yy = Ye - (zz - ze) / s - 0.2
            tube([Vector((xx, -yy, zz + 0.06)), Vector((xx, yy, zz + 0.06))], [0.06, 0.06], 'bamboo', segs=6)
    # the gablet vents: slatted bamboo screens set back in the upright triangles
    part('vents')
    for xg, sgn in ((RP['xg0'], -1), (RP['xg1'], 1)):
        zg, zr, yg = RP['zg'], RP['zr'], RP['yg']
        for k in range(7):
            y = -yg + 2 * yg * (k + 0.5) / 7
            zt = zg + (zr - zg) * (1 - abs(y) / yg)
            tube([Vector((xg - sgn * 0.12, y, zg - rt * 0.6)), Vector((xg - sgn * 0.12, y, zt - rt * 0.8))], [0.02, 0.02], 'bamboo', segs=4)
        # carved horns crossing over the vent, the house's mark
        part('horns')
        hl = rng.uniform(1.0, 1.4)
        for sy in (-1, 1):
            a = Vector((xg, sy * yg * 1.05, zg - 0.05))
            b = Vector((xg + sgn * 0.08, -sy * 0.15, zr + 0.25))
            c = b + Vector((sgn * 0.25, -sy * hl * 0.45, hl * 0.85))
            pts = bezier(a, b, c, 6)
            tube(pts, [0.07, 0.07, 0.065, 0.06, 0.05, 0.035, 0.015], 'lacquer' if variant == 'great' else 'wood', segs=5)
    # ridge cap: a bound bundle along the ridge
    part('ridge')
    zr = RP['zr']
    tube([Vector((RP['xg0'] - 0.2, 0, zr + 0.08)), Vector((RP['xg1'] + 0.2, 0, zr + 0.08))], [0.13, 0.13], 'thatch', segs=6)
    nb = int((RP['xg1'] - RP['xg0']) / 0.7)
    for k in range(nb + 1):
        x = RP['xg0'] + (RP['xg1'] - RP['xg0']) * k / max(nb, 1)
        tube([Vector((x - 0.04, 0, zr + 0.08)), Vector((x + 0.04, 0, zr + 0.08))], [0.15, 0.15], 'rope', segs=6)
    # hip caps: bound bundles of thatch down every hip, from the gablet foot to the eave corner
    part('hips')
    for (cx_, xg_) in ((xe0, RP['xg0']), (xe1, RP['xg1'])):
        for sy in (-1, 1):
            A = Vector((cx_, sy * Ye, ze + 0.05))
            B = Vector((xg_, sy * RP['yg'], RP['zg'] + 0.05))
            tube([A, B], [0.11, 0.11], 'thatch', segs=6)
            for kk in range(1, 5):
                q = A.lerp(B, kk / 5)
                tube([q - (B - A).normalized() * 0.04, q + (B - A).normalized() * 0.04], [0.13, 0.13], 'rope', segs=6)
    # rafters and purlins under the thatch: what you see when you look up from inside
    part('rafters')
    under = rt * 1.1 + 0.05
    for x in [xr0 + (xr1 - xr0) * k / int(W / 0.75) for k in range(int(W / 0.75) + 1)]:
        for sy in (-1, 1):
            a = Vector((x, sy * (D / 2 + 0.05), roof_z(x, sy * (D / 2), xe0, xe1, Ye, ze, s) - under))
            zt = roof_z(x, 0.0, xe0, xe1, Ye, ze, s) - under
            b = Vector((x, sy * 0.05, zt))
            if b.z - a.z > 0.2:
                tube([a, b], [0.045, 0.04], 'bamboo', segs=5)
    for k in range(1, 5):
        frac = k / 5
        for sy in (-1, 1):
            y = sy * (D / 2) * (1 - frac)
            xa = max(xe0 + (Ye - abs(y)) + 0.1, xr0 - Vd)
            xb = min(xe1 - (Ye - abs(y)) - 0.1, xr1 + 0.1)
            if xb - xa < 0.5:
                continue
            za = roof_z((xa + xb) / 2, y, xe0, xe1, Ye, ze, s) - under - 0.06
            tube([Vector((xa, y, za)), Vector((xb, y, za))], [0.04, 0.04], 'bamboo', segs=5)
    # king posts from the tie beams up to the ridge
    for x in pxs[1:-1] if len(pxs) > 2 else [0.0]:
        tube([Vector((x, 0, Fz + Hw + 0.05)), Vector((x, 0, roof_z(x, 0, xe0, xe1, Ye, ze, s) - under))], [0.06, 0.06], 'wood', segs=6)
    # ------------------------------------------------------------------------------------------------- room plan
    group('shell')
    clear = [(xr0 - 0.1, D / 2 - door_c - dw / 2 - 0.35 - D / 2, xr0 + 1.4, D / 2 - door_c + dw / 2 + 0.35 - D / 2)]
    # (the door's y span in room coordinates: the W wall runs from yr1 to yr0, so t maps to y = yr1 - t)
    dy_a, dy_b = yr1 - doors[0][2], yr1 - doors[0][1]
    clear = [(xr0 - 0.1, dy_a - 0.35, xr0 + 1.5, dy_b + 0.35)]
    for hxx in hearths:
        clear.append((hxx - 0.95, -0.95, hxx + 0.95, 0.95))
    wins_plan = [('S', a, b) for a, b in wins_S] + [('N', a, b) for a, b in wins_N] + [('E', a, b) for a, b in win_E]
    prng = stream('room')
    if great:
        wants = ['bed', 'bed', 'wardrobe', 'table', 'bench', 'bench', 'bookshelf', 'cupboard', 'drawers', 'desk', 'chair',
                 'shelf', 'chest', 'trunk', 'side_table', 'stool', 'stool', 'stool', 'bottle_rack', 'peg_rack']
    else:
        pool = ['wardrobe', 'cupboard', 'drawers', 'desk', 'bookshelf', 'chest', 'trunk', 'side_table', 'bottle_rack', 'bench']
        prng.shuffle(pool)
        wants = ['bed', 'table', 'shelf', 'stool', 'stool'] + pool[:5] + ['chair', 'peg_rack']
    furn = plan_room(prng, xr0 + T / 2, xr1 - T / 2, yr0 + T / 2, yr1 - T / 2, Fz + 0.035,
                     [('W', D / 2 - door_c - dw / 2 + 0.0, D / 2 - door_c + dw / 2)], wins_plan, clear,
                     [w for w in wants if w != 'peg_rack'])
    plan = [[fid, round(x, 3), round(Fz + 0.035, 3), round(-y, 3), round(r, 4)] for (fid, x, y, r) in furn]
    # stools that found no wall go round the table, and the rug lies in the middle of the free floor
    tables = [p for p in plan if p[0] == 'table']
    under_house = []
    for k in range(3):
        under_house.append([round(rng.uniform(xr0 + 0.6, xr1 - 0.6), 3), 0.0, round(-rng.uniform(yr0 + 0.6, yr1 - 0.6), 3)])
    surface('under', (0, 0, 0.0), W - 1.2, D - 1.2)
    surface('porch', (xr0 - Vd / 2, D * 0.25, pz + 0.035), Vd - 0.5, D * 0.4)
    eye = (xr0 + 0.4, door_c * -1 + 0.0, Fz + 1.6)
    return {'W': W, 'D': D, 'floor': Fz, 'Hw': Hw, 'porch': [xr0 - Vd, pz], 'eave': ze, 'ridge': RP['zr'],
            'roof': {'xe0': xe0, 'xe1': xe1, 'Ye': Ye, 'ze': ze, 's': s},
            'markers': {'eye': [xr0 + 0.5, -(yr1 - (doors[0][1] + doors[0][2]) / 2), Fz + 1.6], 'hearth': [hearths[0], 0, Fz + 0.2],
                        'hearths': [[h, 0, Fz + 0.2] for h in hearths], 'door': [xr0, yr1 - (doors[0][1] + doors[0][2]) / 2, Fz],
                        'stair_foot': [sx, y_bot - 0.4, 0.0]},
            'furniture': plan, 'windows': {'S': wins_S, 'N': wins_N, 'E': win_E}}


# ------------------------------------------------------------------------------------------------------- the granary
def granary():
    rng = stream('shape')
    W, D, Fz = rng.uniform(2.4, 2.9), rng.uniform(2.0, 2.4), rng.uniform(1.5, 1.7)
    group('shell')
    part('posts')
    for x in (-W / 2, W / 2):
        for y in (-D / 2, D / 2):
            blob((x, y, 0.05), (0.26, 0.24, 0.16), 'stone', rng, subdiv=1, rough=0.2, flat_bottom=-0.1)
            post(x, y, 0.1, Fz + 1.55, 0.11, rng)
            collide((x, y, Fz / 2), (0.24, 0.24, Fz))
            # rat guards: a wooden disc on every post under the floor
            lathe([(0.0, Fz - 0.45), (0.36, Fz - 0.42), (0.36, Fz - 0.38), (0.0, Fz - 0.36)], 10, 'wood', center=(x, y, 0))
    part('floor')
    sbox((0, 0, Fz), (W + 0.1, D + 0.1, 0.08), 'plank')
    for y in (-D / 2, D / 2):
        box((0, y, Fz - 0.12), (W + 0.4, 0.14, 0.14), 'wood')
    part('walls')
    T = 0.07
    H = 1.5
    wall_run((-W / 2, -D / 2), (W / 2, -D / 2), Fz + 0.04, Fz + H, T, [], 'weave', rng)
    wall_run((W / 2, D / 2), (-W / 2, D / 2), Fz + 0.04, Fz + H, T, [], 'weave', rng)
    wall_run((W / 2, -D / 2), (W / 2, D / 2), Fz + 0.04, Fz + H, T, [], 'weave', rng)
    wall_run((-W / 2, D / 2), (-W / 2, -D / 2), Fz + 0.04, Fz + H, T, [(D / 2 - 0.4, D / 2 + 0.4, 0.15, 1.3)], 'weave', rng)
    surface('store', (0.25, 0, Fz + 0.04), W - 0.9, D - 0.5)
    part('ladder')
    # a notched log ladder leaning on the door sill
    lad_top = Vector((-W / 2 - 0.15, 0, Fz + 0.15))
    lad_bot = Vector((-W / 2 - 1.25, 0, 0.0))
    tube([lad_bot, lad_top], [0.11, 0.09], 'wood', segs=7)
    n = 5
    for k in range(1, n + 1):
        p = lad_bot.lerp(lad_top, k / (n + 1))
        box((p.x + 0.03, 0, p.z + 0.04), (0.14, 0.2, 0.05), 'wood')
    collide(((lad_bot.x + lad_top.x) / 2, 0, (lad_bot.z + lad_top.z) / 2 - 0.05), (math.hypot(1.1, Fz + 0.15) + 0.1, 0.6, 0.08),
            0.0, 0.0)
    COLS[-1][6] = 0.0
    COLS[-1][7] = 0.0
    COLS.pop()   # too steep for the walker: the granary is looked into, not climbed
    group('roof')
    part('thatch')
    ze, s, ov = Fz + H - 0.25, 1.35, 0.55
    Ye = D / 2 + ov
    RP = roof_planes(-W / 2 - ov, W / 2 + ov, Ye, ze, s, 0.55)
    for poly in RP['faces']:
        slab(poly, 0.22, 'thatch')
    part('horns')
    for xg, sgn in ((RP['xg0'], -1), (RP['xg1'], 1)):
        for sy in (-1, 1):
            a = Vector((xg, sy * RP['yg'], RP['zg']))
            b = Vector((xg, 0, RP['zr'] + 0.2))
            c = b + Vector((sgn * 0.2, -sy * 0.35, 0.6))
            tube(bezier(a, b, c, 5), [0.05, 0.05, 0.045, 0.04, 0.03, 0.012], 'wood', segs=5)
    return {'W': W, 'D': D, 'floor': Fz, 'Hw': H, 'markers': {'door': [-W / 2, 0, Fz]}}


# ---------------------------------------------------------------------------------------------- the spirit shrine
def shrine():
    rng = stream('shape')
    group('shell')
    part('base')
    blob((0, 0, 0.1), (0.55, 0.5, 0.3), 'stone', rng, subdiv=2, rough=0.15, flat_bottom=0.0)
    collide((0, 0, 0.2), (0.9, 0.9, 0.4))
    part('post')
    post(0, 0, 0.3, 1.35, 0.09, rng, slot='lacquer')
    collide((0, 0, 0.9), (0.2, 0.2, 1.2))
    part('deck')
    box((0, 0, 1.38), (0.95, 0.75, 0.06), 'plank')
    for (x, y) in ((-0.42, -0.32), (0.42, -0.32), (0.42, 0.32), (-0.42, 0.32)):
        tube([Vector((x, y, 1.41)), Vector((x, y, 1.62))], [0.018, 0.018], 'lacquer', segs=4)
    part('house')
    box((0, 0.08, 1.72), (0.6, 0.45, 0.6), 'lacquer')
    box((0, -0.15, 1.66), (0.26, 0.02, 0.4), 'wood')
    surface('offering', (0, -0.3, 1.41), 0.8, 0.2)
    group('roof')
    part('roof')
    RP = roof_planes(-0.48, 0.48, 0.42, 1.98, 1.3, 0.2)
    for poly in RP['faces']:
        slab(poly, 0.06, 'thatch')
    for xg, sgn in ((RP['xg0'], -1), (RP['xg1'], 1)):
        for sy in (-1, 1):
            a = Vector((xg, sy * RP['yg'], RP['zg']))
            b = Vector((xg, 0, RP['zr'] + 0.08))
            c = b + Vector((sgn * 0.08, -sy * 0.14, 0.3))
            tube(bezier(a, b, c, 4), [0.025, 0.025, 0.02, 0.015, 0.006], 'lacquer', segs=4)
    # cloth streamers tied round the post
    part('cloth')
    for k in range(3):
        a = k * 2.1
        p0 = Vector((0.09 * math.cos(a), 0.09 * math.sin(a), 1.15))
        slab([p0, p0 + Vector((0.03 * math.cos(a + 1.5), 0.03 * math.sin(a + 1.5), 0)), p0 + Vector((0.2 * math.cos(a), 0.2 * math.sin(a), -0.55)),
              p0 + Vector((0.17 * math.cos(a), 0.17 * math.sin(a), -0.6))], 0.004, 'cloth')
    return {}


# --------------------------------------------------------------------------------------------- the bamboo water wheel
def waterwheel():
    rng = stream('shape')
    R = rng.uniform(2.1, 2.5)
    hub = R + 0.25
    group('shell')
    part('frame')
    for y in (-0.75, 0.75):
        for x in (-0.35, 0.35):
            tube([Vector((x * 1.6, y, -0.6)), Vector((x * 0.25, y, hub + 0.1))], [0.09, 0.08], 'wood', segs=6)
        box((0, y, hub + 0.05), (0.32, 0.2, 0.14), 'wood')
    # the trough on bamboo trestles: split bamboo running off to the fields
    part('trough')
    for k in range(5):
        x = 0.6 + k * 1.6
        for y in (-0.15, 0.15):
            tube([Vector((x, y + 0.9, -0.6)), Vector((x, 0.9, hub - 0.4 - k * 0.12))], [0.04, 0.04], 'bamboo', segs=5)
    tube([Vector((0.0, 0.9, hub - 0.3)), Vector((7.5, 0.9, hub - 0.95))], [0.13, 0.13], 'bamboo', segs=8)
    group('wheel')
    part('hub')
    tube([Vector((0, -0.95, hub)), Vector((0, 0.95, hub))], [0.12, 0.12], 'wood', segs=8)
    part('spokes')
    n = 16
    for y in (-0.55, 0.55):
        ring = []
        for k in range(n):
            a = 2 * math.pi * k / n
            ring.append(Vector((R * math.cos(a), y, hub + R * math.sin(a))))
            tube([Vector((0, y * 0.5, hub)), ring[-1]], [0.035, 0.03], 'bamboo', segs=5)
        for k in range(n):
            tube([ring[k], ring[(k + 1) % n]], [0.04, 0.04], 'bamboo', segs=5)
    part('paddles')
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        c = Vector(((R + 0.05) * math.cos(a), 0, hub + (R + 0.05) * math.sin(a)))
        t = Vector((-math.sin(a), 0, math.cos(a)))
        rad = Vector((math.cos(a), 0, math.sin(a)))
        slab([c - Vector((0, 0.58, 0)) - rad * 0.3, c + Vector((0, 0.58, 0)) - rad * 0.3, c + Vector((0, 0.58, 0)) + rad * 0.15,
              c - Vector((0, 0.58, 0)) + rad * 0.15], 0.03, 'weave', down=t)
        # bamboo buckets lashed at a slant: they fill at the bottom and tip into the trough at the top
        b0 = c + rad * 0.12 + Vector((0, 0.62, 0))
        tube([b0 - t * 0.28, b0 + t * 0.28 + rad * 0.12], [0.07, 0.07], 'bamboo', segs=6)
    return {'markers': {'hub': [0, hub, 0], 'R': R}}


# ------------------------------------------------------------------------------------------------------------ the land
def emergent():
    """A rainforest giant: a straight pale trunk on plank buttresses, the crown held high in a few broad clumps,
    lianas hanging from the limbs and ferns sitting in the forks."""
    rng = stream('shape')
    H = rng.uniform(24, 31)
    tz = H * rng.uniform(0.66, 0.74)
    group('shell')
    part('trunk')
    lean = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * 0.6
    pts = [Vector((0, 0, -0.4)) + lean * (t ** 2) + Vector((0, 0, tz * t)) for t in (i / 8 for i in range(9))]
    rad = [0.95 - 0.55 * (i / 8) ** 0.8 for i in range(9)]
    tube(pts, rad, 'bark', segs=11)
    part('buttress')
    nb = rng.randint(5, 7)
    for k in range(nb):
        a = 2 * math.pi * k / nb + rng.uniform(-0.25, 0.25)
        reach = rng.uniform(2.0, 3.6)
        hgt = rng.uniform(2.8, 4.6)
        d = Vector((math.cos(a), math.sin(a), 0))
        side = Vector((-d.y, d.x, 0))
        prof = []
        for i in range(7):
            t = i / 6
            r = 0.6 + reach * t
            z = hgt * (1 - t) ** 1.8 - 0.3
            prof.append(d * r + Vector((0, 0, max(z, -0.3))) + side * math.sin(t * 3) * 0.25)
        poly = [Vector((d.x * 0.5, d.y * 0.5, hgt + 0.4))] + prof + [Vector((d.x * 0.5, d.y * 0.5, -0.3))]
        slab([p + side * 0.11 for p in poly], 0.22, 'bark', down=-side)
    part('limbs')
    top = pts[-1]
    nl = rng.randint(4, 6)
    clumps = []
    for k in range(nl):
        a = 2 * math.pi * k / nl + rng.uniform(-0.4, 0.4)
        L = rng.uniform(4.5, 7.5)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(0.5, 1.0))).normalized()
        a0 = top - Vector((0, 0, rng.uniform(0, 2.5)))
        mid = a0 + d * L * 0.5 + Vector((0, 0, 0.6))
        end = a0 + d * L + Vector((0, 0, rng.uniform(1, 3)))
        tube(bezier(a0, mid, end, 5), [0.38, 0.3, 0.24, 0.18, 0.13, 0.09], 'bark', segs=7)
        clumps.append(end)
        # a liana loops down from the limb to the ground
        if rng.random() < 0.8:
            anchor = a0.lerp(end, rng.uniform(0.4, 0.8))
            foot = Vector((anchor.x * 1.15 + rng.uniform(-2, 2), anchor.y * 1.15 + rng.uniform(-2, 2), -0.2))
            part('liana')
            pts_l = [anchor.lerp(foot, t) + Vector((math.sin(t * 9 + k) * 0.25, math.cos(t * 7 + k) * 0.25, 0)) for t in (i / 10 for i in range(11))]
            tube(pts_l, [0.07] * 11, 'root', segs=5)
            part('limbs')
    part('crown')
    for c in clumps + [top + Vector((0, 0, 2.5))]:
        r = rng.uniform(3.2, 4.6)
        leaf_mass(c + Vector((0, 0, 0.8)), (r, r * rng.uniform(0.8, 1.1), r * 0.62), rng, n_leaf=110, leaf_len=1.3)
        for j in range(4):
            o = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.7, 0.7))) * r * 0.9
            leaf_mass(c + o + Vector((0, 0, 0.4)), (r * 0.6, r * 0.55, r * 0.48), rng, n_leaf=40, leaf_len=1.1)
    part('epiphytes')
    for k in range(4):
        z = rng.uniform(4, tz - 2)
        t = z / tz
        p = Vector((0, 0, -0.4)) + lean * (t ** 2) + Vector((0, 0, z))
        a = rng.uniform(0, 2 * math.pi)
        base = p + Vector((math.cos(a), math.sin(a), 0)) * (0.95 - 0.55 * t ** 0.8)
        for j in range(9):
            b = j * 2 * math.pi / 9
            strip_leaf(base, (math.cos(b) * 0.8 + math.cos(a) * 0.5, math.sin(b) * 0.8 + math.sin(a) * 0.5, 0.9), rng.uniform(0.9, 1.3), 0.22, rng, 'frond', segs=4, arch=0.5)
    collide((0, 0, 4), (1.6, 1.6, 8))
    return {'H': H}


def midtree():
    """The middle canopy: a 9 to 15 m tree with a smooth grey trunk that forks low, and a deep rounded crown built from
    overlapping leaf clumps, so the forest wall reads solid and layered under the giants. Cheaper than a giant, so the
    page can stand hundreds of them shoulder to shoulder."""
    rng = stream('shape')
    H = rng.uniform(9, 15)
    group('shell')
    part('trunk')
    fork = H * rng.uniform(0.35, 0.5)
    lean = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * 0.35
    base_pts = [Vector((0, 0, -0.3)) + lean * t * t + Vector((0, 0, fork * t)) for t in (i / 4 for i in range(5))]
    tube(base_pts, [0.42, 0.33, 0.29, 0.27, 0.25], 'bark', segs=8)
    # three short root flares instead of the giant's planks
    for k in range(3):
        a = 2 * math.pi * k / 3 + rng.uniform(-0.3, 0.3)
        d = Vector((math.cos(a), math.sin(a), 0))
        tube([d * 0.2 + Vector((0, 0, 1.1)), d * 0.7 + Vector((0, 0, 0.2)), d * 1.2 + Vector((0, 0, -0.25))], [0.16, 0.12, 0.06], 'bark', segs=5)
    part('limbs')
    top = base_pts[-1]
    ends = []
    for k in range(rng.randint(3, 4)):
        a = 2 * math.pi * k / 3.5 + rng.uniform(-0.4, 0.4)
        d = Vector((math.cos(a) * 0.55, math.sin(a) * 0.55, 1)).normalized()
        L = (H - fork) * rng.uniform(0.6, 0.85)
        end = top + d * L
        tube(bezier(top, top + d * L * 0.5 + Vector((0, 0, 0.4)), end, 4), [0.2, 0.15, 0.1, 0.07, 0.05], 'bark', segs=6)
        ends.append(end)
    part('crown')
    cz = sum((e.z for e in ends), 0) / len(ends)
    R = rng.uniform(2.6, 3.6)
    leaf_mass((0, 0, cz + 0.6), (R, R * 0.95, R * 0.75), rng, n_leaf=90, subdiv=2, leaf_len=1.0)
    for e in ends:
        r = R * rng.uniform(0.55, 0.75)
        leaf_mass(e + Vector((0, 0, 0.3)), (r, r, r * 0.8), rng, n_leaf=50, subdiv=1, leaf_len=0.9)
    for k in range(5):
        a = rng.uniform(0, 2 * math.pi)
        o = Vector((math.cos(a) * R * 0.8, math.sin(a) * R * 0.8, rng.uniform(-1.4, 0.2)))
        r = R * rng.uniform(0.4, 0.55)
        leaf_mass(Vector((0, 0, cz)) + o, (r, r, r * 0.75), rng, n_leaf=34, subdiv=1, leaf_len=0.8)
    # a few creepers hanging out of the crown
    part('liana')
    for k in range(rng.randint(2, 4)):
        a = rng.uniform(0, 2 * math.pi)
        st = Vector((math.cos(a) * R * 0.7, math.sin(a) * R * 0.7, cz - R * 0.4))
        n = 8
        L = rng.uniform(2.5, cz - 1.5)
        pts = [st + Vector((math.sin(i * 1.3 + k) * 0.12, math.cos(i * 1.1 + k) * 0.12, -L * i / n)) for i in range(n + 1)]
        tube(pts, [0.035] * (n + 1), 'root', segs=4)
        for i in range(2, n + 1, 2):
            leaf_quad(pts[i], (math.cos(a + i), math.sin(a + i), -0.2), 0.35, 0.14, (0, 0, 1), 'leaf', fold=0.2, droop=0.2)
    collide((0, 0, 2), (0.8, 0.8, 4))
    return {'H': H}


def palm():
    """A clump of slender jungle palms: ringed green-grey stems, each topped by a shaft of pinnate fronds that arch
    out and down; old fronds hang dry under the crown."""
    rng = stream('shape')
    group('shell')
    ns = rng.randint(2, 4)
    for s_ in range(ns):
        part(f'stem{s_}')
        a = rng.uniform(0, 2 * math.pi)
        r = 0 if s_ == 0 else rng.uniform(0.4, 0.9)
        base = Vector((r * math.cos(a), r * math.sin(a), -0.15))
        H = rng.uniform(5.5, 9.0) * (1 if s_ == 0 else rng.uniform(0.45, 0.85))
        out = Vector((math.cos(a), math.sin(a), 0)) * (0 if s_ == 0 else H * 0.12)
        top = base + out + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), H))
        pts = bezier(base, base + Vector((0, 0, H * 0.5)), top, 8)
        tube(pts, [0.12 - 0.03 * i / 8 for i in range(9)], 'bamboo', segs=7)
        # leaf rings: a slightly wider band every stretch of stem
        for i in range(1, 8):
            tube([pts[i] - (pts[i + 1] - pts[i]) * 0.04, pts[i] + (pts[i + 1] - pts[i]) * 0.04], [0.125 - 0.03 * i / 8] * 2, 'wood', segs=7)
        crown = pts[-1]
        tube([crown, crown + Vector((0, 0, 0.9))], [0.1, 0.08], 'frond', segs=6)    # the green crownshaft
        nf = rng.randint(8, 11)
        for k in range(nf):
            b = 2 * math.pi * k / nf + rng.uniform(-0.2, 0.2)
            dead = k < 2 and rng.random() < 0.7
            up = rng.uniform(0.3, 1.2) if not dead else -1.6
            d = Vector((math.cos(b), math.sin(b), up)).normalized()
            L = rng.uniform(2.2, 3.0) * (1 if s_ == 0 else 0.8)
            NS = 9
            st = crown + Vector((0, 0, 0.8))
            rach = [st + d * L * t + Vector((0, 0, -(1.3 if not dead else 0.2) * L * t * t)) for t in (i / NS for i in range(NS + 1))]
            tube(rach, [0.03] * (NS + 1), 'frond' if not dead else 'dry', segs=3)
            side = Vector((-math.sin(b), math.cos(b), 0))
            for i in range(1, NS + 1):
                w = 0.75 * math.sin(math.pi * min(i, NS - 0.5) / (NS + 0.5)) + 0.12
                fw = (rach[min(i + 1, NS)] - rach[i - 1]).normalized()
                for sg in (-1, 1):
                    leaf_quad(rach[i], side * sg + fw * 0.5 + Vector((0, 0, -0.35)), w, 0.07, (0, 0, 1), 'dry' if dead else 'frond', fold=0.1, droop=0.25)
    collide((0, 0, 2), (0.4, 0.4, 4))
    return {}


def jetty():
    """The river landing: a plank jetty on hardwood piles running out from the bank (+y is out over the water), a
    dugout moored at its end, and fish-drying racks on the shore end. The bank is at z = 0; the water is about 0.9 m
    below it. A village by a river eats from it: this is where the fish come in and dry."""
    rng = stream('shape')
    L, Wd, dz = rng.uniform(6.5, 8.0), rng.uniform(1.5, 1.8), 0.35
    group('shell')
    part('piles')
    ys = [0.4 + i * (L - 0.4) / 4 for i in range(5)]
    for y in ys:
        for x in (-Wd / 2, Wd / 2):
            post(x + rng.uniform(-0.05, 0.05), y, -2.6, dz + 0.05, 0.1, rng, lean=rng.uniform(-0.05, 0.05))
            collide((x, y, (dz - 2.6) / 2), (0.2, 0.2, dz + 2.6))
        box((0, y, dz - 0.08), (Wd + 0.3, 0.13, 0.12), 'wood')
    part('deck')
    for x in (-Wd / 2 + 0.12, Wd / 2 - 0.12):
        box((x, L / 2, dz - 0.0), (0.12, L, 0.1), 'wood')
    y = -0.6
    while y < L:
        w = rng.uniform(0.18, 0.26)
        sl = 'plank' if rng.random() > 0.15 else 'bamboo'
        box((rng.uniform(-0.03, 0.03), y + w / 2, dz + 0.07), (Wd + rng.uniform(-0.1, 0.12), w - 0.015, 0.045), sl, rot=rng.uniform(-0.03, 0.03))
        y += w
    collide((0, (L - 0.6) / 2, dz + 0.07), (Wd, L + 0.6, 0.06))
    surface('porch', (0, L - 0.9, dz + 0.1), Wd - 0.4, 1.2)
    # a bamboo hand rail along one side
    part('rail')
    for y in ys[1:]:
        post(Wd / 2, y, dz + 0.05, dz + 0.95, 0.04, rng, slot='bamboo', segs=5)
    tube([Vector((Wd / 2, ys[1], dz + 0.92)), Vector((Wd / 2, ys[-1], dz + 0.92))], [0.035, 0.035], 'bamboo', segs=5)
    collide((Wd / 2, (ys[1] + ys[-1]) / 2, dz + 0.5), (0.06, ys[-1] - ys[1], 0.9))
    part('boat')
    # the dugout: one hollowed log, pointed both ends, lying beside the jetty's end, its paddle across it
    bx, by, bz = -Wd / 2 - 0.65, L - 1.6, -0.82
    BL = rng.uniform(4.2, 5.0)
    rings = []
    for i in range(11):
        t = i / 10
        hw = 0.36 * math.sin(math.pi * t) ** 0.6 + 0.02
        y = by - BL / 2 + BL * t
        lift = 0.18 * (2 * t - 1) ** 4
        rings.append([Vector((bx - hw, y, bz + 0.32 + lift)), Vector((bx - hw * 0.9, y, bz + 0.08)), Vector((bx, y, bz)),
                      Vector((bx + hw * 0.9, y, bz + 0.08)), Vector((bx + hw, y, bz + 0.32 + lift)),
                      Vector((bx + hw * 0.75, y, bz + 0.3 + lift)), Vector((bx + hw * 0.7, y, bz + 0.12)),
                      Vector((bx - hw * 0.7, y, bz + 0.12)), Vector((bx - hw * 0.75, y, bz + 0.3 + lift))])
    solid_rings(rings, 'wood')
    tube([Vector((bx - 0.5, by + 0.4, bz + 0.38)), Vector((bx + 0.6, by - 0.2, bz + 0.36))], [0.025, 0.025], 'wood', segs=4)
    slab([(bx + 0.55, by - 0.2, bz + 0.37), (bx + 0.95, by - 0.42, bz + 0.37), (bx + 1.0, by - 0.3, bz + 0.37), (bx + 0.6, by - 0.1, bz + 0.37)], 0.02, 'wood')
    # the mooring rope from the bow to the end pile
    tube(sag_curve(Vector((bx, by + BL / 2 - 0.2, bz + 0.45)), Vector((-Wd / 2, ys[-1], dz - 0.2)), 0.25, n=6), [0.012] * 7, 'rope', segs=4)
    part('racks')
    # fish-drying racks on the bank: two A-frames, a pole between, split fish hung in a row
    for k in range(2):
        rx = rng.uniform(1.6, 2.4) * (1 if k else -1)
        ry = rng.uniform(-2.2, -1.2)
        rl = rng.uniform(1.8, 2.4)
        for e in (-1, 1):
            yy = ry + e * rl / 2
            tube([Vector((rx - 0.35, yy, -0.05)), Vector((rx, yy, 1.6))], [0.035, 0.03], 'bamboo', segs=5)
            tube([Vector((rx + 0.35, yy, -0.05)), Vector((rx, yy, 1.6))], [0.035, 0.03], 'bamboo', segs=5)
        tube([Vector((rx, ry - rl / 2 - 0.15, 1.56)), Vector((rx, ry + rl / 2 + 0.15, 1.56))], [0.03, 0.03], 'bamboo', segs=5)
        for j in range(int(rl / 0.16)):
            fy = ry - rl / 2 + 0.12 + j * 0.16
            tube([Vector((rx, fy, 1.55)), Vector((rx, fy, 1.42))], [0.006, 0.006], 'rope', segs=3)
            slab([(rx, fy - 0.05, 1.42), (rx, fy + 0.05, 1.42), (rx + 0.01, fy + 0.03, 1.05), (rx, fy, 0.98), (rx - 0.01, fy - 0.03, 1.05)], 0.02, 'clay')
        collide((rx, ry, 0.8), (0.7, rl, 1.6))
    # a fish trap leaning on the first pile
    part('trap')
    tp = Vector((-Wd / 2 - 0.35, 1.0, -0.05))
    lathe([(0.0, 0.0), (0.22, 0.05), (0.28, 0.4), (0.2, 0.75), (0.07, 0.95), (0.0, 0.96)], 9, 'weave', center=tp)
    return {'L': L, 'deck': dz, 'markers': {'end': [0, L, dz]}}


def timberyard():
    """The village's trade: a sawpit under a lean-to of thatch where two men rip ironwood logs into planks, a log pile
    hauled in from the forest, a rack of cut bamboo drying for walls and floors, and a chopping block."""
    rng = stream('shape')
    group('shell')
    part('sawpit')
    TL, TH = rng.uniform(3.6, 4.4), 1.55
    for x in (-TL / 2 + 0.4, TL / 2 - 0.4):
        for e in (-1, 1):
            tube([Vector((x, e * 0.55, -0.05)), Vector((x, e * 0.12, TH))], [0.07, 0.06], 'wood', segs=6)
        box((x, 0, TH), (0.16, 0.5, 0.14), 'wood')
        collide((x, 0, TH / 2), (0.2, 1.1, TH))
    logr = rng.uniform(0.3, 0.38)
    tube([Vector((-TL / 2 - 0.3, 0, TH + logr)), Vector((TL / 2 + 0.3, 0, TH + logr))], [logr, logr * 0.92], 'root', segs=10)
    # the sawn part: a pale flat face where the first planks came off, and the saw standing in the cut
    box((TL / 2 - 0.4, 0, TH + logr * 0.4), (1.6, logr * 1.6, 0.04), 'plank')
    box((0.4, 0.0, TH + logr), (0.05, 0.02, 1.7), 'ash')
    for z in (TH + logr - 0.85, TH + logr + 0.85):
        box((0.4, 0, z), (0.05, 0.4, 0.05), 'wood')
    collide((0, 0, TH + logr), (TL + 0.6, logr * 2, logr * 2))
    # sawdust round the pit
    blob((0, 0, -0.02), (TL / 2 + 0.3, 1.0, 0.06), 'dry', rng, subdiv=1, rough=0.25, flat_bottom=-0.05)
    part('shade')
    SW, SD, SH = TL + 1.4, 3.0, 2.9
    for x in (-SW / 2, SW / 2):
        post(x, -SD / 2, -0.05, SH, 0.09, rng)
        post(x, SD / 2, -0.05, SH - 0.7, 0.09, rng)
        collide((x, -SD / 2, SH / 2), (0.18, 0.18, SH))
        collide((x, SD / 2, SH / 2), (0.18, 0.18, SH - 0.7))
    box((0, -SD / 2, SH), (SW + 0.3, 0.12, 0.12), 'wood')
    box((0, SD / 2, SH - 0.7), (SW + 0.3, 0.12, 0.12), 'wood')
    slab([(-SW / 2 - 0.5, -SD / 2 - 0.7, SH + 0.28), (SW / 2 + 0.5, -SD / 2 - 0.7, SH + 0.28), (SW / 2 + 0.5, SD / 2 + 0.7, SH - 0.7 - 0.0),
          (-SW / 2 - 0.5, SD / 2 + 0.7, SH - 0.7 - 0.0)], 0.2, 'thatch')
    part('logs')
    # the log pile: hauled ironwood, stacked in a pyramid on two skids
    px, py = rng.uniform(-1.0, 1.0), SD / 2 + 2.4
    LL = rng.uniform(4.0, 5.0)
    for x in (-LL / 2 + 0.5, LL / 2 - 0.5):
        box((px + x, py, 0.06), (0.2, 2.4, 0.14), 'wood')
    rows = [4, 3, 2]
    for r_, n in enumerate(rows):
        for i in range(n):
            rr = rng.uniform(0.24, 0.3)
            y = py + (i - (n - 1) / 2) * 0.56
            z = 0.13 + rr + r_ * 0.48
            tube([Vector((px - LL / 2 + rng.uniform(-0.2, 0.2), y, z)), Vector((px + LL / 2 + rng.uniform(-0.2, 0.2), y, z))], [rr, rr * 0.9], 'root', segs=9)
    collide((px, py, 0.8), (LL, 2.3, 1.6))
    part('bamboo')
    # a rack of cut culms leaning on a rail, drying before they are split
    bx, by = -SW / 2 - 2.2, rng.uniform(-1.0, 0.5)
    post(bx, by - 1.4, -0.05, 1.9, 0.07, rng)
    post(bx, by + 1.4, -0.05, 1.9, 0.07, rng)
    tube([Vector((bx, by - 1.55, 1.85)), Vector((bx, by + 1.55, 1.85))], [0.05, 0.05], 'wood', segs=6)
    for k in range(18):
        yy = by - 1.3 + k * 2.6 / 17 + rng.uniform(-0.04, 0.04)
        side = 1 if k % 2 else -1
        top = Vector((bx, yy, 1.88 + rng.uniform(0, 0.25)))
        foot = Vector((bx + side * rng.uniform(0.9, 1.2), yy + rng.uniform(-0.15, 0.15), -0.02))
        tube([foot, top + (top - foot).normalized() * rng.uniform(0.3, 1.2)], [0.045, 0.04], 'bamboo', segs=6)
    collide((bx, by, 1.0), (2.2, 3.0, 2.0))
    part('block')
    cx, cy = SW / 2 + 1.4, rng.uniform(-1.4, 1.4)
    tube([Vector((cx, cy, -0.05)), Vector((cx, cy, 0.55))], [0.32, 0.3], 'wood', segs=10)
    tube([Vector((cx - 0.05, cy, 0.62)), Vector((cx + 0.55, cy + 0.2, 0.95))], [0.025, 0.022], 'wood', segs=5)
    box((cx, cy, 0.62), (0.18, 0.04, 0.12), 'ash', rot=0.35)
    collide((cx, cy, 0.27), (0.62, 0.62, 0.6))
    surface('under', (cx + 0.2, cy + 1.6, 0.0), 1.8, 1.2)
    surface('under', (0, -SD / 2 - 1.4, 0.0), SW - 1.0, 1.0)
    return {'W': SW + 5, 'D': SD + 6}


def banyan():
    """A strangler fig grown into a hall of roots: a braided trunk, long level limbs, and prop roots dropped from them
    that have thickened into pillars."""
    rng = stream('shape')
    group('shell')
    part('trunk')
    Ht = rng.uniform(5.5, 7.5)
    n = rng.randint(9, 13)
    for k in range(n):
        a0 = 2 * math.pi * k / n
        r0 = rng.uniform(1.2, 2.2)
        pts, rad = [], []
        for i in range(9):
            t = i / 8
            a = a0 + t * rng.uniform(0.8, 1.6)
            r = r0 * (1 - t) + 0.55 * t
            pts.append(Vector((r * math.cos(a), r * math.sin(a), -0.4 + t * Ht)))
            rad.append(rng.uniform(0.28, 0.5) * (1.3 - 0.5 * t))
        tube(pts, rad, 'root', segs=7)
    tube([Vector((0, 0, -0.3)), Vector((0, 0, Ht + 1.0))], [1.1, 0.9], 'bark', segs=10)
    part('limbs')
    nl = rng.randint(6, 8)
    ends = []
    for k in range(nl):
        a = 2 * math.pi * k / nl + rng.uniform(-0.3, 0.3)
        L = rng.uniform(7, 11)
        d = Vector((math.cos(a), math.sin(a), 0))
        a0 = Vector((0, 0, Ht + rng.uniform(-0.5, 1.2)))
        pts = bezier(a0, a0 + d * L * 0.5 + Vector((0, 0, rng.uniform(1.5, 3))), a0 + d * L + Vector((0, 0, rng.uniform(1, 3.5))), 7)
        tube(pts, [0.6, 0.5, 0.42, 0.34, 0.27, 0.2, 0.14, 0.09], 'bark', segs=8)
        ends.append(pts)
        # prop roots: straight down from the limb, some thick as pillars, some still thin cords
        part('props')
        for j in range(rng.randint(3, 6)):
            p = pts[rng.randint(2, 6)]
            thick = rng.random() < 0.45
            r = rng.uniform(0.18, 0.32) if thick else rng.uniform(0.03, 0.06)
            foot = Vector((p.x + rng.uniform(-0.2, 0.2), p.y + rng.uniform(-0.2, 0.2), -0.3 if thick else rng.uniform(-0.3, p.z * 0.5)))
            tube([p, p.lerp(foot, 0.5) + Vector((rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), 0)), foot], [r * 0.7, r, r * (1.5 if thick else 1)], 'root', segs=6 if thick else 4)
            if thick:
                collide((foot.x, foot.y, p.z / 2), (r * 2, r * 2, p.z))
        part('limbs')
    part('crown')
    for pts in ends:
        for p in (pts[3], pts[5], pts[7]):
            r = rng.uniform(3.0, 4.2)
            leaf_mass(p + Vector((0, 0, 1.6)), (r, r, r * 0.45), rng, n_leaf=55, leaf_len=0.8)
    leaf_mass(Vector((0, 0, Ht + 6)), (6, 6, 2.6), rng, n_leaf=90, subdiv=3, leaf_len=0.9)
    collide((0, 0, 3), (3.2, 3.2, 6))
    return {}


def bamboo():
    rng = stream('shape')
    group('shell')
    n = rng.randint(16, 26)
    for k in range(n):
        part(f'culm{k}')
        a = rng.uniform(0, 2 * math.pi)
        r0 = rng.uniform(0, 0.9)
        base = Vector((r0 * math.cos(a), r0 * math.sin(a), -0.2))
        H = rng.uniform(7, 13)
        out = Vector((math.cos(a), math.sin(a), 0)) * (r0 + 0.4) * rng.uniform(1.2, 3.0)
        top = base + out + Vector((0, 0, H))
        mid = base + out * 0.15 + Vector((0, 0, H * 0.6))
        pts = bezier(base, mid, top + out * 0.6 - Vector((0, 0, H * 0.12)), 10)
        rr = rng.uniform(0.06, 0.1)
        tube(pts, [rr * (1 - 0.5 * i / 10) for i in range(11)], 'bamboo', segs=6)
        # leaf sprays from the upper half: a short twig with a fan of narrow leaves
        for i in range(3, 10):
            for j in range(3 + (i > 5)):
                p = pts[i].lerp(pts[i + 1], rng.random())
                d = (pts[i + 1] - pts[i]).normalized()
                sd = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.2, 0.4))).normalized()
                tw = p + sd * 0.6
                tube([p, tw], [0.01, 0.006], 'bamboo', segs=3)
                for q in range(8):
                    ld = (sd + Vector((rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8), rng.uniform(-0.9, -0.1)))).normalized()
                    leaf_quad(tw.lerp(p, q / 16), ld, rng.uniform(0.4, 0.6), 0.075, (0, 0, 1), 'leaf', fold=0.15, droop=0.35)
    # the clump's dry litter of fallen culm sheaths
    part('sheaths')
    for k in range(10):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.3, 1.4)
        c = Vector((r * math.cos(a), r * math.sin(a), 0.02))
        leaf_quad(c, (math.cos(a + 1), math.sin(a + 1), 0.05), rng.uniform(0.3, 0.5), 0.16, (0, 0, 1), 'dry', fold=0.05)
    collide((0, 0, 2), (1.4, 1.4, 4))
    return {}


def banana():
    rng = stream('shape')
    group('shell')
    nst = rng.randint(2, 4)
    for s_ in range(nst):
        part(f'plant{s_}')
        a = rng.uniform(0, 2 * math.pi)
        r = 0 if s_ == 0 else rng.uniform(0.5, 1.0)
        base = Vector((r * math.cos(a), r * math.sin(a), -0.1))
        H = rng.uniform(2.0, 2.7) * (1 if s_ == 0 else rng.uniform(0.5, 0.8))
        top = base + Vector((rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), H))
        tube([base, base.lerp(top, 0.5), top], [0.17, 0.14, 0.11], 'frond', segs=8)
        # old leaf sheaths hang dry round the stem
        for k in range(3):
            b = rng.uniform(0, 2 * math.pi)
            p = base.lerp(top, rng.uniform(0.4, 0.8))
            strip_leaf(p + Vector((math.cos(b) * 0.1, math.sin(b) * 0.1, 0)), (math.cos(b) * 0.3, math.sin(b) * 0.3, -1), rng.uniform(0.6, 1.0), 0.18, rng, 'dry', segs=3, arch=0.0)
        nl = rng.randint(6, 9)
        for k in range(nl):
            b = 2 * math.pi * k / nl * 1.3 + rng.uniform(-0.2, 0.2)
            up = rng.uniform(1.0, 2.2) if k < nl - 2 else rng.uniform(2.5, 4.0)
            d = Vector((math.cos(b), math.sin(b), up)).normalized()
            pet = top + d * 0.45
            tube([top, pet], [0.04, 0.03], 'frond', segs=4)
            dead = k == 0 and rng.random() < 0.6
            strip_leaf(pet, d, rng.uniform(2.1, 2.8) * (1 if s_ == 0 else 0.75), rng.uniform(0.6, 0.75), rng,
                       'dry' if dead else 'frond', segs=10, arch=0.42 if not dead else 0.9, tear=0.25 + 0.3 * rng.random(), twist=0.05)
        if s_ == 0:
            # the hanging bunch and its purple bud
            part('bunch')
            stalk = bezier(top, top + Vector((0.5, 0, 0.1)), top + Vector((0.7, 0, -1.0)), 5)
            tube(stalk, [0.03] * 6, 'frond', segs=4)
            for i in range(1, 4):
                c = stalk[i]
                for j in range(6):
                    b = j * math.pi / 3
                    leaf_quad(c, (math.cos(b) * 0.5, math.sin(b) * 0.5, 0.8), 0.18, 0.05, (0, 0, 1), 'dry', fold=0.4)
            blob(stalk[-1] + Vector((0, 0, -0.1)), (0.09, 0.09, 0.2), 'lacquer', rng, subdiv=1, rough=0.1)
    collide((0, 0, 1), (0.4, 0.4, 2))
    return {}


def taro():
    rng = stream('shape')
    group('shell')
    part('base')
    blob((0, 0, 0.05), (0.25, 0.22, 0.15), 'frond', rng, subdiv=1, rough=0.2)
    n = rng.randint(5, 8)
    for k in range(n):
        part(f'leaf{k}')
        a = 2 * math.pi * k / n + rng.uniform(-0.3, 0.3)
        h = rng.uniform(0.9, 1.7)
        d = Vector((math.cos(a), math.sin(a), 0))
        tip = d * rng.uniform(0.3, 0.7) + Vector((0, 0, h))
        tube(bezier(Vector((0, 0, 0.1)), d * 0.1 + Vector((0, 0, h * 0.6)), tip, 4), [0.035, 0.03, 0.028, 0.025, 0.02], 'frond', segs=5)
        L = rng.uniform(0.8, 1.3)
        strip_leaf(tip, d + Vector((0, 0, -0.35)), L, L * 0.85, rng, 'leaf', segs=6, arch=0.25, heart=1.0)
    return {}


def treefern():
    rng = stream('shape')
    group('shell')
    part('trunk')
    H = rng.uniform(2.2, 3.8)
    top = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), H))
    tube(bezier(Vector((0, 0, -0.1)), Vector((0, 0, H * 0.5)), top, 5), [0.2, 0.16, 0.15, 0.14, 0.15, 0.18], 'root', segs=8)
    part('fronds')
    n = rng.randint(10, 14)
    for k in range(n):
        a = 2 * math.pi * k / n + rng.uniform(-0.15, 0.15)
        up = rng.uniform(0.2, 0.9)
        L = rng.uniform(1.8, 2.6)
        d = Vector((math.cos(a), math.sin(a), up)).normalized()
        NS = 16
        rach = [top + d * L * t + Vector((0, 0, -0.9 * L * t * t)) for t in (i / NS for i in range(NS + 1))]
        tube(rach, [0.025] * (NS + 1), 'frond', segs=3)
        side = Vector((-math.sin(a), math.cos(a), 0))
        for i in range(1, NS + 1):
            w = 0.5 * math.sin(math.pi * min(i, NS - 0.5) / (NS + 0.5)) + 0.06
            fw = (rach[min(i + 1, NS)] - rach[i - 1]).normalized()
            for sg in (-1, 1):
                leaf_quad(rach[i], side * sg + fw * 0.35 + Vector((0, 0, -0.15)), w, 0.13, (0, 0, 1), 'frond', fold=0.12, droop=0.2)
    collide((0, 0, 1), (0.4, 0.4, 2))
    return {}


def karst():
    """A limestone tower: sheer fluted sides, undercut at the foot, ledges that hold shrubs, a jungle cap, and vines
    hanging down the faces."""
    rng = stream('shape')
    H = rng.uniform(34, 46)
    R0 = rng.uniform(6.5, 8.5)
    group('shell')
    part('rock')
    segs = 28
    off = [rng.uniform(0, 100) for _ in range(6)]
    nr = 18
    prof = []
    for i in range(nr + 1):
        t = i / nr
        r = R0 * (1 - 0.45 * t ** 1.1)
        if 0.05 < t < 0.14:
            r *= 0.86                      # the undercut notch the river cut
        if abs(t - 0.45) < 0.03 or abs(t - 0.72) < 0.03:
            r *= 1.08                      # ledges
        z = H * t
        prof.append((r, z))
    prof.append((R0 * 0.3, H + 0.8))

    def wob(k, i):
        a = 2 * math.pi * i / segs
        t = k / nr
        return (0.16 * math.sin(a * 3 + off[0] + t * 4) + 0.1 * math.sin(a * 7 + off[1] + t * 9) + 0.07 * abs(math.sin(a * 5.5 + off[5]))
                + 0.05 * math.sin(a * 13 + off[2]) + 0.06 * math.sin(t * 17 + off[3] + a * 2))
    lathe(prof, segs, 'stone', wob=wob)
    # a second, smaller tower grown into the first
    part('rock2')
    R1 = R0 * 0.55
    c2 = Vector((R0 * 0.7, R0 * 0.25, 0))
    prof2 = [(R1 * (1 - 0.6 * (i / 12) ** 1.2), H * 0.7 * i / 12) for i in range(13)] + [(R1 * 0.25, H * 0.7 + 0.5)]
    lathe(prof2, 16, 'stone', center=c2, wob=lambda k, i: 0.1 * math.sin(i * 1.9 + k * 0.7 + off[4]))
    part('cap')
    for k in range(12):
        a = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(0, R0 * 0.5)
        leaf_mass((rr * math.cos(a), rr * math.sin(a), H + rng.uniform(0.3, 1.8)), (rng.uniform(2.5, 4.0), rng.uniform(2.5, 4.0), rng.uniform(1.4, 2.4)), rng, n_leaf=40, leaf_len=1.0)
    part('ledges')
    for tl in (0.45, 0.72):
        for k in range(5):
            a = rng.uniform(0, 2 * math.pi)
            r = R0 * (1 - 0.45 * tl ** 1.1) * 1.0
            leaf_mass((r * math.cos(a), r * math.sin(a), H * tl + 0.6), (1.4, 1.4, 0.8), rng, n_leaf=16, leaf_len=0.6)
    part('vines')
    for k in range(24):
        a = rng.uniform(0, 2 * math.pi)
        t0 = rng.choice([0.45, 0.72, 0.98])
        r = R0 * (1 - 0.45 * t0 ** 1.1)
        p0 = Vector((r * math.cos(a), r * math.sin(a), H * t0))
        L = rng.uniform(5, 14)
        pts = [p0 + Vector((math.cos(a), math.sin(a), 0)) * (0.3 + 0.15 * math.sin(i)) + Vector((0, 0, -L * i / 8)) for i in range(9)]
        tube(pts, [0.06] * 9, 'root', segs=4)
        for i in range(1, 9, 2):
            leaf_quad(pts[i], (math.cos(a), math.sin(a), -0.6), 0.4, 0.16, (0, 0, 1), 'leaf')
    collide((0, 0, H / 2), (R0 * 1.5, R0 * 1.5, H))
    return {'H': H, 'R': R0}


def boulders():
    rng = stream('shape')
    for i in range(5):
        group(f'b{i}')
        part(f'b{i}')
        r = 0.4 + i * 0.35
        blob((i * 4.0, 0, r * 0.3), (r * rng.uniform(1.0, 1.4), r, r * rng.uniform(0.6, 0.85)), 'stone', rng, subdiv=2, rough=0.2,
             flat_bottom=-0.15)
        # a moss cap on the top
        part(f'm{i}')
        blob((i * 4.0 + rng.uniform(-0.1, 0.1), 0, r * 0.3 + r * 0.55), (r * 0.8, r * 0.7, r * 0.22), 'moss', rng, subdiv=2, rough=0.25)
    GROUPS.remove('shell') if 'shell' in GROUPS and False else None
    return {}


BUILDERS = {'stilthouse': lambda: stilthouse('house'), 'longhouse': lambda: stilthouse('great'), 'granary': granary,
            'shrine': shrine, 'waterwheel': waterwheel, 'emergent': emergent, 'banyan': banyan, 'bamboo': bamboo, 'midtree': midtree, 'palm': palm, 'jetty': jetty, 'timberyard': timberyard,
            'banana': banana, 'taro': taro, 'treefern': treefern, 'karst': karst, 'boulders': boulders}
t0 = time.time()
INFO = BUILDERS[args.asset]()
INFO['colliders'] = COLS
INFO['surfaces'] = SURF
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
print(f'[{NAME}] built {len(bm.faces)} faces in {time.time() - t0:.1f}s')
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
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
    from jungle_paint import paint_atlas
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
    render_preview.render(scene, objs, os.path.join(args.out, NAME), INFO, clay=args.geom)
print(f'[{NAME}] done in {time.time() - t0:.1f}s')
