"""
savedata.py — SaveData: simple JSON-backed persistent key-value store.

Games need to save high scores, settings, progress, and unlocks.
``SaveData`` stores any JSON-serialisable values in a single file on disk,
auto-creating the directory if needed.

Usage::

    from flet_game import SaveData

    save = SaveData("mygame")        # loads existing data automatically
    save.set("high_score", 1234)
    save.set("volume", 0.8)
    save.save()                      # flush to disk

    # Next session:
    save = SaveData("mygame")
    score = save.get("high_score", default=0)   # → 1234

File location
-------------
* **Windows** — ``%APPDATA%\\flet_game\\<name>.json``
* **macOS / Linux** — ``~/.local/share/flet_game/<name>.json``

Override with the ``path`` parameter for a custom location::

    save = SaveData("levels", path="data/levels.json")

Thread / async safety
---------------------
All operations are synchronous and not thread-safe.  For Flet apps, call
:meth:`save` from the main asyncio task (event handlers and ``@loop.on_update``
callbacks run in the main asyncio loop, so no locking is needed in typical
usage).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator


class SaveData:
    """JSON-backed persistent key-value store.

    Parameters
    ----------
    name
        Logical name for this save file (no extension, no path).
        Different games should use different names.
    path
        Override the automatic platform path and use a specific file path.
        If omitted, data is stored in the platform's standard app-data folder.
    auto_save
        When ``True`` (default ``False``), call :meth:`save` automatically
        after every :meth:`set` and :meth:`delete`.  Convenient for small
        data; avoid for high-frequency writes (e.g., per-frame counters).
    """

    def __init__(
        self,
        name: str = "game",
        path: str | None = None,
        auto_save: bool = False,
    ) -> None:
        self._name = name
        self._auto_save = auto_save
        self._path = Path(path) if path else self._default_path(name)
        self._data: dict[str, Any] = {}
        self.load()

    # ── File path ─────────────────────────────────────────────────────────────

    @staticmethod
    def _default_path(name: str) -> Path:
        """Return the platform-appropriate save file path."""
        # Windows: %APPDATA%\flet_game\
        # macOS / Linux: ~/.local/share/flet_game/
        base = (
            os.environ.get("APPDATA")
            or os.path.join(os.path.expanduser("~"), ".local", "share")
        )
        return Path(base) / "flet_game" / f"{name}.json"

    @property
    def path(self) -> Path:
        """Absolute path to the backing JSON file."""
        return self._path

    @property
    def name(self) -> str:
        """Logical name of this save data."""
        return self._name

    # ── Persistence ───────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Read data from disk.

        Called automatically in :meth:`__init__`.  Returns ``True`` if the
        file existed and was parsed successfully; ``False`` otherwise (a fresh
        file will be created on the next :meth:`save` call).
        """
        try:
            text = self._path.read_text(encoding="utf-8")
            self._data = json.loads(text)
            if not isinstance(self._data, dict):
                self._data = {}
            return True
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._data = {}
            return False

    def save(self) -> None:
        """Write current data to disk.

        Creates the parent directory if it does not exist.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete_file(self) -> bool:
        """Delete the backing JSON file from disk.

        Returns ``True`` if the file was deleted, ``False`` if it didn't exist.
        """
        try:
            self._path.unlink()
            return True
        except FileNotFoundError:
            return False

    # ── Key-value API ─────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value stored under *key*, or *default* if absent."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key*.

        *value* must be JSON-serialisable (str, int, float, bool, None,
        list, dict — standard Python types).
        """
        self._data[key] = value
        if self._auto_save:
            self.save()

    def delete(self, key: str) -> bool:
        """Remove *key* from the store.

        Returns ``True`` if the key existed, ``False`` otherwise.
        """
        existed = key in self._data
        self._data.pop(key, None)
        if self._auto_save and existed:
            self.save()
        return existed

    def clear(self) -> None:
        """Remove all keys from the in-memory store.

        Call :meth:`save` afterwards to persist the cleared state.
        """
        self._data.clear()
        if self._auto_save:
            self.save()

    # ── Convenience ───────────────────────────────────────────────────────────

    def increment(self, key: str, amount: int | float = 1, default: int | float = 0) -> int | float:
        """Add *amount* to the numeric value at *key* and return the new value.

        If *key* is absent, starts from *default*.

        .. code-block:: python

            save.increment("plays")          # plays += 1
            save.increment("coins", 10)      # coins += 10
        """
        new_val = self._data.get(key, default) + amount
        self._data[key] = new_val
        if self._auto_save:
            self.save()
        return new_val

    def update_high_score(self, key: str, score: int | float) -> bool:
        """Store *score* under *key* only if it is higher than the current value.

        Returns ``True`` if *score* was a new high score, ``False`` otherwise.
        """
        current = self._data.get(key, None)
        if current is None or score > current:
            self._data[key] = score
            if self._auto_save:
                self.save()
            return True
        return False

    def keys(self) -> list[str]:
        """Return a list of all stored keys."""
        return list(self._data.keys())

    def all(self) -> dict[str, Any]:
        """Return a shallow copy of the entire data dict."""
        return dict(self._data)

    # ── Dict-style access ─────────────────────────────────────────────────────

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        self.delete(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"SaveData({self._name!r}, keys={list(self._data.keys())})"
