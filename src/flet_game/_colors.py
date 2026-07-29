"""
_colors.py — Shared colour resolution helper for flet_game.

Lets user-facing APIs accept CSS-friendly strings ("red", "blue_400",
"#FF6600") instead of requiring ft.Colors constants everywhere.
"""

from __future__ import annotations

from typing import Optional

import flet as ft


def _resolve_color(value: Optional[str]) -> Optional[str]:
    """
    Accept any of these colour formats and return what Flet expects:

      - None          → None
      - "#FF6600"     → "#FF6600"   (CSS hex — passed through unchanged)
      - "orange"      → ft.Colors.ORANGE
      - "blue_400"    → ft.Colors.BLUE_400   (underscore shade notation)
      - "deep-orange" → ft.Colors.DEEP_ORANGE  (hyphens also accepted)
      - ft.Colors.X   → ft.Colors.X   (already resolved — passed through)

    This lets gamer-coders write Sprite(color="red") instead of
    Sprite(color=ft.Colors.RED).
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value  # already an ft.Colors constant or other Flet type
    if value.startswith("#"):
        return value  # CSS hex — Flet handles these natively
    # Map friendly names ("orange", "blue_400", "deep-orange") → ft.Colors.*
    ft_key = value.upper().replace("-", "_").replace(" ", "_")
    return getattr(ft.Colors, ft_key, value)  # fall back to raw string
