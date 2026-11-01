"""Geometry kit for the Vanehold Pass assets (Blender 5.x, bpy as a module).

Every primitive is a closed solid with chamfered edges, tagged per face with a material slot, a part id and a grain axis.
The painter later reads those per texel, so each stone, board and shingle gets its own tone, grain and wear.
"""
import math
import random
import zlib

import bpy
import bmesh
from mathutils import Matrix, Vector


def stream(seed, stage):
    """One random stream per stage, hashed from the seed and the stage name, so stages never reshuffle each other."""
    return random.Random(zlib.crc32(f'{seed}/{stage}'.encode()))


def V(x, y, z):
    return Vector((x, y, z))


def frame(direction, up=(0, 0, 1)):
    """3x3 rotation taking +Z onto direction, with +X kept as level as possible."""
    d = Vector(direction).normalized()
    u = Vector(up)
    if abs(d.dot(u)) > 0.98:
        u = Vector((1, 0, 0))
    x = u.cross(d).normalized()
    y = d.cross(x)
    return Matrix((x, y, d)).transposed()


class Kit:
    def __init__(self, slots, glow=()):
        self.bm = bmesh.new()
        self.slots = list(slots)
        self.glow = set(glow)               # slots kept as flat glowing materials, outside the atlas
        self.SI = {s: i for i, s in enumerate(self.slots)}
        self.L_part = self.bm.faces.layers.float.new('part')
        self.L_ax = [self.bm.faces.layers.float.new(n) for n in ('ax', 'ay', 'az')]
        self.L_node = self.bm.faces.layers.int.new('node')
        self.node = 0                        # which exported node the next primitives belong to (0 = the main body)
        self.nodes = ['body']
        self.parts = ['none']
        self.lights = []                     # (pos, colour, watts, radius) lamps used only by the light bake
        self.markers = {}

    # ---------- bookkeeping ----------
    def part(self, name):
        self.parts.append(name)
        return len(self.parts) - 1

    def tag(self, faces, slot, part, axis):
        si = self.SI[slot]
        ax = Vector(axis).normalized() if Vector(axis).length > 1e-6 else Vector((0, 0, 1))
        for f in faces:
            f.material_index = si
            f[self.L_part] = float(part)
            f[self.L_node] = self.node
            for k in range(3):
                f[self.L_ax[k]] = ax[k]

    def _bevel(self, verts, e):
        if e <= 0:
            return
        edges = list({ed for v in verts for ed in v.link_edges})
        bmesh.ops.bevel(self.bm, geom=list(verts) + edges, offset=e, offset_type='OFFSET', segments=1,
                        profile=0.5, affect='EDGES', clamp_overlap=True)

    # ---------- primitives ----------
    def box(self, c, size, rot=None, slot='stone', name='box', e=0.0, axis=None, part=None):
        """Chamfered box centred on c, size (sx, sy, sz) in its own frame, rot a 3x3 matrix."""
        rot = rot if rot is not None else Matrix.Identity(3)
        m = Matrix.Translation(Vector(c)) @ rot.to_4x4() @ Matrix.Diagonal(Vector((*size, 1)))
        res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        vs = res['verts']
        faces = list({f for v in vs for f in v.link_faces})
        if axis is None:   # grain along the longest side
            k = max(range(3), key=lambda i: size[i])
            axis = rot.col[k]
        pid = part if part is not None else self.part(name)
        self.tag(faces, slot, pid, axis)
        self._bevel(vs, min(e, 0.45 * min(size)))
        return pid

    def beam(self, p0, p1, w, d, slot='wood', name='beam', e=0.012, roll=0.0, part=None):
        p0, p1 = Vector(p0), Vector(p1)
        L = (p1 - p0).length
        R = frame(p1 - p0) @ Matrix.Rotation(roll, 3, 'Z')
        return self.box((p0 + p1) / 2, (w, d, L), R, slot, name, e, axis=p1 - p0, part=part)

    def prism(self, base, direction, length, r1, r2, slot='stone', name='prism', segs=6, spin=0.0, e=0.0, part=None):
        R = frame(direction) @ Matrix.Rotation(spin, 3, 'Z')
        m = Matrix.Translation(Vector(base)) @ R.to_4x4() @ Matrix.Translation((0, 0, length / 2))
        res = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=segs, radius1=max(r1, 1e-4),
                                    radius2=max(r2, 1e-4), depth=length, matrix=m)
        vs = res['verts']
        faces = list({f for v in vs for f in v.link_faces})
        pid = part if part is not None else self.part(name)
        self.tag(faces, slot, pid, direction)
        self._bevel(vs, min(e, 0.3 * min(r1, r2 if r2 > 1e-3 else r1)))
        return pid

    def slab(self, pts, h, slot='stone', name='slab', e=0.0, up=(0, 0, 1), axis=None, part=None):
        """Closed prism from a convex outline (list of 3D points, counter-clockwise seen from up) extruded by h."""
        up = Vector(up).normalized() * h
        bot = [self.bm.verts.new(Vector(p)) for p in pts]
        top = [self.bm.verts.new(Vector(p) + up) for p in pts]
        n = len(pts)
        faces = [self.bm.faces.new(top), self.bm.faces.new(list(reversed(bot)))]
        for i in range(n):
            j = (i + 1) % n
            faces.append(self.bm.faces.new((bot[i], bot[j], top[j], top[i])))
        pid = part if part is not None else self.part(name)
        self.tag(faces, slot, pid, axis if axis is not None else (Vector(pts[1]) - Vector(pts[0])))
        self._bevel(bot + top, e)
        return pid

    def rock(self, c, r, rng, slot='stone', name='rock', subd=1, squash=(1, 1, 1), jag=0.25, part=None):
        """Faceted boulder: an icosphere pushed about by noise, flat facets kept on purpose."""
        res = bmesh.ops.create_icosphere(self.bm, subdivisions=subd, radius=1.0,
                                         matrix=Matrix.Translation(Vector(c)))
        vs = res['verts']
        ph = [rng.uniform(0, 6.28) for _ in range(6)]
        for v in vs:
            d = v.co - Vector(c)
            k = 1 + jag * (math.sin(d.x * 2.1 + ph[0]) * math.sin(d.y * 2.3 + ph[1]) + 0.6 * math.sin(d.z * 3.1 + ph[2])
                           + 0.4 * math.sin((d.x + d.z) * 4.3 + ph[3])) / 2
            v.co = Vector(c) + Vector((d.x * squash[0], d.y * squash[1], d.z * squash[2])) * r * k
        faces = list({f for v in vs for f in v.link_faces})
        pid = part if part is not None else self.part(name)
        self.tag(faces, slot, pid, (0, 0, 1))
        return pid

    def tube(self, pts, radius, slot='rope', name='rope', segs=5, part=None):
        """Rope or rod along a polyline, rotation-minimising frames, capped."""
        pts = [Vector(p) for p in pts]
        rings, prev = [], None
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            if prev is None:
                a = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
                nrm = t.cross(a).normalized()
            else:
                nrm = (prev - t * prev.dot(t)).normalized()
            prev = nrm
            b = t.cross(nrm)
            r = radius[i] if isinstance(radius, (list, tuple)) else radius
            rings.append([self.bm.verts.new(p + (nrm * math.cos(2 * math.pi * k / segs) + b * math.sin(2 * math.pi * k / segs)) * r)
                          for k in range(segs)])
        faces = []
        for a, b in zip(rings, rings[1:]):
            for k in range(segs):
                faces.append(self.bm.faces.new((a[k], a[(k + 1) % segs], b[(k + 1) % segs], b[k])))
        faces.append(self.bm.faces.new(list(reversed(rings[0]))))
        faces.append(self.bm.faces.new(rings[-1]))
        pid = part if part is not None else self.part(name)
        self.tag(faces, slot, pid, pts[-1] - pts[0])
        return pid

    def use_node(self, name):
        """Primitives from here on go to a separate exported node (a cutaway roof, a turning rotor)."""
        if name not in self.nodes:
            self.nodes.append(name)
        self.node = self.nodes.index(name)

    def light(self, pos, colour=(1.0, 0.62, 0.3), watts=120.0, radius=0.15):
        self.lights.append((tuple(pos), colour, watts, radius))

    # ---------- output ----------
    def to_object(self, name):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        for p in me.polygons:
            p.use_smooth = False
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
        for s in self.slots:
            mat = bpy.data.materials.get('bake_' + s) or bpy.data.materials.new('bake_' + s)
            me.materials.append(mat)
        obj['parts'] = len(self.parts)
        return obj
