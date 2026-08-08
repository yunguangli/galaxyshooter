"""
loop.py — GameLoop: the asyncio-based heartbeat of flet_game.

The GameLoop drives all frame-by-frame game logic. It runs as an asyncio
background task (via page.run_task), calls every registered update callback
with a delta-time value, then flushes the UI in a single page.update() per
frame — far more efficient than per-sprite updates.

Delta-time (dt)
---------------
dt is the elapsed wall-clock seconds since the last frame. Multiplying velocities
by dt makes all movement frame-rate-independent:

    sprite.x += 200 * dt   # always moves at 200 px/second, regardless of FPS

dt is capped at 100 ms to prevent the "spiral of death" after a pause or a
transient frame drop (e.g. the first frame after page focus is restored).

Usage
-----
    loop = GameLoop(page, fps=60)

    @loop.on_update
    def update(dt: float) -> None:         # plain def — no 'async' needed
        player.x += speed * dt

    # async def also works if you need to await something inside:
    @loop.on_update
    async def animate(dt: float) -> None:
        await some_coroutine()

    loop.start()    # begins the background task
    loop.pause()    # freezes updates; loop sleeps but does not exit
    loop.resume()   # continues from where it left off
    loop.stop()     # exits the loop permanently on the next tick
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import time
from typing import Callable, Awaitable

import flet as ft

# Type alias for update callbacks.
# Both sync (def) and async (async def) functions are accepted — GameLoop
# detects at registration time and dispatches accordingly.
UpdateCallback = Callable[[float], Awaitable[None]] | Callable[[float], None]

# Maximum dt to inject after a pause or frame drop (seconds).
# Prevents physics objects from teleporting after stalls.
_MAX_DT: float = 0.1

# ---------------------------------------------------------------------------
# Batch-update flag (module-level so Sprite._update() can check it)
# ---------------------------------------------------------------------------
# Set to True while update callbacks are executing. Sprite._update() checks
# this flag to skip per-control flushes — the loop does one page.update() per
# frame after all callbacks complete, which avoids double-flushing every sprite
# that moved.  Using a counter (not a bool) supports nested/multiple loops.
_batch_depth: int = 0

# Frame-dirty flag — set by controls (RaycastCanvas.render(), Label._update(),
# VirtualJoystick, ...) whenever they actually mutate UI state inside a frame.
# When GameLoop.skip_clean_frames is enabled, frames where nothing was marked
# dirty skip the end-of-frame page.update() entirely (the tree diff would be
# empty, so the bridge round-trip is pure overhead).
_frame_dirty: bool = False


def batch_active() -> bool:
    """Return True while a GameLoop frame is dispatching callbacks."""
    return _batch_depth > 0


def mark_frame_dirty() -> None:
    """Record that a control mutated UI state inside this frame.

    Controls that change geometry/text/visibility during a game-loop frame
    call this (instead of relying on the end-of-frame page.update() alone) so
    the loop knows the frame actually needs a flush when ``skip_clean_frames``
    is enabled.
    """
    global _frame_dirty
    _frame_dirty = True


def consume_frame_dirty() -> bool:
    """Return True if any control marked this frame dirty (and reset the flag)."""
    global _frame_dirty
    if _frame_dirty:
        _frame_dirty = False
        return True
    return False


def _apply_timer_resolution() -> None:
    """Best-effort Windows multimedia timer fix (safe no-op elsewhere).

    ``asyncio.sleep()`` on Windows rounds up to the ~15.6 ms system timer
    tick, which caps a 60 Hz game loop at ~32 fps.  ``timeBeginPeriod(1)``
    lowers the tick to 1 ms so sleeps can hit the frame budget precisely.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            winmm = ctypes.WinDLL("winmm", use_last_error=True)
            winmm.timeBeginPeriod(1)
        except Exception:
            pass


class GameLoop:
    """
    Asyncio-based game loop with delta-time and a decorator-based update system.

    Parameters
    ----------
    page : ft.Page
        The Flet page — used to schedule the background task and flush the UI.
    fps : int
        Target frames per second (default 60). The loop sleeps the unused
        portion of each frame budget. Actual FPS depends on system load and
        the cost of your update callbacks.
    """

    def __init__(self, page: ft.Page, fps: int = 60) -> None:
        self._page = page
        self._target_fps: int = max(1, fps)
        self._callbacks: list[tuple[UpdateCallback, bool]] = []
        self._batch_updates: bool = True
        # Opt-in: skip the end-of-frame page.update() on frames where no
        # control marked itself dirty.  Default off (library-safe).
        self._skip_clean_frames: bool = False

        # Loop state
        self._running: bool = False
        self._paused: bool = False

        # Performance counters (updated once per second)
        self._measured_fps: float = 0.0
        self._measured_dt_ms: float = 0.0

        # InputManagers registered via register_input() — ticked at the start
        # of each frame so is_key_down() shares one time.monotonic() result.
        self._input_managers: list = []

        # Desktop 60 fps is otherwise capped at ~32 by the ~15.6 ms Windows
        # timer tick — asyncio.sleep() can't round below it.
        _apply_timer_resolution()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def on_update(self, fn: UpdateCallback) -> UpdateCallback:
        """
        Decorator — register an async callback to be called every frame.

        The callback receives `dt` (delta-time in seconds since the last frame).
        Multiple callbacks are supported; they run sequentially in registration order.

        Example
        -------
            @loop.on_update
            async def physics(dt: float) -> None:
                ball.x += vx * dt
                ball.y += vy * dt
        """
        self._callbacks.append((fn, inspect.iscoroutinefunction(fn)))
        return fn

    def add_callback(self, fn: UpdateCallback) -> None:
        """Programmatically add an update callback (alternative to decorator)."""
        self._callbacks.append((fn, inspect.iscoroutinefunction(fn)))

    def remove_callback(self, fn: UpdateCallback) -> None:
        """Remove a previously registered callback."""
        self._callbacks = [(cb, a) for cb, a in self._callbacks if cb is not fn]

    def register_input(self, inp) -> None:
        """Register an :class:`~flet_game.InputManager` to be ticked at the
        start of every frame.  This lets :meth:`~flet_game.InputManager.is_key_down`
        share one ``time.monotonic()`` call per frame instead of one per key check.

        :class:`~flet_game.Scene` calls this automatically when it creates its
        internal InputManager, so manual registration is only needed when you
        create a standalone InputManager outside a Scene.
        """
        if inp not in self._input_managers:
            self._input_managers.append(inp)

    def unregister_input(self, inp) -> None:
        """Remove a previously registered InputManager."""
        try:
            self._input_managers.remove(inp)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the game loop as an asyncio background task.
        Has no effect if the loop is already running.
        """
        if self._running:
            return
        self._running = True
        self._paused = False
        # page.run_task schedules the coroutine on Flet's event loop.
        self._page.run_task(self._loop)

    def stop(self) -> None:
        """
        Stop the loop. It exits on the next tick (within one frame period).
        Call start() to restart from scratch.
        """
        self._running = False
        self._paused = False

    def pause(self) -> None:
        """
        Pause the loop. Callbacks are skipped and the UI is not refreshed,
        but the asyncio task keeps sleeping so it can be resumed instantly.
        dt is still tracked correctly — prev_time advances even while paused,
        so there is no dt spike on resume.
        """
        self._paused = True

    def resume(self) -> None:
        """Resume a paused loop."""
        self._paused = False

    def toggle_pause(self) -> None:
        """Convenience: flip between paused and running."""
        self._paused = not self._paused

    # ------------------------------------------------------------------
    # Batch context (for use outside frame callbacks)
    # ------------------------------------------------------------------

    def begin_update(self) -> None:
        """Enter batch-update mode outside the game loop.

        While active, ``Sprite._update()`` suppresses per-control flushes
        just like during a frame.  Call :meth:`end_update` to flush once::

            loop.begin_update()
            sprite.x = 10
            sprite.y = 20
            sprite.opacity = 0.5
            loop.end_update()    # single page.update()
        """
        global _batch_depth
        _batch_depth += 1

    def end_update(self) -> None:
        """Exit batch-update mode and flush all pending control changes.

        Only flushes at the outermost nesting level (when ``_batch_depth``
        reaches 0) so nested ``begin_update``/``end_update`` contexts produce
        a single ``page.update()``, not one per exit.  Unlike the loop's
        end-of-frame path, the manual ``end_update()`` flush always fires
        regardless of ``batch_updates`` — its whole purpose is to flush.
        """
        global _batch_depth
        if _batch_depth > 0:
            _batch_depth -= 1
        if _batch_depth > 0:
            return  # still inside an outer batch — defer the flush
        try:
            self._page.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True while the loop task is alive and not paused."""
        return self._running and not self._paused

    @property
    def is_paused(self) -> bool:
        """True while the loop task is alive but paused."""
        return self._running and self._paused

    @property
    def fps(self) -> float:
        """Measured frames per second, averaged over the last second."""
        return self._measured_fps

    @property
    def dt_ms(self) -> float:
        """Last measured frame time in milliseconds."""
        return self._measured_dt_ms

    @property
    def target_fps(self) -> int:
        """Target FPS. Can be changed at runtime."""
        return self._target_fps

    @target_fps.setter
    def target_fps(self, value: int) -> None:
        self._target_fps = max(1, value)

    @property
    def batch_updates(self) -> bool:
        """Whether to call ``page.update()`` once after every frame's callbacks.

        Mid-frame per-control flushes are always suppressed via
        :func:`batch_active` while callbacks run.  Set this to ``False`` when
        a scene flushes only dirty canvases itself (``canvas.update()``) and
        wants to skip the full-page end-of-frame walk.
        """
        return self._batch_updates

    @batch_updates.setter
    def batch_updates(self, value: bool) -> None:
        self._batch_updates = bool(value)

    @property
    def skip_clean_frames(self) -> bool:
        """Whether to skip ``page.update()`` on frames where nothing changed.

        When enabled, controls must call :func:`mark_frame_dirty` whenever
        they mutate UI state inside a frame (RaycastCanvas.render(),
        Label._update() and VirtualJoystick already do).  Frames where no
        control marks itself dirty skip the end-of-frame flush entirely —
        the page-tree diff would be empty anyway, so the bridge round-trip
        is pure overhead.  Default ``False``; scenes that mutate raw Flet
        controls directly should leave it off.
        """
        return self._skip_clean_frames

    @skip_clean_frames.setter
    def skip_clean_frames(self, value: bool) -> None:
        self._skip_clean_frames = bool(value)

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """The main async loop body — runs as a background task."""
        prev_time = time.monotonic()

        # FPS measurement accumulators (reset every second)
        frame_count: int = 0
        fps_elapsed: float = 0.0

        while self._running:
            frame_start = time.monotonic()

            # --- Delta-time -------------------------------------------------
            # Cap at _MAX_DT to avoid physics explosions after pauses or stalls.
            dt = min(frame_start - prev_time, _MAX_DT)
            prev_time = frame_start

            # --- FPS measurement --------------------------------------------
            # We count ALL frames (paused or not) for honest FPS reporting,
            # but only accumulate fps_elapsed while actively updating.
            if not self._paused:
                frame_count += 1
                fps_elapsed += dt
                self._measured_dt_ms = dt * 1000.0

                if fps_elapsed >= 1.0:
                    self._measured_fps = round(frame_count / fps_elapsed, 1)
                    frame_count = 0
                    fps_elapsed = 0.0

                # --- Tick registered InputManagers -------------------------
                # Share the frame start time so is_key_down() doesn't call
                # time.monotonic() for every key polled in this frame.
                for _inp in self._input_managers:
                    _inp.frame_tick(frame_start)

                # --- Update callbacks ---------------------------------------
                # Always suppress per-control update() during callbacks via
                # batch_active(), so Label/Sprite/Joystick setters never each
                # flush mid-frame.  The optional end-of-frame page.update() is
                # separate: scenes that only flush dirty canvases can set
                # batch_updates=False without thrashing the Flet bridge.
                global _batch_depth
                _batch_depth += 1
                try:
                    # Dispatch each callback — plain def and async def both work.
                    # The async flag is computed once at registration time (in
                    # on_update / add_callback) to avoid per-frame reflection.
                    try:
                        # Snapshot: callbacks may run_scene() mid-frame, which
                        # removes the old scene's callbacks and registers the
                        # new scene's — mutating the list during iteration.
                        for cb, is_async in list(self._callbacks):
                            if is_async:
                                await cb(dt)
                            else:
                                cb(dt)
                    except (AttributeError, RuntimeError) as exc:
                        # Covers both closed-browser and destroyed-session
                        # (window closed / session torn down mid-callback):
                        # page.session.connection is None → AttributeError,
                        # or page.update() raises "destroyed session" (e.g. a
                        # scene callback flushing its own canvas after close).
                        if not isinstance(exc, RuntimeError) or (
                            "destroyed session" in str(exc).lower()
                        ):
                            self._running = False
                            return
                        raise
                finally:
                    _batch_depth -= 1
                    # Invalidate the cached timestamp so any is_key_down()
                    # call outside a frame (e.g. in an event handler) falls
                    # back to a fresh time.monotonic() call.
                    for _inp in self._input_managers:
                        _inp._cached_now = -1.0

                if self._batch_updates:
                    # --- Single page flush per frame ------------------------
                    # One page.update() is much cheaper than calling
                    # control.update() for every sprite that moved this frame.
                    # With skip_clean_frames enabled, frames where no control
                    # marked itself dirty skip the flush entirely — the tree
                    # diff would be empty, so the round-trip is pure overhead.
                    if not self._skip_clean_frames or consume_frame_dirty():
                        try:
                            self._page.update()
                        except RuntimeError as exc:
                            # Session destroyed (window closed while loop was running).
                            # Exit cleanly rather than spamming error callbacks.
                            if "destroyed session" in str(exc).lower():
                                self._running = False
                                return
                            raise

            # --- Sleep the remaining frame budget ---------------------------
            frame_elapsed = time.monotonic() - frame_start
            sleep_for = max(0.0, (1.0 / self._target_fps) - frame_elapsed)
            await asyncio.sleep(sleep_for)

    def __repr__(self) -> str:
        state = "running" if self.is_running else ("paused" if self.is_paused else "stopped")
        return f"GameLoop(fps={self._target_fps}, state={state!r}, measured={self._measured_fps})"
