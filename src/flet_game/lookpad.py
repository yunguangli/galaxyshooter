"""
lookpad.py — LookPad: relative drag-to-look trackpad for right-thumb input.

Step 13 of the flet_game engine.

``LookPad`` covers a rectangular touch zone and tracks the cumulative
horizontal drag since the last game-loop frame.  Call ``consume_dx()`` once
per frame to get the accumulated pixels; multiply by a sensitivity constant
to convert to radians.  Double-tapping toggles ADS (Aim Down Sights) mode.
Use ``control`` to place the transparent overlay in any ``ft.Stack``.

Usage::

    import math
    import flet as ft
    from flet_game import LookPad, Loop, Scene

    def main(page: ft.Page) -> None:
        scene  = Scene(page, width=390, height=500)
        loop   = Loop(page, fps=60)

        # Create the look trackpad — right half of a 780-px tall screen
        lookpad = LookPad(width=195, height=780)
        lookpad.control.left = 195   # position inside the parent Stack
        lookpad.control.top  = 0

        overlay_stack = ft.Stack(
            width=390, height=780,
            controls=[
                base_layout,        # Column / Stack with game view + dpad
                lookpad.control,    # transparent overlay on the right half
            ],
        )

        LOOK_SENSITIVITY = 0.008   # radians per pixel of drag

        @loop.on_update
        def update(dt: float) -> None:
            # Drag pixels → rotation radians (already per-frame, no × dt)
            rotation_delta = lookpad.consume_dx() * LOOK_SENSITIVITY

            fov = 30.0 if lookpad.ads else 66.0   # ADS zoom
            ...

        scene.mount()
        page.controls.append(overlay_stack)
        page.update()
        loop.start()

    ft.run(main)
"""

from __future__ import annotations

import flet as ft


class LookPad:
    """Relative drag-to-look trackpad for right-thumb FPS input.

    Accumulates horizontal drag pixels between game-loop frames so the
    camera rotates smoothly regardless of gesture event timing.  A
    double-tap toggles ADS (Aim Down Sights) mode.

    Unlike a joystick, there is no "centre" — dragging anywhere in the zone
    rotates the camera relative to where the finger started.

    Parameters
    ----------
    width : float
        Width of the touch zone in px (typically half the screen width).
    height : float
        Height of the touch zone in px (typically the full screen height).

    Notes
    -----
    Set ``control.left`` and ``control.top`` before adding to a parent Stack
    to position the overlay over the desired screen region.

    Example
    -------
    .. code-block:: python

        lookpad = LookPad(width=195, height=780)
        lookpad.control.left = 195   # right half of a 390-px wide screen
        lookpad.control.top  = 0

        # In update():
        angle += lookpad.consume_dx() * 0.008   # 0.008 rad/px (fast)
        fov    = 30.0 if lookpad.ads else 66.0
    """

    def __init__(self, width: float, height: float) -> None:
        self._width  = float(width)
        self._height = float(height)
        self._dx: float = 0.0
        self._ads: bool = False

        self._gd = ft.GestureDetector(
            width=self._width,
            height=self._height,
            on_pan_update=self._on_pan_update,
            on_double_tap=self._on_double_tap,
            content=ft.Container(
                width=self._width,
                height=self._height,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def ads(self) -> bool:
        """True while Aim Down Sights (double-tap toggle) is active."""
        return self._ads

    @property
    def control(self) -> ft.GestureDetector:
        """The transparent ``ft.GestureDetector`` to overlay in a ``ft.Stack``.

        Set ``control.left`` and ``control.top`` to position the touch zone
        before adding to the parent Stack.
        """
        return self._gd

    def consume_dx(self) -> float:
        """Return accumulated horizontal drag in px since the last call, then reset.

        Call exactly once per game-loop frame.  Positive = dragged right
        (turn right); negative = dragged left.  Multiply by a sensitivity
        constant to convert px → radians::

            angle += lookpad.consume_dx() * 0.008   # 0.008 rad/px
        """
        v = self._dx
        self._dx = 0.0
        return v

    def reset(self) -> None:
        """Clear accumulated drag and exit ADS (e.g. on pause or scene switch)."""
        self._dx  = 0.0
        self._ads = False

    # ── Internal handlers ─────────────────────────────────────────────────────

    def _on_pan_update(self, e: ft.DragUpdateEvent) -> None:
        self._dx += e.local_delta.x

    def _on_double_tap(self, _e) -> None:
        self._ads = not self._ads
