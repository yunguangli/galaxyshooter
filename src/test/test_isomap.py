"""
test_isomap.py — Interactive demo for IsoMap (Step 18).

Controls
--------
WASD / Arrow keys  — pan the map
Tab                — toggle between flat map and dungeon map (from mapgen)
Click / Tap        — highlight a tile (cycle colour) and print coords
Escape / Q         — quit

What this demonstrates
----------------------
- Diamond tile rendering on a flet.canvas.Canvas
- Wall extrusion (3-D isometric blocks) with auto-shaded faces
- Painter's algorithm depth sorting
- View-frustum culling (only visible tiles rendered)
- Camera panning with keyboard
- Tap-to-tile coordinate conversion and click callbacks
- mapgen.generate_random_map() integration for a dungeon layout
- FPS counter via GameLoop.fps
"""

import sys
import os
import math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import flet as ft
import flet.canvas as cv
from flet_game import (
    IsoMap,
    Scene,
    GameLoop,
    InputManager,
    Label,
    generate_random_map,
)

# ── Layout constants ──────────────────────────────────────────────────────────
W, H    = 800, 600
COLS    = 24
ROWS    = 24
TILE_W  = 64
TILE_H  = 32

# ── Terrain palette ───────────────────────────────────────────────────────────
GRASS   = "#4a7c3f"
DIRT    = "#8b6340"
WATER   = "#2a5f8f"
STONE   = "#6b6b7b"
SAND    = "#c4a265"
SNOW    = "#dce8ee"
WALL    = "#555566"
WALL_H  = 28   # px extruded height for wall tiles

# Highlight colours cycled on click
HIGHLIGHT_COLORS = ["#ffdd44", "#ff8822", "#ff4444", "#aa44ff", "#44aaff"]

# ── Build helpers ─────────────────────────────────────────────────────────────

def build_flat_map(iso: IsoMap) -> None:
    """Flat terrain map with varied tile types."""
    import random
    rng = random.Random(42)

    # Base: mostly grass with patches of dirt/sand/snow
    for ty in range(ROWS):
        for tx in range(COLS):
            r = rng.random()
            if r < 0.55:
                color = GRASS
            elif r < 0.70:
                color = DIRT
            elif r < 0.80:
                color = SAND
            elif r < 0.88:
                color = STONE
            else:
                color = SNOW
            iso.set_tile(tx, ty, color=color)

    # Water "pond" in the middle
    cx, cy = COLS // 2, ROWS // 2
    for dy in range(-2, 3):
        for dx in range(-3, 4):
            iso.set_tile(cx + dx, cy + dy, color=WATER)

    # Some wall/block tiles (3-D boxes)
    wall_positions = [
        (3, 3), (4, 3), (3, 4),
        (18, 6), (19, 6), (18, 7), (19, 7),
        (10, 16), (10, 17),
        (6, 18),
    ]
    for tx, ty in wall_positions:
        iso.set_tile(tx, ty, color="#887755", wall_h=WALL_H)


def build_dungeon_map(iso: IsoMap) -> None:
    """Dungeon layout from mapgen — walls become extruded blocks."""
    grid, walkable = generate_random_map(
        COLS, ROWS,
        room_attempts=14,
        min_room=3, max_room=6,
        corridor_width=1,
        seed=99,
    )
    for ty in range(ROWS):
        for tx in range(COLS):
            if grid[ty][tx] == 0:
                # Wall cell — dark stone block
                iso.set_tile(tx, ty, color=WALL, wall_h=WALL_H)
            else:
                # Floor cell — stone flags
                iso.set_tile(tx, ty, color=STONE, wall_h=0)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(page: ft.Page) -> None:
    page.title    = "IsoMap — flet_game Step 18"
    page.bgcolor  = ft.Colors.BLACK
    page.padding  = 0

    scene = Scene(page, width=W, height=H, bgcolor="#1a1a2e")
    inp   = scene.input
    loop  = GameLoop(page, fps=60)

    # ── Create IsoMap ─────────────────────────────────────────────────────
    iso = IsoMap(
        cols=COLS, rows=ROWS,
        tile_w=TILE_W, tile_h=TILE_H,
        viewport_w=W, viewport_h=H,
        default_color=GRASS,
        border=True,
    )
    iso.center_on(COLS / 2, ROWS / 2)
    build_flat_map(iso)

    # Add the IsoMap control to scene — it fills the full canvas
    scene.add(iso.control, z=0)

    # ── HUD labels ────────────────────────────────────────────────────────
    fps_label  = Label(x=8,  y=8,  text="FPS: --", size=14, color="#aaffaa", bold=True)
    info_label = Label(x=8,  y=28, text="WASD: pan  |  Arrows: move person  |  Tab: toggle  |  Click: tile",
                       size=12, color="#aaaaaa")
    tile_label = Label(x=8,  y=48, text="", size=13, color="#ffdd44")
    mode_label = Label(x=W - 10, y=8, text="[flat]", size=14, color="#88aaff",
                       bold=True)
    # Align mode_label to the right via x offset (manual, since Label has no
    # right-alignment — we update x after mount)

    scene.add(fps_label,  z=10)
    scene.add(info_label, z=10)
    scene.add(tile_label, z=10)
    scene.add(mode_label, z=10)

    # ── Character (isometric person) ──────────────────────────────────────
    CHAR_BOB_AMP  = 3.0    # vertical bounce height in px
    CHAR_BOB_FREQ = 6.0    # bobs per second while stepping
    CHAR_STEP     = 0.18   # seconds between tile steps

    char_tx   = [COLS // 2]     # character tile position (mutable cells)
    char_ty   = [ROWS // 4]
    char_cool = [0.0]            # step cooldown; >0 while mid-step animation plays
    char_walk = [0.0]            # accumulated time used as bob phase

    def _char_quad(color: str) -> cv.Path:
        """Pre-allocate a 4-vertex cv.Path for the character shapes."""
        return cv.Path(
            elements=[
                cv.Path.MoveTo(0.0, 0.0), cv.Path.LineTo(0.0, 0.0),
                cv.Path.LineTo(0.0, 0.0), cv.Path.LineTo(0.0, 0.0),
                cv.Path.Close(),
            ],
            paint=ft.Paint(style=ft.PaintingStyle.FILL, color=color),
        )

    char_shadow = _char_quad("#00000055")           # translucent diamond shadow
    char_body   = _char_quad("#4488cc")             # blue shirt / torso
    char_head   = cv.Circle(
        x=0.0, y=0.0, radius=7,
        paint=ft.Paint(style=ft.PaintingStyle.FILL, color="#f5c89a"),
    )
    char_canvas = cv.Canvas(
        shapes=[char_shadow, char_body, char_head],
        width=W, height=H,
    )
    scene.add(char_canvas, z=5)   # above map (z=0), below HUD (z=10)

    def render_char() -> None:
        """Mutate pre-allocated character shapes in-place (zero new objects)."""
        tx, ty = char_tx[0], char_ty[0]
        hw, hh  = TILE_W / 2.0, TILE_H / 2.0
        top_x   = iso.origin_x + (tx - ty) * hw
        top_y   = iso.origin_y + (tx + ty) * hh
        cx      = top_x + hw      # horizontal centre of tile diamond
        cy      = top_y + hh      # vertical centre of tile diamond

        # Walking bob — only while step cooldown is running
        moving = char_cool[0] > 0.0
        bob    = math.sin(char_walk[0] * CHAR_BOB_FREQ * math.pi * 2) * CHAR_BOB_AMP if moving else 0.0

        # Shadow — squashed diamond on the tile surface
        sw, sh = hw * 0.55, hh * 0.45
        se = char_shadow.elements
        se[0].x, se[0].y = cx,      cy - sh
        se[1].x, se[1].y = cx + sw, cy
        se[2].x, se[2].y = cx,      cy + sh
        se[3].x, se[3].y = cx - sw, cy

        # Body — narrow upright rectangle above tile centre
        bw, bh  = 8, 18
        foot_y  = cy - 2 - bob
        head_y  = foot_y - bh
        be = char_body.elements
        be[0].x, be[0].y = cx - bw, foot_y
        be[1].x, be[1].y = cx + bw, foot_y
        be[2].x, be[2].y = cx + bw, head_y
        be[3].x, be[3].y = cx - bw, head_y

        # Head — circle sitting just above body, also bobs
        char_head.x = cx
        char_head.y = head_y - 7 - bob

        if char_canvas.page:
            char_canvas.update()

    # ── Map mode toggle ────────────────────────────────────────────────────
    current_mode = ["flat"]   # mutable cell

    def switch_map(mode: str) -> None:
        if mode == "flat":
            build_flat_map(iso)
            mode_label.text = "[flat]"
        else:
            build_dungeon_map(iso)
            mode_label.text = "[dungeon]"
        iso.render()

    @inp.on_key_down("tab")
    def toggle_map(e=None) -> None:
        current_mode[0] = "dungeon" if current_mode[0] == "flat" else "flat"
        switch_map(current_mode[0])
        tile_label.text = ""

    # ── Tile click highlight ───────────────────────────────────────────────
    selected: dict = {}   # {(tx,ty): highlight_index}

    def on_tile_click(tx: int, ty: int, tile) -> None:
        key = (tx, ty)
        idx = selected.get(key, -1)
        if idx == -1:
            # First click — save original colour and highlight
            selected[key] = 0
            tile.data = {"orig_color": tile.color, "orig_top": tile.top_color}
            tile.color     = HIGHLIGHT_COLORS[0]
            tile.top_color = HIGHLIGHT_COLORS[0]
        else:
            next_idx = idx + 1
            if next_idx >= len(HIGHLIGHT_COLORS):
                # Restore original colour and de-select
                orig = tile.data
                tile.color     = orig["orig_color"]
                tile.top_color = orig["orig_top"]
                tile.data      = None
                del selected[key]
            else:
                selected[key] = next_idx
                tile.color     = HIGHLIGHT_COLORS[next_idx]
                tile.top_color = HIGHLIGHT_COLORS[next_idx]

        tile_label.text = f"Tile ({tx}, {ty})  tag={tile.tag!r}  passable={tile.passable}"
        iso.render()

    iso.on_tile_click(on_tile_click)

    # ── Keyboard panning ───────────────────────────────────────────────────
    PAN_SPEED = 180.0   # px per second

    @loop.on_update
    def update(dt: float) -> None:
        fps_label.text = f"FPS: {loop.fps:.0f}"

        # ── WASD: free camera pan ──────────────────────────────────────────────
        dx, dy = 0.0, 0.0
        if inp.is_key_down("a"): dx =  PAN_SPEED * dt
        if inp.is_key_down("d"): dx = -PAN_SPEED * dt
        if inp.is_key_down("w"): dy =  PAN_SPEED * dt
        if inp.is_key_down("s"): dy = -PAN_SPEED * dt
        needs_char = False
        if dx or dy:
            iso.pan(dx, dy)
            iso.render()
            needs_char = True    # panning shifts character's screen position

        # ── Arrow keys: move character, camera follows ─────────────────────────
        char_cool[0] = max(0.0, char_cool[0] - dt)
        if char_cool[0] == 0.0:
            ntx, nty = char_tx[0], char_ty[0]
            if   inp.is_key_down("arrowup"):    nty -= 1
            elif inp.is_key_down("arrowdown"):  nty += 1
            elif inp.is_key_down("arrowleft"):  ntx -= 1
            elif inp.is_key_down("arrowright"): ntx += 1
            if (ntx, nty) != (char_tx[0], char_ty[0]):
                t = iso.get_tile(ntx, nty)
                if t and t.wall_h == 0:
                    char_tx[0], char_ty[0] = ntx, nty
                    char_cool[0] = CHAR_STEP
                    iso.center_on(ntx, nty)
                    iso.render()
                    needs_char = True
        char_walk[0] += dt
        # Only re-render character when something changed:
        # - map was panned (needs_char) → screen position shifted
        # - mid-step cooldown active   → bob animation still playing
        if needs_char or char_cool[0] > 0.0:
            render_char()

    # ── Quit ──────────────────────────────────────────────────────────────
    @inp.on_key_down("escape")
    @inp.on_key_down("q")
    async def quit_game(e=None) -> None:
        loop.stop()
        scene.unmount()
        await page.window.close()

    # ── Mount and start ───────────────────────────────────────────────────
    scene.mount()
    iso.render()   # first draw AFTER mount so canvas.page is set
    render_char()  # draw character after mount
    loop.start()


ft.run(main)
