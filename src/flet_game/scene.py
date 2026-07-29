"""
scene.py — Scene: canvas container and object manager for flet_game.

``Scene`` owns a ``ft.Stack`` canvas and an ``InputManager``, manages the
lifetime of :class:`~flet_game.Sprite` / :class:`~flet_game.Label` / raw
``ft.Control`` objects, and exposes a clean mount / unmount lifecycle.

It eliminates the per-test boilerplate of creating a canvas, wiring
keyboard/mouse input, managing a background container, and adding every
sprite control to the page by hand.

Usage — plain::

    scene = Scene(page, width=800, height=600, bgcolor="#111122")

    player = Sprite(x=80, y=200, width=40, height=40, color="blue", tag="player")
    score  = Label(text="Score: 0", x=10, y=8, color="white", size=16)

    scene.add(player)           # z=0 — game objects layer
    scene.add(score, z=10)      # z=10 — HUD layer (drawn on top)
    scene.add_overlay(joy.control, z=20)  # touch widgets (own GestureDetector)

    # Grab pre-wired helpers:
    inp = scene.input            # InputManager
    fx  = SplashEffect(page, scene.canvas)

    scene.mount()               # adds the scene to the page, calls on_enter()
    loop.start()

Usage — subclass::

    class GameScene(Scene):
        def on_enter(self):
            self.player = Sprite(x=80, y=200, width=40, height=40, color="blue")
            self.add(self.player)

        def on_exit(self):
            ...   # optional teardown

    scene = GameScene(page, width=800, height=600)
    scene.mount()
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .loop import GameLoop
import flet as ft

from .sprite import Sprite
from .label import Label
from .button import Button
from .input import InputManager
from ._colors import _resolve_color

# Hoisted to module level — used by _rebuild_canvas / _rebuild_overlay to
# detect mid-frame scene mutations and defer the page.update() to the loop's
# end-of-frame flush (see loop.py).
try:
    from .loop import batch_active as _batch_active
except ImportError:
    _batch_active = None

# A "game object" accepted by Scene.add / remove / clear.
_Obj = Union[Sprite, Label, Button, ft.Control]


class Scene:
    """Canvas container and object manager for a single game screen.

    Parameters
    ----------
    page
        The Flet ``Page``.
    width, height
        Canvas size in pixels.
    bgcolor
        Background colour (CSS hex, name, or ``ft.Colors.*``).
    clip
        Whether to clip children at the canvas boundary.
    safe_area
        Wrap the canvas in ``ft.SafeArea`` so game content avoids system
        chrome (status bar, notches, home indicator on iOS/Android).
        Defaults to ``False`` for backward compatibility.  Toggle at
        runtime via the ``scene.safe_area`` property.
    safe_area_top / safe_area_bottom / safe_area_left / safe_area_right
        Per-side control over which system insets are respected.  All
        default to ``True`` when ``safe_area=True``.
    """

    def __init__(
        self,
        page: ft.Page,
        width: float = 800,
        height: float = 600,
        bgcolor: str = ft.Colors.BLACK,
        clip: bool = True,
        safe_area: bool = False,
        safe_area_top: bool = True,
        safe_area_bottom: bool = True,
        safe_area_left: bool = True,
        safe_area_right: bool = True,
    ) -> None:
        self._page = page
        self._width = float(width)
        self._height = float(height)
        self._bgcolor = _resolve_color(bgcolor)
        self._mounted = False
        # True while the scene is in a Game stack but not on-screen.
        self._paused = False

        # GameLoop injected by Game._set_loop() so @self.on_update callbacks
        # can be registered and auto-removed without the user managing them.
        self._loop: GameLoop | None = None
        # Callbacks registered via @self.on_update — removed automatically
        # when the scene unmounts, so on_exit() needs no manual cleanup.
        self._managed_callbacks: list = []

        # When True, _rebuild_canvas() defers the rebuild and page.update()
        # until the caller exits the defer_rebuild() context.  This lets
        # add_many/remove_many batch mutations without N rebuilds.
        self._rebuild_deferred: int = 0

        # (z, obj, flet_control) — sorted ascending by z; objects at equal z
        # are drawn in insertion order.
        self._objects: list[tuple[int, _Obj, ft.Control]] = []
        # Overlay layer — sibling OF the InputManager GestureDetector so touch
        # widgets (VirtualJoystick, LookPad, etc.) are not nested inside it.
        # Nested GestureDetectors fight in Flutter's gesture arena and often
        # swallow pan events on mobile.
        self._overlay_objects: list[tuple[int, _Obj, ft.Control]] = []

        # Background fill — always the first child of the canvas.
        self._bg = ft.Container(
            width=self._width,
            height=self._height,
            bgcolor=self._bgcolor,
        )

        self._canvas = ft.Stack(
            width=self._width,
            height=self._height,
            controls=[self._bg],
            clip_behavior=(
                ft.ClipBehavior.HARD_EDGE if clip else ft.ClipBehavior.NONE
            ),
        )

        # InputManager auto-wraps the canvas so keyboard + mouse both work.
        # Fix the GestureDetector to the canvas width so that
        # page.horizontal_alignment = CENTER correctly centres the scene on
        # mobile (without a fixed width the GD expands to fill the page and
        # the Stack left-aligns inside it).
        self._input = InputManager(page)
        self._wrapped = self._input.wrap(self._canvas)
        self._wrapped.width  = self._width
        self._wrapped.height = self._height

        # Overlay stack sits on top of the input-wrapped canvas as a sibling.
        # GameView scales ``_root`` so both layers stay aligned.
        self._overlay = ft.Stack(
            width=self._width,
            height=self._height,
            controls=[],
            clip_behavior=ft.ClipBehavior.NONE,
        )
        self._root = ft.Stack(
            width=self._width,
            height=self._height,
            controls=[self._wrapped, self._overlay],
            clip_behavior=(
                ft.ClipBehavior.HARD_EDGE if clip else ft.ClipBehavior.NONE
            ),
        )

        # SafeArea state — stored before _build_mount_ctrl() is called.
        self._sa_enabled = safe_area
        self._sa_top     = safe_area_top
        self._sa_bottom  = safe_area_bottom
        self._sa_left    = safe_area_left
        self._sa_right   = safe_area_right
        self._build_mount_ctrl()

    # ── SafeArea ──────────────────────────────────────────────────────────────

    def _build_mount_ctrl(self) -> None:
        """Build (or rebuild) ``self._mount_ctrl`` — the control added to the page.

        When ``safe_area=True`` the root stack is wrapped in ``ft.SafeArea`` so
        game content avoids system chrome (status bar, notches, home
        indicator).  Horizontal centering on wide screens is still handled by
        ``page.horizontal_alignment = CENTER`` as before.

        When ``safe_area=False`` (default) ``_mount_ctrl`` is the root stack
        (input-wrapped canvas + overlay).
        """
        if self._sa_enabled:
            self._mount_ctrl: ft.Control = ft.SafeArea(
                content=self._root,
                avoid_intrusions_top=self._sa_top,
                avoid_intrusions_bottom=self._sa_bottom,
                avoid_intrusions_left=self._sa_left,
                avoid_intrusions_right=self._sa_right,
            )
        else:
            self._mount_ctrl = self._root

    @property
    def safe_area(self) -> bool:
        """Whether the canvas is wrapped in a system-chrome-aware ``ft.SafeArea``."""
        return self._sa_enabled

    @safe_area.setter
    def safe_area(self, value: bool) -> None:
        """Toggle SafeArea wrapping at runtime.  Re-mounts live if already mounted."""
        if value == self._sa_enabled:
            return
        self._sa_enabled = value
        was_mounted = self._mounted
        if was_mounted:
            try:
                self._page.controls.remove(self._mount_ctrl)
            except ValueError:
                pass
        self._build_mount_ctrl()
        if was_mounted:
            self._page.controls.append(self._mount_ctrl)
            self._page.update()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _set_loop(self, loop: GameLoop) -> None:  # type: ignore[name-defined]
        """Connect this scene to the shared GameLoop. Called by ``Game`` before mount.

        After this call ``@self.on_update`` callbacks are registered with the
        real loop immediately.  Any callbacks queued before this call (e.g.
        declared in ``__init__``) are registered here.
        """
        self._loop = loop
        loop.register_input(self._input)
        for fn in self._managed_callbacks:
            loop.add_callback(fn)

    def on_update(self, fn):
        """Decorator — register a per-frame callback scoped to this scene.

        The callback is added to the game loop automatically and removed when
        the scene unmounts — no manual ``remove_callback`` needed in
        ``on_exit``.

        Call this inside :meth:`on_enter` so each mount creates a fresh
        registration::

            class GameScene(Scene):
                def on_enter(self):
                    self.player = Sprite(x=80, y=200, width=40, height=40)
                    self.add(self.player)

                    @self.on_update
                    def update(dt: float) -> None:
                        self.player.x += 200 * dt

        *fn* receives a single ``dt`` argument (seconds since last frame).
        Both plain ``def`` and ``async def`` are accepted.
        """
        self._managed_callbacks.append(fn)
        if self._loop is not None:
            self._loop.add_callback(fn)
        return fn

    def mount(self) -> None:
        """Add this scene to the page and call :meth:`on_enter`.

        Call once after setup.  Any objects added before ``mount()`` are
        included in the first render.
        """
        if self._mounted:
            return
        # Re-register the keyboard handler.  This is necessary when the scene
        # was instantiated before a previous scene was destroyed — Python
        # evaluates function arguments before the call, so the new scene's
        # InputManager may register page.on_keyboard_event only to have it
        # overwritten moments later by the old scene's inp.destroy().
        self._input.activate()
        self._page.controls.append(self._mount_ctrl)
        self._page.update()
        self._mounted = True
        self.on_enter()

    def unmount(self) -> None:
        """Call :meth:`on_exit`, remove from page, and release resources.

        Stop any :class:`~flet_game.GameLoop` *before* calling this.
        """
        if not self._mounted:
            return
        # Auto-remove all @self.on_update callbacks from the loop before
        # calling on_exit() so the user doesn't have to do it manually.
        self._deregister_callbacks()
        if self._loop is not None:
            self._loop.unregister_input(self._input)
        self.on_exit()
        self._input.destroy()
        try:
            self._page.controls.remove(self._mount_ctrl)
        except ValueError:
            pass
        self._page.update()
        self._mounted = False

    def on_enter(self) -> None:
        """Called after :meth:`mount`.  Override in subclasses to set up the scene."""

    def on_exit(self) -> None:
        """Called before :meth:`unmount`.  Override in subclasses for teardown."""

    # ── Stack helpers (used by Game) ───────────────────────────────────────────

    def _pause(self) -> None:
        """Visually suspend without full teardown.  Used by Game.push_scene.

        The scene's sprites, labels, and registered input callbacks are kept
        alive; only the canvas widget is removed from the page.  Keyboard
        processing is silenced so the hidden scene cannot intercept events.
        ``on_exit`` is NOT called — use :meth:`unmount` for a full teardown.
        """
        if not self._mounted:
            return
        self._input.deactivate()
        try:
            self._page.controls.remove(self._mount_ctrl)
        except ValueError:
            pass
        self._page.update()
        self._mounted = False
        self._paused = True

    def _resume(self) -> None:
        """Restore a previously paused scene.  Used by Game.pop_scene.

        Re-adds the canvas to the page and re-activates the keyboard handler.
        ``on_enter`` is NOT called — the scene is continued, not restarted.
        """
        if not self._paused:
            return
        self._page.controls.append(self._mount_ctrl)
        self._page.update()
        self._mounted = True
        self._paused = False
        self._input.activate()

    def _destroy(self) -> None:
        """Full cleanup whether the scene is mounted, paused, or neither.
        Used by Game when clearing the scene stack.
        """
        if self._mounted:
            self.unmount()  # unmount already calls _deregister_callbacks
        elif self._paused:
            self._deregister_callbacks()
            self.on_exit()
            self._input.destroy()
            self._paused = False

    # ── Callback-cleanup helper ───────────────────────────────────────────────

    def _deregister_callbacks(self) -> None:
        """Remove all managed callbacks from the loop and clear the list."""
        if self._loop is not None:
            for fn in self._managed_callbacks:
                self._loop.remove_callback(fn)
        self._managed_callbacks.clear()

    # ── Game-object management ────────────────────────────────────────────────

    def add(self, obj: _Obj, z: int = 0, *, overlay: bool = False) -> None:
        """Add a Sprite, Label, or ``ft.Control`` to the scene.

        Parameters
        ----------
        obj
            The object to add.  Sprites and Labels expose a ``.control``
            attribute; raw ``ft.Control`` instances are added directly.
        z
            Draw order layer.  Lower z values are drawn behind higher ones.
            Objects at the same z are drawn in insertion order.
            Typical convention: ``z=0`` for game objects, ``z=10`` for HUD.
        overlay
            If ``True``, place the control on the overlay stack (a sibling
            *above* the scene's InputManager ``GestureDetector``).  Use this
            for ``VirtualJoystick``, ``LookPad``, and any other touch widget
            that owns its own ``GestureDetector`` — nesting those inside the
            scene GD breaks pan gestures on mobile.
        """
        if overlay:
            self.add_overlay(obj, z=z)
            return
        ctrl = _to_control(obj)
        insert_idx = len(self._objects)
        for i, (oz, _, _) in enumerate(self._objects):
            if oz > z:
                insert_idx = i
                break
        self._objects.insert(insert_idx, (z, obj, ctrl))
        self._rebuild_canvas()

    def add_overlay(self, obj: _Obj, z: int = 0) -> None:
        """Add a control to the gesture-safe overlay layer above the game canvas.

        Overlay controls are **not** nested inside the scene InputManager
        ``GestureDetector``.  Prefer this for on-screen joysticks and pads::

            joy = VirtualJoystick(width=160, height=160)
            joy.control.left = 10
            joy.control.top = scene.height - 170
            scene.add_overlay(joy.control, z=20)
        """
        ctrl = _to_control(obj)
        insert_idx = len(self._overlay_objects)
        for i, (oz, _, _) in enumerate(self._overlay_objects):
            if oz > z:
                insert_idx = i
                break
        self._overlay_objects.insert(insert_idx, (z, obj, ctrl))
        self._rebuild_overlay()

    def add_many(self, objects: list[tuple[_Obj, int] | _Obj], z: int = 0) -> None:
        """Batch-add multiple objects with a single canvas rebuild.

        Parameters
        ----------
        objects
            A list where each element is either ``(obj, z)`` or a bare ``obj``
            (in which case the default *z* parameter is used).
        z
            Default z-layer for bare objects (no effect on ``(obj, z)`` tuples).
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
        """Batch-remove multiple objects with a single canvas rebuild."""
        remove_set = {id(_to_control(obj)) for obj in objects}
        with self.defer_rebuild():
            self._objects = [
                (oz, o, c) for oz, o, c in self._objects
                if id(c) not in remove_set
            ]

    @contextmanager
    def defer_rebuild(self) -> Iterator[None]:
        """Context manager that defers canvas rebuild and page updates.

        Use when adding/removing many objects::

            with scene.defer_rebuild():
                for i in range(100):
                    scene.add(Sprite(...))
        """
        self._rebuild_deferred += 1
        try:
            yield
        finally:
            self._rebuild_deferred -= 1
            if self._rebuild_deferred == 0:
                self._rebuild_canvas()
                self._rebuild_overlay()

    def remove(self, obj: _Obj) -> None:
        """Remove a Sprite, Label, or ``ft.Control`` from the scene or overlay."""
        ctrl = _to_control(obj)
        before = len(self._objects)
        self._objects = [
            (oz, o, c) for oz, o, c in self._objects if c is not ctrl
        ]
        if len(self._objects) != before:
            self._rebuild_canvas()
            return
        before_ov = len(self._overlay_objects)
        self._overlay_objects = [
            (oz, o, c) for oz, o, c in self._overlay_objects if c is not ctrl
        ]
        if len(self._overlay_objects) != before_ov:
            self._rebuild_overlay()

    def clear(self, tag: str | None = None) -> None:
        """Remove objects from the scene (canvas layer).

        Parameters
        ----------
        tag
            If given, only remove Sprites / Labels whose ``.tag`` matches.
            If ``None``, remove *all* managed canvas objects (background is kept).
            Overlay objects are not cleared; use :meth:`clear_overlay`.
        """
        if tag is None:
            self._objects.clear()
        else:
            self._objects = [
                (oz, o, c) for oz, o, c in self._objects
                if not (isinstance(o, (Sprite, Label, Button)) and o.tag == tag)
            ]
        self._rebuild_canvas()

    def clear_overlay(self) -> None:
        """Remove every control from the gesture-safe overlay layer."""
        self._overlay_objects.clear()
        self._rebuild_overlay()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def canvas(self) -> ft.Stack:
        """The raw ``ft.Stack`` canvas.  Pass to :class:`~flet_game.SplashEffect`."""
        return self._canvas

    @property
    def overlay(self) -> ft.Stack:
        """Gesture-safe overlay stack (sibling above the input-wrapped canvas)."""
        return self._overlay

    @property
    def root(self) -> ft.Stack:
        """Root stack containing the input-wrapped canvas and overlay.

        :class:`~flet_game.GameView` applies its scale transform here so both
        layers stay aligned on every screen size.
        """
        return self._root

    @property
    def input(self) -> InputManager:
        """The pre-wired :class:`~flet_game.InputManager`."""
        return self._input

    @property
    def width(self) -> float:
        return self._width

    @property
    def height(self) -> float:
        return self._height

    @property
    def bgcolor(self) -> str | None:
        """Background colour.  Set to change the background at runtime."""
        return self._bgcolor

    @bgcolor.setter
    def bgcolor(self, value: str) -> None:
        self._bgcolor = _resolve_color(value)
        self._bg.bgcolor = self._bgcolor
        if self._mounted:
            self._page.update()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild_canvas(self) -> None:
        """Rebuild ``canvas.controls`` from the sorted ``_objects`` list.

        When inside a ``defer_rebuild()`` context the actual rebuild is skipped;
        the deferred rebuild runs when the outermost context exits.

        When called from inside a GameLoop frame (``batch_active()`` is True),
        the ``canvas.controls`` reassignment still happens (it marks the
        canvas dirty) but the ``page.update()`` flush is deferred to the
        loop's single end-of-frame flush — preventing N mid-frame full-page
        diffs when sprites are spawned from an ``@loop.on_update`` callback.
        """
        if self._rebuild_deferred > 0:
            return
        self._canvas.controls = [self._bg] + [c for _, _, c in self._objects]
        if self._mounted and (_batch_active is None or not _batch_active()):
            self._page.update()

    def _rebuild_overlay(self) -> None:
        """Rebuild ``overlay.controls`` from the sorted ``_overlay_objects`` list."""
        if self._rebuild_deferred > 0:
            return
        self._overlay.controls = [c for _, _, c in self._overlay_objects]
        if self._mounted and (_batch_active is None or not _batch_active()):
            self._page.update()

    def __repr__(self) -> str:
        return (
            f"Scene(w={self._width}, h={self._height}, "
            f"objects={len(self._objects)}, "
            f"overlay={len(self._overlay_objects)}, mounted={self._mounted})"
        )


# ── Module-level helpers ───────────────────────────────────────────────────────

def _to_control(obj: _Obj) -> ft.Control:
    """Return the underlying Flet control for a Sprite, Label, Button, or ft.Control."""
    if isinstance(obj, (Sprite, Label, Button)):
        return obj.control
    return obj
