"""
test_drawing.py — Step 8 test: DrawingCanvas (single-player).

Demonstrates DrawingCanvas standalone usage:

  - Free-hand drawing with a colour palette and brush-size slider
  - Eraser toggle
  - Undo (remove last stroke)
  - Clear (erase everything)

DrawingCanvas is intentionally NOT integrated with Game / Scene / GameLoop —
it is an event-driven surface that accumulates content, which is a fundamentally
different model from the action-game subsystem.

Run:  cd src && flet run test_drawing.py
"""

import os
import sys

import flet as ft

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import DrawingCanvas

# ── Layout constants ──────────────────────────────────────────────────────────

CANVAS_W = 960
CANVAS_H = 580

PALETTE: list[str] = [
    "#000000",  # black
    "#e63946",  # red
    "#f4a261",  # orange
    "#f1c40f",  # yellow
    "#2ecc71",  # green
    "#3498db",  # blue
    "#9b59b6",  # purple
    "#ffffff",  # white (also useful against dark backgrounds)
]

TOOLBAR_BG = "#16213e"
PAGE_BG    = "#0f3460"


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main(page: ft.Page) -> None:
    page.title   = "flet_game — DrawingCanvas (Step 8)"
    page.bgcolor = PAGE_BG
    page.padding = 0

    dc = DrawingCanvas(
        page,
        width=CANVAS_W,
        height=CANVAS_H,
        bgcolor="#ffffff",
        brush_color=PALETTE[0],
        brush_size=4.0,
    )

    # ── Active-colour indicator ───────────────────────────────────────────────

    active_dot = ft.Container(
        width=18, height=18,
        bgcolor=dc.brush_color,
        border_radius=9,
        border=ft.Border.all(2, "#ffffff"),
    )

    def _set_color(color: str) -> None:
        dc.eraser = False
        dc.brush_color = color
        active_dot.bgcolor = color
        eraser_btn.style = ft.ButtonStyle(color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE))
        page.update()

    # ── Colour swatches ───────────────────────────────────────────────────────

    swatches = [
        ft.Container(
            width=28, height=28,
            bgcolor=c,
            border_radius=5,
            border=ft.Border.all(2, "#444466"),
            tooltip=c,
            on_click=lambda e, c=c: _set_color(c),
        )
        for c in PALETTE
    ]

    # ── Brush-size slider ─────────────────────────────────────────────────────

    size_slider = ft.Slider(
        min=1, max=40, value=dc.brush_size,
        width=160,
        active_color="#aaaacc",
        label="{value}",
        on_change=lambda e: setattr(dc, "brush_size", e.control.value),
    )

    # ── Eraser button ─────────────────────────────────────────────────────────

    eraser_btn = ft.TextButton(
        "⬜ Eraser",
        style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE)),
    )

    def _toggle_eraser(_e=None) -> None:
        dc.eraser = not dc.eraser
        eraser_btn.style = ft.ButtonStyle(
            color=ft.Colors.WHITE if dc.eraser
            else ft.Colors.with_opacity(0.5, ft.Colors.WHITE)
        )
        page.update()

    eraser_btn.on_click = _toggle_eraser

    # ── Undo / Clear ──────────────────────────────────────────────────────────

    undo_btn  = ft.TextButton(
        "↩ Undo",
        style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
        on_click=lambda _e: dc.undo(),
    )
    clear_btn = ft.TextButton(
        "🗑 Clear",
        style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
        on_click=lambda _e: dc.clear(),
    )

    # ── Toolbar row ───────────────────────────────────────────────────────────

    toolbar = ft.Container(
        bgcolor=TOOLBAR_BG,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        width=CANVAS_W,
        content=ft.Row(
            controls=[
                active_dot,
                ft.Container(width=6),
                *swatches,
                ft.VerticalDivider(width=16, color="transparent"),
                ft.Text("Size:", color="#aaaacc", size=13),
                size_slider,
                ft.VerticalDivider(width=1, color="#334466"),
                eraser_btn,
                ft.VerticalDivider(width=1, color="#334466"),
                undo_btn,
                clear_btn,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
    )

    hint = ft.Container(
        bgcolor=TOOLBAR_BG,
        padding=ft.Padding.symmetric(horizontal=14, vertical=4),
        width=CANVAS_W,
        content=ft.Text(
            "Click and drag to draw  •  Undo removes the last stroke  •"
            "  Clear resets the canvas",
            color="#556688",
            size=12,
        ),
    )

    page.add(
        ft.Column(
            controls=[toolbar, dc.control, hint],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )


ft.run(main)
