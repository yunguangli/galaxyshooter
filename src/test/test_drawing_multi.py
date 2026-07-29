"""
test_drawing_multi.py — Step 8: Collaborative drawing via page.pubsub.

Two or more players share a canvas in real time.  Each finished stroke is
broadcast to every other connected session via Flet's built-in pubsub channel.

How to test locally
-------------------
    cd src
    flet run --web test_drawing_multi.py

Then open http://localhost:8550 in **two browser tabs**.  Each tab is a
separate Flet session (= a separate player).  Strokes drawn in one tab appear
on the other in real time.

Architecture
------------
- ``page.pubsub`` is Flet's built-in broadcast channel.  It works across all
  sessions connected to the same server process — no external WebSocket server
  required for local co-op.
- ``dc.session_id`` is a UUID generated per DrawingCanvas instance.  It is
  included in every pubsub message so the receiver can skip its own echoes.
- Stroke points are plain Python lists (JSON-safe), so they pass cleanly
  through pubsub without custom serialisation.
- "Clear All" broadcasts a clear event so all players' canvases reset together.

For a true cross-machine multiplayer game (players on different computers),
you would replace page.pubsub with a WebSocket client connecting to a shared
server — that is out of scope for Step 8.
"""

import os
import sys

import flet as ft

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import DrawingCanvas

# ── Layout constants ──────────────────────────────────────────────────────────

CANVAS_W = 960
CANVAS_H = 540

# Distinct default colours per player (assigned deterministically from session_id).
PLAYER_PALETTE: list[str] = [
    "#e63946",  # red
    "#3498db",  # blue
    "#2ecc71",  # green
    "#f4a261",  # orange
    "#9b59b6",  # purple
    "#f1c40f",  # yellow
    "#1abc9c",  # teal
    "#e67e22",  # dark orange
]

# Swatches the user can switch to manually.
BRUSH_PALETTE: list[str] = [
    "#000000", "#e63946", "#f4a261", "#f1c40f",
    "#2ecc71", "#3498db", "#9b59b6", "#ffffff",
]

TOOLBAR_BG = "#16213e"
PAGE_BG    = "#0f3460"


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main(page: ft.Page) -> None:
    page.title   = "flet_game — Collaborative Drawing (Step 8)"
    page.bgcolor = PAGE_BG
    page.padding = 0

    dc = DrawingCanvas(
        page,
        width=CANVAS_W,
        height=CANVAS_H,
        bgcolor="#ffffff",
        brush_size=4.0,
    )

    # Give each player a distinct default colour derived from their session ID.
    dc.brush_color = PLAYER_PALETTE[hash(dc.session_id) % len(PLAYER_PALETTE)]

    # ── Multiplayer sync via page.pubsub ──────────────────────────────────────

    @dc.on_stroke_end
    def _broadcast(stroke: dict) -> None:
        """Send our finished stroke to all other sessions."""
        page.pubsub.send_all({
            "type": "stroke",
            "from": dc.session_id,
            "stroke": {
                "color":  stroke["color"],
                "size":   stroke["size"],
                # Serialise tuples as lists for pubsub compatibility.
                "points": [list(p) for p in stroke["points"]],
            },
        })

    def _on_message(message: dict) -> None:
        """Handle a message received from another session."""
        if message.get("from") == dc.session_id:
            return  # ignore our own echo

        if message.get("type") == "stroke":
            dc.apply_stroke(message["stroke"])
        elif message.get("type") == "clear":
            # Remote player cleared — reset our canvas too (no re-broadcast).
            dc.clear()

    page.pubsub.subscribe(_on_message)

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
            width=26, height=26,
            bgcolor=c,
            border_radius=4,
            border=ft.Border.all(2, "#444466"),
            tooltip=c,
            on_click=lambda e, c=c: _set_color(c),
        )
        for c in BRUSH_PALETTE
    ]

    # ── Brush-size slider ─────────────────────────────────────────────────────

    size_slider = ft.Slider(
        min=1, max=40, value=dc.brush_size,
        width=140,
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

    # ── Undo (local only) ─────────────────────────────────────────────────────

    undo_btn = ft.TextButton(
        "↩ Undo",
        style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
        on_click=lambda _e: dc.undo(),
        tooltip="Removes your last stroke locally",
    )

    # ── Clear All (broadcast) ─────────────────────────────────────────────────

    def _clear_all(_e=None) -> None:
        dc.clear()
        page.pubsub.send_all({"type": "clear", "from": dc.session_id})

    clear_btn = ft.TextButton(
        "🗑 Clear All",
        style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.7, ft.Colors.WHITE)),
        on_click=_clear_all,
        tooltip="Clears the canvas for all players",
    )

    # ── Session badge ─────────────────────────────────────────────────────────

    session_badge = ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(width=12, height=12, bgcolor=dc.brush_color, border_radius=6),
                ft.Text(
                    f"You  …{dc.session_id[-6:]}",
                    color="#8899bb",
                    size=12,
                ),
            ],
            spacing=5,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        tooltip="Your session ID",
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

    hint = ft.Container(
        bgcolor=TOOLBAR_BG,
        padding=ft.Padding.symmetric(horizontal=14, vertical=4),
        width=CANVAS_W,
        content=ft.Text(
            "Open a second browser tab to collaborate  •"
            "  Each player gets a distinct default colour  •"
            "  Clear All resets every player's canvas",
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
