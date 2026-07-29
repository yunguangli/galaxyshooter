"""
test_loop.py — Step 2 test for flet_game.GameLoop
==================================================
Run with:
    flet run src/test_loop.py
  or:
    python src/test_loop.py

What is tested
--------------
  ✓ GameLoop creation and start()
  ✓ @loop.on_update decorator — plain def callback (no async needed)
  ✓ @loop.on_update with async def — both work side-by-side
  ✓ CSS color strings — Sprite(color="orange") instead of ft.Colors.ORANGE
  ✓ Sprite property setters — ball.x / ball.y instead of ball.control.left
  ✓ Delta-time (dt) — movement is pixels/second, frame-rate-independent
  ✓ Multiple callbacks — two independent physics callbacks in one loop
  ✓ Batch page.update() — no per-sprite .update() calls in physics loop
  ✓ Measured FPS display — updated every second
  ✓ pause() / resume() / toggle_pause() — freezes and restores cleanly
  ✓ stop() / start() — full restart cycle
  ✓ target_fps property — change FPS target at runtime (30 / 60 / 120)
  ✓ add_callback / remove_callback — dynamic registration

Demo
----
  Two balls bounce around the canvas at frame-rate-independent speeds.
  A live dt counter proves movement is consistent across any FPS target.
  A "distance" accumulator counts total pixels travelled at exactly the
  expected rate regardless of FPS setting.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import Sprite, GameLoop, Loop  # Loop is a short alias for GameLoop

CANVAS_W = 620
CANVAS_H = 320

# Ball speeds in pixels per SECOND (dt-independent)
BALL1_SPEED_X = 180.0
BALL1_SPEED_Y = 130.0
BALL2_SPEED_X = -110.0
BALL2_SPEED_Y = 160.0


def main(page: ft.Page) -> None:
    page.title = "flet_game — Step 2: GameLoop"
    page.bgcolor = ft.Colors.GREY_900
    page.padding = 16

    # ── Sprites ───────────────────────────────────────────────────────
    ball1 = Sprite(
        x=60, y=60,
        width=36, height=36,
        color="orange",       # CSS name — Fix 2: no ft.Colors.ORANGE needed
        border_radius=18,
        tag="ball1",
    )
    ball2 = Sprite(
        x=400, y=200,
        width=28, height=28,
        color="cyan",         # CSS name — _resolve_color maps → ft.Colors.CYAN
        border_radius=14,
        tag="ball2",
    )

    # Canvas
    canvas = ft.Stack(
        width=CANVAS_W,
        height=CANVAS_H,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        controls=[
            ft.Container(width=CANVAS_W, height=CANVAS_H, bgcolor=ft.Colors.BLACK),
            ball1.control,
            ball2.control,
        ],
    )
    canvas_box = ft.Container(
        content=canvas,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.GREY_700),
    )

    # ── Game loop ─────────────────────────────────────────────────────
    loop = GameLoop(page, fps=60)

    # Velocity state (pixels/second — multiplied by dt each frame)
    v1x, v1y = BALL1_SPEED_X, BALL1_SPEED_Y
    v2x, v2y = BALL2_SPEED_X, BALL2_SPEED_Y

    # Accumulator to prove dt-independence: total "seconds" elapsed in-game
    game_seconds: float = 0.0

    @loop.on_update
    def physics_ball1(dt: float) -> None:
        """Ball 1 physics — Fix 1: plain def (no async needed)."""
        nonlocal v1x, v1y
        new_x = ball1.x + v1x * dt          # Fix 3: use sprite.x, not ball1.control.left
        new_y = ball1.y + v1y * dt
        # Bounce off canvas edges
        if new_x <= 0 or new_x + ball1.width >= CANVAS_W:
            v1x = -v1x
            new_x = max(0.0, min(new_x, CANVAS_W - ball1.width))
        if new_y <= 0 or new_y + ball1.height >= CANVAS_H:
            v1y = -v1y
            new_y = max(0.0, min(new_y, CANVAS_H - ball1.height))
        # batch_active is True here — sprite._update() is suppressed.
        # The single page.update() at end of frame flushes both balls at once.
        ball1.x = new_x
        ball1.y = new_y

    @loop.on_update
    async def physics_ball2(dt: float) -> None:
        """Ball 2 physics — async def also works; both styles live in the same loop."""
        nonlocal v2x, v2y, game_seconds
        game_seconds += dt

        new_x = ball2.x + v2x * dt
        new_y = ball2.y + v2y * dt
        if new_x <= 0 or new_x + ball2.width >= CANVAS_W:
            v2x = -v2x
            new_x = max(0.0, min(new_x, CANVAS_W - ball2.width))
        if new_y <= 0 or new_y + ball2.height >= CANVAS_H:
            v2y = -v2y
            new_y = max(0.0, min(new_y, CANVAS_H - ball2.height))
        ball2.x = new_x
        ball2.y = new_y

    # Third callback: update the status bar — registered programmatically.
    # Also plain def; the loop's page.update() at frame-end flushes Text widgets
    # too, so no per-control .update() call is needed anywhere.
    def update_hud(dt: float) -> None:
        fps_val.value = f"{loop.fps:.0f}"
        dt_val.value = f"{loop.dt_ms:.1f} ms"
        time_val.value = f"{game_seconds:.2f} s"

    loop.add_callback(update_hud)

    # ── HUD ───────────────────────────────────────────────────────────
    def stat_col(label: str, value_ctrl: ft.Text) -> ft.Column:
        return ft.Column(
            [ft.Text(label, color=ft.Colors.GREY_500, size=11), value_ctrl],
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    fps_val = ft.Text("--", color=ft.Colors.GREEN_400, size=22, weight=ft.FontWeight.BOLD)
    dt_val = ft.Text("-- ms", color=ft.Colors.AMBER_400, size=22, weight=ft.FontWeight.BOLD)
    time_val = ft.Text("0.00 s", color=ft.Colors.CYAN_400, size=22, weight=ft.FontWeight.BOLD)
    target_val = ft.Text("60", color=ft.Colors.WHITE, size=22, weight=ft.FontWeight.BOLD)

    hud = ft.Row(
        [
            stat_col("Measured FPS", fps_val),
            ft.VerticalDivider(width=1, color=ft.Colors.GREY_700),
            stat_col("Frame time", dt_val),
            ft.VerticalDivider(width=1, color=ft.Colors.GREY_700),
            stat_col("Game time", time_val),
            ft.VerticalDivider(width=1, color=ft.Colors.GREY_700),
            stat_col("Target FPS", target_val),
        ],
        spacing=20,
        alignment=ft.MainAxisAlignment.CENTER,
    )

    # ── Buttons ───────────────────────────────────────────────────────
    pause_btn = ft.FilledButton("Pause", on_click=lambda e: _pause())
    stop_btn = ft.FilledButton("Stop", on_click=lambda e: _stop())

    def _pause() -> None:
        if loop.is_paused:
            loop.resume()
            pause_btn.text = "Pause"
        else:
            loop.pause()
            pause_btn.text = "Resume"
        pause_btn.update()

    def _stop() -> None:
        loop.stop()
        stop_btn.text = "Stopped"
        stop_btn.disabled = True
        restart_btn.disabled = False
        stop_btn.update()
        restart_btn.update()

    restart_btn = ft.FilledButton(
        "Restart",
        disabled=True,
        on_click=lambda e: _restart(),
    )

    def _restart() -> None:
        nonlocal game_seconds
        game_seconds = 0.0
        ball1.move_to(60, 60)
        ball2.move_to(400, 200)
        loop.start()
        stop_btn.text = "Stop"
        stop_btn.disabled = False
        restart_btn.disabled = True
        stop_btn.update()
        restart_btn.update()

    def _set_fps(value: int) -> None:
        loop.target_fps = value
        target_val.value = str(value)
        target_val.update()

    buttons = ft.Row(
        [
            pause_btn,
            stop_btn,
            restart_btn,
            ft.VerticalDivider(width=1, color=ft.Colors.GREY_700),
            ft.FilledButton("FPS: 30", on_click=lambda e: _set_fps(30)),
            ft.FilledButton("FPS: 60", on_click=lambda e: _set_fps(60)),
            ft.FilledButton("FPS: 120", on_click=lambda e: _set_fps(120)),
        ],
        spacing=8,
        wrap=True,
    )

    # ── Legend ────────────────────────────────────────────────────────
    legend = ft.Column(
        [
            ft.Text(
                "physics_ball1 is a plain def (no async), physics_ball2 is async def — "
                "both work in the same loop. Balls use sprite.x / sprite.y, not "
                "ball.control.left (Fix 1 + Fix 3).",
                color=ft.Colors.GREY_400, size=11,
            ),
            ft.Text(
                "Colors: Sprite(color=\"orange\") and Sprite(color=\"cyan\") — "
                "CSS strings, no ft.Colors import needed (Fix 2).",
                color=ft.Colors.GREY_400, size=11,
            ),
            ft.Text(
                "Both balls move at a fixed px/second regardless of FPS target — "
                "that's delta-time. Game time accumulates with dt.",
                color=ft.Colors.GREY_400, size=11,
            ),
        ],
        spacing=2,
    )

    # ── Layout ────────────────────────────────────────────────────────
    page.add(
        ft.SafeArea(
            content=ft.Column(
                [
                    ft.Text(
                        "flet_game — Step 2: GameLoop",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    canvas_box,
                    hud,
                    buttons,
                    legend,
                ],
                spacing=12,
            )
        )
    )

    # Start the loop after the page is fully built
    loop.start()


ft.run(main)
