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

import functools
import math
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

        # Sprite list — populated via set_sprites().  Each item is a SpriteDef.
        self._sprites: list[SpriteDef] = []

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

        # Pre-computed ray direction table — one entry per column.
        # Recalculated when columns or fov changes.  Each entry is
        # (ray_angle_delta_from_center, cos_component, sin_component) but
        # we only store the delta; cos/sin are computed from the player
        # angle at render time via a cheap incremental trick.
        self._ray_table: list[float] = []
        self._build_ray_table()

        # Persistent shapes list — rebuilt only when column count changes.
        # Avoids creating new lists every frame.
        self._shapes: list = list(self._wall_shapes)

        # Per-column perpendicular wall distances (filled each frame).
        self._col_dists: list[float] = [0.0] * self._cols

        # Static background: ceiling top-half, floor bottom-half.
        half = self._height / 2
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
        self._ctrl = ft.Stack(
            width=self._width,
            height=self._height,
            controls=[bg, self._cv, *self._sprite_images, *self._seg_slots],
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def control(self) -> ft.Stack:
        """``ft.Stack`` to pass to ``scene.add(rc.control)``."""
        return self._ctrl

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

    @property
    def fov(self) -> float:
        """Current horizontal FOV in degrees.  Assign to zoom in/out at runtime."""
        return math.degrees(self._fov)

    @fov.setter
    def fov(self, degrees: float) -> None:
        self._fov = math.radians(float(degrees))
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
        # Rebuild the persistent shapes list to include the new wall shapes.
        self._shapes = list(self._wall_shapes)

    def _build_ray_table(self) -> None:
        """Pre-compute the angular offset for each column relative to the
        centre of the FOV.  Stored once and reused every frame — avoids
        ``col / divisor * fov`` arithmetic in the hot loop."""
        divisor = max(1, self._cols - 1)
        self._ray_table = [
            (col / divisor) * self._fov for col in range(self._cols)
        ]

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
        textures = self._wall_textures
        for col in range(self._cols):
            ray_a = angle - half_fov + self._ray_table[col]
            dist, wtype, side, wall_hit = self._cast(px, py, ray_a)
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

        # ── Sprite rendering (billboard sprites, depth-sorted back-to-front) ──

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
            screen_y = half_h - sprite_h + (self._cam_h - sprite.z) * sprite_base + sprite.floor_offset * sprite_base

            screen_x = half_w + (sprite_angle / self._fov) * self._width - sprite_w / 2

            visible.append((dist, screen_x, sprite_w, sprite_h, screen_y, sprite))

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
        shadow_end = used_shadows if used_shadows > 0 else 0
        self._shapes[self._cols:self._cols + shadow_end] = (
            self._shadow_shapes[:used_shadows]
        )
        # Trim any leftover shadows from a previous frame
        del self._shapes[self._cols + shadow_end:]
        self._used_sprite_images = used_images
        self._used_seg_images = used_segs
        self._cv.shapes = self._shapes
        if _batch_active is not None and _batch_active():
            return
        self._cv.update()

    # ── DDA Raycasting ─────────────────────────────────────────────────────────

    def _cast(
        self, px: float, py: float, angle: float
    ) -> tuple[float, int, int, float]:
        """Cast a single ray using DDA.

        Returns ``(perp_distance, wall_type, side, wall_hit)``.

        ``side``: ``0`` = X-face hit (NS wall), ``1`` = Y-face hit (EW wall).
        ``wall_type``: value from the map grid (1-based).
        ``wall_hit``: fractional position along the wall face (0.0–1.0),
            used as the texture U coordinate.
        """
        rdx = math.cos(angle)
        rdy = math.sin(angle)

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
            wall_hit = (py + perp * rdy / max(abs(rdx), 1e-30)) % 1.0
        else:
            # Y-face hit (horizontal wall) — U is based on X position.
            wall_hit = (px + perp * rdx / max(abs(rdy), 1e-30)) % 1.0

        return (max(0.01, perp), wtype, side, wall_hit)


# ── Colour helpers (module-level, no self needed) ─────────────────────────────

def _parse(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


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
