"""
audio.py — SoundManager: easy sound-effect playback for flet_game.

Requires the ``flet-audio`` package (installed separately)::

    pip install flet-audio

``SoundManager`` wraps ``flet_audio.Audio`` with four game-friendly
improvements:

1. **Named sounds** — load once, play by name.
2. **Polyphonic pool** — each sound gets N backing Audio instances so
   rapid-fire sounds don't cut each other off.
3. **Fire-and-forget** — :meth:`play` is a plain (sync) method; it
   dispatches the async ``audio.play()`` via ``page.run_task`` so you
   can call it safely from any callback or game-loop update.
4. **Asset-aware** — pass an ``assets_dir`` at construction and use
   :meth:`load_asset` to compose paths relative to your assets folder.

Usage::

    from flet_game import SoundManager

    # Sounds from the Flet assets folder (src/assets/ when using flet run)
    snd = SoundManager(page, assets_dir="sounds")
    snd.load_asset("hit",    "hit.wav")        # → src/assets/sounds/hit.wav
    snd.load_asset("music",  "bgm.mp3", pool_size=1)

    # Or load with any explicit source:
    snd.load("shoot", "sounds/shoot.wav")      # asset-relative path
    snd.load("boom",  "https://cdn.example.com/boom.mp3")  # URL
    snd.load("beep",  raw_wav_bytes)           # raw bytes (programmatic)

    snd.play("hit")
    snd.play("shoot", volume=0.6)

    snd.volume  = 0.8     # global volume (0.0–1.0)
    snd.enabled = False   # mute all
    snd.destroy()         # call before page closes
"""

from __future__ import annotations

import os
from typing import Optional

import flet as ft

from .audio_utils import make_beep, make_melody

try:
    import flet_audio as fta
    _AUDIO_AVAILABLE = True
except ImportError:
    fta = None  # type: ignore[assignment]
    _AUDIO_AVAILABLE = False


def audio_available() -> bool:
    """Return True if ``flet-audio`` is installed."""
    return _AUDIO_AVAILABLE


class SoundManager:
    """
    Named, polyphonic sound-effect player for flet_game.

    Parameters
    ----------
    page
        The Flet ``Page``.  Audio services are registered here.
    pool_size
        Default number of simultaneous instances per sound.  Increase for
        sounds that can overlap rapidly (e.g. rapid-fire bullet SFX).
    assets_dir
        Optional subdirectory inside your Flet assets folder used by
        :meth:`load_asset`.  Example: ``assets_dir="sounds"`` makes
        ``load_asset("hit", "hit.wav")`` resolve to ``sounds/hit.wav``
        relative to the Flet assets root.  Defaults to ``""`` (assets root).

    Raises
    ------
    ImportError
        If ``flet-audio`` is not installed.
    """

    def __init__(
        self,
        page: ft.Page,
        pool_size: int = 3,
        assets_dir: str = "",
    ) -> None:
        if not _AUDIO_AVAILABLE:
            raise ImportError(
                "flet-audio is not installed.\n"
                "Install it with:  pip install flet-audio"
            )
        self._page = page
        self._default_pool = pool_size
        self._assets_dir = assets_dir
        self._volume = 1.0
        self._enabled = True
        self._broken = False
        self._pools: dict[str, list] = {}
        self._pool_idx: dict[str, int] = {}

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(
        self,
        name: str,
        src: str | bytes,
        pool_size: Optional[int] = None,
    ) -> None:
        """Register a sound effect under *name*.

        Parameters
        ----------
        name
            Key used in :meth:`play`.
        src
            Audio source — one of:

            * **Asset-relative path** ``"sounds/hit.wav"`` — resolved by the
              Flet runtime relative to your ``assets_dir`` (``src/assets/``
              when using ``flet run``).  This is the standard way to ship
              audio files with a real game.
            * **Absolute file path** ``"/home/user/sounds/hit.wav"``
            * **URL** ``"https://cdn.example.com/hit.mp3"``
            * **Raw bytes** — a complete WAV/MP3 file as a Python
              ``bytes`` object (handy for programmatic beeps in demos).

            See supported formats:
            https://github.com/bluefireteam/audioplayers/blob/main/troubleshooting.md
        pool_size
            Number of simultaneous instances for this sound.  Defaults to the
            value passed to ``SoundManager(pool_size=...)``.
        """
        n = pool_size if pool_size is not None else self._default_pool
        pool = []
        for _ in range(n):
            a = fta.Audio(
                src=src,
                volume=self._volume,
                release_mode=fta.ReleaseMode.STOP,
            )
            try:
                self._page.services.append(a)
            except Exception:
                self._broken = True
                return
            pool.append(a)
        self._pools[name] = pool
        self._pool_idx[name] = 0
        self._page.update()

    # ── Asset-aware loading ───────────────────────────────────────────────────

    def load_asset(
        self,
        name: str,
        filename: str,
        pool_size: Optional[int] = None,
    ) -> None:
        """Load a sound from the Flet assets folder.

        Joins ``assets_dir`` (set at construction) with *filename* using
        ``os.path.join`` and forwards to :meth:`load`.  The resulting path is
        relative to the Flet assets root, e.g. ``src/assets/`` when running
        with ``flet run``.

        Example::

            # SoundManager(page, assets_dir="sounds")
            snd.load_asset("hit", "hit.wav")      # → "sounds/hit.wav"
            snd.load_asset("bgm", "bgm/loop.mp3") # → "sounds/bgm/loop.mp3"

            # SoundManager(page)  (no assets_dir)
            snd.load_asset("hit", "sounds/hit.wav") # → "sounds/hit.wav"
        """
        path = os.path.join(self._assets_dir, filename) if self._assets_dir else filename
        # Normalise separators to forward-slash for Flet's asset resolver
        path = path.replace("\\", "/")
        self.load(name, path, pool_size)

    # ── Playback ──────────────────────────────────────────────────────────────

    def play(self, name: str, volume: Optional[float] = None) -> None:
        """Fire-and-forget play. Safe to call from sync *or* async context.

        Silently does nothing if *name* was never loaded, or if
        :attr:`enabled` is ``False``.

        Parameters
        ----------
        name
            Sound key (must have been registered with :meth:`load`).
        volume
            Per-call volume override (0.0–1.0).  ``None`` uses the
            instance's :attr:`volume`.
        """
        if not self._enabled or self._broken or name not in self._pools:
            return
        pool = self._pools[name]
        idx = self._pool_idx[name]
        audio = pool[idx]
        self._pool_idx[name] = (idx + 1) % len(pool)
        if volume is not None:
            audio.volume = max(0.0, min(1.0, float(volume)))
        # audio.play() is a coroutine — dispatch via page.run_task with
        # exception guard so TimeoutError doesn't crash the loop.
        async def _play():
            try:
                await audio.play()
            except Exception:
                self._broken = True
        self._page.run_task(_play)

    # ── Volume / enabled ──────────────────────────────────────────────────────

    @property
    def volume(self) -> float:
        """Global volume: 0.0 (silent) → 1.0 (full). Default ``1.0``."""
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, float(value)))
        for pool in self._pools.values():
            for a in pool:
                a.volume = self._volume
        self._page.update()  # flush volume change to Flutter audio players

    @property
    def enabled(self) -> bool:
        """If ``False``, :meth:`play` is a no-op (effectively muted)."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def muted(self) -> bool:
        """``True`` when all playback is suppressed.

        Friendlier alias for ``not enabled`` — toggle with::

            snd.muted = True   # silence everything
            snd.muted = False  # restore playback
        """
        return not self._enabled

    @muted.setter
    def muted(self, value: bool) -> None:
        self._enabled = not bool(value)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def destroy(self) -> None:
        """Remove all Audio services from the page.

        Call this before closing the window to release audio resources.
        """
        for pool in self._pools.values():
            for a in pool:
                try:
                    self._page.services.remove(a)
                except ValueError:
                    pass
        self._pools.clear()
        self._pool_idx.clear()

    def __repr__(self) -> str:
        return (
            f"SoundManager(sounds={list(self._pools)!r}, "
            f"volume={self._volume}, enabled={self._enabled})"
        )


class BuiltinSounds:
    """Pre-built beep-based sound effects — no asset files required.

    Loads common game sounds (hit, shoot, build, destroy, death, select,
    train, move, error) using programmatic waveforms so your game has
    instant audio without any external files.

    Usage::

        from flet_game import SoundManager, BuiltinSounds

        snd = SoundManager(page, pool_size=4)
        sfx = BuiltinSounds(snd)
        sfx.load_all()

        sfx.play("hit")
        sfx.play("victory")
        sfx.volume = 0.6

    Or create one with an auto-managed internal SoundManager::

        sfx = BuiltinSounds(page, pool_size=4)
        sfx.load_all()

    .. note::

       Requires ``flet-audio`` (``pip install flet-audio``).  :meth:`load_all`
       silently does nothing when the package is missing.
    """

    #: Default sound definitions — each entry is passed to :func:`make_beep`.
    SOUNDS: dict[str, dict] = {
        "hit":     {"freq": 220, "duration": 0.08, "volume": 0.40},
        "shoot":   {"freq": 880, "duration": 0.04, "volume": 0.35},
        "build":   {"freq": 440, "duration": 0.15, "volume": 0.40},
        "destroy": {"freq": 120, "duration": 0.40, "volume": 0.50},
        "death":   {"freq": 660, "duration": 0.10, "volume": 0.30},
        "select":  {"freq": 1047, "duration": 0.06, "volume": 0.25},
        "train":   {"freq": 440, "duration": 0.10, "volume": 0.30},
        "move":    {"freq": 330, "duration": 0.05, "volume": 0.20},
        "error":   {"freq": 180, "duration": 0.20, "volume": 0.40},
    }

    #: Melody-based sounds — list of ``(freq, duration)`` notes.
    MELODIES: dict[str, list[tuple[float, float]]] = {
        "victory": [(523, 0.10), (659, 0.10), (784, 0.20)],
        "defeat":  [(392, 0.12), (330, 0.12), (262, 0.25)],
    }

    def __init__(
        self,
        page_or_snd: ft.Page | SoundManager,
        pool_size: int = 3,
    ) -> None:
        self._owned: bool
        if isinstance(page_or_snd, SoundManager):
            self._snd = page_or_snd
            self._owned = False
        else:
            self._snd = SoundManager(page_or_snd, pool_size=pool_size)
            self._owned = True

    def load_all(self) -> None:
        """Load all built-in sound definitions.

        Calls :meth:`SoundManager.load` for every entry in :attr:`SOUNDS`
        and :attr:`MELODIES`.  Safe to call multiple times (subsequent
        calls are no-ops when sounds already exist).
        """
        if not _AUDIO_AVAILABLE:
            return
        for name, kwargs in self.SOUNDS.items():
            if name not in self._snd._pools:
                self._snd.load(name, make_beep(**kwargs))
        for name, notes in self.MELODIES.items():
            if name not in self._snd._pools:
                self._snd.load(name, make_melody(notes))

    def play(self, name: str, volume: float | None = None) -> None:
        """Fire-and-forget play a named sound."""
        self._snd.play(name, volume)

    @property
    def volume(self) -> float:
        """Global playback volume 0.0–1.0."""
        return self._snd.volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._snd.volume = value

    @property
    def enabled(self) -> bool:
        """If ``False``, :meth:`play` is a no-op."""
        return self._snd.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._snd.enabled = bool(value)

    @property
    def muted(self) -> bool:
        """Alias for ``not enabled``."""
        return not self._snd.enabled

    @muted.setter
    def muted(self, value: bool) -> None:
        self._snd.enabled = not bool(value)

    def destroy(self) -> None:
        """Release audio resources.  Call before closing the page."""
        if self._owned:
            self._snd.destroy()
