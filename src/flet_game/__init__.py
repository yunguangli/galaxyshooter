"""
flet_game — A casual game library built on top of Flet 1.0+.

Design philosophy
-----------------
- Ursina-style simplicity  : minimal boilerplate, sane defaults everywhere.
- pygame-style clarity     : explicit sprite list, game loop, AABB collision.
- Flet-native              : no custom render loop or canvas — every visual
                             element is a real Flet control, so Flet's built-in
                             animations, theming, and hot-reload all work for free.

Architecture (implemented step by step)
----------------------------------------
Step 1  Sprite        — ft.Container-based game entity (position, color, image,
                         opacity, rotation, scale, AABB collision helpers).
Step 2  GameLoop      — asyncio-based update loop with delta-time (target 60 fps).
Step 2.5 Label        — text entity positioned absolutely on the game canvas.
Step 3  InputManager  — keyboard (ft.KeyboardListener) + touch/mouse
                         (ft.GestureDetector) state tracker.
Step 4  CollisionSystem — AABB overlap checks across sprite groups.
Step 5  Scene         — ft.Stack canvas that owns sprites, input, and the loop.
Step 6  Game          — top-level shell: wires Scene + Loop + Input, handles
                         scene switching and the @on_update decorator.
Step 7  Leaderboard   — persistent leaderboard via ft.SharedPreferences
                         (localStorage on web, NSUserDefaults on iOS, etc.);
                         async add/clear, sync top/rank_of.
Step 8  DrawingCanvas — flet.canvas-backed free-hand drawing surface with undo,
                         brush/eraser, and stroke serialisation for multiplayer sync.
Step 11 RaycastCanvas — Wolfenstein-style DDA raycasting 3-D renderer;
                         flet.canvas.Rect batch per frame; distance fog, Y-side
                         shading, configurable map grid and wall colours.
Step 12 VirtualJoystick — dynamic on-screen analogue stick; appears at thumb
                         touch point; vx/vy axes with configurable dead zone.
Step 13 LookPad         — relative drag-to-look trackpad for right-thumb FPS
                         input; accumulates dx per frame; double-tap = ADS.
Phase 2 Tween, AudioManager.
Phase 3 ParticleSystem, HUD helpers, MainMenuScene template.

Quick start (Step 1 only)
--------------------------
    import flet as ft
    from flet_game import Sprite

    def main(page: ft.Page) -> None:
        player = Sprite(x=100, y=100, width=50, height=50, color=ft.Colors.BLUE)
        canvas = ft.Stack(width=800, height=600,
                          controls=[player.control])
        page.add(canvas)
        player.move_to(400, 300, duration=600)   # animated move

    ft.run(main)

Short aliases (recommended for new code)
-----------------------------------------
    from flet_game import Loop, Input, Collider, Audio, Effects

    Loop    = GameLoop         # shorter
    Input   = InputManager     # standard game-dev name
    Collider= CollisionSystem  # common game-dev term
    Audio   = SoundManager     # simpler, direct
    Effects = SplashEffect     # more general

See docs/API.md for the full reference.
"""

# ── Defensive patches for Flet internals (dead data-channel ports) ─────────
from ._patch import install as _install_patches

_install_patches()
del _install_patches

# ── Step 1: Sprite ────────────────────────────────────────────────────────────
from .sprite import Sprite

# ── Step 2: GameLoop ──────────────────────────────────────────────────────────
from .loop import GameLoop

# ── Step 2.5: Label ───────────────────────────────────────────────────────────
from .label import Label
from .button import Button

# ── Step 3: InputManager ──────────────────────────────────────────────────────
from .input import InputManager

# ── Step 4: CollisionSystem ───────────────────────────────────────────────────
from .collision import CollisionSystem

# ── Step 4.5: SoundManager + SplashEffect + audio utilities ─────────────────
from .audio import SoundManager, BuiltinSounds, audio_available
from .audio_utils import make_beep, make_melody
from .particles import SplashEffect

# ── Step 5: Scene ─────────────────────────────────────────────────────────────
from .scene import Scene

# ── Step 6: Game ──────────────────────────────────────────────────────────────
from .game import Game

# ── Step 7: Leaderboard — local JSON save/load ───────────────────────────────
from .leaderboard import Leaderboard

# ── Step 8: DrawingCanvas (separate from action-game subsystem) ───────────────
from .drawing import DrawingCanvas

# ── Step 9: Camera — scrolling viewport for worlds larger than the window ─────
from .camera import Camera

# ── Step 10: Platformer prefab — physics controller + all-in-one world ────────
from .platformer import PlatformerController, PlatformerWorld

# ── Step 11: RaycastCanvas — Wolfenstein-style 3-D raycasting renderer ─────────
from .raycast import (
    RaycastCanvas,
    SpriteDef,
    WallDecal,
    CeilingLight,
    FloorBand,
    DEFAULT_MAP,
    DEFAULT_WALL_COLORS,
)
from .wall_texture import WallTexture
from .stairs import StairDef
from .ramp import RampDef

# ── Step 12: VirtualJoystick — dynamic on-screen analogue joystick ───────────
from .joystick import VirtualJoystick

# ── Step 13: LookPad — relative drag-to-look trackpad with ADS double-tap ─────
from .lookpad import LookPad

# ── Map generation utilities ──────────────────────────────────────────────────
from .mapgen import generate_random_map, spawn_points

# ── Step 14: GameView — responsive auto-scaler for fixed-design-size games ────
from .gameview import GameView

# ── Step 15: SpriteAnimation — frame-by-frame sprite animation ───────────────
from .animation import SpriteAnimation

# ── Step 16: SaveData — JSON-backed persistent key-value store ────────────────
from .savedata import SaveData

# ── Step 17: ObjectPool — pre-allocate and reuse Sprite / Label objects ───────
from .pool import ObjectPool

# ── Step 18: IsoMap — isometric tile-map with diamond rendering ───────────────
from .isomap import IsoMap, IsoTile, iso_to_screen, screen_to_iso

# ── Phase 5: PrefabLibrary — base64-embedded default sprites (no Pillow) ──────
from .prefab import HERO, ENEMY, ITEM, SKELETON, SLIME, KEY, MEDKIT, BAT, PISTOL, RIFLE, SWORD, BAZOOKA, FIST, PISTOL_FPS, RIFLE_FPS, SWORD_FPS, BAZOOKA_FPS, FIST_FPS, PrefabSprite, PrefabCharacter, make_prefab_sprite_defs

# ── Phase 5b: PngKit — zero-dependency procedural PNG / data-URI generation ───
from .pngkit import Pix, FONT, make_text_png, make_rect_uri, encode_png, hex_to_rgb

# ── Phase 6: SpriteLibrary — dynamic asset scanner for user sprites ──────────
from .sprite_library import SpriteLibrary, SpriteEntry, SpriteState
from .sprite_factories import make_sprite_defs_from_library

# ── Friendly short aliases (entry-level friendly; full names still work) ──────
# These are the recommended names for new code — shorter and more game-dev
# familiar. The original names remain as aliases so existing code is unaffected.
Loop     = GameLoop           # shorter alias for GameLoop
Input    = InputManager       # standard game-dev name for input handling
Collider = CollisionSystem    # common game-dev term for collision detection
Audio    = SoundManager       # simpler, direct name
Effects  = SplashEffect       # more general than "SplashEffect"
SFX      = BuiltinSounds      # short alias

__all__ = [
    # Step 1
    "Sprite",
    # Step 2
    "GameLoop", "Loop",
    # Step 2.5
    "Label",
    "Button",
    # Step 3
    "InputManager", "Input",
    # Step 4
    "CollisionSystem", "Collider",
    # Step 4.5
    "SoundManager", "Audio",
    "BuiltinSounds",
    "audio_available",
    "make_beep",
    "make_melody",
    "SplashEffect", "Effects",
    # Step 5
    "Scene",
    # Step 6
    "Game",
    # Step 7
    "Leaderboard",
    # Step 8 — Drawing (separate from action-game subsystem)
    "DrawingCanvas",
    # Step 9 — Camera
    "Camera",
    # Step 10 — Platformer prefab
    "PlatformerController",
    "PlatformerWorld",
    # Step 11 — Raycasting 3-D renderer
    "RaycastCanvas",
    "WallTexture",
    "SpriteDef",
    "WallDecal",
    "CeilingLight",
    "FloorBand",
    "StairDef",
    "RampDef",
    "DEFAULT_MAP",
    "DEFAULT_WALL_COLORS",
    # Step 12 — Virtual joystick
    "VirtualJoystick",
    # Step 13 — Look trackpad
    "LookPad",
    # Map generation
    "generate_random_map",
    "spawn_points",
    # Step 14 — GameView
    "GameView",
    # Step 15 — SpriteAnimation
    "SpriteAnimation",
    # Step 16 — SaveData
    "SaveData",
    # Step 17 — ObjectPool
    "ObjectPool",
    # Step 18 — IsoMap
    "IsoMap",
    "IsoTile",
    "iso_to_screen",
    "screen_to_iso",
    # Phase 5 — Prefab sprites
    "HERO",
    "ENEMY",
    "ITEM",
    "SKELETON",
    "SLIME",
    "KEY",
    "MEDKIT",
    "BAT",
    "PISTOL",
    "RIFLE",
    "SWORD",
    "BAZOOKA",
    "FIST",
    "PISTOL_FPS",
    "RIFLE_FPS",
    "SWORD_FPS",
    "BAZOOKA_FPS",
    "FIST_FPS",
    "PrefabSprite",
    "PrefabCharacter",
    "make_prefab_sprite_defs",
    # Phase 5b — PngKit
    "Pix",
    "FONT",
    "make_text_png",
    "make_rect_uri",
    "encode_png",
    "hex_to_rgb",
    # Phase 6 — SpriteLibrary
    "SpriteLibrary",
    "SpriteEntry",
    "SpriteState",
    "make_sprite_defs_from_library",
]

