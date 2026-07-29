"""
camera.py — Camera: 2D scrolling viewport for worlds larger than the window.

``Camera`` wraps a *world canvas* (an ``ft.Stack``) inside a *viewport*
(a clipping ``ft.Stack``).  Moving the camera shifts the world canvas so that
only the relevant portion is visible — all world objects update in a single
Flet control change per frame, regardless of how many sprites exist.

Usage — basic follow-cam::

    cam = Camera(world_width=3200, world_height=480,
                 viewport_width=800, viewport_height=480)

    # Add the viewport to the scene (or page) — NOT the world directly.
    scene.add(cam.control)

    # Add world objects to the camera (they scroll with it).
    player = Sprite(x=80, y=200, width=40, height=64, color="cyan")
    cam.add(player)

    # HUD labels go directly on the scene so they stay fixed on screen.
    hud = Label(text="Score: 0", x=10, y=8)
    scene.add(hud, z=10)

    # Inside the game-loop callback:
    def update(dt):
        player.x += speed * dt
        cam.follow(player, lerp=0.08)   # smooth follow, clamped to bounds

Usage — manual camera control::

    cam.x = player.x - cam.viewport_width / 2
    cam.y = 0

Usage — parallax layers::

    # Create additional Camera layers with a speed fraction.
    bg_layer = cam.add_layer(speed=0.3)   # scrolls at 30 % of camera speed
    far_layer = cam.add_layer(speed=0.6)

    bg_sprite = Sprite(x=0, y=0, width=3200, height=480, image="sky.png")
    bg_layer.controls.append(bg_sprite.control)

    # bg_layer is updated automatically when cam.x / cam.y change.

Coordinate model::

    cam.x, cam.y          — top-left of the viewport in *world* coordinates
    sprite.x, sprite.y    — always in *world* coordinates
    cam.world_to_screen() — convert world → screen (for UI overlays)
    cam.screen_to_world() — convert screen → world (for mouse clicks)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Union, Optional

import flet as ft

from .sprite import Sprite
from .label import Label

# Game objects accepted by Camera.add / remove / clear.
_Obj = Union[Sprite, Label, ft.Control]


def _to_control(obj: _Obj) -> ft.Control:
    """Return the underlying ft.Control for Sprite / Label / raw control."""
    if isinstance(obj, (Sprite, Label)):
        return obj.control
    return obj


class _ParallaxLayer:
    """Internal: a world-sized Stack that scrolls at a fraction of camera speed."""

    def __init__(self, world_width: float, world_height: float, speed: float) -> None:
        self.speed = float(speed)
        self._stack = ft.Stack(
            width=world_width,
            height=world_height,
            clip_behavior=ft.ClipBehavior.NONE,
        )
        # Position will be set by the camera when cam.x / cam.y change.
        self._stack.left = 0.0
        self._stack.top = 0.0

    @property
    def controls(self) -> list:
        """Direct access to the underlying Stack's control list."""
        return self._stack.controls

    @property
    def stack(self) -> ft.Stack:
        return self._stack

    def _update(self, cam_x: float, cam_y: float) -> None:
        """Reposition this layer based on the camera position and speed factor."""
        self._stack.left = -cam_x * self.speed
        self._stack.top = -cam_y * self.speed


class Camera:
    """2D scrolling camera / viewport for game worlds larger than the window.

    The camera maintains a *world canvas* — an ``ft.Stack`` the size of the
    whole world — positioned inside a *viewport* ``ft.Stack`` that is clipped
    to the visible area.  Moving the camera shifts the world canvas in one
    Flet control update per frame (O(1)), not per sprite (O(n)).

    Parameters
    ----------
    world_width, world_height
        Full dimensions of the game world in pixels.
    viewport_width, viewport_height
        Visible window size.  Typically matches the ``Scene`` / page size.
    page
        Optional ``ft.Page`` reference.  If supplied, ``update()`` calls
        ``page.update()`` automatically after property changes.  Pass it when
        you need standalone camera updates outside a game loop.

    Notes
    -----
    * World objects (sprites, labels) go in ``cam.add()`` — they scroll.
    * HUD / overlay objects go in ``scene.add(obj, z=10)`` — they stay fixed.
    * ``cam.control`` is the viewport; add **this** (not the world stack) to
      the scene or page.
    """

    def __init__(
        self,
        world_width: float,
        world_height: float,
        viewport_width: float,
        viewport_height: float,
        page: Optional[ft.Page] = None,
    ) -> None:
        self._world_w = float(world_width)
        self._world_h = float(world_height)
        self._vp_w = float(viewport_width)
        self._vp_h = float(viewport_height)
        self._page = page

        self._x = 0.0
        self._y = 0.0

        # When True, _rebuild_world() defers the rebuild until the outermost
        # defer_rebuild() context exits.  Lets add_many batch without N rebuilds.
        self._rebuild_deferred: int = 0

        # (z, obj, ft_control) list for world objects — z-sorted.
        self._objects: list[tuple[int, _Obj, ft.Control]] = []

        # Parallax layers (ordered; rendered before the main world layer).
        self._parallax_layers: list[_ParallaxLayer] = []

        # The world Stack — holds all world-space sprites.
        self._world = ft.Stack(
            width=self._world_w,
            height=self._world_h,
            clip_behavior=ft.ClipBehavior.NONE,
        )
        self._world.left = 0.0
        self._world.top = 0.0

        # Viewport — clips to visible area; world + parallax layers are children.
        self._viewport = ft.Stack(
            width=self._vp_w,
            height=self._vp_h,
            controls=[self._world],
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    # ── Public read-only properties ───────────────────────────────────────────

    @property
    def x(self) -> float:
        """Left edge of the viewport in world coordinates."""
        return self._x

    @x.setter
    def x(self, value: float) -> None:
        self._x = self._clamp_x(value)
        self._apply_scroll()

    @property
    def y(self) -> float:
        """Top edge of the viewport in world coordinates."""
        return self._y

    @y.setter
    def y(self, value: float) -> None:
        self._y = self._clamp_y(value)
        self._apply_scroll()

    @property
    def viewport_width(self) -> float:
        """Width of the visible area."""
        return self._vp_w

    @property
    def viewport_height(self) -> float:
        """Height of the visible area."""
        return self._vp_h

    @property
    def world_width(self) -> float:
        """Full world width."""
        return self._world_w

    @property
    def world_height(self) -> float:
        """Full world height."""
        return self._world_h

    @property
    def control(self) -> ft.Control:
        """The viewport ``ft.Stack`` — add this to the scene or page."""
        return self._viewport

    @property
    def canvas(self) -> ft.Stack:
        """The world canvas Stack.  Direct access for advanced use-cases."""
        return self._world

    # ── Camera movement ───────────────────────────────────────────────────────

    def move_to(self, x: float, y: float) -> None:
        """Teleport camera so that world point (x, y) is the top-left corner."""
        self._x = self._clamp_x(x)
        self._y = self._clamp_y(y)
        self._apply_scroll()

    def center_on(self, wx: float, wy: float) -> None:
        """Teleport camera so that world point (wx, wy) is the viewport centre."""
        self.move_to(wx - self._vp_w / 2, wy - self._vp_h / 2)

    def follow(
        self,
        target: Union[Sprite, Label],
        lerp: float = 1.0,
        x_only: bool = False,
        y_only: bool = False,
    ) -> None:
        """Smoothly move the camera to keep *target* centred in the viewport.

        Parameters
        ----------
        target
            A :class:`~flet_game.Sprite` or :class:`~flet_game.Label` to track.
        lerp
            Interpolation factor per frame (0 < lerp ≤ 1).  ``1.0`` snaps
            instantly; ``0.05``–``0.15`` gives smooth easing.  Multiply by
            ``dt * target_fps`` to make it frame-rate-independent.
        x_only
            If ``True``, only track the target horizontally.
        y_only
            If ``True``, only track the target vertically.
        """
        tw = getattr(target, "width", 0)
        th = getattr(target, "height", 0)
        target_x = target.x + tw / 2 - self._vp_w / 2
        target_y = target.y + th / 2 - self._vp_h / 2

        new_x = self._x + (target_x - self._x) * lerp if not y_only else self._x
        new_y = self._y + (target_y - self._y) * lerp if not x_only else self._y

        # Clamp once so the early-out comparison reflects the final values.
        clamped_x = self._clamp_x(new_x)
        clamped_y = self._clamp_y(new_y)

        # Stationary-target early-out: if the camera position is unchanged
        # after lerp + clamp, skip the world.left/top writes and the parallax
        # layer repositioning.  Without this, follow() runs the full scroll
        # mutation every frame even when the target is standing still, marking
        # the world canvas (and every parallax layer) dirty for the end-of-frame
        # page.update() diff.
        if clamped_x == self._x and clamped_y == self._y:
            return

        self._x = clamped_x
        self._y = clamped_y
        self._apply_scroll()

    def pan(self, dx: float, dy: float) -> None:
        """Shift the camera by (dx, dy) world pixels, clamped to bounds."""
        self._x = self._clamp_x(self._x + dx)
        self._y = self._clamp_y(self._y + dy)
        self._apply_scroll()

    # ── Coordinate conversion ─────────────────────────────────────────────────

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        """Convert world coordinates to viewport (screen) coordinates."""
        return wx - self._x, wy - self._y

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert viewport (screen) coordinates to world coordinates."""
        return sx + self._x, sy + self._y

    def is_visible(self, obj: _Obj, margin: float = 0.0) -> bool:
        """Return ``True`` if *obj* overlaps the viewport (with optional margin)."""
        x = getattr(obj, "x", 0)
        y = getattr(obj, "y", 0)
        w = getattr(obj, "width", 0)
        h = getattr(obj, "height", 0)
        return (
            x + w + margin > self._x
            and x - margin < self._x + self._vp_w
            and y + h + margin > self._y
            and y - margin < self._y + self._vp_h
        )

    # ── World-object management ───────────────────────────────────────────────

    def add(self, obj: _Obj, z: int = 0) -> None:
        """Add a Sprite, Label, or ``ft.Control`` to the world canvas.

        Parameters
        ----------
        obj
            The object to add.  Sprites/Labels expose a ``.control``
            attribute; raw ``ft.Control`` instances are added directly.
        z
            Draw order.  Lower z is rendered behind higher z.  Use negative
            values (e.g. ``z=-10``) for background tiles/images and positive
            values (e.g. ``z=10``) for foreground details.
        """
        ctrl = _to_control(obj)
        insert_idx = len(self._objects)
        for i, (oz, _, _) in enumerate(self._objects):
            if oz > z:
                insert_idx = i
                break
        self._objects.insert(insert_idx, (z, obj, ctrl))
        self._rebuild_world()

    def add_many(self, objects: list[tuple[_Obj, int] | _Obj], z: int = 0) -> None:
        """Batch-add multiple world objects with a single rebuild.

        Parameters
        ----------
        objects
            A list where each element is either ``(obj, z)`` or a bare ``obj``
            (in which case the default *z* parameter is used).
        z
            Default z-layer for bare objects.
        """
        with self.defer_rebuild():
            for entry in objects:
                if isinstance(entry, tuple):
                    obj, oz = entry
                else:
                    obj, oz = entry, z
                ctrl = _to_control(obj)
                insert_idx = len(self._objects)
                for i, (existing_z, _, _) in enumerate(self._objects):
                    if existing_z > oz:
                        insert_idx = i
                        break
                self._objects.insert(insert_idx, (oz, obj, ctrl))

    def remove_many(self, objects: list) -> None:
        """Batch-remove multiple world objects with a single rebuild."""
        remove_set = {id(_to_control(obj)) for obj in objects}
        with self.defer_rebuild():
            self._objects = [
                (z, o, c) for z, o, c in self._objects
                if id(c) not in remove_set
            ]

    @contextmanager
    def defer_rebuild(self) -> Iterator[None]:
        """Context manager that defers world canvas rebuild.

        Use when adding/removing many objects::

            with cam.defer_rebuild():
                for i in range(100):
                    cam.add(Sprite(...))
        """
        self._rebuild_deferred += 1
        try:
            yield
        finally:
            self._rebuild_deferred -= 1
            if self._rebuild_deferred == 0:
                self._rebuild_world()

    def remove(self, obj: _Obj) -> None:
        """Remove a Sprite, Label, or ``ft.Control`` from the world canvas."""
        ctrl = _to_control(obj)
        self._objects = [
            (z, o, c) for (z, o, c) in self._objects if c is not ctrl
        ]
        self._rebuild_world()

    def clear(self, tag: Optional[str] = None) -> None:
        """Remove world objects.

        Parameters
        ----------
        tag
            If given, only objects whose ``.tag`` attribute equals *tag* are
            removed.  If ``None`` (default), all world objects are cleared.
        """
        if tag is None:
            self._objects.clear()
        else:
            self._objects = [
                (z, o, c)
                for (z, o, c) in self._objects
                if getattr(o, "tag", None) != tag
            ]
        self._rebuild_world()

    def objects(self, tag: Optional[str] = None) -> list[_Obj]:
        """Return world objects, optionally filtered by tag.

        Parameters
        ----------
        tag
            If given, only objects whose ``.tag`` attribute equals *tag* are
            returned.  If ``None`` (default), all world objects are returned.
        """
        objs = [o for (_, o, _) in self._objects]
        if tag is not None:
            objs = [o for o in objs if getattr(o, "tag", None) == tag]
        return objs

    # ── Parallax layers ───────────────────────────────────────────────────────

    def add_layer(self, speed: float = 0.5) -> ft.Stack:
        """Create a parallax layer that scrolls at a fraction of camera speed.

        Parameters
        ----------
        speed
            Scroll speed relative to the main world (0.0 = fixed, 1.0 = same
            speed as world).  Values between 0.1 and 0.8 are typical for
            background layers.

        Returns
        -------
        ft.Stack
            The layer's ``ft.Stack``.  Use :meth:`add_to_layer` to place
            sprites into it, or append raw controls via ``layer.controls``.

        Example
        -------
        ::

            sky_layer = cam.add_layer(speed=0.25)
            sky = Sprite(x=0, y=0, width=3200, height=480, image="sky.png")
            cam.add_to_layer(sky, sky_layer)
        """
        layer = _ParallaxLayer(self._world_w, self._world_h, speed)
        # Insert before the main world stack in the viewport.
        self._parallax_layers.append(layer)
        self._viewport.controls.insert(
            len(self._parallax_layers) - 1, layer.stack
        )
        return layer.stack

    def add_to_layer(self, obj: _Obj, layer: ft.Stack) -> None:
        """Add a Sprite, Label, or ``ft.Control`` to a parallax layer.

        Removes the need to access ``layer.controls`` directly::

            sky_layer = cam.add_layer(speed=0.25)
            sky = Sprite(x=0, y=0, width=3200, height=480, image="sky.png")
            cam.add_to_layer(sky, sky_layer)   # Sprite or ft.Control both work

        Parameters
        ----------
        obj
            A :class:`~flet_game.Sprite`, :class:`~flet_game.Label`, or raw
            ``ft.Control`` to place on the layer.
        layer
            The ``ft.Stack`` returned by :meth:`add_layer`.
        """
        layer.controls.append(_to_control(obj))

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _clamp_x(self, value: float) -> float:
        max_x = max(0.0, self._world_w - self._vp_w)
        return max(0.0, min(float(value), max_x))

    def _clamp_y(self, value: float) -> float:
        max_y = max(0.0, self._world_h - self._vp_h)
        return max(0.0, min(float(value), max_y))

    def _apply_scroll(self) -> None:
        """Update the world stack and all parallax layers to match cam.x/y."""
        self._world.left = -self._x
        self._world.top = -self._y
        for layer in self._parallax_layers:
            layer._update(self._x, self._y)

    def _rebuild_world(self) -> None:
        """Re-sync the world Stack's control list from self._objects.

        When inside a ``defer_rebuild()`` context the actual rebuild is skipped;
        the deferred rebuild runs when the outermost context exits.
        """
        if self._rebuild_deferred > 0:
            return
        self._world.controls = [c for (_, _, c) in self._objects]
