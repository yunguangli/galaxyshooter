"""
test_raycast.py — Step 11: RaycastCanvas demo (Wolfenstein-style 3D).

A playable first-person raycasting demo with both keyboard and on-screen
touch controls, so it runs on desktop and mobile phones.

Keyboard controls
-----------------
  Arrow-Left  / A  : rotate left
  Arrow-Right / D  : rotate right
  Arrow-Up    / W  : move forward
  Arrow-Down  / S  : move backward

Touch controls (on-screen D-pad)
---------------------------------
  The bottom 280 px shows a cross-shaped D-pad:
      [▲ FWD]
  [◄ ROT]   [► ROT]
      [▼ BWD]

Features shown
--------------
  RaycastCanvas   — 3D raycasting view (80 columns, 66° FOV)
  Scene           — canvas container + input wiring
  Loop            — 60 fps game loop with delta-time movement
  InputManager    — keyboard + virtual-key touch controls (press_key / release_key)
  Label           — on-canvas HUD overlay (position, FPS)
  Sprite          — minimap overlay in top-right corner

Run:  cd src && python test/test_raycast.py
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
    VirtualJoystick,
)

# ── Map ─────────────────────────────────────────────────────────────────────────────────

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

# ── Layout ────────────────────────────────────────────────────────────────────────────

W       = 390            # portrait phone width
H       = 780            # portrait phone height
VIEW_H  = 500            # 3-D raycasting viewport
CTRL_H  = H - VIEW_H    # 280 px touch-control strip

# Minimap (top-right corner of the 3-D view)
MINI_CELL = 7                               # px per map cell
MINI_W    = MAP_COLS * MINI_CELL            # 112 px
MINI_H    = MAP_ROWS * MINI_CELL            # 112 px
MINI_X    = W - MINI_W - 6                 # top-left x inside scene
MINI_Y    = 6                              # top-left y inside scene

# Virtual joystick (left half of D-pad strip)
# Y coords are relative to the D-pad Stack origin (not the full window).
JOY_AREA_W  = W // 2     # 195 — left half is the joystick touch zone
JOY_BASE_R  = 60          # outer ring radius (px)
JOY_KNOB_R  = 28          # inner knob radius (px)
JOY_MAX_R   = 52          # max knob displacement from touch origin (px)

# Dash (right half of D-pad strip)
DASH_SPEED    = 12.0      # lateral strafe speed during a dash (map units/sec)
DASH_DURATION = 0.18      # how long each dash lasts (seconds)

# Player start
START_PX    = 1.5
START_PY    = 1.5
START_ANGLE = 0.0           # facing east (+X)

# Movement  (auto-sprint: high default speed, no manual toggle needed)
MOVE_SPEED  = 5.0            # map units / second
ROT_SPEED   = 2.5            # radians / second
WALL_MARGIN = 0.2            # collision buffer (map units)

# Wall colours: type 1=red, type 2=blue, type 3=green
WALL_COLORS = ["#bb2200", "#1144cc", "#117744", "#cc9900"]


# ── Touch button helper ──────────────────────────────────────────────────────────────────

# ── Main ─────────────────────────────────────────────────────────────────────────────────

def main(page: ft.Page) -> None:
    page.title   = "flet_game — RaycastCanvas demo"
    page.bgcolor = "#111111"
    page.padding = 0
    page.window.width     = W + 20
    page.window.height    = H + 80
    page.window.resizable = False
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    scene = Scene(page, width=W, height=VIEW_H, bgcolor="#111111")
    inp   = scene.input

    # ── 3-D raycasting view (fills top VIEW_H px) ──────────────────────────────
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
    )
    scene.add(rc.control, z=0)

    # ── HUD overlay (top-left of the 3-D view) ──────────────────────────────
    lbl_pos = Label(x=8, y=6,  text="Pos: 0.0, 0.0",  size=12, color="#aaaacc")
    lbl_fps = Label(x=8, y=22, text="FPS: --",          size=12, color="#aaaacc")
    for lbl in (lbl_pos, lbl_fps):
        scene.add(lbl, z=10)

    # ── Minimap (top-right corner of the 3-D view) ─────────────────────────
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

    # ── D-pad strip: virtual joystick (left) + dash buttons (right) ─────────────
    # Lives outside the scene's GestureDetector — no nesting conflict.

    # Virtual joystick (reusable engine component — vx/vy read each frame)
    joystick = VirtualJoystick(width=JOY_AREA_W, height=CTRL_H)

    # Dash state
    _dash_timer = 0.0   # seconds remaining for current dash
    _dash_dir   = 0.0   # +1 = strafe right, -1 = strafe left

    # Dash buttons (right half) — single-tap to trigger a lateral strafe burst
    def _make_dash(label: str, x: float, y: float, w: float, h: float, direction: float):
        def _fire(_e) -> None:
            nonlocal _dash_timer, _dash_dir
            _dash_timer = DASH_DURATION
            _dash_dir   = direction
        return ft.GestureDetector(
            left=x, top=y, width=w, height=h,
            on_tap_down=_fire,
            content=ft.Container(
                width=w, height=h,
                bgcolor="#ffffff0d",
                border_radius=ft.BorderRadius.all(14),
                border=ft.Border.all(1.5, "#ffffff20"),
                alignment=ft.Alignment.CENTER,
                content=ft.Text(label, size=28, color="#aaccee",
                                weight=ft.FontWeight.BOLD),
            ),
        )

    _dash_bw  = (W - JOY_AREA_W - 12) // 2    # ~89 px per dash button
    _dash_by2 = (CTRL_H - 120) // 2           # y to centre 120-px buttons
    dash_l = _make_dash("◄◄", JOY_AREA_W + 6,              _dash_by2, _dash_bw, 120, -1.0)
    dash_r = _make_dash("►►", JOY_AREA_W + 6 + _dash_bw + 6, _dash_by2, _dash_bw, 120,  1.0)

    dpad = ft.Stack(
        width=W,
        height=CTRL_H,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        controls=[
            ft.Container(width=W, height=CTRL_H, bgcolor="#0d0d1a"),
            # Divider between joystick zone and dash zone
            ft.Container(
                left=JOY_AREA_W, top=0,
                width=1, height=CTRL_H,
                bgcolor="#222244",
            ),
            # Virtual joystick (engine component — owns all visuals + GD)
            joystick.control,
            # Dash buttons
            dash_l,
            dash_r,
            # Dash zone label
            ft.Container(
                left=JOY_AREA_W, top=CTRL_H - 28, width=W - JOY_AREA_W, height=24,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("◄◄ dash ►►", size=11, color="#2a2a44"),
            ),
            # Keyboard hint (bottom of joystick zone)
            ft.Container(
                left=0, top=CTRL_H - 28, width=JOY_AREA_W, height=24,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("WASD / arrows", size=11, color="#2a2a44"),
            ),
        ],
    )

    # ── Player state ──────────────────────────────────────────────────────────────────
    px    = START_PX
    py    = START_PY
    angle = START_ANGLE

    # ── FPS counter ───────────────────────────────────────────────────────────────────
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

    # ── Collision helper ────────────────────────────────────────────────────────────
    def _walkable(nx: float, ny: float) -> bool:
        m = WALL_MARGIN
        for ddx, ddy in ((m, m), (m, -m), (-m, m), (-m, -m)):
            cx, cy = int(nx + ddx), int(ny + ddy)
            if not (0 <= cx < MAP_COLS and 0 <= cy < MAP_ROWS):
                return False
            if MAP[cy][cx] != 0:
                return False
        return True

    # ── Game loop ─────────────────────────────────────────────────────────────────────
    loop = Loop(page, fps=60)

    @loop.on_update
    def update(dt: float) -> None:
        nonlocal px, py, angle, _dash_timer

        # ── Rotation: keyboard OR left-joystick horizontal axis ──────────────────
        rot = 0.0
        if inp.is_key_down("arrowleft") or inp.is_key_down("a"):  rot -= ROT_SPEED
        if inp.is_key_down("arrowright") or inp.is_key_down("d"): rot += ROT_SPEED
        rot += joystick.vx * ROT_SPEED    # joystick horizontal → turn speed
        angle = (angle + rot * dt) % (2 * math.pi)

        # ── Forward / backward: keyboard OR left-joystick vertical axis ─────────
        fdx = math.cos(angle) * MOVE_SPEED * dt
        fdy = math.sin(angle) * MOVE_SPEED * dt

        if inp.is_key_down("arrowup") or inp.is_key_down("w"):
            if _walkable(px + fdx, py): px += fdx
            if _walkable(px, py + fdy): py += fdy
        if inp.is_key_down("arrowdown") or inp.is_key_down("s"):
            if _walkable(px - fdx, py): px -= fdx
            if _walkable(px, py - fdy): py -= fdy

        if joystick.vy:    # dead zone handled inside VirtualJoystick
            spd = -joystick.vy * MOVE_SPEED * dt   # negative = forward on screen
            ddx = math.cos(angle) * spd
            ddy = math.sin(angle) * spd
            if _walkable(px + ddx, py): px += ddx
            if _walkable(px, py + ddy): py += ddy

        # ── Dash: lateral strafe burst ─────────────────────────────────────
        if _dash_timer > 0:
            _dash_timer = max(0.0, _dash_timer - dt)
            # Perpendicular to facing direction
            sdx = math.cos(angle + math.pi / 2) * DASH_SPEED * dt * _dash_dir
            sdy = math.sin(angle + math.pi / 2) * DASH_SPEED * dt * _dash_dir
            if _walkable(px + sdx, py): px += sdx
            if _walkable(px, py + sdy): py += sdy

        # ── Render & HUD ─────────────────────────────────────────────────
        rc.render(px, py, angle)
        player_dot.x = MINI_X + px * MINI_CELL - 3
        player_dot.y = MINI_Y + py * MINI_CELL - 3
        deg = math.degrees(angle) % 360
        lbl_pos.text = f"{px:.1f}, {py:.1f}  ∠{deg:.0f}°"
        _update_fps(dt)

    # ── Mount & start ──────────────────────────────────────────────────────────────────
    scene.mount()
    page.spacing = 0        # no gap between scene and D-pad
    page.controls.append(dpad)
    page.update()
    loop.start()


if __name__ == "__main__":
    ft.run(main)
