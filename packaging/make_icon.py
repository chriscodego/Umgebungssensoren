"""Generate packaging/app.ico from scratch — standard library only.

    python packaging/make_icon.py

The result is committed, so this script only has to run when the artwork changes.
Keeping the icon generated rather than downloaded avoids an external asset with an
unclear licence and keeps the file reproducible.

Motif: a thermometer (white tube and bulb, red column) on a dark teal rounded square —
an environmental sensor display, reduced to what still reads at 16x16.

Icon entries are plain 32-bit BGRA DIBs (no PNG compression) so that every consumer
in the chain understands them: PyInstaller's resource writer, Inno Setup's
SetupIconFile, and the Windows shell.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

ICO_PATH = Path(__file__).resolve().parent / "app.ico"

#: Canonical Windows icon sizes.
SIZES = (16, 32, 48, 256)


#: Supersampling factor used for anti-aliasing. 256 px is rendered at 2x to keep the
#: pure-Python render time sane; the small sizes need the extra smoothing more.
def _oversample(size: int) -> int:
    return 2 if size >= 128 else 4


Color = tuple[int, int, int, int]

BACKGROUND: Color = (0x13, 0x4E, 0x4A, 0xFF)  # dark teal, rounded square
GLASS: Color = (0xF4, 0xF7, 0xF8, 0xFF)  # near-white thermometer glass
COLUMN: Color = (0xE5, 0x48, 0x3B, 0xFF)  # red column
TICK: Color = (0x9F, 0xD8, 0xCF, 0xFF)  # light teal scale marks

#: Layers in painting order, each ``(x0, y0, x1, y1, radius, colour)`` in unit coords.
#: A rectangle whose radius is half its width is a circle (the bulb).
LAYERS: tuple[tuple[float, float, float, float, float, Color], ...] = (
    (0.02, 0.02, 0.98, 0.98, 0.18, BACKGROUND),
    (0.64, 0.24, 0.80, 0.30, 0.03, TICK),
    (0.64, 0.38, 0.76, 0.44, 0.03, TICK),
    (0.64, 0.52, 0.80, 0.58, 0.03, TICK),
    (0.40, 0.10, 0.60, 0.70, 0.10, GLASS),
    (0.32, 0.56, 0.68, 0.92, 0.18, GLASS),
    (0.46, 0.30, 0.54, 0.72, 0.04, COLUMN),
    (0.38, 0.62, 0.62, 0.86, 0.12, COLUMN),
)


def _rounded_rect_inside(
    px: float, py: float, x0: float, y0: float, x1: float, y1: float, radius: float
) -> bool:
    """Signed-distance test for a rounded rectangle in unit coordinates."""
    half_x = (x1 - x0) / 2 - radius
    half_y = (y1 - y0) / 2 - radius
    qx = abs(px - (x0 + x1) / 2) - half_x
    qy = abs(py - (y0 + y1) / 2) - half_y
    distance = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - radius
    return distance <= 0.0


def _sample(px: float, py: float) -> Color:
    """Colour of a single point; later layers paint over earlier ones."""
    result: Color = (0, 0, 0, 0)
    for x0, y0, x1, y1, radius, colour in LAYERS:
        if _rounded_rect_inside(px, py, x0, y0, x1, y1, radius):
            result = colour
    return result


def render(size: int) -> list[Color]:
    """Render one icon size, top-down, row-major, as straight (non-premultiplied) RGBA."""
    factor = _oversample(size)
    big = size * factor
    samples_per_pixel = factor * factor

    # Render the supersampled image once, then box-filter it down.
    hi: list[Color] = []
    for row in range(big):
        py = (row + 0.5) / big
        for column in range(big):
            hi.append(_sample((column + 0.5) / big, py))

    pixels: list[Color] = []
    for row in range(size):
        for column in range(size):
            r = g = b = a = 0
            for sub_row in range(factor):
                base = (row * factor + sub_row) * big + column * factor
                for sub_column in range(factor):
                    sr, sg, sb, sa = hi[base + sub_column]
                    # Weight colour by coverage so transparent edges do not darken.
                    r += sr * sa
                    g += sg * sa
                    b += sb * sa
                    a += sa
            if a == 0:
                pixels.append((0, 0, 0, 0))
            else:
                pixels.append((r // a, g // a, b // a, a // samples_per_pixel))
    return pixels


def _dib(size: int, pixels: list[Color]) -> bytes:
    """BITMAPINFOHEADER + bottom-up BGRA rows + an all-zero AND mask."""
    header = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        size,  # biWidth
        size * 2,  # biHeight: colour rows plus mask rows
        1,  # biPlanes
        32,  # biBitCount
        0,  # biCompression = BI_RGB
        size * size * 4,  # biSizeImage
        0,
        0,
        0,
        0,
    )
    body = bytearray()
    for row in range(size - 1, -1, -1):  # DIBs are stored bottom-up
        for column in range(size):
            r, g, b, a = pixels[row * size + column]
            body += bytes((b, g, r, a))

    # The 1-bit AND mask is ignored for 32-bit icons but must still be present.
    mask_row_bytes = ((size + 31) // 32) * 4
    body += bytes(mask_row_bytes * size)
    return header + bytes(body)


def build_ico() -> bytes:
    images = [_dib(size, render(size)) for size in SIZES]

    out = bytearray(struct.pack("<HHH", 0, 1, len(SIZES)))  # ICONDIR: reserved, type, count
    offset = 6 + 16 * len(SIZES)
    for size, image in zip(SIZES, images, strict=True):
        out += struct.pack(
            "<BBBBHHII",
            size % 256,  # 256 is encoded as 0
            size % 256,
            0,  # no colour palette
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(image),
            offset,
        )
        offset += len(image)
    for image in images:
        out += image
    return bytes(out)


def main() -> int:
    ICO_PATH.write_bytes(build_ico())
    print(f"Wrote {ICO_PATH} ({ICO_PATH.stat().st_size} bytes, sizes: {list(SIZES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
