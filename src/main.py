from __future__ import annotations

import flet as ft
import flet_audio as fta
from flet import Scale
from flet_game import Game

from galaxy import StartView

DESIGN_W = 400.0
DESIGN_H = 700.0


def _rescale(page: ft.Page, game: Game) -> None:
    if game.scene is None:
        return
    pw = max(page.width, 1.0)
    ph = max(page.height, 1.0)
    s = min(pw / DESIGN_W, ph / DESIGN_H)
    game.scene.root.scale = Scale(scale_x=s, scale_y=s)
    game.scene.root.update()


def main(page: ft.Page) -> None:
    page.title = "Galaxy Shooter"
    page.bgcolor = ft.Colors.BLACK
    page.padding = 0
    page.spacing = 0
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.window.width = 414
    page.window.height = 750

    test_audio = fta.Audio(
        src="https://www.soundjay.com/buttons/sounds/button-09a.mp3",
        autoplay=True,
        volume=1.0,
    )
    page.services.append(test_audio)
    page.update()

    game = Game(
        page,
        width=DESIGN_W,
        height=DESIGN_H,
        fps=60,
        title="Galaxy Shooter",
        bgcolor=ft.Colors.BLACK,
    )

    page.on_resized = lambda e: _rescale(page, game)

    game.run(StartView(game))
    _rescale(page, game)


ft.run(main)
