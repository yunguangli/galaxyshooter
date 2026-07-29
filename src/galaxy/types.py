from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlayerData:
    x: float = 180.0
    y: float = 620.0
    speed: float = 280.0
    fire_rate: float = 8.0
    last_shot_time: float = -999.0
    power_level: int = 1
    invincible_until: float = 0.0
    alive: bool = True


@dataclass
class BulletData:
    x: float = 0.0
    y: float = 0.0
    speed: float = 500.0
    is_enemy: bool = False
    active: bool = False


@dataclass
class EnemyData:
    x: float = 0.0
    y: float = 0.0
    speed: float = 80.0
    hp: int = 1
    kind: str = "alien1"
    shoot_timer: float = 0.0
    shoot_interval: float = 99.0
    move_dir: float = 0.0
    move_timer: float = 0.0
    active: bool = False
    sprite_w: float = 36.0
    sprite_h: float = 36.0


@dataclass
class PowerUpData:
    x: float = 0.0
    y: float = 0.0
    kind: str = "spread"
    speed: float = 100.0
    active: bool = False


@dataclass
class WaveData:
    number: int = 1
    spawned: int = 0
    killed: int = 0
    per_wave: int = 8
    spawn_interval: float = 1.2
    timer: float = 0.0
    completed: bool = False
    boss_wave: bool = False


@dataclass
class GameData:
    score: int = 0
    lives: int = 3
    level: int = 1
    status: str = "title"
    high_score: int = 0
    combo: int = 0
    comboTimer: float = 0.0
    powerUpTimer: float = 0.0
    activePowerUp: str = ""
