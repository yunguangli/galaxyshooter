"""
sprite.py — Sprite: the core game entity for flet_game.

A Sprite wraps an ft.Container positioned absolutely inside an ft.Stack
using the inherited LayoutControl properties `left` and `top`.

All visual properties (position, color, opacity, rotation, scale) are Python
properties that update the underlying ft.Container and trigger a UI refresh
automatically once the control is mounted on the page.

Animated variants (animate_to, fade_to, rotate_to, scale_to) leverage Flet's
built-in implicit animation system so no manual tweening loop is needed.
"""

from __future__ import annotations

import math
from typing import Optional, Callable

import flet as ft

from ._colors import _resolve_color

# Hoisted to module level: previously imported inside Sprite._update() on
# every property-setter call (hundreds of times per frame for moving sprites).
# `loop` has no engine-internal imports, so there is no circular-import risk.
try:
    from .loop import batch_active as _batch_active
except ImportError:  # loop module not yet loaded at import time
    _batch_active = None


class Sprite:
    """
    A game entity backed by an ft.Container positioned inside an ft.Stack.

    Parameters
    ----------
    x, y         : initial position in pixels from the top-left of the Stack
    width, height: size in pixels
    color        : background colour string (e.g. ft.Colors.RED or "#FF0000")
    image        : image URL or local asset path (displayed via DecorationImage)
    border_radius: uniform corner radius in pixels
    rotation     : initial rotation in degrees (clockwise)
    scale        : uniform scale factor (1.0 = normal size)
    opacity      : 0.0 (invisible) → 1.0 (fully opaque)
    visible      : whether the sprite is rendered
    tag          : arbitrary string label for game logic (e.g. "enemy", "bullet")
    on_click     : callback(e) fired when the sprite is clicked/tapped
    on_hover     : callback(e) fired when the pointer enters or leaves
    """

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 50,
        height: float = 50,
        color: Optional[str] = None,
        image: Optional[str] = None,
        border_radius: float = 0,
        rotation: float = 0.0,
        scale: float = 1.0,
        opacity: float = 1.0,
        visible: bool = True,
        tag: str = "",
        on_click: Optional[Callable] = None,
        on_hover: Optional[Callable] = None,
    ):
        self.tag = tag
        # Track rotation in degrees separately: Flet's Rotate.angle uses radians
        # internally, but our public API always speaks degrees for game-dev clarity.
        self._rotation_deg = float(rotation)

        # Cached AABB — invalidated when position or size changes.
        # Avoids recomputing bounds on every collision check.
        self._cached_bounds: tuple[float, float, float, float] | None = None

        self._control = ft.Container(
            width=width,
            height=height,
            bgcolor=_resolve_color(color),
            border_radius=ft.BorderRadius.all(border_radius) if border_radius else None,
            image=(
                ft.DecorationImage(src=image, fit=ft.BoxFit.COVER)
                if image
                else None
            ),
            # Flet Rotate.angle is radians; convert from the degree API we expose.
            rotate=ft.Rotate(angle=math.radians(rotation)),
            # scale accepts a plain float (ScaleValue) — no ft.Scale wrapper needed.
            scale=scale,
            opacity=opacity,
            visible=visible,
            on_click=on_click,
            on_hover=on_hover,
            # left/top are LayoutControl properties that position this container
            # absolutely within a parent ft.Stack. They have no effect in other
            # container types (Column, Row, etc.).
            left=x,
            top=y,
        )

    # ------------------------------------------------------------------
    # Raw Flet control access
    # ------------------------------------------------------------------

    @property
    def control(self) -> ft.Container:
        """The underlying ft.Container. Append this to ft.Stack.controls."""
        return self._control

    # ------------------------------------------------------------------
    # Position
    # ------------------------------------------------------------------

    @property
    def x(self) -> float:
        return self._control.left or 0.0

    @x.setter
    def x(self, value: float) -> None:
        # Clear animate_position so the move is instant. Without this, a previous
        # animate_to() call would make every subsequent x/y assignment animated too.
        # Guard with is-not-None to skip the write in the common case (game loop).
        if self._control.animate_position is not None:
            self._control.animate_position = None
        self._control.left = value
        self._invalidate_bounds()
        self._update()

    @property
    def y(self) -> float:
        return self._control.top or 0.0

    @y.setter
    def y(self, value: float) -> None:
        # Same animate_position guard as the x setter (see above).
        if self._control.animate_position is not None:
            self._control.animate_position = None
        self._control.top = value
        self._invalidate_bounds()
        self._update()

    def move_to(
        self,
        x: float,
        y: float,
        duration: int = 0,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
        on_end: Optional[Callable] = None,
    ) -> None:
        """Move the sprite to (x, y).

        Parameters
        ----------
        x, y
            Target position in pixels.
        duration
            Animation duration in milliseconds.  ``0`` (default) moves
            instantly; any positive value triggers a smooth Flet animation.
        curve
            Easing curve used when *duration* > 0.
        on_end
            Optional callback fired when the animation finishes.
        """
        if duration > 0:
            # Animated move — enable Flet implicit position animation.
            self._control.animate_position = ft.Animation(
                duration=duration, curve=curve
            )
            if on_end is not None:
                self._control.on_animation_end = on_end
        else:
            # Instant move — clear any lingering animation first.
            self._control.animate_position = None
        self._control.left = x
        self._control.top = y
        self._update()

    def animate_to(
        self,
        x: float,
        y: float,
        duration: int = 300,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
        on_end: Optional[Callable] = None,
    ) -> None:
        """Alias for ``move_to(x, y, duration=duration)`` — kept for compatibility."""
        self.move_to(x, y, duration=duration, curve=curve, on_end=on_end)

    # ------------------------------------------------------------------
    # Size
    # ------------------------------------------------------------------

    @property
    def width(self) -> float:
        return self._control.width or 0.0

    @width.setter
    def width(self, value: float) -> None:
        self._control.width = value
        self._invalidate_bounds()
        self._update()

    @property
    def height(self) -> float:
        return self._control.height or 0.0

    @height.setter
    def height(self, value: float) -> None:
        self._control.height = value
        self._invalidate_bounds()
        self._update()

    def resize(self, width: float, height: float) -> None:
        """Instantly set both width and height in one call."""
        self._control.width = width
        self._control.height = height
        self._invalidate_bounds()
        self._update()

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------

    @property
    def color(self) -> Optional[str]:
        return self._control.bgcolor

    @color.setter
    def color(self, value: Optional[str]) -> None:
        self._control.bgcolor = _resolve_color(value)
        self._update()

    @property
    def image(self) -> Optional[str]:
        return self._control.image.src if self._control.image else None

    @image.setter
    def image(self, value: Optional[str]) -> None:
        # Reuse the existing DecorationImage when only the src changes —
        # SpriteAnimation.update() hits this every frame advance, so avoiding
        # a fresh ft.DecorationImage allocation per frame matters.
        cur = self._control.image
        if value is None:
            if cur is not None:
                self._control.image = None
        elif cur is not None:
            cur.src = value
        else:
            self._control.image = ft.DecorationImage(src=value, fit=ft.BoxFit.COVER)
        self._update()

    @property
    def border_radius(self) -> float:
        br = self._control.border_radius
        if br is None:
            return 0.0
        # ft.BorderRadius object — top_left holds the uniform value
        return float(getattr(br, "top_left", 0) or 0)

    @border_radius.setter
    def border_radius(self, value: float) -> None:
        self._control.border_radius = ft.BorderRadius.all(value) if value else None
        self._update()

    @property
    def opacity(self) -> float:
        v = self._control.opacity
        return float(v) if v is not None else 1.0

    @opacity.setter
    def opacity(self, value: float) -> None:
        self._control.animate_opacity = None  # instant change
        self._control.opacity = max(0.0, min(1.0, value))
        self._update()

    def fade_to(
        self,
        opacity: float,
        duration: int = 300,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
    ) -> None:
        """Smoothly animate the sprite's opacity to the given value (0.0–1.0)."""
        self._control.animate_opacity = ft.Animation(duration=duration, curve=curve)
        self._control.opacity = max(0.0, min(1.0, opacity))
        self._update()

    @property
    def visible(self) -> bool:
        return bool(self._control.visible)

    @visible.setter
    def visible(self, value: bool) -> None:
        self._control.visible = value
        self._update()

    # ------------------------------------------------------------------
    # Transform
    # ------------------------------------------------------------------

    @property
    def rotation(self) -> float:
        """Rotation in degrees (clockwise)."""
        return self._rotation_deg

    @rotation.setter
    def rotation(self, degrees: float) -> None:
        self._rotation_deg = degrees
        self._control.animate_rotation = None  # instant change
        self._control.rotate = ft.Rotate(angle=math.radians(degrees))
        self._update()

    def rotate_to(
        self,
        degrees: float,
        duration: int = 300,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
    ) -> None:
        """Smoothly animate rotation to the given angle (degrees, clockwise)."""
        self._rotation_deg = degrees
        self._control.animate_rotation = ft.Animation(duration=duration, curve=curve)
        self._control.rotate = ft.Rotate(angle=math.radians(degrees))
        self._update()

    @property
    def scale(self) -> float:
        s = self._control.scale
        if s is None:
            return 1.0
        # Flet may return the raw float we set, or an ft.Scale object —
        # handle both so the getter is always reliable.
        if isinstance(s, (int, float)):
            return float(s)
        return float(getattr(s, "scale", 1.0))

    @scale.setter
    def scale(self, value: float) -> None:
        self._control.animate_scale = None  # instant change
        self._control.scale = value
        self._update()

    def scale_to(
        self,
        scale: float,
        duration: int = 300,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
    ) -> None:
        """Smoothly animate the sprite's scale."""
        self._control.animate_scale = ft.Animation(duration=duration, curve=curve)
        self._control.scale = scale
        self._update()

    # ------------------------------------------------------------------
    # Input callbacks
    # ------------------------------------------------------------------

    @property
    def on_click(self) -> Optional[Callable]:
        return self._control.on_click

    @on_click.setter
    def on_click(self, value: Optional[Callable]) -> None:
        self._control.on_click = value
        # No visual update needed — Flet registers event handlers dynamically

    @property
    def on_hover(self) -> Optional[Callable]:
        return self._control.on_hover

    @on_hover.setter
    def on_hover(self, value: Optional[Callable]) -> None:
        self._control.on_hover = value

    # ------------------------------------------------------------------
    # Collision helpers
    # ------------------------------------------------------------------

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """AABB bounding box: (left, top, right, bottom).

        Result is cached until a position or size property changes.
        """
        if self._cached_bounds is None:
            self._cached_bounds = (
                self.x, self.y,
                self.x + self.width, self.y + self.height,
            )
        return self._cached_bounds

    def _invalidate_bounds(self) -> None:
        """Force the AABB cache to be recomputed on the next access."""
        self._cached_bounds = None

    def collides_with(self, other: "Sprite") -> bool:
        """
        AABB overlap check against another Sprite.
        Returns True if the two sprites' bounding boxes overlap.
        """
        ax1, ay1, ax2, ay2 = self.bounds
        bx1, by1, bx2, by2 = other.bounds
        return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1

    def contains_point(self, px: float, py: float) -> bool:
        """Returns True if the point (px, py) is inside this sprite's bounding box."""
        x1, y1, x2, y2 = self.bounds
        return x1 <= px <= x2 and y1 <= py <= y2

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def hide(self) -> None:
        """Make this sprite invisible (``visible = False``).

        The sprite stays in the canvas and in any collision groups — only its
        rendering is suppressed.  Use ``scene.remove(sprite)`` to fully detach
        it from the canvas.
        """
        self.visible = False

    def show(self) -> None:
        """Make this sprite visible again (``visible = True``)."""
        self.visible = True

    def destroy(self) -> None:
        """Alias for :meth:`hide` — kept for compatibility."""
        self.hide()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update(self) -> None:
        """Trigger a Flet UI refresh if the control is mounted on a page."""
        # Flet 0.86+ raises RuntimeError (not returns None) when .page is
        # accessed on an unmounted control, so guard with try/except.
        try:
            if not self._control.page:
                return
        except RuntimeError:
            return
        # When the GameLoop is active it sets loop.batch_active = True and
        # calls page.update() once per frame. Skip the per-control flush during
        # that window to avoid double-flushing every sprite that moved.
        if _batch_active is not None and _batch_active():
            return
        self._control.update()

    def update(self) -> None:
        """Public alias for :meth:`_update` — force a Flet UI refresh.

        Useful when mutating sprite properties outside a
        :class:`~flet_game.GameLoop` callback (e.g. in button handlers).
        Inside a game-loop callback the batch flush handles the refresh,
        so calling this is a safe no-op during active frames.
        """
        self._update()

    def __repr__(self) -> str:
        return (
            f"Sprite(tag={self.tag!r}, x={self.x}, y={self.y}, "
            f"w={self.width}, h={self.height})"
        )
