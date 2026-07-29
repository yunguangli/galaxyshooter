from __future__ import annotations

import math
import random

from .types import (
    BulletData,
    EnemyData,
    GameData,
    PlayerData,
    PowerUpData,
    WaveData,
)

DESIGN_W = 400.0
DESIGN_H = 700.0

PLAYER_W = 40
PLAYER_H = 52
ENEMY_W = 36
ENEMY_H = 36
BOSS_W = 120
BOSS_H = 120
BULLET_W = 6
BULLET_H = 16
POWERUP_W = 24
POWERUP_H = 24
ENEMY_BULLET_W = 6
ENEMY_BULLET_H = 6

POWERUP_KINDS = ("spread", "speed", "life")


class GalaxyManager:
    def __init__(self) -> None:
        self.game = GameData()
        self.player = PlayerData()
        self.wave = WaveData()
        self.bullets: list[BulletData] = []
        self.enemy_bullets: list[BulletData] = []
        self.enemies: list[EnemyData] = []
        self.powerups: list[PowerUpData] = []
        self._time = 0.0

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start_game(self) -> None:
        hs = self.game.high_score
        self.game = GameData(high_score=hs, status="playing")
        self.player = PlayerData()
        self.wave = WaveData()
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.enemies.clear()
        self.powerups.clear()
        self._time = 0.0

    # ── Per-frame update ───────────────────────────────────────────────────

    def update(
        self, dt: float, move_dir: float, shooting: bool
    ) -> None:
        if self.game.status != "playing":
            return
        self._time += dt
        self._update_combo(dt)
        self._update_powerup(dt)
        self._update_player(dt, move_dir, shooting)
        self._update_bullets(dt)
        self._update_enemy_bullets(dt)
        self._update_enemies(dt)
        self._update_powerups(dt)
        self._update_wave(dt)
        self._check_collisions()

    # ── Player ─────────────────────────────────────────────────────────────

    def _update_player(
        self, dt: float, move_dir: float, shooting: bool
    ) -> None:
        p = self.player
        if not p.alive:
            return
        p.x += move_dir * p.speed * dt
        p.x = max(0.0, min(DESIGN_W - PLAYER_W, p.x))
        if shooting:
            self._try_shoot()

    def _try_shoot(self) -> None:
        p = self.player
        interval = 1.0 / p.fire_rate
        if self._time - p.last_shot_time < interval:
            return
        p.last_shot_time = self._time
        cx = p.x + PLAYER_W / 2
        if p.power_level >= 3:
            self._spawn_bullet(cx - 8, p.y)
            self._spawn_bullet(cx, p.y - 8)
            self._spawn_bullet(cx + 8, p.y)
        elif p.power_level == 2:
            self._spawn_bullet(cx - 4, p.y)
            self._spawn_bullet(cx + 4, p.y)
        else:
            self._spawn_bullet(cx, p.y)

    # ── Bullets ────────────────────────────────────────────────────────────

    def _spawn_bullet(self, x: float, y: float) -> None:
        for b in self.bullets:
            if not b.active:
                b.x = x - BULLET_W / 2
                b.y = y
                b.speed = 500.0
                b.active = True
                return
        self.bullets.append(
            BulletData(x=x - BULLET_W / 2, y=y, speed=500.0, active=True)
        )

    def _spawn_enemy_bullet(self, x: float, y: float) -> None:
        for b in self.enemy_bullets:
            if not b.active:
                b.x = x - ENEMY_BULLET_W / 2
                b.y = y
                b.speed = 200.0
                b.active = True
                return
        self.enemy_bullets.append(
            BulletData(
                x=x - ENEMY_BULLET_W / 2,
                y=y,
                speed=200.0,
                active=True,
            )
        )

    def _update_bullets(self, dt: float) -> None:
        for b in self.bullets:
            if not b.active:
                continue
            b.y -= b.speed * dt
            if b.y < -BULLET_H:
                b.active = False

    def _update_enemy_bullets(self, dt: float) -> None:
        for b in self.enemy_bullets:
            if not b.active:
                continue
            b.y += b.speed * dt
            if b.y > DESIGN_H + ENEMY_BULLET_H:
                b.active = False

    def _update_enemies(self, dt: float) -> None:
        lvl = self.game.level
        # Hoist active bullet list outside enemy loop — avoid O(N*M) list comp
        active_bullets = [b for b in self.bullets if b.active]
        dodge_enabled = len(active_bullets) < 20
        for e in self.enemies:
            if not e.active:
                continue
            e.y += e.speed * dt

            # Sine-wave pathing — amplitude and frequency scale with level
            if e.wave_amplitude > 0.0:
                e.wave_phase += e.wave_frequency * dt
                sine_offset = math.sin(e.wave_phase) * e.wave_amplitude
                # Blend sine path with dodge input
                e.x = max(
                    0.0,
                    min(DESIGN_W - e.sprite_w, e.x + sine_offset * dt * 60.0),
                )

            # More agile: change direction more frequently and dodge
            # when the player's bullet is nearby
            e.move_timer -= dt
            if e.move_timer <= 0.0:
                e.move_dir = random.uniform(-1.0, 1.0)
                e.move_timer = random.uniform(0.3, 1.5)
            # Dodge sideways when a bullet is approaching
            if dodge_enabled:
                for b in active_bullets:
                    if abs(b.x - (e.x + e.sprite_w / 2)) < 30 and b.y < e.y + e.sprite_h and b.y > e.y:
                        e.move_dir = 1.0 if b.x < e.x else -1.0
                        break
            e.x += e.move_dir * 60.0 * dt  # lateral movement
            e.x = max(0.0, min(DESIGN_W - e.sprite_w, e.x))

            if e.kind in ("alien1", "alien2", "boss"):
                e.shoot_timer -= dt
                if e.shoot_timer <= 0.0:
                    ex = e.x + e.sprite_w / 2
                    ey = e.y + e.sprite_h
                    self._spawn_enemy_bullet(ex, ey)
                    e.shoot_timer = e.shoot_interval

            if e.y > DESIGN_H + 60:
                e.active = False

    # ── Wave system ────────────────────────────────────────────────────────

    def _update_wave(self, dt: float) -> None:
        w = self.wave
        if w.completed:
            return
        w.timer -= dt
        if w.timer <= 0.0 and w.spawned < w.per_wave:
            self._spawn_enemy()
            w.spawned += 1
            w.timer = w.spawn_interval
        if w.spawned >= w.per_wave and all(
            not e.active for e in self.enemies
        ):
            w.completed = True
            self._next_wave()

    def _next_wave(self) -> None:
        self.game.level += 1
        lvl = self.game.level
        self.wave = WaveData(
            number=lvl,
            per_wave=min(80, 15 + lvl * 4),
            spawn_interval=max(0.15, 0.9 - lvl * 0.03),
            boss_wave=(lvl % 5 == 0),
            timer=0.5,
        )

    def _spawn_enemy(self) -> None:
        w = self.wave
        lvl = self.game.level
        kind = "boss" if w.boss_wave and w.spawned == 0 else random.choice(
            ["alien1", "alien1", "alien2"] if lvl >= 2 else ["alien1"]
        )
        if kind == "boss":
            hp = 20 + lvl * 5
            sw, sh = BOSS_W, BOSS_H
            speed = 50.0 + lvl * 2
            shoot_int = random.uniform(0.4, 1.2)
            wave_amp = 40.0 + lvl * 5.0
            wave_freq = 1.5 + lvl * 0.3
        elif kind == "alien2":
            hp = 3 if lvl >= 3 else 2
            sw, sh = ENEMY_W, ENEMY_H
            speed = 90.0 + lvl * 5
            shoot_int = random.uniform(0.8, 2.0)
            wave_amp = 20.0 + lvl * 3.0
            wave_freq = 2.0 + lvl * 0.2
        else:
            hp = 1
            sw, sh = ENEMY_W, ENEMY_H
            speed = 70.0 + lvl * 4
            shoot_int = random.uniform(1.5, 3.5)
            wave_amp = 5.0 + lvl * 2.0
            wave_freq = 2.5 + lvl * 0.15
        for e in self.enemies:
            if not e.active:
                e.x = random.uniform(0.0, DESIGN_W - sw)
                e.y = -sh
                e.speed = speed
                e.hp = hp
                e.kind = kind
                e.shoot_timer = random.uniform(0.5, 2.0)
                e.shoot_interval = shoot_int
                e.move_dir = random.uniform(-1.0, 1.0)
                e.move_timer = random.uniform(0.3, 1.5)
                e.sprite_w = sw
                e.sprite_h = sh
                e.wave_amplitude = wave_amp
                e.wave_frequency = wave_freq
                e.wave_phase = random.uniform(0.0, 2.0 * math.pi)
                e.active = True
                return
        self.enemies.append(
            EnemyData(
                x=random.uniform(0.0, DESIGN_W - sw),
                y=-sh,
                speed=speed,
                hp=hp,
                kind=kind,
                shoot_timer=random.uniform(0.5, 2.0),
                shoot_interval=shoot_int,
                move_dir=random.uniform(-1.0, 1.0),
                move_timer=random.uniform(0.3, 1.5),
                sprite_w=sw,
                sprite_h=sh,
                wave_amplitude=wave_amp,
                wave_frequency=wave_freq,
                wave_phase=random.uniform(0.0, 2.0 * math.pi),
                active=True,
            )
        )

    # ── Power-ups ──────────────────────────────────────────────────────────

    def _update_powerups(self, dt: float) -> None:
        for pu in self.powerups:
            if not pu.active:
                continue
            pu.y += pu.speed * dt
            if pu.y > DESIGN_H + POWERUP_H:
                pu.active = False

    def _spawn_powerup(self, x: float, y: float) -> None:
        kind = random.choice(POWERUP_KINDS)
        for pu in self.powerups:
            if not pu.active:
                pu.x = x
                pu.y = y
                pu.kind = kind
                pu.active = True
                return
        self.powerups.append(
            PowerUpData(x=x, y=y, kind=kind, active=True)
        )

    def _collect_powerup(self, kind: str) -> None:
        p = self.player
        g = self.game
        if kind == "spread":
            p.power_level = min(3, p.power_level + 1)
            g.powerUpTimer = 8.0
            g.activePowerUp = "spread"
        elif kind == "speed":
            p.fire_rate = 14.0
            g.powerUpTimer = 8.0
            g.activePowerUp = "speed"
        elif kind == "life":
            g.lives = min(5, g.lives + 1)
            g.score += 500

    # ── Combo system ───────────────────────────────────────────────────────

    def _update_combo(self, dt: float) -> None:
        g = self.game
        if g.comboTimer > 0.0:
            g.comboTimer -= dt
            if g.comboTimer <= 0.0:
                g.combo = 0

    def _update_powerup(self, dt: float) -> None:
        g = self.game
        p = self.player
        if g.powerUpTimer > 0.0:
            g.powerUpTimer -= dt
            if g.powerUpTimer <= 0.0:
                g.activePowerUp = ""
                p.power_level = 1
                p.fire_rate = 8.0

    # ── Collisions ─────────────────────────────────────────────────────────

    def _check_collisions(self) -> None:
        self._check_bullets_vs_enemies()
        self._check_enemies_vs_player()
        self._check_enemy_bullets_vs_player()
        self._check_powerups_vs_player()

    def _check_bullets_vs_enemies(self) -> None:
        # Early-out when no enemies are active
        active_enemies = [e for e in self.enemies if e.active]
        if not active_enemies:
            return
        for b in self.bullets:
            if not b.active:
                continue
            bx, by = b.x, b.y
            for e in active_enemies:
                if (
                    bx < e.x + e.sprite_w
                    and bx + BULLET_W > e.x
                    and by < e.y + e.sprite_h
                    and by + BULLET_H > e.y
                ):
                    b.active = False
                    e.hp -= 1
                    if e.hp <= 0:
                        e.active = False
                        self._on_enemy_killed(e)
                    break

    def _check_enemies_vs_player(self) -> None:
        p = self.player
        if not p.alive or self._time < p.invincible_until:
            return
        px, py = p.x, p.y
        for e in self.enemies:
            if not e.active:
                continue
            if (
                px < e.x + e.sprite_w
                and px + PLAYER_W > e.x
                and py < e.y + e.sprite_h
                and py + PLAYER_H > e.y
            ):
                self._hit_player()
                return

    def _check_enemy_bullets_vs_player(self) -> None:
        p = self.player
        if not p.alive or self._time < p.invincible_until:
            return
        px, py = p.x, p.y
        for b in self.enemy_bullets:
            if not b.active:
                continue
            if (
                b.x < px + PLAYER_W
                and b.x + ENEMY_BULLET_W > px
                and b.y < py + PLAYER_H
                and b.y + ENEMY_BULLET_H > py
            ):
                b.active = False
                self._hit_player()
                return

    def _check_powerups_vs_player(self) -> None:
        p = self.player
        if not p.alive:
            return
        px, py = p.x, p.y
        for pu in self.powerups:
            if not pu.active:
                continue
            if (
                px < pu.x + POWERUP_W
                and px + PLAYER_W > pu.x
                and py < pu.y + POWERUP_H
                and py + PLAYER_H > pu.y
            ):
                pu.active = False
                self._collect_powerup(pu.kind)

    # ── Events ─────────────────────────────────────────────────────────────

    def _on_enemy_killed(self, e: EnemyData) -> None:
        base = (
            100
            if e.kind == "alien1"
            else 200 if e.kind == "alien2" else 1000
        )
        multiplier = 1.0 + self.game.combo * 0.5
        self.game.score += int(base * multiplier)
        self.game.combo += 1
        self.game.comboTimer = 2.0
        if random.random() < 0.2:
            cx = e.x + e.sprite_w / 2
            cy = e.y + e.sprite_h / 2
            self._spawn_powerup(cx - POWERUP_W / 2, cy - POWERUP_H / 2)

    def _hit_player(self) -> None:
        self.game.lives -= 1
        self.game.combo = 0
        if self.game.lives <= 0:
            self.player.alive = False
            self.game.status = "game_over"
            self.game.high_score = max(
                self.game.high_score, self.game.score
            )
        else:
            self.player.invincible_until = self._time + 2.0
