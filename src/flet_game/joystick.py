"""
joystick.py — VirtualJoystick: reusable on-screen analogue stick widget.

Prefer mounting via ``scene.add_overlay(joystick.control)`` so the stick's
GestureDetector is not nested inside the scene InputManager wrap.

Read ``vx`` / ``vy`` each frame for -1..+1 axes (dead-zone filtered).
Read ``._vx`` / ``._vy`` for raw unfiltered values.

Design note: the stick is anchored at the CENTER of the touch zone, not at
the touch point.  This means on_pan_down (which fires immediately, before
Flutter's 18px touch slop) can compute axes from the initial touch position
relative to the center — giving instant direction response without waiting
for on_pan_update.
"""

from __future__ import annotations

import math
import time

import flet as ft


class VirtualJoystick:
    """Fixed-center on-screen analogue joystick for touch / mouse-drag input."""

    def __init__(
        self,
        width: float,
        height: float,
        *,
        base_radius: float = 60.0,
        knob_radius: float = 28.0,
        max_displacement: float = 52.0,
        dead_zone: float = 0.08,
        base_color: str = "#ffffff0c",
        base_border_color: str = "#ffffff40",
        knob_color: str = "#ffffff66",
        guide_border_color: str = "#ffffff12",
        drag_interval: int = 16,
        refresh_rate: float = 30.0,
    ) -> None:
        self._width = float(width)
        self._height = float(height)
        self._base_r = float(base_radius)
        self._knob_r = float(knob_radius)
        self._max_r = float(max_displacement)
        self._dead = float(dead_zone)
        self._drag_interval = int(drag_interval)
        self._refresh_min_interval: float = 1.0 / max(1.0, float(refresh_rate))
        self._last_refresh: float = 0.0

        self._vx: float = 0.0
        self._vy: float = 0.0
        self._held: bool = False
        self._visual_dirty: bool = False
        self._allow_flush: bool = False

        # Anchor = center of the zone (fixed, not at touch point)
        self._cx_zone = self._width / 2.0
        self._cy_zone = self._height / 2.0

        self._guide = ft.Container(
            left=self._cx_zone - self._base_r,
            top=self._cy_zone - self._base_r,
            width=self._base_r * 2,
            height=self._base_r * 2,
            border_radius=ft.BorderRadius.all(self._base_r),
            border=ft.Border.all(1, guide_border_color),
        )
        self._base = ft.Container(
            visible=False,
            left=self._cx_zone - self._base_r,
            top=self._cy_zone - self._base_r,
            width=self._base_r * 2,
            height=self._base_r * 2,
            border_radius=ft.BorderRadius.all(self._base_r),
            bgcolor=base_color,
            border=ft.Border.all(2, base_border_color),
        )
        self._knob = ft.Container(
            visible=False,
            width=self._knob_r * 2,
            height=self._knob_r * 2,
            border_radius=ft.BorderRadius.all(self._knob_r),
            bgcolor=knob_color,
        )

        _gd = ft.GestureDetector(
            left=0,
            top=0,
            width=self._width,
            height=self._height,
            drag_interval=self._drag_interval,
            mouse_cursor=ft.MouseCursor.BASIC,
            on_pan_down=self._on_down,
            on_pan_start=self._on_start,
            on_pan_update=self._on_update,
            on_pan_end=self._on_end,
            on_pan_cancel=self._on_end,
            content=ft.Container(
                width=self._width,
                height=self._height,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
        )

        self._control = ft.Stack(
            width=self._width,
            height=self._height,
            controls=[self._guide, self._base, self._knob, _gd],
        )

    @property
    def held(self) -> bool:
        return self._held

    @property
    def vx(self) -> float:
        return 0.0 if abs(self._vx) < self._dead else self._vx

    @property
    def vy(self) -> float:
        return 0.0 if abs(self._vy) < self._dead else self._vy

    @property
    def control(self) -> ft.Stack:
        return self._control

    def reset(self) -> None:
        self._on_end(None)

    def flush_visual(self) -> None:
        """Push geometry from the game loop (not the pan handler)."""
        now = time.monotonic()
        if self._allow_flush:
            do = True
        elif self._held and self._visual_dirty:
            do = (now - self._last_refresh) >= max(self._refresh_min_interval, 1.0 / 15.0)
        else:
            do = False
        if not do:
            return
        self._visual_dirty = False
        self._allow_flush = False
        self._last_refresh = now
        try:
            self._control.update()
        except (AttributeError, RuntimeError):
            pass

    def _schedule_refresh(self, *, force: bool = False) -> None:
        self._visual_dirty = True
        if not force:
            return
        self._allow_flush = True
        try:
            from .loop import batch_active
            if batch_active():
                return
        except ImportError:
            pass
        self.flush_visual()

    def _apply_axes(self, px: float, py: float) -> None:
        """Compute axes from pointer position relative to the zone CENTER."""
        dx = px - self._cx_zone
        dy = py - self._cy_zone
        dist = math.hypot(dx, dy)
        if dist > self._max_r:
            scale = self._max_r / dist
            dx *= scale
            dy *= scale
        self._vx = dx / self._max_r
        self._vy = dy / self._max_r
        self._knob.left = self._cx_zone + dx - self._knob_r
        self._knob.top = self._cy_zone + dy - self._knob_r
        self._visual_dirty = True

    def _on_down(self, e) -> None:
        """Fires immediately on touch (before 18px slop).

        Anchor at the CENTER and compute axes from the touch position.
        This gives instant direction without waiting for on_pan_update.
        """
        pos = getattr(e, "local_position", None)
        if pos is None:
            return
        self._held = True
        self._apply_axes(float(pos.x), float(pos.y))
        self._base.visible = self._knob.visible = True
        self._schedule_refresh(force=True)

    def _on_start(self, e: ft.DragStartEvent) -> None:
        self._held = True
        self._base.visible = self._knob.visible = True
        self._schedule_refresh(force=True)

    def _on_update(self, e: ft.DragUpdateEvent) -> None:
        pos = getattr(e, "local_position", None)
        if pos is not None:
            self._apply_axes(float(pos.x), float(pos.y))
            return
        delta = getattr(e, "local_delta", None)
        if delta is None:
            return
        self._apply_axes(self._cx_zone + float(delta.x), self._cy_zone + float(delta.y))

    def _on_end(self, _e) -> None:
        self._held = False
        self._vx = self._vy = 0.0
        self._base.visible = self._knob.visible = False
        self._schedule_refresh(force=True)
