"""Default sprite images for characters, enemies, and items.

Generates minimal RGBA PNG images using only the Python standard library
(``struct``, ``zlib``).  No Pillow required.

Sprite sizes (all RGBA):

- Hero:      32 x 64 px  (idle + walk)
- Enemy:     32 x 64 px  (idle + walk)
- Skeleton:  32 x 64 px  (idle + walk)
- Slime:     32 x 32 px  (idle + walk)
- Item:      32 x 32 px  (coin)
- Key:       32 x 32 px  (key)

PNG generation is **lazy** — pixel data is only encoded on first access.
"""

from __future__ import annotations

import struct
import zlib
from base64 import b64encode
from dataclasses import dataclass, field
from typing import Optional


# ── PNG generation helpers ───────────────────────────────────────────────────

def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    c = chunk_type + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)


def _make_png(width: int, height: int, pixels: bytes) -> str:
    """Create a ``data:image/png;base64,...`` URI from raw RGBA pixel data.

    ``pixels`` must be ``width * height * 4`` bytes, top-to-bottom,
    left-to-right.
    """
    raw = b""
    for row in range(height):
        raw += b"\x00" + pixels[row * width * 4:(row + 1) * width * 4]
    compressed = zlib.compress(raw)
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        signature
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + b64encode(png).decode("ascii")


# ── Pixel helpers ────────────────────────────────────────────────────────────

def _px(pixels: bytearray, w: int, x: int, y: int,
        r: int, g: int, b: int, a: int = 255) -> None:
    if 0 <= x < w and 0 <= y < len(pixels) // (w * 4):
        idx = (y * w + x) * 4
        pixels[idx:idx + 4] = bytes([r, g, b, a])


def _box(pixels: bytearray, w: int, x0: int, y0: int, x1: int, y1: int,
         r: int, g: int, b: int, a: int = 255) -> None:
    for y in range(y0, y1):
        for x in range(x0, x1):
            _px(pixels, w, x, y, r, g, b, a)


# ── Sprite generators ────────────────────────────────────────────────────────

def _gen_hero_idle() -> str:
    """32 x 64 blue-clad hero (idle)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    # Hair
    _box(p, W, 10, 2, 22, 10, 80, 50, 30)
    # Head (skin)
    _box(p, W, 10, 8, 22, 22, 220, 180, 140)
    # Eyes
    _px(p, W, 13, 13, 0, 0, 0)
    _px(p, W, 18, 13, 0, 0, 0)
    # Mouth
    _box(p, W, 14, 18, 18, 19, 180, 100, 80)
    # Neck
    _box(p, W, 14, 22, 18, 26, 210, 170, 130)
    # Body (blue tunic)
    _box(p, W, 8, 26, 24, 46, 30, 80, 200)
    # Belt
    _box(p, W, 8, 42, 24, 46, 140, 100, 40)
    _px(p, W, 15, 43, 220, 180, 60)  # buckle
    _px(p, W, 16, 43, 220, 180, 60)
    # Arms (skin)
    _box(p, W, 4, 28, 8, 44, 220, 180, 140)
    _box(p, W, 24, 28, 28, 44, 220, 180, 140)
    # Hands
    _box(p, W, 4, 44, 8, 48, 210, 170, 130)
    _box(p, W, 24, 44, 28, 48, 210, 170, 130)
    # Legs (brown pants)
    _box(p, W, 10, 46, 15, 60, 100, 70, 40)
    _box(p, W, 17, 46, 22, 60, 100, 70, 40)
    # Boots
    _box(p, W, 9, 58, 15, 64, 60, 40, 20)
    _box(p, W, 17, 58, 23, 64, 60, 40, 20)
    return _make_png(W, H, bytes(p))


def _gen_hero_walk1() -> str:
    """32 x 64 blue-clad hero (walk frame 1 — left leg forward)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    # Head (same as idle)
    _box(p, W, 10, 2, 22, 10, 80, 50, 30)
    _box(p, W, 10, 8, 22, 22, 220, 180, 140)
    _px(p, W, 13, 13, 0, 0, 0)
    _px(p, W, 18, 13, 0, 0, 0)
    _box(p, W, 14, 18, 18, 19, 180, 100, 80)
    _box(p, W, 14, 22, 18, 26, 210, 170, 130)
    # Body (blue tunic, slight lean)
    _box(p, W, 8, 26, 24, 46, 30, 80, 200)
    _box(p, W, 8, 42, 24, 46, 140, 100, 40)
    _px(p, W, 15, 43, 220, 180, 60)
    _px(p, W, 16, 43, 220, 180, 60)
    # Arms (swung)
    _box(p, W, 4, 28, 8, 42, 220, 180, 140)
    _box(p, W, 24, 30, 28, 44, 220, 180, 140)
    _box(p, W, 4, 42, 8, 46, 210, 170, 130)
    _box(p, W, 24, 44, 28, 48, 210, 170, 130)
    # Legs — walk frame 1: left forward, right back
    _box(p, W, 8, 46, 14, 60, 100, 70, 40)   # left leg (forward)
    _box(p, W, 18, 46, 24, 58, 100, 70, 40)   # right leg (back)
    # Boots
    _box(p, W, 7, 58, 14, 64, 60, 40, 20)     # left boot (forward)
    _box(p, W, 18, 56, 24, 62, 60, 40, 20)     # right boot (back)
    return _make_png(W, H, bytes(p))


def _gen_hero_walk2() -> str:
    """32 x 64 blue-clad hero (walk frame 2 — right leg forward)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    # Head
    _box(p, W, 10, 2, 22, 10, 80, 50, 30)
    _box(p, W, 10, 8, 22, 22, 220, 180, 140)
    _px(p, W, 13, 13, 0, 0, 0)
    _px(p, W, 18, 13, 0, 0, 0)
    _box(p, W, 14, 18, 18, 19, 180, 100, 80)
    _box(p, W, 14, 22, 18, 26, 210, 170, 130)
    # Body
    _box(p, W, 8, 26, 24, 46, 30, 80, 200)
    _box(p, W, 8, 42, 24, 46, 140, 100, 40)
    _px(p, W, 15, 43, 220, 180, 60)
    _px(p, W, 16, 43, 220, 180, 60)
    # Arms (swung opposite)
    _box(p, W, 4, 30, 8, 44, 220, 180, 140)
    _box(p, W, 24, 28, 28, 42, 220, 180, 140)
    _box(p, W, 4, 44, 8, 48, 210, 170, 130)
    _box(p, W, 24, 42, 28, 46, 210, 170, 130)
    # Legs — walk frame 2: right forward, left back
    _box(p, W, 8, 46, 14, 58, 100, 70, 40)    # left leg (back)
    _box(p, W, 18, 46, 24, 60, 100, 70, 40)    # right leg (forward)
    # Boots
    _box(p, W, 8, 56, 14, 62, 60, 40, 20)     # left boot (back)
    _box(p, W, 17, 58, 24, 64, 60, 40, 20)     # right boot (forward)
    return _make_png(W, H, bytes(p))


def _gen_enemy_idle() -> str:
    """32 x 64 red demon (idle)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    # Horns
    _box(p, W, 8, 0, 11, 6, 160, 40, 40)
    _box(p, W, 21, 0, 24, 6, 160, 40, 40)
    # Head
    _box(p, W, 9, 4, 23, 20, 180, 60, 60)
    # Eyes (glowing yellow)
    _px(p, W, 12, 10, 255, 255, 0)
    _px(p, W, 13, 10, 255, 255, 0)
    _px(p, W, 18, 10, 255, 255, 0)
    _px(p, W, 19, 10, 255, 255, 0)
    # Mouth (fangs)
    _box(p, W, 12, 16, 20, 18, 100, 0, 0)
    _px(p, W, 14, 18, 255, 255, 255)  # fang
    _px(p, W, 17, 18, 255, 255, 255)  # fang
    # Neck
    _box(p, W, 13, 20, 19, 24, 170, 50, 50)
    # Body (armored torso)
    _box(p, W, 7, 24, 25, 46, 200, 40, 40)
    _box(p, W, 9, 26, 23, 30, 140, 30, 30)  # chest plate
    # Belt
    _box(p, W, 7, 42, 25, 46, 100, 30, 30)
    # Arms (red)
    _box(p, W, 3, 26, 7, 44, 190, 50, 50)
    _box(p, W, 25, 26, 29, 44, 190, 50, 50)
    # Claws
    _box(p, W, 3, 44, 7, 48, 120, 30, 30)
    _box(p, W, 25, 44, 29, 48, 120, 30, 30)
    _px(p, W, 3, 48, 200, 200, 200)
    _px(p, W, 6, 48, 200, 200, 200)
    _px(p, W, 25, 48, 200, 200, 200)
    _px(p, W, 28, 48, 200, 200, 200)
    # Legs (dark red)
    _box(p, W, 10, 46, 15, 60, 150, 20, 20)
    _box(p, W, 17, 46, 22, 60, 150, 20, 20)
    # Hooves
    _box(p, W, 9, 58, 15, 64, 80, 50, 30)
    _box(p, W, 17, 58, 23, 64, 80, 50, 30)
    return _make_png(W, H, bytes(p))


def _gen_enemy_walk1() -> str:
    """32 x 64 red demon (walk frame 1)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    _box(p, W, 8, 0, 11, 6, 160, 40, 40)
    _box(p, W, 21, 0, 24, 6, 160, 40, 40)
    _box(p, W, 9, 4, 23, 20, 180, 60, 60)
    _px(p, W, 12, 10, 255, 255, 0)
    _px(p, W, 13, 10, 255, 255, 0)
    _px(p, W, 18, 10, 255, 255, 0)
    _px(p, W, 19, 10, 255, 255, 0)
    _box(p, W, 12, 16, 20, 18, 100, 0, 0)
    _px(p, W, 14, 18, 255, 255, 255)
    _px(p, W, 17, 18, 255, 255, 255)
    _box(p, W, 13, 20, 19, 24, 170, 50, 50)
    _box(p, W, 7, 24, 25, 46, 200, 40, 40)
    _box(p, W, 9, 26, 23, 30, 140, 30, 30)
    _box(p, W, 7, 42, 25, 46, 100, 30, 30)
    # Arms swung
    _box(p, W, 3, 28, 7, 42, 190, 50, 50)
    _box(p, W, 25, 30, 29, 44, 190, 50, 50)
    _box(p, W, 3, 42, 7, 46, 120, 30, 30)
    _box(p, W, 25, 44, 29, 48, 120, 30, 30)
    _px(p, W, 3, 46, 200, 200, 200)
    _px(p, W, 28, 48, 200, 200, 200)
    # Legs walk frame 1
    _box(p, W, 8, 46, 14, 60, 150, 20, 20)
    _box(p, W, 18, 46, 24, 58, 150, 20, 20)
    _box(p, W, 7, 58, 14, 64, 80, 50, 30)
    _box(p, W, 18, 56, 24, 62, 80, 50, 30)
    return _make_png(W, H, bytes(p))


def _gen_enemy_walk2() -> str:
    """32 x 64 red demon (walk frame 2)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    _box(p, W, 8, 0, 11, 6, 160, 40, 40)
    _box(p, W, 21, 0, 24, 6, 160, 40, 40)
    _box(p, W, 9, 4, 23, 20, 180, 60, 60)
    _px(p, W, 12, 10, 255, 255, 0)
    _px(p, W, 13, 10, 255, 255, 0)
    _px(p, W, 18, 10, 255, 255, 0)
    _px(p, W, 19, 10, 255, 255, 0)
    _box(p, W, 12, 16, 20, 18, 100, 0, 0)
    _px(p, W, 14, 18, 255, 255, 255)
    _px(p, W, 17, 18, 255, 255, 255)
    _box(p, W, 13, 20, 19, 24, 170, 50, 50)
    _box(p, W, 7, 24, 25, 46, 200, 40, 40)
    _box(p, W, 9, 26, 23, 30, 140, 30, 30)
    _box(p, W, 7, 42, 25, 46, 100, 30, 30)
    # Arms swung opposite
    _box(p, W, 3, 30, 7, 44, 190, 50, 50)
    _box(p, W, 25, 28, 29, 42, 190, 50, 50)
    _box(p, W, 3, 44, 7, 48, 120, 30, 30)
    _box(p, W, 25, 42, 29, 46, 120, 30, 30)
    _px(p, W, 3, 48, 200, 200, 200)
    _px(p, W, 28, 46, 200, 200, 200)
    # Legs walk frame 2
    _box(p, W, 8, 46, 14, 58, 150, 20, 20)
    _box(p, W, 18, 46, 24, 60, 150, 20, 20)
    _box(p, W, 8, 56, 14, 62, 80, 50, 30)
    _box(p, W, 17, 58, 24, 64, 80, 50, 30)
    return _make_png(W, H, bytes(p))


def _gen_skeleton_idle() -> str:
    """32 x 64 white skeleton (idle)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    # Skull
    _box(p, W, 10, 2, 22, 18, 230, 230, 220)
    # Eye sockets
    _box(p, W, 12, 8, 15, 12, 30, 30, 30)
    _box(p, W, 17, 8, 20, 12, 30, 30, 30)
    # Eye glints
    _px(p, W, 13, 9, 200, 50, 50)
    _px(p, W, 18, 9, 200, 50, 50)
    # Nose hole
    _px(p, W, 15, 14, 30, 30, 30)
    _px(p, W, 16, 14, 30, 30, 30)
    # Jaw
    _box(p, W, 12, 15, 20, 18, 200, 200, 190)
    # Spine
    _box(p, W, 14, 18, 18, 26, 220, 220, 210)
    # Ribcage
    _box(p, W, 8, 24, 24, 38, 220, 220, 210)
    _box(p, W, 10, 26, 22, 28, 30, 30, 30)  # gap
    _box(p, W, 10, 30, 22, 32, 30, 30, 30)  # gap
    _box(p, W, 10, 34, 22, 36, 30, 30, 30)  # gap
    # Pelvis
    _box(p, W, 10, 38, 22, 44, 210, 210, 200)
    # Arms (bone)
    _box(p, W, 4, 26, 8, 42, 220, 220, 210)
    _box(p, W, 24, 26, 28, 42, 220, 220, 210)
    # Hands (claw)
    _box(p, W, 4, 42, 8, 46, 200, 200, 190)
    _box(p, W, 24, 42, 28, 46, 200, 200, 190)
    # Legs (bone)
    _box(p, W, 11, 44, 14, 58, 210, 210, 200)
    _box(p, W, 18, 44, 21, 58, 210, 210, 200)
    # Feet
    _box(p, W, 10, 58, 15, 64, 190, 190, 180)
    _box(p, W, 17, 58, 22, 64, 190, 190, 180)
    return _make_png(W, H, bytes(p))


def _gen_skeleton_walk1() -> str:
    """32 x 64 skeleton (walk frame 1)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    _box(p, W, 10, 2, 22, 18, 230, 230, 220)
    _box(p, W, 12, 8, 15, 12, 30, 30, 30)
    _box(p, W, 17, 8, 20, 12, 30, 30, 30)
    _px(p, W, 13, 9, 200, 50, 50)
    _px(p, W, 18, 9, 200, 50, 50)
    _px(p, W, 15, 14, 30, 30, 30)
    _px(p, W, 16, 14, 30, 30, 30)
    _box(p, W, 12, 15, 20, 18, 200, 200, 190)
    _box(p, W, 14, 18, 18, 26, 220, 220, 210)
    _box(p, W, 8, 24, 24, 38, 220, 220, 210)
    _box(p, W, 10, 26, 22, 28, 30, 30, 30)
    _box(p, W, 10, 30, 22, 32, 30, 30, 30)
    _box(p, W, 10, 34, 22, 36, 30, 30, 30)
    _box(p, W, 10, 38, 22, 44, 210, 210, 200)
    # Arms swung
    _box(p, W, 4, 28, 8, 40, 220, 220, 210)
    _box(p, W, 24, 30, 28, 42, 220, 220, 210)
    _box(p, W, 4, 40, 8, 44, 200, 200, 190)
    _box(p, W, 24, 42, 28, 46, 200, 200, 190)
    # Legs walk 1
    _box(p, W, 9, 44, 13, 58, 210, 210, 200)
    _box(p, W, 19, 44, 23, 56, 210, 210, 200)
    _box(p, W, 8, 58, 14, 64, 190, 190, 180)
    _box(p, W, 19, 56, 23, 62, 190, 190, 180)
    return _make_png(W, H, bytes(p))


def _gen_skeleton_walk2() -> str:
    """32 x 64 skeleton (walk frame 2)."""
    W, H = 32, 64
    p = bytearray(W * H * 4)
    _box(p, W, 10, 2, 22, 18, 230, 230, 220)
    _box(p, W, 12, 8, 15, 12, 30, 30, 30)
    _box(p, W, 17, 8, 20, 12, 30, 30, 30)
    _px(p, W, 13, 9, 200, 50, 50)
    _px(p, W, 18, 9, 200, 50, 50)
    _px(p, W, 15, 14, 30, 30, 30)
    _px(p, W, 16, 14, 30, 30, 30)
    _box(p, W, 12, 15, 20, 18, 200, 200, 190)
    _box(p, W, 14, 18, 18, 26, 220, 220, 210)
    _box(p, W, 8, 24, 24, 38, 220, 220, 210)
    _box(p, W, 10, 26, 22, 28, 30, 30, 30)
    _box(p, W, 10, 30, 22, 32, 30, 30, 30)
    _box(p, W, 10, 34, 22, 36, 30, 30, 30)
    _box(p, W, 10, 38, 22, 44, 210, 210, 200)
    # Arms swung opposite
    _box(p, W, 4, 30, 8, 42, 220, 220, 210)
    _box(p, W, 24, 28, 28, 40, 220, 220, 210)
    _box(p, W, 4, 42, 8, 46, 200, 200, 190)
    _box(p, W, 24, 40, 28, 44, 200, 200, 190)
    # Legs walk 2
    _box(p, W, 9, 44, 13, 56, 210, 210, 200)
    _box(p, W, 19, 44, 23, 58, 210, 210, 200)
    _box(p, W, 9, 56, 13, 62, 190, 190, 180)
    _box(p, W, 18, 58, 24, 64, 190, 190, 180)
    return _make_png(W, H, bytes(p))


def _gen_slime_idle() -> str:
    """32 x 32 green slime blob (idle)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Body (rounded blob)
    _box(p, W, 6, 10, 26, 28, 60, 180, 60)
    _box(p, W, 8, 6, 24, 10, 60, 180, 60)
    _box(p, W, 10, 4, 22, 6, 60, 180, 60)
    # Highlight
    _box(p, W, 10, 8, 18, 14, 100, 220, 100)
    _box(p, W, 12, 6, 16, 8, 120, 240, 120)
    # Eyes
    _box(p, W, 10, 14, 13, 18, 255, 255, 255)
    _box(p, W, 19, 14, 22, 18, 255, 255, 255)
    _px(p, W, 11, 16, 0, 0, 0)
    _px(p, W, 20, 16, 0, 0, 0)
    # Mouth
    _box(p, W, 13, 22, 19, 24, 40, 120, 40)
    return _make_png(W, H, bytes(p))


def _gen_slime_walk1() -> str:
    """32 x 32 green slime (squish frame)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Squished wider body
    _box(p, W, 4, 14, 28, 28, 60, 180, 60)
    _box(p, W, 6, 10, 26, 14, 60, 180, 60)
    _box(p, W, 8, 8, 24, 10, 60, 180, 60)
    # Highlight
    _box(p, W, 8, 12, 16, 16, 100, 220, 100)
    # Eyes (lower)
    _box(p, W, 10, 18, 13, 22, 255, 255, 255)
    _box(p, W, 19, 18, 22, 22, 255, 255, 255)
    _px(p, W, 11, 20, 0, 0, 0)
    _px(p, W, 20, 20, 0, 0, 0)
    # Mouth
    _box(p, W, 13, 24, 19, 26, 40, 120, 40)
    return _make_png(W, H, bytes(p))


def _gen_slime_walk2() -> str:
    """32 x 32 green slime (stretch frame)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Stretched taller body
    _box(p, W, 8, 6, 24, 28, 60, 180, 60)
    _box(p, W, 10, 4, 22, 6, 60, 180, 60)
    # Highlight
    _box(p, W, 12, 8, 18, 14, 100, 220, 100)
    _box(p, W, 14, 6, 18, 8, 120, 240, 120)
    # Eyes (higher)
    _box(p, W, 11, 10, 14, 14, 255, 255, 255)
    _box(p, W, 18, 10, 21, 14, 255, 255, 255)
    _px(p, W, 12, 12, 0, 0, 0)
    _px(p, W, 19, 12, 0, 0, 0)
    # Mouth
    _box(p, W, 13, 20, 19, 22, 40, 120, 40)
    return _make_png(W, H, bytes(p))


def _gen_item_coin() -> str:
    """32 x 32 gold coin."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Outer ring
    for y in range(H):
        for x in range(W):
            dx, dy = x - 15.5, y - 15.5
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= 13:
                # Gold fill
                _px(p, W, x, y, 255, 200, 0)
            if 11 <= dist <= 13:
                # Darker rim
                _px(p, W, x, y, 200, 150, 0)
            if 8 <= dist <= 10:
                # Inner ring
                _px(p, W, x, y, 255, 220, 50)
    # Highlight
    _box(p, W, 10, 8, 14, 12, 255, 240, 100)
    # Dollar sign
    _box(p, W, 15, 8, 17, 24, 200, 150, 0)
    _box(p, W, 12, 10, 20, 12, 200, 150, 0)
    _box(p, W, 12, 20, 20, 22, 200, 150, 0)
    return _make_png(W, H, bytes(p))


def _gen_item_key() -> str:
    """32 x 32 gold key."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Key head (circle)
    for y in range(H):
        for x in range(W):
            dx, dy = x - 10, y - 10
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= 7:
                _px(p, W, x, y, 220, 180, 40)
            if 4 <= dist <= 6:
                _px(p, W, x, y, 180, 140, 20)
    # Key hole
    _px(p, W, 10, 10, 40, 40, 40)
    # Key shaft
    _box(p, W, 16, 9, 28, 12, 220, 180, 40)
    # Key teeth
    _box(p, W, 24, 12, 26, 16, 220, 180, 40)
    _box(p, W, 20, 12, 22, 15, 220, 180, 40)
    return _make_png(W, H, bytes(p))


def _gen_bat_idle() -> str:
    """32 x 32 dark bat with wings spread (idle)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Body (dark purple)
    _box(p, W, 12, 12, 20, 22, 74, 32, 96)
    # Head
    _box(p, W, 13, 8, 19, 14, 74, 32, 96)
    # Ears
    _box(p, W, 12, 5, 14, 9, 74, 32, 96)
    _box(p, W, 18, 5, 20, 9, 74, 32, 96)
    # Eyes (glowing red)
    _px(p, W, 14, 10, 255, 40, 40)
    _px(p, W, 17, 10, 255, 40, 40)
    # Fangs
    _px(p, W, 14, 14, 255, 255, 255)
    _px(p, W, 17, 14, 255, 255, 255)
    # Wings (dark purple, spread)
    # Left wing
    _box(p, W, 2, 10, 12, 14, 60, 24, 80)
    _box(p, W, 0, 12, 4, 16, 60, 24, 80)
    _box(p, W, 4, 14, 10, 18, 60, 24, 80)
    # Right wing
    _box(p, W, 20, 10, 30, 14, 60, 24, 80)
    _box(p, W, 28, 12, 32, 16, 60, 24, 80)
    _box(p, W, 22, 14, 28, 18, 60, 24, 80)
    # Wing membrane lines
    _px(p, W, 3, 13, 90, 40, 110)
    _px(p, W, 6, 15, 90, 40, 110)
    _px(p, W, 29, 13, 90, 40, 110)
    _px(p, W, 26, 15, 90, 40, 110)
    # Feet
    _px(p, W, 13, 22, 74, 32, 96)
    _px(p, W, 18, 22, 74, 32, 96)
    return _make_png(W, H, bytes(p))


def _gen_bat_fly1() -> str:
    """32 x 32 bat with wings up (fly frame 1)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Body
    _box(p, W, 12, 14, 20, 24, 74, 32, 96)
    # Head
    _box(p, W, 13, 10, 19, 16, 74, 32, 96)
    # Ears
    _box(p, W, 12, 7, 14, 11, 74, 32, 96)
    _box(p, W, 18, 7, 20, 11, 74, 32, 96)
    # Eyes
    _px(p, W, 14, 12, 255, 40, 40)
    _px(p, W, 17, 12, 255, 40, 40)
    # Fangs
    _px(p, W, 14, 16, 255, 255, 255)
    _px(p, W, 17, 16, 255, 255, 255)
    # Wings UP
    # Left wing (pointing up-left)
    _box(p, W, 2, 4, 12, 8, 60, 24, 80)
    _box(p, W, 0, 2, 4, 6, 60, 24, 80)
    _box(p, W, 6, 6, 12, 10, 60, 24, 80)
    # Right wing (pointing up-right)
    _box(p, W, 20, 4, 30, 8, 60, 24, 80)
    _box(p, W, 28, 2, 32, 6, 60, 24, 80)
    _box(p, W, 20, 6, 26, 10, 60, 24, 80)
    # Wing membrane
    _px(p, W, 3, 5, 90, 40, 110)
    _px(p, W, 29, 5, 90, 40, 110)
    # Feet
    _px(p, W, 13, 24, 74, 32, 96)
    _px(p, W, 18, 24, 74, 32, 96)
    return _make_png(W, H, bytes(p))


def _gen_bat_fly2() -> str:
    """32 x 32 bat with wings down (fly frame 2)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Body
    _box(p, W, 12, 12, 20, 22, 74, 32, 96)
    # Head
    _box(p, W, 13, 8, 19, 14, 74, 32, 96)
    # Ears
    _box(p, W, 12, 5, 14, 9, 74, 32, 96)
    _box(p, W, 18, 5, 20, 9, 74, 32, 96)
    # Eyes
    _px(p, W, 14, 10, 255, 40, 40)
    _px(p, W, 17, 10, 255, 40, 40)
    # Fangs
    _px(p, W, 14, 14, 255, 255, 255)
    _px(p, W, 17, 14, 255, 255, 255)
    # Wings DOWN
    # Left wing (pointing down-left)
    _box(p, W, 2, 16, 12, 20, 60, 24, 80)
    _box(p, W, 0, 18, 4, 22, 60, 24, 80)
    _box(p, W, 6, 18, 12, 22, 60, 24, 80)
    # Right wing (pointing down-right)
    _box(p, W, 20, 16, 30, 20, 60, 24, 80)
    _box(p, W, 28, 18, 32, 22, 60, 24, 80)
    _box(p, W, 20, 18, 26, 22, 60, 24, 80)
    # Wing membrane
    _px(p, W, 3, 19, 90, 40, 110)
    _px(p, W, 29, 19, 90, 40, 110)
    # Feet
    _px(p, W, 13, 22, 74, 32, 96)
    _px(p, W, 18, 22, 74, 32, 96)
    return _make_png(W, H, bytes(p))


def _gen_weapon_pistol() -> str:
    """32 x 32 pistol sprite (grey metal, brown grip)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Barrel (dark grey)
    _box(p, W, 14, 6, 18, 18, 80, 80, 80)
    # Slide (lighter grey)
    _box(p, W, 13, 8, 19, 16, 120, 120, 120)
    # Muzzle
    _box(p, W, 15, 4, 17, 7, 60, 60, 60)
    # Grip (brown)
    _box(p, W, 13, 18, 19, 26, 139, 90, 43)
    # Grip texture lines
    _px(p, W, 14, 20, 120, 75, 35)
    _px(p, W, 16, 22, 120, 75, 35)
    _px(p, W, 18, 24, 120, 75, 35)
    # Trigger guard
    _box(p, W, 11, 16, 13, 20, 100, 100, 100)
    # Trigger
    _px(p, W, 12, 18, 80, 80, 80)
    # Sight (top)
    _px(p, W, 15, 3, 140, 140, 140)
    # Highlight on slide
    _px(p, W, 14, 10, 160, 160, 160)
    return _make_png(W, H, bytes(p))


def _gen_weapon_rifle() -> str:
    """32 x 32 rifle sprite (long barrel, wooden stock)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Barrel (dark grey)
    _box(p, W, 4, 12, 22, 14, 70, 70, 70)
    # Barrel tip
    _box(p, W, 2, 12, 5, 14, 50, 50, 50)
    # Receiver (lighter grey)
    _box(p, W, 18, 10, 24, 16, 100, 100, 100)
    # Magazine
    _box(p, W, 20, 16, 22, 22, 60, 60, 60)
    # Stock (brown wood)
    _box(p, W, 22, 11, 30, 17, 139, 90, 43)
    # Stock grain
    _px(p, W, 24, 13, 120, 75, 35)
    _px(p, W, 27, 15, 120, 75, 35)
    # Grip (below receiver)
    _box(p, W, 19, 16, 21, 24, 80, 60, 30)
    # Trigger guard
    _box(p, W, 17, 15, 19, 18, 90, 90, 90)
    # Trigger
    _px(p, W, 18, 17, 70, 70, 70)
    # Front sight
    _px(p, W, 5, 10, 140, 140, 140)
    # Rear sight
    _px(p, W, 20, 9, 140, 140, 140)
    # Highlight on barrel
    _px(p, W, 8, 11, 110, 110, 110)
    return _make_png(W, H, bytes(p))


def _gen_weapon_sword() -> str:
    """32 x 32 sword sprite (silver blade, golden hilt)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Blade (silver, angled)
    _box(p, W, 14, 2, 17, 18, 200, 200, 210)
    # Blade edge highlight
    _px(p, W, 14, 4, 220, 220, 230)
    _px(p, W, 14, 8, 220, 220, 230)
    _px(p, W, 14, 12, 220, 220, 230)
    # Blade shadow
    _px(p, W, 16, 6, 170, 170, 180)
    _px(p, W, 16, 10, 170, 170, 180)
    # Tip
    _px(p, W, 15, 1, 210, 210, 220)
    # Crossguard (golden)
    _box(p, W, 11, 18, 20, 20, 218, 165, 32)
    # Crossguard highlights
    _px(p, W, 12, 18, 240, 190, 60)
    _px(p, W, 18, 19, 240, 190, 60)
    # Grip (dark leather)
    _box(p, W, 14, 20, 17, 26, 60, 40, 20)
    # Grip wrapping
    _px(p, W, 14, 22, 80, 55, 30)
    _px(p, W, 16, 24, 80, 55, 30)
    # Pommel (golden)
    _box(p, W, 13, 26, 18, 28, 218, 165, 32)
    return _make_png(W, H, bytes(p))


def _gen_weapon_bazooka() -> str:
    """32 x 32 bazooka/rocket launcher sprite (olive green tube)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Main tube (olive green)
    _box(p, W, 3, 12, 26, 18, 80, 100, 50)
    # Tube front opening (dark)
    _box(p, W, 1, 13, 4, 17, 40, 40, 40)
    # Tube rear (darker green)
    _box(p, W, 24, 12, 28, 18, 60, 80, 40)
    # Shoulder rest
    _box(p, W, 20, 18, 26, 22, 70, 90, 45)
    # Grip (below tube)
    _box(p, W, 12, 18, 16, 26, 100, 80, 50)
    # Grip texture
    _px(p, W, 13, 20, 85, 65, 40)
    _px(p, W, 15, 23, 85, 65, 40)
    # Trigger guard
    _box(p, W, 10, 17, 12, 20, 90, 90, 90)
    # Trigger
    _px(p, W, 11, 19, 70, 70, 70)
    # Front sight
    _px(p, W, 5, 10, 120, 120, 120)
    # Rear sight
    _px(p, W, 22, 10, 120, 120, 120)
    # Tube highlight
    _px(p, W, 8, 13, 100, 125, 65)
    _px(p, W, 16, 14, 100, 125, 65)
    # Exhaust vent (rear)
    _box(p, W, 26, 14, 28, 16, 50, 50, 50)
    return _make_png(W, H, bytes(p))


def _gen_weapon_fist() -> str:
    """32 x 32 bare fist sprite (skin tone, clenched)."""
    W, H = 32, 32
    p = bytearray(W * H * 4)
    # Main fist (skin tone)
    _box(p, W, 10, 8, 22, 22, 220, 180, 140)
    # Knuckles (lighter)
    _px(p, W, 11, 9, 235, 195, 155)
    _px(p, W, 14, 9, 235, 195, 155)
    _px(p, W, 17, 9, 235, 195, 155)
    _px(p, W, 20, 9, 235, 195, 155)
    # Finger lines
    _px(p, W, 11, 13, 200, 160, 120)
    _px(p, W, 14, 14, 200, 160, 120)
    _px(p, W, 17, 13, 200, 160, 120)
    _px(p, W, 20, 14, 200, 160, 120)
    # Thumb (wrapped)
    _box(p, W, 8, 12, 11, 18, 210, 170, 130)
    # Thumb nail
    _px(p, W, 9, 13, 240, 210, 180)
    # Wrist (darker skin)
    _box(p, W, 11, 22, 21, 28, 195, 155, 115)
    # Wrist crease
    _px(p, W, 12, 23, 180, 140, 100)
    _px(p, W, 16, 24, 180, 140, 100)
    # Fist shadow
    _px(p, W, 21, 20, 190, 150, 110)
    _px(p, W, 22, 16, 190, 150, 110)
    return _make_png(W, H, bytes(p))


# ── FPS weapon sprites (first-person held view, 128x128, 60° angle) ───────────

def _gen_weapon_pistol_fps() -> str:
    """128x128 FPS pistol — 60° angle, hand from bottom-right, muzzle upper-right."""
    W, H = 128, 128
    p = bytearray(W * H * 4)
    # Right arm (bottom-right corner, fills to bottom edge)
    _box(p, W, 76, 80, 118, 128, 195, 155, 115)
    _box(p, W, 80, 74, 124, 128, 200, 160, 120)
    # Forearm skin details
    _px(p, W, 82, 90, 185, 145, 105)
    _px(p, W, 88, 95, 185, 145, 105)
    _px(p, W, 94, 100, 185, 145, 105)
    # Right hand gripping pistol (knuckles)
    _box(p, W, 68, 64, 96, 86, 210, 170, 130)
    _px(p, W, 69, 65, 230, 190, 150)
    _px(p, W, 73, 64, 230, 190, 150)
    _px(p, W, 77, 64, 230, 190, 150)
    _px(p, W, 81, 64, 230, 190, 150)
    _px(p, W, 85, 64, 230, 190, 150)
    _px(p, W, 89, 64, 230, 190, 150)
    _px(p, W, 93, 65, 230, 190, 150)
    # Finger creases
    _px(p, W, 70, 72, 195, 155, 115)
    _px(p, W, 74, 70, 195, 155, 115)
    _px(p, W, 78, 70, 195, 155, 115)
    _px(p, W, 82, 70, 195, 155, 115)
    _px(p, W, 86, 70, 195, 155, 115)
    _px(p, W, 90, 71, 195, 155, 115)
    # Thumb wrapped around grip
    _box(p, W, 62, 72, 70, 88, 205, 165, 125)
    _px(p, W, 63, 73, 220, 180, 140)
    # Pistol grip (brown, in hand)
    _box(p, W, 68, 44, 84, 68, 139, 90, 43)
    _box(p, W, 70, 46, 82, 66, 125, 80, 38)
    _px(p, W, 71, 50, 110, 70, 32)
    _px(p, W, 74, 56, 110, 70, 32)
    _px(p, W, 77, 62, 110, 70, 32)
    # Grip texture lines
    _px(p, W, 69, 48, 100, 60, 28)
    _px(p, W, 69, 52, 100, 60, 28)
    _px(p, W, 69, 56, 100, 60, 28)
    _px(p, W, 69, 60, 100, 60, 28)
    # Trigger guard
    _box(p, W, 60, 42, 68, 54, 100, 100, 100)
    _px(p, W, 61, 46, 80, 80, 80)
    _px(p, W, 62, 50, 80, 80, 80)
    # Trigger
    _px(p, W, 64, 48, 90, 90, 90)
    _px(p, W, 64, 49, 90, 90, 90)
    # Slide (60° angle)
    for i in range(28):
        sx = 68 - i
        sy = 44 - i * 2
        if sy < 0: break
        _px(p, W, sx, sy, 120, 120, 120)
        _px(p, W, sx, sy + 1, 120, 120, 120)
        _px(p, W, sx + 1, sy, 145, 145, 145)
        _px(p, W, sx - 1, sy + 2, 100, 100, 100)
    # Slide serrations
    for i in range(5):
        sx = 62 - i * 4
        sy = 32 - i * 8
        if sy > 0:
            _px(p, W, sx, sy, 100, 100, 100)
            _px(p, W, sx, sy + 1, 100, 100, 100)
    # Barrel (extending further)
    for i in range(14):
        bx = 40 - i
        by = 0 - i * 2 + 40
        if by < 0: break
        _px(p, W, bx, by, 80, 80, 80)
        _px(p, W, bx, by + 1, 80, 80, 80)
        _px(p, W, bx + 1, by, 95, 95, 95)
    # Muzzle (dark circle at tip)
    _px(p, W, 26, 2, 50, 50, 50)
    _px(p, W, 27, 2, 50, 50, 50)
    _px(p, W, 28, 2, 50, 50, 50)
    _px(p, W, 25, 3, 50, 50, 50)
    _px(p, W, 29, 3, 50, 50, 50)
    _px(p, W, 26, 4, 40, 40, 40)
    _px(p, W, 27, 4, 40, 40, 40)
    _px(p, W, 28, 4, 40, 40, 40)
    # Front sight
    _box(p, W, 28, 6, 30, 10, 150, 150, 150)
    _px(p, W, 29, 7, 170, 170, 170)
    # Rear sight (near hand)
    _box(p, W, 62, 34, 66, 38, 150, 150, 150)
    _px(p, W, 63, 35, 170, 170, 170)
    # Ejection port
    _box(p, W, 50, 28, 56, 34, 90, 90, 90)
    _px(p, W, 51, 29, 75, 75, 75)
    # Accessory rail (under barrel)
    _box(p, W, 54, 40, 62, 44, 80, 80, 80)
    return _make_png(W, H, bytes(p))


def _gen_weapon_rifle_fps() -> str:
    """128x128 FPS rifle — 60° angle, two hands, muzzle upper-right."""
    W, H = 128, 128
    p = bytearray(W * H * 4)
    # Right arm (bottom-right corner, fills to bottom edge)
    _box(p, W, 78, 76, 118, 128, 195, 155, 115)
    _box(p, W, 82, 70, 124, 128, 200, 160, 120)
    # Forearm details
    _px(p, W, 84, 86, 185, 145, 105)
    _px(p, W, 90, 92, 185, 145, 105)
    _px(p, W, 96, 98, 185, 145, 105)
    # Right hand gripping stock
    _box(p, W, 70, 64, 96, 84, 210, 170, 130)
    _px(p, W, 71, 65, 230, 190, 150)
    _px(p, W, 75, 64, 230, 190, 150)
    _px(p, W, 79, 64, 230, 190, 150)
    _px(p, W, 83, 64, 230, 190, 150)
    _px(p, W, 87, 64, 230, 190, 150)
    _px(p, W, 91, 64, 230, 190, 150)
    _px(p, W, 95, 65, 230, 190, 150)
    # Finger creases
    _px(p, W, 72, 72, 195, 155, 115)
    _px(p, W, 76, 70, 195, 155, 115)
    _px(p, W, 80, 70, 195, 155, 115)
    _px(p, W, 84, 70, 195, 155, 115)
    _px(p, W, 88, 70, 195, 155, 115)
    _px(p, W, 92, 71, 195, 155, 115)
    # Thumb
    _box(p, W, 64, 72, 72, 86, 205, 165, 125)
    _px(p, W, 65, 73, 220, 180, 140)
    # Rifle stock (brown wood)
    _box(p, W, 72, 48, 96, 68, 139, 90, 43)
    _box(p, W, 74, 50, 94, 66, 125, 80, 38)
    _px(p, W, 76, 52, 110, 70, 32)
    _px(p, W, 80, 58, 110, 70, 32)
    _px(p, W, 84, 64, 110, 70, 32)
    # Wood grain
    _px(p, W, 73, 52, 115, 72, 35)
    _px(p, W, 73, 56, 115, 72, 35)
    _px(p, W, 73, 60, 115, 72, 35)
    # Receiver (grey)
    _box(p, W, 50, 34, 74, 52, 100, 100, 100)
    _box(p, W, 52, 36, 72, 50, 115, 115, 115)
    _px(p, W, 54, 38, 130, 130, 130)
    _px(p, W, 60, 44, 130, 130, 130)
    # Trigger guard
    _box(p, W, 56, 50, 64, 60, 90, 90, 90)
    _px(p, W, 57, 53, 70, 70, 70)
    _px(p, W, 58, 56, 70, 70, 70)
    # Trigger
    _px(p, W, 59, 52, 80, 80, 80)
    _px(p, W, 59, 53, 80, 80, 80)
    # Magazine
    _box(p, W, 58, 54, 66, 72, 60, 60, 60)
    _box(p, W, 59, 56, 64, 70, 50, 50, 50)
    # Left hand supporting foregrip
    _box(p, W, 30, 44, 46, 58, 210, 170, 130)
    _px(p, W, 31, 45, 230, 190, 150)
    _px(p, W, 35, 44, 230, 190, 150)
    _px(p, W, 39, 44, 230, 190, 150)
    _px(p, W, 43, 44, 230, 190, 150)
    # Left thumb
    _box(p, W, 28, 50, 32, 58, 205, 165, 125)
    # Barrel (60° angle)
    for i in range(38):
        bx = 50 - i
        by = 34 - i * 2
        if by < 0: break
        _px(p, W, bx, by, 70, 70, 70)
        _px(p, W, bx, by + 1, 70, 70, 70)
        _px(p, W, bx + 1, by, 90, 90, 90)
        _px(p, W, bx - 1, by + 2, 55, 55, 55)
    # Muzzle brake
    for i in range(4):
        mx = 12 - i
        my = 0 - i * 2 + 14
        if my > 0: break
        _px(p, W, mx, my, 60, 60, 60)
        _px(p, W, mx + 1, my, 60, 60, 60)
    # Muzzle (dark)
    _px(p, W, 12, 2, 50, 50, 50)
    _px(p, W, 13, 2, 50, 50, 50)
    _px(p, W, 14, 2, 50, 50, 50)
    _px(p, W, 11, 3, 50, 50, 50)
    _px(p, W, 15, 3, 50, 50, 50)
    _px(p, W, 12, 4, 40, 40, 40)
    _px(p, W, 13, 4, 40, 40, 40)
    _px(p, W, 14, 4, 40, 40, 40)
    # Front sight
    _box(p, W, 14, 6, 16, 12, 150, 150, 150)
    _px(p, W, 15, 8, 170, 170, 170)
    # Rear sight
    _box(p, W, 44, 26, 50, 32, 150, 150, 150)
    _px(p, W, 45, 28, 170, 170, 170)
    # Scope rail
    _box(p, W, 38, 24, 50, 28, 80, 80, 80)
    _px(p, W, 39, 25, 95, 95, 95)
    # Forward assist
    _px(p, W, 66, 42, 85, 85, 85)
    _px(p, W, 67, 42, 85, 85, 85)
    return _make_png(W, H, bytes(p))


def _gen_weapon_sword_fps() -> str:
    """128x128 FPS sword — 60° angle, blade upper-right."""
    W, H = 128, 128
    p = bytearray(W * H * 4)
    # Right arm (bottom-right, fills to bottom edge)
    _box(p, W, 76, 78, 118, 128, 195, 155, 115)
    _box(p, W, 80, 72, 124, 128, 200, 160, 120)
    # Forearm details
    _px(p, W, 82, 88, 185, 145, 105)
    _px(p, W, 88, 94, 185, 145, 105)
    _px(p, W, 94, 100, 185, 145, 105)
    # Right hand gripping hilt
    _box(p, W, 66, 62, 94, 84, 210, 170, 130)
    _px(p, W, 67, 63, 230, 190, 150)
    _px(p, W, 71, 62, 230, 190, 150)
    _px(p, W, 75, 62, 230, 190, 150)
    _px(p, W, 79, 62, 230, 190, 150)
    _px(p, W, 83, 62, 230, 190, 150)
    _px(p, W, 87, 62, 230, 190, 150)
    _px(p, W, 91, 63, 230, 190, 150)
    # Finger creases
    _px(p, W, 68, 70, 195, 155, 115)
    _px(p, W, 72, 68, 195, 155, 115)
    _px(p, W, 76, 68, 195, 155, 115)
    _px(p, W, 80, 68, 195, 155, 115)
    _px(p, W, 84, 68, 195, 155, 115)
    _px(p, W, 88, 69, 195, 155, 115)
    # Thumb
    _box(p, W, 60, 70, 68, 84, 205, 165, 125)
    _px(p, W, 61, 71, 220, 180, 140)
    # Grip (dark leather, 60° angle)
    for i in range(16):
        gx = 66 - i
        gy = 62 - i * 2
        if gy < 0: break
        _px(p, W, gx, gy, 50, 30, 15)
        _px(p, W, gx, gy + 1, 50, 30, 15)
        _px(p, W, gx + 1, gy, 65, 40, 22)
    # Grip wrapping
    for i in range(4):
        wx = 62 - i * 3
        wy = 54 - i * 6
        if wy > 0:
            _px(p, W, wx, wy, 40, 25, 12)
            _px(p, W, wx + 1, wy, 40, 25, 12)
    # Crossguard (golden, 60° angle)
    for i in range(14):
        cx = 50 - i
        cy = 30 - i * 2
        if cy < 0: break
        _px(p, W, cx, cy, 218, 165, 32)
        _px(p, W, cx, cy + 1, 218, 165, 32)
        _px(p, W, cx + 1, cy, 240, 190, 60)
        _px(p, W, cx - 1, cy + 2, 195, 145, 25)
    # Crossguard detail
    _px(p, W, 48, 26, 255, 210, 80)
    _px(p, W, 46, 30, 255, 210, 80)
    # Blade (silver, 60° angle to upper-right)
    for i in range(20):
        bx = 36 - i
        by = 2 - i * 2
        if by < 0: break
        _px(p, W, bx, by, 200, 200, 210)
        _px(p, W, bx, by + 1, 200, 200, 210)
        _px(p, W, bx + 1, by, 225, 225, 235)
        _px(p, W, bx - 1, by + 2, 175, 175, 185)
        _px(p, W, bx, by + 3, 160, 160, 170)
    # Blade edge highlight
    for i in range(18):
        ex = 34 - i
        ey = 4 - i * 2
        if ey > 0:
            _px(p, W, ex, ey, 240, 240, 250)
    # Blade tip
    _px(p, W, 16, 0, 210, 210, 220)
    _px(p, W, 17, 0, 220, 220, 230)
    _px(p, W, 16, 1, 230, 230, 240)
    _px(p, W, 18, 0, 210, 210, 220)
    return _make_png(W, H, bytes(p))


def _gen_weapon_bazooka_fps() -> str:
    """128x128 FPS bazooka — 60° angle, tube upper-right."""
    W, H = 128, 128
    p = bytearray(W * H * 4)
    # Right arm/shoulder (bottom-right, fills to bottom edge)
    _box(p, W, 76, 74, 118, 128, 195, 155, 115)
    _box(p, W, 80, 68, 124, 128, 200, 160, 120)
    # Forearm details
    _px(p, W, 82, 84, 185, 145, 105)
    _px(p, W, 88, 90, 185, 145, 105)
    _px(p, W, 94, 96, 185, 145, 105)
    # Right hand on rear grip
    _box(p, W, 66, 62, 94, 82, 210, 170, 130)
    _px(p, W, 67, 63, 230, 190, 150)
    _px(p, W, 71, 62, 230, 190, 150)
    _px(p, W, 75, 62, 230, 190, 150)
    _px(p, W, 79, 62, 230, 190, 150)
    _px(p, W, 83, 62, 230, 190, 150)
    _px(p, W, 87, 62, 230, 190, 150)
    _px(p, W, 91, 63, 230, 190, 150)
    # Finger creases
    _px(p, W, 68, 70, 195, 155, 115)
    _px(p, W, 72, 68, 195, 155, 115)
    _px(p, W, 76, 68, 195, 155, 115)
    _px(p, W, 80, 68, 195, 155, 115)
    _px(p, W, 84, 68, 195, 155, 115)
    _px(p, W, 88, 69, 195, 155, 115)
    # Thumb
    _box(p, W, 60, 70, 68, 84, 205, 165, 125)
    _px(p, W, 61, 71, 220, 180, 140)
    # Shoulder rest (on shoulder)
    _box(p, W, 72, 48, 96, 66, 70, 90, 45)
    _box(p, W, 74, 50, 94, 64, 60, 80, 38)
    _px(p, W, 76, 52, 85, 105, 55)
    # Shoulder pad detail
    _px(p, W, 73, 54, 55, 75, 35)
    _px(p, W, 73, 58, 55, 75, 35)
    # Main tube (olive green, 60° angle)
    for i in range(34):
        tx = 72 - i
        ty = 48 - i * 2
        if ty < 0: break
        _px(p, W, tx, ty, 80, 100, 50)
        _px(p, W, tx, ty + 1, 80, 100, 50)
        _px(p, W, tx + 1, ty, 100, 125, 65)
        _px(p, W, tx - 1, ty + 2, 65, 85, 40)
        _px(p, W, tx, ty + 2, 70, 90, 45)
    # Tube bands
    for b in range(3):
        bx = 62 - b * 10
        by = 28 - b * 20
        if by > 0:
            _px(p, W, bx, by, 90, 110, 55)
            _px(p, W, bx + 1, by, 90, 110, 55)
    # Front opening (dark)
    _px(p, W, 38, 2, 40, 40, 40)
    _px(p, W, 39, 2, 40, 40, 40)
    _px(p, W, 40, 2, 40, 40, 40)
    _px(p, W, 37, 3, 40, 40, 40)
    _px(p, W, 41, 3, 40, 40, 40)
    _px(p, W, 38, 4, 30, 30, 30)
    _px(p, W, 39, 4, 30, 30, 30)
    _px(p, W, 40, 4, 30, 30, 30)
    # Left hand supporting foregrip
    _box(p, W, 34, 46, 50, 60, 210, 170, 130)
    _px(p, W, 35, 47, 230, 190, 150)
    _px(p, W, 39, 46, 230, 190, 150)
    _px(p, W, 43, 46, 230, 190, 150)
    _px(p, W, 47, 46, 230, 190, 150)
    # Left thumb
    _box(p, W, 32, 52, 36, 60, 205, 165, 125)
    # Foregrip (below tube)
    _box(p, W, 36, 54, 46, 68, 100, 80, 50)
    _box(p, W, 37, 56, 44, 66, 90, 70, 42)
    _px(p, W, 38, 58, 85, 65, 40)
    # Trigger guard
    _box(p, W, 50, 54, 58, 62, 90, 90, 90)
    _px(p, W, 51, 56, 70, 70, 70)
    _px(p, W, 52, 58, 70, 70, 70)
    # Trigger
    _px(p, W, 53, 55, 80, 80, 80)
    _px(p, W, 53, 56, 80, 80, 80)
    # Front sight
    _box(p, W, 40, 4, 42, 10, 130, 130, 130)
    _px(p, W, 41, 6, 150, 150, 150)
    # Rear sight
    _box(p, W, 64, 36, 68, 42, 130, 130, 130)
    _px(p, W, 65, 38, 150, 150, 150)
    # Exhaust vent (rear)
    _px(p, W, 76, 50, 50, 50, 50)
    _px(p, W, 78, 48, 50, 50, 50)
    _px(p, W, 80, 46, 50, 50, 50)
    # Sighting scope
    _box(p, W, 58, 32, 66, 40, 45, 45, 50)
    _px(p, W, 59, 34, 60, 60, 65)
    return _make_png(W, H, bytes(p))


def _gen_weapon_fist_fps() -> str:
    """128x128 FPS fist — 60° angle, fist punching upper-right."""
    W, H = 128, 128
    p = bytearray(W * H * 4)
    # Forearm (bottom-right, 60° angle, fills to bottom edge)
    for i in range(28):
        ax = 98 - i
        ay = 128 - i * 2
        if ay < 72: break
        _box(p, W, ax - 6, ay, ax + 6, min(ay + 8, 128), 195, 155, 115)
        _box(p, W, ax - 3, ay - 3, ax + 3, min(ay + 5, 128), 200, 160, 120)
    # Forearm hair detail
    _px(p, W, 88, 100, 180, 140, 100)
    _px(p, W, 92, 106, 180, 140, 100)
    _px(p, W, 96, 112, 180, 140, 100)
    # Wrist
    _box(p, W, 58, 56, 76, 72, 205, 165, 125)
    _px(p, W, 59, 58, 185, 145, 105)
    _px(p, W, 66, 59, 185, 145, 105)
    _px(p, W, 73, 60, 185, 145, 105)
    # Wrist bone
    _px(p, W, 62, 57, 215, 175, 135)
    _px(p, W, 70, 57, 215, 175, 135)
    # Main fist (60° orientation)
    _box(p, W, 32, 14, 66, 52, 220, 180, 140)
    _box(p, W, 34, 16, 64, 50, 215, 175, 135)
    # Knuckles (prominent, lighter)
    _px(p, W, 34, 15, 240, 200, 160)
    _px(p, W, 38, 14, 240, 200, 160)
    _px(p, W, 42, 14, 240, 200, 160)
    _px(p, W, 46, 14, 240, 200, 160)
    _px(p, W, 50, 15, 240, 200, 160)
    _px(p, W, 54, 16, 240, 200, 160)
    _px(p, W, 58, 18, 240, 200, 160)
    _px(p, W, 62, 20, 240, 200, 160)
    # Knuckle shadows
    _px(p, W, 35, 17, 200, 160, 120)
    _px(p, W, 39, 16, 200, 160, 120)
    _px(p, W, 43, 16, 200, 160, 120)
    _px(p, W, 47, 16, 200, 160, 120)
    _px(p, W, 51, 17, 200, 160, 120)
    _px(p, W, 55, 18, 200, 160, 120)
    # Finger segments
    _box(p, W, 33, 22, 41, 36, 215, 175, 135)
    _box(p, W, 41, 20, 49, 36, 215, 175, 135)
    _box(p, W, 49, 19, 57, 36, 215, 175, 135)
    _box(p, W, 57, 20, 65, 36, 215, 175, 135)
    # Finger creases
    _px(p, W, 34, 29, 200, 160, 120)
    _px(p, W, 35, 30, 200, 160, 120)
    _px(p, W, 42, 28, 200, 160, 120)
    _px(p, W, 43, 29, 200, 160, 120)
    _px(p, W, 50, 27, 200, 160, 120)
    _px(p, W, 51, 28, 200, 160, 120)
    _px(p, W, 58, 28, 200, 160, 120)
    _px(p, W, 59, 29, 200, 160, 120)
    # Thumb (wrapped over fingers)
    _box(p, W, 30, 32, 40, 48, 210, 170, 130)
    _box(p, W, 31, 33, 38, 46, 215, 175, 135)
    _px(p, W, 31, 34, 230, 190, 150)
    _px(p, W, 32, 35, 245, 215, 185)
    # Thumb knuckle
    _px(p, W, 33, 33, 235, 195, 155)
    # Fist shadow
    _px(p, W, 64, 44, 200, 160, 120)
    _px(p, W, 65, 40, 200, 160, 120)
    _px(p, W, 66, 36, 200, 160, 120)
    _px(p, W, 67, 32, 200, 160, 120)
    # Impact lines (60° motion toward upper-right)
    _px(p, W, 26, 10, 255, 255, 255)
    _px(p, W, 24, 6, 255, 255, 255)
    _px(p, W, 22, 2, 255, 255, 255)
    _px(p, W, 20, 0, 255, 255, 255)
    _px(p, W, 28, 4, 255, 255, 255)
    _px(p, W, 30, 8, 255, 255, 255)
    return _make_png(W, H, bytes(p))


# ── Public API ───────────────────────────────────────────────────────────────

@dataclass
class PrefabSprite:
    """A single prefab image as a base64 data URI."""
    data_uri: str
    width: int
    height: int


@dataclass
class PrefabCharacter:
    """Animation frames for a prefab character."""
    idle: PrefabSprite
    walk: list[PrefabSprite] = field(default_factory=list)


# ── Lazy-evaluated prefab instances ─────────────────────────────────────────

HERO = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_hero_idle(), width=32, height=64),
    walk=[
        PrefabSprite(data_uri=_gen_hero_walk1(), width=32, height=64),
        PrefabSprite(data_uri=_gen_hero_walk2(), width=32, height=64),
    ],
)
"""Default hero sprite with idle + walk animation."""

ENEMY = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_enemy_idle(), width=32, height=64),
    walk=[
        PrefabSprite(data_uri=_gen_enemy_walk1(), width=32, height=64),
        PrefabSprite(data_uri=_gen_enemy_walk2(), width=32, height=64),
    ],
)
"""Default enemy (demon) sprite with idle + walk animation."""

SKELETON = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_skeleton_idle(), width=32, height=64),
    walk=[
        PrefabSprite(data_uri=_gen_skeleton_walk1(), width=32, height=64),
        PrefabSprite(data_uri=_gen_skeleton_walk2(), width=32, height=64),
    ],
)
"""Skeleton sprite with idle + walk animation."""

SLIME = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_slime_idle(), width=32, height=32),
    walk=[
        PrefabSprite(data_uri=_gen_slime_walk1(), width=32, height=32),
        PrefabSprite(data_uri=_gen_slime_walk2(), width=32, height=32),
    ],
)
"""Slime sprite with idle + walk animation."""

ITEM = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_item_coin(), width=32, height=32),
)
"""Default item sprite (coin)."""

KEY = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_item_key(), width=32, height=32),
)
"""Key item sprite."""


BAT = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_bat_idle(), width=32, height=32),
    walk=[PrefabSprite(data_uri=_gen_bat_fly1(), width=32, height=32),
          PrefabSprite(data_uri=_gen_bat_fly2(), width=32, height=32)],
)
"""Flying bat sprite (use z=1.5 for elevated position)."""


# ── Weapon prefabs ───────────────────────────────────────────────────────────

PISTOL = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_pistol(), width=32, height=32),
)
"""Pistol weapon sprite (sidearm)."""

RIFLE = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_rifle(), width=32, height=32),
)
"""Rifle weapon sprite (primary)."""

SWORD = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_sword(), width=32, height=32),
)
"""Sword weapon sprite (melee)."""

BAZOOKA = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_bazooka(), width=32, height=32),
)
"""Bazooka/rocket launcher weapon sprite (heavy)."""

FIST = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_fist(), width=32, height=32),
)
"""Bare fist weapon sprite (unarmed)."""


# ── FPS weapon prefabs (first-person held view, 64x64) ──────────────────────

PISTOL_FPS = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_pistol_fps(), width=96, height=96),
)
"""FPS pistol — held from bottom-right, barrel diagonal to upper-left."""

RIFLE_FPS = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_rifle_fps(), width=96, height=96),
)
"""FPS rifle — two hands, barrel diagonal to upper-left."""

SWORD_FPS = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_sword_fps(), width=96, height=96),
)
"""FPS sword — held from bottom-right, blade diagonal to upper-left."""

BAZOOKA_FPS = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_bazooka_fps(), width=96, height=96),
)
"""FPS bazooka — on shoulder from bottom-right, tube diagonal to upper-left."""

FIST_FPS = PrefabCharacter(
    idle=PrefabSprite(data_uri=_gen_weapon_fist_fps(), width=96, height=96),
)
"""FPS fist — arm from bottom-right, fist punching to upper-left."""


def make_prefab_sprite_defs(
    *,
    hero_pos: tuple[float, float] = (3.5, 1.5),
    enemy_positions: Optional[list[tuple[float, float]]] = None,
    item_positions: Optional[list[tuple[float, float]]] = None,
    z: float = 0.0,
) -> list:
    """Create a list of :class:`~flet_game.raycast.SpriteDef` objects using
    embedded prefab sprites.

    Import ``SpriteDef`` from ``flet_game`` separately.

    Parameters
    ----------
    hero_pos:
        World position for the hero.  ``None`` to skip.
    enemy_positions:
        List of world positions for enemies.
    item_positions:
        List of world positions for collectible items.
    z:
        Height above ground in map units (default ``0.0`` = on the floor).
    """
    from flet_game.raycast import SpriteDef  # lazy import

    result: list = []

    if hero_pos is not None:
        result.append(
            SpriteDef(x=hero_pos[0], y=hero_pos[1],
                      image=HERO.idle.data_uri,
                      aspect_ratio=0.5, z=z, world_height=1.0)
        )

    if enemy_positions:
        for pos in enemy_positions:
            result.append(
                SpriteDef(x=pos[0], y=pos[1],
                          image=ENEMY.idle.data_uri,
                          aspect_ratio=0.5, z=z, world_height=1.0)
            )

    if item_positions:
        for pos in item_positions:
            result.append(
                SpriteDef(x=pos[0], y=pos[1],
                          image=ITEM.idle.data_uri,
                          aspect_ratio=1.0, z=0.3, world_height=0.4)
            )

    return result
