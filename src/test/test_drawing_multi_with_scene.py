"""
test_drawing_multi_with_scene.py — Step 8 (Scene variant): Collaborative drawing.

Same multiplayer pubsub logic as test_drawing_multi.py, but wired through
Game + Scene so keyboard shortcuts and the scene lifecycle are handled by
the engine.

Comparison
----------
  test_drawing_multi.py             — standalone, raw page.add()
  test_drawing_multi_with_scene.py  — uses Game + Scene (this file)

Key differences from the non-Scene version
-------------------------------------------
  - ``CollabScene(Scene)`` subclass; on_exit() unsubscribes pubsub cleanly
  - Keyboard: Ctrl+Z → local undo, Delete → clear-all broadcast, Esc → quit
  - Toolbar lives outside the scene canvas (appended to page separately)

How to test locally
-------------------
    cd src
    flet run --web test_drawing_multi_with_scene.py

Open http://localhost:8550 in two browser tabs.
Strokes drawn in one tab appear on the other in real time.

Run:  cd src && flet run --web test_drawing_multi_with_scene.py
"""

import os
import sys

import flet as ft

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import Game, Scene, Label, DrawingCanvas

# ── Layout constants ──────────────────────────────────────────────────────────

CANVAS_W  = 960
CANVAS_H  = 540
TOOLBAR_H = 48

PLAYER_PALETTE: list[str] = [
    "#e63946", "#3498db", "#2ecc71", "#f4a261",
    "#9b59b6", "#f1c40f", "#1abc9c", "#e67e22",
]
BRUSH_PALETTE: list[str] = [
    "#000000", "#e63946", "#f4a261", "#f1c40f",
    "#2ecc71", "#3498db", "#9b59b6", "#ffffff",
]

TOOLBAR_BG = "#16213e"
PAGE_BG    = "#0f3460"


# ═══════════════════════════════════════════════════════════════════════════════
# CollabScene
# ═══════════════════════════════════════════════════════════════════════════════

class CollabScene(Scene):
    """Multiplayer drawing scene backed by page.pubsub."""

    def __init__(self, game: Game, toolbar_ref: list) -> None:
        super().__init__(game.page, CANVAS_W, CANVAS_H, bgcolor="#ffffff")
        self._game = game
        self._toolbar_ref = toolbar_ref
        self._dc: DrawingCanvas | None = None

    def on_enter(self) -> None:
        dc = DrawingCanvas(
            self._page,
            width=self._width,
            height=self._height,
            bgcolor="#ffffff",
            brush_size=4.0,
        )
        self._dc = dc
        dc.brush_color = PLAYER_PALETTE[hash(dc.session_id) % len(PLAYER_PALETTE)]
        self.add(dc.control)

        # ── pubsub ────────────────────────────────────────────────────────────

        @dc.on_stroke_end
        def _broadcast(stroke: dict) -> None:
            self._page.pubsub.send_all({
                "type":   "stroke",
                "from":   dc.session_id,
                "stroke": {
                    "color":  stroke["color"],
                    "size":   stroke["size"],
                    "points": [list(p) for p in stroke["points"]],
                },
            })

        def _on_message(message: dict) -> None:
            if message.get("from") == dc.session_id:
                return
            if message.get("type") == "stroke":
                dc.apply_stroke(message["stroke"])
            elif message.get("type") == "clear":
                dc.clear()

        self._page.pubsub.subscribe(_on_message)

        # ── Keyboard shortcuts ────────────────────────────────────────────────

        @self.input.on_key_down("ctrl+z")
        def kb_undo(e=None) -> None:
            dc.undo()

        @self.input.on_key_down("delete")
        def kb_clear_all(e=None) -> None:
            dc.clear()
            self._page.pubsub.send_all({"type": "clear", "from": dc.session_id})

        @self.input.on_key_down("escape")
        async def kb_quit(e=None) -> None:
            await self._game.page.window.close()

        # ── Active-colour indicator ───────────────────────────────────────────

        active_dot = ft.Container(
            width=18, height=18,
            bgcolor=dc.brush_color,
            border_radius=9,
            border=ft.Border.all(2, "#ffffff"),
        )
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

        # ── Swatches ──────────────────────────────────────────────────────────

        swatches = [
            ft.Container(
                width=26, height=26,
                bgcolor=c,
                border_radius=4,
                border=ft.Border.all(2, "#444466"),
                tooltip=c,
                on_click=lambda e, c=c: _set_color(c),
            )
            for c in BRUSH_PALETTE
        ]

        # ── Size slider ───────────────────────────────────────────────────────

        size_slider = ft.Slider(
            min=1, max=40, value=dc.brush_size,
            width=140,
            active_color="#aaaacc",
            label="{value}",
            on_change=lambda e: setattr(dc, "brush_size", e.control.value),
        )

        # ── Eraser ────────────────────────────────────────────────────────────

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

        # ── Undo / Clear All ──────────────────────────────────────────────────

        undo_btn = ft.TextButton(
            "↩ Undo",
            style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
            on_click=lambda _e: dc.undo(),
            tooltip="Local only  (Ctrl+Z)",
        )

        def _clear_all(_e=None) -> None:
            dc.clear()
            self._page.pubsub.send_all({"type": "clear", "from": dc.session_id})

        clear_btn = ft.TextButton(
            "🗑 Clear All",
            style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
            on_click=_clear_all,
            tooltip="Resets all players  (Del)",
        )

        # ── Session badge ─────────────────────────────────────────────────────

        session_badge = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(width=12, height=12, bgcolor=dc.brush_color, border_radius=6),
                    ft.Text(f"You  \u2026{dc.session_id[-6:]}", color="#8899bb", size=12),
                ],
                spacing=5,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            tooltip="Your session ID",
        )

        # ── HUD hint (inside scene canvas) ────────────────────────────────────

        hint_lbl = Label(
            text="Ctrl+Z: undo   Del: clear all   \u2022   open a 2nd tab to collaborate",
            x=CANVAS_W / 2,
            y=CANVAS_H - 16,
            color="#aaaacc",
            size=11,
        )
        self.add(hint_lbl, z=10)

        # ── Toolbar (written back for page layout) ────────────────────────────

        self._toolbar_ref[0] = ft.Container(
            bgcolor=TOOLBAR_BG,
            padding=ft.Padding.symmetric(horizontal=14, vertical=6),
            width=CANVAS_W,
            content=ft.Row(
                controls=[
                    active_dot,
                    ft.Container(width=6),
                    *swatches,
                    ft.VerticalDivider(width=14, color="transparent"),
                    ft.Text("Size:", color="#aaaacc", size=13),
                    size_slider,
                    ft.VerticalDivider(width=1, color="#334466"),
                    eraser_btn,
                    ft.VerticalDivider(width=1, color="#334466"),
                    undo_btn,
                    clear_btn,
                    ft.VerticalDivider(width=1, color="#334466"),
                    session_badge,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
        )

    def on_exit(self) -> None:
        """Unsubscribe from pubsub when the scene is torn down."""
        self._page.pubsub.unsubscribe()


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main(page: ft.Page) -> None:
    page.title   = "flet_game — Collaborative Drawing + Scene (Step 8)"
    page.bgcolor = PAGE_BG
    page.padding = 0

    toolbar_ref: list = [None]

    game  = Game(page, width=CANVAS_W, height=CANVAS_H)
    scene = CollabScene(game, toolbar_ref)

    # Placeholder keeps the column layout stable before mount.
    toolbar_placeholder = ft.Container(
        bgcolor=TOOLBAR_BG, width=CANVAS_W, height=TOOLBAR_H,
    )
    page.add(
        ft.Column(
            controls=[toolbar_placeholder],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )

    game.run(scene)

    if toolbar_ref[0] is not None:
        page.controls[0].controls[0] = toolbar_ref[0]
        page.update()


ft.run(main)
