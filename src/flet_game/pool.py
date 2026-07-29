"""
pool.py — ObjectPool: pre-allocate and reuse game objects to avoid GC pressure.

In real-time games, creating and destroying hundreds of short-lived objects
per second (bullets, particles, debris) triggers Python garbage collection and
causes frame-rate hiccups.  An ``ObjectPool`` pre-allocates a fixed set of
objects and recycles them by toggling visibility instead of creating/destroying.

Usage — bullet pool::

    from flet_game import Sprite, ObjectPool

    # Create a pool of 30 yellow bullet sprites — all hidden at start.
    bullet_pool = ObjectPool(
        factory=lambda: Sprite(x=0, y=0, width=6, height=6,
                               color="yellow", border_radius=3),
        scene=scene,
        max_size=30,
    )
    bullet_pool.prewarm()   # optional: allocate all objects upfront

    # Fire a bullet:
    bullet = bullet_pool.acquire()
    if bullet is not None:
        bullet.x = player.x + 16
        bullet.y = player.y
        bullet.show()

    # In @loop.on_update, when the bullet goes off-screen:
    bullet_pool.release(bullet)   # hides it and returns to pool

    # Release everything (e.g. on game-over):
    bullet_pool.release_all()

Scene integration
-----------------
If a ``scene`` is provided, each newly created object's control is added to
the scene automatically (at the given ``z`` layer).  If ``scene`` is ``None``,
you must add the controls to the canvas yourself after acquiring.

Without a scene::

    pool = ObjectPool(lambda: Sprite(...), max_size=20)
    pool.prewarm(scene=scene, z=5)   # add controls to scene at prewarm time
"""

from __future__ import annotations

from typing import Callable, Optional, TypeVar

_T = TypeVar("_T")


class ObjectPool:
    """Pre-allocate and reuse game objects.

    Parameters
    ----------
    factory
        A zero-argument callable that creates a new object.
        Called at most ``max_size`` times total.

        Example::

            factory = lambda: Sprite(x=0, y=0, width=8, height=8, color="cyan")

    max_size
        Maximum number of objects the pool will ever allocate.
        ``acquire()`` returns ``None`` once all objects are in use.
    scene
        Optional :class:`~flet_game.Scene`.  When provided, the control of
        each newly allocated Sprite/Label/Button is added to the scene
        automatically so it is rendered as part of the scene's canvas.
    z
        Z-layer used when auto-adding controls to the scene.  Default 5.
    """

    def __init__(
        self,
        factory: Callable,
        max_size: int = 50,
        scene=None,
        z: int = 5,
    ) -> None:
        self._factory = factory
        self._max = max_size
        self._scene = scene
        self._z = z
        self._free: list = []   # idle objects
        self._active: list = [] # in-use objects

    # ── Public API ────────────────────────────────────────────────────────────

    def prewarm(self, count: Optional[int] = None, scene=None, z: Optional[int] = None) -> "ObjectPool":
        """Pre-allocate *count* objects now (default: fill to ``max_size``).

        **Always call this before mount() / loop.start() for zero-allocation
        gameplay.**  Runtime ``acquire()`` from an empty pool calls
        ``scene.add()`` which triggers a full canvas rebuild — expensive during
        a frame.  Prewarming avoids this.

        All pre-warmed objects are placed in the free list (hidden, ready to
        be acquired).

        Parameters
        ----------
        count
            Number of objects to pre-create.  Capped at ``max_size - current_total``.
        scene
            Override the pool's scene for this prewarm call only.
        z
            Override the z-layer for this prewarm call only.
        """
        target = count if count is not None else self._max
        target = min(target, self._max - self.size)
        for _ in range(target):
            obj = self._create(scene=scene, z=z)
            self._free.append(obj)
        return self

    def acquire(self) -> Optional[object]:
        """Get an idle object from the pool.

        Returns ``None`` if all ``max_size`` objects are currently active.
        The caller is responsible for repositioning and showing the object::

            obj = pool.acquire()
            if obj is not None:
                obj.x, obj.y = spawn_x, spawn_y
                obj.show()
        """
        if self._free:
            obj = self._free.pop()
        else:
            obj = self._create()
            if obj is None:
                return None
        self._active.append(obj)
        return obj

    def release(self, obj, auto_hide: bool = True) -> None:
        """Return *obj* to the pool.

        Parameters
        ----------
        obj
            The object to release.
        auto_hide
            If ``True`` (default), the object is hidden before returning to the
            free list.  Set to ``False`` when you want to reposition the object
            and hide in a single :class:`~flet_game.GameLoop` batch frame::

                # Manual (batch-friendly) release:
                obj.x = new_x
                obj.y = new_y
                obj.hide()
                pool.release(obj, auto_hide=False)
        """
        try:
            self._active.remove(obj)
        except ValueError:
            pass
        if obj not in self._free:
            if auto_hide:
                try:
                    obj.hide()
                except AttributeError:
                    try:
                        obj.visible = False
                    except AttributeError:
                        pass
            self._free.append(obj)

    def release_all(self) -> None:
        """Return all active objects to the pool without hiding them.

        Typically followed by iterating ``active`` to hide each object first::

            for obj in pool.active:
                obj.hide()
            pool.release_all()

        Or use :meth:`release_all_and_hide` for a one-liner.
        """
        self._free.extend(self._active)
        self._active.clear()

    def release_all_and_hide(self) -> None:
        """Hide and release all currently active objects in one call.

        Implemented as a single O(N) pass: hide every active object, then
        bulk-transfer the active list into the free list.  The previous
        implementation called ``release(obj)`` per object, which did an
        O(N) ``list.remove`` per call → O(N²) total for large pools.
        """
        for obj in self._active:
            try:
                obj.hide()
            except AttributeError:
                try:
                    obj.visible = False
                except AttributeError:
                    pass
        self._free.extend(self._active)
        self._active.clear()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def active(self) -> list:
        """A snapshot list of currently in-use objects."""
        return list(self._active)

    @property
    def free(self) -> list:
        """A snapshot list of idle objects ready to be acquired."""
        return list(self._free)

    @property
    def size(self) -> int:
        """Total number of allocated objects (active + free)."""
        return len(self._active) + len(self._free)

    @property
    def active_count(self) -> int:
        """Number of currently in-use objects."""
        return len(self._active)

    @property
    def free_count(self) -> int:
        """Number of idle objects available for acquisition."""
        return len(self._free)

    @property
    def max_size(self) -> int:
        """Maximum pool capacity."""
        return self._max

    @property
    def is_exhausted(self) -> bool:
        """``True`` when all objects are in use and no more can be created."""
        return len(self._free) == 0 and self.size >= self._max

    # ── Internal ──────────────────────────────────────────────────────────────

    def _create(self, scene=None, z=None) -> Optional[object]:
        """Allocate one new object if the pool is not full. Returns None if full."""
        if self.size >= self._max:
            return None
        obj = self._factory()
        # Auto-add to scene if available.
        target_scene = scene or self._scene
        target_z = z if z is not None else self._z
        if target_scene is not None:
            try:
                target_scene.add(obj, z=target_z)
            except AttributeError:
                pass
        return obj

    def __repr__(self) -> str:
        return (
            f"ObjectPool(active={len(self._active)}, free={len(self._free)}, "
            f"max={self._max})"
        )
