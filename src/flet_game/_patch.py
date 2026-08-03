"""Defensive patches for Flet internals (idempotent, safe to import anywhere).

``Dart_PostCObject_DL failed``
-----------------------------
On embedded native builds (``flet build`` for Android/iOS) the RawImage
data channel is a Dart native port.  When the widget leaves the Flutter
tree — scene transitions, pause/resume, app backgrounding — Dart disposes
the port, but a stale ``on_data_channel_open`` can still arrive and Flet's
internal frame-replay then calls ``send_bytes`` on the dead port, raising
``RuntimeError: Dart_PostCObject_DL failed`` from inside the event
dispatcher (``session.dispatch_event`` → ``raw_image._capture_channel``).
The dispatcher catches it and shows "The application encountered an
error" on the phone, and the viewport freezes.

PostCObject failing is always fatal for that channel — there is no valid
payload recovery.  We therefore swallow the error and mark the channel
closed so every later ``send`` no-ops; when the client remounts the
widget it opens a fresh channel (new port), which works normally.
"""

from __future__ import annotations

import logging

_log = logging.getLogger("flet_game")


def install() -> bool:
    """Patch ``_DartBridgeDataChannel.send``.  Returns True if patched."""
    try:
        from flet.data_channel import _DartBridgeDataChannel
    except ImportError:
        return False

    original = _DartBridgeDataChannel.send
    if getattr(original, "_flet_game_dead_port_guard", False):
        return True

    def send(self, payload: bytes) -> None:
        if getattr(self, "_closed", False):
            return
        try:
            original(self, payload)
        except RuntimeError as exc:
            if "Dart_PostCObject_DL" in str(exc):
                _log.warning(
                    "Dart data channel %r died (%s) — disabling it; a "
                    "remount opens a fresh channel.",
                    getattr(self, "_port", "?"), exc,
                )
                self._closed = True
            else:
                raise

    send._flet_game_dead_port_guard = True
    _DartBridgeDataChannel.send = send
    return True
