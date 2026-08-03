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
        page_sized: bool = False,
        safe_area: bool = False,
    ) -> None:
        self._scene = scene
        self._mode = mode
        self._bgcolor = bgcolor
        self._page_sized = page_sized
        self._safe_area = safe_area
        self._sx = 1.0
        self._sy = 1.0
        self._mounted = False

        inner = ft.Container(
            content=scene._mount_ctrl,
            expand=True,
            bgcolor=bgcolor,
            alignment=ft.Alignment.CENTER,
        )
        if safe_area:
            # Whole app inside one SafeArea: system chrome (notch, status bar,
            # home indicator / gesture nav) insets the content, and because the
            # scene is sized to the *safe* area (see _page_design_size) nothing
            # is clipped — the game still fills the entire screen.
            self._outer: ft.Control = ft.SafeArea(
                content=inner,
                expand=True,
                avoid_intrusions_top=True,
                avoid_intrusions_bottom=True,
                avoid_intrusions_left=True,
                avoid_intrusions_right=True,
            )
        else:
            self._outer = inner

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
        if self._page_sized:
            page = self._scene._page
            pw, ph = self._page_design_size(page)
            dw, dh = self._scene._width, self._scene._height
            if abs(pw - dw) < 1.0 and abs(ph - dh) < 1.0:
                return  # design already matches the page → 1:1, nothing to do
            # A real resize after mount: DO NOT hard-resize the scene (its
            # children are absolutely positioned and would not move, pushing
            # them off-screen). Instead uniformly fit-scale the fixed design
            # — everything stays centred and visible, nothing is clipped.
            s = min(pw / dw, ph / dh) if dw > 0 and dh > 0 else 1.0
            if abs(s - self._sx) < 1e-4 and abs(s - self._sy) < 1e-4:
                return
            self._sx = self._sy = s
            self._scene.root.scale = ft.Scale(scale_x=s, scale_y=s)
            if self._mounted:
                self._scene.root.update()
            return
        sx, sy = self._calc()
        if sx == self._sx and sy == self._sy:
            return
        self._sx, self._sy = sx, sy
        self._scene.root.scale = ft.Scale(scale_x=sx, scale_y=sy)
        if self._mounted:
            self._scene.root.update()

    def _safe_insets(self, page) -> tuple[float, float, float, float]:
        """Return the system safe-area insets (left, top, right, bottom).

        On desktop these are all 0; on mobile they are the MediaQuery padding
        (status bar / notch / home indicator / gesture nav bar).
        """
        try:
            pad = page.padding
        except Exception:
            pad = None
        if pad is None:
            return 0.0, 0.0, 0.0, 0.0

        def num(v, default=0.0) -> float:
            try:
                f = float(v)
                return f if f > 0 else default
            except (TypeError, ValueError):
                return default

        if isinstance(pad, (int, float)):
            return num(pad), num(pad), num(pad), num(pad)
        return (
            num(getattr(pad, "left", 0)),
            num(getattr(pad, "top", 0)),
            num(getattr(pad, "right", 0)),
            num(getattr(pad, "bottom", 0)),
        )

    def _page_design_size(self, page) -> tuple[float, float]:
        """Design size = page size MINUS safe-area insets.

        The scene is resized to this so it exactly fills the SafeArea box (no
        letterboxing, no clipping of the bottom controls) while still using
        every available pixel.
        """
        pw = ph = 0.0
        try:
            pw = float(page.width or 0.0)
            ph = float(page.height or 0.0)
        except (TypeError, ValueError):
            pw = ph = 0.0
        if pw <= 0:
            pw = float(getattr(getattr(page, "window", None), "width", None)
                       or self._scene._width)
        if ph <= 0:
            ph = float(getattr(getattr(page, "window", None), "height", None)
                       or self._scene._height)
        if self._safe_area or self._page_sized:
            l, t, r, b = self._safe_insets(page)
            pw = max(1.0, pw - l - r)
            ph = max(1.0, ph - t - b)
        return pw, ph

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

        if self._page_sized:
            # Make the game canvas exactly the safe page size (no
            # letterboxing) — the scene must build its objects off
            # self.width / self.height, which then match the real screen.
            pw, ph = self._page_design_size(page)
            self._scene.resize(pw, ph)

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
        if self._page_sized:
            # Design size already equals the (safe) page size → 1:1.
            return 1.0, 1.0
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