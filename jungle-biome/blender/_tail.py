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
