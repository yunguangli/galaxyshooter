"""
mapgen.py — Map generation utilities for flet_game.

Provides parameterized map generators suitable for raycasters, dungeon
crawlers, and platformer levels.  All generators return ``list[list[int]]``
grids where 0 = walkable and 1+ = wall type (1-based index into the game's
wall colour list).

Usage::

    from flet_game import generate_random_map, spawn_points

    MAP, walkable = generate_random_map(16, 16, wall_types=[1, 2, 3], fill_pct=0.28)
    # walkable is a list of (row, col) tuples.
    for r, c in walkable:
        MAP[r][c] = 0   # guaranteed walkable

    enemies = spawn_points(walkable, count=8, min_spacing=3.0)
    # enemies is a list of (col, row) world coords (centered in cells).
"""

from __future__ import annotations

import random
from typing import Optional


def generate_random_map(
    width: int = 16,
    height: int = 16,
    *,
    wall_types: Optional[list[int]] = None,
    fill_pct: float = 0.28,
    border: bool = True,
    room_size: int = 3,
    seed: Optional[int] = None,
) -> tuple[list[list[int]], list[tuple[int, int]]]:
    """Generate a random wall map suitable for raycast or top-down games.

    The algorithm ensures all walkable cells are connected via flood-fill,
    so the player can never be trapped.  Walls are assigned random types.

    Parameters
    ----------
    width, height
        Map dimensions in cells.  Default 16×16.
    wall_types
        List of wall type integers to randomly assign (1-based index into
        your game's wall colour list).  Default ``[1, 2, 3]``.
    fill_pct
        Fraction of cells to attempt to fill with walls.  Higher = denser.
        Default 0.28 (~28% walls).
    border
        If True (default), the outer edge is always wall (type 1).
    room_size
        Guaranteed clear area around each corner of the border interior
        (creates starting rooms).  Default 3.
    seed
        RNG seed for reproducible maps.  ``None`` uses system entropy.

    Returns
    -------
    (map_2d, walkable_cells)
        ``map_2d`` is a ``list[list[int]]`` grid.
        ``walkable_cells`` is a ``list[tuple[int, int]]`` of ``(row, col)``
        indices guaranteed to be 0 (walkable).
    """
    if wall_types is None:
        wall_types = [1, 2, 3]

    rng = random.Random(seed)

    # Start with all-empty grid.
    grid: list[list[int]] = [[0] * width for _ in range(height)]

    # Border walls.
    if border:
        for c in range(width):
            grid[0][c] = 1
            grid[height - 1][c] = 1
        for r in range(1, height - 1):
            grid[r][0] = 1
            grid[r][width - 1] = 1

    # Ensure starting rooms in corners (guaranteed clear).
    corners = [
        (1, 1),
        (1, width - 2),
        (height - 2, 1),
        (height - 2, width - 2),
    ]
    for cr, cc in corners:
        for dr in range(-room_size + 1, room_size):
            for dc in range(-room_size + 1, room_size):
                rr, cc2 = cr + dr, cc + dc
                if 1 <= rr < height - 1 and 1 <= cc2 < width - 1:
                    grid[rr][cc2] = 0

    # Scatter random walls.
    interior_cells = [
        (r, c)
        for r in range(1, height - 1)
        for c in range(1, width - 1)
    ]
    rng.shuffle(interior_cells)
    wall_count = int(len(interior_cells) * fill_pct)
    for i in range(wall_count):
        r, c = interior_cells[i]
        grid[r][c] = rng.choice(wall_types)

    # Flood-fill from (1, 1) to find all walkable cells reachable from start.
    visited: set[tuple[int, int]] = set()
    stack = [(1, 1)]
    while stack:
        r, c = stack.pop()
        if (r, c) in visited:
            continue
        if r < 0 or r >= height or c < 0 or c >= width:
            continue
        if grid[r][c] != 0:
            continue
        visited.add((r, c))
        stack.extend([(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)])

    # Carve passages to unreachable empty cells.
    all_empty = {
        (r, c)
        for r in range(1, height - 1)
        for c in range(1, width - 1)
        if grid[r][c] == 0
    }
    unreachable = all_empty - visited
    for r, c in unreachable:
        # Carve toward the nearest visited cell.
        best_dist = float("inf")
        best_target = (1, 1)
        for vr, vc in visited:
            d = abs(r - vr) + abs(c - vc)
            if d < best_dist:
                best_dist = d
                best_target = (vr, vc)
        # Carve a straight Manhattan path.
        crt, cct = r, c
        tr, tc = best_target
        while crt != tr:
            crt += 1 if tr > crt else -1
            if 1 <= crt < height - 1 and 1 <= cct < width - 1:
                grid[crt][cct] = 0
                visited.add((crt, cct))
        while cct != tc:
            cct += 1 if tc > cct else -1
            if 1 <= crt < height - 1 and 1 <= cct < width - 1:
                grid[crt][cct] = 0
                visited.add((crt, cct))

    walkable = sorted(visited)
    return grid, walkable


def spawn_points(
    walkable: list[tuple[int, int]],
    count: int = 8,
    *,
    min_spacing: float = 2.5,
    seed: Optional[int] = None,
) -> list[tuple[float, float]]:
    """Select *count* spawn positions from walkable cells.

    Positions are returned as world coordinates (col + 0.5, row + 0.5)
    — cell-centred — suitable for passing to ``RaycastCanvas.set_sprites()``.

    Parameters
    ----------
    walkable
        List of ``(row, col)`` tuples from ``generate_random_map()``.
    count
        Number of spawn points to select.  Clamped to available cells.
    min_spacing
        Minimum Euclidean distance between spawn points (in map units).
    seed
        RNG seed for reproducible placement.

    Returns
    -------
    List of ``(world_x, world_y)`` floats, cell-centred.
    """
    rng = random.Random(seed)

    available: list[tuple[int, int]] = []
    for r, c in walkable:
        if r >= 1 and r < 99 and c >= 1 and c < 99:
            available.append((r, c))

    rng.shuffle(available)

    chosen: list[tuple[int, int]] = []
    for r, c in available:
        world_x = c + 0.5
        world_y = r + 0.5
        too_close = False
        for cr, cc in chosen:
            dist = ((r - cr) ** 2 + (c - cc) ** 2) ** 0.5
            if dist < min_spacing:
                too_close = True
                break
        if not too_close:
            chosen.append((r, c))
        if len(chosen) >= count:
            break

    return [(c + 0.5, r + 0.5) for r, c in chosen]
