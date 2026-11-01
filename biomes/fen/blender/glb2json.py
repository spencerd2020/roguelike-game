"""Turn .glb files into self-contained glTF JSON (the binary chunk as a base64 data URI), for hosts that only serve .json.

usage: python glb2json.py OUTDIR file.glb [...]
"""
import base64, json, os, struct, sys

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for path in sys.argv[2:]:
    b = open(path, 'rb').read()
    n = struct.unpack('<I', b[12:16])[0]
    j = json.loads(b[20:20 + n])
    rest = b[20 + n:]
    blen = struct.unpack('<I', rest[:4])[0]
    binary = rest[8:8 + blen]
    j['buffers'] = [{'byteLength': len(binary), 'uri': 'data:application/octet-stream;base64,' + base64.b64encode(binary).decode()}]
    name = os.path.splitext(os.path.basename(path))[0] + '.json'
    json.dump(j, open(os.path.join(out, name), 'w'), separators=(',', ':'))
