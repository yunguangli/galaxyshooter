"""
test_platformer.py — PlatformerWorld prefab demo.

Shows how to build a complete scrolling platformer by changing props.
Compare with test_camera.py: this does the same thing in far less code
because PlatformerWorld handles scene, camera, physics, and input setup.

Controls
--------
← / A             move left
→ / D             move right
Space / ↑ / W     jump  (double-tap mid-air for second jump if max_jumps=2)
Q / Esc           quit

Tunable props
-------------
Edit WORLD_PROPS and PLATFORMS below to customise the game.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import PlatformerWorld, Label

# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — Tune the game feel
# ═══════════════════════════════════════════════════════════════════════════════
# Change any value below and re-run to see the effect instantly.
# ───────────────────────────────────────────────────────────────────────────────
WORLD_PROPS = dict(
    world_width      = 3200,        # total world width in pixels
    viewport_width   = 800,         # visible area width (= window width)
    viewport_height  = 480,         # visible area height (= window height)
    bgcolor          = "#0d0d1f",   # background colour (CSS hex or name)
    floor_y          = 415,         # Y coordinate of the floor top edge (px)
    floor_color      = "#3a6b2a",  # floor fill colour
    floor_edge_color = "#5a9e3c",  # thin bright strip at the floor top edge
    player_color     = "#00e5ff",  # player sprite colour
    player_width     = 40,         # player width in pixels
    player_height    = 56,         # player height in pixels
    player_start_x   = 60,         # starting X position in world coordinates
    walk_speed       = 260,        # horizontal speed (px / s)
    gravity          = 900,        # downward acceleration (px / s²)
    jump_speed       = 530,        # upward velocity when jumping (px / s)
    max_jumps        = 2,          # 1 = single jump, 2 = double jump
    coyote_time      = 0.08,       # grace period to jump after walking off edge
    jump_buffer_time = 0.10,       # how long a jump press is remembered
)

# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — Design the level layout
# ═══════════════════════════════════════════════════════════════════════════════
# Each platform is: (x, y, width, height)
#   x, y   = top-left corner in world coordinates
#   width  = how wide the platform is (px)
#   height = how tall the platform is (px)
#
# Platforms are one-way: the player can jump through them from below,
# but lands on top when falling.
# ───────────────────────────────────────────────────────────────────────────────
PLATFORMS = [
    (250,  350,  130,  16),   # platform 1  — starting area
    (460,  305,  120,  16),   # platform 2  — small step up
    (680,  330,  130,  16),   # platform 3  — medium height
    (920,  360,  100,  16),   # platform 4  — low and short
    (1140, 300,  120,  16),   # platform 5  — high, needs a good jump
    (1380, 340,  110,  16),   # platform 6  — mid-height
    (1620, 320,  130,  16),   # platform 7  — wide, safe landing
    (1860, 295,  120,  16),   # platform 8  — high up
    (2100, 350,  110,  16),   # platform 9  — back to low
    (2340, 310,  120,  16),   # platform 10 — medium
    (2580, 330,  130,  16),   # platform 11 — wide
    (2820, 300,  110,  16),   # platform 12 — high
    (3060, 345,  120,  16),   # platform 13 — final platform
]


async def main(page: ft.Page) -> None:
    page.title   = "flet_game — PlatformerWorld Demo"
    page.bgcolor = ft.Colors.BLACK

    # ═══════════════════════════════════════════════════════════════════════════
    #  STEP 3 — Create the world (one call does it all)
    # ═══════════════════════════════════════════════════════════════════════════
    # PlatformerWorld automatically creates:
    #   - A Scene (screen) with background + input
    #   - A Camera (scrolling viewport for the wide world)
    #   - A ground Sprite (the floor you walk on)
    #   - A player Sprite (you control this)
    #   - A PlatformerController (handles physics + input)
    #   - A GameLoop (60 fps clock shared by all callbacks)
    # ───────────────────────────────────────────────────────────────────────────
    world = PlatformerWorld(page, **WORLD_PROPS)

    # ═══════════════════════════════════════════════════════════════════════════
    #  STEP 4 — Add parallax background layers
    # ═══════════════════════════════════════════════════════════════════════════
    # Layers scroll at different speeds to create depth.
    #   speed=0.0  → fixed (like the sky)
    #   speed=0.25 → slow (distant mountains)
    #   speed=0.55 → medium (hills)
    #   speed=1.0  → same as the world (no parallax)
    # ───────────────────────────────────────────────────────────────────────────
    sky   = world.add_layer(speed=0.25)   # distant sky / stars
    hills = world.add_layer(speed=0.55)   # midground hills

    # ── Sky: alternating dark-blue strips ─────────────────────────────────────
    for i in range(8):
        sky.controls.append(
            ft.Container(
                width=400, height=415,
                bgcolor="#12123a" if i % 2 == 0 else "#0f0f30",
                left=float(i * 400), top=0.0,
            )
        )
    # ── Stars: tiny white dots scattered across the sky ────────────────────────
    for sx, sy in [
        (40,30),(200,20),(320,60),(530,90),(750,55),(910,75),(1050,20),
        (1250,50),(1380,70),(1600,85),(1840,65),(2080,80),(2200,20),(2430,40),
        (2680,30),(2800,55),(3050,70),(3180,60),
    ]:
        sky.controls.append(
            ft.Container(width=3, height=3, bgcolor="#ffffff",
                         left=float(sx), top=float(sy))
        )

    # ── Hills: rounded green blobs in the midground ───────────────────────────
    for hx, hh, hw, hc in [
        (0,  290,100,"#1e3f1a"),(220,310,130,"#19361a"),(380,295,100,"#1e3f1a"),
        (540,320, 90,"#19361a"),(720,300,120,"#1e3f1a"),(920,285,110,"#19361a"),
        (1100,310,100,"#1e3f1a"),(1280,295,130,"#19361a"),
        (1440,300,110,"#1e3f1a"),(1640,315, 95,"#1e3f1a"),
        (1820,295,125,"#19361a"),(2000,310,105,"#1e3f1a"),
        (2180,300,120,"#19361a"),(2360,285,130,"#1e3f1a"),
        (2540,310,100,"#19361a"),(2720,295,115,"#1e3f1a"),
        (2900,315,105,"#19361a"),(3060,300,120,"#1e3f1a"),
    ]:
        hills.controls.append(
            ft.Container(
                width=float(hw), height=float(hh),
                bgcolor=hc,
                border_radius=ft.BorderRadius.all(36),
                left=float(hx), top=float(415 - hh),
            )
        )

    # ═══════════════════════════════════════════════════════════════════════════
    #  STEP 5 — Place platforms
    # ═══════════════════════════════════════════════════════════════════════════
    # Each platform is added to both the camera (so it scrolls) and the
    # controller (so the player can land on it).
    # ───────────────────────────────────────────────────────────────────────────
    for px, py, pw, ph in PLATFORMS:
        world.add_platform(px, py, pw, ph)

    # ═══════════════════════════════════════════════════════════════════════════
    #  STEP 6 — Add decorative collectibles (coins)
    # ═══════════════════════════════════════════════════════════════════════════
    # These are just visual — no collision logic in this demo.
    # Each coin sits above a platform as a golden circle.
    # ───────────────────────────────────────────────────────────────────────────
    for cx, cy in [
        (280,310),(490,265),(710,290),(950,320),(1170,260),
        (1410,300),(1650,280),(1890,255),(2130,310),(2370,270),
        (2610,290),(2850,260),(3090,305),
    ]:
        world.cam.add(
            ft.Container(width=16, height=16, bgcolor="#ffd700",
                         border_radius=ft.BorderRadius.all(8),
                         left=float(cx), top=float(cy)),
            z=2,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    #  STEP 7 — Add HUD (fixed on screen, not scrolled)
    # ═══════════════════════════════════════════════════════════════════════════
    # HUD labels are added to the Scene (not the Camera), so they stay in
    # the same position on screen even as the world scrolls.
    # ───────────────────────────────────────────────────────────────────────────
    max_cam_x = WORLD_PROPS["world_width"] - WORLD_PROPS["viewport_width"]
    hud_cam   = Label(text="Camera X:     0", x=10, y=8,
                      color="#ffffff", size=14)
    hud_jump  = Label(text="Jumps left: 2",   x=10, y=28,
                      color="#aaaaaa", size=12)
    hint      = Label(
        text=(
            "← → WASD : move   |   Space / ↑ / W : jump"
            "   |   Q / Esc : quit"
        ),
        x=10, y=WORLD_PROPS["viewport_height"] - 26,
        color="#555555", size=12,
    )
    world.scene.add(hud_cam,  z=10)
    world.scene.add(hud_jump, z=10)
    world.scene.add(hint,     z=10)

    # ═══════════════════════════════════════════════════════════════════════════
    #  STEP 8 — Add per-frame logic (HUD update)
    # ═══════════════════════════════════════════════════════════════════════════
    # This callback runs every frame (60 times per second).
    # It updates the HUD labels with the latest camera position and jump count.
    # ───────────────────────────────────────────────────────────────────────────
    @world.loop.on_update
    def tick(dt: float) -> None:
        hud_cam.text  = f"Camera X: {int(world.cam.x):4d} / {max_cam_x}"
        hud_jump.text = f"Jumps left: {world.ctrl.jumps_left}"

    # ═══════════════════════════════════════════════════════════════════════════
    #  STEP 9 — Add quit controls
    # ═══════════════════════════════════════════════════════════════════════════
    # Press Q or Escape to stop the loop and close the scene.
    # ───────────────────────────────────────────────────────────────────────────
    @world.scene.input.on_key_down("q")
    @world.scene.input.on_key_down("escape")
    async def quit_game(e=None):
        world.loop.stop()
        world.scene.unmount()

    # ═══════════════════════════════════════════════════════════════════════════
    #  STEP 10 — Launch!
    # ═══════════════════════════════════════════════════════════════════════════
    # mount() adds the scene to the page and starts the game loop.
    # This must be the LAST call — everything else must be set up before it.
    # ───────────────────────────────────────────────────────────────────────────
    world.mount()


_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
ft.run(main, assets_dir=_ASSETS_DIR)
