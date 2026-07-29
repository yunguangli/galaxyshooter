"""
test_game.py — Step 6 interactive test for Game.

Demonstrates the full Game API including the scene stack (push / pop / run_scene):

  TitleScene          ← SPACE to start a new game
    ↓  game.run_scene()
  GameScene           ← ESC to pause, WASD to move, SPACE to shoot
    ↓  game.push_scene()  +  game.loop.pause()
  PauseScene          ← ESC: resume game   Q: quit to title
    ↓  game.pop_scene()  +  game.loop.resume()
  GameScene (resumed) ← game state preserved

  Win / Lose in GameScene → dialog → game.run_scene(TitleScene)

Key differences from test_scene.py
-----------------------------------
- Single Game instance replaces separate GameLoop + Scene boilerplate.
- game.run(TitleScene) — mounts first scene and starts loop in one call.
- Scenes are subclasses; on_enter() sets up state, @self.on_update registers the
  frame callback and auto-removes it when the scene exits.
- ESC from GameScene demonstrates push_scene (stack) not run_scene (replace).

Run:  cd src && flet run test_game.py
"""

import flet as ft
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import (
    Game, Scene, Sprite, Label, GameLoop,
    Collider, Effects, Audio,
    audio_available, make_beep,
    Leaderboard,
)

BEEP_SHOOT = make_beep(freq=880,  duration=0.04, volume=0.35)
BEEP_HURT  = make_beep(freq=180,  duration=0.14, volume=0.60)

# ── Asset paths ───────────────────────────────────────────────────────────────
# Asset paths are relative to the assets_dir root ("assets/" folder).
# Using relative paths ensures they are served correctly on web, desktop,
# and mobile — absolute OS paths only work on desktop.
GIF_EXPLOSION = "fire_explosion.gif"
SFX_HIT       = "cinematic-explosion.mp3"
BGM_LOOP      = "freesound_song.mp3"

# ── Constants ─────────────────────────────────────────────────────────────────

W, H            = 800, 480
PLAYER_W, PLAYER_H = 40, 40
BULLET_W, BULLET_H = 12, 6
ENEMY_W,  ENEMY_H  = 38, 38
ENEMY_COUNT    = 6
BULLET_SPEED   = 500
PLAYER_SPEED   = 220
ENEMY_SPEED_MIN = 60
ENEMY_SPEED_MAX = 130
MAX_HEALTH     = 5
HURT_COOLDOWN  = 0.8


# ═══════════════════════════════════════════════════════════════════════════════
# TitleScene — static title screen, SPACE starts a new game
# ═══════════════════════════════════════════════════════════════════════════════

class TitleScene(Scene):
    def __init__(self, game: Game, lb: Leaderboard) -> None:
        super().__init__(game.page, game.width, game.height, "#0a0a1a")
        self._game = game
        self._lb = lb

    def on_enter(self) -> None:
        cx = self._width / 2

        title = Label(
            text="flet_game", x=cx, y=self._height / 2 - 100,
            color="white", size=56,
        )
        sub = Label(
            text="Step 7 — Leaderboard",
            x=cx, y=self._height / 2 - 30,
            color="#6688cc", size=18,
        )
        hint = Label(
            text="SPACE: play   Q: quit",
            x=cx, y=self._height / 2 + 40,
            color="#888888", size=16,
        )
        for lbl in (title, sub, hint):
            self.add(lbl, z=10)

        # ── Leaderboard ───────────────────────────────────────────────────────
        board_title = Label(
            text="— Top Scores —",
            x=cx, y=self._height / 2 + 85,
            color="#aaaacc", size=14,
        )
        self.add(board_title, z=10)
        entries = self._lb.top(5)
        if not entries:
            no_score = Label(
                text="No scores yet — be the first!",
                x=cx, y=self._height / 2 + 110,
                color="#555577", size=13,
            )
            self.add(no_score, z=10)
        else:
            for i, entry in enumerate(entries):
                row = Label(
                    text=f"{i+1}.  {entry['name']:<16} {entry['score']:>5}",
                    x=cx, y=self._height / 2 + 110 + i * 22,
                    color="#778899", size=13,
                )
                self.add(row, z=10)

        @self.input.on_key_down("space")
        def start(e=None) -> None:
            self._game.run_scene(GameScene(self._game, self._lb))

        @self.input.on_key_down("q")
        async def quit_game(e=None) -> None:
            await self._game.page.window.close()


# ═══════════════════════════════════════════════════════════════════════════════
# PauseScene — pushed on top of GameScene; ESC resumes, Q quits to title
# ═══════════════════════════════════════════════════════════════════════════════

class PauseScene(Scene):
    def __init__(self, game: Game, lb: Leaderboard) -> None:
        super().__init__(game.page, game.width, game.height, "#1a1a33")
        self._game = game
        self._lb = lb

    def on_enter(self) -> None:
        cx = self._width / 2
        cy = self._height / 2

        paused = Label(text="PAUSED", x=cx, y=cy - 50, color="white", size=48)
        hint = Label(
            text="ESC: resume   Q: quit to title",
            x=cx, y=cy + 20, color="#aaaaaa", size=18,
        )
        self.add(paused, z=10)
        self.add(hint, z=10)

        @self.input.on_key_down("escape")
        def do_resume(e=None) -> None:
            self._game.pop_scene()
            self._game.loop.resume()

        @self.input.on_key_down("q")
        def do_quit(e=None) -> None:
            # pop_scene destroys PauseScene; _clear_stack inside run_scene
            # destroys GameScene.  TitleScene.on_enter wires fresh input.
            self._game.run_scene(TitleScene(self._game, self._lb))


# ═══════════════════════════════════════════════════════════════════════════════
# GameScene — the shoot-em-up (adds its update callback; removes on exit)
# ═══════════════════════════════════════════════════════════════════════════════

class GameScene(Scene):
    def __init__(self, game: Game, lb: Leaderboard) -> None:
        super().__init__(game.page, game.width, game.height, "#111122")
        self._game = game
        self._lb = lb
        self._music = None
        self._snd = None

    def on_enter(self) -> None:
        # ── Mutable state (local to this on_enter closure) ────────────────────
        score      = 0
        health     = MAX_HEALTH
        hurt_timer = 0.0
        game_over  = False

        bullets:      list[Sprite] = []
        enemies:      list[Sprite] = []
        all_sprites:  list[Sprite] = []
        enemy_speeds: dict[int, float] = {}

        random.seed()   # random seed per game so each run differs

        # ── HUD ───────────────────────────────────────────────────────────────
        score_lbl  = Label(text="Score: 0",
                           x=10, y=8, color="white", size=16)
        health_lbl = Label(text=f"Health: {'♥ ' * MAX_HEALTH}",
                           x=10, y=30, color="#ff4444", size=16)
        hint_lbl   = Label(text="WASD/Arrows: move   SPACE: shoot   ESC: pause",
                           x=10, y=self._height - 26, color="#aaaaaa", size=13)
        for lbl in (score_lbl, health_lbl, hint_lbl):
            self.add(lbl, z=10)

        # ── Effects & sound ───────────────────────────────────────────────────
        fx = Effects(self._game.page, self.canvas)

        snd: Audio | None = None
        if audio_available():
            import flet_audio as fta
            # Looping background music.
            # Desktop/mobile: autoplay=True is reliable — Flutter handles
            # load→play internally.
            # Web: autoplay=True causes a 30-second TimeoutException (browser
            # blocks audio before a user gesture). Instead we hook on_loaded
            # so play() fires only once the source is actually ready in the
            # browser's audio element — avoiding the race a bare run_task has.
            try:
                web = self._game.page.web
                if web:
                    async def _on_bgm_loaded(e, _self=self):
                        try:
                            await _self._music.play()
                        except Exception:
                            pass  # browser blocked; safe to ignore

                    self._music = fta.Audio(
                        src=BGM_LOOP,
                        release_mode=fta.ReleaseMode.LOOP,
                        volume=0.35,
                        on_loaded=_on_bgm_loaded,
                    )
                else:
                    self._music = fta.Audio(
                        src=BGM_LOOP,
                        release_mode=fta.ReleaseMode.LOOP,
                        volume=0.35,
                        autoplay=True,
                    )
                self._game.page.services.append(self._music)
                self._game.page.update()
            except Exception:
                self._music = None
            # Polyphonic sound effects
            snd = Audio(self._game.page, pool_size=4)
            snd.load("shoot", BEEP_SHOOT, pool_size=6)
            snd.load("hit",   SFX_HIT)
            snd.load("hurt",  BEEP_HURT)
            self._snd = snd

        # ── Player ────────────────────────────────────────────────────────────
        player = Sprite(
            tag="player",
            x=80, y=self._height // 2 - PLAYER_H // 2,
            width=PLAYER_W, height=PLAYER_H, color="#3399ff",
        )
        self.add(player)
        all_sprites.append(player)

        # ── Enemies ───────────────────────────────────────────────────────────
        spacing = int(self._height) // (ENEMY_COUNT + 1)
        for i in range(ENEMY_COUNT):
            ey  = spacing * (i + 1) - ENEMY_H // 2
            ex  = self._width + random.randint(0, 200)
            spd = random.uniform(ENEMY_SPEED_MIN, ENEMY_SPEED_MAX)
            e = Sprite(
                tag="enemy",
                x=ex, y=ey,
                width=ENEMY_W, height=ENEMY_H, color="#cc2222",
            )
            self.add(e)
            enemies.append(e)
            all_sprites.append(e)
            enemy_speeds[id(e)] = spd

        # ── Input ─────────────────────────────────────────────────────────────
        inp = self.input

        def _spawn_bullet() -> None:
            if game_over:
                return
            b = Sprite(
                tag="bullet",
                x=player.x + PLAYER_W,
                y=player.y + PLAYER_H // 2 - BULLET_H // 2,
                width=BULLET_W, height=BULLET_H, color="#ffee44",
            )
            self.add(b)
            bullets.append(b)
            all_sprites.append(b)
            if snd:
                snd.play("shoot")

        @inp.on_key_down("space")
        def fire(e=None) -> None:
            _spawn_bullet()

        @inp.on_key_down("escape")
        def do_pause(e=None) -> None:
            if not game_over:
                self._game.push_scene(PauseScene(self._game, self._lb))
                self._game.loop.pause()

        # ── Collision ─────────────────────────────────────────────────────────
        col = Collider()

        @col.on_collision("bullet", "enemy")
        def bullet_hits_enemy(bullet: Sprite, enemy: Sprite) -> None:
            nonlocal score
            if not bullet.visible or not enemy.visible:
                return
            bullet.hide()
            enemy.hide()
            score += 1
            score_lbl.text = f"Score: {score}"
            cx = enemy.x + ENEMY_W / 2
            cy = enemy.y + ENEMY_H / 2
            fx.animate(cx, cy, src=GIF_EXPLOSION, kind="gif", width=80, height=80, duration=700)
            if snd:
                snd.play("hit")
            if all(not en.visible for en in enemies):
                _show_result("You Win! 🎉", score)

        # ── Dialog ────────────────────────────────────────────────────────────
        def _show_result(title: str, final_score: int) -> None:
            nonlocal game_over
            game_over = True
            self._game.loop.stop()

            rank = self._lb.rank_of(final_score)
            name_field = ft.TextField(
                value="Player",
                label="Your name",
                width=220,
                autofocus=True,
            )

            async def _save_and_go(e: ft.ControlEvent) -> None:
                await self._lb.add(name_field.value, final_score)
                self._game.page.pop_dialog()
                self._game.run_scene(TitleScene(self._game, self._lb))
                self._game.loop.start()

            self._game.page.show_dialog(ft.AlertDialog(
                title=ft.Text(title),
                content=ft.Column(
                    controls=[
                        ft.Text(f"Score: {final_score}   (rank #{rank})"),
                        name_field,
                    ],
                    tight=True,
                    spacing=10,
                ),
                actions=[ft.TextButton("Save & back to title", on_click=_save_and_go)],
            ))

        # ── Frame update ──────────────────────────────────────────────────────
        # @self.on_update registers with the loop AND auto-removes when the
        # scene exits — no manual add_callback / remove_callback needed.
        @self.on_update
        def update(dt: float) -> None:
            nonlocal health, hurt_timer, game_over

            if game_over:
                return

            # Player movement
            vx, vy = 0.0, 0.0
            if inp.is_key_down("w") or inp.is_key_down("up"):    vy = -PLAYER_SPEED
            if inp.is_key_down("s") or inp.is_key_down("down"):  vy =  PLAYER_SPEED
            if inp.is_key_down("a") or inp.is_key_down("left"):  vx = -PLAYER_SPEED
            if inp.is_key_down("d") or inp.is_key_down("right"): vx =  PLAYER_SPEED
            player.x = max(0.0, min(self._width  - PLAYER_W, player.x + vx * dt))
            player.y = max(0.0, min(self._height - PLAYER_H, player.y + vy * dt))

            # Bullets
            for b in bullets:
                if b.visible:
                    b.x += BULLET_SPEED * dt
                    if b.x > self._width:
                        b.hide()

            # Enemies
            for en in enemies:
                if en.visible:
                    en.x -= enemy_speeds[id(en)] * dt
                    if en.x < -ENEMY_W:
                        en.x = self._width + 20
                        en.y = max(0, min(
                            self._height - ENEMY_H,
                            en.y + (50 if en.y < self._height / 2 else -50),
                        ))

            col.update(all_sprites, self._game.page)

            # Hurt
            hurt_timer = max(0.0, hurt_timer - dt)
            if hurt_timer == 0.0:
                for en in Collider.collisions_with(player, enemies):
                    if en.visible:
                        health -= 1
                        hurt_timer = HURT_COOLDOWN
                        fx.ring(
                            player.x + PLAYER_W / 2, player.y + PLAYER_H / 2,
                            color="#ff2222", radius=26, duration=400,
                        )
                        if snd:
                            snd.play("hurt")
                        hearts = "♥ " * health + "♡ " * (MAX_HEALTH - health)
                        health_lbl.text = f"Health: {hearts.strip()}"
                        if health <= 0:
                            _show_result("Game Over", score)
                        break

            if hurt_timer > 0.0:
                player.color = "#ff2222" if hurt_timer > HURT_COOLDOWN * 0.5 else "#ff9933"
            elif not game_over:
                player.color = "#3399ff"

        # Start the loop (no-op if already running; restartable after stop()).
        self._game.loop.start()

    def on_exit(self) -> None:
        """Stop audio; frame callback is auto-removed by @self.on_update."""
        if self._music is not None:
            try:
                self._game.page.services.remove(self._music)
                self._game.page.update()
            except Exception:
                pass
            self._music = None
        if self._snd is not None:
            self._snd.destroy()
            self._snd = None


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

async def main(page: ft.Page) -> None:
    lb = Leaderboard(page)
    await lb.load()   # populate from shared_preferences before first scene mounts

    game = Game(
        page,
        width=W, height=H,
        fps=60,
        title="flet_game — Game (Step 7)",
    )
    # game.run() mounts TitleScene and starts the loop.
    # TitleScene is static so the loop ticks idle until GameScene pushes callbacks.
    game.run(TitleScene(game, lb))


_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
ft.run(main, assets_dir=_ASSETS_DIR)
