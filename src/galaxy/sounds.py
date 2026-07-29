from __future__ import annotations

import flet as ft

from flet_game import BuiltinSounds, audio_available


class AudioController:
    def __init__(self, page: ft.Page) -> None:
        self._sfx: BuiltinSounds | None = None
        if not audio_available():
            return
        self._sfx = BuiltinSounds(page, pool_size=3)
        self._sfx.load_all()

    @property
    def available(self) -> bool:
        return self._sfx is not None

    def _play(self, name: str, volume: float) -> None:
        if self._sfx:
            self._sfx.play(name, volume)

    def play_shoot(self) -> None:
        self._play("shoot", 0.6)

    def play_hit(self) -> None:
        self._play("hit", 0.7)

    def play_explosion(self) -> None:
        self._play("destroy", 0.7)

    def play_pickup(self) -> None:
        self._play("select", 0.6)

    def play_death(self) -> None:
        self._play("death", 0.8)

    def play_victory(self) -> None:
        self._play("victory", 0.7)

    def play_defeat(self) -> None:
        self._play("defeat", 0.7)

    def destroy(self) -> None:
        if self._sfx:
            self._sfx.destroy()