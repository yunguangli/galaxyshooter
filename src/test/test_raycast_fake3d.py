"""Test script: 3D billboard sprites with z-height, scale, and ground placement.

Demonstrates SpriteDef with z (height above ground), world_height, scale_x/scale_y,
and floor_offset.  Ground sprites (z=0) stay on the floor regardless of player
movement.  Flying sprites (z>0) appear elevated with shadows on the ground below.

Usage:
    cd src
    python test/test_raycast_fake3d.py
"""
from __future__ import annotations

import math
import os
import sys

import flet as ft

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flet_game import Loop, RaycastCanvas, Scene, SpriteDef

MAP = [
    [1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1],
]

_ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets")

def main(page: ft.Page) -> None:
    page.title = "Fake 3D Sprites"
    page.bgcolor = "#111111"
    page.window.width = 520
    page.window.height = 680

    scene = Scene(page, width=500, height=600, bgcolor="#111111")
    inp   = scene.input
    loop  = Loop(page, fps=60)

    rc = RaycastCanvas(
        width=500, height=600,
        map_data=MAP,
        wall_colors=["#cc2200", "#cc2200"],
        fog_distance=6.0,
    )
    scene.add(rc.control)

    px, py, angle = 1.5, 2.5, 0.0

    # Ground sprites (z=0): feet on the floor, correct perspective
    # world_height = sprite height in map units (1.0 = one cell tall)
    # floor_offset = world-unit offset to push sprite down (compensates for
    # transparent space below the feet in the sprite image)
    sprites = [
        SpriteDef(x=3.5, y=2.5, image="monster.png",
                  z=0.0, world_height=1.0, aspect_ratio=0.45,
                  floor_offset=0.05),
        SpriteDef(x=2.5, y=3.5, image="monster.png",
                  z=0.0, world_height=1.0, aspect_ratio=0.45,
                  floor_offset=0.05),
    ]
    # Flying sprite (z=1.5): elevated above ground, shadow on floor below
    sprites.append(
        SpriteDef(x=4.0, y=1.5, image="monster.png",
                  z=1.5, world_height=0.6, aspect_ratio=0.45, shadow=True)
    )
    # Stretched sprite: scale_x/scale_y to compensate for undersized images
    sprites.append(
        SpriteDef(x=5.5, y=2.5, image="monster.png",
                  z=0.0, world_height=0.5, aspect_ratio=0.45,
                  scale_x=1.5, scale_y=2.0, floor_offset=0.05)
    )

    rc.set_sprites(sprites)

    @loop.on_update
    def on_update(dt: float) -> None:
        nonlocal px, py, angle
        speed = 3.0 * dt
        rot = 2.0 * dt
        if inp.is_key_down("arrowleft"):  angle -= rot
        if inp.is_key_down("arrowright"): angle += rot
        dx = math.cos(angle) * speed
        dy = math.sin(angle) * speed
        if inp.is_key_down("arrowup"):
            nx, ny = px + dx, py + dy
            if MAP[int(ny)][int(nx)] == 0:
                px, py = nx, ny
        if inp.is_key_down("arrowdown"):
            nx, ny = px - dx, py - dy
            if MAP[int(ny)][int(nx)] == 0:
                px, py = nx, ny
        rc.render(px, py, angle)

    scene.mount()
    loop.start()

# assets_dir is resolved relative to this script's directory (src/test/)
# so it resolves to src/assets/ where monster.png lives
ft.run(main, assets_dir=_ASSETS)
