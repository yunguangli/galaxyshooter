from __future__ import annotations

import math
import random

import flet as ft
from flet_game import SplashEffect

STAR_COUNT = 30
STAR_COLORS = (
    "#ffffff",
    "#90caf9",
    "#ce93d8",
    "#fff9c4",
)


class Star:
    def __init__(self, width: float, height: float) -> None:
        self.x = random.uniform(0, width)
        self.y = random.uniform(0, height)
        self.speed = random.uniform(30, 120)
        self.size = random.uniform(1.0, 2.5)
        self.color = random.choice(STAR_COLORS)
        self.opacity = random.uniform(0.3, 1.0)
        self._w = width
        self._h = height
        self._container: ft.Container | None = None

    def build(self) -> ft.Container:
        self._container = ft.Container(
            left=self.x,
            top=self.y,
            width=self.size,
            height=self.size,
            bgcolor=self.color,
            opacity=self.opacity,
            border_radius=ft.BorderRadius.all(self.size / 2)
            if self.size > 1.5
            else None,
            animate_opacity=ft.Animation(duration=1200),
        )
        return self._container

    def update(self, dt: float) -> None:
        self.y += self.speed * dt
        if self.y > self._h:
            self.y = -self.size
            self.x = random.uniform(0, self._w)
        if self._container:
            self._container.top = self.y
            self._container.left = self.x


class Starfield:
    def __init__(self, width: float, height: float) -> None:
        self._width = width
        self._height = height
        self.stars: list[Star] = [Star(width, height) for _ in range(STAR_COUNT)]
        self._containers: list[ft.Container] = []

    def build_all(self) -> list[ft.Container]:
        self._containers = [s.build() for s in self.stars]
        return self._containers

    def update(self, dt: float) -> None:
        for s in self.stars:
            s.update(dt)


class Effects:
    def __init__(self, page: ft.Page, canvas: ft.Stack) -> None:
        self._fx = SplashEffect(page, canvas)

    def explosion(self, x: float, y: float) -> None:
        self._fx.burst(
            x, y, color="#ff6d00", count=10, distance=40, size=6, duration=350
        )
        self._fx.burst(
            x, y, color="#ffab00", count=6, distance=28, size=4, duration=300
        )
        self._fx.ring(x, y, color="#ffffff", radius=20, thickness=2, duration=250)

    def small_explosion(self, x: float, y: float) -> None:
        self._fx.burst(
            x, y, color="#ff9100", count=6, distance=24, size=4, duration=300
        )
        self._fx.ring(x, y, color="#ffffff", radius=14, thickness=2, duration=200)

    def big_explosion(self, x: float, y: float) -> None:
        self._fx.burst(
            x, y, color="#ff3d00", count=16, distance=56, size=8, duration=500
        )
        self._fx.burst(
            x, y, color="#ff9100", count=10, distance=36, size=5, duration=400
        )
        self._fx.ring(x, y, color="#ffffff", radius=30, thickness=3, duration=300)

    def pickup(self, x: float, y: float, color: str = "#ffd740") -> None:
        self._fx.burst(x, y, color=color, count=8, distance=28, size=4, duration=350)
        self._fx.ring(x, y, color="#ffffff", radius=16, thickness=2, duration=250)

    def hit_flash(self, x: float, y: float) -> None:
        self._fx.ring(x, y, color="#ffffff", radius=24, thickness=3, duration=150)

    def trail(self, x: float, y: float) -> None:
        self._fx.burst(
            x, y, color="#ff6d00", count=3, distance=14, size=3, duration=280
        )
        self._fx.burst(
            x, y, color="#ffab00", count=2, distance=10, size=2, duration=220
        )
