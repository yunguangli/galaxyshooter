"""
game.py — Game: top-level application shell for flet_game.

``Game`` owns a :class:`~flet_game.GameLoop` and a *scene stack*, making it
the highest-level API in the library.  It combines the boilerplate that would
normally live in ``main()``:

* Window sizing and title.
* A single ``GameLoop`` shared by all scenes.
* Scene lifecycle (mount / unmount / push / pop).

Scene stack
-----------
The stack lets you layer scenes without destroying lower ones:

    ┌──────────────────────────────────────────────────────┐
    │  PauseMenuScene   ← top — mounted, input active      │
    │  GameScene        ← suspended — off-screen, alive    │
    └──────────────────────────────────────────────────────┘

Three navigation operations:

* ``run_scene(scene)``  — clear the stack; show *scene*.  Use for major
  transitions: title → gameplay → game-over.
* ``push_scene(scene)`` — suspend current; show *scene* on top.  Use for
  overlays such as pause menus.  Pair with ``game.loop.pause()`` to freeze
  gameplay.
* ``pop_scene()``       — destroy top; restore previous.  Pair with
  ``game.loop.resume()`` to resume gameplay.

Recommended subclass pattern::

    class TitleScene(Scene):
        def __init__(self, game: Game) -> None:
            super().__init__(game.page, game.width, game.height, "#0a0a1a")
            self._game = game

        def on_enter(self) -> None:
            title = Label(text="My Game", x=200, y=200, size=48, color="white")
            self.add(title, z=10)

            @self.input.on_key_down("space")
            def start(e=None) -> None:
                self._game.run_scene(GameScene(self._game))

    def main(page: ft.Page) -> None:
        game = Game(page, width=800, height=600, title="My Game")
        game.run(TitleScene(game))

    ft.run(main)

``@game.on_update`` registers frame callbacks on the internal loop.  If you
add callbacks per-scene (via ``game.loop.add_callback(fn)`` in ``on_enter``
and ``game.loop.remove_callback(fn)`` in ``on_exit``), callbacks are
automatically scoped to the active scene's lifetime.
"""

from __future__ import annotations

import flet as ft

from .scene import Scene
from .loop import GameLoop
from .input import InputManager


class Game:
    """Top-level application shell combining a :class:`~flet_game.GameLoop`
    and a scene stack.

    Parameters
    ----------
    page
        The Flet ``Page``.
    width, height
        Canvas size in pixels.  Also used to pre-size the window.
    fps
        Target frames per second for the internal ``GameLoop``.
    title
        Window title (sets ``page.title``).
    bgcolor
        Page background colour shown around the canvas.
    resizable
        Whether the window can be resized by the user.
    """

    def __init__(
        self,
        page: ft.Page,
        width: float = 800,
        height: float = 600,
        fps: int = 60,
        title: str = "flet_game",
        bgcolor: str = ft.Colors.BLACK,
        resizable: bool = False,
    ) -> None:
        self._page = page
        self._width = float(width)
        self._height = float(height)

        page.title = title
        page.bgcolor = bgcolor
        # Centre the fixed-size canvas in the page on both axes so the UI is
        # centred on phones/tablets whose screens differ from width x height.
        # (Scene._wrapped is fixed to the canvas width so CENTER aligns the
        # Stack itself; without these the canvas hugs the top-left corner.)
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.vertical_alignment = ft.MainAxisAlignment.CENTER
        page.window.width = self._width + 20
        page.window.height = self._height + 80
        page.window.resizable = resizable

        self._loop = GameLoop(page, fps=fps)

        # Scene stack — the active scene is always _stack[-1].
        # Scenes below the top are paused (off-screen, not destroyed).
        self._stack: list[Scene] = []

    # ── Scene navigation ──────────────────────────────────────────────────────

    @property
    def scene(self) -> Scene | None:
        """The currently active (mounted) scene, or ``None``."""
        return self._stack[-1] if self._stack else None

    def run_scene(self, scene: Scene) -> None:
        """Clear the stack and make *scene* the only active scene.

        All current scenes are fully destroyed (``on_exit`` is called).
        Use for major transitions such as title → gameplay → game-over.
        """
        self._clear_stack()
        self._stack.append(scene)
        scene._set_loop(self._loop)  # connect loop so @scene.on_update works
        scene.mount()

    def push_scene(self, scene: Scene) -> None:
        """Push *scene* on top of the stack; suspend the current scene.

        The current scene is removed from the page and its keyboard handler
        silenced, but its objects and state remain intact in memory.  Use for
        overlays such as pause menus.

        Tip — freeze gameplay while the overlay is up::

            game.push_scene(PauseScene(game))
            game.loop.pause()
        """
        if self._stack:
            self._stack[-1]._pause()
        self._stack.append(scene)
        scene._set_loop(self._loop)  # connect loop so @scene.on_update works
        scene.mount()

    def pop_scene(self) -> Scene | None:
        """Destroy the top scene and restore the one below it.

        Returns the destroyed scene, or ``None`` if the stack was empty.

        Tip — resume gameplay after the overlay is dismissed::

            game.pop_scene()
            game.loop.resume()
        """
        if not self._stack:
            return None
        top = self._stack.pop()
        top._destroy()
        if self._stack:
            self._stack[-1]._resume()
        return top

    # ── GameLoop delegation ───────────────────────────────────────────────────

    @property
    def loop(self) -> GameLoop:
        """The internal :class:`~flet_game.GameLoop`."""
        return self._loop

    @property
    def on_update(self):
        """Decorator — register a permanent frame callback on the internal loop.

        For callbacks that should live only as long as one scene, prefer
        ``@scene.on_update`` inside ``on_enter()`` — those are auto-removed
        when the scene unmounts.

        Identical to ``@game.loop.on_update`` but available from the game
        object directly::

            @game.on_update
            def update(dt: float) -> None:
                player.x += speed * dt
        """
        return self._loop.on_update

    def start(self) -> None:
        """Start the game loop."""
        self._loop.start()

    def stop(self) -> None:
        """Stop the game loop permanently (restartable via :meth:`start`)."""
        self._loop.stop()

    def pause(self) -> None:
        """Pause the game loop (frame callbacks suspended, task kept alive)."""
        self._loop.pause()

    def resume(self) -> None:
        """Resume a paused game loop."""
        self._loop.resume()

    def run(self, scene: Scene | None = None) -> None:
        """Mount *scene* and start the game loop.

        If *scene* is ``None``, the loop starts with whatever scene is
        currently active (useful when scenes start the loop themselves via
        ``game.loop.start()`` in ``on_enter``).
        """
        if scene is not None:
            self.run_scene(scene)
        self._loop.start()

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def page(self) -> ft.Page:
        """The Flet ``Page``."""
        return self._page

    @property
    def input(self) -> InputManager | None:
        """The active scene's :class:`~flet_game.InputManager`, or ``None``."""
        s = self.scene
        return s.input if s else None

    @property
    def width(self) -> float:
        return self._width

    @property
    def height(self) -> float:
        return self._height

    @property
    def fps(self) -> int:
        return self._loop._target_fps

    @property
    def is_running(self) -> bool:
        """``True`` while the loop is alive and not paused."""
        return self._loop.is_running

    @property
    def is_paused(self) -> bool:
        """``True`` while the loop task is alive but paused."""
        return self._loop.is_paused

    # ── Internal ──────────────────────────────────────────────────────────────

    def _clear_stack(self) -> None:
        """Fully destroy every scene in the stack (top-down)."""
        for s in reversed(self._stack):
            s._destroy()
        self._stack.clear()

    def __repr__(self) -> str:
        scene_name = type(self.scene).__name__ if self.scene else "None"
        return (
            f"Game(w={self._width}, h={self._height}, fps={self.fps}, "
            f"scene={scene_name}, stack_depth={len(self._stack)})"
        )
