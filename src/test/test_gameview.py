"""
test_gameview.py — Step 14: GameView responsive auto-scaler
============================================================
Run with:
    python src/test/test_gameview.py
  or:
    flet run src/test/test_gameview.py

What is tested
--------------
  ✓ GameView wraps a fixed 390×780 design scene
  ✓ mode="fit"      — canvas scales uniformly; black bars fill leftover space
  ✓ mode="fill"     — canvas fills the window, cropping the overflow axis
  ✓ mode="stretch"  — canvas stretches to fill (non-uniform)
  ✓ page.on_resized — rescales on every window resize
  ✓ Touch/keyboard events still fire in design coordinates (not scaled coords)
  ✓ Scene add/remove works normally through the view

Demo
----
A 390×780 portrait design canvas appears centred in whatever window size you
give it.  Three mode buttons at the bottom switch between fit / fill / stretch.
Click the canvas to verify touch coordinates are in the 0-390 / 0-780 space.
Press ESC or Q to quit.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import Scene, Sprite, Label, Loop, Input, GameView

# ── Design constants ──────────────────────────────────────────────────────────
DW, DH = 390, 780          # fixed design resolution (portrait phone)
BALL_SPEED = 220.0          # px/s

# ── Colours ───────────────────────────────────────────────────────────────────
BG      = "#0d1b2a"
BALL_C  = "#f4a261"
GRID_C  = "#1a2f45"


def main(page: ft.Page) -> None:
    page.title = "flet_game — Step 14: GameView"
    page.bgcolor = ft.Colors.BLACK
    page.padding = 0

    # ── Build the fixed-design scene ─────────────────────────────────────────
    scene = Scene(page, width=DW, height=DH, bgcolor=BG)
    inp   = scene.input
    loop  = Loop(page, fps=60)

    # Grid lines to make scaling obvious
    for gx in range(0, DW, 78):
        line = Sprite(x=gx, y=0, width=1, height=DH, color=GRID_C)
        scene.add(line, z=0)
    for gy in range(0, DH, 78):
        line = Sprite(x=0, y=gy, width=DW, height=1, color=GRID_C)
        scene.add(line, z=0)

    # Corner markers — confirm edges are at design coords
    for cx, cy in [(0, 0), (DW-20, 0), (0, DH-20), (DW-20, DH-20)]:
        scene.add(Sprite(x=cx, y=cy, width=20, height=20, color="#e63946"))

    # Centre cross
    scene.add(Sprite(x=DW//2-1, y=0, width=2, height=DH, color="#ffffff33"))
    scene.add(Sprite(x=0, y=DH//2-1, width=DW, height=2, color="#ffffff33"))

    # Bouncing ball
    ball = Sprite(x=DW//2-20, y=DH//2-20, width=40, height=40,
                  color=BALL_C, border_radius=20)
    scene.add(ball, z=5)

    # HUD labels
    lbl_mode = Label(text="mode: fit", x=10, y=10,
                     color="white", size=14, bold=True)
    lbl_click = Label(text="tap/click the canvas", x=10, y=34,
                      color="#aaaaaa", size=12)
    lbl_scale = Label(text="scale: 1.00", x=10, y=DH-30,
                      color="#aaaaaa", size=12)
    scene.add(lbl_mode,  z=10)
    scene.add(lbl_click, z=10)
    scene.add(lbl_scale, z=10)

    # ── Physics ───────────────────────────────────────────────────────────────
    vx, vy = BALL_SPEED, BALL_SPEED * 0.7

    @loop.on_update
    def update(dt: float) -> None:
        nonlocal vx, vy
        ball.x += vx * dt
        ball.y += vy * dt
        if ball.x < 0:
            ball.x = 0; vx = abs(vx)
        elif ball.x > DW - ball.width:
            ball.x = DW - ball.width; vx = -abs(vx)
        if ball.y < 0:
            ball.y = 0; vy = abs(vy)
        elif ball.y > DH - ball.height:
            ball.y = DH - ball.height; vy = -abs(vy)

    # ── Touch — verify design-space coords ───────────────────────────────────
    @inp.on_click
    def on_tap(x: float, y: float) -> None:
        lbl_click.text = f"tap: ({x:.0f}, {y:.0f})  ← design coords"
        lbl_click.update()

    # ── Keyboard ─────────────────────────────────────────────────────────────
    @inp.on_key_down("escape")
    @inp.on_key_down("q")
    async def quit(e=None): await page.window.close()

    # ── GameView ─────────────────────────────────────────────────────────────
    view = GameView(scene, mode="fit")

    # ── Mode switcher (outside the scene — plain Flet buttons) ───────────────
    current_mode = {"v": "fit"}

    def set_mode(m: str) -> None:
        current_mode["v"] = m
        view._mode = m
        lbl_mode.text = f"mode: {m}"
        lbl_mode.update()
        view.layout()
        lbl_scale.text = f"scale: {view.scale_x:.2f}"
        lbl_scale.update()

    btn_fit     = ft.TextButton("fit",     on_click=lambda _: set_mode("fit"))
    btn_fill    = ft.TextButton("fill",    on_click=lambda _: set_mode("fill"))
    btn_stretch = ft.TextButton("stretch", on_click=lambda _: set_mode("stretch"))

    page.add(ft.Row([btn_fit, btn_fill, btn_stretch],
                    alignment=ft.MainAxisAlignment.CENTER))

    # ── Mount ─────────────────────────────────────────────────────────────────
    view.mount()

    # Refresh scale label after first layout
    def _on_resize(e):
        lbl_scale.text = f"scale: {view.scale_x:.2f}"
        lbl_scale.update()

    _prev = page.on_resized
    def _combined(e):
        if callable(_prev): _prev(e)
        _on_resize(e)
    page.on_resized = _combined

    loop.start()


ft.run(main)
