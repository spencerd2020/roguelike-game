"""Grow every atlas island's paint outwards into the empty space round it, so mipmaps never pull in the background colour
(the dark seams that showed on lime walls at a distance). Reads a kit glb, rasterises its own UV triangles to find the
painted area, dilates the colours 32 px, and writes the glb back with the same nodes and materials.

usage: python fix_seams.py in.glb [out.glb] [--png atlas.png]   (with --png, the lossless atlas from the build is used)
"""
import sys, os
import numpy as np
import bpy
from PIL import Image, ImageDraw

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
png = None
if '--png' in argv:
    i = argv.index('--png'); png = argv[i + 1]; del argv[i:i + 2]
src = argv[0]
dst = argv[1] if len(argv) > 1 else src

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
bpy.ops.import_scene.gltf(filepath=src)
mat = bpy.data.materials.get('atlas')
tex = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE')
im = tex.image
W, H = im.size
if png:
    src_rgb = np.asarray(Image.open(png).convert('RGB')).astype(np.float32) / 255.0
    src_rgb = src_rgb[::-1]                       # PIL rows run top down, Blender's bottom up
else:
    px = np.array(im.pixels[:], np.float32).reshape(H, W, 4)
    src_rgb = px[..., :3]

mask = Image.new('L', (W, H), 0)
d = ImageDraw.Draw(mask)
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    me = o.data
    uv = me.uv_layers.active.data
    for poly in me.polygons:
        if me.materials[poly.material_index].name != 'atlas':
            continue
        pts = [(uv[li].uv[0] * W, uv[li].uv[1] * H) for li in poly.loop_indices]
        d.polygon(pts, fill=255, outline=255)
m = np.asarray(mask) > 0                          # rows in uv space, bottom up like Blender's pixels
# every empty pixel takes the colour of the nearest painted one (one distance transform, exact, fast)
from scipy.ndimage import distance_transform_edt
_, (iy, ix) = distance_transform_edt(~m, return_indices=True)
rgb = src_rgb[iy, ix]
out = np.concatenate([rgb, np.ones((H, W, 1), np.float32)], 2)
new = bpy.data.images.new('atlas_fixed', W, H, alpha=False)
new.pixels.foreach_set(out.ravel())
new.pack()
tex.image = new
tex.interpolation = 'Closest'
for o in bpy.data.objects:
    o.select_set(o.type == 'MESH')
bpy.ops.export_scene.gltf(filepath=dst, export_format='GLB', use_selection=True, export_image_format='JPEG', export_jpeg_quality=90,
                          export_normals=True, export_texcoords=True, export_vertex_color='NONE')
print('fixed', dst, os.path.getsize(dst), 'covered', round(m.mean(), 3))
