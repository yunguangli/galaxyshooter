"""
pngkit.py — Pix: zero-dependency procedural PNG / data-URI generation.

A tiny RGBA pixel canvas plus helpers for generating PNG images as
``data:image/png;base64,...`` URIs using only the stdlib (``struct``,
``zlib``, ``base64``).  No Pillow required.  Use it for programmatic
sprites, textures, sign text, solid rects, and UI art that would
otherwise need image files.

Quick start::

    from flet_game import Pix, make_text_png, make_rect_uri

    # Solid rectangle as a data URI (e.g. a floor line billboard):
    uri = make_rect_uri(4, 64, "#e8c820")

    # Procedural 64x64 image:
    p = Pix(64, 64)
    p.fill(0, 0, 64, 64, "#1d4a33")
    p.fill(8, 8, 56, 24, "#122e20")
    sprite_uri = p.uri()

    # Rendered text (5x7 bitmap font, A-Z / 0-9):
    sign = make_text_png("EXIT 8", "#f0f0f0", bg="#3a3a3a", pad=7, scale=4)

All functions are deterministic and allocation-light — safe to call at
import time and to cache the resulting URIs.
"""

from __future__ import annotations

import base64
import struct
import zlib


def png_chunk(ctype: bytes, data: bytes) -> bytes:
    """Build one PNG chunk (length + type + data + CRC32)."""
    c = ctype + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)


def encode_png(w: int, h: int, pixels: bytearray) -> str:
    """Encode raw RGBA ``pixels`` (w*h*4 bytes, row-major) as a PNG data URI."""
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter byte: None
        raw.extend(pixels[y * w * 4:(y + 1) * w * 4])
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", ihdr)
    png += png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += png_chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode()


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Parse ``#rrggbb`` (or ``rrggbb``) into an (r, g, b) tuple."""
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


class Pix:
    """A small RGBA pixel canvas that encodes itself as a PNG data URI.

    Attributes:
        w: Canvas width in pixels.
        h: Canvas height in pixels.
        px: The raw RGBA bytearray (``w * h * 4`` bytes), public for
            low-level access.
    """

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.px = bytearray(w * h * 4)

    def set(self, x: int, y: int, r: int, g: int, b: int, a: int = 255) -> None:
        """Set one pixel.  Out-of-bounds coordinates are ignored."""
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 4
            self.px[i:i + 4] = bytes([r, g, b, a])

    def fill(self, x0: int, y0: int, x1: int, y1: int, color: str, a: int = 255) -> None:
        """Fill the rectangle [x0, x1) x [y0, y1) with a hex colour."""
        r, g, b = hex_to_rgb(color)
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.set(x, y, r, g, b, a)

    def uri(self) -> str:
        """Encode the canvas as a PNG data URI."""
        return encode_png(self.w, self.h, self.px)


# 5×7 bitmap font for sign text (A-Z, 0-9, space, ., -).
# Each glyph is a list of 7 rows; a "1" paints a pixel.
FONT: dict[str, list[str]] = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "11111"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
}


def make_text_png(
    text: str,
    fg: str,
    bg: str | None = None,
    border: str | None = None,
    pad: int = 2,
    scale: int = 2,
) -> str:
    """Render uppercase text with the 5×7 :data:`FONT` into a PNG data URI.

    Parameters
    ----------
    text : str
        Text to render (lowercase is auto-uppercased; unknown glyphs
        render as a space).
    fg : str
        Foreground (glyph) hex colour.
    bg : str | None
        Optional background hex colour (transparent when omitted).
    border : str | None
        Optional 1-pixel frame colour drawn around the whole image.
    pad : int
        Padding around the glyph block (in unscaled pixels).
    scale : int
        Integer scale factor applied to glyphs and padding.

    Returns
    -------
    str
        A ``data:image/png;base64,...`` URI.
    """
    text = text.upper()
    fw = len(text) * 6 - 1
    w = (fw + pad * 2) * scale
    h = (7 + pad * 2) * scale
    p = Pix(w, h)
    if bg is not None:
        p.fill(0, 0, w, h, bg)
    if border is not None:
        p.fill(0, 0, w, 1, border)
        p.fill(0, h - 1, w, h, border)
        p.fill(0, 0, 1, h, border)
        p.fill(w - 1, 0, w, h, border)
    fr, fg_, fb = hex_to_rgb(fg)
    for ci, ch in enumerate(text):
        glyph = FONT.get(ch, FONT[" "])
        for ry, row in enumerate(glyph):
            for rx, bit in enumerate(row):
                if bit == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            p.set((pad + ci * 6 + rx) * scale + sx,
                                  (pad + ry) * scale + sy, fr, fg_, fb)
    return p.uri()


def make_rect_uri(w: int, h: int, color: str) -> str:
    """A solid-colour rectangle as a PNG data URI."""
    p = Pix(w, h)
    p.fill(0, 0, w, h, color)
    return p.uri()
