"""Turn .glb files into self-contained glTF JSON (the binary chunk as a base64 data URI), for hosts that only serve .json.
--max-tex N shrinks any texture larger than N px (nearest, palette kept), so the web page stays light enough for phones.

usage: python glb2json.py OUTDIR [--max-tex 2048] file.glb [...]
"""
import base64, io, json, os, struct, sys


def shrink(png, max_px):
    from PIL import Image
    im = Image.open(io.BytesIO(png))
    if max(im.size) <= max_px:
        return png
    f = max_px / max(im.size)
    mode = im.mode
    im = im.convert('RGBA').resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.NEAREST)
    if mode == 'P' or len(im.getcolors(1 << 16) or []) <= 256:
        a = im.getchannel('A')
        if a.getextrema() == (255, 255):
            im = im.convert('RGB').quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = io.BytesIO()
    im.save(out, 'PNG', optimize=True)
    return out.getvalue()


def convert(path, out, max_px=0):
    b = open(path, 'rb').read()
    n = struct.unpack('<I', b[12:16])[0]
    j = json.loads(b[20:20 + n])
    rest = b[20 + n:]
    blen = struct.unpack('<I', rest[:4])[0]
    binary = rest[8:8 + blen]
    if max_px:
        img_views = {im['bufferView'] for im in j.get('images', []) if 'bufferView' in im}
        chunks = []
        for i, bv in enumerate(j['bufferViews']):
            data = binary[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]
            if i in img_views:
                data = shrink(data, max_px)
            chunks.append(data)
        nb = bytearray()
        for bv, data in zip(j['bufferViews'], chunks):
            while len(nb) % 4:
                nb.append(0)
            bv['byteOffset'] = len(nb)
            bv['byteLength'] = len(data)
            nb += data
        binary = bytes(nb)
    j['buffers'] = [{'byteLength': len(binary), 'uri': 'data:application/octet-stream;base64,' + base64.b64encode(binary).decode()}]
    name = os.path.splitext(os.path.basename(path))[0] + '.json'
    json.dump(j, open(os.path.join(out, name), 'w'), separators=(',', ':'))


if __name__ == '__main__':
    args = sys.argv[1:]
    out = args.pop(0)
    max_px = 0
    if args and args[0] == '--max-tex':
        args.pop(0)
        max_px = int(args.pop(0))
    os.makedirs(out, exist_ok=True)
    for p in args:
        convert(p, out, max_px)
