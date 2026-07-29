"""
drawing.py — DrawingCanvas: a free-hand drawing surface for flet_game.

DrawingCanvas is intentionally separate from the action-game subsystem
(Sprite / GameLoop / Scene) because drawing games work differently:

* **Event-driven, not loop-driven** — strokes are recorded from pointer drag
  events, not from 60 fps tick callbacks.
* **Persistent state** — the canvas accumulates content; frames are never cleared.
* **Collaboration-ready** — each finished stroke is a plain serialisable dict
  so it can be sent over a network (e.g. via ``page.pubsub``) and replayed on
  another client.

Quick start::

    from flet_game import DrawingCanvas

    dc = DrawingCanvas(page, width=800, height=600, bgcolor="#ffffff")
    page.add(dc.control)

    dc.brush_color = "#e63946"
    dc.brush_size  = 5.0

    dc.clear()
    dc.undo()

    @dc.on_stroke_end
    def sync(stroke: dict) -> None:
        page.pubsub.send_all({"type": "stroke", "stroke": stroke,
                               "from": dc.session_id})

Receiving remote strokes::

    def on_message(message: dict) -> None:
        if message.get("type") == "stroke" and message["from"] != dc.session_id:
            dc.apply_stroke(message["stroke"])

    page.pubsub.subscribe(on_message)

Performance note
----------------
``flet.canvas.Canvas`` renders every shape in ``canvas.shapes`` on each
``canvas.update()`` call.  To keep updates fast as the shape list grows, the
class periodically calls ``await canvas.capture()`` (which bakes all current
shapes into a background bitmap) then clears ``canvas.shapes``.  This is the
same technique shown in Flet's own free-hand drawing example.
"""

from __future__ import annotations

import uuid
from typing import Callable

import flet as ft
import flet.canvas as cv

# Flatten shapes into a capture after this many cv.Line segments.
# Mirrors the constant in Flet's own free-hand drawing example.
_CAPTURE_EVERY: int = 30


class DrawingCanvas:
    """A free-hand drawing surface backed by ``flet.canvas.Canvas``.

    Parameters
    ----------
    page:
        The Flet page.
    width, height:
        Dimensions of the drawing surface in logical pixels.
    bgcolor:
        Background fill colour (CSS hex or Flet color name).  Also used as the
        eraser colour when ``eraser=True``.
    brush_color:
        Initial brush colour.
    brush_size:
        Initial stroke width in logical pixels.
    drag_interval:
        Milliseconds between pan-update events fired by the GestureDetector.
        Lower = smoother strokes, more events.  10 ms matches Flet's example.
    """

    def __init__(
        self,
        page: ft.Page,
        width: float = 800,
        height: float = 600,
        bgcolor: str = "#ffffff",
        brush_color: str = "#000000",
        brush_size: float = 3.0,
        drag_interval: int = 10,
    ) -> None:
        self._page = page
        self._width = width
        self._height = height
        self._bgcolor = bgcolor
        self._brush_color = brush_color
        self._brush_size = float(brush_size)
        self._eraser = False

        # Finished strokes — list of dicts with keys:
        #   "color": str, "size": float, "points": list[tuple[float, float]]
        # Kept in full so undo and apply_stroke (remote replay) work correctly.
        self._strokes: list[dict] = []

        # Points accumulated during the current drag gesture.
        self._current_points: list[tuple[float, float]] = []

        # Number of cv.Line shapes added to canvas.shapes since the last capture.
        self._seg_count: int = 0

        # Callbacks fired when the user lifts the pen (stroke complete).
        self._stroke_end_cbs: list[Callable[[dict], None]] = []

        # Unique ID for this drawing session — used to filter own strokes when
        # receiving pubsub messages (so we don't re-apply our own broadcasts).
        self.session_id: str = str(uuid.uuid4())

        # ── Build the flet.canvas.Canvas ──────────────────────────────────────
        self._canvas = cv.Canvas(
            width=width,
            height=height,
            shapes=[cv.Fill(ft.Paint(color=bgcolor))],
            content=ft.GestureDetector(
                on_pan_start=self._on_pan_start,
                on_pan_update=self._on_pan_update,
                on_pan_end=self._on_pan_end,
                drag_interval=drag_interval,
            ),
        )

        # Outer container enforces hard clipping so strokes don't bleed outside.
        self._control = ft.Container(
            content=self._canvas,
            width=width,
            height=height,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    # ── Public control ─────────────────────────────────────────────────────────

    @property
    def control(self) -> ft.Container:
        """The Flet widget to add to the page or a layout container."""
        return self._control

    # ── Brush properties ───────────────────────────────────────────────────────

    @property
    def brush_color(self) -> str:
        """Current brush colour (CSS hex or Flet color name)."""
        return self._brush_color

    @brush_color.setter
    def brush_color(self, value: str) -> None:
        self._brush_color = value

    @property
    def brush_size(self) -> float:
        """Stroke width in logical pixels."""
        return self._brush_size

    @brush_size.setter
    def brush_size(self, value: float) -> None:
        self._brush_size = max(0.5, float(value))

    @property
    def eraser(self) -> bool:
        """When ``True``, drawing paints with bgcolor (erases existing content)."""
        return self._eraser

    @eraser.setter
    def eraser(self, value: bool) -> None:
        self._eraser = bool(value)

    @property
    def bgcolor(self) -> str:
        """Background / eraser colour."""
        return self._bgcolor

    # ── Canvas operations ──────────────────────────────────────────────────────

    def clear(self) -> None:
        """Erase the entire canvas and reset stroke history.

        The Fill background colour is restored.  Any ``capture()`` bitmap is
        cleared asynchronously via ``page.run_task``.
        """
        self._strokes.clear()
        self._current_points.clear()
        self._seg_count = 0
        self._canvas.shapes.clear()
        self._canvas.shapes.append(cv.Fill(ft.Paint(color=self._bgcolor)))
        self._canvas.update()
        # Clear the captured background bitmap asynchronously.
        self._page.run_task(self._canvas.clear_capture)

    def undo(self) -> None:
        """Remove the last finished stroke and redraw from history.

        Only removes strokes drawn on *this* client.  Remote strokes received
        via ``apply_stroke()`` are also stored in history and can be undone.
        """
        if not self._strokes:
            return
        self._strokes.pop()
        self._page.run_task(self._undo_async)

    async def _undo_async(self) -> None:
        await self._canvas.clear_capture()
        self._seg_count = 0
        self._canvas.shapes.clear()
        self._canvas.shapes.append(cv.Fill(ft.Paint(color=self._bgcolor)))
        self._rebuild_shapes()
        self._canvas.update()

    def _rebuild_shapes(self) -> None:
        """Re-add all strokes from ``_strokes`` to ``canvas.shapes`` (no update)."""
        for stroke in self._strokes:
            pts = stroke["points"]
            paint = _make_paint(stroke["color"], stroke["size"])
            for i in range(1, len(pts)):
                x1, y1 = pts[i - 1]
                x2, y2 = pts[i]
                self._canvas.shapes.append(
                    cv.Line(x1=x1, y1=y1, x2=x2, y2=y2, paint=paint)
                )
                self._seg_count += 1

    def apply_stroke(self, stroke: dict) -> None:
        """Draw a stroke received from another player (network / pubsub sync).

        Parameters
        ----------
        stroke:
            A dict with keys:

            * ``"color"`` — CSS hex string or Flet color name.
            * ``"size"``  — stroke width (float).
            * ``"points"``— list of ``[x, y]`` or ``(x, y)`` coordinates.
        """
        pts_raw = stroke.get("points", [])
        if not pts_raw:
            return
        pts: list[tuple[float, float]] = [
            (float(p[0]), float(p[1])) for p in pts_raw
        ]
        normalized: dict = {
            "color": stroke["color"],
            "size": float(stroke["size"]),
            "points": pts,
        }
        self._strokes.append(normalized)

        paint = _make_paint(normalized["color"], normalized["size"])
        for i in range(1, len(pts)):
            x1, y1 = pts[i - 1]
            x2, y2 = pts[i]
            self._canvas.shapes.append(
                cv.Line(x1=x1, y1=y1, x2=x2, y2=y2, paint=paint)
            )
            self._seg_count += 1
        self._canvas.update()

        if self._seg_count >= _CAPTURE_EVERY:
            self._page.run_task(self._do_capture)

    # ── on_stroke_end hook ─────────────────────────────────────────────────────

    def on_stroke_end(self, fn: Callable[[dict], None]) -> Callable:
        """Decorator — called with the finished stroke dict when the pen is lifted.

        The stroke dict has keys ``"color"`` (str), ``"size"`` (float), and
        ``"points"`` (list of (x, y) tuples).

        Typical use — broadcast to other players::

            @dc.on_stroke_end
            def sync(stroke: dict) -> None:
                msg = {
                    "type": "stroke",
                    "stroke": {
                        "color": stroke["color"],
                        "size":  stroke["size"],
                        # Serialise as lists for pubsub/JSON compatibility:
                        "points": [list(p) for p in stroke["points"]],
                    },
                    "from": dc.session_id,
                }
                page.pubsub.send_all(msg)
        """
        self._stroke_end_cbs.append(fn)
        return fn

    # ── Internal pan handlers ──────────────────────────────────────────────────

    def _on_pan_start(self, e: ft.DragStartEvent) -> None:
        x, y = e.local_position.x, e.local_position.y
        # Store start point twice — ensures a single tap produces a visible dot
        # (a zero-length line with round caps renders as a circle).
        self._current_points = [(x, y), (x, y)]

    async def _on_pan_update(self, e: ft.DragUpdateEvent) -> None:
        if not self._current_points:
            return
        x1, y1 = self._current_points[-1]
        x2, y2 = e.local_position.x, e.local_position.y
        self._current_points.append((x2, y2))

        color = self._bgcolor if self._eraser else self._brush_color
        self._canvas.shapes.append(
            cv.Line(x1=x1, y1=y1, x2=x2, y2=y2, paint=_make_paint(color, self._brush_size))
        )
        self._seg_count += 1
        self._canvas.update()

        if self._seg_count >= _CAPTURE_EVERY:
            await self._do_capture()

    def _on_pan_end(self, e: ft.DragEndEvent) -> None:
        if not self._current_points:
            return
        color = self._bgcolor if self._eraser else self._brush_color
        stroke: dict = {
            "color": color,
            "size": self._brush_size,
            "points": list(self._current_points),
        }
        self._strokes.append(stroke)
        self._current_points.clear()

        for cb in self._stroke_end_cbs:
            try:
                cb(stroke)
            except Exception:
                pass

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _do_capture(self) -> None:
        """Bake canvas.shapes into a background bitmap, then clear the shape list."""
        await self._canvas.capture()
        self._canvas.shapes.clear()
        self._canvas.update()
        self._seg_count = 0


# ── Module-level paint factory (avoids repeated object creation) ───────────────

def _make_paint(color: str, size: float) -> ft.Paint:
    return ft.Paint(
        color=color,
        stroke_width=size,
        style=ft.PaintingStyle.STROKE,
        stroke_cap=ft.StrokeCap.ROUND,
        stroke_join=ft.StrokeJoin.ROUND,
    )
