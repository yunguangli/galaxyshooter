"""
test_sprite.py — Step 1 test for flet_game.Sprite
==================================================
Run with:
    flet run src/test_sprite.py
  or:
    python src/test_sprite.py

What is tested
--------------
  ✓ Sprite creation  — color, image URL, border_radius, opacity, tag
  ✓ Sprite creation  — color, image URL, border_radius, opacity, tag
  ✓ move_to(x, y)    — instant repositioning (no animation)
  ✓ move_to(duration=) — animated movement; animate_to() is a backward-compat alias
  ✓ fade_to()        — animated opacity via Flet animate_opacity
  ✓ rotate_to()      — animated rotation via Flet animate_rotation
  ✓ scale_to()       — animated scale via Flet animate_scale
  ✓ hide() / show()  — toggle visibility; destroy() is a backward-compat alias for hide()
  ✓ Property setters — .x, .y, .color, .opacity, .visible, .rotation, .scale
  ✓ bounds           — (left, top, right, bottom) tuple
  ✓ collides_with()  — AABB overlap detection
  ✓ contains_point() — point-in-bounds check
  ✓ on_click         — callback assigned after creation
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import Sprite

CANVAS_W = 620
CANVAS_H = 340


def main(page: ft.Page) -> None:
    page.title = "flet_game — Step 1: Sprite"
    page.bgcolor = ft.Colors.GREY_900
    page.padding = 16

    # ── Status bar ────────────────────────────────────────────────────
    status = ft.Text(
        "← Click a sprite, or use the buttons below.",
        color=ft.Colors.AMBER,
        size=13,
        italic=True,
    )

    def log(msg: str) -> None:
        status.value = msg
        status.update()

    # ── Create sprites ────────────────────────────────────────────────

    # Red box — demonstrates animate_to with BOUNCE_OUT
    red = Sprite(
        x=30, y=120,
        width=70, height=70,
        color="red",          # CSS name — _resolve_color maps → ft.Colors.RED
        tag="red",
    )

    # Blue rounded box — demonstrates scale_to
    blue = Sprite(
        x=200, y=90,
        width=80, height=80,
        color="blue_400",      # shade notation — maps → ft.Colors.BLUE_400
        border_radius=14,
        tag="blue",
    )

    # Green semi-transparent box — demonstrates fade_to
    green = Sprite(
        x=370, y=200,
        width=65, height=65,
        color="green",         # CSS name — maps → ft.Colors.GREEN
        opacity=0.4,
        tag="green",
    )

    # Image sprite — demonstrates rotate_to
    img = Sprite(
        x=490, y=25,
        width=100, height=100,
        image="https://picsum.photos/100/100",
        border_radius=8,
        tag="image",
    )

    # Small orange dot — used to demo collides_with and contains_point
    dot = Sprite(
        x=160, y=110,
        width=20, height=20,
        color="orange",        # CSS name — maps → ft.Colors.ORANGE
        border_radius=10,
        tag="dot",
    )

    # ── Click handlers ────────────────────────────────────────────────

    def on_red_click(e: ft.ControlEvent) -> None:
        target_x = 400 if red.x < 200 else 30
        red.move_to(target_x, 120, duration=700,
                    curve=ft.AnimationCurve.BOUNCE_OUT)
        log(f"[red] move_to({target_x}, 120, duration=700)  bounds={red.bounds}")

    def on_blue_click(e: ft.ControlEvent) -> None:
        new_scale = 0.5 if blue.scale > 0.75 else 1.0
        blue.scale_to(new_scale, duration=400)
        log(f"[blue] scale_to({new_scale})  collides_with(red)={blue.collides_with(red)}")

    def on_green_click(e: ft.ControlEvent) -> None:
        new_op = 1.0 if green.opacity < 0.6 else 0.1
        green.fade_to(new_op, duration=500)
        log(f"[green] fade_to({new_op:.1f})")

    def on_img_click(e: ft.ControlEvent) -> None:
        new_rot = img.rotation + 45
        img.rotate_to(new_rot, duration=400, curve=ft.AnimationCurve.EASE_OUT)
        log(f"[image] rotate_to({new_rot}°)  current rotation={img.rotation}°")

    def on_dot_click(e: ft.ControlEvent) -> None:
        # Move dot on top of red to demonstrate collision
        dot.move_to(red.x + 5, red.y + 5, duration=500)
        log(f"[dot] move_to(duration=500) → check collision with the button below")

    red.on_click = on_red_click
    blue.on_click = on_blue_click
    green.on_click = on_green_click
    img.on_click = on_img_click
    dot.on_click = on_dot_click

    # ── Canvas (ft.Stack) ─────────────────────────────────────────────
    canvas = ft.Stack(
        width=CANVAS_W,
        height=CANVAS_H,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        controls=[
            # Background
            ft.Container(width=CANVAS_W, height=CANVAS_H, bgcolor=ft.Colors.BLACK),
            # Sprites — add .control to mount each one
            red.control,
            blue.control,
            green.control,
            img.control,
            dot.control,
        ],
    )

    canvas_box = ft.Container(
        content=canvas,
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.GREY_700),
    )

    # ── Buttons ───────────────────────────────────────────────────────

    def btn_reset(e: ft.ControlEvent) -> None:
        red.move_to(30, 120)
        blue.move_to(200, 90)
        green.move_to(370, 200)
        img.move_to(490, 25)
        dot.move_to(160, 110)
        blue.scale = 1.0
        green.opacity = 0.4
        img.rotation = 0
        log("All sprites reset to initial positions (move_to — instant).")

    def btn_collision(e: ft.ControlEvent) -> None:
        r_d = dot.collides_with(red)
        b_d = dot.collides_with(blue)
        pt = dot.contains_point(red.x + 10, red.y + 10)
        log(
            f"dot.collides_with(red)={r_d}  "
            f"dot.collides_with(blue)={b_d}  "
            f"dot.contains_point(red+10,red+10)={pt}"
        )

    def btn_toggle_green(e: ft.ControlEvent) -> None:
        green.visible = not green.visible
        log(f"[green] visible={green.visible}  (property setter — instant)")

    def btn_change_color(e: ft.ControlEvent) -> None:
        import random
        palette = [
            "red", "orange", "purple",
            "cyan", "pink", "yellow",
            "#E91E63", "#00BCD4",     # hex strings also work
        ]
        red.color = random.choice(palette)
        log(f"[red] color set to {red.color!r} via .color setter")

    def btn_bounds(e: ft.ControlEvent) -> None:
        log(
            f"bounds → red={red.bounds}  blue={blue.bounds}  "
            f"green={green.bounds}  img={img.bounds}  dot={dot.bounds}"
        )

    def btn_destroy(e: ft.ControlEvent) -> None:
        dot.hide()
        log("[dot] hide() called → sprite hidden (use show() to reveal again)")

    buttons = ft.Row(
        controls=[
            ft.FilledButton("Reset all", on_click=btn_reset),
            ft.FilledButton("Check collision", on_click=btn_collision),
            ft.FilledButton("Toggle green", on_click=btn_toggle_green),
            ft.FilledButton("Random color", on_click=btn_change_color),
            ft.FilledButton("Print bounds", on_click=btn_bounds),
            ft.FilledButton("Hide dot", on_click=btn_destroy),
        ],
        wrap=True,
        spacing=8,
        run_spacing=8,
    )

    # ── Legend ────────────────────────────────────────────────────────
    def legend_row(color: str, text: str) -> ft.Row:
        return ft.Row([
            ft.Container(width=12, height=12, bgcolor=color,
                         border_radius=ft.BorderRadius.all(2)),
            ft.Text(text, color=ft.Colors.GREY_400, size=11),
        ], spacing=6)

    legend = ft.Column([
        ft.Text("Click each sprite to interact:", color=ft.Colors.GREY_500, size=11),
        legend_row(ft.Colors.RED,        "RED   → move_to(duration=700, BOUNCE_OUT), toggles left ↔ right"),
        legend_row(ft.Colors.BLUE_400,   "BLUE  → scale_to 50% / 100%"),
        legend_row(ft.Colors.GREEN,      "GREEN → fade_to 10% / 100%"),
        legend_row(ft.Colors.ORANGE,     "DOT   → move_to(duration=500) onto red (then check collision)"),
        ft.Row([
            ft.Container(width=12, height=12,
                         border_radius=ft.BorderRadius.all(2),
                         image=ft.DecorationImage(
                             src="https://picsum.photos/12/12",
                             fit=ft.BoxFit.COVER,
                         )),
            ft.Text("IMAGE → rotate_to +45° per click", color=ft.Colors.GREY_400, size=11),
        ], spacing=6),
    ], spacing=3)

    # ── Layout ────────────────────────────────────────────────────────
    page.add(
        ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.Text(
                        "flet_game — Step 1: Sprite",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    canvas_box,
                    status,
                    buttons,
                    legend,
                ],
                spacing=12,
            )
        )
    )


ft.run(main)
