from __future__ import annotations

import math
import time

import flet as ft
from flet import Scale
from flet_game import Button, Game, Label, Scene, Sprite

from .fx import Effects, Starfield
from .hud import HUD
from .manager import (
    BOSS_H,
    BOSS_W,
    BULLET_H,
    BULLET_W,
    DESIGN_H,
    DESIGN_W,
    ENEMY_BULLET_H,
    ENEMY_BULLET_W,
    ENEMY_H,
    ENEMY_W,
    PLAYER_H,
    PLAYER_W,
    POWERUP_H,
    POWERUP_W,
    GalaxyManager,
)
from .sounds import AudioController
from .sprites import POWERUP_COLORS, make_player_sprite, prewarm_pools

_HOLD_MS = 0.8


def _rescale_from_page(page: ft.Page, scene: Scene) -> None:
    pw = max(page.width or DESIGN_W, 1.0)
    ph = max(page.height or DESIGN_H, 1.0)
    s = min(pw / DESIGN_W, ph / DESIGN_H)
    scene.root.scale = Scale(scale_x=s, scale_y=s)
    scene.root.update()


class StartView(Scene):
    def __init__(self, game: Game) -> None:
        super().__init__(
            game.page, DESIGN_W, DESIGN_H, "#0a0a1a", clip=True
        )
        self._game = game

    def on_enter(self) -> None:
        self._starfield = Starfield(DESIGN_W, DESIGN_H)
        with self.defer_rebuild():
            for c in self._starfield.build_all():
                self.add(c, z=0)

        title = Label(
            x=DESIGN_W / 2 - 100,
            y=180,
            text="GALAXY\nSHOOTER",
            size=42,
            color="#00e5ff",
            bold=True,
        )
        title._text_ctrl.text_align = ft.TextAlign.CENTER
        self.add(title, z=10)

        self._subtitle = Label(
            x=DESIGN_W / 2 - 80,
            y=300,
            text="TAP OR PRESS SPACE",
            size=16,
            color="#ffffff",
            opacity=1.0,
        )
        self.add(self._subtitle, z=10)

        def on_start(_=None) -> None:
            self._game.run_scene(PlayView(self._game))

        btn = Button(
            x=DESIGN_W / 2 - 70,
            y=380,
            width=140,
            height=48,
            text="START",
            text_size=22,
            bold=True,
            text_color="#ffffff",
            color="#1a237e",
            hover_color="#283593",
            border_radius=24,
            on_click=on_start,
        )
        self.add(btn, z=10)

        self._blink_time = 0.0

        @self.on_update
        def update(dt: float) -> None:
            self._starfield.update(dt)
            self._blink_time += dt
            self._subtitle.opacity = 0.5 + 0.5 * math.sin(
                self._blink_time * 3.0
            )

        @self.input.on_key_down("space")
        def on_space(_=None) -> None:
            on_start()

        @self.input.on_key_down("enter")
        def on_enter(_=None) -> None:
            on_start()

        @self.input.on_click
        def on_tap(x: float, y: float) -> None:
            on_start()


class PlayView(Scene):
    def __init__(self, game: Game) -> None:
        super().__init__(
            game.page, DESIGN_W, DESIGN_H, "#0a0a1a", clip=True
        )
        self._game = game
        self._manager = GalaxyManager()
        self._effects: Effects | None = None
        self._hud = HUD()
        self._audio: AudioController | None = None
        self._player_sprite: Sprite | None = None
        self._starfield: Starfield | None = None
        self._pools: dict = {}
        self._arrow_left_ts = -999.0
        self._arrow_right_ts = -999.0
        self._space_ts = -999.0
        self._trail_timers: dict[int, float] = {}
        self._touch_shoot_ts = -999.0

    def on_enter(self) -> None:
        self._manager.start_game()

        self._starfield = Starfield(DESIGN_W, DESIGN_H)
        with self.defer_rebuild():
            for c in self._starfield.build_all():
                self.add(c, z=0)

        self._player_sprite = make_player_sprite()
        self.add(self._player_sprite, z=2)

        self._pools = prewarm_pools(self)

        self.add(self._hud.score_label, z=10)
        self.add(self._hud.level_label, z=10)
        self.add(self._hud.lives_label, z=10)
        self.add(self._hud.combo_label, z=10)
        self.add(self._hud.powerup_label, z=10)

        self._effects = Effects(self._page, self.canvas)
        self._audio = AudioController(self._page)

        self._game_over_played = False
        self._touch_x: float | None = None
        self._prev_shot_time: float = -999.0

        self._setup_input()
        self._setup_update()
        _rescale_from_page(self._page, self)

    def _setup_input(self) -> None:
        inp = self.input

        @inp.on_key_down("arrowleft")
        def key_left(_=None) -> None:
            self._arrow_left_ts = time.monotonic()

        @inp.on_key_down("arrowright")
        def key_right(_=None) -> None:
            self._arrow_right_ts = time.monotonic()

        @inp.on_key_down("space")
        def key_shoot(_=None) -> None:
            self._space_ts = time.monotonic()

        @inp.on_drag
        def on_drag(x: float, y: float, dx: float, dy: float) -> None:
            self._touch_x = x
            self._touch_shoot_ts = time.monotonic()

        @inp.on_click
        def on_click(x: float, y: float) -> None:
            if self._manager.game.status == "playing":
                self._touch_x = x
                self._touch_shoot_ts = time.monotonic()

    def _setup_update(self) -> None:
        @self.on_update
        def update(dt: float) -> None:
            self._starfield.update(dt)
            m = self._manager
            now = time.monotonic()

            left = self.input.is_key_down("arrowleft")
            right = self.input.is_key_down("arrowright")

            if not left:
                left = (now - self._arrow_left_ts) < _HOLD_MS
            if not right:
                right = (now - self._arrow_right_ts) < _HOLD_MS

            if left and right:
                move_dir = 1.0 if self._arrow_right_ts > self._arrow_left_ts else -1.0
            elif left:
                move_dir = -1.0
            elif right:
                move_dir = 1.0
            elif self._touch_x is not None:
                cx = m.player.x + PLAYER_W / 2
                diff = self._touch_x - cx
                move_dir = 1.0 if diff > 4 else -1.0 if diff < -4 else 0.0
                self._touch_x = None
            else:
                move_dir = 0.0

            shooting = (
                self.input.is_key_down("space")
                or (now - self._space_ts) < _HOLD_MS
                or (now - self._touch_shoot_ts) < _HOLD_MS
            )

            prev_shot_time = m.player.last_shot_time
            prev_powerups = {id(pu): pu for pu in m.powerups if pu.active}

            prev_active = m.player.alive
            prev_lives = m.game.lives
            prev_enemies = {id(e): e for e in m.enemies if e.active}
            m.update(dt, move_dir, shooting)

            if m.player.last_shot_time != prev_shot_time and self._audio.available:
                self._audio.play_shoot()
                # Dramatic muzzle flash scaled by power level
                if self._player_sprite and m.player.alive:
                    cx = m.player.x + PLAYER_W / 2
                    cy = m.player.y
                    self._effects.muzzle_flash(cx, cy, m.player.power_level)

            for puid, old_pu in prev_powerups.items():
                if not old_pu.active and old_pu.y < DESIGN_H and self._audio.available:
                    self._audio.play_pickup()
                    break

            for eid, old_e in prev_enemies.items():
                if old_e.active:
                    continue
                cx = old_e.x + (BOSS_W if old_e.kind == "boss" else ENEMY_W) / 2
                cy = old_e.y + (BOSS_H if old_e.kind == "boss" else ENEMY_H) / 2
                if old_e.kind == "boss":
                    self._effects.big_explosion(cx, cy)
                else:
                    self._effects.explosion(cx, cy)
                if self._audio.available:
                    self._audio.play_explosion()

            for e in m.enemies:
                if not e.active:
                    self._trail_timers.pop(id(e), None)
                    continue
                last = self._trail_timers.get(id(e), -999.0)
                if m._time - last >= 0.15:
                    self._trail_timers[id(e)] = m._time
                    cx = e.x + e.sprite_w / 2
                    cy = e.y - 4
                    self._effects.trail(cx, cy)

            self._sync_view(m)

            if prev_active and not m.player.alive:
                if self._audio.available:
                    self._audio.play_death()
                self._effects.big_explosion(
                    m.player.x + PLAYER_W / 2,
                    m.player.y + PLAYER_H / 2,
                )
            if m.game.lives < prev_lives and m.player.alive:
                if self._audio.available:
                    self._audio.play_hit()
                self._effects.hit_flash(
                    m.player.x + PLAYER_W / 2,
                    m.player.y + PLAYER_H / 2,
                )

            if m.game.status == "game_over" and not self._game_over_played:
                self._game_over_played = True
                if self._audio.available:
                    self._audio.play_defeat()
                self._game.run_scene(GameOverView(self._game, m))

    def _sync_view(self, m: GalaxyManager) -> None:
        pool_b = self._pools["bullets"]
        pool_eb = self._pools["ebullets"]
        pool_a1 = self._pools["alien1"]
        pool_a2 = self._pools["alien2"]
        pool_boss = self._pools["boss"]
        pool_pu = self._pools["powerups"]

        pool_b.release_all_and_hide()
        for b in m.bullets:
            if not b.active:
                continue
            s = pool_b.acquire()
            if s is None:
                break
            s.x = b.x
            s.y = b.y
            s.visible = True

        pool_eb.release_all_and_hide()
        for b in m.enemy_bullets:
            if not b.active:
                continue
            s = pool_eb.acquire()
            if s is None:
                break
            s.x = b.x
            s.y = b.y
            s.visible = True

        pool_a1.release_all_and_hide()
        pool_a2.release_all_and_hide()
        pool_boss.release_all_and_hide()
        for e in m.enemies:
            if not e.active:
                continue
            if e.kind == "boss":
                s = pool_boss.acquire()
            elif e.kind == "alien2":
                s = pool_a2.acquire()
            else:
                s = pool_a1.acquire()
            if s is None:
                continue
            s.x = e.x
            s.y = e.y
            s.visible = True

        pool_pu.release_all_and_hide()
        for pu in m.powerups:
            if not pu.active:
                continue
            s = pool_pu.acquire()
            if s is None:
                break
            s.color = POWERUP_COLORS.get(pu.kind, "#ffffff")
            s.x = pu.x
            s.y = pu.y
            s.visible = True

        self._player_sprite.x = m.player.x
        self._player_sprite.y = m.player.y
        self._player_sprite.visible = m.player.alive
        if m.player.invincible_until > m._time:
            self._player_sprite.opacity = (
                0.3 + 0.7 * abs(math.sin(m._time * 12))
            )
        else:
            self._player_sprite.opacity = 1.0

        self._hud.sync(m.game)

    def on_exit(self) -> None:
        if self._audio is not None:
            self._audio.destroy()


class GameOverView(Scene):
    def __init__(self, game: Game, manager: GalaxyManager) -> None:
        super().__init__(
            game.page, DESIGN_W, DESIGN_H, "#0a0a1a", clip=True
        )
        self._game = game
        self._manager = manager

    def on_enter(self) -> None:
        self._starfield = Starfield(DESIGN_W, DESIGN_H)
        with self.defer_rebuild():
            for c in self._starfield.build_all():
                self.add(c, z=0)

        go_label = Label(
            x=DESIGN_W / 2 - 100,
            y=160,
            text="GAME OVER",
            size=40,
            color="#ff1744",
            bold=True,
        )
        self.add(go_label, z=10)

        score_text = f"SCORE: {self._manager.game.score:,}"
        score_label = Label(
            x=DESIGN_W / 2 - 80,
            y=250,
            text=score_text,
            size=22,
            color="#ffffff",
        )
        self.add(score_label, z=10)

        hs = self._manager.game.high_score
        hi_text = f"HIGH SCORE: {hs:,}"
        hi_label = Label(
            x=DESIGN_W / 2 - 90,
            y=290,
            text=hi_text,
            size=18,
            color="#ffd740",
            bold=True,
        )
        self.add(hi_label, z=10)

        lvl_text = f"LEVEL REACHED: {self._manager.game.level}"
        lvl_label = Label(
            x=DESIGN_W / 2 - 80,
            y=330,
            text=lvl_text,
            size=16,
            color="#90caf9",
        )
        self.add(lvl_label, z=10)

        def restart(_=None) -> None:
            self._game.run_scene(PlayView(self._game))

        def restart_at_level(_=None) -> None:
            # Reset player position and lives but keep the level
            self._manager.game.level = max(1, self._manager.game.level)
            self._manager.game.lives = 3
            self._manager.game.status = "playing"
            self._game.run_scene(PlayView(self._game))

        # Restart button — full reset to level 1
        btn_restart = Button(
            x=DESIGN_W / 2 - 155,
            y=420,
            width=140,
            height=48,
            text="RESTART",
            text_size=20,
            bold=True,
            text_color="#ffffff",
            color="#b71c1c",
            hover_color="#d32f2f",
            border_radius=24,
            on_click=restart,
        )
        self.add(btn_restart, z=10)

        # Continue button — restart at the current level
        btn_continue = Button(
            x=DESIGN_W / 2 + 15,
            y=420,
            width=140,
            height=48,
            text="CONTINUE",
            text_size=20,
            bold=True,
            text_color="#ffffff",
            color="#1a237e",
            hover_color="#283593",
            border_radius=24,
            on_click=restart_at_level,
        )
        self.add(btn_continue, z=10)

        self._blink_time = 0.0
        self._tap_label = Label(
            x=DESIGN_W / 2 - 90,
            y=500,
            text="TAP TO RESTART",
            size=16,
            color="#ffffff",
            opacity=1.0,
        )
        self.add(self._tap_label, z=10)

        @self.on_update
        def update(dt: float) -> None:
            self._starfield.update(dt)
            self._blink_time += dt
            self._tap_label.opacity = 0.4 + 0.6 * math.sin(
                self._blink_time * 3.0
            )

        @self.input.on_key_down("space")
        def on_space(_=None) -> None:
            restart()

        @self.input.on_key_down("enter")
        def on_enter(_=None) -> None:
            restart()

        @self.input.on_key_down("c")
        def on_continue(_=None) -> None:
            restart_at_level()

        @self.input.on_click
        def on_tap(x: float, y: float) -> None:
            restart()
