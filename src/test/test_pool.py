"""
test_pool.py — Step 17: ObjectPool pre-allocated sprite reuse
=============================================================
Run with:
    python src/test/test_pool.py
  or:
    flet run src/test/test_pool.py

What is tested
--------------
  ✓ ObjectPool(factory, max_size, scene, z)
  ✓ prewarm()       — pre-allocates all objects at scene startup
  ✓ acquire()       — pulls an idle object from the free list
  ✓ release()       — returns object to free list
  ✓ release_all_and_hide() — bulk return for game-over / scene reset
  ✓ is_exhausted    — True when all max_size objects are in use
  ✓ active_count / free_count / size — pool statistics
  ✓ No new Sprite allocations during gameplay — pool reuses the same objects

Demo
----
A cannon fires yellow bullets from the left.  Each bullet is acquired from a
pool of 20.  When it exits the right edge it is released back.  A live counter
shows active/free counts.  Pressing SPACE fires a burst of 5 bullets.
Pressing C clears all active bullets.  Pool exhaustion is shown in red.
Press ESC or Q to quit.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
import flet as ft
from flet_game import Sprite, GameLoop, Label, Scene, Input, ObjectPool

W, H = 640, 420
POOL_MAX  = 20          # never allocate more than this many bullets
BSPEED_BASE = 320.0     # px/s base bullet speed


def main(page: ft.Page) -> None:
    page.title = "flet_game — Step 17: ObjectPool"
    page.bgcolor = ft.Colors.GREY_900
    page.padding = 0
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # ── Scene ─────────────────────────────────────────────────────────────────
    scene = Scene(page, width=W, height=H, bgcolor="#0a0a1a")
    inp   = scene.input
    loop  = GameLoop(page, fps=60)

    # ── Cannon (static) ───────────────────────────────────────────────────────
    cannon = Sprite(x=20, y=H//2-15, width=30, height=30,
                    color="#4cc9f0", border_radius=4)
    scene.add(cannon, z=5)

    # ── HUD labels ────────────────────────────────────────────────────────────
    lbl_active = Label(text="active:  0", x=10, y=10, color="white", size=14, bold=True)
    lbl_free   = Label(text="free:   20", x=10, y=32, color="white", size=14)
    lbl_total  = Label(text="total:  20", x=10, y=54, color="white", size=14)
    lbl_fired  = Label(text="fired:   0", x=10, y=76, color="#aaa",  size=12)
    lbl_exhaust= Label(text="",           x=10, y=98, color="red",   size=14, bold=True)
    lbl_hint   = Label(
        text="SPACE = burst of 5  |  C = clear all  |  ESC = quit",
        x=W//2-200, y=H-24, color="#555", size=12,
    )
    for lbl in (lbl_active, lbl_free, lbl_total, lbl_fired, lbl_exhaust, lbl_hint):
        scene.add(lbl, z=10)

    # ── Bullet pool ───────────────────────────────────────────────────────────
    # Factory: create a hidden bullet sprite with auto-add to scene (z=4).
    pool = ObjectPool(
        factory=lambda: Sprite(x=-20, y=0, width=10, height=6,
                               color="#f4d03f", border_radius=3),
        max_size=POOL_MAX,
        scene=scene,
        z=4,
    )
    pool.prewarm()  # pre-create all POOL_MAX bullets now — zero cost during play

    # Per-bullet velocity stored alongside each object (using a dict keyed by id).
    bullet_vy: dict[int, float] = {}

    fired_total = [0]

    def fire(n: int = 1) -> None:
        for _ in range(n):
            b = pool.acquire()
            if b is None:
                lbl_exhaust.text = "⚠ pool exhausted!"
                lbl_exhaust.update()
                return
            lbl_exhaust.text = ""
            b.x = 60
            b.y = H // 2 - 3 + random.uniform(-30, 30)
            speed = BSPEED_BASE + random.uniform(-60, 80)
            bullet_vy[id(b)] = speed
            b.show()
            fired_total[0] += 1

    # ── Physics ───────────────────────────────────────────────────────────────
    @loop.on_update
    def update(dt: float) -> None:
        to_release = []
        for b in pool.active:
            spd = bullet_vy.get(id(b), BSPEED_BASE)
            b.x += spd * dt
            if b.x > W + 10:
                to_release.append(b)

        for b in to_release:
            b.hide()
            pool.release(b)

        # Update HUD
        ex = pool.is_exhausted
        lbl_active.text = f"active: {pool.active_count:3d}"
        lbl_free.text   = f"free:   {pool.free_count:3d}"
        lbl_total.text  = f"total:  {pool.size:3d}  / {POOL_MAX}"
        lbl_fired.text  = f"fired:  {fired_total[0]:4d} total (0 new allocs)"
        lbl_active.color = "red" if ex else "white"
        lbl_active.update()
        lbl_free.update()
        lbl_total.update()
        lbl_fired.update()

    # ── Auto-fire every 0.3 s ─────────────────────────────────────────────────
    auto_timer = [0.0]

    @loop.on_update
    def auto_fire(dt: float) -> None:
        auto_timer[0] += dt
        if auto_timer[0] >= 0.30:
            auto_timer[0] = 0.0
            fire(1)

    # ── Keyboard ─────────────────────────────────────────────────────────────
    @inp.on_key_down("space")
    def burst(e=None): fire(5)

    @inp.on_key_down("c")
    def clear_all(e=None):
        pool.release_all_and_hide()
        lbl_exhaust.text = ""
        lbl_exhaust.update()

    @inp.on_key_down("escape")
    @inp.on_key_down("q")
    async def quit(e=None): await page.window.close()

    # ── Touch fire ────────────────────────────────────────────────────────────
    @inp.on_click
    def on_tap(x, y): fire(3)

    # ── Mount ─────────────────────────────────────────────────────────────────
    scene.mount()
    page.update()
    loop.start()


ft.run(main)
