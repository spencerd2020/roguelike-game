"""GLB -> self-contained glTF JSON (buffer as a data URI), the form artifacts can serve. usage: glb2json.py in.glb out.json"""
import base64, json, struct, sys
b = open(sys.argv[1], 'rb').read()
assert b[:4] == b'glTF'
off, js, bin_ = 12, None, b''
while off < len(b):
    ln, typ = struct.unpack_from('<II', b, off)
    chunk = b[off + 8: off + 8 + ln]
    if typ == 0x4E4F534A: js = json.loads(chunk)
    elif typ == 0x004E4942: bin_ = chunk
    off += 8 + ln
js['buffers'][0]['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(bin_).decode()
open(sys.argv[2], 'w').write(json.dumps(js, separators=(',', ':')))
