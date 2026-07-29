"""Dynamic sprite asset scanner for ``assets/sprites/``.

Discovers **any** sub-directories under ``assets/sprites/`` at runtime.
Each sub-directory is treated as a character or enemy type, and image
files inside are grouped by state (``idle``, ``walk``, ``attack``, etc.).

When a requested sprite is not found in the user's assets, the library
falls back to :mod:`flet_game.prefab` built-in sprites so the game
always has something to render.

Directory layout
----------------
::

    assets/sprites/
        hero/               ← any name works
            idle1.png
            idle2.png
            walk1.png
            walk2.png
        skeleton/
            idle1.png
            attack1.png
        coin/
            idle1.png

File names are sorted lexicographically; ``idle1.png`` comes before
``idle2.png``.  Any image format supported by Flet (PNG, JPG, GIF, WEBP)
is accepted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


@dataclass
class SpriteState:
    """A list of image paths for one animation state."""
    name: str
    frames: list[str] = field(default_factory=list)


@dataclass
class SpriteEntry:
    """A discovered sprite type with its animation states."""
    name: str
    directory: str
    states: dict[str, SpriteState] = field(default_factory=dict)

    @property
    def idle(self) -> Optional[str]:
        """First idle frame path, or ``None``."""
        s = self.states.get("idle")
        return s.frames[0] if s and s.frames else None

    @property
    def walk(self) -> list[str]:
        """Walk animation frames."""
        s = self.states.get("walk")
        return s.frames if s else []

    def state_frames(self, state: str) -> list[str]:
        """All frames for a given state."""
        s = self.states.get(state)
        return s.frames if s else []


class SpriteLibrary:
    """Discovers and manages sprite assets from ``assets/sprites/``.

    Parameters
    ----------
    assets_dir:
        Absolute path to the application's assets directory.
        If ``None``, the library scans ``<cwd>/assets/sprites/``.
    """

    def __init__(self, assets_dir: Optional[str] = None) -> None:
        self._assets_dir = assets_dir or os.path.join(os.getcwd(), "assets")
        self._sprites_dir = os.path.join(self._assets_dir, "sprites")
        self._entries: dict[str, SpriteEntry] = {}
        self._scan()

    @property
    def sprites_dir(self) -> str:
        return self._sprites_dir

    @property
    def entries(self) -> dict[str, SpriteEntry]:
        """All discovered sprite types, keyed by directory name."""
        return self._entries

    def _scan(self) -> None:
        """Walk ``assets/sprites/`` and build entry dicts."""
        if not os.path.isdir(self._sprites_dir):
            return

        for name in sorted(os.listdir(self._sprites_dir)):
            subdir = os.path.join(self._sprites_dir, name)
            if not os.path.isdir(subdir):
                continue
            entry = SpriteEntry(name=name, directory=subdir)

            # Scan immediate files for animation states
            for fname in sorted(os.listdir(subdir)):
                fpath = os.path.join(subdir, fname)
                if not os.path.isfile(fpath):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext not in IMAGE_EXTS:
                    continue

                stem = os.path.splitext(fname)[0]
                # Extract state name: "idle1" → "idle", "walk2" → "walk"
                state_name = _extract_state(stem)

                if state_name not in entry.states:
                    entry.states[state_name] = SpriteState(name=state_name)
                entry.states[state_name].frames.append(fpath)

            if entry.states:
                self._entries[name] = entry

    def rescan(self) -> None:
        """Re-scan the sprites directory (call after adding files at runtime)."""
        self._entries.clear()
        self._scan()

    def get(self, name: str) -> Optional[SpriteEntry]:
        """Look up a sprite type by directory name."""
        return self._entries.get(name)

    def get_idle_path(self, name: str) -> Optional[str]:
        """Return the first idle frame path for *name*, or ``None``."""
        e = self._entries.get(name)
        return e.idle if e else None

    def get_state_paths(self, name: str, state: str) -> list[str]:
        """Return all frame paths for a given state."""
        e = self._entries.get(name)
        return e.state_frames(state) if e else []

    def list_names(self) -> list[str]:
        """Return all discovered sprite type names."""
        return list(self._entries.keys())


def _extract_state(stem: str) -> str:
    """Derive the animation state from a file stem.

    ``"idle1"`` → ``"idle"``,  ``"walk2"`` → ``"walk"``,
    ``"attack"`` → ``"attack"``.
    """
    i = len(stem)
    while i > 0 and stem[i - 1].isdigit():
        i -= 1
    return stem[:i] if i > 0 else stem
