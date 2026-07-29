"""
benchmark_engine_perf.py — headless render benchmark for flet_game.

Measures average render cost for the two hottest engine paths:
- RaycastCanvas.render()
- IsoMap.render()

Run:
    cd /home/panger/Coding/python_projects/flet_games
    PYTHONPATH=src /home/panger/Coding/python_projects/venv/bin/python src/test/benchmark_engine_perf.py
"""

from __future__ import annotations

import math
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import IsoMap, RaycastCanvas, SpriteDef


RAYCAST_MAP: list[list[int]] = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 2, 0, 0, 0, 3, 3, 0, 1],
    [1, 0, 0, 2, 0, 0, 0, 0, 0, 3, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 3, 3, 0, 0, 2, 2, 0, 0, 0, 1],
    [1, 0, 3, 0, 0, 0, 2, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 2, 2, 0, 0, 0, 3, 3, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]


def _summarize(name: str, samples_ms: list[float]) -> None:
    avg = statistics.fmean(samples_ms)
    med = statistics.median(samples_ms)
    p95 = statistics.quantiles(samples_ms, n=20)[18] if len(samples_ms) >= 20 else max(samples_ms)
    fps = 1000.0 / avg if avg > 0 else 0.0
    print(f"{name}: avg={avg:.3f} ms  median={med:.3f} ms  p95={p95:.3f} ms  est_fps={fps:.1f}")


def bench_raycast(frames: int = 240) -> None:
    rc = RaycastCanvas(
        width=390,
        height=500,
        columns=80,
        map_data=RAYCAST_MAP,
        wall_colors=["#bb2200", "#1144cc", "#117744"],
        ceiling_color="#1a1a2e",
        floor_color="#2f2f2f",
        fog_distance=10.0,
        max_sprites=16,
    )
    rc._cv.update = lambda: None
    sprites = [
        SpriteDef(x=3.5, y=2.5, image="enemy.png", aspect_ratio=0.35),
        SpriteDef(x=8.5, y=2.5, image="enemy.png", aspect_ratio=0.35),
        SpriteDef(x=8.5, y=8.5, image="item.png", aspect_ratio=1.0, world_height=0.5),
        SpriteDef(x=3.5, y=8.5, image="enemy.png", aspect_ratio=0.35),
    ]
    rc.set_sprites(sprites)
    samples_ms: list[float] = []
    px = py = 5.5

    for frame in range(frames):
        angle = (frame / frames) * math.tau
        start = time.perf_counter()
        rc.render(px, py, angle)
        samples_ms.append((time.perf_counter() - start) * 1000.0)

    _summarize("RaycastCanvas.render", samples_ms)


def _make_bench_isomap(render_walls: bool) -> IsoMap:
    iso = IsoMap(
        cols=32,
        rows=32,
        tile_w=64,
        tile_h=32,
        viewport_w=800,
        viewport_h=600,
        border=False,
        render_walls=render_walls,
    )
    iso._canvas.update = lambda: None

    for ty in range(32):
        for tx in range(32):
            wall_h = 24 if (tx + ty) % 7 == 0 else 0
            color = "#5b6f42" if wall_h == 0 else "#6a5a48"
            iso.set_tile(tx, ty, color=color, wall_h=wall_h)
    iso.center_on(16, 16)
    iso.render()
    return iso


def bench_isomap(frames: int = 240, render_walls: bool = True) -> None:
    iso = _make_bench_isomap(render_walls)
    samples_ms: list[float] = []
    for frame in range(frames):
        iso.pan(math.sin(frame * 0.08) * 2.0, math.cos(frame * 0.05) * 1.5)
        start = time.perf_counter()
        iso.render()
        samples_ms.append((time.perf_counter() - start) * 1000.0)

    label = "IsoMap.render (walls)" if render_walls else "IsoMap.render (flat)"
    _summarize(label, samples_ms)


def main() -> None:
    print("flet_game headless benchmark")
    bench_raycast()
    bench_isomap(render_walls=True)
    bench_isomap(render_walls=False)


if __name__ == "__main__":
    main()