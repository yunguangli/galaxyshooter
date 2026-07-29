from __future__ import annotations

from flet_game import ObjectPool, Sprite

from .manager import (
    BOSS_H,
    BOSS_W,
    BULLET_H,
    BULLET_W,
    ENEMY_BULLET_H,
    ENEMY_BULLET_W,
    ENEMY_H,
    ENEMY_W,
    PLAYER_H,
    PLAYER_W,
    POWERUP_H,
    POWERUP_W,
)

ASSET = "{}.png"


def make_player_sprite() -> Sprite:
    return Sprite(
        x=0,
        y=0,
        width=PLAYER_W,
        height=PLAYER_H,
        image=ASSET.format("spaceship"),
        tag="player",
    )


def make_enemy_sprite(kind: str) -> Sprite:
    w, h = ENEMY_W, ENEMY_H
    return Sprite(
        x=0,
        y=0,
        width=w,
        height=h,
        image=ASSET.format(kind),
        tag="enemy",
        visible=False,
    )


def make_boss_sprite() -> Sprite:
    return Sprite(
        x=0,
        y=0,
        width=BOSS_W,
        height=BOSS_H,
        image=ASSET.format("boss"),
        tag="boss",
        visible=False,
    )


def make_player_bullet_sprite() -> Sprite:
    return Sprite(
        x=0,
        y=0,
        width=BULLET_W,
        height=BULLET_H,
        color="#00e5ff",
        tag="bullet",
        visible=False,
    )


def make_enemy_bullet_sprite() -> Sprite:
    return Sprite(
        x=0,
        y=0,
        width=ENEMY_BULLET_W,
        height=ENEMY_BULLET_H,
        color="#ff5252",
        tag="ebullet",
        visible=False,
    )


POWERUP_COLORS = {
    "spread": "#ffd740",
    "speed": "#69f0ae",
    "life": "#ff4081",
}


def make_powerup_sprite(kind: str) -> Sprite:
    c = POWERUP_COLORS.get(kind, "#ffffff")
    return Sprite(
        x=0,
        y=0,
        width=POWERUP_W,
        height=POWERUP_H,
        color=c,
        tag=f"powerup_{kind}",
        visible=False,
        border_radius=4,
    )


def prewarm_pools(scene) -> dict:
    bullet_pool = ObjectPool(
        factory=make_player_bullet_sprite, max_size=40, scene=scene, z=5
    ).prewarm()
    enemy_bullet_pool = ObjectPool(
        factory=make_enemy_bullet_sprite, max_size=30, scene=scene, z=5
    ).prewarm()
    alien1_pool = ObjectPool(
        factory=lambda: make_enemy_sprite("alien1"),
        max_size=20,
        scene=scene,
        z=3,
    ).prewarm()
    alien2_pool = ObjectPool(
        factory=lambda: make_enemy_sprite("alien2"),
        max_size=10,
        scene=scene,
        z=3,
    ).prewarm()
    boss_pool = ObjectPool(
        factory=make_boss_sprite, max_size=1, scene=scene, z=3
    ).prewarm()
    powerup_pool = ObjectPool(
        factory=lambda: make_powerup_sprite("spread"),
        max_size=8,
        scene=scene,
        z=4,
    ).prewarm()
    return {
        "bullets": bullet_pool,
        "ebullets": enemy_bullet_pool,
        "alien1": alien1_pool,
        "alien2": alien2_pool,
        "boss": boss_pool,
        "powerups": powerup_pool,
    }
