"""
input.py — InputManager: keyboard and mouse/touch state for flet_game.

Keyboard state is polled inside game-loop callbacks (no "async" required):

    input = InputManager(page)

    @loop.on_update
    def update(dt: float) -> None:
        if input.is_key_down("arrowleft"):
            player.x -= 200 * dt

Per-key event callbacks are registered with decorators:

    @input.on_key_down("space")
    def shoot(e: ft.KeyboardEvent) -> None:
        spawn_bullet()

Mouse / touch events reach the canvas through a GestureDetector that
InputManager creates when you call input.wrap(canvas):

    canvas = ft.Stack([player.control, ...], width=W, height=H)
    page.add(input.wrap(canvas))   # <-- add the GestureDetector, not canvas

    @input.on_click
    def handle_click(x: float, y: float) -> None:
        spawn_effect(x, y)

Implementation notes
--------------------
Flet's page.on_keyboard_event fires on key-down (and OS key-repeat when held).
Key-up events are not sent by all Flet builds; InputManager handles this with a
dual-timestamp strategy:

  _first_press[k]  — time.monotonic() of the initial press
  _last_event[k]   — time.monotonic() of the most-recent key-down or repeat

is_key_down() returns True while:
  • it is within 350 ms of the first press  (covers the OS repeat delay, ~300 ms)
  • OR the last event was within 150 ms       (covers the OS repeat interval, ~30 ms)

If Flet does supply key-up events (type attribute on KeyboardEvent), they are
used directly and the timestamps are cleared immediately.
"""

from __future__ import annotations

import inspect
import time
from typing import Callable, Optional

import flet as ft


# ─── Key name normalisation ────────────────────────────────────────────────────

# Short aliases for arrow keys — defined once at module level, not per call.
_ARROW_ALIASES: dict[str, str] = {
    "up": "arrowup",
    "down": "arrowdown",
    "left": "arrowleft",
    "right": "arrowright",
}


def _norm(key: str) -> str:
    """Return a canonical key name: lower-case, no spaces, hyphens, or underscores.

    The space bar arrives from Flet as ``" "`` (a single space character).
    After stripping it becomes ``""`` — we map that to ``"space"`` so that
    ``is_key_down("space")`` and ``@inp.on_key_down("space")`` both work.

    Arrow-key short aliases: ``"up"`` → ``"arrowup"``, ``"down"`` → ``"arrowdown"``,
    ``"left"`` → ``"arrowleft"``, ``"right"`` → ``"arrowright"``.

    Examples that all map to the same key::

        "ArrowLeft"  "Arrow Left"  "arrow_left"  "arrowleft"  "ARROWLEFT"  "left"
        " "  "space"  "Space"   (space bar)
    """
    stripped = key.strip()
    if stripped == "":        # space bar: " " → strip → "" → "space"
        return "space"
    norm = stripped.lower().replace(" ", "").replace("_", "").replace("-", "")
    # Allow short aliases for arrow keys
    return _ARROW_ALIASES.get(norm, norm)


# Timeout (seconds) that covers the OS initial-repeat delay (~300 ms on most
# systems) so is_key_down stays True between the first press and the first repeat.
_INITIAL_HOLD_WINDOW: float = 0.35

# Timeout (seconds) above the fastest OS key-repeat interval (~16 ms at 60 Hz)
# to treat a key as still held between consecutive repeat events.
_REPEAT_HOLD_WINDOW: float = 0.15


# ─── InputManager ─────────────────────────────────────────────────────────────

class InputManager:
    """Keyboard + mouse/touch input manager for a flet_game scene.

    Parameters
    ----------
    page : ft.Page
        The Flet page.  InputManager registers page.on_keyboard_event here.

    Keyboard polling (inside a GameLoop callback)::

        input = InputManager(page)

        @loop.on_update
        def update(dt):
            vx = 0.0
            if input.is_key_down("arrowleft") or input.is_key_down("a"):
                vx = -200
            if input.is_key_down("arrowright") or input.is_key_down("d"):
                vx = 200
            player.x += vx * dt

    Per-key event callbacks::

        @input.on_key_down("space")
        def fire(e: ft.KeyboardEvent) -> None:
            spawn_bullet()

        @input.on_key_up("space")
        def stop_fire(e: ft.KeyboardEvent) -> None:
            ...

    Mouse / touch (wrap the canvas before adding to the page)::

        canvas = ft.Stack([player.control], width=W, height=H)
        page.add(input.wrap(canvas))

        @input.on_click
        def spawn(x: float, y: float) -> None:
            ...

        @input.on_drag
        def drag(x: float, y: float, dx: float, dy: float) -> None:
            ...

    Cleanup (call when the scene is torn down)::

        input.destroy()
    """

    def __init__(self, page: ft.Page) -> None:
        self._page = page

        # Keys currently considered "held" (normalised names).
        # We derive this from timestamps rather than a simple set so that key-up
        # is detected even when Flet does not send explicit key-up events.
        self._first_press: dict[str, float] = {}   # key → time of initial press
        self._last_event:  dict[str, float] = {}   # key → time of latest key event

        # Callback tables.
        self._key_down_cbs: dict[str, list[Callable]] = {}
        self._key_up_cbs:   dict[str, list[Callable]] = {}
        self._click_cbs:    list[Callable] = []
        self._drag_cbs:     list[Callable] = []
        self._hover_cbs:    list[Callable] = []

        # Last tap-down position — captured by on_tap_down so that on_tap
        # (which carries no coordinates) can still report a useful position.
        self._tap_pos: tuple[float, float] = (0.0, 0.0)

        # Active flag — False while the scene is suspended in the stack.
        # _on_kb_event returns early when False so that a scene that is
        # off-screen does not intercept key events.
        self._active: bool = True

        # Virtual keys: injected by on-screen touch buttons via press_key() /
        # release_key().  is_key_down() returns True for any key in this set
        # regardless of timestamps, giving perfect frame-accurate hold detection
        # without the OS key-repeat timing heuristics.
        self._virtual_keys: set[str] = set()

        # GestureDetector created by wrap() — stored so on_drag() can lazily
        # add the pan recognizer after wrap() has been called.
        self._gd: ft.GestureDetector | None = None

        # Cached frame timestamp set by frame_tick().  When set, is_key_down()
        # uses this instead of calling time.monotonic() per key check, saving
        # N syscalls per frame when N keys are polled in one update callback.
        self._cached_now: float = -1.0

        # Register page-level keyboard handler.
        self._page.on_keyboard_event = self._on_kb_event

    # ── Keyboard — polling ─────────────────────────────────────────────────────

    def is_key_down(self, key: str) -> bool:
        """Return ``True`` while *key* is held down.

        Key names are case-insensitive; spaces, underscores, and hyphens are
        ignored.  Common names::

            "arrowleft"   "arrowright"  "arrowup"   "arrowdown"
            "a" "w" "s" "d"            (letters are lower-case)
            "space" or " "
            "enter"  "escape"  "shift"  "control"

        Call this inside a GameLoop update callback for smooth held-key movement::

            if input.is_key_down("arrowleft"):
                player.x -= 200 * dt
        """
        k = _norm(key)
        # _norm already maps " " and "space" → "space", so no extra alias needed.

        # Virtual keys (from on-screen touch buttons) are always authoritative.
        if k in self._virtual_keys:
            return True

        # Use the cached frame timestamp if frame_tick() was called this frame,
        # otherwise fall back to a fresh monotonic read.
        now = self._cached_now if self._cached_now >= 0 else time.monotonic()
        first = self._first_press.get(k)
        if first is None:
            return False  # key was never pressed

        # Still within the initial-hold window (before OS repeat kicks in)?
        if now - first < _INITIAL_HOLD_WINDOW:
            return True

        # Still receiving repeat events?
        last = self._last_event.get(k)
        if last is not None and now - last < _REPEAT_HOLD_WINDOW:
            return True

        # Key timed out — clean up and report released.
        self._first_press.pop(k, None)
        self._last_event.pop(k, None)
        return False

    def frame_tick(self, now: float) -> None:
        """Cache the current frame timestamp so every :meth:`is_key_down` call
        within this frame shares one ``time.monotonic()`` result.

        Call once at the top of each ``@loop.on_update`` callback (or let
        :class:`~flet_game.GameLoop` do it automatically when the InputManager
        is registered via :meth:`register`).

        Parameters
        ----------
        now
            The frame start time from ``time.monotonic()``.
        """
        self._cached_now = now

    # ── Virtual keys (on-screen touch buttons) ────────────────────────────────

    def press_key(self, key: str) -> None:
        """Simulate pressing and holding *key* from an on-screen touch button.

        The key stays "held" until :meth:`release_key` is called.
        This is frame-accurate — no OS key-repeat timing heuristics apply.

        Typical use with a ``ft.GestureDetector`` touch button::

            gd = ft.GestureDetector(
                on_tap_down=lambda e: inp.press_key("arrowup"),
                on_tap_up=lambda e: inp.release_key("arrowup"),
                on_pan_end=lambda e: inp.release_key("arrowup"),  # safety
                content=ft.Container(...),
            )
        """
        self._virtual_keys.add(_norm(key))

    def release_key(self, key: str) -> None:
        """Release a virtual key previously pressed with :meth:`press_key`."""
        self._virtual_keys.discard(_norm(key))

    def release_all_virtual_keys(self) -> None:
        """Release every virtual key at once (call on scene pause / unmount)."""
        self._virtual_keys.clear()

    # ── Keyboard — event callbacks ─────────────────────────────────────────────

    def on_key_down(self, key: str) -> Callable:
        """Decorator — fire *fn(e)* once on the initial press of *key*.

            @input.on_key_down("space")
            def shoot(e: ft.KeyboardEvent) -> None:
                spawn_bullet()
        """
        def decorator(fn: Callable) -> Callable:
            self._key_down_cbs.setdefault(_norm(key), []).append(fn)
            return fn
        return decorator

    def on_key_up(self, key: str) -> Callable:
        """Decorator — fire *fn(e)* when *key* is released.

        Note: requires Flet to emit key-up events (available in most Flet 1.0+
        builds).  If not supported, this callback will not fire.

            @input.on_key_up("escape")
            def quit(e: ft.KeyboardEvent) -> None:
                loop.stop()
        """
        def decorator(fn: Callable) -> Callable:
            self._key_up_cbs.setdefault(_norm(key), []).append(fn)
            return fn
        return decorator

    # ── Mouse / touch ──────────────────────────────────────────────────────────

    def wrap(self, control: ft.Control) -> ft.GestureDetector:
        """Wrap *control* in a ``ft.GestureDetector`` tied to this InputManager.

        Returns the ``GestureDetector`` — add *that* to the page instead of the
        raw control::

            canvas = ft.Stack([...], width=W, height=H)
            page.add(input.wrap(canvas))

        After wrapping, ``on_click``, ``on_drag``, and ``on_hover`` decorators
        will receive events from the canvas.

        Note: the pan recognizer (``on_pan_start`` / ``on_pan_update``) is NOT
        wired here by default.  It is added lazily the first time ``@on_drag``
        is used.  This avoids arena competition with ``ft.Container``
        ``on_click`` handlers inside the canvas (e.g. ``Button`` controls).
        """
        self._gd = ft.GestureDetector(
            content=control,
            on_tap_down=self._on_tap_down,  # fires click callbacks (tap may not fire with pan)
            on_pan_start=self._on_drag_start if self._drag_cbs else None,
            on_pan_update=self._on_drag      if self._drag_cbs else None,
            on_hover=self._on_hover,
            mouse_cursor=ft.MouseCursor.BASIC,
        )
        return self._gd

    def on_click(self, fn: Callable) -> Callable:
        """Decorator — fire *fn(x, y)* on canvas tap / left-click.

            @input.on_click
            def spawn(x: float, y: float) -> None:
                Sprite(x=x, y=y, ...).add_to(canvas)
        """
        self._click_cbs.append(fn)
        return fn

    def on_drag(self, fn: Callable) -> Callable:
        """Decorator — fire *fn(x, y, dx, dy)* during drag / pan events.

        ``dx`` / ``dy`` are the delta since the last drag event (in pixels).

            @input.on_drag
            def drag_player(x, y, dx, dy):
                player.x += dx
                player.y += dy
        """
        self._drag_cbs.append(fn)
        # Lazily enable pan recognition on the GestureDetector the first time
        # a drag callback is registered.  This prevents the pan recognizer from
        # competing with inner Button / Container on_click handlers in games
        # that do not use drag input.
        if len(self._drag_cbs) == 1 and getattr(self, '_gd', None) is not None:
            self._gd.on_pan_start  = self._on_drag_start
            self._gd.on_pan_update = self._on_drag
        return fn

    def on_hover(self, fn: Callable) -> Callable:
        """Decorator — fire *fn(x, y)* when the pointer moves over the canvas.

            @input.on_hover
            def track_cursor(x: float, y: float) -> None:
                cursor_sprite.move_to(x - 8, y - 8)
        """
        self._hover_cbs.append(fn)
        return fn

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def destroy(self) -> None:
        """Unregister all event handlers.  Call when the scene is torn down."""
        self._page.on_keyboard_event = None
        self._active = False
        self._first_press.clear()
        self._last_event.clear()
        self._key_down_cbs.clear()
        self._key_up_cbs.clear()
        self._click_cbs.clear()
        self._drag_cbs.clear()
        self._hover_cbs.clear()

    def deactivate(self) -> None:
        """Suspend keyboard processing. Used by Game.push_scene to silence a scene
        that is off-screen but still alive in the stack."""
        self._active = False
        self._first_press.clear()
        self._last_event.clear()

    def activate(self) -> None:
        """Resume keyboard processing and re-register the page handler.
        Call when a paused scene is restored to the top of the stack."""
        self._first_press.clear()
        self._last_event.clear()
        self._active = True
        self._page.on_keyboard_event = self._on_kb_event

    # ── Internal event handlers ────────────────────────────────────────────────

    def _on_kb_event(self, e: ft.KeyboardEvent) -> None:
        if not self._active:
            return
        k = _norm(e.key)

        # Detect key-up if Flet provides a 'type' attribute on the event.
        # The attribute may be a string or an enum; normalise to a plain string.
        raw_type = getattr(e, "type", None)
        if raw_type is not None:
            type_str = (raw_type.value if hasattr(raw_type, "value") else str(raw_type)).lower()
            if "up" in type_str:
                # Explicit key-up — clear timestamps and fire callbacks.
                self._first_press.pop(k, None)
                self._last_event.pop(k, None)
                self._dispatch(self._key_up_cbs, k, e)
                return

        # Key-down or repeat event.
        now = time.monotonic()
        first = self._first_press.get(k)
        last  = self._last_event.get(k)

        # A press is "fresh" when the key was never pressed, or when it timed
        # out (i.e. the key was released and Flet sent no key-up event).
        # Without this check, the first press sets _first_press[k] forever and
        # every subsequent press is wrongly treated as a repeat.
        is_fresh = (
            first is None
            or (
                now - first >= _INITIAL_HOLD_WINDOW
                and (last is None or now - last >= _REPEAT_HOLD_WINDOW)
            )
        )
        if is_fresh:
            self._first_press[k] = now
            self._dispatch(self._key_down_cbs, k, e)
        # Always refresh the last-event timestamp (covers OS key-repeat events).
        self._last_event[k] = now

    def _dispatch(
        self,
        table: dict[str, list[Callable]],
        key: str,
        event: ft.KeyboardEvent,
    ) -> None:
        for cb in table.get(key, []):
            if inspect.iscoroutinefunction(cb):
                self._page.run_task(cb, event)
            else:
                cb(event)

    def _on_tap_down(self, e) -> None:
        pos = getattr(e, "local_position", None)
        if pos is not None:
            x, y = float(pos.x), float(pos.y)
        else:
            x, y = (getattr(e, "local_x", 0.0), getattr(e, "local_y", 0.0))
        self._tap_pos = (x, y)
        for cb in self._click_cbs:
            if inspect.iscoroutinefunction(cb):
                self._page.run_task(cb, x, y)
            else:
                cb(x, y)

    def _on_drag_start(self, e) -> None:
        # on_pan_start must be registered to activate the pan gesture recognizer.
        # Fire drag callbacks with dx=dy=0 so callers know the drag began.
        pos = e.local_position
        x, y = float(pos.x), float(pos.y)
        for cb in self._drag_cbs:
            if inspect.iscoroutinefunction(cb):
                self._page.run_task(cb, x, y, 0.0, 0.0)
            else:
                cb(x, y, 0.0, 0.0)

    def _on_drag(self, e) -> None:
        pos   = e.local_position
        delta = e.local_delta
        x,  y  = float(pos.x),            float(pos.y)
        dx, dy = (float(delta.x), float(delta.y)) if delta is not None else (0.0, 0.0)
        for cb in self._drag_cbs:
            if inspect.iscoroutinefunction(cb):
                self._page.run_task(cb, x, y, dx, dy)
            else:
                cb(x, y, dx, dy)

    def _on_hover(self, e) -> None:
        pos = e.local_position
        x, y = float(pos.x), float(pos.y)
        for cb in self._hover_cbs:
            if inspect.iscoroutinefunction(cb):
                self._page.run_task(cb, x, y)
            else:
                cb(x, y)

    def __repr__(self) -> str:
        held = [k for k in self._first_press if self.is_key_down(k)]
        return f"InputManager(held={held!r})"
