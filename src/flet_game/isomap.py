"""
isomap.py — IsoMap: isometric tile-map with proper diamond rendering.

Step 18 of the flet_game engine.

Draws a grid of diamond-shaped tiles using a single ``flet.canvas.Canvas``.
All ``cv.Path`` shapes are **pre-allocated once** at construction and mutated
in-place on every ``render()`` call — the same technique used by
``RaycastCanvas`` to stay fast at 60 fps.  Flet's delta-update protocol then
sends only the changed vertex coordinates and colours to Flutter rather than
re-serialising the entire shape list.

Key features
------------
- True diamond tiles via ``flet.canvas.Path`` (4-vertex polygon)
- Painter's algorithm depth sort  (ascending tx+ty, tiebreak by ty)
- Wall extrusion  — left and right faces auto-shaded from the top colour
- View-frustum culling  — culled tiles get transparent paint (no new objects)
- Pre-allocated shape pool — zero Python object creation per render()
- Camera pan via ``pan(dx, dy)`` or ``center_on(tx, ty)``
- Tap-to-tile click detection with mathematical inverse projection
- Module-level ``iso_to_screen`` / ``screen_to_iso`` utilities

Quick start::

    from flet_game import IsoMap, Scene, GameLoop

    def main(page: ft.Page) -> None:
        scene = Scene(page, width=800, height=600)
        loop  = GameLoop(page, fps=60)
        inp   = scene.input

        iso = IsoMap(cols=20, rows=20, tile_w=64, tile_h=32,
                     viewport_w=800, viewport_h=600)
        iso.fill("#3a5a3a")
        iso.set_tile(5, 5, color="#887755", wall_h=28)
        iso.center_on(10, 10)
        scene.add(iso.control)

        PAN = 180.0
        @loop.on_update
        def update(dt):
            dx = dy = 0.0
            if inp.is_key_down("a"): dx =  PAN * dt
            if inp.is_key_down("d"): dx = -PAN * dt
            if inp.is_key_down("w"): dy =  PAN * dt
            if inp.is_key_down("s"): dy = -PAN * dt
            if dx or dy:
                iso.pan(dx, dy)
                iso.render()

        scene.mount()
        iso.render()   # first draw AFTER mount
        loop.start()

    ft.run(main)

mapgen integration::

    from flet_game import IsoMap, generate_random_map

    grid, walkable = generate_random_map(20, 20)
    iso = IsoMap(cols=20, rows=20, ...)
    for ty in range(20):
        for tx in range(20):
            if grid[ty][tx] == 0:
                iso.set_tile(tx, ty, color="#555566", wall_h=32)
    iso.render()
"""

from __future__ import annotations

import bisect
import functools
import math
from typing import Optional, Callable

import flet as ft
import flet.canvas as cv

_TRANSPARENT = "#00000000"


# ── Module-level coordinate utilities ────────────────────────────────────────


def iso_to_screen(
    tx: float,
    ty: float,
    tile_w: int,
    tile_h: int,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
) -> tuple[float, float]:
    """Convert isometric grid coords → canvas pixel position of the tile's top vertex.

    The returned point is the topmost pixel of the diamond, not its centre.
    """
    sx = origin_x + (tx - ty) * tile_w / 2
    sy = origin_y + (tx + ty) * tile_h / 2
    return sx, sy


def screen_to_iso(
    sx: float,
    sy: float,
    tile_w: int,
    tile_h: int,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
) -> tuple[float, float]:
    """Convert canvas pixel position → fractional isometric grid coords.

    Returns floating-point tile coords.  Use ``math.floor`` on each component
    and clamp to grid bounds to get the integer tile index.

    Math derivation
    ---------------
    Forward::

        sx = origin_x + (tx - ty) * tw / 2
        sy = origin_y + (tx + ty) * th / 2

    Let u = sx - origin_x, v = sy - origin_y.  Solving::

        tx = u/tw + v/th
        ty = v/th - u/tw
    """
    u = sx - origin_x
    v = sy - origin_y
    tx = u / tile_w + v / tile_h
    ty = v / tile_h - u / tile_w
    return tx, ty


# ── Shape pre-allocation helpers ──────────────────────────────────────────────


def _make_quad_path(style: ft.PaintingStyle, stroke_width: float = 1.0) -> cv.Path:
    """Pre-allocate a cv.Path with 5 mutable elements for a 4-vertex polygon."""
    return cv.Path(
        elements=[
            cv.Path.MoveTo(0.0, 0.0),
            cv.Path.LineTo(0.0, 0.0),
            cv.Path.LineTo(0.0, 0.0),
            cv.Path.LineTo(0.0, 0.0),
            cv.Path.Close(),
        ],
        paint=ft.Paint(style=style, color=_TRANSPARENT, stroke_width=stroke_width),
    )


def _update_quad(
    path: cv.Path,
    p0x: float, p0y: float,
    p1x: float, p1y: float,
    p2x: float, p2y: float,
    p3x: float, p3y: float,
    color: str,
) -> None:
    """Mutate a pre-allocated 4-vertex Path in place — no new objects created.

    Takes the 4 vertices as 8 scalar floats instead of 4 tuples, so the hot
    render loop avoids ~4 tuple allocations per visible tile per frame
    (~4000 allocations/frame for a 32×32 visible map).
    """
    e = path.elements
    e0, e1, e2, e3 = e[0], e[1], e[2], e[3]
    e0.x, e0.y = p0x, p0y
    e1.x, e1.y = p1x, p1y
    e2.x, e2.y = p2x, p2y
    e3.x, e3.y = p3x, p3y
    path.paint.color = color


# ── Tile data class ───────────────────────────────────────────────────────────


class IsoTile:
    """Per-cell tile data.

    All attributes may be mutated at runtime; call ``IsoMap.render()``
    afterwards to see the change.
    """

    __slots__ = ("color", "top_color", "wall_color", "wall_h", "passable", "tag", "data")

    def __init__(
        self,
        color: str = "#3a5a3a",
        top_color: Optional[str] = None,
        wall_color: Optional[str] = None,
        wall_h: int = 0,
        passable: bool = True,
        tag: str = "",
        data: object = None,
    ) -> None:
        self.color      = color
        self.top_color  = top_color or color   # top-face fill (defaults to color)
        self.wall_color = wall_color           # left wall face; auto-derived if None
        self.wall_h     = wall_h               # wall extrusion in pixels (0 = flat)
        self.passable   = passable
        self.tag        = tag
        self.data       = data                 # free user payload


# ── IsoMap ────────────────────────────────────────────────────────────────────


class IsoMap:
    """Isometric tile-map renderer using a single ``flet.canvas.Canvas``.

    All shapes are **pre-allocated** at construction (1-4 ``cv.Path`` objects
    per tile depending on options). ``render()`` mutates their vertices and
    paint colours in-place so
    Flet's delta-update protocol only transmits the changed values, not the
    entire shape list.  This matches the approach used by ``RaycastCanvas`` and
    gives smooth scrolling at 60 fps for maps up to ~40×40 tiles.

    Parameters
    ----------
    cols, rows:
        Grid dimensions (number of tiles on each axis).
    tile_w, tile_h:
        Diamond pixel dimensions.  ``tile_h = tile_w // 2`` gives the classic
        2:1 isometric look; ``tile_h = tile_w`` gives a steeper dimetric view.
    origin_x, origin_y:
        Initial pixel offset of the grid's top vertex (tile 0,0) within the
        canvas.  ``center_on(cols/2, rows/2)`` is a convenient alternative.
    viewport_w, viewport_h:
        Pixel size of the visible area (controls clip and the canvas extent).
    default_color:
        Fill colour applied to all tiles at construction.
    default_wall_h:
        Initial wall height for all tiles (usually 0 = flat).
    border:
        Whether to draw a thin semi-transparent stroke on each top face.
        Doubles the shape count — leave ``False`` (default) for best performance.
    render_walls:
        Whether to allocate and draw the left/right wall faces for tiles whose
        ``wall_h > 0``. Disable this for a lower-detail mobile mode that keeps
        the isometric top faces but avoids the extra wall-shape cost.
    """

    def __init__(
        self,
        cols: int = 20,
        rows: int = 20,
        tile_w: int = 64,
        tile_h: int = 32,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        viewport_w: float = 800.0,
        viewport_h: float = 600.0,
        default_color: str = "#3a5a3a",
        default_wall_h: int = 0,
        border: bool = False,
        render_walls: bool = True,
    ) -> None:
        self._cols   = cols
        self._rows   = rows
        self._tw     = tile_w
        self._th     = tile_h
        self._ox     = origin_x
        self._oy     = origin_y
        self._vw     = viewport_w
        self._vh     = viewport_h
        self._border = border
        self._render_walls = render_walls

        # ── Grid — row-major [ty][tx] ──────────────────────────────────────
        self._grid: list[list[IsoTile]] = [
            [
                IsoTile(color=default_color, wall_h=default_wall_h)
                for _ in range(cols)
            ]
            for _ in range(rows)
        ]

        # ── Painter's algorithm draw order: ascending tx+ty; tiebreak by ty ─
        self._draw_order: list[tuple[int, int]] = sorted(
            ((tx, ty) for ty in range(rows) for tx in range(cols)),
            key=lambda p: (p[0] + p[1], p[1]),
        )

        # ── Pre-allocate shapes — 1-4 per tile in draw order ───────────────
        # Layout per tile: [left_wall, right_wall, top_fill, top_border]
        # All start transparent; render() fills them with real geometry.
        all_shapes: list[cv.Path] = []
        self._tile_shapes: list[
            tuple[cv.Path | None, cv.Path | None, cv.Path, cv.Path | None]
        ] = []

        for _ in self._draw_order:
            lw = _make_quad_path(ft.PaintingStyle.FILL) if self._render_walls else None
            rw = _make_quad_path(ft.PaintingStyle.FILL) if self._render_walls else None
            tf = _make_quad_path(ft.PaintingStyle.FILL)
            tb = (
                _make_quad_path(ft.PaintingStyle.STROKE, stroke_width=0.8)
                if self._border else None
            )
            self._tile_shapes.append((lw, rw, tf, tb))
            if lw is not None:
                all_shapes.append(lw)
            if rw is not None:
                all_shapes.append(rw)
            all_shapes.append(tf)
            if tb is not None:
                all_shapes.append(tb)

        # ── Canvas — shapes list is set once and never replaced ────────────
        self._canvas = cv.Canvas(
            shapes=all_shapes,
            width=viewport_w,
            height=viewport_h,
        )

        # Tile-tap GestureDetector is wired lazily by on_tile_click().
        # A full-viewport pan/tap GD with no consumer still enters Flutter's
        # gesture arena and can fight nested touch controls (joysticks).
        self._click_callback: Optional[Callable[[int, int, IsoTile], None]] = None
        self._gd: ft.GestureDetector | None = None
        self._container = ft.Container(
            content=self._canvas,
            width=viewport_w,
            height=viewport_h,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        #: Add ``iso.control`` to ``scene.add()`` or directly to a ``ft.Stack``.
        self.control: ft.Control = self._container

        # ── Dirty flag — avoids redundant canvas.update() on static maps ────
        self._dirty: bool = True  # True initially so first render() draws

        # ── Cached bisect key — avoids recreating a lambda every render() ───
        self._draw_key = lambda p: (p[0] + p[1], p[1])

        # ── Active-shape tracking — avoids iterating all shapes to clear ────
        # Stores indices into _tile_shapes that were drawn (not culled) last
        # frame.  On the next frame, only these need clearing if they fall
        # outside the new visible range.
        self._active_shape_indices: list[int] = []

    # ── Public grid API ───────────────────────────────────────────────────────

    def invalidate(self) -> None:
        """Mark the map as needing a redraw.  Call after batch-modifying tiles
        without using :meth:`set_tile` (e.g. direct grid mutations).
        render() returns immediately if the map is not dirty.
        """
        self._dirty = True

    def set_tile(
        self,
        tx: int,
        ty: int,
        color: Optional[str] = None,
        top_color: Optional[str] = None,
        wall_color: Optional[str] = None,
        wall_h: Optional[int] = None,
        passable: Optional[bool] = None,
        tag: str = "",
        data: object = None,
    ) -> None:
        """Update one tile's properties.  Call ``render()`` to apply changes."""
        if not (0 <= tx < self._cols and 0 <= ty < self._rows):
            return
        t = self._grid[ty][tx]
        if color      is not None: t.color      = color; t.top_color = color
        if top_color  is not None: t.top_color  = top_color
        if wall_color is not None: t.wall_color = wall_color
        if wall_h     is not None: t.wall_h     = wall_h
        if passable   is not None: t.passable   = passable
        if tag:                    t.tag        = tag
        if data is not None:       t.data       = data
        self._dirty = True

    def get_tile(self, tx: int, ty: int) -> Optional[IsoTile]:
        """Return the ``IsoTile`` at (tx, ty), or ``None`` if out of bounds."""
        if 0 <= tx < self._cols and 0 <= ty < self._rows:
            return self._grid[ty][tx]
        return None

    def fill(self, color: str, wall_h: int = 0) -> None:
        """Set all tiles to the same colour.  Call ``render()`` after."""
        for row in self._grid:
            for t in row:
                t.color     = color
                t.top_color = color
                t.wall_h    = wall_h
        self._dirty = True

    # ── Camera pan ────────────────────────────────────────────────────────────

    def pan(self, dx: float, dy: float) -> None:
        """Shift the map by (dx, dy) screen pixels.  Call ``render()`` after."""
        self._ox += dx
        self._oy += dy
        self._dirty = True

    def center_on(self, tx: float, ty: float) -> None:
        """Pan so that grid cell (tx, ty) is centred in the viewport.

        Does NOT call ``render()`` automatically so you can batch more changes.
        """
        sx, sy = iso_to_screen(tx, ty, self._tw, self._th, 0.0, 0.0)
        self._ox = self._vw / 2 - sx
        self._oy = self._vh / 2 - sy
        self._dirty = True

    @property
    def origin_x(self) -> float:
        return self._ox

    @property
    def origin_y(self) -> float:
        return self._oy

    @property
    def render_walls(self) -> bool:
        """Whether wall side faces are rendered for extruded tiles."""
        return self._render_walls

    @render_walls.setter
    def render_walls(self, value: bool) -> None:
        """Toggle wall side-face rendering at runtime.

        Disabling this keeps top faces and click detection intact while
        skipping the extra wall-face updates in :meth:`render`.
        """
        if value == self._render_walls:
            return
        self._render_walls = value
        if not value:
            for lw, rw, _, _ in self._tile_shapes:
                if lw is not None:
                    lw.paint.color = _TRANSPARENT
                if rw is not None:
                    rw.paint.color = _TRANSPARENT
        self._dirty = True

    # ── Coordinate conversion ─────────────────────────────────────────────────

    def iso_to_screen(self, tx: float, ty: float) -> tuple[float, float]:
        """Grid → screen pixel (top vertex of the diamond tile)."""
        return iso_to_screen(tx, ty, self._tw, self._th, self._ox, self._oy)

    def screen_to_iso(self, sx: float, sy: float) -> tuple[float, float]:
        """Screen pixel → fractional grid coords."""
        return screen_to_iso(sx, sy, self._tw, self._th, self._ox, self._oy)

    def screen_to_tile(self, sx: float, sy: float) -> Optional[tuple[int, int]]:
        """Screen pixel → integer tile coords, or ``None`` if out of bounds."""
        ftx, fty = self.screen_to_iso(sx, sy)
        tx = int(math.floor(ftx + 1e-6))
        ty = int(math.floor(fty + 1e-6))
        if 0 <= tx < self._cols and 0 <= ty < self._rows:
            return tx, ty
        return None

    def on_tile_click(self, callback: Callable[[int, int, IsoTile], None]) -> None:
        """Register a callback fired when a tile is tapped.

        The callback receives ``(tx, ty, tile)`` where ``tile`` is the
        :class:`IsoTile` instance at that grid position.
        """
        self._click_callback = callback
        if self._gd is None:
            self._gd = ft.GestureDetector(
                content=self._canvas,
                on_tap=self._on_tap,
            )
            self._container.content = self._gd
            try:
                if self._container.page is not None:
                    self._container.update()
            except RuntimeError:
                pass

    def _on_tap(self, e: ft.TapEvent) -> None:
        if self._click_callback is None:
            return
        local_x = e.local_x
        local_y = e.local_y
        tile_coords = self.screen_to_tile(local_x, local_y)
        if tile_coords is None:
            return
        tx, ty = tile_coords
        tile = self._grid[ty][tx]
        self._click_callback(tx, ty, tile)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _visible_tile_range(self) -> tuple[int, int]:
        """Return ``(start, end)`` indices into ``_draw_order`` for visible tiles.

        Uses bisect on the ``(tx + ty)`` sum to skip tiles that are definitely
        off-screen — avoids iterating every tile for large maps.
        """
        hh = self._th / 2.0
        margin = self._tw
        # y-range of visible area in isometric-sum space.
        # Tile top_y = oy + (tx + ty) * hh.  A tile is visible when its top_y
        # is within [-th - margin, vh + margin].
        min_sum = max(0, int((-margin - self._oy) / hh))
        max_sum = min(self._cols + self._rows,
                      int(math.ceil((self._vh + margin - self._oy) / hh)) + 1)
        if min_sum > max_sum:
            return 0, 0
        # _draw_order is sorted by (tx + ty, ty).  Use bisect to find the slice.
        start = bisect.bisect_left(self._draw_order, (min_sum, 0), key=self._draw_key)
        end   = bisect.bisect_right(self._draw_order, (max_sum, self._rows), key=self._draw_key)
        return start, end

    def render(self) -> None:
        """Update the canvas by mutating pre-allocated shapes in-place.

        Call this:
        - Once after ``scene.mount()`` for the initial draw.
        - After any ``set_tile()`` / ``fill()`` calls.
        - After ``pan()`` / ``center_on()``.

        Uses view-frustum culling — culled shapes are made transparent (paint
        colour → ``"#00000000"``) rather than removed, so the shape list stays
        fixed and Flet only sends delta changes each frame.

        Returns immediately if the map is not dirty (no changes since last
        render).  Call :meth:`invalidate` to force a redraw.
        """
        if not self._dirty:
            return
        self._dirty = False

        tw, th   = self._tw, self._th
        hw, hh   = tw / 2.0, th / 2.0
        ox, oy   = self._ox, self._oy
        vw, vh   = self._vw, self._vh
        margin   = tw
        border_c = "#00000040" if self._border else _TRANSPARENT

        # Only iterate tiles whose (tx + ty) sum could be visible.
        # Tiles outside this range are guaranteed off-screen; their shapes
        # stay transparent from the last frame (or initial state).
        range_start, range_end = self._visible_tile_range()
        # Clear ONLY shapes that were active last frame but are now outside the
        # visible range.  This avoids iterating all 1600+ transparent shapes.
        prev_active = self._active_shape_indices
        new_active: list[int] = []

        for i in prev_active:
            if i < range_start or i >= range_end:
                # This shape was visible last frame but is outside the range now.
                lw, rw, tf, tb = self._tile_shapes[i]
                if tf.paint.color != _TRANSPARENT:
                    tf.paint.color = _TRANSPARENT
                    if tb is not None:
                        tb.paint.color = _TRANSPARENT
                    if lw is not None:
                        lw.paint.color = _TRANSPARENT
                    if rw is not None:
                        rw.paint.color = _TRANSPARENT

        for global_idx in range(range_start, range_end):
            tx, ty = self._draw_order[global_idx]
            lw, rw, tf, tb = self._tile_shapes[global_idx]

            # ── Compute top vertex in screen space ─────────────────────────
            top_x = ox + (tx - ty) * hw
            top_y = oy + (tx + ty) * hh

            # ── Frustum cull — make transparent and skip ───────────────────
            if (
                top_x + tw < -margin
                or top_x > vw + margin
                or top_y + th + 64 < -margin
                or top_y > vh + margin
            ):
                if tf.paint.color != _TRANSPARENT:
                    tf.paint.color = _TRANSPARENT
                    if tb is not None:
                        tb.paint.color = _TRANSPARENT
                    if lw is not None:
                        lw.paint.color = _TRANSPARENT
                    if rw is not None:
                        rw.paint.color = _TRANSPARENT
                continue

            # This shape is visible — track it for next frame's clearing pass.
            new_active.append(global_idx)

            tile = self._grid[ty][tx]

            # ── Diamond vertices as scalars (avoids 4 tuple allocations/tile) ──
            top_x_hw   = top_x + hw       # top vertex x
            top_x_tw   = top_x + tw       # right vertex x
            top_y_hh   = top_y + hh       # left/right vertex y
            top_y_th   = top_y + th       # bottom vertex y

            # ── Wall faces ─────────────────────────────────────────────────
            wh = tile.wall_h
            if wh > 0 and self._render_walls and lw is not None and rw is not None:
                left_wc  = tile.wall_color if tile.wall_color else _darken(tile.color, 0.60)
                right_wc = _darken(tile.color, 0.42)
                # bottom-down / left-down / right-down (scalars, no tuples)
                bd_x, bd_y = top_x_hw, top_y_th + wh
                ld_x, ld_y = top_x,      top_y_hh + wh
                rd_x, rd_y = top_x_tw,   top_y_hh + wh
                _update_quad(lw,
                             top_x,    top_y_hh,   # left
                             top_x_hw, top_y_th,  # bottom
                             bd_x,     bd_y,       # bottom-down
                             ld_x,     ld_y,       # left-down
                             left_wc)
                _update_quad(rw,
                             top_x_hw, top_y_th,  # bottom
                             top_x_tw, top_y_hh,  # right
                             rd_x,     rd_y,       # right-down
                             bd_x,     bd_y,       # bottom-down
                             right_wc)
            else:
                if lw is not None and lw.paint.color != _TRANSPARENT:
                    lw.paint.color = _TRANSPARENT
                if rw is not None and rw.paint.color != _TRANSPARENT:
                    rw.paint.color = _TRANSPARENT

            # ── Top face ───────────────────────────────────────────────────
            _update_quad(tf,
                         top_x_hw, top_y,     # top
                         top_x_tw, top_y_hh,  # right
                         top_x_hw, top_y_th,  # bottom
                         top_x,    top_y_hh,  # left
                         tile.top_color)
            if tb is not None:
                tb.paint.color = border_c
                _update_quad(tb,
                             top_x_hw, top_y,     # top
                             top_x_tw, top_y_hh,  # right
                             top_x_hw, top_y_th,  # bottom
                             top_x,    top_y_hh,  # left
                             border_c)

        self._active_shape_indices = new_active


# ── Colour helpers ────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=512)
def _darken(hex_color: str, factor: float) -> str:
    """Return a darkened version of a CSS hex colour string.

    Cached — same ``(color, factor)`` pair always returns the same result with
    no repeated string parsing.
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return hex_color
    r = max(0, int(int(h[0:2], 16) * factor))
    g = max(0, int(int(h[2:4], 16) * factor))
    b = max(0, int(int(h[4:6], 16) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"

