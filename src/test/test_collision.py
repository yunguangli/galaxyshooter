"""
test_collision.py — Step 4 interactive test for Collider, Audio, and Effects
(short aliases for CollisionSystem, SoundManager, SplashEffect).

Demo
----
- Blue player moves with WASD / arrow keys.
- SPACE fires yellow bullets (move right).
- Red enemies drift in from the right.
- Bullet hits enemy  → enemy + bullet disappear, burst SFX + particle burst.
- Player touches enemy → player flashes red, ring SFX + expanding ring.
- Health 0  → Game Over dialog.
- All enemies gone → You Win dialog.

Sound
-----
Programmatic WAV beeps are generated in-memory so no audio files are needed.
Replace the beep data with real files / URLs if you want proper sounds:

    snd.load("hit",   "assets/sounds/hit.wav")
    snd.load("hurt",  "assets/sounds/hurt.wav")
    snd.load("shoot", "assets/sounds/shoot.wav")

Run:  cd src && flet run test_collision.py
"""

import flet as ft
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flet_game import (
    Sprite, GameLoop, Label, Input, Collider, Effects, Audio,
    make_beep, audio_available,
)

# ── Beep sounds (no audio files needed) ──────────────────────────────────────

BEEP_SHOOT = make_beep(freq=880,  duration=0.04, volume=0.35)
BEEP_HIT   = make_beep(freq=330,  duration=0.10, volume=0.55)
BEEP_HURT  = make_beep(freq=180,  duration=0.14, volume=0.60)

# ── Layout constants ──────────────────────────────────────────────────────────

W, H = 800, 480
PLAYER_W, PLAYER_H = 40, 40
BULLET_W, BULLET_H = 12, 6
ENEMY_W,  ENEMY_H  = 38, 38
ENEMY_COUNT   = 6
BULLET_SPEED  = 500      # px / s
PLAYER_SPEED  = 220      # px / s
ENEMY_SPEED_MIN = 60
ENEMY_SPEED_MAX = 130
MAX_HEALTH    = 5
HURT_COOLDOWN = 0.8      # seconds between player-hurt events

# ── State ─────────────────────────────────────────────────────────────────────

score     = 0
health    = MAX_HEALTH
hurt_timer = 0.0
game_over  = False

bullets:     list[Sprite] = []
enemies:     list[Sprite] = []
all_sprites: list[Sprite] = []


def main(page: ft.Page) -> None:
    global score, health, hurt_timer, game_over

    page.title = "flet_game — Collision + Sound + Particles"
    page.bgcolor = ft.Colors.BLACK
    page.window.width = W + 20
    page.window.height = H + 120
    page.window.resizable = False

    # ── Canvas ────────────────────────────────────────────────────────────────

    canvas = ft.Stack(width=W, height=H, clip_behavior=ft.ClipBehavior.HARD_EDGE)
    canvas.controls.append(ft.Container(width=W, height=H, bgcolor="#111122"))

    # ── HUD labels ────────────────────────────────────────────────────────────

    score_label  = Label(text="Score: 0",
                         x=10, y=8,  color="white",   size=16)
    health_label = Label(text=f"Health: {'♥ ' * MAX_HEALTH}",
                         x=10, y=30, color="#ff4444",  size=16)
    hint_label   = Label(text="WASD / Arrows: move   SPACE: shoot",
                         x=10, y=H - 26, color="#aaaaaa", size=13)
    canvas.controls += [
        score_label.control,
        health_label.control,
        hint_label.control,
    ]

    # ── SplashEffect (visual — always available) ──────────────────────────────

    fx = Effects(page, canvas)

    # ── SoundManager (optional — skips if flet-audio missing) ────────────────────

    snd: Audio | None = None
    if audio_available():
        snd = Audio(page, pool_size=4)
        snd.load("shoot", BEEP_SHOOT, pool_size=6)
        snd.load("hit",   BEEP_HIT)
        snd.load("hurt",  BEEP_HURT)

    # ── Player ────────────────────────────────────────────────────────────────

    player = Sprite(
        tag="player",
        x=80, y=H // 2 - PLAYER_H // 2,
        width=PLAYER_W, height=PLAYER_H,
        color="#3399ff",
    )
    canvas.controls.append(player.control)
    all_sprites.append(player)

    # ── Enemy wave ────────────────────────────────────────────────────────────

    import random
    random.seed(42)

    _enemy_speeds: dict[int, float] = {}

    def _spawn_enemies() -> None:
        spacing = H // (ENEMY_COUNT + 1)
        for i in range(ENEMY_COUNT):
            ey = spacing * (i + 1) - ENEMY_H // 2
            ex = W + random.randint(0, 200)
            spd = random.uniform(ENEMY_SPEED_MIN, ENEMY_SPEED_MAX)
            e = Sprite(
                tag="enemy",
                x=ex, y=ey,
                width=ENEMY_W, height=ENEMY_H,
                color="#cc2222",
            )
            canvas.controls.append(e.control)
            enemies.append(e)
            all_sprites.append(e)
            _enemy_speeds[id(e)] = spd

    _spawn_enemies()

    # ── Bullet factory ────────────────────────────────────────────────────────

    def _spawn_bullet() -> None:
        if game_over:
            return
        bx = player.x + PLAYER_W
        by = player.y + PLAYER_H // 2 - BULLET_H // 2
        b = Sprite(
            tag="bullet",
            x=bx, y=by,
            width=BULLET_W, height=BULLET_H,
            color="#ffee44",
        )
        canvas.controls.append(b.control)
        bullets.append(b)
        all_sprites.append(b)
        if snd:
            snd.play("shoot")

    # ── InputManager ──────────────────────────────────────────────────────────

    inp = Input(page)

    @inp.on_key_down("space")
    def fire(e=None) -> None:
        _spawn_bullet()

    # ── CollisionSystem ───────────────────────────────────────────────────────

    col = Collider()

    @col.on_collision("bullet", "enemy")
    def bullet_hits_enemy(bullet: Sprite, enemy: Sprite) -> None:
        global score
        if not bullet.visible or not enemy.visible:
            return
        bullet.hide()
        enemy.hide()
        score += 1
        score_label.text = f"Score: {score}"

        # Centre of destroyed enemy
        cx = enemy.x + ENEMY_W / 2
        cy = enemy.y + ENEMY_H / 2
        fx.burst(cx, cy, color="#ff8800", count=10, distance=48, duration=420)
        if snd:
            snd.play("hit")

        _check_win()

    # ── Game-state helpers ────────────────────────────────────────────────────

    def _update_health_label() -> None:
        hearts = "♥ " * health + "♡ " * (MAX_HEALTH - health)
        health_label.text = f"Health: {hearts.strip()}"

    def _check_win() -> None:
        if all(not e.visible for e in enemies):
            _show_dialog("You Win! 🎉", f"Score: {score}")

    def _show_dialog(title: str, body: str) -> None:
        global game_over
        game_over = True
        loop.stop()

        async def _quit(e: ft.ControlEvent) -> None:
            page.pop_dialog()
            await page.window.close()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(body),
            actions=[ft.TextButton("OK", on_click=_quit)],
        ))

    # ── Game loop ─────────────────────────────────────────────────────────────

    loop = GameLoop(page)

    @loop.on_update
    def update(dt: float) -> None:
        global health, hurt_timer, game_over

        if game_over:
            return

        vx, vy = 0.0, 0.0
        if inp.is_key_down("w") or inp.is_key_down("up"):     vy = -PLAYER_SPEED
        if inp.is_key_down("s") or inp.is_key_down("down"):   vy =  PLAYER_SPEED
        if inp.is_key_down("a") or inp.is_key_down("left"):   vx = -PLAYER_SPEED
        if inp.is_key_down("d") or inp.is_key_down("right"):  vx =  PLAYER_SPEED

        player.x = max(0.0, min(W - PLAYER_W, player.x + vx * dt))
        player.y = max(0.0, min(H - PLAYER_H, player.y + vy * dt))

        for b in bullets:
            if b.visible:
                b.x += BULLET_SPEED * dt
                if b.x > W:
                    b.hide()

        for e in enemies:
            if e.visible:
                e.x -= _enemy_speeds[id(e)] * dt
                if e.x < -ENEMY_W:
                    e.x = W + 20
                    e.y = max(0, min(H - ENEMY_H, e.y + (50 - 100 * (e.y > H / 2))))

        col.update(all_sprites, page)

        hurt_timer = max(0.0, hurt_timer - dt)
        if hurt_timer == 0.0:
            for e in Collider.collisions_with(player, enemies):
                if e.visible:
                    health -= 1
                    hurt_timer = HURT_COOLDOWN
                    fx.ring(
                        player.x + PLAYER_W / 2,
                        player.y + PLAYER_H / 2,
                        color="#ff2222", radius=26, duration=400,
                    )
                    if snd:
                        snd.play("hurt")
                    player.color = "#ff2222"
                    _update_health_label()
                    if health <= 0:
                        game_over = True
                        _show_dialog("Game Over", f"Final score: {score}")
                    break

        if hurt_timer > 0.0:
            player.color = "#ff2222" if hurt_timer > HURT_COOLDOWN * 0.5 else "#ff9933"
        else:
            player.color = "#3399ff"

    # ── Layout ────────────────────────────────────────────────────────────────

    page.add(ft.Column(
        [inp.wrap(canvas)],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    ))
    loop.start()


ft.run(main)
