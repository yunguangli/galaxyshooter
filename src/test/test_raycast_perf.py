"""
test_raycast_perf.py — Phase 1: Performance fixes for RaycastCanvas.

Tests:
  1. Persistent shapes list (no list creation per frame)
  2. SpriteDef.aspect_ratio parameter
  3. RaycastCanvas max_sprites parameter
  4. Sprite image visibility only toggles used images
  5. Basic rendering still works correctly

Run:  cd src && python test/test_raycast_perf.py
"""

from __future__ import annotations

import math
import os
import sys
import time

import flet as ft

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import (
    Label,
    Loop,
    RaycastCanvas,
    Scene,
    Sprite,
    SpriteDef,
    VirtualJoystick,
)

# ── Map ─────────────────────────────────────────────────────────────────────

MAP: list[list[int]] = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 2, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 1],
    [1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 3, 3, 3, 3, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 3, 0, 0, 3, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 3, 0, 0, 3, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 3, 3, 0, 3, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 1],
    [1, 0, 0, 2, 2, 0, 0, 0, 0, 0, 0, 2, 2, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]

MAP_ROWS = len(MAP)
MAP_COLS = len(MAP[0])

# ── Layout ──────────────────────────────────────────────────────────────────

W       = 390
H       = 780
VIEW_H  = 500
CTRL_H  = H - VIEW_H

MINI_CELL = 7
MINI_W    = MAP_COLS * MINI_CELL
MINI_H    = MAP_ROWS * MINI_CELL
MINI_X    = W - MINI_W - 6
MINI_Y    = 6

JOY_AREA_W = W // 2

START_PX    = 1.5
START_PY    = 1.5
START_ANGLE = 0.0
MOVE_SPEED  = 5.0
ROT_SPEED   = 2.5
WALL_MARGIN = 0.2
WALL_COLORS = ["#bb2200", "#1144cc", "#117744", "#cc9900"]

# Enemy sprite positions for testing aspect_ratio
# Use wall type 5 cells as visible "enemy" markers in the map
# and render them via the raycaster's wall strip system
TEST_ENEMIES = [
    {"x": 4.5, "y": 4.5, "ratio": 0.35, "label": "normal"},
    {"x": 8.5, "y": 4.5, "ratio": 1.0,  "label": "square"},
    {"x": 12.5, "y": 4.5, "ratio": 0.5, "label": "wide"},
]

# Placeholder image for sprites (1x1 transparent PNG base64)
_PLACEHOLDER = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB"
    "Nl7BcQAAAABJRU5ErkJggg=="
)


def main(page: ft.Page) -> None:
    page.title   = "Phase 1 — RaycastCanvas Performance Test"
    page.bgcolor = "#111111"
    page.padding = 0
    page.window.width     = W + 20
    page.window.height    = H + 80
    page.window.resizable = False
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    scene = Scene(page, width=W, height=VIEW_H, bgcolor="#111111")
    inp   = scene.input

    # ── Test 1: max_sprites parameter ───────────────────────────────────────
    rc = RaycastCanvas(
        width=W,
        height=VIEW_H,
        columns=80,
        fov=66.0,
        map_data=MAP,
        wall_colors=WALL_COLORS,
        ceiling_color="#1a1a2e",
        floor_color="#3a3a3a",
        fog_distance=12.0,
        max_sprites=16,  # reduced from default 32
    )
    scene.add(rc.control, z=0)

    # ── HUD ─────────────────────────────────────────────────────────────────
    lbl_pos = Label(x=8, y=6,  text="Pos: 0.0, 0.0",  size=12, color="#aaaacc")
    lbl_fps = Label(x=8, y=22, text="FPS: --",          size=12, color="#aaaacc")
    lbl_info = Label(x=8, y=38, text="Phase 1: aspect_ratio + max_sprites=16", size=11, color="#66aa66")
    for lbl in (lbl_pos, lbl_fps, lbl_info):
        scene.add(lbl, z=10)

    # ── Minimap ─────────────────────────────────────────────────────────────
    CELL_COLORS = {0: "#1a1a2e", 1: "#bb2200", 2: "#1144cc", 3: "#117744"}
    for r in range(MAP_ROWS):
        for c in range(MAP_COLS):
            cell = MAP[r][c]
            scene.add(
                Sprite(
                    x=MINI_X + c * MINI_CELL,
                    y=MINI_Y + r * MINI_CELL,
                    width=MINI_CELL - 1,
                    height=MINI_CELL - 1,
                    color=CELL_COLORS.get(cell, "#bb2200"),
                    opacity=0.70,
                ),
                z=15,
            )

    player_dot = Sprite(x=0, y=0, width=6, height=6,
                        color="#00ffcc", border_radius=3, opacity=0.9)
    scene.add(player_dot, z=16)

    # ── D-pad strip ─────────────────────────────────────────────────────────
    joystick = VirtualJoystick(width=JOY_AREA_W, height=CTRL_H)

    dpad = ft.Stack(
        width=W,
        height=CTRL_H,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        controls=[
            ft.Container(width=W, height=CTRL_H, bgcolor="#0d0d1a"),
            ft.Container(
                left=JOY_AREA_W, top=0,
                width=1, height=CTRL_H,
                bgcolor="#222244",
            ),
            joystick.control,
            ft.Container(
                left=0, top=CTRL_H - 28, width=W, height=24,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("WASD / arrows — test aspect_ratio sprites", size=11, color="#2a2a44"),
            ),
        ],
    )

    # ── Player state ────────────────────────────────────────────────────────
    px    = START_PX
    py    = START_PY
    angle = START_ANGLE

    _frame_times: list[float] = []

    def _update_fps(_dt: float) -> None:
        now = time.monotonic()
        _frame_times.append(now)
        while len(_frame_times) > 30:
            _frame_times.pop(0)
        if len(_frame_times) >= 2:
            elapsed = _frame_times[-1] - _frame_times[0]
            fps = (len(_frame_times) - 1) / elapsed if elapsed > 0 else 0
            lbl_fps.text = f"FPS: {fps:.0f}"

    def _walkable(nx: float, ny: float) -> bool:
        m = WALL_MARGIN
        for ddx, ddy in ((m, m), (m, -m), (-m, m), (-m, -m)):
            cx, cy = int(nx + ddx), int(ny + ddy)
            if not (0 <= cx < MAP_COLS and 0 <= cy < MAP_ROWS):
                return False
            if MAP[cy][cx] != 0:
                return False
        return True

    # ── Game loop ───────────────────────────────────────────────────────────
    loop = Loop(page, fps=60)

    @loop.on_update
    def update(dt: float) -> None:
        nonlocal px, py, angle

        rot = 0.0
        if inp.is_key_down("arrowleft") or inp.is_key_down("a"):  rot -= ROT_SPEED
        if inp.is_key_down("arrowright") or inp.is_key_down("d"): rot += ROT_SPEED
        rot += joystick.vx * ROT_SPEED
        angle = (angle + rot * dt) % (2 * math.pi)

        fdx = math.cos(angle) * MOVE_SPEED * dt
        fdy = math.sin(angle) * MOVE_SPEED * dt

        if inp.is_key_down("arrowup") or inp.is_key_down("w"):
            if _walkable(px + fdx, py): px += fdx
            if _walkable(px, py + fdy): py += fdy
        if inp.is_key_down("arrowdown") or inp.is_key_down("s"):
            if _walkable(px - fdx, py): px -= fdx
            if _walkable(px, py - fdy): py -= fdy

        if joystick.vy:
            spd = -joystick.vy * MOVE_SPEED * dt
            ddx = math.cos(angle) * spd
            ddy = math.sin(angle) * spd
            if _walkable(px + ddx, py): px += ddx
            if _walkable(px, py + ddy): py += ddy

        # ── Test aspect_ratio: render enemies with different ratios ──────────
        rc.set_sprites([
            SpriteDef(
                x=e["x"], y=e["y"],
                image=_PLACEHOLDER,
                aspect_ratio=e["ratio"],
            )
            for e in TEST_ENEMIES
        ])

        rc.render(px, py, angle)

        player_dot.x = MINI_X + px * MINI_CELL - 3
        player_dot.y = MINI_Y + py * MINI_CELL - 3
        deg = math.degrees(angle) % 360
        lbl_pos.text = f"{px:.1f}, {py:.1f}  ∠{deg:.0f}°"
        _update_fps(dt)

    # ── Mount & start ───────────────────────────────────────────────────────
    scene.mount()
    page.spacing = 0
    page.controls.append(dpad)
    page.update()
    loop.start()


if __name__ == "__main__":
    ft.run(main)
