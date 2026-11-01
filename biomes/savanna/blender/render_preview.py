"""Cycles previews for the savanna kit: an outside view, and for houses a view from inside and a roof-off cutaway."""
import math
import bpy
from mathutils import Vector


def _cam(scene, loc, target, lens=35):
    cam = bpy.data.cameras.new('cam')
    cam.lens = lens
    cam.clip_start = 0.05
    co = bpy.data.objects.new('cam', cam)
    scene.collection.objects.link(co)
    co.location = loc
    d = Vector(target) - Vector(loc)
    co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = co
    return co


def place_furniture(scene, info, props_dir):
    """Stand the shared props where the generator put them (previews only; the house glb never carries them)."""
    import os
    src = {}
    for f in info.get('furniture', []):
        if f['prop'] not in src:
            path = os.path.join(props_dir, f['prop'] + '.glb')
            if not os.path.exists(path):
                print('no prop', path); continue
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=path)
            new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
            src[f['prop']] = new[0]
            new[0].location = (0, 0, -100)
        o = src[f['prop']].copy()
        scene.collection.objects.link(o)
        o.location = f['pos']
        o.rotation_mode = 'XYZ'
        o.rotation_euler = (0, 0, f['yaw'])


def render(scene, objs, base, info, clay=False, props_dir=None):
    if props_dir and not clay:
        place_furniture(scene, info, props_dir)
    scene.render.resolution_x, scene.render.resolution_y = 960, 640
    scene.cycles.samples = 48
    scene.cycles.max_bounces = 4
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast' if 'AgX - Medium High Contrast' in [x for x in ('AgX - Medium High Contrast',)] else 'None'
    world = scene.world
    bg = world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.55, 0.7, 0.95, 1)
    bg.inputs[1].default_value = 0.9
    sun = bpy.data.lights.new('key', 'SUN')
    sun.energy = 4.5
    sun.color = (1.0, 0.93, 0.8)
    sun.angle = math.radians(3)
    so = bpy.data.objects.new('key', sun)
    so.rotation_euler = (math.radians(50), 0, math.radians(-40))
    scene.collection.objects.link(so)
    # ground
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.02))
    gnd = bpy.context.active_object
    gm = bpy.data.materials.new('ground')
    gm.use_nodes = True
    gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.35, 0.18, 0.09, 1)
    gnd.data.materials.append(gm)
    if clay:
        cm = bpy.data.materials.new('clay')
        for o in objs:
            o.data.materials.clear()
            o.data.materials.append(cm)
    (x0, y0, z0), (x1, y1, z1) = info['bounds']
    size = max(x1 - x0, y1 - y0, z1 - z0)
    c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    _cam(scene, c + Vector((size * 1.1, size * 1.25, size * 0.55)), c - Vector((0, 0, size * 0.08)), 35)
    scene.render.filepath = base + '_out.png'
    bpy.ops.render.render(write_still=True)
    if 'markers' in info:
        mk = info['markers']
        eye = Vector(mk['eye'])
        _cam(scene, eye, Vector(mk['hearth']) + (Vector(mk['hearth']) - eye) * 1.2 + Vector((0, 0, 0.4)), 16)
        bg.inputs[1].default_value = 1.4
        fire = bpy.data.lights.new('fire', 'POINT')
        fire.energy = 160
        fire.color = (1.0, 0.55, 0.25)
        fire.shadow_soft_size = 0.3
        fo = bpy.data.objects.new('fire', fire)
        fo.location = Vector(mk['hearth']) + Vector((0, 0, 0.25))
        scene.collection.objects.link(fo)
        scene.view_settings.exposure = 1.3
        scene.render.filepath = base + '_in.png'
        bpy.ops.render.render(write_still=True)
        for o in objs:
            if o.name in ('roof', 'dome'):
                o.hide_render = True
        _cam(scene, c + Vector((size * 0.45, size * 0.6, size * 0.9)), Vector((0, 0, info['floor'] + 0.3)), 30)
        scene.view_settings.exposure = 0.0
        scene.render.filepath = base + '_cut.png'
        bpy.ops.render.render(write_still=True)
