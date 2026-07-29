"""
leaderboard.py — Step 7: cross-platform leaderboard via ft.SharedPreferences.

Uses Flet's ``ft.SharedPreferences`` (Flutter shared_preferences plugin) so
scores persist on every platform without any path logic:

  Web     — localStorage
  Desktop — JSON file managed by Flutter
  iOS     — NSUserDefaults
  Android — SharedPreferences

Write operations are **async**; read operations (``top``, ``rank_of``) are
**sync** because they read from an in-memory cache loaded by ``await lb.load()``.

Usage::

    async def main(page: ft.Page) -> None:
        lb = Leaderboard(page)
        await lb.load()           # populate from storage once at startup

        entries = lb.top(5)       # sync — reads from in-memory cache
        rank    = lb.rank_of(42)  # sync

        await lb.add("Alice", 42) # async — updates memory + persists
        await lb.clear()          # async — removes our key from storage

    ft.run(main)

Note: ``ft.SharedPreferences`` is shared across all Flet apps for the same
user, so all keys are prefixed with ``"flet_game."`` to avoid collisions.
"""

from __future__ import annotations

import json
import time

import flet as ft

# Unique prefix avoids collision with other Flet apps' shared_preferences.
_STORAGE_KEY = "flet_game.leaderboard.v1"


class Leaderboard:
    """Cross-platform persistent leaderboard backed by ``ft.SharedPreferences``.

    Parameters
    ----------
    page:
        The Flet ``Page`` — needed to register the SharedPreferences service.
    max_entries:
        Maximum number of entries kept after each ``add()`` call.
    """

    def __init__(self, page: ft.Page, max_entries: int = 10) -> None:
        self._page = page
        self._max = max_entries
        self._entries: list[dict] = []
        self._sp = ft.SharedPreferences()
        page.services.append(self._sp)
        page.update()  # flush SharedPreferences service registration

    # ── Persistence ───────────────────────────────────────────────────────────

    async def load(self) -> None:
        """Populate the in-memory cache from ``shared_preferences``.

        Call once at app startup (``await lb.load()``) before reading entries.
        Safe to call again to refresh from storage.
        """
        try:
            raw = await self._sp.get(_STORAGE_KEY)
            if isinstance(raw, str):
                data = json.loads(raw)
                if isinstance(data, list):
                    self._entries = data
                    return
        except Exception:
            pass
        self._entries = []

    # ── Public API ────────────────────────────────────────────────────────────

    async def add(self, name: str, score: int) -> None:
        """Add an entry, re-sort by score descending, trim, then persist.

        Parameters
        ----------
        name:
            Player name (stripped; defaults to ``"Player"`` if blank).
        score:
            Integer score (higher = better).
        """
        name = (name or "Player").strip() or "Player"
        self._entries.append({
            "name":  name,
            "score": int(score),
            "ts":    int(time.time()),
        })
        self._entries.sort(key=lambda e: e["score"], reverse=True)
        self._entries = self._entries[: self._max]
        await self._sp.set(_STORAGE_KEY, json.dumps(self._entries))

    def top(self, n: int | None = None) -> list[dict]:
        """Return the top *n* entries from in-memory cache (sync).

        Each entry is a dict with keys ``"name"``, ``"score"``, ``"ts"``.
        The list is always sorted by score descending.
        Call ``await lb.load()`` first to ensure the cache is populated.
        """
        n = n if n is not None else self._max
        return list(self._entries[:n])

    async def clear(self) -> None:
        """Remove all entries from memory and from ``shared_preferences``."""
        self._entries = []
        await self._sp.remove(_STORAGE_KEY)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def rank_of(self, score: int) -> int:
        """Return the 1-based rank the given score would achieve (before insertion)."""
        rank = 1
        for e in self._entries:
            if e["score"] > score:
                rank += 1
        return rank

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"Leaderboard(entries={len(self._entries)})"
