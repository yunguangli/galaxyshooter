"""SpriteDef helper factories — create SpriteDef lists from prefab or
library sources without manual per-sprite boilerplate.
"""

from __future__ import annotations

from typing import Optional, Sequence

# Re-export the prefab factory for convenience
from .prefab import make_prefab_sprite_defs  # noqa: F401


def make_sprite_defs_from_library(
    library: "SpriteLibrary",
    placements: list[dict],
    z: float = 0.0,
) -> list:
    """Create a list of :class:`SpriteDef` objects from a scanned sprite library.

    Parameters
    ----------
    library:
        A :class:`SpriteLibrary` instance (from ``flet_game.SpriteLibrary``).
    placements:
        A list of dicts, each with keys:

        - ``"name"`` — directory name in ``assets/sprites/`` (e.g. ``"hero"``).
        - ``"x"`` / ``"y"`` — world position.
        - ``"state"`` *(optional)* — animation state (default ``"idle"``).
        - ``"z"`` *(optional)* — height above ground override.
        - ``"world_height"`` *(optional)* — world height override.
    z:
        Default height above ground (map units) for all sprites.
    """
    from .raycast import SpriteDef
    from .prefab import HERO, ENEMY, ITEM, SKELETON, SLIME, KEY, BAT, PISTOL, RIFLE, SWORD, BAZOOKA, FIST, PISTOL_FPS, RIFLE_FPS, SWORD_FPS, BAZOOKA_FPS, FIST_FPS

    result: list = []

    for p in placements:
        name = p["name"]
        state = p.get("state", "idle")

        # Try user library first
        path = library.get_idle_path(name) if state == "idle" else None
        if path is None:
            frames = library.get_state_paths(name, state)
            path = frames[0] if frames else None

        # Fall back to prefab
        if path is None:
            prefab_map = {
                "hero": HERO, "enemy": ENEMY, "item": ITEM,
                "skeleton": SKELETON, "slime": SLIME, "key": KEY,
                "bat": BAT, "pistol": PISTOL, "rifle": RIFLE,
                "sword": SWORD, "bazooka": BAZOOKA, "fist": FIST,
                "pistol_fps": PISTOL_FPS, "rifle_fps": RIFLE_FPS,
                "sword_fps": SWORD_FPS, "bazooka_fps": BAZOOKA_FPS,
                "fist_fps": FIST_FPS,
            }
            prefab = prefab_map.get(name)
            if prefab:
                path = prefab.idle.data_uri

        if path is None:
            continue

        result.append(
            SpriteDef(
                x=p["x"], y=p["y"],
                image=path,
                aspect_ratio=p.get("aspect_ratio", 0.45),
                z=p.get("z", z),
                world_height=p.get("world_height", 1.0),
                shadow=p.get("shadow", True),
                shadow_alpha=p.get("shadow_alpha", 0.33),
            )
        )

    return result
