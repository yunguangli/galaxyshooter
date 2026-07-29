"""
particles.py — SplashEffect: visual particle effects for flet_game.

No extra packages required for programmatic effects — uses Flet's built-in
implicit animation system.  Optional Lottie / Rive support requires the
corresponding packages:

    pip install flet-lottie   # for .json / .lottie animations
    pip install flet-rive     # for .riv animations

``SplashEffect`` provides three kinds of effects on any ``ft.Stack`` canvas:

* :meth:`ring` — Expanding, fading circle outline.  Impact flashes.
* :meth:`burst` — N dots fly outward while fading.  Explosions / pickups.
* :meth:`animate` — Play a GIF, Lottie, or Rive animation file at a
  position.  Auto-removed after *duration* ms.

All methods are **fire-and-forget** (sync) and clean up after themselves.

Usage::

    from flet_game import SplashEffect

    canvas = ft.Stack(width=800, height=600)
    fx = SplashEffect(page, canvas)

    # Programmatic effects (no files needed):
    fx.ring(cx, cy, color="#ff2222", radius=26, duration=400)
    fx.burst(cx, cy, color="#ff8800", count=10, distance=48, duration=420)

    # File-based animations:
    fx.animate(cx, cy, src="effects/explode.json",  width=80, height=80, duration=800)
    fx.animate(cx, cy, src="effects/sparkle.gif",   width=64, height=64, loop=True, duration=1200)
    fx.animate(cx, cy, src="effects/hit.riv",       width=60, height=60, duration=600)
"""

from __future__ import annotations

import asyncio
import math
import os

import flet as ft

from ._colors import _resolve_color

# ── Optional animation package imports ────────────────────────────────────────

try:
    import flet_lottie as _ftl
    _LOTTIE_AVAILABLE = True
except ImportError:
    _ftl = None  # type: ignore[assignment]
    _LOTTIE_AVAILABLE = False

try:
    import flet_rive as _ftr
    _RIVE_AVAILABLE = True
except ImportError:
    _ftr = None  # type: ignore[assignment]
    _RIVE_AVAILABLE = False

# Extension → animation kind
_KIND_MAP: dict[str, str] = {
    ".gif":    "gif",
    ".png":    "gif",   # static PNG via ft.Image
    ".json":   "lottie",
    ".lottie": "lottie",
    ".riv":    "rive",
}


class SplashEffect:
    """
    Short-lived visual effects drawn on a canvas (``ft.Stack``).

    Parameters
    ----------
    page
        The Flet ``Page`` (used to schedule async cleanup tasks via
        ``page.run_task`` and to call ``page.update()``).
    canvas
        The ``ft.Stack`` that acts as the game canvas.  Particle controls
        are appended to and later removed from ``canvas.controls``.
    """

    def __init__(
        self,
        page: ft.Page,
        canvas: ft.Stack,
        max_concurrent: int = 16,
    ) -> None:
        self._page = page
        self._canvas = canvas
        self._max_concurrent = max_concurrent
        self._active_count = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def ring(
        self,
        x: float,
        y: float,
        color: str = "#ffffff",
        radius: float = 24,
        thickness: int = 3,
        duration: int = 350,
    ) -> None:
        """Show an expanding, fading ring centered at *(x, y)*.

        Parameters
        ----------
        x, y
            Centre of the ring in canvas coordinates.
        color
            Ring border colour (CSS name, ``"#rrggbb"``, or ``ft.Colors.*``).
        radius
            Initial radius in pixels.  The ring expands to ~2.5× this.
        thickness
            Border width in pixels.
        duration
            Animation duration in milliseconds.
        """
        if self._active_count >= self._max_concurrent:
            return
        self._active_count += 1
        self._page.run_task(
            self._do_ring, x, y, color, radius, thickness, duration
        )

    def burst(
        self,
        x: float,
        y: float,
        color: str = "#ffffff",
        count: int = 8,
        distance: float = 36,
        size: int = 8,
        duration: int = 400,
    ) -> None:
        """Show *count* small dots flying outward from *(x, y)*.

        Parameters
        ----------
        x, y
            Origin of the burst in canvas coordinates.
        color
            Particle colour (CSS name, ``"#rrggbb"``, or ``ft.Colors.*``).
        count
            Number of particles.
        distance
            How far each particle travels (pixels).
        size
            Diameter of each particle dot (pixels).
        duration
            Animation duration in milliseconds.
        """
        if self._active_count >= self._max_concurrent:
            return
        self._active_count += 1
        self._page.run_task(
            self._do_burst, x, y, color, count, distance, size, duration
        )

    # ── Internal async workers ────────────────────────────────────────────────

    async def _do_ring(
        self,
        x: float,
        y: float,
        color: str,
        radius: float,
        thickness: int,
        duration: int,
    ) -> None:
        resolved = _resolve_color(color)
        steps = max(8, duration // 25)       # ~25 ms per step
        step_dt = (duration / 1000) / steps
        r0, r1 = radius, radius * 2.5

        ring = ft.Container(
            width=r0 * 2,
            height=r0 * 2,
            left=x - r0,
            top=y - r0,
            border_radius=ft.BorderRadius.all(r0),
            border=ft.Border.all(thickness, resolved),
            opacity=1.0,
        )
        self._canvas.controls.append(ring)
        # Per-step flushes target the canvas subtree (canvas.update()) instead
        # of the whole page (page.update()).  Each step still mutates the ring
        # container; Flet's per-control .update() sends only the ring's delta,
        # avoiding the full-page WebSocket diff that interleaves with the
        # GameLoop's own end-of-frame page.update().
        try:
            self._canvas.update()      # render ring at initial size
            for step in range(1, steps + 1):
                t = step / steps
                t_ease = 1.0 - (1.0 - t) ** 2   # ease-out quad
                r = r0 + (r1 - r0) * t_ease
                ring.width  = r * 2
                ring.height = r * 2
                ring.left   = x - r
                ring.top    = y - r
                ring.border_radius = ft.BorderRadius.all(r)
                ring.opacity = 1.0 - t
                ring.update()
                await asyncio.sleep(step_dt)
            if ring in self._canvas.controls:
                self._canvas.controls.remove(ring)
            self._canvas.update()
        except RuntimeError:
            pass  # page session destroyed — silently exit
        finally:
            self._active_count = max(0, self._active_count - 1)

    async def _do_burst(
        self,
        x: float,
        y: float,
        color: str,
        count: int,
        distance: float,
        size: int,
        duration: int,
    ) -> None:
        resolved = _resolve_color(color)
        half = size / 2
        steps = max(8, duration // 25)       # ~25 ms per step
        step_dt = (duration / 1000) / steps
        angles = [2 * math.pi * i / count for i in range(count)]

        particles: list[tuple[ft.Container, float]] = []
        for angle in angles:
            p = ft.Container(
                width=size,
                height=size,
                border_radius=ft.BorderRadius.all(half),
                bgcolor=resolved,
                left=x - half,
                top=y - half,
                opacity=1.0,
            )
            self._canvas.controls.append(p)
            particles.append((p, angle))

        try:
            self._canvas.update()     # show particles at origin
            for step in range(1, steps + 1):
                t = step / steps
                t_ease = 1.0 - (1.0 - t) ** 2  # ease-out quad
                for p, angle in particles:
                    p.left    = x - half + math.cos(angle) * distance * t_ease
                    p.top     = y - half + math.sin(angle) * distance * t_ease
                    p.opacity = 1.0 - t
                # Flush the canvas subtree once per step (not per particle,
                # not the whole page).  All particle mutations above are
                # batched into this single canvas-subtree diff.
                self._canvas.update()
                await asyncio.sleep(step_dt)
            for p, _ in particles:
                if p in self._canvas.controls:
                    self._canvas.controls.remove(p)
            self._canvas.update()
        except RuntimeError:
            pass  # page session destroyed — silently exit
        finally:
            self._active_count = max(0, self._active_count - 1)

    # ── File-based animation ────────────────────────────────────────────────────

    def animate(
        self,
        x: float,
        y: float,
        src: str,
        width: float = 80,
        height: float = 80,
        duration: int | None = 800,
        kind: str = "auto",
        loop: bool = False,
        speed: float = 1.0,
    ) -> None:
        """Play a GIF, Lottie, or Rive animation centred at *(x, y)*.

        The animation control is added to the canvas and automatically removed
        after *duration* milliseconds.  Pass ``duration=None`` to keep it until
        you remove it manually.

        Parameters
        ----------
        x, y
            Centre of the animation in canvas coordinates.
        src
            File path (asset-relative or absolute) or URL.

            * **GIF / PNG** — ``"effects/explode.gif"``  (built-in ``ft.Image``)
            * **Lottie** — ``"effects/hit.json"``        (requires ``flet-lottie``)
            * **Rive** — ``"effects/spark.riv"``          (requires ``flet-rive``)
        width, height
            Size of the animation in pixels.
        duration
            Milliseconds before the control is removed from the canvas.
            ``None`` disables auto-removal (you manage the lifecycle).
        kind
            ``"auto"`` detects from the file extension.  Explicit values:
            ``"gif"``, ``"lottie"``, ``"rive"``.
        loop
            Whether the animation should loop (GIF and Lottie only;
            Rive loops by default based on its artboard settings).
        speed
            Playback speed multiplier for Rive (``1.0`` = normal).

        Raises
        ------
        ImportError
            If the required package (``flet-lottie`` / ``flet-rive``) is
            not installed when *kind* is ``"lottie"`` / ``"rive"``.
        ValueError
            If the file extension is unknown and *kind* is ``"auto"``.
        """
        if self._active_count >= self._max_concurrent:
            return
        self._active_count += 1
        self._page.run_task(
            self._do_animate, x, y, src, width, height, duration, kind, loop, speed
        )

    async def _do_animate(
        self,
        x: float,
        y: float,
        src: str,
        width: float,
        height: float,
        duration: int | None,
        kind: str,
        loop: bool,
        speed: float,
    ) -> None:
        resolved_kind = _resolve_kind(src, kind)
        try:
            content = _make_anim_control(src, width, height, loop, speed, resolved_kind)
        except (ImportError, ValueError):
            self._active_count = max(0, self._active_count - 1)
            raise  # propagate — don't silently swallow config errors

        wrapper = ft.Container(
            content=content,
            left=x - width / 2,
            top=y - height / 2,
            width=width,
            height=height,
        )
        self._canvas.controls.append(wrapper)
        try:
            self._page.update()
            if duration is not None:
                await asyncio.sleep(duration / 1000)
                if wrapper in self._canvas.controls:
                    self._canvas.controls.remove(wrapper)
                self._page.update()
        except RuntimeError:
            pass  # page destroyed — silently exit
        finally:
            self._active_count = max(0, self._active_count - 1)


# ───────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ───────────────────────────────────────────────────────────────────────────

def _resolve_kind(src: str, kind: str) -> str:
    """Return the concrete kind string for *src*, resolving ``"auto"``."""
    if kind != "auto":
        return kind
    ext = os.path.splitext(src.split("?")[0])[-1].lower()  # strip query strings
    if ext not in _KIND_MAP:
        raise ValueError(
            f"Cannot detect animation kind from extension {ext!r}.  "
            "Pass kind='gif', 'lottie', or 'rive' explicitly."
        )
    return _KIND_MAP[ext]


def _make_anim_control(
    src: str,
    width: float,
    height: float,
    loop: bool,
    speed: float,
    kind: str,
) -> ft.Control:
    """Return the appropriate Flet control for the given animation *kind*."""
    if kind == "gif" or kind == "png":
        return ft.Image(
            src=src,
            width=width,
            height=height,
            fit=ft.BoxFit.CONTAIN,
            repeat=ft.ImageRepeat.REPEAT if loop else ft.ImageRepeat.NO_REPEAT,
        )

    if kind == "lottie":
        if not _LOTTIE_AVAILABLE:
            raise ImportError(
                "flet-lottie is not installed.\n"
                "Install it with:  pip install flet-lottie"
            )
        return _ftl.Lottie(
            src=src,
            width=width,
            height=height,
            animate=True,
            repeat=loop,
            fit=ft.BoxFit.CONTAIN,
        )

    if kind == "rive":
        if not _RIVE_AVAILABLE:
            raise ImportError(
                "flet-rive is not installed.\n"
                "Install it with:  pip install flet-rive"
            )
        return _ftr.Rive(
            src=src,
            width=width,
            height=height,
            fit=ft.BoxFit.CONTAIN,
            speed_multiplier=speed,
        )

    raise ValueError(f"Unknown animation kind: {kind!r}")
