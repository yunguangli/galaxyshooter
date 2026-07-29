"""
test_drawing_with_scene.py — Step 8 (Scene variant): DrawingCanvas inside a Scene.

Demonstrates how DrawingCanvas integrates with the Game / Scene architecture:

  - DrawingCanvas added to Scene.canvas via scene.add(dc.control)
  - Keyboard shortcuts wired through scene.input (no gesture conflict)
  - HUD Labels rendered on top via scene.add(lbl, z=10)
  - Toolbar built as a separate ft.Row outside the Scene canvas

Comparison with test_drawing.py (raw page.add() approach)
----------------------------------------------------------
  test_drawing.py             — standalone, no engine integration
  test_drawing_with_scene.py  — uses Game + Scene (this file)

Key differences
---------------
  - ``DrawingScene(Scene)`` subclass owns the canvas; on_exit() tears down pubsub
  - Keyboard: Ctrl+Z → undo, Delete → clear, Escape → quit (via scene.input)
  - Toolbar is appended to page separately (above the Scene canvas)
  - Toolbar callbacks use closures that reference the Scene's DrawingCanvas

Run:  cd src && flet run test_drawing_with_scene.py
"""

import os
import sys

import flet as ft

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import Game, Scene, Label, DrawingCanvas

# ── Layout constants ──────────────────────────────────────────────────────────

CANVAS_W   = 960
CANVAS_H   = 540   # scene canvas (drawing area)
TOOLBAR_H  = 48    # toolbar strip above

PALETTE: list[str] = [
    "#000000", "#e63946", "#f4a261", "#f1c40f",
    "#2ecc71", "#3498db", "#9b59b6", "#ffffff",
]

TOOLBAR_BG = "#16213e"
PAGE_BG    = "#0f3460"


# ═══════════════════════════════════════════════════════════════════════════════
# DrawingScene
# ═══════════════════════════════════════════════════════════════════════════════

class DrawingScene(Scene):
    """A Scene whose canvas is a DrawingCanvas, with a keyboard-driven toolbar."""

    def __init__(self, game: Game, toolbar_ref: list) -> None:
        # bgcolor="#ffffff" so the scene background IS the drawing surface bg.
        super().__init__(game.page, CANVAS_W, CANVAS_H, bgcolor="#ffffff")
        self._game = game
        # toolbar_ref is a 1-element list so on_enter() can write back
        # the toolbar ft.Row to the caller after the dc is created.
        self._toolbar_ref = toolbar_ref

    def on_enter(self) -> None:
        # DrawingCanvas fills the full scene canvas.
        dc = DrawingCanvas(
            self._page,
            width=self._width,
            height=self._height,
            bgcolor="#ffffff",
            brush_color=PALETTE[0],
            brush_size=4.0,
        )
        self._dc = dc
        # scene.add() accepts raw ft.Control — no special handling needed.
        self.add(dc.control)

        # ── Keyboard shortcuts (scene.input — no GestureDetector conflict) ────
        @self.input.on_key_down("ctrl+z")
        def kb_undo(e=None) -> None:
            dc.undo()

        @self.input.on_key_down("delete")
        def kb_clear(e=None) -> None:
            dc.clear()
            _sync_eraser_btn(False)

        @self.input.on_key_down("escape")
        async def kb_quit(e=None) -> None:
            await self._game.page.window.close()

        # ── Active-colour indicator (lives inside the HUD) ────────────────────
        active_dot = ft.Container(
            width=18, height=18,
            bgcolor=dc.brush_color,
            border_radius=9,
            border=ft.Border.all(2, "#ffffff"),
        )

        # eraser_btn is created below; hold a mutable cell so _set_color can
        # reference it before the button is constructed.
        eraser_cell: list = [None]

        def _set_color(color: str) -> None:
            dc.eraser = False
            dc.brush_color = color
            active_dot.bgcolor = color
            if eraser_cell[0]:
                eraser_cell[0].style = ft.ButtonStyle(
                    color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE)
                )
            self._page.update()

        def _sync_eraser_btn(active: bool) -> None:
            if eraser_cell[0]:
                eraser_cell[0].style = ft.ButtonStyle(
                    color=ft.Colors.WHITE if active
                    else ft.Colors.with_opacity(0.5, ft.Colors.WHITE)
                )

        # ── Colour swatches ───────────────────────────────────────────────────
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

        # ── Brush-size slider ─────────────────────────────────────────────────
        size_slider = ft.Slider(
            min=1, max=40, value=dc.brush_size,
            width=160,
            active_color="#aaaacc",
            label="{value}",
            on_change=lambda e: setattr(dc, "brush_size", e.control.value),
        )

        # ── Eraser button ─────────────────────────────────────────────────────
        eraser_btn = ft.TextButton(
            "⬜ Eraser",
            style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE)),
        )
        eraser_cell[0] = eraser_btn

        def _toggle_eraser(_e=None) -> None:
            dc.eraser = not dc.eraser
            _sync_eraser_btn(dc.eraser)
            self._page.update()

        eraser_btn.on_click = _toggle_eraser

        # ── Undo / Clear buttons ──────────────────────────────────────────────
        undo_btn = ft.TextButton(
            "↩ Undo",
            style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
            on_click=lambda _e: dc.undo(),
            tooltip="Ctrl+Z",
        )
        clear_btn = ft.TextButton(
            "🗑 Clear",
            style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
            on_click=lambda _e: dc.clear(),
            tooltip="Delete",
        )

        # ── Keyboard hint Label (HUD, z=10, inside the scene canvas) ─────────
        hint_lbl = Label(
            text="Ctrl+Z: undo   Del: clear   Esc: quit",
            x=CANVAS_W / 2,
            y=CANVAS_H - 16,
            color="#aaaacc",
            size=11,
        )
        self.add(hint_lbl, z=10)

        # ── Toolbar (written back to the caller via toolbar_ref) ──────────────
        toolbar = ft.Container(
            bgcolor=TOOLBAR_BG,
            padding=ft.Padding.symmetric(horizontal=14, vertical=6),
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
        self._toolbar_ref[0] = toolbar

    def on_exit(self) -> None:
        """No pubsub to unsubscribe in single-player; nothing to tear down."""


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main(page: ft.Page) -> None:
    page.title   = "flet_game — DrawingCanvas + Scene (Step 8)"
    page.bgcolor = PAGE_BG
    page.padding = 0

    # toolbar_ref[0] is filled by DrawingScene.on_enter() before mount returns.
    toolbar_ref: list = [None]

    game = Game(page, width=CANVAS_W, height=CANVAS_H)
    scene = DrawingScene(game, toolbar_ref)

    # Add toolbar placeholder so page layout is established before mount.
    toolbar_placeholder = ft.Container(
        bgcolor=TOOLBAR_BG,
        width=CANVAS_W, height=TOOLBAR_H,
    )
    page.add(
        ft.Column(
            controls=[toolbar_placeholder],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )

    # game.run() mounts the scene (calls on_enter, which fills toolbar_ref[0]).
    game.run(scene)

    # Replace placeholder with the real toolbar built by on_enter().
    if toolbar_ref[0] is not None:
        page.controls[0].controls[0] = toolbar_ref[0]
        page.update()


ft.run(main)
