"""
label.py — Label: a text entity positioned absolutely on the game canvas.

Like Sprite, a Label wraps its content inside an absolutely-positioned
ft.Container, so it slots into an ft.Stack game canvas and can be
repositioned, faded, and updated from inside a GameLoop callback without
any manual .update() calls.

    score = Label(x=10, y=10, text="Score: 0", size=20, color="white")
    canvas.controls.append(score.control)

    @loop.on_update
    def tick(dt):
        score.text = f"Score: {pts}"   # updates live — no .update() needed
"""

from __future__ import annotations

import math
from typing import Optional, Callable

import flet as ft

from ._colors import _resolve_color

# Hoisted to module level: previously imported inside Label._update() on
# every property-setter call. See sprite.py for the same pattern.
try:
    from .loop import batch_active as _batch_active
    from .loop import mark_frame_dirty as _mark_dirty
except ImportError:
    _batch_active = None
    _mark_dirty = None


class Label:
    """
    A text entity positioned absolutely inside an ft.Stack game canvas.

    Backed by an ft.Text inside a transparent ft.Container with left/top
    positioning. Property setters synchronise with the underlying Flet
    controls and trigger a UI refresh automatically — or stay silent during
    GameLoop frames and let the single page.update() handle the flush.
    """

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        text: str = "",
        size: float = 16,
        color: str | None = "white",   # CSS name, "#hex", or ft.Colors.*
        bold: bool = False,
        italic: bool = False,
        opacity: float = 1.0,
        visible: bool = True,
        tag: str = "",
        on_click: Callable | None = None,
    ) -> None:
        self._tag = tag

        self._text_ctrl = ft.Text(
            value=text,
            size=size,
            color=_resolve_color(color),
            weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
            italic=italic,
            # Prevent the Text from expanding beyond its natural width so
            # the container stays tight around the content.
            no_wrap=True,
        )

        # Transparent container gives us left/top absolute positioning on
        # the Stack while letting the ft.Text show through.
        self._container = ft.Container(
            left=x,
            top=y,
            content=self._text_ctrl,
            opacity=opacity,
            visible=visible,
            on_click=on_click,
            # No background — Label is pure text on the canvas.
            bgcolor=None,
        )

    # ------------------------------------------------------------------
    # Core properties
    # ------------------------------------------------------------------

    @property
    def tag(self) -> str:
        return self._tag

    @property
    def control(self) -> ft.Container:
        """The underlying ft.Container — append to ft.Stack.controls to mount."""
        return self._container

    @property
    def x(self) -> float:
        """Horizontal position from the left edge of the Stack."""
        return self._container.left

    @x.setter
    def x(self, value: float) -> None:
        self._container.left = value
        self._update()

    @property
    def y(self) -> float:
        """Vertical position from the top edge of the Stack."""
        return self._container.top

    @y.setter
    def y(self, value: float) -> None:
        self._container.top = value
        self._update()

    @property
    def text(self) -> str:
        """The displayed string."""
        return self._text_ctrl.value

    @text.setter
    def text(self, value: str) -> None:
        self._text_ctrl.value = value
        self._update()

    @property
    def size(self) -> float:
        """Font size in logical pixels."""
        return self._text_ctrl.size

    @size.setter
    def size(self, value: float) -> None:
        self._text_ctrl.size = value
        self._update()

    @property
    def color(self) -> str | None:
        """Text colour — CSS name, shade, hex, or ft.Colors.*"""
        return self._text_ctrl.color

    @color.setter
    def color(self, value: str | None) -> None:
        self._text_ctrl.color = _resolve_color(value)
        self._update()

    @property
    def opacity(self) -> float:
        return self._container.opacity

    @opacity.setter
    def opacity(self, value: float) -> None:
        self._container.opacity = max(0.0, min(1.0, value))
        self._update()

    @property
    def visible(self) -> bool:
        return self._container.visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._container.visible = value
        self._update()

    @property
    def bold(self) -> bool:
        return self._text_ctrl.weight == ft.FontWeight.BOLD

    @bold.setter
    def bold(self, value: bool) -> None:
        self._text_ctrl.weight = ft.FontWeight.BOLD if value else ft.FontWeight.NORMAL
        self._update()

    # ------------------------------------------------------------------
    # Position methods
    # ------------------------------------------------------------------

    def move_to(
        self,
        x: float,
        y: float,
        duration: int = 0,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
        on_end: Callable | None = None,
    ) -> None:
        """Move the label to (x, y).

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
            self._container.animate_position = ft.Animation(duration, curve)
            if on_end:
                self._container.on_animation_end = on_end
        else:
            self._container.animate_position = None
        self._container.left = x
        self._container.top = y
        self._update()

    def animate_to(
        self,
        x: float,
        y: float,
        duration: int = 300,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
        on_end: Callable | None = None,
    ) -> None:
        """Alias for ``move_to(x, y, duration=duration)`` — kept for compatibility."""
        self.move_to(x, y, duration=duration, curve=curve, on_end=on_end)

    # ------------------------------------------------------------------
    # Appearance methods
    # ------------------------------------------------------------------

    def fade_to(
        self,
        opacity: float,
        duration: int = 300,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
    ) -> None:
        """Animate opacity from current value to `opacity` (0.0–1.0)."""
        self._container.animate_opacity = ft.Animation(duration, curve)
        self._container.opacity = max(0.0, min(1.0, opacity))
        self._update()

    @property
    def scale(self) -> float:
        """Uniform scale factor (1.0 = normal size)."""
        s = self._container.scale
        if s is None:
            return 1.0
        if isinstance(s, (int, float)):
            return float(s)
        return float(getattr(s, "scale", 1.0))

    @scale.setter
    def scale(self, value: float) -> None:
        self._container.animate_scale = None  # instant change
        self._container.scale = float(value)
        self._update()

    def scale_to(
        self,
        scale: float,
        duration: int = 300,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
    ) -> None:
        """Smoothly animate the label's scale (1.0 = normal size)."""
        self._container.animate_scale = ft.Animation(duration, curve)
        self._container.scale = float(scale)
        self._update()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def hide(self) -> None:
        """Make this label invisible (``visible = False``)."""
        self.visible = False

    def show(self) -> None:
        """Make this label visible again (``visible = True``)."""
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
            if not self._container.page:
                return
        except RuntimeError:
            return
        # When the GameLoop is active, batch_active() returns True and a single
        # page.update() fires at end of frame — suppress per-control updates.
        if _batch_active is not None and _batch_active():
            _mark_dirty()
            return
        self._container.update()

    def update(self) -> None:
        """Public alias for :meth:`_update` — force a Flet UI refresh.

        Useful when setting label properties outside a :class:`~flet_game.GameLoop`
        callback (e.g. in button handlers or event callbacks).
        Inside a game-loop callback the batch flush already handles the refresh,
        so calling this is a no-op during active frames.
        """
        self._update()

    def __repr__(self) -> str:
        return (
            f"Label(tag={self.tag!r}, x={self.x}, y={self.y}, "
            f"text={self.text!r})"
        )
