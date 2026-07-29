"""
button.py -- Button: a tappable game-UI entity for flet_game.

A Button combines the background rectangle of a Sprite with the auto-centred
text of a Label into a single scene object. No more manual Sprite + Label
pairs with hand-tuned x/y offsets for every in-game button.

    # Before (the old way -- Tetris bottom bar incident):
    scene.add(Sprite(x=bx, y=by, width=90, height=58, color="#12122a",
                     border_radius=14, on_click=cb), z=30)
    scene.add(Label(x=bx + 33, y=by + 12, text="<", size=28,
                    color="#ffffff", bold=True), z=31)

    # After:
    scene.add(Button(x=bx, y=by, width=90, height=58, text="<",
                     text_size=28, color="#12122a", border_radius=14,
                     on_click=cb), z=30)

Like Sprite and Label, Button:
  - positions itself absolutely inside an ft.Stack via left/top
  - is added to a Scene with scene.add(button, z=N)
  - exposes .control for direct ft.Stack use
  - provides property setters that auto-call page.update() when live
  - respects the GameLoop batch-update protocol (silent during frames)
  - supports ink ripple, optional hover colour, fade / move animations
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from ._colors import _resolve_color

# Hoisted to module level: previously imported inside Button._update() on
# every property-setter call. See sprite.py for the same pattern.
try:
    from .loop import batch_active as _batch_active
except ImportError:
    _batch_active = None


class Button:
    """
    A tappable UI button entity for the game canvas.

    Text is always auto-centred inside the button rectangle -- no manual
    offset arithmetic needed.

    Parameters
    ----------
    x, y          : position in scene-canvas pixels (top-left corner)
    width, height : button size in pixels
    text          : label shown inside the button
    text_size     : font size (default 18)
    text_color    : font colour -- CSS name, '#hex', or ft.Colors.*
    bold          : bold font weight
    color         : background colour (default '#12122a')
    hover_color   : background colour while the pointer is over the button;
                    ``None`` keeps the same color but the ink ripple still
                    gives visual feedback
    border_radius : corner radius in pixels (default 8)
    opacity       : 0.0 (invisible) to 1.0 (fully opaque)
    visible       : whether the button is rendered
    on_click      : callback(e) fired when the button is tapped / clicked
    tag           : arbitrary string label for game logic
    """

    def __init__(
        self,
        x: float = 0,
        y: float = 0,
        width: float = 120,
        height: float = 44,
        text: str = "Button",
        text_size: float = 18,
        text_color: Optional[str] = "white",
        bold: bool = False,
        color: Optional[str] = "#12122a",
        hover_color: Optional[str] = None,
        border_radius: float = 8,
        opacity: float = 1.0,
        visible: bool = True,
        on_click: Optional[Callable] = None,
        tag: str = "",
    ) -> None:
        self._tag = tag
        self._color = _resolve_color(color)
        self._hover_color = _resolve_color(hover_color) if hover_color else None

        self._text_ctrl = ft.Text(
            value=text,
            size=text_size,
            color=_resolve_color(text_color),
            weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
            no_wrap=True,
        )

        # Single ft.Container: left/top positions it in the Stack;
        # alignment=CENTER auto-centres the text child; ink=True gives
        # Material ripple feedback on tap without any extra work.
        self._control = ft.Container(
            left=x,
            top=y,
            width=width,
            height=height,
            bgcolor=self._color,
            border_radius=(
                ft.BorderRadius.all(border_radius) if border_radius else None
            ),
            opacity=opacity,
            visible=visible,
            on_click=on_click,
            on_hover=self._handle_hover if self._hover_color else None,
            ink=True,                      # Material splash on tap
            content=self._text_ctrl,
            alignment=ft.Alignment.CENTER, # text always centred -- no maths needed
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_hover(self, e) -> None:
        """Toggle between normal and hover background colour."""
        self._control.bgcolor = (
            self._hover_color if e.data == "true" else self._color
        )
        self._update()

    def _update(self) -> None:
        """Trigger a Flet UI refresh -- silent during GameLoop frames."""
        # Flet 0.86+ raises RuntimeError (not returns None) when .page is
        # accessed on an unmounted control, so guard with try/except.
        try:
            if not self._control.page:
                return
        except RuntimeError:
            return
        if _batch_active is not None and _batch_active():
            return
        self._control.update()

    # ------------------------------------------------------------------
    # Raw Flet access
    # ------------------------------------------------------------------

    @property
    def control(self) -> ft.Container:
        """The underlying ft.Container -- append to ft.Stack or use scene.add()."""
        return self._control

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def tag(self) -> str:
        return self._tag

    # ------------------------------------------------------------------
    # Position
    # ------------------------------------------------------------------

    @property
    def x(self) -> float:
        return self._control.left or 0.0

    @x.setter
    def x(self, value: float) -> None:
        self._control.animate_position = None
        self._control.left = value
        self._update()

    @property
    def y(self) -> float:
        return self._control.top or 0.0

    @y.setter
    def y(self, value: float) -> None:
        self._control.animate_position = None
        self._control.top = value
        self._update()

    def move_to(
        self,
        x: float,
        y: float,
        duration: int = 0,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
        on_end: Optional[Callable] = None,
    ) -> None:
        """Move the button to (x, y), optionally animated."""
        if duration > 0:
            self._control.animate_position = ft.Animation(duration, curve)
            if on_end:
                self._control.on_animation_end = on_end
        else:
            self._control.animate_position = None
        self._control.left = x
        self._control.top = y
        self._update()

    # ------------------------------------------------------------------
    # Text
    # ------------------------------------------------------------------

    @property
    def text(self) -> str:
        return self._text_ctrl.value

    @text.setter
    def text(self, value: str) -> None:
        self._text_ctrl.value = value
        self._update()

    @property
    def text_color(self) -> str | None:
        return self._text_ctrl.color

    @text_color.setter
    def text_color(self, value: str | None) -> None:
        self._text_ctrl.color = _resolve_color(value)
        self._update()

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------

    @property
    def color(self) -> str | None:
        return self._color

    @color.setter
    def color(self, value: str | None) -> None:
        self._color = _resolve_color(value)
        self._control.bgcolor = self._color
        self._update()

    @property
    def visible(self) -> bool:
        return self._control.visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._control.visible = value
        self._update()

    @property
    def opacity(self) -> float:
        return self._control.opacity or 1.0

    @opacity.setter
    def opacity(self, value: float) -> None:
        self._control.animate_opacity = None
        self._control.opacity = max(0.0, min(1.0, value))
        self._update()

    def fade_to(
        self,
        opacity: float,
        duration: int = 300,
        curve: ft.AnimationCurve = ft.AnimationCurve.EASE_IN_OUT,
    ) -> None:
        """Animate opacity from current value to `opacity` (0.0-1.0)."""
        self._control.animate_opacity = ft.Animation(duration, curve)
        self._control.opacity = max(0.0, min(1.0, opacity))
        self._update()

    def show(self) -> None:
        """Make this button visible."""
        self.visible = True

    def hide(self) -> None:
        """Make this button invisible."""
        self.visible = False

    def __repr__(self) -> str:
        return (
            f"Button(tag={self._tag!r}, x={self.x}, y={self.y}, "
            f"text={self.text!r})"
        )
