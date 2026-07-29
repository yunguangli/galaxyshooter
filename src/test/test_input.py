"""
test_input.py — Step 3 test for flet_game.InputManager
=======================================================
Run with:
    flet run src/test_input.py

What is tested
--------------
  ✓ is_key_down()      — WASD / arrow keys move the player sprite (polling)
  ✓ on_key_down()      — Space bar fires a bullet (one-shot callback)
  ✓ on_key_down()      — Escape key quits via AlertDialog
  ✓ on_click()         — canvas tap teleports the player
  ✓ on_drag()          — drag paints temporary trail dots on the canvas
  ✓ on_hover()         — crosshair Label tracks the mouse cursor
  ✓ InputManager.wrap()— GestureDetector wraps the ft.Stack canvas
  ✓ InputManager.destroy() — called on quit to unregister all handlers
  ✓ GameLoop + InputManager — batch mode; no explicit .update() calls needed

Demo
----
  Blue player square moves with WASD or arrow keys.
  Press SPACE to shoot a yellow bullet (moves right, despawns off-canvas).
  Click/tap anywhere to teleport the player to that spot.
  Click and drag to paint a trail of small orange dots.
  Mouse cursor shows a crosshair label with its canvas co-ordinates.
  FPS label updates each frame (top-right).
  Press ESC or click the "Quit" button to close.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import Sprite, GameLoop, Label, InputManager, Input  # Input is an alias for InputManager

CANVAS_W = 640
CANVAS_H = 360
PLAYER_SPEED = 220.0       # pixels per second
BULLET_SPEED = 380.0       # pixels per second
MAX_BULLETS = 10


def main(page: ft.Page) -> None:
    page.title = "flet_game — Step 3: InputManager"
    page.bgcolor = ft.Colors.GREY_900
    page.padding = 16

    # ── Player sprite ──────────────────────────────────────────────────────────
    player = Sprite(
        x=CANVAS_W // 2 - 16,
        y=CANVAS_H // 2 - 16,
        width=32, height=32,
        color="blue_400",
        border_radius=4,
        tag="player",
    )

    # ── Bullet pool ────────────────────────────────────────────────────────────
    bullets: list[Sprite] = []

    def _spawn_bullet() -> None:
        if len(bullets) >= MAX_BULLETS:
            return
        b = Sprite(
            x=player.x + 30,
            y=player.y + 12,
            width=10, height=6,
            color="yellow_400",
            border_radius=3,
            tag="bullet",
        )
        bullets.append(b)
        canvas.controls.append(b.control)

    # ── Trail dots ─────────────────────────────────────────────────────────────
    trail_dots: list[Sprite] = []

    def _add_trail_dot(x: float, y: float) -> None:
        dot = Sprite(x=x - 4, y=y - 4, width=8, height=8,
                     color="deep-orange", border_radius=4, opacity=0.6, tag="trail")
        trail_dots.append(dot)
        canvas.controls.append(dot.control)
        # Auto-remove oldest dot if too many
        if len(trail_dots) > 60:
            old = trail_dots.pop(0)
            canvas.controls.remove(old.control)

    # ── HUD labels ─────────────────────────────────────────────────────────────
    fps_label = Label(x=CANVAS_W - 90, y=8,  text="FPS: --",
                      size=13, color="green_300", tag="fps")
    info_label = Label(x=8, y=8, text="WASD/arrows: move  |  Space: shoot  |  Click: teleport  |  Drag: trail  |  Esc: quit",
                       size=12, color="grey_400", tag="info")
    coord_label = Label(x=8, y=CANVAS_H - 24, text="x=0  y=0",
                        size=12, color="grey_500", tag="coord")

    # ── Canvas (ft.Stack) ──────────────────────────────────────────────────────
    canvas = ft.Stack(
        controls=[
            player.control,
            fps_label.control,
            info_label.control,
            coord_label.control,
        ],
        width=CANVAS_W,
        height=CANVAS_H,
    )

    # ── InputManager ───────────────────────────────────────────────────────────
    inp = Input(page)   # short alias for InputManager

    # ── InputManager — mouse/touch callbacks ───────────────────────────────────
    @inp.on_click
    def handle_click(x: float, y: float) -> None:
        # Teleport player (centre the sprite on the click point)
        player.move_to(x - player.width / 2, y - player.height / 2)

    @inp.on_drag
    def handle_drag(x: float, y: float, dx: float, dy: float) -> None:
        # Move player to the drag position (centred on cursor)
        player.x = max(0, min(CANVAS_W - player.width,  x - player.width  / 2))
        player.y = max(0, min(CANVAS_H - player.height, y - player.height / 2))
        # Paint a trail dot at the drag position
        _add_trail_dot(x, y)

    @inp.on_hover
    def handle_hover(x: float, y: float) -> None:
        coord_label.text = f"cursor x={x:.0f}  y={y:.0f}"

    # ── InputManager — keyboard event callbacks ────────────────────────────────
    @inp.on_key_down("space")
    def fire_bullet(e: ft.KeyboardEvent) -> None:
        _spawn_bullet()

    # ── Quit dialog ────────────────────────────────────────────────────────────
    game_state = {"quitting": False}

    def _restart(e: ft.ControlEvent) -> None:
        page.pop_dialog()
        game_state["quitting"] = False
        player.move_to(CANVAS_W // 2 - 16, CANVAS_H // 2 - 16)
        loop.resume()

    async def _quit(e: ft.ControlEvent) -> None:
        inp.destroy()
        loop.stop()
        page.pop_dialog()
        await page.window.close()

    quit_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Quit?"),
        content=ft.Text("Do you want to quit the demo?"),
        actions=[
            ft.FilledButton("Keep Playing", on_click=_restart),
            ft.TextButton("Quit", on_click=_quit),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        on_dismiss=lambda e: loop.resume() if not game_state["quitting"] else None,
    )

    def _show_quit_dialog(e: ft.KeyboardEvent | None = None) -> None:
        if game_state["quitting"]:
            return
        game_state["quitting"] = True
        loop.pause()
        page.show_dialog(quit_dialog)

    @inp.on_key_down("escape")
    def handle_escape(e: ft.KeyboardEvent) -> None:
        _show_quit_dialog()

    quit_btn = ft.TextButton("Quit", on_click=_show_quit_dialog)

    # ── GameLoop ───────────────────────────────────────────────────────────────
    loop = GameLoop(page, fps=60)

    @loop.on_update
    def update(dt: float) -> None:
        # ── Player movement (polling) ──────────────────────────────────────────
        vx, vy = 0.0, 0.0
        if inp.is_key_down("arrowleft")  or inp.is_key_down("a"):
            vx = -PLAYER_SPEED
        if inp.is_key_down("arrowright") or inp.is_key_down("d"):
            vx = PLAYER_SPEED
        if inp.is_key_down("arrowup")    or inp.is_key_down("w"):
            vy = -PLAYER_SPEED
        if inp.is_key_down("arrowdown")  or inp.is_key_down("s"):
            vy = PLAYER_SPEED

        player.x = max(0, min(CANVAS_W - player.width,  player.x + vx * dt))
        player.y = max(0, min(CANVAS_H - player.height, player.y + vy * dt))

        # ── Bullet movement ────────────────────────────────────────────────────
        dead: list[Sprite] = []
        for b in bullets:
            b.x += BULLET_SPEED * dt
            if b.x > CANVAS_W:
                dead.append(b)
        for b in dead:
            bullets.remove(b)
            canvas.controls.remove(b.control)

        # ── HUD ───────────────────────────────────────────────────────────────
        fps_label.text   = f"FPS: {loop.fps:.0f}"
        coord_label.text = f"player x={player.x:.0f}  y={player.y:.0f}"

    # ── Layout and start ───────────────────────────────────────────────────────
    page.add(
        ft.Column(
            controls=[
                inp.wrap(canvas),   # GestureDetector wraps the Stack
                ft.Row(
                    controls=[quit_btn],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=8,
        )
    )

    loop.start()


ft.run(main)
