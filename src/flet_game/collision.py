"""
collision.py — CollisionSystem: AABB collision detection for flet_game.

CollisionSystem provides three usage modes:

1. **Static helpers** — one-off checks anywhere in your code:

       pairs = CollisionSystem.check_groups(bullets, enemies)
       hits  = CollisionSystem.check_one(player, enemies)
       hit   = CollisionSystem.check_point(mx, my, coins)

2. **Rule-based callbacks** — declare "tag A hits tag B" once; call
   ``update(sprites)`` every frame:

       col = CollisionSystem()

       @col.on_collision("bullet", "enemy")
       def bullet_hit(bullet: Sprite, enemy: Sprite) -> None:
           bullet.destroy()
           enemy.destroy()

       @loop.on_update
       def update(dt):
           col.update(all_sprites)   # fires callbacks for every overlap

3. **Collision response** — push overlapping sprites apart:

       CollisionSystem.separate(player, wall)   # instant separation

SpatialHash broadphase
----------------------
For large numbers of sprites (100+), ``CollisionSystem`` can use a
:class:`SpatialHash` to avoid O(N²) pair checks.  Pass it to ``update()``::

    grid = SpatialHash(cell_size=64)

    @loop.on_update
    def tick(dt):
        grid.clear()
        grid.insert_many(all_sprites)
        col.update(all_sprites, page, spatial_hash=grid)

The ``SpatialHash`` can also be used standalone for broadphase queries::

    nearby = grid.query(player)  # candidates (may include false positives)
"""

from __future__ import annotations

from typing import Callable, Optional
import inspect
import math

from .sprite import Sprite


# ---------------------------------------------------------------------------
# SpatialHash — grid-based broadphase
# ---------------------------------------------------------------------------

class SpatialHash:
    """Grid-based spatial hash for broadphase collision culling.

    Divides the world into *cell_size* × *cell_size* cells.  Each sprite is
    inserted into every cell its AABB overlaps.  Queries return all candidate
    sprites from the cells the query overlaps — a fast broadphase that avoids
    O(N²) pair checks.

    Usage::

        grid = SpatialHash(cell_size=64)

        # Every frame before collision checks:
        grid.clear()
        grid.insert_many(all_sprites)

        # Broadphase query — quick candidate list:
        candidates = grid.query(player)          # all sprites in nearby cells
        for other in candidates:
            if other is not player and player.collides_with(other):
                ...

    Parameters
    ----------
    cell_size
        Width and height of each grid cell in pixels.  Typical values: 64–256.
        Smaller cells = fewer candidates but more insert overhead.
    """

    def __init__(self, cell_size: float = 128) -> None:
        self._cell_size = float(cell_size)
        self._cells: dict[tuple[int, int], list[Sprite]] = {}

    def _cell_range(self, bounds: tuple[float, float, float, float]) -> tuple:
        """Return (min_cx, min_cy, max_cx, max_cy) for an AABB."""
        x1, y1, x2, y2 = bounds
        cs = self._cell_size
        return (
            int(math.floor(x1 / cs)),
            int(math.floor(y1 / cs)),
            int(math.floor((x2 - 1) / cs)),
            int(math.floor((y2 - 1) / cs)),
        )

    def insert(self, sprite: Sprite) -> None:
        """Insert *sprite* into all cells its AABB overlaps."""
        cmin_x, cmin_y, cmax_x, cmax_y = self._cell_range(sprite.bounds)
        for cy in range(cmin_y, cmax_y + 1):
            for cx in range(cmin_x, cmax_x + 1):
                key = (cx, cy)
                self._cells.setdefault(key, []).append(sprite)

    def insert_many(self, sprites: list[Sprite]) -> None:
        """Batch-insert all *sprites*.  Faster than per-sprite loops."""
        for s in sprites:
            if s.visible:
                cmin_x, cmin_y, cmax_x, cmax_y = self._cell_range(s.bounds)
                for cy in range(cmin_y, cmax_y + 1):
                    for cx in range(cmin_x, cmax_x + 1):
                        key = (cx, cy)
                        self._cells.setdefault(key, []).append(s)

    def query(self, sprite: Sprite) -> list[Sprite]:
        """Return candidate sprites from cells overlapping *sprite*'s AABB.

        The returned list may contain duplicates and false positives (sprites
        in nearby cells that do not actually overlap).  Deduplicate and do a
        narrowphase check before declaring a collision.
        """
        seen: set[int] = set()
        result: list[Sprite] = []
        cmin_x, cmin_y, cmax_x, cmax_y = self._cell_range(sprite.bounds)
        for cy in range(cmin_y, cmax_y + 1):
            for cx in range(cmin_x, cmax_x + 1):
                for s in self._cells.get((cx, cy), ()):
                    sid = id(s)
                    if sid not in seen:
                        seen.add(sid)
                        if s.visible:
                            result.append(s)
        return result

    def clear(self) -> None:
        """Remove all sprites from the grid.  Call once per frame."""
        self._cells.clear()

    def __repr__(self) -> str:
        total = sum(len(v) for v in self._cells.values())
        return f"SpatialHash(cells={len(self._cells)}, sprites={total})"


# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

SpritePair = tuple[Sprite, Sprite]
CollisionCallback = Callable[[Sprite, Sprite], None]


# ---------------------------------------------------------------------------
# CollisionSystem
# ---------------------------------------------------------------------------

class CollisionSystem:
    """AABB (axis-aligned bounding-box) collision detection for flet_game.

    Parameters
    ----------
    None — CollisionSystem is stateless unless you register rules via
    :meth:`on_collision`.

    Static helpers (no instance needed)::

        # All overlapping pairs within one group:
        for a, b in CollisionSystem.check_group(sprites):
            ...

        # Every pair where a bullet overlaps an enemy:
        for bullet, enemy in CollisionSystem.check_groups(bullets, enemies):
            bullet.destroy()
            enemy.destroy()

        # All sprites that contain a mouse click:
        clicked = CollisionSystem.check_point(mx, my, clickable_sprites)

    Rule-based usage::

        col = CollisionSystem()

        @col.on_collision("bullet", "enemy")
        def on_hit(bullet: Sprite, enemy: Sprite) -> None:
            bullet.destroy()
            enemy.destroy()

        @loop.on_update
        def update(dt: float) -> None:
            col.update(all_sprites)   # checks all rules, fires callbacks

    Collision response::

        CollisionSystem.separate(player, wall)  # push apart on smallest axis

    Auto broadphase
    ---------------
    When :meth:`update` is called with ``spatial_hash=None`` (the default)
    and the visible sprite count exceeds
    :attr:`auto_spatialhash_threshold` (default ``50``), a
    :class:`SpatialHash` is auto-instantiated for that frame so the pair
    check is O(N) instead of O(N²).  Pass an explicit ``spatial_hash=`` to
    reuse one across frames (avoids re-instantiating per call), or raise the
    threshold to disable the auto-fallback.
    """

    #: Visible-sprite count above which ``update()`` auto-instantiates a
    #: ``SpatialHash`` for broadphase culling when none was passed.  Set this
    #: to a very large number (e.g. ``sys.maxsize``) to force brute-force.
    auto_spatialhash_threshold: int = 50

    def __init__(self) -> None:
        # Each rule: (tag_a, tag_b, callback, symmetric, is_async)
        # symmetric=True means the rule fires for (A hits B) AND (B hits A).
        # is_async is captured once at registration to avoid per-pair
        # inspect.iscoroutinefunction() reflection in the hot loop.
        self._rules: list[tuple[str, str, CollisionCallback, bool, bool]] = []

    # ── Rule-based API ─────────────────────────────────────────────────────────

    def on_collision(
        self,
        tag_a: str,
        tag_b: str,
        symmetric: bool = False,
    ) -> Callable:
        """Decorator — register *fn(a, b)* to fire when a sprite tagged *tag_a*
        overlaps a sprite tagged *tag_b*.

        Parameters
        ----------
        tag_a, tag_b
            The :attr:`Sprite.tag` values to match.  Matching is exact
            (case-sensitive).
        symmetric
            If ``True``, also fires ``fn(b, a)`` when a *tag_b* sprite is the
            first actor (saves registering two mirror rules).

            @col.on_collision("bullet", "enemy")
            def on_hit(bullet: Sprite, enemy: Sprite) -> None:
                bullet.destroy()
                enemy.destroy()

            # async handlers are also supported:
            @col.on_collision("player", "coin", symmetric=False)
            async def collect_coin(player: Sprite, coin: Sprite) -> None:
                coin.destroy()
                await play_sound("ding")
        """
        def decorator(fn: CollisionCallback) -> CollisionCallback:
            self._rules.append((tag_a, tag_b, fn, symmetric, inspect.iscoroutinefunction(fn)))
            return fn
        return decorator

    def update(
        self,
        sprites: list[Sprite],
        page=None,
        spatial_hash: Optional[SpatialHash] = None,
    ) -> None:
        """Check every registered rule against *sprites* and fire callbacks.

        Call this once per frame inside a ``@loop.on_update`` callback::

            @loop.on_update
            def update(dt: float) -> None:
                col.update(all_sprites)

        Parameters
        ----------
        sprites
            Flat list of all active sprites.  Invisible sprites are skipped.
        page
            Optional ``ft.Page`` — required only when async collision callbacks
            are used (passed to ``page.run_task``).
        spatial_hash
            Optional :class:`SpatialHash` for broadphase culling.  When set,
            the per-rule pair loops are replaced by spatial queries — much
            faster for 100+ sprites::

                grid = SpatialHash(cell_size=64)
                grid.clear()
                grid.insert_many(all_sprites)
                col.update(all_sprites, page, spatial_hash=grid)
        """
        visible = [s for s in sprites if s.visible]

        # Auto-fallback: when no spatial_hash was passed and the visible
        # sprite count exceeds the threshold, instantiate one for this frame
        # so the per-rule pair loop runs in O(N) instead of O(N²).  Callers
        # who pass an explicit spatial_hash= (reused across frames) bypass
        # this allocation.  Raise auto_spatialhash_threshold to disable.
        if spatial_hash is None and len(visible) > self.auto_spatialhash_threshold:
            spatial_hash = SpatialHash()
            spatial_hash.insert_many(visible)

        # Build tag → sprites lookup once per frame (avoids O(R·N) filtering).
        by_tag: dict[str, list[Sprite]] = {}
        for s in visible:
            by_tag.setdefault(s.tag, []).append(s)

        for tag_a, tag_b, cb, symmetric, is_async in self._rules:
            group_a = by_tag.get(tag_a, [])
            group_b = by_tag.get(tag_b, [])
            if not group_a or not group_b:
                continue

            if spatial_hash is not None:
                # Broadphase: for each a, query nearby candidates from group_b.
                for a in group_a:
                    candidates = spatial_hash.query(a)
                    for b in candidates:
                        if b.tag != tag_b or b is a:
                            continue
                        if a.collides_with(b):
                            _invoke(cb, a, b, page, is_async)
                            if symmetric:
                                _invoke(cb, b, a, page, is_async)
            else:
                # Brute-force: check all pairs (fine for small groups).
                for a in group_a:
                    for b in group_b:
                        if a is b:
                            continue
                        if a.collides_with(b):
                            _invoke(cb, a, b, page, is_async)
                            if symmetric:
                                _invoke(cb, b, a, page, is_async)

    # ── Static helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def check_group(sprites: list[Sprite]) -> list[SpritePair]:
        """Return all unique overlapping pairs within a single group.

        Each pair ``(a, b)`` is returned once (``(b, a)`` is not duplicated)::

            for wall_a, wall_b in CollisionSystem.check_group(walls):
                ...
        """
        result: list[SpritePair] = []
        visible = [s for s in sprites if s.visible]
        for i, a in enumerate(visible):
            for b in visible[i + 1 :]:
                if a.collides_with(b):
                    result.append((a, b))
        return result

    @staticmethod
    def check_groups(
        group_a: list[Sprite],
        group_b: list[Sprite],
    ) -> list[SpritePair]:
        """Return all overlapping pairs between two groups.

        Every ``(a, b)`` pair where *a* is from *group_a* and *b* is from
        *group_b* is checked.  Sprites in both groups are also checked::

            hits = CollisionSystem.check_groups(bullets, enemies)
            for bullet, enemy in hits:
                bullet.destroy()
                enemy.destroy()
        """
        result: list[SpritePair] = []
        va = [s for s in group_a if s.visible]
        vb = [s for s in group_b if s.visible]
        for a in va:
            for b in vb:
                if a is not b and a.collides_with(b):
                    result.append((a, b))
        return result

    @staticmethod
    def check_one(
        sprite: Sprite,
        group: list[Sprite],
    ) -> list[Sprite]:
        """Return every sprite in *group* that overlaps *sprite*::

            enemies_hit = CollisionSystem.check_one(player, enemies)
        """
        return [
            s for s in group
            if s is not sprite and s.visible and sprite.collides_with(s)
        ]

    @staticmethod
    def collisions_with(
        sprite: Sprite,
        group: list[Sprite],
    ) -> list[Sprite]:
        """Return every sprite in *group* that overlaps *sprite*.

        Friendlier alias for :meth:`check_one` — reads naturally as
        "what does this sprite collide with?"::

            for enemy in Collider.collisions_with(player, enemies):
                enemy.hide()
        """
        return CollisionSystem.check_one(sprite, group)

    @staticmethod
    def check_point(
        x: float,
        y: float,
        sprites: list[Sprite],
    ) -> list[Sprite]:
        """Return every sprite whose bounding box contains the point *(x, y)*::

            clicked = CollisionSystem.check_point(mx, my, clickable)
        """
        return [s for s in sprites if s.visible and s.contains_point(x, y)]

    # ── Collision response ─────────────────────────────────────────────────────

    @staticmethod
    def separate(a: Sprite, b: Sprite) -> None:
        """Push *a* and *b* apart along the axis of minimum penetration.

        Both sprites are moved by half the overlap distance in opposite
        directions so they no longer overlap::

            if player.collides_with(wall):
                CollisionSystem.separate(player, wall)
        """
        ax1, ay1, ax2, ay2 = a.bounds
        bx1, by1, bx2, by2 = b.bounds

        # Overlap on each axis
        dx = min(ax2, bx2) - max(ax1, bx1)
        dy = min(ay2, by2) - max(ay1, by1)

        if dx <= 0 or dy <= 0:
            return  # not actually overlapping

        half = 0.5
        if dx < dy:
            # Smaller overlap on X — push horizontally
            if (ax1 + ax2) / 2 < (bx1 + bx2) / 2:
                a.x -= dx * half
                b.x += dx * half
            else:
                a.x += dx * half
                b.x -= dx * half
        else:
            # Smaller overlap on Y — push vertically
            if (ay1 + ay2) / 2 < (by1 + by2) / 2:
                a.y -= dy * half
                b.y += dy * half
            else:
                a.y += dy * half
                b.y -= dy * half

    def __repr__(self) -> str:
        return f"CollisionSystem(rules={len(self._rules)})"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _invoke(
    cb: CollisionCallback,
    a: Sprite,
    b: Sprite,
    page,
    is_async: bool = False,
) -> None:
    """Call *cb(a, b)*, dispatching async callbacks via page.run_task.

    The ``is_async`` flag is normally captured at rule-registration time by
    :meth:`CollisionSystem.on_collision` and passed through here so we avoid
    ``inspect.iscoroutinefunction(cb)`` reflection on every collision pair.
    """
    if is_async:
        if page is not None:
            page.run_task(cb, a, b)
    else:
        cb(a, b)
