"""
test_raycast_prefab.py — Prefab sprites raycaster demo.

Shows all built-in prefab characters and items rendered in the 3-D raycasting
view.  No external sprite PNG files required — everything is generated from
the ``flet_game.prefab`` module.

Features shown
--------------
  RaycastCanvas   — 3-D raycasting view (80 columns, 66° FOV)
  Prefab sprites  — HERO, ENEMY, SKELETON, SLIME, ITEM (coin), KEY
  SpriteDef       — billboard sprites with depth sorting + wall occlusion
  Scene           — canvas container + input wiring
  Loop            — 60 fps game loop with delta-time movement
  InputManager    — keyboard input
  Label           — on-canvas HUD overlay
  Sprite          — minimap overlay with coloured dots per enemy type

Run:  cd src && python test/test_raycast_prefab.py
"""

from __future__ import annotations

import math
import os
import sys
import time

import flet as ft
import flet.canvas as cv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import (
    HERO,
    ENEMY,
    SKELETON,
    SLIME,
    ITEM,
    KEY,
    BAT,
    PISTOL,
    RIFLE,
    SWORD,
    BAZOOKA,
    FIST,
    PISTOL_FPS,
    RIFLE_FPS,
    SWORD_FPS,
    BAZOOKA_FPS,
    FIST_FPS,
    Label,
    Loop,
    RaycastCanvas,
    Scene,
    Sprite,
    SpriteDef,
)

# ── Map ──────────────────────────────────────────────────────────────────────

MAP = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 2, 0, 0, 0, 0, 0, 0, 3, 3, 0, 0, 1],
    [1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 1],
    [1, 0, 0, 3, 3, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]

WALL_COLORS = ["#bb2200", "#1144cc", "#117744"]

# ── Layout ───────────────────────────────────────────────────────────────────

W      = 390
H      = 780
VIEW_H = 530
CTRL_H = H - VIEW_H
MINI_CELL = 7
MAP_ROWS = len(MAP)
MAP_COLS = len(MAP[0])
MINI_W = MAP_COLS * MINI_CELL
MINI_H = MAP_ROWS * MINI_CELL
MINI_X = W - MINI_W - 6
MINI_Y = 6

FOG_DISTANCE = 6.0
COLUMNS = 80

# ── Prefab sprite positions ──────────────────────────────────────────────────

# Each tuple: (SpriteDef args, minimap dot color, label)
# All sprites placed in open corridors visible from the start position (1.5, 7.5).
PREFAB_LAYOUT = [
    # Hero — visible down the left corridor
    ({"x": 2.5, "y": 1.5, "image": HERO.idle.data_uri,
      "aspect_ratio": 0.5, "world_height": 1.0}, "#00ffcc", "HERO"),
    # Enemy — right corridor
    ({"x": 8.5, "y": 1.5, "image": ENEMY.idle.data_uri,
      "aspect_ratio": 0.5, "world_height": 1.0}, "#ff4444", "ENEMY"),
    # Skeleton — far right corridor
    ({"x": 13.5, "y": 1.5, "image": SKELETON.idle.data_uri,
      "aspect_ratio": 0.5, "world_height": 1.0}, "#dddddd", "SKELETON"),
    # Slime — centre corridor (avoid wall at col 7-8)
    ({"x": 10.5, "y": 7.5, "image": SLIME.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.4}, "#44cc44", "SLIME"),
    # Coin — bottom corridor
    ({"x": 8.5, "y": 13.5, "image": ITEM.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.4}, "#ffcc00", "COIN"),
    # Key — bottom-right
    ({"x": 13.5, "y": 13.5, "image": KEY.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.4}, "#ccaa00", "KEY"),
    # Bat — flying in the central open area (elevated)
    ({"x": 5.5, "y": 5.5, "image": BAT.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.8, "z": 1.5}, "#9933cc", "BAT"),
    # Pistol — top-left corridor
    ({"x": 2.5, "y": 4.5, "image": PISTOL.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.4}, "#aaaacc", "PISTOL"),
    # Rifle — right side
    ({"x": 14.5, "y": 7.5, "image": RIFLE.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.4}, "#6688aa", "RIFLE"),
    # Sword — bottom-left
    ({"x": 2.5, "y": 13.5, "image": SWORD.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.4}, "#ccccdd", "SWORD"),
    # Bazooka — top-right
    ({"x": 13.5, "y": 4.5, "image": BAZOOKA.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.4}, "#557744", "BAZOOKA"),
    # Fist — centre
    ({"x": 7.5, "y": 10.5, "image": FIST.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.4}, "#ddaa88", "FIST"),
    # FPS weapons (placed on ground for demo — normally HUD overlays)
    ({"x": 4.5, "y": 2.5, "image": PISTOL_FPS.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.6}, "#aaaaff", "PISTOL_FPS"),
    ({"x": 6.5, "y": 2.5, "image": RIFLE_FPS.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.6}, "#6688ff", "RIFLE_FPS"),
    ({"x": 8.5, "y": 2.5, "image": SWORD_FPS.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.6}, "#ccccff", "SWORD_FPS"),
    ({"x": 10.5, "y": 2.5, "image": BAZOOKA_FPS.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.6}, "#55ff44", "BAZOOKA_FPS"),
    ({"x": 12.5, "y": 2.5, "image": FIST_FPS.idle.data_uri,
      "aspect_ratio": 1.0, "world_height": 0.6}, "#ffddaa", "FIST_FPS"),
]

# ── Player start ─────────────────────────────────────────────────────────────

START_PX    = 1.5
START_PY    = 7.5
START_ANGLE = 0.0
MOVE_SPEED  = 5.0
ROT_SPEED   = 2.0


def main(page: ft.Page) -> None:
    page.title   = "Prefab Sprite Raycaster Demo"
    page.bgcolor = "#111111"
    page.padding = 0
    page.spacing = 0
    page.window.width  = W + 20
    page.window.height = H + 80
    page.window.resizable = False

    scene = Scene(page, width=W, height=VIEW_H, bgcolor="#111111")
    inp   = scene.input

    # ── 3-D raycasting view ──────────────────────────────────────────────────
    rc = RaycastCanvas(
        width=W,
        height=VIEW_H,
        columns=COLUMNS,
        fov=66.0,
        map_data=MAP,
        wall_colors=WALL_COLORS,
        ceiling_color="#1a1a2e",
        floor_color="#3a3a3a",
        fog_distance=FOG_DISTANCE,
    )
    scene.add(rc.control, z=0)

    # ── HUD ──────────────────────────────────────────────────────────────────
    lbl_pos = Label(x=8, y=6,  text="Pos: 0.0, 0.0", size=12, color="#aaaacc")
    lbl_fps = Label(x=8, y=22, text="FPS: --",        size=12, color="#aaaacc")
    lbl_info = Label(x=8, y=38,
                     text="Prefabs: Characters + Weapons + FPS Weapons",
                     size=10, color="#888888")
    for lbl in (lbl_pos, lbl_fps, lbl_info):
        scene.add(lbl, z=10)

    # ── Minimap ──────────────────────────────────────────────────────────────
    CELL_COLORS = {0: "#1a1a2e", 1: "#bb2200", 2: "#1144cc", 3: "#117744"}
    mini_shapes = []
    for r in range(MAP_ROWS):
        for c in range(MAP_COLS):
            cell = MAP[r][c]
            mini_shapes.append(
                cv.Rect(
                    x=MINI_X + c * MINI_CELL,
                    y=MINI_Y + r * MINI_CELL,
                    width=MINI_CELL - 1,
                    height=MINI_CELL - 1,
                    paint=ft.Paint(color=CELL_COLORS.get(cell, "#bb2200")),
                )
            )
    mini_canvas = cv.Canvas(shapes=mini_shapes, width=W, height=VIEW_H)
    scene.add(mini_canvas, z=15)

    player_dot = Sprite(x=0, y=0, width=6, height=6,
                        color="#00ffcc", border_radius=3, opacity=0.9)
    scene.add(player_dot, z=16)

    # Prefab dots on minimap
    prefab_dots: list[Sprite] = []
    for _, dot_color, label in PREFAB_LAYOUT:
        dot = Sprite(x=0, y=0, width=5, height=5,
                     color=dot_color, border_radius=2, opacity=0.85)
        prefab_dots.append(dot)
        scene.add(dot, z=16)

    # ── Player state ─────────────────────────────────────────────────────────
    px    = START_PX
    py    = START_PY
    angle = START_ANGLE

    # ── FPS counter ──────────────────────────────────────────────────────────
    from collections import deque
    _frame_times: deque = deque(maxlen=30)

    # ── Game loop ────────────────────────────────────────────────────────────
    loop = Loop(page, fps=60)
    loop.register_input(scene.input)

    @loop.on_update
    def update(dt: float) -> None:
        nonlocal px, py, angle

        # Rotation
        rot = 0.0
        if inp.is_key_down("arrowleft") or inp.is_key_down("a"):
            rot -= ROT_SPEED
        if inp.is_key_down("arrowright") or inp.is_key_down("d"):
            rot += ROT_SPEED
        angle = (angle + rot * dt) % (2 * math.pi)

        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        # Movement
        speed = MOVE_SPEED * dt
        if inp.is_key_down("arrowup") or inp.is_key_down("w"):
            nx, ny = px + cos_a * speed, py + sin_a * speed
            if MAP[int(ny)][int(nx)] == 0:
                px, py = nx, ny
        if inp.is_key_down("arrowdown") or inp.is_key_down("s"):
            nx, ny = px - cos_a * speed, py - sin_a * speed
            if MAP[int(ny)][int(nx)] == 0:
                px, py = nx, ny
        # Strafe
        half_pi = math.pi / 2
        strafe_cos = math.cos(angle + half_pi)
        strafe_sin = math.sin(angle + half_pi)
        if inp.is_key_down("q"):
            nx, ny = px - strafe_cos * speed, py - strafe_sin * speed
            if MAP[int(ny)][int(nx)] == 0:
                px, py = nx, ny
        if inp.is_key_down("e"):
            nx, ny = px + strafe_cos * speed, py + strafe_sin * speed
            if MAP[int(ny)][int(nx)] == 0:
                px, py = nx, ny

        # ── Feed prefab sprites to renderer ──────────────────────────────────
        sprite_buf = []
        for args, _, _ in PREFAB_LAYOUT:
            sprite_buf.append(SpriteDef(**args))
        rc.set_sprites(sprite_buf)

        # ── Render & HUD ────────────────────────────────────────────────────
        rc.render(px, py, angle)
        player_dot.x = MINI_X + px * MINI_CELL - 3
        player_dot.y = MINI_Y + py * MINI_CELL - 3

        for i, (args, _, _) in enumerate(PREFAB_LAYOUT):
            prefab_dots[i].x = MINI_X + args["x"] * MINI_CELL - 2
            prefab_dots[i].y = MINI_Y + args["y"] * MINI_CELL - 2

        deg = math.degrees(angle) % 360
        lbl_pos.text = f"{px:.1f}, {py:.1f}  {deg:.0f} deg"

        # FPS
        now = time.monotonic()
        _frame_times.append(now)
        if len(_frame_times) >= 2:
            elapsed = _frame_times[-1] - _frame_times[0]
            fps = (len(_frame_times) - 1) / elapsed if elapsed > 0 else 0
            lbl_fps.text = f"FPS: {fps:.0f}"

    # ── Mount & start ────────────────────────────────────────────────────────
    scene.mount()
    loop.start()


if __name__ == "__main__":
    ft.run(main)
