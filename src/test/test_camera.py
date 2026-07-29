"""
test_camera.py — Camera / Viewport demo for flet_game.

A side-scrolling world 4× wider than the viewport (3 200 × 480 px).
The camera follows the player with smooth easing while two parallax
layers (sky and hills) scroll at different speeds, giving depth.

Controls
--------
← / A         move left
→ / D         move right
Space / ↑ / W jump
Q / Esc       quit
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import Camera, Sprite, Label, Scene, GameLoop

# ── Constants ──────────────────────────────────────────────────────────────────
VIEWPORT_W, VIEWPORT_H = 800, 480
WORLD_W,    WORLD_H    = 3200, 480

FLOOR_Y      = 415          # top edge of the ground strip
PLAYER_W     = 40
PLAYER_H     = 56
GRAVITY      = 900          # px / s²
JUMP_VY      = -530         # px / s  (negative = upward in Flet coords)
PLAYER_SPEED = 260          # px / s


# ── Helper — place a raw container in a parallax layer ────────────────────────
def _raw(cam: Camera, layer: ft.Stack, x, y, w, h, color, radius=0) -> None:
    """Add a positioned ft.Container to a parallax layer via cam.add_to_layer()."""
    cam.add_to_layer(
        ft.Container(
            width=float(w), height=float(h),
            bgcolor=color,
            border_radius=ft.BorderRadius.all(radius) if radius else None,
            left=float(x), top=float(y),
        ),
        layer,
    )


async def main(page: ft.Page) -> None:
    page.title  = "flet_game — Camera Demo"
    page.bgcolor = ft.Colors.BLACK

    scene = Scene(page, width=VIEWPORT_W, height=VIEWPORT_H, bgcolor="#0d0d1f")
    inp   = scene.input

    # ── Camera ─────────────────────────────────────────────────────────────────
    cam = Camera(
        world_width=WORLD_W,   world_height=WORLD_H,
        viewport_width=VIEWPORT_W, viewport_height=VIEWPORT_H,
    )
    scene.add(cam.control)

    # ── Parallax layer 0 — distant sky / stars (25 % camera speed) ────────────
    sky = cam.add_layer(speed=0.25)
    # Two tiled rectangles that together span 4× viewport (alternating shade)
    for i in range(8):
        _raw(cam, sky, i * 400, 0, 400, FLOOR_Y,
             "#12123a" if i % 2 == 0 else "#0f0f30")
    # Sprinkle some "stars" (tiny white squares)
    star_coords = [
        (40, 30), (120, 80), (200, 20), (320, 60), (450, 40),
        (530, 90), (640, 15), (750, 55), (820, 35), (910, 75),
        (1010,20), (1120,50), (1250,30), (1380,70), (1500,40),
        (1600,85), (1720,25), (1840,65), (1950,45), (2080,80),
        (2200,20), (2320,60), (2430,40), (2550,75), (2680,30),
        (2800,55), (2920,20), (3050,70), (3120,35), (3180,60),
    ]
    for sx, sy in star_coords:
        _raw(cam, sky, sx, sy, 3, 3, "#ffffff")

    # ── Parallax layer 1 — midground hills (55 % camera speed) ───────────────
    hills = cam.add_layer(speed=0.55)
    hill_defs = [
        (0,   290, 100, "#1e3f1a"),  (220, 310, 130, "#19361a"),
        (380, 295, 100, "#1e3f1a"),  (540, 320,  90, "#19361a"),
        (720, 300, 120, "#1e3f1a"),  (920, 285, 110, "#19361a"),
        (1100,310, 100, "#1e3f1a"), (1280,295, 130, "#19361a"),
        (1440,300, 110, "#1e3f1a"), (1640,315,  95, "#1e3f1a"),
        (1820,295, 125, "#19361a"), (2000,310, 105, "#1e3f1a"),
        (2180,300, 120, "#19361a"), (2360,285, 130, "#1e3f1a"),
        (2540,310, 100, "#19361a"), (2720,295, 115, "#1e3f1a"),
        (2900,315, 105, "#19361a"), (3060,300, 120, "#1e3f1a"),
    ]
    for hx, hh, hw, hc in hill_defs:
        _raw(cam, hills, hx, FLOOR_Y - hh, hw, hh, hc, radius=36)

    # ── World — ground ─────────────────────────────────────────────────────────
    ground = Sprite(x=0, y=FLOOR_Y, width=WORLD_W, height=WORLD_H - FLOOR_Y,
                    color="#3a6b2a")
    cam.add(ground, z=-1)

    # Ground detail — lighter strip at the very top edge
    ground_edge = Sprite(x=0, y=FLOOR_Y, width=WORLD_W, height=6, color="#5a9e3c")
    cam.add(ground_edge, z=-1)

    # ── World — distance markers (every 800 px = 1 "km") ─────────────────────
    for km in range(1, 4):
        pole = Sprite(x=km * 800 - 2, y=FLOOR_Y - 70,
                      width=4, height=70, color="#888888")
        cam.add(pole, z=0)
        tag = Label(text=f"{km} km", x=km * 800 - 22, y=FLOOR_Y - 94,
                    color="#cccccc", size=13)
        cam.add(tag, z=0)

    # ── World — floating platforms ─────────────────────────────────────────────
    plat_defs = [
        (250,  350, 130, 16), (480,  305, 110, 16),
        (700,  330, 140, 16), (930,  360,  90, 16),
        (1080, 300, 120, 16), (1280, 340, 100, 16),
        (1480, 320, 130, 16), (1700, 295, 110, 16),
        (1920, 350, 100, 16), (2120, 310, 120, 16),
        (2340, 330, 130, 16), (2560, 300, 100, 16),
        (2760, 345, 110, 16), (2960, 320, 120, 16),
    ]
    plat_sprites: list[Sprite] = []
    for px, py, pw, ph in plat_defs:
        p = Sprite(x=px, y=py, width=pw, height=ph,
                   color="#4a7c35", border_radius=4)
        cam.add(p, z=1)
        plat_sprites.append(p)

    # ── World — obstacles / pillars ────────────────────────────────────────────
    pillar_xs = [550, 1050, 1550, 2050, 2550, 3050]
    for px in pillar_xs:
        cam.add(Sprite(x=px, y=FLOOR_Y - 80, width=28, height=80,
                       color="#8b1a1a"), z=1)

    # ── World — collectible coins ──────────────────────────────────────────────
    coin_defs = [
        (280, 310), (510, 265), (730, 290), (960, 320),
        (1110,260), (1310,300), (1510,280), (1730,255),
        (1950,310), (2150,270), (2370,290), (2590,260),
        (2790,305), (2990,280),
    ]
    for cx, cy in coin_defs:
        cam.add(Sprite(x=cx, y=cy, width=16, height=16,
                       color="#ffd700", border_radius=8), z=2)

    # ── World — player ─────────────────────────────────────────────────────────
    player = Sprite(
        x=60, y=FLOOR_Y - PLAYER_H,
        width=PLAYER_W, height=PLAYER_H,
        color="#00e5ff", border_radius=8, tag="player",
    )
    # Eyes (decorative — two tiny dark circles)
    cam.add(player, z=5)

    # ── HUD — fixed on screen, not scrolled ───────────────────────────────────
    cam_lbl  = Label(text="Camera X:  0 / 2400", x=10, y=8,
                     color="#ffffff", size=14)
    pos_lbl  = Label(text="Player X:  60", x=10, y=28,
                     color="#aaaaaa", size=12)
    hint_lbl = Label(
        text="← → WASD : move   |   Space / ↑ / W : jump   |   Q / Esc : quit",
        x=10, y=VIEWPORT_H - 26, color="#777777", size=12,
    )
    scene.add(cam_lbl,  z=10)
    scene.add(pos_lbl,  z=10)
    scene.add(hint_lbl, z=10)

    # ── Physics state ──────────────────────────────────────────────────────────
    player_vy = 0.0
    on_ground  = True

    # ── Game loop ──────────────────────────────────────────────────────────────
    loop = GameLoop(page)

    def update(dt: float) -> None:
        nonlocal player_vy, on_ground

        # — Horizontal movement
        dx = 0.0
        if inp.is_key_down("left") or inp.is_key_down("a"):
            dx = -PLAYER_SPEED * dt
        if inp.is_key_down("right") or inp.is_key_down("d"):
            dx = PLAYER_SPEED * dt
        player.x = max(0.0, min(WORLD_W - PLAYER_W, player.x + dx))

        # — Gravity
        player_vy += GRAVITY * dt
        player.y  += player_vy * dt

        # — Floor collision
        if player.y >= FLOOR_Y - PLAYER_H:
            player.y  = float(FLOOR_Y - PLAYER_H)
            player_vy = 0.0
            on_ground  = True
        else:
            # Platform collision — top-edge only, while falling
            on_ground = False
            prev_bottom = (player.y - player_vy * dt) + PLAYER_H
            curr_bottom = player.y + PLAYER_H
            for p in plat_sprites:
                if (
                    player.x + PLAYER_W > p.x
                    and player.x < p.x + p.width
                    and prev_bottom <= p.y + 4        # was above
                    and curr_bottom >= p.y             # now overlaps top
                    and player_vy > 0                  # falling down
                ):
                    player.y  = p.y - PLAYER_H
                    player_vy = 0.0
                    on_ground  = True
                    break

        # — Jump
        if on_ground and (
            inp.is_key_down("up")
            or inp.is_key_down("space")
            or inp.is_key_down("w")
        ):
            player_vy = JUMP_VY
            on_ground  = False

        # — Camera: smooth follow on X, snap on Y (horizontal scroller feel)
        cam.follow(player, lerp=0.10, y_only=False)

        # — HUD
        max_cam_x = WORLD_W - VIEWPORT_W
        cam_lbl.text = f"Camera X: {int(cam.x):4d} / {max_cam_x}"
        pos_lbl.text = f"Player X: {int(player.x):4d}"

    # — Quit on Q or Escape
    @inp.on_key_down("q")
    @inp.on_key_down("escape")
    async def quit_game(e=None):
        loop.stop()
        scene.unmount()

    loop.add_callback(update)
    scene.mount()
    loop.start()


_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
ft.run(main, assets_dir=_ASSETS_DIR)
