"""Turn kit and prop glb files into what the published page can serve: a glTF JSON file with its geometry embedded as
base64 and each texture as its own .jpg or .png file next to it (the artifact host serves JSON and images, not .glb).

usage: python glb_to_page.py out_dir file.glb [file.glb ...]    -> out_dir/<name>.json + out_dir/<name>_<i>.<ext>
"""
import base64, json, os, struct, sys

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for path in sys.argv[2:]:
    name = os.path.splitext(os.path.basename(path))[0]
    data = open(path, 'rb').read()
    jl = struct.unpack('<I', data[12:16])[0]
    j = json.loads(data[20:20 + jl])
    bl = struct.unpack('<I', data[20 + jl:24 + jl])[0]
    binb = data[28 + jl:28 + jl + bl]
    views = j['bufferViews']
    img_views = {im['bufferView'] for im in j.get('images', []) if 'bufferView' in im}
    for i, im in enumerate(j.get('images', [])):
        if 'bufferView' not in im:
            continue
        v = views[im['bufferView']]
        raw = binb[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']]
        ext = 'jpg' if im.get('mimeType') == 'image/jpeg' else 'png'
        fn = f'{name}_{i}.{ext}'
        open(os.path.join(out, fn), 'wb').write(raw)
        im.pop('bufferView')
        im['uri'] = fn
    # rebuild the buffer without the image views, and renumber the views the accessors use
    remap, blob, new_views = {}, b'', []
    for i, v in enumerate(views):
        if i in img_views:
            continue
        chunk = binb[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']]
        while len(blob) % 4:
            blob += b'\0'
        nv = dict(v)
        nv['byteOffset'] = len(blob)
        blob += chunk
        remap[i] = len(new_views)
        new_views.append(nv)
    for a in j.get('accessors', []):
        if 'bufferView' in a:
            a['bufferView'] = remap[a['bufferView']]
        if 'sparse' in a:                      # morph targets: sparse indices and values point at views too
            for k in ('indices', 'values'):
                a['sparse'][k]['bufferView'] = remap[a['sparse'][k]['bufferView']]
    j['bufferViews'] = new_views
    j['buffers'] = [{'byteLength': len(blob), 'uri': 'data:application/octet-stream;base64,' + base64.b64encode(blob).decode()}]
    json.dump(j, open(os.path.join(out, name + '.json'), 'w'), separators=(',', ':'))
print('converted', len(sys.argv) - 2)
