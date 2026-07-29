"""
platformer.py — Platformer prefab: PlatformerController + PlatformerWorld.

``PlatformerController``  — low-level physics and input handler; attach to any Sprite.
``PlatformerWorld``       — high-level all-in-one prefab: Scene + Camera + ground + player.

Platforms are **solid** from the top and below: the player lands on the top
surface while falling, and is pushed back when jumping into the underside.

Features
--------
- Gravity, floor snap, solid platform collision (top and ceiling)
- Double / triple jump via *max_jumps*
- Coyote time: grace period to jump just after walking off an edge
- Jump buffer: press jump slightly early, fires automatically on landing

Usage — PlatformerWorld (minimal setup)::

    import flet as ft
    from flet_game import PlatformerWorld

    async def main(page: ft.Page) -> None:
        world = PlatformerWorld(
            page,
            world_width=3200, viewport_width=800, viewport_height=480,
            max_jumps=2,
        )
        world.add_platform(x=250, y=350, width=130, height=16)
        world.add_platform(x=480, y=305, width=110, height=16)
        world.mount()

    ft.run(main, assets_dir="assets")

Usage — PlatformerController (low-level)::

    from flet_game import PlatformerController, Camera, Scene, Sprite, GameLoop

    cam  = Camera(world_width=3200, world_height=480,
                  viewport_width=800, viewport_height=480)
    scene = Scene(page, width=800, height=480)
    scene.add(cam.control)

    player = Sprite(x=60, y=359, width=40, height=56, color="#00e5ff", tag="player")
    cam.add(player, z=5)

    ctrl = PlatformerController(
        sprite=player,
        inp=scene.input,
        ground_y=415,
        platforms=plat_sprites,
        walk_speed=260,
        gravity=900,
        jump_speed=530,
        max_jumps=1,
    )

    loop = GameLoop(page)

    def update(dt):
        ctrl.update(dt)
        cam.follow(player, lerp=0.10, x_only=True)

    loop.add_callback(update)
    scene.mount()
    loop.start()
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import flet as ft

from .camera import Camera
from .input import InputManager
from .label import Label
from .loop import GameLoop
from .scene import Scene
from .sprite import Sprite


# Default key bindings (normalised to InputManager conventions)
_DEFAULT_LEFT_KEYS:  Tuple[str, ...] = ("left",  "a")
_DEFAULT_RIGHT_KEYS: Tuple[str, ...] = ("right", "d")
_DEFAULT_JUMP_KEYS:  Tuple[str, ...] = ("up", "space", "w")


class PlatformerController:
    """Physics + input controller for a 2D side-scrolling platformer.

    Attach to any ``Sprite``; call ``update(dt)`` once per frame from a
    ``GameLoop`` callback.

    Platforms are **one-way**: the player passes through them while rising and
    lands on the top surface while falling.  This is the classic Mario-style
    behaviour.

    Parameters
    ----------
    sprite : Sprite
        The player sprite to control.
    inp : InputManager
        The scene's ``InputManager`` instance.  Jump keys are registered here.
    ground_y : float
        World Y coordinate of the floor surface (top edge of the ground).
    platforms : list[Sprite], optional
        One-way platform sprites.  Add / remove later via ``add_platform`` /
        ``remove_platform``.
    walk_speed : float
        Horizontal speed in pixels per second (default 260).
    gravity : float
        Downward acceleration in px/s² (default 900).
    jump_speed : float
        Initial upward velocity when jumping in px/s (default 530).
    max_jumps : int
        Maximum consecutive jumps before landing (1 = single, 2 = double jump).
    world_left : float
        Leftmost world X the player can reach (default 0).
    world_right : float
        Rightmost world X the player can reach (default ∞).
    coyote_time : float
        Seconds of grace after walking off an edge during which jumping still
        works (default 0.08).
    jump_buffer_time : float
        Seconds a jump key press is remembered before landing; fires
        automatically when the player touches down (default 0.10).
    move_keys : dict, optional
        Override default key bindings::

            move_keys = {
                "left":  ("arrowleft", "a"),
                "right": ("arrowright", "d"),
                "jump":  ("space", "arrowup", "w"),
            }
    """

    def __init__(
        self,
        sprite: Sprite,
        inp: InputManager,
        ground_y: float,
        *,
        platforms: Optional[List[Sprite]] = None,
        walk_speed: float = 260.0,
        gravity: float = 900.0,
        jump_speed: float = 530.0,
        max_jumps: int = 1,
        world_left: float = 0.0,
        world_right: float = math.inf,
        coyote_time: float = 0.08,
        jump_buffer_time: float = 0.10,
        move_keys: Optional[Dict[str, Tuple[str, ...]]] = None,
    ) -> None:
        self._sprite = sprite
        self._inp = inp

        self._ground_y = float(ground_y)
        self._walk_speed = float(walk_speed)
        self._gravity = float(gravity)
        self._jump_speed = float(jump_speed)
        self._max_jumps = int(max_jumps)
        self._world_left = float(world_left)
        self._world_right = float(world_right)
        self._coyote_time = float(coyote_time)
        self._jump_buf_time = float(jump_buffer_time)

        self._platforms: List[Sprite] = list(platforms) if platforms else []

        # Runtime physics state
        self._vy: float = 0.0
        self._grounded: bool = True
        self._jumps_left: int = self._max_jumps
        self._facing: int = 1          # +1 = right, -1 = left
        self._coyote_timer: float = 0.0
        self._jump_buffer: float = 0.0

        # Key bindings
        if move_keys is None:
            move_keys = {}
        self._left_keys  = tuple(move_keys.get("left",  _DEFAULT_LEFT_KEYS))
        self._right_keys = tuple(move_keys.get("right", _DEFAULT_RIGHT_KEYS))
        jump_keys        = tuple(move_keys.get("jump",  _DEFAULT_JUMP_KEYS))

        # Register jump via on_key_down (single-press event, not held-key polling)
        for key in jump_keys:
            @inp.on_key_down(key)
            def _on_jump(e=None):  # noqa: E306
                self._jump_pressed()

    # ── Public properties ───────────────────────────────────────────────────────

    @property
    def grounded(self) -> bool:
        """``True`` while the player is on the floor or a platform."""
        return self._grounded

    @property
    def vy(self) -> float:
        """Current vertical velocity — positive = downward in Flet screen coords."""
        return self._vy

    @property
    def jumps_left(self) -> int:
        """Remaining jumps before the player must land to refresh."""
        return self._jumps_left

    @property
    def facing(self) -> int:
        """``+1`` when facing right, ``-1`` when facing left."""
        return self._facing

    # ── Public methods ──────────────────────────────────────────────────────────

    def add_platform(self, sprite: Sprite) -> None:
        """Add *sprite* to the one-way platform collision list."""
        if sprite not in self._platforms:
            self._platforms.append(sprite)

    def remove_platform(self, sprite: Sprite) -> None:
        """Remove *sprite* from the platform collision list (no-op if absent)."""
        try:
            self._platforms.remove(sprite)
        except ValueError:
            pass

    def jump(self) -> None:
        """Programmatically trigger a jump, bypassing the normal guard checks.

        Useful for scripted sequences or custom jump logic.  For standard
        gameplay, rely on the automatic key handling instead.
        """
        self._vy = -self._jump_speed
        self._jumps_left = max(0, self._jumps_left - 1)
        self._grounded = False
        self._coyote_timer = 0.0
        self._jump_buffer = 0.0

    def update(self, dt: float) -> None:
        """Advance physics and input for one frame.

        Call exactly once per ``GameLoop`` tick::

            def update(dt: float) -> None:
                ctrl.update(dt)
                cam.follow(player, lerp=0.10, x_only=True)

            loop.add_callback(update)
        """
        spr = self._sprite
        inp = self._inp
        h   = spr.height

        was_grounded = self._grounded

        # ── Horizontal movement ────────────────────────────────────────────────
        dx = 0.0
        if any(inp.is_key_down(k) for k in self._left_keys):
            dx -= self._walk_speed * dt
            self._facing = -1
        if any(inp.is_key_down(k) for k in self._right_keys):
            dx += self._walk_speed * dt
            self._facing = 1
        spr.x = max(self._world_left,
                    min(self._world_right - spr.width, spr.x + dx))

        # ── Vertical physics ───────────────────────────────────────────────────
        self._vy += self._gravity * dt
        spr.y    += self._vy * dt

        # ── Floor collision ────────────────────────────────────────────────────
        floor_top = self._ground_y - h
        if spr.y >= floor_top:
            spr.y = floor_top
            self._land()

        else:
            # ── Platform collision (solid top and ceiling) ────────────────────
            self._grounded = False

            if self._vy < 0:  # rising — ceiling collision
                old_top = spr.y - self._vy * dt   # head position before this frame
                new_top = spr.y
                for p in self._platforms:
                    if not p.visible:
                        continue
                    if spr.x + spr.width <= p.x or spr.x >= p.x + p.width:
                        continue
                    # Head crossed the platform top from below to above this frame
                    if old_top >= p.y > new_top:
                        spr.y = p.y + 1.0   # snap head just below platform top
                        self._vy = 0.0       # kill upward velocity; gravity handles the rest
                        break

            elif self._vy > 0:  # falling — land on top surface
                # Player's bottom edge one frame ago and now
                prev_bottom = (spr.y - self._vy * dt) + h
                curr_bottom = spr.y + h

                for p in self._platforms:
                    if not p.visible:
                        continue          # platform removed / invisible
                    # Horizontal overlap check
                    if spr.x + spr.width <= p.x or spr.x >= p.x + p.width:
                        continue
                    # Vertical: player bottom must cross platform top this frame.
                    # +8 px tolerance to handle fast movement and thin platforms.
                    if prev_bottom > p.y + 8:
                        continue          # player was already below the platform
                    if curr_bottom < p.y:
                        continue          # player hasn't reached the platform yet
                    # Land on top
                    spr.y = p.y - h
                    self._land()
                    break

            # ── Coyote time ────────────────────────────────────────────────────
            # Start the grace timer only when the player *falls* off a surface
            # (vy >= 0), not when they jump away (vy < 0 after jump()).
            if was_grounded and not self._grounded and self._vy >= 0:
                self._coyote_timer = self._coyote_time
            elif not self._grounded:
                self._coyote_timer = max(0.0, self._coyote_timer - dt)

        # ── Jump buffer countdown ──────────────────────────────────────────────
        if self._jump_buffer > 0:
            self._jump_buffer = max(0.0, self._jump_buffer - dt)

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _land(self) -> None:
        """Called when the player touches the floor or a platform top."""
        self._vy = 0.0
        self._grounded = True
        self._coyote_timer = 0.0
        self._jumps_left = self._max_jumps

        # Fire buffered jump immediately
        buf = self._jump_buffer
        self._jump_buffer = 0.0
        if buf > 0:
            self.jump()

    def _jump_pressed(self) -> None:
        """Decide whether to jump or store a buffer when a jump key is pressed."""
        if self._grounded or self._coyote_timer > 0:
            # Normal ground jump or coyote-time jump
            self._coyote_timer = 0.0
            self.jump()
        elif self._jumps_left > 0:
            # Double / triple jump while airborne
            self.jump()
        else:
            # Can't jump yet — buffer the press for the next landing
            self._jump_buffer = self._jump_buf_time


# ────────────────────────────────────────────────────────────────────────────────


class PlatformerWorld:
    """All-in-one platformer prefab: Camera + Scene + ground + player.

    Creates a complete scrolling platformer world with minimal code::

        world = PlatformerWorld(
            page,
            world_width=3200, viewport_width=800, viewport_height=480,
            max_jumps=2,       # double jump
        )
        world.add_platform(x=250, y=350, width=130, height=16)
        world.add_platform(x=480, y=305, width=110, height=16)

        # Optional: add HUD labels to the fixed scene layer
        score_lbl = Label(text="Score: 0", x=10, y=8, color="white")
        world.scene.add(score_lbl, z=10)

        # Optional: extra per-frame logic
        @world.loop.on_update
        def tick(dt):
            score_lbl.text = f"Score: {pts}"

        world.mount()  # starts scene + loop

    Public attributes
    -----------------
    scene  : Scene
    cam    : Camera
    player : Sprite
    ctrl   : PlatformerController
    loop   : GameLoop

    Parameters
    ----------
    page : ft.Page
        The Flet page.
    world_width : float
        Total world width in pixels.
    viewport_width : float
        Visible area width (usually = window width).
    viewport_height : float
        Visible area height (usually = window height).
    bgcolor : str
        Scene background colour (default ``"#0d0d1f"``).
    floor_y : float, optional
        World Y coordinate of the floor top edge.
        Defaults to ``viewport_height - 65``.
    floor_color : str
        Main floor fill colour (default ``"#3a6b2a"``).
    floor_edge_color : str
        Thin bright strip at the floor top edge (default ``"#5a9e3c"``).
    player_color : str
        Player sprite colour (default ``"#00e5ff"``).
    player_width : float
        Player width in pixels (default 40).
    player_height : float
        Player height in pixels (default 56).
    player_start_x : float
        Player starting X in world coordinates (default 60).
    walk_speed : float
        Horizontal speed in px/s (default 260).
    gravity : float
        Gravity in px/s² (default 900).
    jump_speed : float
        Initial jump velocity in px/s (default 530).
    max_jumps : int
        Jumps before landing required; 1 = single, 2 = double (default 1).
    coyote_time : float
        Jump grace period after walking off an edge, in seconds (default 0.08).
    jump_buffer_time : float
        Jump input is buffered for this many seconds before landing (default 0.10).
    fps : int
        Target frames per second (default 60).
    """

    def __init__(
        self,
        page: ft.Page,
        world_width: float,
        viewport_width: float,
        viewport_height: float,
        *,
        bgcolor: str = "#0d0d1f",
        floor_y: Optional[float] = None,
        floor_color: str = "#3a6b2a",
        floor_edge_color: str = "#5a9e3c",
        player_color: str = "#00e5ff",
        player_width: float = 40.0,
        player_height: float = 56.0,
        player_start_x: float = 60.0,
        walk_speed: float = 260.0,
        gravity: float = 900.0,
        jump_speed: float = 530.0,
        max_jumps: int = 1,
        coyote_time: float = 0.08,
        jump_buffer_time: float = 0.10,
        fps: int = 60,
    ) -> None:
        world_width    = float(world_width)
        viewport_width  = float(viewport_width)
        viewport_height = float(viewport_height)

        if floor_y is None:
            floor_y = viewport_height - 65.0
        floor_y = float(floor_y)

        # ── Camera + Scene ─────────────────────────────────────────────────────
        self.cam = Camera(
            world_width=world_width,
            world_height=viewport_height,     # horizontal scroller: same height
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        self.scene = Scene(
            page,
            width=viewport_width,
            height=viewport_height,
            bgcolor=bgcolor,
        )
        self.scene.add(self.cam.control)

        # ── Ground ─────────────────────────────────────────────────────────────
        ground_h = viewport_height - floor_y
        _ground = Sprite(
            x=0, y=floor_y,
            width=world_width, height=ground_h,
            color=floor_color,
        )
        _edge = Sprite(
            x=0, y=floor_y,
            width=world_width, height=6,
            color=floor_edge_color,
        )
        self.cam.add(_ground, z=-1)
        self.cam.add(_edge,   z=-1)

        # ── Player ─────────────────────────────────────────────────────────────
        self.player = Sprite(
            x=float(player_start_x),
            y=floor_y - float(player_height),
            width=float(player_width),
            height=float(player_height),
            color=player_color,
            border_radius=8,
            tag="player",
        )
        self.cam.add(self.player, z=5)

        # ── PlatformerController ────────────────────────────────────────────────
        self.ctrl = PlatformerController(
            sprite=self.player,
            inp=self.scene.input,
            ground_y=floor_y,
            walk_speed=walk_speed,
            gravity=gravity,
            jump_speed=jump_speed,
            max_jumps=max_jumps,
            world_left=0.0,
            world_right=world_width,
            coyote_time=coyote_time,
            jump_buffer_time=jump_buffer_time,
        )

        # ── GameLoop with built-in physics + camera update ─────────────────────
        self.loop = GameLoop(page, fps=fps)

        def _default_update(dt: float) -> None:
            self.ctrl.update(dt)
            self.cam.follow(self.player, lerp=0.10, x_only=True)

        self._default_cb = _default_update
        self.loop.add_callback(_default_update)

    # ── Content helpers ─────────────────────────────────────────────────────────

    def add_platform(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        color: str = "#4a7c35",
        *,
        border_radius: float = 4.0,
    ) -> Sprite:
        """Add a one-way platform to the world.

        Returns the ``Sprite`` so it can be stored, moved, or toggled later::

            moving_plat = world.add_platform(x=400, y=300, width=100, height=16)
            # later:
            moving_plat.x += 5   # move it in a game-loop callback
        """
        plat = Sprite(
            x=float(x), y=float(y),
            width=float(width), height=float(height),
            color=color, border_radius=border_radius,
        )
        self.cam.add(plat, z=1)
        self.ctrl.add_platform(plat)
        return plat

    def add_layer(self, speed: float) -> ft.Stack:
        """Add a parallax background layer behind the world.

        Returns an ``ft.Stack``; populate its ``.controls`` list directly::

            sky = world.add_layer(speed=0.25)
            sky.controls.append(
                ft.Container(width=3200, height=300, bgcolor="#12123a",
                             left=0, top=0)
            )

        Call *before* ``mount()`` so the layer is visible from the first frame.

        Speed guide:

        +---------+-------------------------------------------+
        | speed   | effect                                    |
        +=========+===========================================+
        | 0.0     | fixed — same as adding to scene directly  |
        | 0.25    | distant sky / stars                       |
        | 0.55    | midground hills / buildings               |
        | 1.0     | same speed as world (no parallax)         |
        +---------+-------------------------------------------+
        """
        return self.cam.add_layer(speed)

    def mount(self) -> None:
        """Mount the scene onto the page and start the game loop.

        Call *after* ``add_platform()``, ``add_layer()``, and any extra
        ``@world.loop.on_update`` / ``world.scene.add()`` calls::

            world.add_platform(...)
            world.scene.add(hud_label, z=10)

            @world.loop.on_update
            def tick(dt):
                hud_label.text = f"X: {int(world.player.x)}"

            world.mount()   # ← last call
        """
        self.scene.mount()
        self.loop.start()
