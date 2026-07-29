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
        self._active_count = 0
        self._max_concurrent = 8  # Reduced from 16 to prevent UI thread flooding

    def _safe_call(self, method, *args, **kwargs) -> None:
        """Safely call SplashEffect method, limiting concurrent effects."""
        if self._active_count >= self._max_concurrent:
            return
        self._active_count += 1
        try:
            method(*args, **kwargs)
        finally:
            self._active_count -= 1

    def explosion(self, x: float, y: float) -> None:
        self._safe_call(
            self._fx.burst, x, y, color="#ff6d00", count=8, distance=36, size=5, duration=300
        )
        self._safe_call(
            self._fx.burst, x, y, color="#ffab00", count=4, distance=24, size=3, duration=250
        )
        self._safe_call(
            self._fx.ring, x, y, color="#ffffff", radius=18, thickness=2, duration=200
        )

    def small_explosion(self, x: float, y: float) -> None:
        self._safe_call(
            self._fx.burst, x, y, color="#ff9100", count=5, distance=20, size=3, duration=250
        )
        self._safe_call(
            self._fx.ring, x, y, color="#ffffff", radius=12, thickness=2, duration=180
        )

    def big_explosion(self, x: float, y: float) -> None:
        self._safe_call(
            self._fx.burst, x, y, color="#ff3d00", count=12, distance=48, size=7, duration=450
        )
        self._safe_call(
            self._fx.burst, x, y, color="#ff9100", count=8, distance=32, size=4, duration=350
        )
        self._safe_call(
            self._fx.ring, x, y, color="#ffffff", radius=26, thickness=3, duration=280
        )

    def pickup(self, x: float, y: float, color: str = "#ffd740") -> None:
        self._safe_call(
            self._fx.burst, x, y, color=color, count=6, distance=24, size=3, duration=300
        )
        self._safe_call(
            self._fx.ring, x, y, color="#ffffff", radius=14, thickness=2, duration=220
        )

    def hit_flash(self, x: float, y: float) -> None:
        self._safe_call(
            self._fx.ring, x, y, color="#ffffff", radius=20, thickness=3, duration=120
        )

    def trail(self, x: float, y: float) -> None:
        # Reduced particle count for better performance
        self._safe_call(
            self._fx.burst, x, y, color="#ff6d00", count=2, distance=10, size=2, duration=200
        )
        self._safe_call(
            self._fx.burst, x, y, color="#ffab00", count=1, distance=8, size=2, duration=180
        )

    def muzzle_flash(self, x: float, y: float, power_level: int) -> None:
        """Dramatic muzzle flash at the player's gun barrel.

        Intensity scales with power_level:
          1 — small flash
          2 — medium flash with sparks
          3 — large flash with ring and spark shower
        """
        if power_level == 1:
            self._safe_call(
                self._fx.burst, x, y, color="#ffffff", count=3, distance=8, size=2, duration=120
            )
        elif power_level == 2:
            self._safe_call(
                self._fx.burst, x, y, color="#ffffff", count=5, distance=12, size=3, duration=150
            )
            self._safe_call(
                self._fx.burst, x, y, color="#00e5ff", count=2, distance=15, size=2, duration=180
            )
            self._safe_call(
                self._fx.ring, x, y, color="#00e5ff", radius=8, thickness=2, duration=180
            )
        else:  # power_level == 3
            self._safe_call(
                self._fx.burst, x, y, color="#ffffff", count=8, distance=18, size=4, duration=200
            )
            self._safe_call(
                self._fx.burst, x, y, color="#00e5ff", count=4, distance=24, size=2, duration=220
            )
            self._safe_call(
                self._fx.burst, x, y, color="#ffd740", count=3, distance=16, size=3, duration=180
            )
            self._safe_call(
                self._fx.ring, x, y, color="#00e5ff", radius=14, thickness=3, duration=220
            )
            self._safe_call(
                self._fx.ring, x, y, color="#ffd740", radius=8, thickness=2, duration=160
            )
