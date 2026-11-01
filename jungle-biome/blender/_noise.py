hexrgb = lambda h: [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
RAMPS = {k: np.array([hexrgb(c) for c in v], np.float32) for k, v in RAMPS.items()}
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16 - 0.5)


def _hash(ix, iy, iz, s):
    h = (ix * 374761393 + iy * 668265263 + iz * 1442695041 + s * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def noise3(p, s=0):
    """Value noise in 3D, -1..1. p: (n, 3)."""
    fl = np.floor(p)
    f = p - fl
    f = f * f * (3 - 2 * f)
    i = fl.astype(np.int64)
    out = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                out = out + w * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, s)
    return out * 2 - 1


def fbm(p, oct=4, s=0):
    v, a, t = 0, 0.5, 0
    for o in range(oct):
        v = v + a * noise3(p * (2 ** o), s + o * 31)
        t += a
        a *= 0.5
    return v / t


def cells(p, s=0):
    """Distance to the nearest and second nearest feature point (3D worley, 27 cells)."""
    fl = np.floor(p).astype(np.int64)
    f1 = np.full(len(p), 9.0, np.float32)
    f2 = np.full(len(p), 9.0, np.float32)
    idc = np.zeros(len(p), np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = fl + np.array([dx, dy, dz])
                fp = c + np.stack([_hash(c[:, 0], c[:, 1], c[:, 2], s + k) for k in (1, 2, 3)], 1)
                d = np.linalg.norm(fp - p, axis=1)
                hid = _hash(c[:, 0], c[:, 1], c[:, 2], s + 9)
                closer = d < f1
                f2 = np.where(closer, f1, np.minimum(f2, d))
                idc = np.where(closer, hid, idc)
                f1 = np.where(closer, d, f1)
    return f1, f2, idc


sm = lambda a, b, x: np.clip((x - a) / (b - a), 0, 1) ** 2 * (3 - 2 * np.clip((x - a) / (b - a), 0, 1))
