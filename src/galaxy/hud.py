from __future__ import annotations

from flet_game import Label

from .types import GameData


class HUD:
    def __init__(self) -> None:
        self.score_label = Label(
            x=12,
            y=8,
            text="0",
            size=22,
            color="#ffffff",
            bold=True,
            tag="hud_score",
        )
        self.level_label = Label(
            x=200,
            y=8,
            text="1",
            size=16,
            color="#90caf9",
            tag="hud_level",
        )
        self.lives_label = Label(
            x=320,
            y=8,
            text="3",
            size=18,
            color="#ff5252",
            tag="hud_lives",
        )
        self.combo_label = Label(
            x=12,
            y=34,
            text="",
            size=14,
            color="#ffd740",
            bold=True,
            tag="hud_combo",
            visible=False,
        )
        self.powerup_label = Label(
            x=200,
            y=34,
            text="",
            size=13,
            color="#69f0ae",
            tag="hud_powerup",
            visible=False,
        )

    def sync(self, game: GameData) -> None:
        self.score_label.text = f"{game.score:,}"
        self.level_label.text = f"Lv {game.level}"
        hearts = "\u2764 " * game.lives
        self.lives_label.text = hearts.strip()
        if game.combo > 0:
            self.combo_label.text = f"x{game.combo + 1}"
            self.combo_label.visible = True
        else:
            self.combo_label.visible = False
        if game.activePowerUp:
            names = {"spread": "SPREAD", "speed": "RAPID"}
            self.powerup_label.text = names.get(
                game.activePowerUp, game.activePowerUp.upper()
            )
            self.powerup_label.visible = True
        else:
            self.powerup_label.visible = False
