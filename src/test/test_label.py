"""
test_label.py — Step 2.5 test for flet_game.Label
===================================================
Run with:
    flet run src/test_label.py

What is tested
--------------
  ✓ Label creation — text, size, color (CSS string), bold, italic
  ✓ label.text     — updated live inside the game loop (score counter, FPS)
  ✓ label.x / y   — repositioning; label.move_to() instant; move_to(duration=) animated
  ✓ label.color    — CSS string color change via property setter
  ✓ label.fade_to()— animated opacity on a hint label
  ✓ label.visible  — show/hide toggle
  ✓ GameLoop + Label — batch mode: no explicit .update() calls in tick callbacks
  ✓ AlertDialog    — page.show_dialog() / page.pop_dialog() for Game Over popup

Demo
----
  A bouncing ball (Sprite) rolls around the canvas.
  Each wall bounce increments a score counter Label.
  An FPS Label updates every frame — proves batch mode flushes Text widgets too.
  At 5 bounces the ball stops and an AlertDialog offers Restart or Quit.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import Sprite, GameLoop, Label

CANVAS_W = 620
CANVAS_H = 320
TARGET_BOUNCES = 5


def main(page: ft.Page) -> None:
    page.title = "flet_game — Step 2.5: Label"
    page.bgcolor = ft.Colors.GREY_900
    page.padding = 16

    # ── Sprites ───────────────────────────────────────────────────────
    ball = Sprite(
        x=60, y=60,
        width=32, height=32,
        color="orange",
        border_radius=16,
        tag="ball",
    )

    # ── Labels on the canvas ──────────────────────────────────────────

    # Score — bold, top-left
    score_label = Label(
        x=10, y=8,
        text="Bounces: 0",
        size=18,
        color="white",
        bold=True,
        tag="score",
    )

    # FPS — smaller, top-right (proves batch mode flushes plain Text too)
    fps_label = Label(
        x=CANVAS_W - 90, y=8,
        text="FPS: --",
        size=13,
        color="green",
        tag="fps",
    )

    # Italic hint at the bottom — fades out after first bounce
    hint_label = Label(
        x=10, y=CANVAS_H - 26,
        text="Watch the ball bounce and the score update!",
        size=12,
        color="grey",
        italic=True,
        tag="hint",
    )

    # Canvas
    canvas = ft.Stack(
        width=CANVAS_W,
        height=CANVAS_H,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        controls=[
            ft.Container(width=CANVAS_W, height=CANVAS_H, bgcolor=ft.Colors.BLACK),
            ball.control,
            score_label.control,
            fps_label.control,
            hint_label.control,
        ],
    )
    canvas_box = ft.Container(
        content=canvas,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.GREY_700),
    )

    # ── Game state ────────────────────────────────────────────────────
    vx, vy = 200.0, 145.0
    bounces = 0
    game_over = False
    hint_faded = False

    # ── AlertDialog (Game Over) ───────────────────────────────────────
    # Pattern from Flet docs: page.show_dialog() / page.pop_dialog()
    def _restart(e: ft.ControlEvent) -> None:
        nonlocal bounces, game_over, hint_faded, vx, vy
        page.pop_dialog()
        bounces = 0
        game_over = False
        hint_faded = False
        vx, vy = 200.0, 145.0
        ball.move_to(60, 60)
        score_label.text = "Bounces: 0"
        score_label.color = "white"
        hint_label.opacity = 1.0
        hint_label.visible = True
        loop.resume()

    async def _quit(e: ft.ControlEvent) -> None:
        loop.stop()            # stop the game loop first to prevent further page.update() calls
        page.pop_dialog()
        await page.window.close()

    game_over_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Game Over!"),
        content=ft.Text(f"You racked up {TARGET_BOUNCES} bounces. Play again?"),
        actions=[
            ft.FilledButton("Restart", on_click=_restart),
            ft.TextButton("Quit", on_click=_quit),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        on_dismiss=lambda e: loop.resume() if game_over else None,
    )

    # ── Game loop ─────────────────────────────────────────────────────
    loop = GameLoop(page, fps=60)

    @loop.on_update
    def physics(dt: float) -> None:
        nonlocal vx, vy, bounces, game_over, hint_faded

        if game_over:
            return

        new_x = ball.x + vx * dt
        new_y = ball.y + vy * dt
        bounced = False

        if new_x <= 0 or new_x + ball.width >= CANVAS_W:
            vx = -vx
            new_x = max(0.0, min(new_x, CANVAS_W - ball.width))
            bounced = True
        if new_y <= 0 or new_y + ball.height >= CANVAS_H:
            vy = -vy
            new_y = max(0.0, min(new_y, CANVAS_H - ball.height))
            bounced = True

        ball.x = new_x
        ball.y = new_y

        if bounced:
            bounces += 1
            score_label.text = f"Bounces: {bounces}"

            # Fade hint out on first bounce
            if not hint_faded:
                hint_label.fade_to(0.0, duration=800)
                hint_faded = True

            # Colour the score warmer as bounces accumulate
            if bounces >= TARGET_BOUNCES:
                game_over = True
                score_label.color = "red"
                loop.pause()
                page.show_dialog(game_over_dialog)
            elif bounces >= 3:
                score_label.color = "orange"

    @loop.on_update
    def hud(dt: float) -> None:
        # Plain def — batch mode: no .update() call — page.update() handles it
        fps_label.text = f"FPS: {loop.fps:.0f}"

    # ── Controls outside the canvas ───────────────────────────────────
    def btn_slide(e: ft.ControlEvent) -> None:
        """Slide score label across the top — tests move_to(duration=)."""
        target_x = CANVAS_W - 150 if score_label.x < 200 else 10
        score_label.move_to(target_x, 8, duration=500,
                            curve=ft.AnimationCurve.EASE_IN_OUT)

    def btn_toggle_fps(e: ft.ControlEvent) -> None:
        fps_label.visible = not fps_label.visible

    def btn_color(e: ft.ControlEvent) -> None:
        import random
        palette = ["white", "yellow", "cyan", "lime", "#FF9800", "#E91E63"]
        score_label.color = random.choice(palette)

    def btn_size(e: ft.ControlEvent) -> None:
        score_label.size = 24 if score_label.size <= 18 else 14

    buttons = ft.Row(
        [
            ft.FilledButton("Slide score label", on_click=btn_slide),
            ft.FilledButton("Toggle FPS", on_click=btn_toggle_fps),
            ft.FilledButton("Random color", on_click=btn_color),
            ft.FilledButton("Toggle size", on_click=btn_size),
        ],
        spacing=8,
        wrap=True,
    )

    legend = ft.Column(
        [
            ft.Text(
                "Score and FPS labels live inside the canvas (ft.Stack), positioned "
                "with Label.x / Label.y — same pattern as Sprite.",
                color=ft.Colors.GREY_400, size=11,
            ),
            ft.Text(
                "No .update() calls anywhere in the game loop — "
                "GameLoop's page.update() flushes Sprite AND Label changes at once.",
                color=ft.Colors.GREY_400, size=11,
            ),
        ],
        spacing=2,
    )

    page.add(
        ft.SafeArea(
            content=ft.Column(
                [
                    ft.Text(
                        "flet_game — Step 2.5: Label",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    canvas_box,
                    buttons,
                    legend,
                ],
                spacing=12,
            )
        )
    )

    loop.start()


ft.run(main)
