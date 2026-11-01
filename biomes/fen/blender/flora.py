"""Fen flora: tallow trees and snags, bladder lilies, pitcher clumps, sundew hummocks, sedge and cotton tussocks, boulders.

Tallow tree: an original tree for this fen. A pale chalky trunk barred with black lenticels, buttressed into the water,
carrying flat tiers of rust-gold needle tufts on near-level limbs (swept tubes plus alpha-cut cards).
"""
import math
import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, noise
import kit
from kit import box, beam, cyl, lathe, tube

CARD_COLS, CARD_ROWS = 4, 3


def P(r, a, z):
    return Vector((r * math.cos(a), r * math.sin(a), z))


# ---------------------------------------------------------------- crown cards
def paint_cards(path, seed=7, kind='needle'):
    """A 1024 sheet: 4 spray shapes x 3 rows (lit, mid, shade), palette swatches, 1-bit alpha."""
    import painter as pt
    S = 1024
    cw, chh = S // CARD_COLS, S // CARD_ROWS
    rgba = np.zeros((S, S, 4), np.uint8)
    rng = np.random.default_rng(seed)
    if kind == 'needle':
        ramp = [pt.RGB[c] for c in ('sph_red', 'sph_rust', 'sph_ochre', 'sph_gold', 'lich_ochre', 'fl_gold')]
    else:
        ramp = [pt.RGB[c] for c in ('bark_ink', 'bark_grey', 'tim_mid', 'tim_silver')]
    twig = [pt.RGB[c] for c in ('bark_ink', 'bark_grey', 'tim_mid')]
    for row in range(CARD_ROWS):
        bright = [0.95, 0.62, 0.32][row]
        for col in range(CARD_COLS):
            x0, y0 = col * cw, row * chh
            cx, cy = x0 + cw / 2, y0 + chh / 2

            def dot(x, y, c, r=1):
                xi, yi = int(x), int(y)
                for dx in range(-r + 1, r):
                    for dy in range(-r + 1, r):
                        xx, yy = xi + dx, yi + dy
                        if x0 + 2 <= xx < x0 + cw - 2 and y0 + 2 <= yy < y0 + chh - 2:
                            rgba[yy, xx, :3] = c
                            rgba[yy, xx, 3] = 255
            # branchlets fan out from the near edge of the card, each carrying dense rosettes of short needles
            nb = 6 + col
            for b in range(nb):
                ang = -math.pi / 2 + (b - (nb - 1) / 2) * (2.2 / nb) + rng.uniform(-0.12, 0.12)
                L = rng.uniform(0.55, 0.8) * chh
                px, py = cx, y0 + chh - 8
                pts = []
                for s in range(48):
                    t = s / 47
                    a2 = ang + math.sin(t * 3 + b) * 0.1
                    pts.append((px + math.cos(a2) * L * t, py + math.sin(a2) * L * t))
                for (x, y) in pts[::2]:
                    dot(x, y, twig[1 if row == 0 else 0], 2)
                for s in range(6, 48, 3):
                    bx, by = pts[s]
                    nn = rng.integers(16, 26)
                    for k in range(nn):
                        na = rng.uniform(0, 2 * math.pi)
                        nl = rng.uniform(8, 17) * (1.0 if kind == 'needle' else 0.5)
                        for q in range(0, int(nl), 1):
                            f = q / nl
                            v = (0.2 + 0.8 * f) * bright + rng.normal(0, 0.07)
                            ci = int(np.clip(round(v * (len(ramp) - 1)), 0, len(ramp) - 1))
                            dot(bx + math.cos(na) * q, by + math.sin(na) * q * 0.85, ramp[ci], 2 if f < 0.6 else 1)
    from PIL import Image
    Image.fromarray(rgba[::-1].copy() if False else rgba, 'RGBA').save(path)


def card_object(name, cards):
    """cards: list of (centre, normal-ish up, size, spin, row, col). Two faces 4 mm apart, so each side shades on its own."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    for (c, n, s, spin, row, col) in cards:
        n = Vector(n).normalized()
        t = n.orthogonal().normalized()
        t = Matrix.Rotation(spin, 3, n) @ t
        b = n.cross(t)
        u0, v0 = col / CARD_COLS, 1 - (row + 1) / CARD_ROWS
        du, dv = 1 / CARD_COLS, 1 / CARD_ROWS
        e = 0.004
        for side, off in ((1, e), (-1, -e)):
            corners = [c + n * off + t * (-s / 2) + b * 0, c + n * off + t * (s / 2) + b * 0,
                       c + n * off + t * (s / 2) + b * s, c + n * off + t * (-s / 2) + b * s]
            # the near edge of the card (where the branchlets start) sits on the limb
            corners = [p - b * s * 0.15 for p in corners]
            uvs = [(u0 + 0.004, v0 + 0.004), (u0 + du - 0.004, v0 + 0.004), (u0 + du - 0.004, v0 + dv - 0.004), (u0 + 0.004, v0 + dv - 0.004)]
            vs = [bm.verts.new(p) for p in corners]
            if side < 0:
                vs, uvs = vs[::-1], uvs[::-1]
            f = bm.faces.new(vs)
            for lp, uv in zip(f.loops, uvs):
                lp[uvl].uv = uv
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def card_finish(ob, png):
    img = bpy.data.images.load(png)
    m = bpy.data.materials.new(ob.name + '_mat')
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = img
    t.interpolation = 'Closest'
    nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(t.outputs['Alpha'], bsdf.inputs['Alpha'])
    bsdf.inputs['Roughness'].default_value = 0.9
    try:
        m.blend_method = 'CLIP'
    except Exception:
        pass
    ob.data.materials.clear()
    ob.data.materials.append(m)


# ---------------------------------------------------------------- tallow tree
def tallow(seed, variant):
    rng = kit.stream(seed, 'tallow:' + variant)
    R = kit.Rec()
    H = {'a': 11.5, 'b': 9.0, 'c': 13.5}[variant] * rng.uniform(0.95, 1.05)
    r0 = {'a': 0.36, 'b': 0.3, 'c': 0.42}[variant]
    lean = Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 0))
    n = 18
    pts, rad = [], []
    for i in range(n):
        t = i / (n - 1)
        bend = lean * (t ** 1.6) + Vector((math.sin(t * 4.2 + 1) * 0.18, math.cos(t * 3.1) * 0.14, 0)) * t
        pts.append(Vector((0, 0, -0.5 + (H + 0.5) * t)) + bend)
        rad.append(r0 * (1 - 0.86 * t ** 0.9) + 0.035 + (0.5 * r0 * max(0, 0.1 - t) * 10) ** 1.2)
    ph = rng.uniform(0, 6)
    lobe = lambda wa, t: 1 + (0.55 * max(0.0, 1 - t / 0.13) ** 2) * max(0.0, math.cos(5 * wa + ph)) ** 2 + \
        0.04 * math.sin(wa * 11 + t * 30)
    tube(R, 'trunk', 'bark', pts, rad, segs=18, lobe=lobe, cap0=False)
    def on_trunk(z):
        for i in range(n - 1):
            if pts[i].z <= z <= pts[i + 1].z:
                f = (z - pts[i].z) / (pts[i + 1].z - pts[i].z)
                return pts[i].lerp(pts[i + 1], f), rad[i] + (rad[i + 1] - rad[i]) * f
        return pts[-1], rad[-1]
    cards = []
    tiers = {'a': 5, 'b': 4, 'c': 6}[variant]
    z_lo, z_hi = H * 0.56, H * 0.95
    li = 0
    for k in range(tiers):
        f = k / max(1, tiers - 1)
        z = z_lo + (z_hi - z_lo) * f
        reach = (3.9 - 2.6 * f) * rng.uniform(0.85, 1.1) * (H / 11.5)
        nl = 4 if k < tiers - 1 else 3
        a0 = rng.uniform(0, 2 * math.pi)
        for j in range(nl):
            a = a0 + 2 * math.pi * j / nl + rng.uniform(-0.35, 0.35)
            base, rb = on_trunk(z)
            rise = math.radians(rng.uniform(4, 12))
            L = reach * rng.uniform(0.75, 1.05)
            lp, lr = [], []
            m = 7
            for s in range(m):
                t = s / (m - 1)
                droop = -0.3 * t * t + 0.35 * t ** 4
                lp.append(base + Vector((math.cos(a), math.sin(a), 0)) * (L * t) + Vector((0, 0, math.tan(rise) * L * t + droop)))
                lr.append(max(0.03, rb * 0.42 * (1 - 0.75 * t)))
            lp[0] = base + Vector((math.cos(a), math.sin(a), 0)) * rb * 0.3
            tube(R, f'limb:{li}', 'bark', lp, lr, segs=8)
            # a flat pad of needle sprays on the outer half of every limb: the tiers read as layers with sky between
            for s in range(3, m):
                q = lp[s]
                for side in (-1, 1):
                    if rng.random() < 0.45:
                        ta = a + side * rng.uniform(0.7, 1.2)
                        tl = rng.uniform(0.5, 0.9) * (1 - 0.3 * f)
                        tp = [q, q + Vector((math.cos(ta), math.sin(ta), 0.05)) * tl * 0.5, q + Vector((math.cos(ta), math.sin(ta), 0.08)) * tl]
                        tube(R, f'twig:{li}:{s}:{side}', 'bark', tp, [lr[s] * 0.55, lr[s] * 0.4, 0.014], segs=5)
                        cards.append((tp[-1], Vector((rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), 1)), rng.uniform(0.85, 1.15), ta - math.pi / 2, 0, 0))
                cards.append((q + Vector((rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), 0.03)),
                              Vector((rng.uniform(-0.22, 0.22), rng.uniform(-0.22, 0.22), 1)), rng.uniform(1.0, 1.3), a - math.pi / 2 + rng.uniform(-0.5, 0.5), 0, 0))
            li += 1
    # a crown tuft at the leader
    for c in range(4):
        cards.append((pts[-1] + Vector((rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), rng.uniform(-0.3, 0.05))),
                      Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 1)), rng.uniform(0.8, 1.1), rng.uniform(0, 6.28), 0, 0))
    # row from height in the crown and from facing: top lit, under-tiers shaded
    zs = [c[0].z for c in cards]
    zmin, zmax = min(zs), max(zs)
    out = []
    for (c, nn, s, spin, _, _) in cards:
        f = (c.z - zmin) / max(1e-3, zmax - zmin)
        outer = Vector((c.x, c.y, 0)).length / 4.0
        lit = f * 0.7 + outer * 0.4 + rng.uniform(-0.2, 0.2)
        row = 0 if lit > 0.62 else (1 if lit > 0.3 else 2)
        out.append((c, nn, s, spin, row, rng.randrange(CARD_COLS)))
    meta = dict(height=H, cards=len(out))
    name_cards = {}

    def make_cards(name):
        return card_object(name + '_cards', out)
    return R, meta, {'cards': make_cards}


def snag(seed):
    rng = kit.stream(seed, 'snag')
    R = kit.Rec()
    H = rng.uniform(5.5, 7.5)
    pts = [Vector((math.sin(t * 2.5) * 0.25 * t, math.cos(t * 1.7) * 0.2 * t, -0.4 + (H + 0.4) * t)) for t in [i / 11 for i in range(12)]]
    rad = [0.34 * (1 - 0.6 * (i / 11)) + 0.04 for i in range(12)]
    ph = rng.uniform(0, 6)
    lobe = lambda wa, t: 1 + 0.5 * max(0.0, 1 - t / 0.15) ** 2 * max(0.0, math.cos(5 * wa + ph)) ** 2 + 0.06 * math.sin(wa * 7 + t * 20)
    tube(R, 'trunk', 'timber', pts, rad, segs=16, lobe=lobe, cap0=False, jag=0.45, rng=rng)
    for k in range(4):
        z = H * rng.uniform(0.4, 0.85)
        i = int(z / H * 11)
        a = rng.uniform(0, 6.28)
        L = rng.uniform(0.5, 1.6)
        b = pts[i]
        tp = [b, b + Vector((math.cos(a), math.sin(a), 0.25)) * L]
        tube(R, f'stub:{k}', 'timber', tp, [rad[i] * 0.4, rad[i] * 0.22], segs=7, jag=0.1, rng=rng)
    return R, dict(height=H)


# ---------------------------------------------------------------- bladder lilies
def revolve_partial(R, part, slot, prof, a0, a1, segs, M):
    """Revolve a closed profile [(r, z)] from a0 to a1 and cap both cut ends."""
    bm = R.bm
    rings = []
    for i in range(segs + 1):
        a = a0 + (a1 - a0) * i / segs
        rings.append([bm.verts.new(M @ Vector((r * math.cos(a), r * math.sin(a), z))) for (r, z) in prof])
    faces = []
    m = len(prof)
    for i in range(segs):
        A, B = rings[i], rings[i + 1]
        for j in range(m):
            faces.append(bm.faces.new((A[j], B[j], B[(j + 1) % m], A[(j + 1) % m])))
    faces.append(bm.faces.new(rings[0]))
    faces.append(bm.faces.new(list(reversed(rings[-1]))))
    R.tag(faces, part, slot, M.to_3x3() @ Vector((1, 0, 0)))
    return faces


def lilies(seed):
    rng = kit.stream(seed, 'lilies')
    R = kit.Rec()
    placed = []
    for k in range(9):
        for _ in range(30):
            r = rng.uniform(0.35, 1.25) if k else 1.5
            c = Vector((rng.uniform(-2.4, 2.4), rng.uniform(-2.4, 2.4), 0)) if k else Vector((0, 0, 0))
            if all((c - p).length > r + q - 0.05 for p, q in placed):
                break
        else:
            continue
        placed.append((c, r))
        rim = 0.08 + r * 0.05
        prof = [(0.03, 0.012), (0.55 * r, 0.01), (0.9 * r, 0.018), (r, rim), (r - 0.022, rim), (0.88 * r, 0.004), (0.5 * r, -0.008), (0.03, -0.012)]
        notch = rng.uniform(0, 6.28)
        M = Matrix.Translation(c) @ Matrix.Rotation(notch, 4, 'Z') @ Matrix.Rotation(rng.uniform(-0.02, 0.02), 4, 'X')
        revolve_partial(R, f'pad:{k}', 'pad', prof, math.radians(9), math.radians(351), 40, M)
    for k in range(2):
        c, r = placed[rng.randrange(1, len(placed))] if len(placed) > 1 else placed[0]
        base = c + Vector((r + 0.15, 0, 0))
        h = rng.uniform(0.45, 0.8)
        top = base + Vector((rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), h))
        tube(R, f'stalk:{k}', 'moss', [base - Vector((0, 0, 0.1)), base.lerp(top, 0.5) + Vector((0.05, 0, 0)), top], [0.022, 0.02, 0.018], segs=6)
        lathe(R, f'sepal:{k}', 'pad', [(0.02, -0.02), (0.1, 0.02), (0.13, 0.07)], 8, M=Matrix.Translation(top), close_top=False, close_bottom=True,
              wob=lambda a, z: 1 + 0.3 * abs(math.cos(a * 2)))
        lathe(R, f'bloom:{k}', 'flower', [(0.03, 0.0), (0.12, 0.05), (0.19, 0.13), (0.21, 0.21), (0.15, 0.25), (0.06, 0.18)], 24,
              M=Matrix.Translation(top + Vector((0, 0, 0.02))), close_top=False, wob=lambda a, z: 1 + 0.22 * abs(math.cos(a * 4)))
        lathe(R, f'heart:{k}', 'lichen', [(0.0001, 0.12), (0.06, 0.13), (0.04, 0.19), (0.0001, 0.2)], 10, M=Matrix.Translation(top), close_top=False)
    return R, dict(pads=len(placed))


# ---------------------------------------------------------------- pitchers on a sphagnum hummock
def hummock(R, rng, rad, h, name='hummock'):
    s0 = rng.uniform(0, 100)
    wob = lambda a, z: 1 + 0.16 * noise.noise(Vector((math.cos(a) * 1.5 + s0, math.sin(a) * 1.5, z * 2)))
    prof = [(rad * 1.05, -0.25), (rad, 0.0), (rad * 0.9, h * 0.45), (rad * 0.7, h * 0.8), (rad * 0.4, h * 0.97), (0.0001, h)]
    lathe(R, name, 'sphag', prof, 28, wob=wob, close_top=False, close_bottom=False)


def pitchers(seed):
    rng = kit.stream(seed, 'pitchers')
    R = kit.Rec()
    hummock(R, rng, 0.9, 0.32)
    for k in range(rng.randrange(6, 10)):
        a, d = rng.uniform(0, 6.28), rng.uniform(0, 0.5)
        h = rng.uniform(0.35, 0.85)
        b = P(d, a, 0.28 - d * 0.35)
        tilt = Matrix.Rotation(rng.uniform(-0.15, 0.15), 4, 'X') @ Matrix.Rotation(rng.uniform(-0.15, 0.15), 4, 'Y')
        M = Matrix.Translation(b) @ Matrix.Rotation(rng.uniform(0, 6.28), 4, 'Z') @ tilt
        w = rng.uniform(0.055, 0.08)
        prof = [(0.0001, -0.05), (w * 0.6, 0.0), (w, h * 0.3), (w * 1.1, h * 0.65), (w * 0.95, h * 0.9), (w * 1.25, h), (w * 1.2, h + 0.012),
                (w * 0.85, h - 0.01), (w * 0.8, h * 0.7), (w * 0.6, h * 0.5)]
        lathe(R, f'pitcher:{k}', 'pitcher', prof, 14, M=M, close_top=True, close_bottom=False, g=(0, 0, 1))
        # the hood leans over the mouth
        hood = M @ Matrix.Translation((-w * 0.6, 0, h + 0.07)) @ Matrix.Rotation(-0.55, 4, 'Y')
        box(R, f'hood:{k}', 'pitcher', hood, (w * 2.2, w * 2.1, 0.012), e=0.004, g=(1, 0, 0))
    for k in range(10):
        a = k * 0.63 + rng.uniform(-0.2, 0.2)
        p0 = P(0.15, a, 0.27)
        p1 = P(0.55 + rng.uniform(0, 0.2), a, 0.2)
        beam(R, f'leaf:{k}', 'pad', p0, p1, 0.07, 0.012, e=0.003, roll=0.2)
    return R, dict(), None


def sundew_hummock(seed):
    rng = kit.stream(seed, 'sundew')
    R = kit.Rec()
    rad = rng.uniform(1.0, 1.4)
    hummock(R, rng, rad, rng.uniform(0.32, 0.5))
    for k in range(rng.randrange(7, 12)):
        a, d = rng.uniform(0, 6.28), rng.uniform(0, rad * 0.7)
        z = 0.42 * (1 - (d / rad) ** 2) * 0.95
        c = P(d, a, z)
        for j in range(8):
            la = j * math.pi / 4 + rng.uniform(-0.2, 0.2)
            q = c + P(0.07, la, 0.025)
            cyl(R, f'dew:{k}:{j}', 'sundew', c, q, 0.008, segs=4)
            lathe(R, f'dewpad:{k}:{j}', 'sundew', [(0.0001, -0.008), (0.022, 0.0), (0.0001, 0.008)], 6, M=Matrix.Translation(q), close_top=False)
    # cotton-grass on the top of the hummock
    for k in range(rng.randrange(5, 9)):
        a, d = rng.uniform(0, 6.28), rng.uniform(0, rad * 0.5)
        c = P(d, a, 0.3)
        h = rng.uniform(0.35, 0.6)
        top = c + Vector((rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08), h))
        tube(R, f'cstem:{k}', 'sedge', [c, c.lerp(top, 0.5), top], [0.012, 0.01, 0.008], segs=4)
        lathe(R, f'cotton:{k}', 'fleece', [(0.0001, -0.02), (0.05, 0.02), (0.06, 0.07), (0.035, 0.11), (0.0001, 0.12)], 9, M=Matrix.Translation(top), close_top=False,
              wob=lambda aa, zz, s=rng.random() * 9: 1 + 0.25 * math.sin(aa * 5 + s + zz * 30))
    return R, dict(), None


def tussock(seed):
    rng = kit.stream(seed, 'tussock')
    R = kit.Rec()
    hummock(R, rng, 0.42, 0.22, name='base')
    for k in range(70):
        a = rng.uniform(0, 6.28)
        d = rng.uniform(0, 0.3)
        c = P(d, a, 0.18 - d * 0.2)
        L = rng.uniform(0.55, 1.15)
        out = rng.uniform(0.15, 0.6) + d
        pts = []
        for s in range(5):
            t = s / 4
            pts.append(c + P(out * L * t * 0.8, a, L * t - (t ** 2) * out * L * 0.55))
        tube(R, f'blade:{k}', 'sedge', pts, [0.018, 0.016, 0.012, 0.008, 0.002], segs=3, cap1=False)
    return R, dict(), None


def boulder(seed, variant):
    rng = kit.stream(seed, 'boulder:' + variant)
    R = kit.Rec()
    bm = R.bm
    res = bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    s0 = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
    sc = Vector((rng.uniform(1.0, 1.5), rng.uniform(0.8, 1.2), rng.uniform(0.55, 0.8)))
    for v in res['verts']:
        p = v.co.copy()
        k = 1 + 0.28 * noise.noise(p * 1.1 + s0) + 0.08 * noise.noise(p * 3.3 + s0)
        # glacial erratic: planed facets
        for ax in (Vector((0.6, 0.2, 0.75)), Vector((-0.5, 0.6, 0.6)), Vector((0.2, -0.8, 0.5))):
            d = p.dot(ax.normalized())
            if d > 0.62:
                k = min(k, 0.62 / max(d, 1e-3) * 1.05)
        p = p * k
        p.x *= sc.x
        p.y *= sc.y
        p.z = p.z * sc.z if p.z > 0 else p.z * 0.4
        v.co = p * 1.0
    R.tag(R.faces_of(res['verts']), 'stone', 'stone', (1, 0, 0))
    return R, dict(), None


def _card_png(path):
    paint_cards(path, 7, 'needle')


ASSETS = {}
for v in ('a', 'b', 'c'):
    ASSETS['tallow_' + v] = dict(fn=lambda v=v: tallow('ambermere', v), size=2048, cfg=dict(ground=0.0),
                                 card_png=_card_png, card_finish=card_finish)
ASSETS['snag'] = dict(fn=lambda: (*snag('ambermere'), None), size=1024, cfg=dict(ground=0.0))
ASSETS['lilies'] = dict(fn=lambda: (*lilies('ambermere'), None), size=1024)
ASSETS['pitchers'] = dict(fn=lambda: pitchers('ambermere'), size=1024, cfg=dict(pit_z0=0.3, pit_z1=0.55))
ASSETS['sundews'] = dict(fn=lambda: sundew_hummock('ambermere'), size=1024)
ASSETS['tussock'] = dict(fn=lambda: tussock('ambermere'), size=1024)
for v in ('a', 'b'):
    ASSETS['boulder_' + v] = dict(fn=lambda v=v: boulder('ambermere', v), size=1024)
