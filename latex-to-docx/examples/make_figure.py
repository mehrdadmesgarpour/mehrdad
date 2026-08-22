"""Generate figure.png (a damped-oscillation plot) for sample.tex.

Uses only the Python standard library, so it runs anywhere.
"""
import math
import struct
import zlib
from pathlib import Path

W, H = 640, 400
BG = (255, 255, 255)
AXIS = (70, 70, 70)
GRID = (225, 225, 225)
CURVE = (31, 119, 180)

px = [[BG for _ in range(W)] for _ in range(H)]


def put(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        px[y][x] = c


# plot area margins
L, R, T, B = 60, 20, 20, 40

# grid
for gx in range(L, W - R + 1, (W - R - L) // 8):
    for y in range(T, H - B):
        put(gx, y, GRID)
for gy in range(T, H - B + 1, (H - B - T) // 6):
    for x in range(L, W - R):
        put(x, gy, GRID)

# axes
for x in range(L, W - R):
    put(x, H - B, AXIS)
    put(x, H - B + 1, AXIS)
for y in range(T, H - B):
    put(L, y, AXIS)
    put(L - 1, y, AXIS)

# damped sine curve: y = exp(-t) * cos(2*pi*t), t in [0, 3]
mid = T + (H - B - T) // 2
amp = (H - B - T) // 2 - 10
prev = None
for i in range(L, W - R):
    t = 3.0 * (i - L) / (W - R - L)
    v = math.exp(-t) * math.cos(2 * math.pi * t)
    j = int(mid - amp * v)
    if prev is not None:
        j0, j1 = sorted((prev, j))
        for jj in range(j0, j1 + 1):
            for d in (-1, 0, 1):
                put(i, jj + d, CURVE)
    prev = j

# encode as PNG
raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in px)


def chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data)))


png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 9))
       + chunk(b"IEND", b""))

out = Path(__file__).with_name("figure.png")
out.write_bytes(png)
print(f"wrote {out} ({len(png)} bytes)")
