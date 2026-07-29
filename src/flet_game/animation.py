"""
animation.py — SpriteAnimation: frame-by-frame animation for Sprite objects.

``SpriteAnimation`` drives a :class:`~flet_game.Sprite` through a sequence of
frames (colours, image URLs, or arbitrary property dicts) at a configurable FPS.
It slots naturally into the flet_game update loop.

Usage — colour cycling::

    from flet_game import Sprite, GameLoop, SpriteAnimation

    coin = Sprite(x=100, y=100, width=32, height=32, color="yellow")

    anim = SpriteAnimation(
        coin,
        frames=["yellow", "gold", "orange", "gold"],
        fps=8,
        loop=True,
    )
    anim.register(loop)   # auto-update via the game loop
    anim.play()

Usage — sprite sheet (image list)::

    frames = [f"assets/player_run_{i}.png" for i in range(1, 9)]
    anim = SpriteAnimation(player, frames=frames, fps=12)
    anim.register(loop)
    anim.play()

Usage — mixed property dicts::

    frames = [
        {"color": "red",  "scale": 1.0},
        {"color": "red",  "scale": 1.2},
        {"color": "white","scale": 1.4},
        {"color": "red",  "scale": 1.2},
    ]
    anim = SpriteAnimation(player, frames, fps=10, loop=False,
                           on_complete=lambda: print("hit flash done"))

Frame format (each element of ``frames``)
------------------------------------------
* ``str`` — if it contains a path separator (``/``, ``\\``) or a file
  extension dot after a non-space char, treated as an **image URL**;
  otherwise treated as a **CSS colour name / hex string**.
* ``dict`` — any combination of ``color``, ``image``, ``scale``,
  ``opacity``, ``rotation``.  Applied to the Sprite each frame advance.
"""

from __future__ import annotations

from typing import Callable, Optional, Union


# ─── Frame type ────────────────────────────────────────────────────────────────

_Frame = Union[str, dict]


def _parse_frame(raw: _Frame) -> dict:
    """Normalise a raw frame entry into a property dict."""
    if isinstance(raw, dict):
        return raw
    # String: detect image vs colour.
    s = raw.strip()
    # Image if it has a path-like component or file extension.
    if "/" in s or "\\" in s or (
        "." in s.split("/")[-1].split("\\")[-1] and not s.startswith("#")
    ):
        return {"image": s}
    return {"color": s}


def _apply_frame(sprite, frame_dict: dict) -> None:
    """Apply a normalised frame dict to a Sprite."""
    if "color" in frame_dict:
        sprite.color = frame_dict["color"]
    if "image" in frame_dict:
        sprite.image = frame_dict["image"]
    if "scale" in frame_dict:
        sprite.scale = frame_dict["scale"]
    if "opacity" in frame_dict:
        sprite.opacity = frame_dict["opacity"]
    if "rotation" in frame_dict:
        sprite.rotation = frame_dict["rotation"]


def _safe_apply(sprite, frame_dict: dict) -> None:
    """Apply a frame dict, silently skipping if the sprite is not yet on the page.

    Sprite property setters call ``_update()`` which requires the control to be
    mounted.  When ``play()`` / ``stop()`` / ``seek()`` are called before
    ``scene.mount()``, we skip the immediate apply — the game loop will apply
    the correct frame on its first tick.
    """
    try:
        _apply_frame(sprite, frame_dict)
    except (RuntimeError, AttributeError):
        pass  # not yet on page — loop will apply on first update()


# ─── SpriteAnimation ──────────────────────────────────────────────────────────

class SpriteAnimation:
    """Frame-by-frame animator for a :class:`~flet_game.Sprite`.

    Parameters
    ----------
    sprite
        The target Sprite to animate.
    frames
        List of frames.  Each element can be:

        * a CSS colour string / hex string (e.g. ``"red"``, ``"#ff0000"``)
        * an image URL string (e.g. ``"assets/run_1.png"``)
        * a dict with any of ``color``, ``image``, ``scale``, ``opacity``,
          ``rotation`` keys
    fps
        Playback rate in frames per second.  Default 12.
    loop
        Whether to loop after the last frame.  Default ``True``.
    on_complete
        Optional callback called once when the animation reaches the last
        frame (only fires when ``loop=False``).
    """

    def __init__(
        self,
        sprite,
        frames: list[_Frame],
        fps: float = 12.0,
        loop: bool = True,
        on_complete: Optional[Callable] = None,
    ) -> None:
        if not frames:
            raise ValueError("SpriteAnimation requires at least one frame")
        self._sprite = sprite
        self._frames = [_parse_frame(f) for f in frames]
        self._fps = float(fps)
        self._loop = loop
        self._on_complete = on_complete
        self._idx = 0
        self._timer = 0.0
        self._playing = False
        self._loop_ref = None   # the game loop if registered
        self._cb_ref = None     # the callback fn registered with loop

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def current_frame(self) -> int:
        """Zero-based index of the frame currently displayed."""
        return self._idx

    @property
    def frame_count(self) -> int:
        """Total number of frames in this animation."""
        return len(self._frames)

    @property
    def fps(self) -> float:
        """Playback rate in frames per second."""
        return self._fps

    @fps.setter
    def fps(self, value: float) -> None:
        self._fps = float(value)

    @property
    def is_playing(self) -> bool:
        """True while the animation is advancing."""
        return self._playing

    @property
    def loop(self) -> bool:
        """Whether the animation loops."""
        return self._loop

    @loop.setter
    def loop(self, value: bool) -> None:
        self._loop = value

    # ── Playback control ──────────────────────────────────────────────────────

    def play(self) -> "SpriteAnimation":
        """Start or resume playback.  Applies the current frame immediately."""
        self._playing = True
        _safe_apply(self._sprite, self._frames[self._idx])
        return self

    def pause(self) -> "SpriteAnimation":
        """Pause playback without resetting the frame counter."""
        self._playing = False
        return self

    def stop(self) -> "SpriteAnimation":
        """Stop and reset to frame 0."""
        self._playing = False
        self._idx = 0
        self._timer = 0.0
        _safe_apply(self._sprite, self._frames[0])
        return self

    def reset(self) -> "SpriteAnimation":
        """Reset to frame 0 without changing playback state."""
        self._idx = 0
        self._timer = 0.0
        _safe_apply(self._sprite, self._frames[0])
        return self

    def seek(self, frame_index: int) -> "SpriteAnimation":
        """Jump to a specific frame and apply it immediately."""
        self._idx = frame_index % len(self._frames)
        self._timer = 0.0
        _safe_apply(self._sprite, self._frames[self._idx])
        return self

    # ── Loop integration ──────────────────────────────────────────────────────

    def register(self, loop) -> "SpriteAnimation":
        """Register with a :class:`~flet_game.GameLoop` for automatic updates.

        After calling this, the animation is updated every frame without any
        manual ``update(dt)`` call.

        .. code-block:: python

            anim.register(loop)
            anim.play()
        """
        if self._loop_ref is not None:
            self.unregister()
        self._loop_ref = loop
        self._cb_ref = self.update
        loop.add_callback(self._cb_ref)
        return self

    def unregister(self) -> "SpriteAnimation":
        """Remove from the game loop.  Safe to call even if not registered."""
        if self._loop_ref is not None and self._cb_ref is not None:
            try:
                self._loop_ref.remove_callback(self._cb_ref)
            except Exception:
                pass
        self._loop_ref = None
        self._cb_ref = None
        return self

    # ── Manual update (call from @loop.on_update if not using register) ───────

    def update(self, dt: float) -> None:
        """Advance the animation by *dt* seconds.

        Call this inside a ``@loop.on_update`` callback if you prefer
        explicit control, or use :meth:`register` for automatic updates.
        """
        if not self._playing or self._fps <= 0:
            return

        interval = 1.0 / self._fps
        self._timer += dt

        advanced = False
        while self._timer >= interval:
            self._timer -= interval
            self._idx += 1
            advanced = True

            if self._idx >= len(self._frames):
                if self._loop:
                    self._idx = 0
                else:
                    self._idx = len(self._frames) - 1
                    self._playing = False
                    _apply_frame(self._sprite, self._frames[self._idx])
                    if self._on_complete is not None:
                        self._on_complete()
                    return  # do not advance further

        if advanced:
            _apply_frame(self._sprite, self._frames[self._idx])

    def __repr__(self) -> str:
        state = "playing" if self._playing else "paused"
        return (
            f"SpriteAnimation(frame={self._idx}/{len(self._frames)-1}, "
            f"fps={self._fps}, {state})"
        )
