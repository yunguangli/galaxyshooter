"""
gameview.py — GameView: responsive scaling wrapper for fixed-design-size games.

``GameView`` takes a ``Scene`` built for a fixed design resolution (e.g. 390×780)
and scales it uniformly to fill any screen — portrait phone, tablet, desktop, or
landscape.

The outer container is sized to the *scaled* game area (not the design size), so
no black bars appear between the game content and the container border.  Page-level
alignment centres the game on screen; ``bgcolor`` fills the letterbox bars.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from .scene import Scene


class GameView:
    def __init__(
        self,
        scene: Scene,
        mode: str = "fit",
        bgcolor: str = ft.Colors.BLACK,
    ) -> None:
        self._scene = scene
        self._mode = mode
        self._bgcolor = bgcolor
        self._sx = 1.0
        self._sy = 1.0
        self._mounted = False

        self._outer = ft.Container(
            content=scene._mount_ctrl,
            expand=True,
            bgcolor=bgcolor,
            alignment=ft.Alignment.CENTER,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def scene(self) -> Scene:
        return self._scene

    @property
    def scale_x(self) -> float:
        return self._sx

    @property
    def scale_y(self) -> float:
        return self._sy

    def layout(self, e=None) -> None:
        sx, sy = self._calc()
        if sx == self._sx and sy == self._sy:
            return
        self._sx, self._sy = sx, sy
        self._scene.root.scale = ft.Scale(scale_x=sx, scale_y=sy)
        if self._mounted:
            self._scene.root.update()

    def mount(self) -> None:
        if self._mounted:
            return
        page = self._scene._page
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER

        _prev = getattr(page, "on_resized", None)

        def _on_resized(e):
            self.layout(e)
            if callable(_prev):
                _prev(e)

        page.on_resized = _on_resized

        self._scene.mount()
        try:
            page.controls.remove(self._scene._mount_ctrl)
        except ValueError:
            pass
        page.controls.append(self._outer)
        self._mounted = True
        page.update()
        self.layout()

    def unmount(self) -> None:
        if not self._mounted:
            return
        page = self._scene._page
        try:
            page.controls.remove(self._outer)
        except ValueError:
            pass
        self._scene._mounted = True
        self._scene.unmount()
        self._mounted = False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _calc(self) -> tuple[float, float]:
        page = self._scene._page
        dw = self._scene._width
        dh = self._scene._height

        pw: float = page.width or 0.0
        ph: float = page.height or 0.0
        if pw <= 0:
            pw = float(getattr(getattr(page, "window", None), "width", None) or dw)
        if ph <= 0:
            ph = float(getattr(getattr(page, "window", None), "height", None) or dh)

        if self._mode == "fill":
            s = max(pw / dw, ph / dh)
        elif self._mode == "stretch":
            return pw / dw, ph / dh
        else:
            s = min(pw / dw, ph / dh)
        return s, s