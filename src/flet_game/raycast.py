"""
raycast.py — RaycastCanvas: Wolfenstein-style raycasting 3D renderer.

Renders a first-person 3D view using the DDA (Digital Differential Analysis)
raycasting algorithm — the same technique used by Wolfenstein 3D (1992).

All vertical column strips are drawn as ``flet.canvas.Rect`` shapes on a
single ``flet.canvas.Canvas`` and submitted in one batch per frame, making
this far more efficient than updating individual Sprite controls.

Quick start::

    from flet_game import RaycastCanvas, SpriteDef, Scene, Loop, Input

    MY_MAP = [
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 0, 1],
        [1, 0, 2, 0, 0, 2, 0, 1],
        [1, 0, 0, 0, 0, 0, 0, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
    ]

    rc = RaycastCanvas(
        width=390, height=600,
        map_data=MY_MAP,
        wall_colors=["#cc2200", "#0044cc"],
        ceiling_color="#222222",
        floor_color="#555555",
        fog_distance=7.0,
    )
    scene.add(rc.control)

    px, py, angle = 1.5, 1.5, 0.0

    @loop.on_update
    def update(dt: float) -> None:
        nonlocal px, py, angle
        # ... rotate / move player, then:
        rc.set_sprites([SpriteDef(x=3.5, y=1.5, image="sprites/monster.png")])
        rc.render(px, py, angle)

Map format
----------
``map_data`` is a 2-D list of ints.  ``0`` = walkable cell.  Any value
``> 0`` is a wall; the value is used as a 1-based index into ``wall_colors``
(clamped to the list length).

    map_data = [
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 2, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 1],
    ]

Coordinate system
-----------------
Map cells are 1×1 units.  Player position ``(px, py)`` is in map units
(e.g. ``1.5, 1.5`` is the centre of the cell at column 1, row 1).
``angle`` is in **radians**: ``0`` points in the +X direction, ``π/2``
points in the +Y direction (down the map rows).

Performance tuning
------------------
``columns=80`` (default) → 80 Rect shapes per frame → ~25 fps on a mid-range
phone.  ``columns=40`` is safer for older devices.  ``columns=120`` gives
smoother walls but needs a faster device.

``fog_distance`` (map units, default 0 = off) blends far walls toward the
ceiling colour, hiding the draw-distance cut-off and adding atmosphere.
"""

from __future__ import annotations

import asyncio
import functools
import math
import time as _time
from dataclasses import dataclass
from typing import Optional

import flet as ft
import flet.canvas as cv

# Hoisted to module level: previously imported inside render() per frame.
try:
    from .loop import batch_active as _batch_active
except ImportError:
    _batch_active = None

# WallTexture is imported lazily in __init__ to avoid circular imports.
WallTexture = None  # type: ignore[assignment,misc]

_FOG_STEPS = 64
_TRANSPARENT = "#00000000"
# 1×1 transparent PNG (base64) — used as default src for pre-allocated ft.Image
# controls so Flet does not warn about an empty src value.
_TRANSPARENT_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB"
    "Nl7BcQAAAABJRU5ErkJggg=="
)


# ── Built-in demo map (10 × 10) ───────────────────────────────────────────────

DEFAULT_MAP: list[list[int]] = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 0, 0, 2, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 0, 0, 2, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]

DEFAULT_WALL_COLORS: list[str] = [
    "#cc2200",  # wall type 1 — red brick
    "#0044cc",  # wall type 2 — blue stone
    "#008844",  # wall type 3 — green
    "#cc9900",  # wall type 4 — yellow
]


@dataclass
class SpriteDef:
    """A billboard sprite in the 3D world space.

    Attributes:
        x: World X position (map units).
        y: World Y position (map units).
        image: Image source path (relative to ``page.assets_dir``).
        z: Height above ground in map units (default 0.0 = on the floor).
            ``0.0`` places feet on the ground.  Positive values elevate
            the sprite (e.g. ``1.5`` for a flying bat, ``2.5`` for a
            ceiling lamp).  The sprite's shadow always renders on the
            ground regardless of ``z``.
        world_height: Sprite height in map units (default 1.0 = one cell
            tall).  Typical values: 0.3 for a small item, 0.9 for a
            short enemy, 1.0 for a tall one.
        aspect_ratio: Width-to-height ratio (default 0.35).  Override for
            non-character sprites (e.g. 1.0 for square items).
        scale_x: Horizontal stretch multiplier (default 1.0).  Values
            greater than 1 make the sprite wider; less than 1 narrower.
            Use to compensate for undersized source images.
        scale_y: Vertical stretch multiplier (default 1.0).  Values
            greater than 1 make the sprite taller; less than 1 shorter.
            Use to compensate for undersized source images.
        shadow: Whether to render a ground shadow beneath this sprite.
        shadow_alpha: Opacity of the ground shadow (0.0–1.0).
        floor_offset: Vertical offset in **world units** (default 0.0).
            Positive values push the sprite DOWN from its natural ground
            position.  Use this to compensate for sprite images that have
            transparent space below the visible feet.  Because it is in
            world units (not pixels), it scales correctly with perspective
            at all distances.  Typical value: 0.05–0.15 for sprites with
            transparent padding below the feet.
    """
    x: float
    y: float
    image: str
    z: float = 0.0
    world_height: float = 1.0
    aspect_ratio: float = 0.35
    scale_x: float = 1.0
    scale_y: float = 1.0
    shadow: bool = True
    shadow_alpha: float = 0.33
    floor_offset: float = 0.0


@dataclass
class WallDecal:
    """A wall-mounted decal that renders flush against a wall face.

    Unlike billboard sprites that always face the camera, wall decals are
    rendered flat against the wall surface.  This makes them ideal for
    posters, frames, signs, fire extinguisher boxes, and other objects
    that should appear attached to walls.

    Attributes
    ----------
    x : float
        World X position (map units) — center of the decal.
    y : float
        World Y position (map units) — center of the decal.
    face : int
        Wall face direction: 0=north (−Y), 1=south (+Y),
        2=east (+X), 3=west (−X).
    color : str
        Hex colour string for the decal.  Use a frame border colour for
        frames, or any colour for solid wall-mounted objects.
    width : float
        Width in world units (default 0.5).  Should be ≤ 1.0 to fit
        on a single wall face.
    height : float
        Height in world units (default 0.5).  Use 0.5 for half-height
        frames, 1.0 for full-height.
    v_offset : float
        Vertical offset from wall center (default 0.0 = centered).
        Positive values move the decal DOWN.  Use 0.0 for vertically
        centered, or adjust for top/bottom alignment.
    """
    x: float
    y: float
    face: int  # 0=north, 1=south, 2=east, 3=west
    color: str
    width: float = 0.5
    height: float = 0.5
    v_offset: float = 0.0


@dataclass
class FloorBand:
    """A thin coloured line lying flat on the floor along a vertical plane.

    Rendered directly into the RawImage framebuffer (rawimage backend only)
    as a per-column single pixel row, so it is atomic with the walls — no
    overlay control, no desync flicker.  Used for yellow platform safety
    lines etc.

    Attributes
    ----------
    x : float
        World X of the vertical plane the line lies on (the line runs along
        the Y axis at this X).
    color : str
        Hex colour string for the line.
    y0, y1 : float
        World-Y range the line spans along the plane (default full map).
    """

    x: float
    color: str
    y0: float = 0.0
    y1: float = 1e9


@dataclass
class CeilingLight:
    """A flat luminous capsule hanging from the ceiling along a vertical plane.

    Rendered directly into the RawImage framebuffer (rawimage backend only)
    as a ceiling band, fog-faded by distance.  Atomic with the walls, so it
    never flickers against them.

    Attributes
    ----------
    x : float
        World X of the vertical plane the light lies on (the light runs
        along the Y axis at this X).
    y : float
        World Y of the light centre.
    z : float
        Height above the floor in map units (default 0.88 ≈ near ceiling).
    half_len : float
        Half-length of the light along the Y axis (world units).
    thickness : float
        Vertical height of the light capsule (world units).
    color : str
        Hex colour string for the lit surface.
    """

    x: float
    y: float
    z: float = 0.88
    half_len: float = 0.2
    thickness: float = 0.08
    color: str = "#fff8e0"


class RaycastCanvas:
    """Wolfenstein-style raycasting 3D renderer backed by ``flet.canvas.Canvas``.

    Parameters
    ----------
    width, height
        Canvas size in pixels.
    columns
        Number of vertical ray columns (= number of Rect shapes per frame).
        Lower → faster but blockier.  Recommended: 40–120.
    fov
        Horizontal field of view in degrees.  66° is the classic Wolfenstein
        value; wider values (90°+) feel more modern.
    map_data
        2-D list of ints.  ``0`` = empty; ``1..N`` = wall type (1-based index
        into ``wall_colors``).  Uses :data:`DEFAULT_MAP` if omitted.
    wall_colors
        Hex colour strings for wall types 1, 2, 3 …  Y-side faces are
        automatically darkened by 35% for depth shading.  Uses
        :data:`DEFAULT_WALL_COLORS` if omitted.
    ceiling_color
        Colour of the ceiling (top half of the viewport).
    floor_color
        Colour of the floor (bottom half of the viewport).
    fog_distance
        Distance in map units at which walls fully blend into
        ``ceiling_color``.  ``0`` disables fog (default).
    max_depth
        Maximum ray travel in map cells before giving up.  Default 20.
    max_sprites
        Maximum billboard sprites rendered per frame.  Default 32.
    wall_textures
        Optional list of :class:`~raw_isomap.wall_texture.WallTexture`
        objects, one per wall type (index 0 = wall type 1, etc.).
        When a texture is provided for a wall type, its vertical colour
        strips replace the flat ``wall_colors`` entry for that type.
        ``None`` (default) means all walls use flat colours.
    camera_height
        Camera height above the floor in world units (default 0.5).
        This controls where the horizon line sits relative to the
        floor.  ``0.5`` means the camera is at half the room height
        (classic Wolfenstein).  Lower values (e.g. 0.3) give a
        crouching perspective; higher values (e.g. 0.7) give a
        tall/overhead feel.  Affects sprite vertical positioning:
        ground sprites (``z=0``) have their feet at
        ``half_h + camera_height * sprite_base``.
    renderer
        Rendering backend for walls/floor/ceiling. ``"canvas"`` keeps the
        existing ``flet.canvas.Canvas`` wall-strip renderer. ``"rawimage"``
        streams a pixel frame through ``ft.RawImage``. ``"auto"`` selects
        ``RawImage`` when available, otherwise falls back to ``"canvas"``.
        Sprite billboards remain regular Flet controls in all modes.
    """

    def __init__(
        self,
        width: float = 390,
        height: float = 600,
        columns: int = 80,
        fov: float = 66.0,
        map_data: Optional[list[list[int]]] = None,
        wall_colors: Optional[list[str]] = None,
        ceiling_color: str = "#383838",
        floor_color: str = "#707070",
        fog_distance: float = 0.0,
        max_depth: int = 20,
        max_sprites: int = 32,
        wall_textures: Optional[list] = None,
        camera_height: float = 0.5,
        renderer: str = "canvas",
    ) -> None:
        self._width  = float(width)
        self._height = float(height)
        self._cols   = columns
        self._fov    = math.radians(fov)
        self._half_fov = self._fov / 2.0
        self._map    = map_data if map_data is not None else DEFAULT_MAP
        self._map_h  = len(self._map)
        self._map_w  = len(self._map[0]) if self._map else 0
        self._wcolors = wall_colors if wall_colors is not None else DEFAULT_WALL_COLORS
        self._ceil   = ceiling_color
        self._floor  = floor_color
        self._fog    = fog_distance
        self._depth  = max_depth
        self._cam_h  = camera_height
        self._renderer = self._resolve_renderer(renderer)

        # Sprite list — populated via set_sprites().  Each item is a SpriteDef.
        self._sprites: list[SpriteDef] = []
        # Identity of the last sprite list handed to render().  The static-
        # camera skip in render() is only taken when it is unchanged too, so
        # engine callers who move sprites while the camera stands still still
        # get their sprites updated.
        self._sprites_key: object = None

        # Wall decal list — populated via set_wall_decals().  Each item is a WallDecal.
        self._wall_decals: list[WallDecal] = []

        # Flat floor decor (safety lines) + ceiling lights — rawimage only,
        # rasterized into the framebuffer so they are atomic with the walls.
        self._floor_bands: list[FloorBand] = []
        self._ceiling_lights: list[CeilingLight] = []
        self._floor_fog: list[tuple[bytes, ...]] = []
        self._light_fog: list[tuple[bytes, ...]] = []

        # Frame-phase timings (exposed for the on-device diagnostics HUD).
        self._dbg_wall_ms: float = 0.0
        self._dbg_sprite_ms: float = 0.0

        # Pre-darken each wall colour for Y-side (EW) faces.
        self._wcolors_dark = [_darken(c, 0.65) for c in self._wcolors]

        # Optional wall textures — indexed by wall type (0 = type 1).
        # Each entry is a WallTexture with .sample(u) → (light, dark).
        self._wall_textures: list | None = wall_textures

        # Pre-allocate the fixed-size wall-strip shape objects and their paints.
        self._wall_paints: list[ft.Paint] = []
        self._wall_shapes: list[cv.Rect] = []
        self._init_wall_shapes()

        # Pre-allocated shadow ovals — one per sprite slot.
        self._max_sprites: int = max_sprites
        self._shadow_paints: list[ft.Paint] = []
        self._shadow_shapes: list[cv.Oval] = []
        for _ in range(self._max_sprites):
            p = ft.Paint(color=_TRANSPARENT)
            self._shadow_paints.append(p)
            self._shadow_shapes.append(
                cv.Oval(x=0, y=0, width=0, height=0, paint=p)
            )

        # Pre-computed fog colour LUT (None when fog is disabled).
        self._fog_lut: list[list[str]] | None = None
        self._build_fog_lut()

        # Pre-baked RGBA byte tables for 2-D grid textures (rawimage only).
        self._grid_lut: list | None = None
        self._build_grid_lut()

        # O(1) wall-decal lookup + per-decal fog RGBA tables, rebuilt by
        # set_wall_decals().
        self._decal_index: dict[tuple[int, int], list[int]] = {}
        self._decal_fog: list[tuple[bytes, ...]] = []
        # Cheap per-column gate: does the (side, plane) this column hit have
        # any decal at all?  Avoids the _decals_at_wall() call for the ~90% of
        # columns with no decal.
        self._decal_plane_keys: set = set()

        # Pre-computed ray direction table — one entry per column.
        # Recalculated when columns or fov changes.  Each entry is
        # (cos_delta, sin_delta) for the column's angle offset from the
        # camera centre; at render time the ray direction is derived from
        # the player angle via the sum-of-angles formulas, so only two
        # trig calls are needed per frame instead of two per column.
        self._ray_table: list[tuple[float, float]] = []
        self._build_ray_table()

        # Persistent shapes list — rebuilt only when column count changes.
        # Avoids creating new lists every frame.
        self._shapes: list = list(self._wall_shapes)

        # Per-column perpendicular wall distances (filled each frame).
        self._col_dists: list[float] = [0.0] * self._cols

        # RawImage streaming state (used only by the optional rawimage backend).
        self._raw_image = None
        self._raw_frame_task: asyncio.Task | None = None
        self._raw_pending_frame: bytes | None = None
        self._raw_frame_width = self._cols
        self._raw_frame_height = max(1, int(self._height))
        self._raw_base_frame = b""
        # Camera key of the last built wall frame.  When the camera has not
        # moved, the previous frame is pixel-identical, so the expensive
        # per-column build AND the RawImage push (a client round-trip) are
        # skipped entirely.  Invalidated whenever columns/fov/template change.
        self._raw_last_key: tuple[float, float, float] | None = None
        # Bytes of the last frame handed to the RawImage channel — used to
        # avoid pushing duplicate frames when the camera moved but the wall
        # strips happened to be unchanged.
        self._raw_last_sent: bytes | None = None
        # Set when the Dart-side data channel dies (e.g. widget disposed by a
        # scene transition).  Frames are then dropped until the client
        # remounts the RawImage and opens a fresh channel (see the
        # on_data_channel_open wrapper below).
        self._raw_channel_dead = False
        # Set while a push attempt failed without an ACK (channel not yet
        # open, timed out, disposed...).  The retry loop re-sends the last
        # frame until one lands; cleared on the first successful push.  This
        # survives the on_data_channel_open wrapper clearing _raw_channel_dead
        # below, so a frame that failed before the channel opened is still
        # re-sent afterwards.
        self._raw_retry_needed = False
        # Optional cap on how many frames per second are pushed to the
        # client (0 = unlimited).  Each push is a PNG encode + upload + ACK
        # round-trip on the client side; capping it (e.g. 30 Hz on phones)
        # halves that work while the walls still update smoothly.
        self.max_push_rate: float = 0.0
        self._raw_last_push: float = 0.0
        self._rebuild_raw_frame_template()

        # Static background: ceiling top-half, floor bottom-half.
        half = self._height / 2
        if self._renderer == "rawimage":
            bg = None
            self._raw_image = ft.RawImage(
                width=self._width,
                height=self._height,
                fit=ft.BoxFit.FILL,
                filter_quality=ft.FilterQuality.NONE,
            )
            # A fresh channel means the client remounted the widget after a
            # scene transition — resume streaming.  Always run Flet's own
            # handler first so the channel capture and pending-ack replay
            # still happen.
            _open = self._raw_image.on_data_channel_open

            def _on_channel_open(e, _capture=_open):
                self._raw_channel_dead = False
                if _capture is not None:
                    _capture(e)

            self._raw_image.on_data_channel_open = _on_channel_open
        else:
            bg = ft.Stack(
                width=self._width,
                height=self._height,
                controls=[
                    ft.Container(width=self._width, height=half, bgcolor=self._ceil),
                    ft.Container(top=half, width=self._width, height=half,
                                 bgcolor=self._floor),
                ],
            )

        # Overlay canvas — only wall strips + shadows; redrawn every frame.
        self._cv = cv.Canvas(
            shapes=[],
            width=self._width,
            height=self._height,
        )

        # Pre-allocated image controls for texture-mapped sprites.
        self._sprite_images: list[ft.Image] = []
        for _ in range(self._max_sprites):
            img = ft.Image(
                src=_TRANSPARENT_PNG,
                width=0,
                height=0,
                fit=ft.BoxFit.COVER,
                align=ft.Alignment(0, 1),  # bottom-center anchor
                visible=False,
            )
            self._sprite_images.append(img)

        # Pre-allocated clipped segment controls for partially-occluded
        # sprites. Each sprite can be split into at most
        # _MAX_SEGS_PER_SPRITE visible spans when parts of it are hidden
        # behind walls.
        self._MAX_SEGS_PER_SPRITE = 8
        self._seg_images: list[ft.Image] = []
        self._seg_slots: list[ft.Container] = []
        for _ in range(self._max_sprites * self._MAX_SEGS_PER_SPRITE):
            img = ft.Image(
                src=_TRANSPARENT_PNG,
                width=0,
                height=0,
                fit=ft.BoxFit.FILL,
                align=ft.Alignment(0, 1),
                visible=False,
            )
            slot = ft.Container(
                content=ft.Stack(
                    width=0,
                    height=0,
                    controls=[img],
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
                width=0,
                height=0,
                visible=False,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            )
            self._seg_images.append(img)
            self._seg_slots.append(slot)

        # Track the number of image controls touched last frame so render()
        # only hides the slots that were actually active.
        self._used_sprite_images = 0
        self._used_seg_images = 0

        # Public control: Stack(background, canvas, sprite images, segment images).
        controls: list[ft.Control] = [self._cv, *self._sprite_images, *self._seg_slots]
        if self._raw_image is not None:
            controls.insert(0, self._raw_image)
        elif bg is not None:
            controls.insert(0, bg)
        self._ctrl = ft.Stack(
            width=self._width,
            height=self._height,
            controls=controls,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def _resolve_renderer(self, renderer: str) -> str:
        mode = (renderer or "canvas").strip().lower()
        if mode not in {"canvas", "rawimage", "auto"}:
            raise ValueError("renderer must be 'canvas', 'rawimage', or 'auto'")
        if mode == "auto":
            return "rawimage" if hasattr(ft, "RawImage") else "canvas"
        if mode == "rawimage" and not hasattr(ft, "RawImage"):
            return "canvas"
        return mode

    def _rebuild_raw_frame_template(self) -> None:
        width = max(1, self._cols)
        height = max(1, int(self._height))
        ceil_rgba = bytes((*_parse(self._ceil), 255))
        floor_rgba = bytes((*_parse(self._floor), 255))
        ceil_row = ceil_rgba * width
        floor_row = floor_rgba * width
        half_h = height // 2
        self._raw_frame_width = width
        self._raw_frame_height = height
        self._raw_base_frame = b"".join([
            ceil_row for _ in range(half_h)
        ] + [
            floor_row for _ in range(height - half_h)
        ])
        # A new template invalidates any cached camera frame.
        self._raw_last_key = None

    def _schedule_raw_frame(self, frame: bytes) -> None:
        if self._raw_image is None:
            return
        # The Dart-side channel is dead (scene transition, disposed widget,
        # or a startup timeout).  Keep the newest frame pending so the
        # retry loop below can re-send it the moment the channel recovers —
        # do NOT drop it, or a static camera would never get walls back.
        if self._raw_channel_dead:
            self._raw_last_sent = frame
            self._raw_pending_frame = frame
            if self._raw_frame_task is not None and not self._raw_frame_task.done():
                return
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            self._raw_frame_task = loop.create_task(self._raw_render_loop())
            return
        # Skip byte-identical frames — the client is already showing this
        # exact image, and every push is an ACK round-trip through the
        # (sometimes saturated) data channel.
        if frame == self._raw_last_sent:
            return
        self._raw_last_sent = frame
        self._raw_pending_frame = frame
        if self._raw_frame_task is not None and not self._raw_frame_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._raw_frame_task = loop.create_task(self._raw_render_loop())

    async def _raw_render_loop(self) -> None:
        import time as _time

        # Self-healing push loop: pops the newest pending frame (or, while
        # the channel is dead, re-sends the latest frame) and retries with a
        # backoff instead of giving up.  This makes startup robust: the
        # first push often races the client's channel opening — if the
        # ready/ack timeout expires, the loop just tries again until the
        # client accepts a frame, so a static camera never stays blank.
        while self._raw_image is not None:
            if self._raw_pending_frame is not None:
                frame = self._raw_pending_frame
                self._raw_pending_frame = None
                self._raw_last_sent = frame
            elif self._raw_retry_needed and self._raw_last_sent is not None:
                # A previous push failed without an ACK — re-send the last
                # frame until the client accepts it (e.g. the very first
                # frame racing the channel opening at startup).
                frame = self._raw_last_sent
            else:
                return

            rate = self.max_push_rate
            if rate > 0:
                interval = 1.0 / rate
                wait = interval - (_time.monotonic() - self._raw_last_push)
                if wait > 0:
                    await asyncio.sleep(wait)
            try:
                self._raw_last_push = _time.monotonic()
                await self._raw_image.render_rgba(
                    width=self._raw_frame_width,
                    height=self._raw_frame_height,
                    pixels=frame,
                    premultiplied=True,
                )
                self._raw_retry_needed = False
                self._raw_channel_dead = False
            except (TimeoutError, asyncio.TimeoutError, RuntimeError):
                # Channel dead, not yet open, or the client never acked.
                self._raw_retry_needed = True
                self._raw_channel_dead = True
                await asyncio.sleep(0.5)
            except Exception:
                self._raw_retry_needed = True
                self._raw_channel_dead = True
                await asyncio.sleep(0.5)

    def _render_wall_frame(
        self,
        px: float,
        py: float,
        angle: float,
        col_w: float,
        half_fov: float,
        lut: list[list[str]] | None,
    ) -> None:
        # Camera did not move — the previous frame is pixel-identical, so
        # skip the per-column build and the RawImage push entirely.  The
        # per-column distances (_col_dists) are still valid for sprite
        # occlusion.  The key is invalidated on columns/fov/template change.
        key = (px, py, angle)
        if key == self._raw_last_key:
            return
        self._raw_last_key = key

        frame = bytearray(self._raw_base_frame)
        textures = self._wall_textures
        grid_tables = self._grid_lut
        height = self._raw_frame_height
        width = self._raw_frame_width
        stride = width * 4
        table = self._ray_table
        _cast = self._cast
        _cols = self._cols
        col_dists = self._col_dists
        fog = self._fog
        ceil = self._ceil
        wcolors = self._wcolors
        wcolors_dark = self._wcolors_dark
        fog_steps = _FOG_STEPS
        h = self._height
        n_colors = len(wcolors)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        half_h = self._height / 2.0
        cam_h = self._cam_h

        # Floor decor (safety lines) + ceiling lights, grouped by their X
        # plane so each distinct plane needs only one ray-plane intersection
        # per column.
        bands = self._floor_bands
        lights = self._ceiling_lights
        floor_by_plane: dict = {}
        if bands:
            for _bi, _b in enumerate(bands):
                floor_by_plane.setdefault(_b.x, []).append(_bi)
        light_by_plane: dict = {}
        if lights:
            for _li, _l in enumerate(lights):
                light_by_plane.setdefault(_l.x, []).append(_li)
        decor_planes = sorted(floor_by_plane.keys() | light_by_plane.keys())
        floor_fog = self._floor_fog
        light_fog = self._light_fog
        decal_plane_keys = self._decal_plane_keys

        for col in range(_cols):
            cd, sd = table[col]
            rdx = cos_a * cd - sin_a * sd
            rdy = sin_a * cd + cos_a * sd
            dist, wtype, side, wall_hit = _cast(px, py, rdx, rdy)
            col_dists[col] = dist

            strip_h = min(h, h / max(dist, 0.001))
            strip_y = (h - strip_h) / 2.0
            idx = wtype - 1
            if idx < 0:
                idx = 0
            elif idx >= n_colors:
                idx = n_colors - 1

            step = 0
            if lut is not None:
                step = min(fog_steps, int(dist * fog_steps / fog))

            grid_entry = None
            if grid_tables is not None and idx < len(grid_tables):
                grid_entry = grid_tables[idx]

            if grid_entry is not None:
                # 2-D grid texture — one span per run-length colour span,
                # each filled with the C-speed extended-slice trick.  All
                # colours come from the pre-baked init-time LUT.
                if strip_h < 24.0:
                    # Distant wall — bands are sub-pixel; single fill with
                    # the strip's vertical average colour.
                    rgba = grid_entry[2][side][min(int(wall_hit * len(grid_entry[2][0])), len(grid_entry[2][0]) - 1)][step]
                    y0 = int(strip_y)
                    if y0 < 0:
                        y0 = 0
                    y1 = int(strip_y + strip_h + 1)
                    if y1 > height:
                        y1 = height
                    if y1 > y0:
                        a = y0 * stride + col * 4
                        b = y1 * stride + col * 4
                        n = y1 - y0
                        frame[a:b:stride] = rgba[0:1] * n
                        frame[a + 1:b + 1:stride] = rgba[1:2] * n
                        frame[a + 2:b + 2:stride] = rgba[2:3] * n
                        frame[a + 3:b + 3:stride] = rgba[3:4] * n
                else:
                    runs_by_u, steps = grid_entry[0] if side == 0 else grid_entry[1]
                    n_strips_t = grid_entry[4]
                    u_idx = int(wall_hit * n_strips_t)
                    if u_idx < 0:
                        u_idx = 0
                    elif u_idx >= n_strips_t:
                        u_idx = n_strips_t - 1
                    band_h = strip_h / grid_entry[3]
                    for r0, r1, cidx in runs_by_u[u_idx]:
                        by0 = int(strip_y + r0 * band_h)
                        by1 = int(strip_y + (r1 + 1) * band_h) + 1
                        if by0 < 0:
                            by0 = 0
                        if by1 > height:
                            by1 = height
                        if by1 <= by0:
                            continue
                        rgba = steps[cidx][step]
                        a = by0 * stride + col * 4
                        b = by1 * stride + col * 4
                        n = by1 - by0
                        frame[a:b:stride] = rgba[0:1] * n
                        frame[a + 1:b + 1:stride] = rgba[1:2] * n
                        frame[a + 2:b + 2:stride] = rgba[2:3] * n
                        frame[a + 3:b + 3:stride] = rgba[3:4] * n
            elif textures is not None and idx < len(textures) and textures[idx] is not None:
                color = textures[idx].sample(wall_hit)[side]
                if lut is not None:
                    color = _blend(color, ceil, step / fog_steps)
                rgba = _rgba(color)
                y0 = int(strip_y)
                if y0 < 0:
                    y0 = 0
                y1 = int(strip_y + strip_h + 1)
                if y1 > height:
                    y1 = height
                if y1 > y0:
                    a = y0 * stride + col * 4
                    b = y1 * stride + col * 4
                    n = y1 - y0
                    frame[a:b:stride] = rgba[0:1] * n
                    frame[a + 1:b + 1:stride] = rgba[1:2] * n
                    frame[a + 2:b + 2:stride] = rgba[2:3] * n
                    frame[a + 3:b + 3:stride] = rgba[3:4] * n
            elif lut is not None:
                color = lut[idx * 2 + side][step]
                rgba = _rgba(color)
                y0 = int(strip_y)
                if y0 < 0:
                    y0 = 0
                y1 = int(strip_y + strip_h + 1)
                if y1 > height:
                    y1 = height
                if y1 > y0:
                    a = y0 * stride + col * 4
                    b = y1 * stride + col * 4
                    n = y1 - y0
                    frame[a:b:stride] = rgba[0:1] * n
                    frame[a + 1:b + 1:stride] = rgba[1:2] * n
                    frame[a + 2:b + 2:stride] = rgba[2:3] * n
                    frame[a + 3:b + 3:stride] = rgba[3:4] * n
            else:
                color = wcolors[idx] if side == 0 else wcolors_dark[idx]
                rgba = _rgba(color)
                y0 = int(strip_y)
                if y0 < 0:
                    y0 = 0
                y1 = int(strip_y + strip_h + 1)
                if y1 > height:
                    y1 = height
                if y1 > y0:
                    a = y0 * stride + col * 4
                    b = y1 * stride + col * 4
                    n = y1 - y0
                    frame[a:b:stride] = rgba[0:1] * n
                    frame[a + 1:b + 1:stride] = rgba[1:2] * n
                    frame[a + 2:b + 2:stride] = rgba[2:3] * n
                    frame[a + 3:b + 3:stride] = rgba[3:4] * n

            # ── Wall decals rasterized into the framebuffer ─────────────
            # Same projection math as the canvas backend; later stacked
            # decals paint over earlier ones (frame → poster inner).
            if decal_plane_keys:
                wall_x = px + rdx * dist
                wall_y = py + rdy * dist
                plane = wall_x if side == 0 else wall_y
                if (side, int(round(plane))) in decal_plane_keys:
                    for decal, d_steps in self._decals_at_wall(wall_x, wall_y, side):
                        decal_h = strip_h * decal.height
                        dy_top = strip_y + (strip_h - decal_h) / 2.0 + decal.v_offset * strip_h
                        dy0 = int(dy_top)
                        dy1 = int(dy_top + decal_h) + 1
                        if dy0 < 0:
                            dy0 = 0
                        if dy1 > height:
                            dy1 = height
                        if dy1 <= dy0:
                            continue
                        rgba = d_steps[step]
                        a = dy0 * stride + col * 4
                        b = dy1 * stride + col * 4
                        n = dy1 - dy0
                        frame[a:b:stride] = rgba[0:1] * n
                        frame[a + 1:b + 1:stride] = rgba[1:2] * n
                        frame[a + 2:b + 2:stride] = rgba[2:3] * n
                        frame[a + 3:b + 3:stride] = rgba[3:4] * n

            # ── Flat floor decor + ceiling lights (rawimage only) ─────────
            # Rasterized per column into the framebuffer so they are atomic
            # with the walls.  A plane crossing closer than the wall (t < dist)
            # is projected to the floor/ceiling row; fog-faded by distance.
            if decor_planes and rdx != 0.0:
                for plx in decor_planes:
                    t = (plx - px) / rdx
                    if t <= 0.001 or t >= dist:
                        continue
                    wy = py + rdy * t
                    scale = h / t
                    if scale > h:
                        scale = h
                    if lut is not None:
                        # Decorative lines/lights fade toward the floor/ceiling
                        # at 60% the wall fog rate — stopping short of full
                        # fade so distant decor stays readable (walls may fade
                        # out completely; lines/lights should not).
                        d_step = int(min(1.0, t / fog) * 0.6 * fog_steps)
                        if d_step > fog_steps:
                            d_step = fog_steps
                    else:
                        d_step = 0
                    f_idx = floor_by_plane.get(plx)
                    if f_idx:
                        for bi in f_idx:
                            b = bands[bi]
                            if wy < b.y0 or wy > b.y1:
                                continue
                            yr = half_h + cam_h * scale
                            yy = int(yr)
                            rgba = floor_fog[bi][d_step]
                            pos = yy * stride + col * 4
                            if 0 <= yy < height:
                                frame[pos:pos + 4] = rgba
                            pos2 = (yy + 1) * stride + col * 4
                            if 0 <= yy + 1 < height:
                                frame[pos2:pos2 + 4] = rgba
                    l_idx = light_by_plane.get(plx)
                    if l_idx:
                        for li in l_idx:
                            l = lights[li]
                            if abs(wy - l.y) > l.half_len:
                                continue
                            yc = half_h - (l.z - cam_h) * scale
                            th = l.thickness * scale
                            if th < 2.0:
                                th = 2.0
                            elif th > 12.0:
                                th = 12.0
                            yy0 = int(yc)
                            yy1 = int(yc + th) + 1
                            if yy1 <= yy0:
                                yy1 = yy0 + 1
                            rgba = light_fog[li][d_step]
                            if yy0 < 0:
                                yy0 = 0
                            if yy1 > height:
                                yy1 = height
                            base = col * 4
                            for r_ in range(yy0, yy1):
                                p_ = r_ * stride + base
                                frame[p_:p_ + 4] = rgba

        self._schedule_raw_frame(bytes(frame))

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def control(self) -> ft.Stack:
        """``ft.Stack`` to pass to ``scene.add(rc.control)``."""
        return self._ctrl

    @property
    def renderer(self) -> str:
        """Selected wall rendering backend: ``canvas`` or ``rawimage``."""
        return self._renderer

    def set_sprites(self, sprites: Optional[list[SpriteDef]] = None) -> None:
        """Replace the sprite list for this frame.

        Each item is a :class:`SpriteDef` instance.  Call before ``render()``
        each frame to update sprite positions.  Pass ``None`` or omit the
        argument to clear all sprites for this frame.

        Example::

            rc.set_sprites([
                SpriteDef(x=3.5, y=4.2, image="sprites/monster.png"),
                SpriteDef(x=8.1, y=2.7, image="sprites/monster2.png",
                          shadow=False),
            ])
            rc.render(px, py, angle)
        """
        self._sprites = sprites if sprites is not None else []

    def set_wall_decals(self, decals: Optional[list[WallDecal]] = None) -> None:
        """Replace the wall decal list for this frame.

        Each item is a :class:`WallDecal` instance.  Call before ``render()``
        each frame to update decal positions.  Pass ``None`` or omit the
        argument to clear all decals for this frame.

        Example::

            rc.set_wall_decals([
                WallDecal(x=2.5, y=4.5, face=2, image="sprites/poster.png",
                          width=0.4, height=0.5, v_offset=0.0),
            ])
            rc.render(px, py, angle)
        """
        self._wall_decals = decals if decals is not None else []
        # O(1) lookup: (side, wall-plane coord) -> decal indices.  Mirrors the
        # matching semantics of _find_decal_at_wall(): side 0 matches on the
        # decal's X plane, side 1 on its Y plane.  Stacked decals (frame +
        # inner) share a key and are returned in list order.
        self._decal_index = {}
        for i, d in enumerate(self._wall_decals):
            for side, plane in ((0, d.x), (1, d.y)):
                self._decal_index.setdefault((side, int(round(plane))), []).append(i)
        self._decal_plane_keys = set(self._decal_index.keys())
        # Pre-baked per-decal fog RGBA tables (one entry per fog step).
        if self._fog_lut is not None:
            self._decal_fog = [
                tuple(
                    _rgba(_blend(d.color, self._ceil, s / _FOG_STEPS))
                    for s in range(_FOG_STEPS + 1)
                )
                for d in self._wall_decals
            ]
        else:
            self._decal_fog = [(_rgba(d.color),) for d in self._wall_decals]
        self._raw_last_key = None

    def set_floor_bands(self, bands: Optional[list[FloorBand]] = None) -> None:
        """Replace the flat floor-decor lines (rawimage backend).

        Each :class:`FloorBand` is rasterized into the RawImage framebuffer
        per column with the walls, so it is atomic with them (no overlay
        control, no wall↔sprite desync flicker).
        """
        self._floor_bands = bands if bands is not None else []
        if self._fog_lut is not None:
            self._floor_fog = [
                tuple(
                    _rgba(_blend(b.color, self._floor, s / _FOG_STEPS))
                    for s in range(_FOG_STEPS + 1)
                )
                for b in self._floor_bands
            ]
        else:
            self._floor_fog = [(_rgba(b.color),) for b in self._floor_bands]
        self._raw_last_key = None

    def set_ceiling_lights(self, lights: Optional[list[CeilingLight]] = None) -> None:
        """Replace the ceiling-light decor (rawimage backend).

        Each :class:`CeilingLight` is drawn as a fog-faded ceiling band in the
        RawImage framebuffer, atomic with the walls.
        """
        self._ceiling_lights = lights if lights is not None else []
        if self._fog_lut is not None:
            self._light_fog = [
                tuple(
                    _rgba(_blend(l.color, self._ceil, s / _FOG_STEPS))
                    for s in range(_FOG_STEPS + 1)
                )
                for l in self._ceiling_lights
            ]
        else:
            self._light_fog = [(_rgba(l.color),) for l in self._ceiling_lights]
        self._raw_last_key = None

    def clear_frame(self) -> None:
        """Blank the view: push one opaque black frame and hide sprites.

        Used when gameplay ends (death / level complete) so the viewport
        shows a clean black screen instead of a frozen frame — a stale
        last-render of fog-blended walls reads as a dark-orange tint on
        screen.  The next ``render()`` call resumes normal frames.
        """
        self._raw_last_key = None
        self._sprites = []
        for i in range(self._used_sprite_images):
            self._sprite_images[i].visible = False
        for i in range(self._used_seg_images):
            self._seg_slots[i].visible = False
            self._seg_images[i].visible = False
        self._used_sprite_images = 0
        self._used_seg_images = 0
        if self._raw_image is not None:
            n = self._raw_frame_width * self._raw_frame_height
            self._schedule_raw_frame(b"\x00\x00\x00\xff" * n)

    @property
    def map_data(self) -> list[list[int]]:
        """The current map grid.  Assign a new 2-D list to replace it."""
        return self._map

    @map_data.setter
    def map_data(self, value: list[list[int]]) -> None:
        self._map   = value
        self._map_h = len(value)
        self._map_w = len(value[0]) if value else 0

    @property
    def columns(self) -> int:
        """Number of ray columns (resolution).  Change between scenes."""
        return self._cols

    @columns.setter
    def columns(self, value: int) -> None:
        self._cols = max(1, value)
        self._init_wall_shapes()
        self._build_ray_table()
        self._col_dists = [0.0] * self._cols
        self._rebuild_raw_frame_template()

    @property
    def fov(self) -> float:
        """Current horizontal FOV in degrees.  Assign to zoom in/out at runtime."""
        return math.degrees(self._fov)

    @fov.setter
    def fov(self, degrees: float) -> None:
        radians = math.radians(float(degrees))
        if math.isclose(self._fov, radians, rel_tol=0.0, abs_tol=1e-9):
            return
        self._fov = radians
        self._half_fov = self._fov / 2.0
        self._build_ray_table()

    def _init_wall_shapes(self) -> None:
        """Allocate (or re-allocate after a column-count change) the wall strip
        shape objects."""
        self._wall_paints = [ft.Paint(color="#000000") for _ in range(self._cols)]
        self._wall_shapes = [
            cv.Rect(x=0, y=0, width=1, height=1, paint=self._wall_paints[i])
            for i in range(self._cols)
        ]
        # Pre-allocate decal shapes (up to 3 stacked decals per column,
        # reused each frame).
        self._decal_paints = [ft.Paint(color=_TRANSPARENT) for _ in range(self._cols * 3)]
        self._decal_shapes = [
            cv.Rect(x=0, y=0, width=0, height=0, paint=self._decal_paints[i])
            for i in range(self._cols * 3)
        ]
        # Rebuild the persistent shapes list to include the new wall shapes.
        self._shapes = list(self._wall_shapes)

    def _build_ray_table(self) -> None:
        """Pre-compute each column's angle offset from the FOV centre and its
        (cos, sin) — reused every frame so the render loop needs only two
        trig calls per frame instead of two per column.  Rebuilding the
        table invalidates any cached RawImage frame (columns/fov changed)."""
        divisor = max(1, self._cols - 1)
        half_fov = self._half_fov
        self._ray_table = [
            (math.cos((col / divisor) * self._fov - half_fov),
             math.sin((col / divisor) * self._fov - half_fov))
            for col in range(self._cols)
        ]
        self._raw_last_key = None

    def _build_fog_lut(self) -> None:
        """Pre-compute fog-blended colours for every wall-colour variant at
        ``_FOG_STEPS + 1`` distance buckets."""
        if self._fog <= 0:
            self._fog_lut = None
            return
        lut: list[list[str]] = []
        for i in range(len(self._wcolors)):
            for base in (self._wcolors[i], self._wcolors_dark[i]):
                lut.append([
                    _blend(base, self._ceil, step / _FOG_STEPS)
                    for step in range(_FOG_STEPS + 1)
                ])
        self._fog_lut = lut

    def _build_grid_lut(self) -> None:
        """Pre-bake RGBA byte tables for 2-D grid textures (rawimage backend).

        For each grid texture, distinct colours are de-duplicated and each
        distinct colour is blended against the ceiling colour at every fog
        step once at init — the per-frame hot loop then only does integer
        index lookups, no hex parsing or blending.

        Per texture the vertical strips are also compressed into **run-length
        form**: each strip ``u`` becomes a short list of ``(row0, row1,
        colour_index)`` spans with consecutive rows that share a colour merged
        into one span.  The hot loop writes one span instead of one band per
        grid row — a tile texture (8 rows) becomes ~2–3 spans instead of 8
        strided slice writes per column.

        Entry layout per texture: ``None`` (no grid) or
        ``[(runs_light, steps_light), (runs_dark, steps_dark),
        (avg_steps_light, avg_steps_dark), n_rows, n_strips]``
        where ``runs_side[u]`` is the run list for strip ``u``,
        ``steps[c][s]`` is the RGBA bytes for colour index ``c`` at fog step
        ``s``, and ``avg_steps[strip][s]`` is the same for the strip's
        vertical average (used when the wall strip is too short for
        individual bands to be visible).
        """
        textures = self._wall_textures
        if textures is None:
            self._grid_lut = None
            return
        tables: list = []
        any_grid = False
        for tex in textures:
            if tex is None or not tex.has_grid:
                tables.append(None)
                continue
            any_grid = True
            n_rows = len(tex.grid_light)
            if n_rows == 0:
                tables.append(None)
                continue
            n_strips = len(tex.grid_light[0])
            entry = []
            for side_rows in (tex.grid_light, tex.grid_dark):
                distinct: list[str] = []
                cmap: dict[str, int] = {}
                idx_rows = []
                for row in side_rows:
                    irow = []
                    for c in row:
                        i = cmap.get(c)
                        if i is None:
                            i = cmap[c] = len(distinct)
                            distinct.append(c)
                        irow.append(i)
                    idx_rows.append(irow)
                if self._fog_lut is not None:
                    steps = [
                        tuple(
                            _rgba(_blend(c, self._ceil, s / _FOG_STEPS))
                            for s in range(_FOG_STEPS + 1)
                        )
                        for c in distinct
                    ]
                else:
                    steps = [(_rgba(c),) for c in distinct]
                # Per-strip run-length merge of consecutive same-colour rows.
                runs_by_u: list[list[tuple[int, int, int]]] = []
                for u in range(n_strips):
                    runs: list[tuple[int, int, int]] = []
                    prev_c: Optional[int] = None
                    r0 = 0
                    for r in range(n_rows):
                        c = idx_rows[r][u]
                        if c != prev_c:
                            if prev_c is not None:
                                runs.append((r0, r - 1, prev_c))
                            prev_c = c
                            r0 = r
                    if prev_c is not None:
                        runs.append((r0, n_rows - 1, prev_c))
                    runs_by_u.append(runs)
                entry.append((runs_by_u, steps))
            # Vertical-average fallback tables for short (distant) strips.
            avg_tables = []
            for avg_colors in (tex._light, tex._dark):
                if self._fog_lut is not None:
                    avg_tables.append([
                        tuple(
                            _rgba(_blend(c, self._ceil, s / _FOG_STEPS))
                            for s in range(_FOG_STEPS + 1)
                        )
                        for c in avg_colors
                    ])
                else:
                    avg_tables.append([(_rgba(c),) for c in avg_colors])
            entry.append(tuple(avg_tables))
            entry.append(n_rows)
            entry.append(n_strips)
            tables.append(entry)
        self._grid_lut = tables if any_grid else None

    def _decals_at_wall(
        self, wall_x: float, wall_y: float, side: int
    ) -> list[tuple[WallDecal, tuple[bytes, ...]]]:
        """Return up to 3 ``(decal, fog_rgba_table)`` matches at a wall hit.

        Uses the O(1) ``_decal_index`` built by ``set_wall_decals()``; the
        matching rules mirror ``_find_decal_at_wall()``.  Stacked decals are
        returned in list order so later decals (e.g. poster inners) are
        painted over earlier ones (frames).
        """
        if not self._decal_index:
            return []
        plane = wall_x if side == 0 else wall_y
        hits: list[tuple[WallDecal, tuple[bytes, ...]]] = []
        for i in self._decal_index.get((side, int(round(plane))), ()):
            d = self._wall_decals[i]
            if side == 0:
                ok = abs(wall_x - d.x) <= 0.01 and abs(wall_y - d.y) <= d.width / 2.0
            else:
                ok = abs(wall_y - d.y) <= 0.01 and abs(wall_x - d.x) <= d.width / 2.0
            if ok:
                hits.append((d, self._decal_fog[i]))
                if len(hits) >= 3:
                    break
        return hits

    def _find_decal_at_wall(self, wall_x: float, wall_y: float, side: int) -> Optional[WallDecal]:
        """Find a wall decal at the given wall hit position.

        Parameters
        ----------
        wall_x, wall_y : float
            World position of the wall hit point.
        side : int
            Raycaster side: 0 = NS wall (X-face), 1 = EW wall (Y-face).

        Returns
        -------
        WallDecal or None
            The first matching decal, or None if no decal is at this position.
        """
        for decal in self._wall_decals:
            if side == 0:
                # NS wall — runs along X axis; check X proximity
                if abs(wall_x - decal.x) <= 0.01 and abs(wall_y - decal.y) <= decal.width / 2.0:
                    return decal
            else:
                # EW wall — runs along Y axis; check Y proximity
                if abs(wall_y - decal.y) <= 0.01 and abs(wall_x - decal.x) <= decal.width / 2.0:
                    return decal
        return None

    def render(self, px: float, py: float, angle: float) -> None:
        """Render one frame from the player's world position and facing angle.

        Call this once per game-loop tick (inside ``@loop.on_update``).

        Parameters
        ----------
        px, py
            Player position in **map units** (e.g. ``1.5, 1.5`` = centre of
            map cell [1][1]).
        angle
            Facing direction in **radians**.  ``0`` = +X axis (east);
            ``math.pi / 2`` = +Y axis (south on the map grid).
        """
        col_w    = self._width / self._cols
        half_fov = self._half_fov
        half_w   = self._width / 2.0
        half_h   = self._height / 2.0
        lut      = self._fog_lut

        # ── Wall columns ──────────────────────────────────────────────────────
        if self._renderer == "rawimage":
            # Camera did not move — the wall frame is pixel-identical AND the
            # overlay sprites are already placed correctly, so skip the entire
            # frame (wall build + RawImage push + sprite control updates).
            # Zero per-frame work while idle kills wall/sprite desync flicker.
            key = (px, py, angle)
            if key == self._raw_last_key and self._sprites is self._sprites_key:
                self._dbg_wall_ms = 0.0
                self._dbg_sprite_ms = 0.0
                return
            self._sprites_key = self._sprites
            _t0 = _time.perf_counter()
            self._render_wall_frame(px, py, angle, col_w, half_fov, lut)
            self._dbg_wall_ms = (_time.perf_counter() - _t0) * 1000.0
        else:
            textures = self._wall_textures
            table = self._ray_table
            _cast = self._cast
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            used_decals = 0
            for col in range(self._cols):
                cd, sd = table[col]
                rdx = cos_a * cd - sin_a * sd
                rdy = sin_a * cd + cos_a * sd
                dist, wtype, side, wall_hit = _cast(px, py, rdx, rdy)
                self._col_dists[col] = dist

                strip_h = min(self._height, self._height / max(dist, 0.001))
                strip_y = (self._height - strip_h) / 2.0
                strip_x = col * col_w

                idx = max(0, min(wtype - 1, len(self._wcolors) - 1))

                # Texture sampling: use texture strips if available for this type.
                if textures is not None and idx < len(textures) and textures[idx] is not None:
                    color = textures[idx].sample(wall_hit)[side]
                    # Apply fog to textured walls: blend toward ceiling colour.
                    if lut is not None:
                        step = min(_FOG_STEPS, int(dist * _FOG_STEPS / self._fog))
                        color = _blend(color, self._ceil, step / _FOG_STEPS)
                elif lut is not None:
                    lut_idx = idx * 2 + side
                    step = min(_FOG_STEPS, int(dist * _FOG_STEPS / self._fog))
                    color = lut[lut_idx][step]
                else:
                    color = self._wcolors[idx] if side == 0 else self._wcolors_dark[idx]

                r = self._wall_shapes[col]
                r.x      = strip_x
                r.y      = strip_y
                r.width  = col_w + 1
                r.height = strip_h
                self._wall_paints[col].color = color

                # ── Wall decals (flat against wall surface) ────────────────
                # Up to 3 stacked decals per column (frame → inner), drawn
                # in list order so later decals paint over earlier ones.
                wall_x = px + rdx * dist
                wall_y = py + rdy * dist
                for decal, _ in self._decals_at_wall(wall_x, wall_y, side):
                    if used_decals >= len(self._decal_shapes):
                        break
                    decal_h = strip_h * decal.height
                    decal_y = strip_y + (strip_h - decal_h) / 2.0 + decal.v_offset * strip_h
                    dr = self._decal_shapes[used_decals]
                    dr.x = strip_x
                    dr.y = decal_y
                    dr.width = col_w + 1
                    dr.height = decal_h
                    self._decal_paints[used_decals].color = decal.color
                    used_decals += 1

        # ── Sprite rendering (billboard sprites, depth-sorted back-to-front) ──
        _t1 = _time.perf_counter()

        visible: list[tuple[float, float, float, float, float, SpriteDef]] = []
        for sprite in self._sprites:
            dx = sprite.x - px
            dy = sprite.y - py
            dist = math.hypot(dx, dy)
            if dist < 0.05:
                continue

            sprite_angle = math.atan2(dy, dx) - angle
            while sprite_angle > math.pi:
                sprite_angle -= 2 * math.pi
            while sprite_angle < -math.pi:
                sprite_angle += 2 * math.pi

            if abs(sprite_angle) > half_fov + 0.1:
                continue

            sprite_base = min(self._height, self._height / max(dist, 0.1))

            world_h = max(sprite.world_height, 0.01)
            sprite_h = world_h * sprite_base * sprite.scale_y
            sprite_w = sprite_h * sprite.aspect_ratio * sprite.scale_x
            screen_y = round(half_h - sprite_h + (self._cam_h - sprite.z) * sprite_base + sprite.floor_offset * sprite_base)

            screen_x = round(half_w + (sprite_angle / self._fov) * self._width - sprite_w / 2)

            # Whole-pixel geometry (snapped once per frame) keeps the
            # per-column occlusion test stable across frames — LookPad
            # micro-noise that would flip a column boundary (and toggle the
            # whole↔segmented draw mode) is absorbed into the ±0.5 px snap.
            visible.append((dist, screen_x, max(1, sprite_w), max(1, sprite_h), screen_y, sprite))

        visible.sort(key=lambda v: v[0], reverse=True)

        # ── Phase 1: cull sprites fully hidden behind walls ────────────────
        # For each sprite, check whether every screen column it spans has a
        # wall closer than the sprite distance.  If so, skip it entirely.
        filtered: list[tuple[float, float, float, float, float, SpriteDef]] = []
        for dist, sx, sw, sh, sy, sprite in visible:
            c0 = max(0, int(sx / col_w))
            c1 = min(self._cols - 1, int((sx + sw) / col_w))
            fully_hidden = True
            for c in range(c0, c1 + 1):
                if self._col_dists[c] >= dist:
                    fully_hidden = False
                    break
            if not fully_hidden:
                filtered.append((dist, sx, sw, sh, sy, sprite))
        visible = filtered

        draw_count = min(len(visible), self._max_sprites)
        used_images = 0
        used_shadows = 0
        prev_used_images = self._used_sprite_images
        prev_used_segs = self._used_seg_images

        # ── Hide only image slots used by the previous frame ───────────────
        for i in range(prev_used_images):
            self._sprite_images[i].visible = False
        for i in range(prev_used_segs):
            self._seg_slots[i].visible = False
            self._seg_images[i].visible = False

        # ── Ground shadows ──────────────────────────────────────────────────
        for si in range(draw_count):
            dist, sx, sw, sh, sy, sprite = visible[si]
            if not sprite.shadow or used_shadows >= len(self._shadow_shapes):
                continue
            shadow_h = sh * 0.18
            shadow_w = sw * 1.3
            p = self._shadow_paints[used_shadows]
            alpha_hex = f"{int(sprite.shadow_alpha * 255):02x}"
            p.color = f"#000000{alpha_hex}"
            r = self._shadow_shapes[used_shadows]
            r.x = sx - (shadow_w - sw) / 2
            # Shadow on the ground: ground_y = half_h + cam_h * sprite_base.
            # Recompute sprite_base from distance for correct perspective.
            s_base = min(self._height, self._height / max(dist, 0.1))
            ground_y = half_h + self._cam_h * s_base
            r.y = ground_y - shadow_h
            r.width = shadow_w
            r.height = shadow_h
            r.paint = p
            used_shadows += 1
        for i in range(used_shadows, len(self._shadow_shapes)):
            self._shadow_paints[i].color = _TRANSPARENT
            r = self._shadow_shapes[i]
            r.x = r.y = r.width = r.height = 0

        # ── Image sprites ───────────────────────────────────────────────────
        # For each visible sprite, determine per-column visibility using the
        # wall z-buffer (_col_dists).  Fully-visible sprites use one
        # _sprite_images slot.  Partially-occluded sprites are split into
        # contiguous visible column segments, each rendered as a narrow
        # _seg_images slot.
        used_segs = 0
        for si in range(draw_count):
            dist, sx, sw, sh, sy, sprite = visible[si]
            if not sprite.image:
                continue

            c0 = max(0, int(sx / col_w))
            c1 = min(self._cols - 1, int((sx + sw) / col_w))

            # Check if the sprite is fully visible (no column occluded).
            fully_visible = True
            for c in range(c0, c1 + 1):
                if self._col_dists[c] < dist:
                    fully_visible = False
                    break

            if fully_visible:
                # Use a single sprite image — no occlusion, fast path.
                if used_images < len(self._sprite_images):
                    img = self._sprite_images[used_images]
                    img.src = sprite.image
                    img.left = int(sx)
                    img.top = int(sy)
                    img.width = max(1, int(sw + 1))
                    img.height = max(1, int(sh + 1))
                    img.visible = True
                    used_images += 1
            else:
                # Partially occluded — split into visible column segments.
                seg_start = None
                for c in range(c0, c1 + 1):
                    col_visible = self._col_dists[c] >= dist
                    if col_visible and seg_start is None:
                        seg_start = c
                    elif not col_visible and seg_start is not None:
                        # Flush the segment [seg_start .. c-1]
                        if used_segs < len(self._seg_images):
                            seg_left = max(sx, seg_start * col_w)
                            seg_right = min(sx + sw, c * col_w)
                            seg_width = max(1.0, seg_right - seg_left)
                            crop_left = max(0.0, seg_left - sx)
                            seg_slot = self._seg_slots[used_segs]
                            seg_stack = seg_slot.content
                            si_img = self._seg_images[used_segs]
                            si_img.src = sprite.image
                            si_img.left = int(-crop_left)
                            si_img.top = 0
                            si_img.width = max(1, int(sw + 1))
                            si_img.height = max(1, int(sh + 1))
                            si_img.visible = True
                            seg_stack.width = max(1, int(seg_width + 1))
                            seg_stack.height = max(1, int(sh + 1))
                            seg_slot.left = int(seg_left)
                            seg_slot.top = int(sy)
                            seg_slot.width = max(1, int(seg_width + 1))
                            seg_slot.height = max(1, int(sh + 1))
                            seg_slot.visible = True
                            si_img.visible = True
                            used_segs += 1
                        seg_start = None
                # Flush trailing segment
                if seg_start is not None and used_segs < len(self._seg_images):
                    seg_left = max(sx, seg_start * col_w)
                    seg_right = min(sx + sw, (c1 + 1) * col_w)
                    seg_width = max(1.0, seg_right - seg_left)
                    crop_left = max(0.0, seg_left - sx)
                    seg_slot = self._seg_slots[used_segs]
                    seg_stack = seg_slot.content
                    si_img = self._seg_images[used_segs]
                    si_img.src = sprite.image
                    si_img.left = int(-crop_left)
                    si_img.top = 0
                    si_img.width = max(1, int(sw + 1))
                    si_img.height = max(1, int(sh + 1))
                    si_img.visible = True
                    seg_stack.width = max(1, int(seg_width + 1))
                    seg_stack.height = max(1, int(sh + 1))
                    seg_slot.left = int(seg_left)
                    seg_slot.top = int(sy)
                    seg_slot.width = max(1, int(seg_width + 1))
                    seg_slot.height = max(1, int(sh + 1))
                    seg_slot.visible = True
                    si_img.visible = True
                    used_segs += 1

        # ── Submit canvas shapes in one batch ───────────────────────────────
        # Mutate the persistent shapes list in-place for the shadow range,
        # then set it on the canvas.  No new list objects created per frame.
        if self._renderer == "rawimage":
            shadow_end = used_shadows if used_shadows > 0 else 0
            self._shapes[:shadow_end] = self._shadow_shapes[:used_shadows]
            del self._shapes[shadow_end:]
        else:
            # Add decal shapes after wall shapes
            decal_start = self._cols
            decal_end = decal_start + used_decals
            self._shapes[decal_start:decal_end] = self._decal_shapes[:used_decals]
            # Add shadow shapes after decal shapes
            shadow_start = decal_end
            shadow_end = shadow_start + (used_shadows if used_shadows > 0 else 0)
            self._shapes[shadow_start:shadow_end] = self._shadow_shapes[:used_shadows]
            # Trim any leftover shapes from a previous frame
            del self._shapes[shadow_end:]
        self._used_sprite_images = used_images
        self._used_seg_images = used_segs
        self._dbg_sprite_ms = (_time.perf_counter() - _t1) * 1000.0
        self._cv.shapes = self._shapes
        if _batch_active is not None and _batch_active():
            return
        self._cv.update()

    # ── DDA Raycasting ─────────────────────────────────────────────────────────

    def _cast(
        self, px: float, py: float, rdx: float, rdy: float
    ) -> tuple[float, int, int, float]:
        """Cast a single ray using DDA.

        ``rdx``/``rdy`` are the precomputed ray direction (unit vector) —
        pass ``(math.cos(a), math.sin(a))`` from the render loop, which
        derives them from the precomputed ray table (two trig calls per
        frame total).

        Returns ``(perp_distance, wall_type, side, wall_hit)``.

        ``side``: ``0`` = X-face hit (NS wall), ``1`` = Y-face hit (EW wall).
        ``wall_type``: value from the map grid (1-based).
        ``wall_hit``: fractional position along the wall face (0.0–1.0),
            used as the texture U coordinate.
        """
        mx = int(px)
        my = int(py)

        ddx = 1e30 if rdx == 0.0 else abs(1.0 / rdx)
        ddy = 1e30 if rdy == 0.0 else abs(1.0 / rdy)

        if rdx < 0:
            step_x = -1
            sdx = (px - mx) * ddx
        else:
            step_x = 1
            sdx = (mx + 1.0 - px) * ddx

        if rdy < 0:
            step_y = -1
            sdy = (py - my) * ddy
        else:
            step_y = 1
            sdy = (my + 1.0 - py) * ddy

        side   = 0
        wtype  = 0
        budget = self._depth

        while budget > 0:
            budget -= 1
            if sdx < sdy:
                sdx += ddx
                mx  += step_x
                side = 0
            else:
                sdy += ddy
                my  += step_y
                side = 1

            if 0 <= mx < self._map_w and 0 <= my < self._map_h:
                cell = self._map[my][mx]
                if cell > 0:
                    wtype = cell
                    break
            else:
                wtype = 1
                break

        if wtype == 0:
            return (float(self._depth), 1, 0, 0.0)

        perp = (sdx - ddx) if side == 0 else (sdy - ddy)

        # Compute texture U coordinate (fractional position along wall face).
        if side == 0:
            # X-face hit (vertical wall) — U is based on Y position.
            wall_hit = (py + perp * rdy) % 1.0
        else:
            # Y-face hit (horizontal wall) — U is based on X position.
            wall_hit = (px + perp * rdx) % 1.0

        return (max(0.01, perp), wtype, side, wall_hit)


# ── Colour helpers (module-level, no self needed) ─────────────────────────────

def _parse(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


@functools.lru_cache(maxsize=1024)
def _rgba(color: str) -> bytes:
    """RGBA8888 bytes for a hex colour — cached so the RawImage wall-frame
    hot loop never re-parses or re-allocates per column."""
    r, g, b = _parse(color)
    return bytes((r, g, b, 255))


def _to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


@functools.lru_cache(maxsize=256)
def _darken(color: str, factor: float) -> str:
    r, g, b = _parse(color)
    return _to_hex(int(r * factor), int(g * factor), int(b * factor))


@functools.lru_cache(maxsize=512)
def _blend(a: str, b: str, t: float) -> str:
    """Linear interpolation between colour ``a`` and colour ``b`` by ``t``."""
    r1, g1, b1 = _parse(a)
    r2, g2, b2 = _parse(b)
    return _to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )
