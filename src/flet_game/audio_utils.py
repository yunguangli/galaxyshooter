"""
audio_utils.py — Audio helper utilities for flet_game.

Provides pure-Python WAV generation so games can produce sound effects
without any external files or audio assets.
"""

import math
import struct


def make_beep(
    freq: float = 440,
    duration: float = 0.08,
    sample_rate: int = 44100,
    volume: float = 0.45,
) -> bytes:
    """Return a mono 16-bit PCM WAV byte string for a sine-wave beep.

    Parameters
    ----------
    freq:        Frequency in Hz (e.g. 880 for a high blip, 180 for a low thud).
    duration:    Length in seconds.
    sample_rate: Samples per second — 44100 is standard.
    volume:      Peak amplitude, 0.0–1.0.  Keep below 0.7 to avoid clipping.

    Returns
    -------
    bytes
        A complete WAV file in memory, ready for ``SoundManager.load(name, bytes)``.

    Example
    -------
    ::

        from flet_game import SoundManager, make_beep

        snd = SoundManager(page)
        snd.load("shoot", make_beep(freq=880,  duration=0.04, volume=0.35))
        snd.load("hurt",  make_beep(freq=180,  duration=0.14, volume=0.60))
        snd.load("coin",  make_beep(freq=1320, duration=0.06, volume=0.40))
        snd.play("shoot")
    """
    n = int(sample_rate * duration)
    pcm = struct.pack(
        f"<{n}h",
        *[
            int(32767 * volume * math.sin(2 * math.pi * freq * i / sample_rate))
            for i in range(n)
        ],
    )
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm),
    )
    return header + pcm


def make_melody(
    notes: list[tuple[float, float]],
    sample_rate: int = 44100,
    volume: float = 0.4,
) -> bytes:
    """Return a mono 16-bit PCM WAV for a sequence of (freq_hz, duration_sec) notes.

    Useful for jingles, fanfares, and alert melodies.

    Parameters
    ----------
    notes
        List of ``(frequency_hz, duration_sec)`` tuples.  Frequencies are
        played back-to-back with no gap.
    sample_rate
        Samples per second.
    volume
        Peak amplitude 0.0–1.0.

    Returns
    -------
    bytes
        A complete WAV file in memory.

    Example
    -------
    ::

        # Ascending C-E-G fanfare
        fanfare = make_melody([(523, 0.12), (659, 0.12), (784, 0.25)], volume=0.5)
        snd.load("victory", fanfare)
    """
    samples: list[int] = []
    for freq, dur in notes:
        n = int(sample_rate * dur)
        for i in range(n):
            samples.append(
                int(32767 * volume * math.sin(2 * math.pi * freq * i / sample_rate))
            )
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm),
    )
    return header + pcm
