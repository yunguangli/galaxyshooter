"""
test_animation.py — Step 15: SpriteAnimation frame-by-frame animation
=======================================================================
Run with:
    python src/test/test_animation.py
  or:
    flet run src/test/test_animation.py

What is tested
--------------
  ✓ SpriteAnimation with colour frames — cycles through a list of CSS colours
  ✓ SpriteAnimation with property-dict frames — color + scale together
  ✓ register(loop)    — auto-update via game loop (no manual update() call)
  ✓ play() / pause() / stop() / reset() / seek()
  ✓ loop=True   — wraps after last frame
  ✓ loop=False  — stops on last frame, fires on_complete callback
  ✓ fps change  — slider updates animation speed at runtime
  ✓ Multiple animations on different sprites simultaneously
  ✓ Sprite.image — photo frames simulated with coloured frames

Demo
----
  Row 1 — "Coin" sprite cycling gold/yellow/orange at 8 fps (loop=True)
  Row 2 — "Flash" sprite: white→red→red pulse, loop=False, then restarts
  Row 3 — "Heartbeat" sprite: colour + scale together (breathe animation)
  Row 4 — "Idle" sprite: manually seeking frames via a slider
Buttons and a FPS slider let you control playback interactively.
Press ESC or Q to quit.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import Sprite, GameLoop, Label, Scene, SpriteAnimation

W, H = 640, 520


def main(page: ft.Page) -> None:
    page.title = "flet_game — Step 15: SpriteAnimation"
    page.bgcolor = ft.Colors.GREY_900
    page.padding = 16
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # ── Scene + loop ─────────────────────────────────────────────────────────
    scene = Scene(page, width=W, height=H, bgcolor="#111")
    inp   = scene.input
    loop  = GameLoop(page, fps=60)

    status = ft.Text("", color=ft.Colors.AMBER, size=13)

    def log(msg: str) -> None:
        status.value = msg
        status.update()

    # ── Row labels ────────────────────────────────────────────────────────────
    def row_label(text, y):
        lbl = Label(text=text, x=8, y=y+10, color="#aaa", size=12)
        scene.add(lbl, z=10)

    row_label("Coin  (colour, loop=True)", 0)
    row_label("Flash (colour, loop=False)", 110)
    row_label("Heartbeat (color+scale, loop=True)", 220)
    row_label("Manual seek (slider)", 330)

    # ── Sprite 1: Coin ────────────────────────────────────────────────────────
    coin = Sprite(x=50, y=30, width=60, height=60, color="gold", border_radius=30)
    scene.add(coin, z=5)

    coin_anim = SpriteAnimation(
        coin,
        frames=["gold", "#ffd700", "orange", "#ffa500", "#ff8c00", "orange"],
        fps=8,
        loop=True,
    )
    coin_anim.register(loop).play()

    lbl_coin = Label(text="frame: 0/5", x=130, y=48, color="white", size=12)
    scene.add(lbl_coin, z=10)

    # ── Sprite 2: Flash ───────────────────────────────────────────────────────
    flash = Sprite(x=50, y=140, width=60, height=60, color="white", border_radius=8)
    scene.add(flash, z=5)

    def restart_flash():
        flash_anim.reset()
        flash_anim.play()
        log("Flash animation complete → restarting")

    flash_anim = SpriteAnimation(
        flash,
        frames=["white", "red", "#ff6666", "red", "#330000"],
        fps=10,
        loop=False,
        on_complete=restart_flash,
    )
    flash_anim.register(loop).play()

    lbl_flash = Label(text="loop=False, on_complete restarts", x=130, y=158,
                      color="white", size=12)
    scene.add(lbl_flash, z=10)

    # ── Sprite 3: Heartbeat ───────────────────────────────────────────────────
    heart = Sprite(x=50, y=250, width=60, height=60, color="#e63946", border_radius=30)
    scene.add(heart, z=5)

    heart_anim = SpriteAnimation(
        heart,
        frames=[
            {"color": "#e63946", "scale": 1.0},
            {"color": "#ff6b6b", "scale": 1.15},
            {"color": "#e63946", "scale": 1.0},
            {"color": "#c1121f", "scale": 0.9},
        ],
        fps=4,
        loop=True,
    )
    heart_anim.register(loop).play()

    lbl_heart = Label(text="property dict: color + scale", x=130, y=268,
                      color="white", size=12)
    scene.add(lbl_heart, z=10)

    # ── Sprite 4: Manual seek ─────────────────────────────────────────────────
    idle_frames = ["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"]
    idle = Sprite(x=50, y=360, width=60, height=60, color=idle_frames[0], border_radius=4)
    scene.add(idle, z=5)

    idle_anim = SpriteAnimation(idle, frames=idle_frames, fps=0, loop=True)
    idle_anim.register(loop)  # registered but fps=0 so update() does nothing

    lbl_idle = Label(text="drag slider →", x=130, y=378, color="white", size=12)
    scene.add(lbl_idle, z=10)

    # ── Update labels each frame ──────────────────────────────────────────────
    @loop.on_update
    def _labels(dt: float) -> None:
        lbl_coin.text  = f"frame: {coin_anim.current_frame}/{coin_anim.frame_count-1}"
        lbl_coin.update()

    # ── Keyboard ─────────────────────────────────────────────────────────────
    @inp.on_key_down("escape")
    @inp.on_key_down("q")
    async def quit(e=None): await page.window.close()

    # ── Mount scene ───────────────────────────────────────────────────────────
    scene.mount()

    # ── Controls (outside scene) ──────────────────────────────────────────────
    def _play(_):
        coin_anim.play(); flash_anim.play(); heart_anim.play()
        log("play")

    def _pause(_):
        coin_anim.pause(); flash_anim.pause(); heart_anim.pause()
        log("pause")

    def _stop(_):
        coin_anim.stop(); flash_anim.stop(); heart_anim.stop()
        log("stop (reset to frame 0)")

    seek_slider = ft.Slider(
        min=0.0, max=float(len(idle_frames)-1), divisions=len(idle_frames)-1,
        value=0.0, label="{value}",
        on_change=lambda e: (
            idle_anim.seek(int(float(e.control.value))),
            lbl_idle.__setattr__("text", f"frame {int(float(e.control.value))}: {idle_frames[int(float(e.control.value))]}"),
            lbl_idle.update(),
        ),
        width=300,
    )

    fps_slider = ft.Slider(
        min=1.0, max=24.0, divisions=23, value=8.0, label="fps: {value}",
        on_change=lambda e: setattr(coin_anim, "fps", float(e.control.value)),
        width=300,
    )

    page.add(
        ft.Row([
            ft.TextButton("Play",  on_click=_play),
            ft.TextButton("Pause", on_click=_pause),
            ft.TextButton("Stop",  on_click=_stop),
        ], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([ft.Text("Coin FPS:"), fps_slider],
               alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([ft.Text("Seek:"), seek_slider],
               alignment=ft.MainAxisAlignment.CENTER),
        status,
    )
    page.update()
    loop.start()


ft.run(main)
