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


