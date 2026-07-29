"""
test_savedata.py — Step 16: SaveData persistent key-value store
================================================================
Run with:
    python src/test/test_savedata.py
  or:
    flet run src/test/test_savedata.py

What is tested
--------------
  ✓ SaveData("test_game") — creates file in platform app-data folder
  ✓ set() / get() / delete() / clear()
  ✓ increment() — atomic add-to-numeric
  ✓ update_high_score() — only saves if new score is higher
  ✓ save() / load() — explicit disk flush and reload
  ✓ auto_save=True — every set() immediately flushes
  ✓ dict-style access — save["key"], save["key"] = value, "key" in save
  ✓ Persistence across simulated restart (load from same file)
  ✓ delete_file() — removes the backing JSON file

Demo
----
Interactive panel: type a key, type a value, click Set / Get / Delete.
A "Play" button increments a play count and checks a high score.
A "Reload" button re-reads from disk to prove persistence.
All current stored keys are shown in a list that updates live.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft
from flet_game import SaveData


def main(page: ft.Page) -> None:
    page.title = "flet_game — Step 16: SaveData"
    page.bgcolor = ft.Colors.GREY_900
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    # ── Create the save store ─────────────────────────────────────────────────
    save = SaveData("flet_game_test", auto_save=False)

    # ── Status / log ─────────────────────────────────────────────────────────
    log_text = ft.Text("", color=ft.Colors.AMBER, size=13, selectable=True)

    def log(msg: str) -> None:
        log_text.value = msg
        log_text.update()

    # ── Key list display ──────────────────────────────────────────────────────
    keys_text = ft.Text("", color=ft.Colors.CYAN, size=12, selectable=True)

    def refresh_keys() -> None:
        if not save.keys():
            keys_text.value = "(no data in memory)"
        else:
            lines = [f"  {k!r}: {save.get(k)!r}" for k in save.keys()]
            keys_text.value = "Current data:\n" + "\n".join(lines)
        if keys_text.page:
            keys_text.update()

    # ── Input fields ──────────────────────────────────────────────────────────
    key_field   = ft.TextField(label="Key",   width=200, bgcolor=ft.Colors.GREY_800)
    value_field = ft.TextField(label="Value", width=200, bgcolor=ft.Colors.GREY_800)

    def _set(_):
        k = key_field.value.strip()
        v = value_field.value.strip()
        if not k:
            log("Key is empty"); return
        # Try to convert to int/float/bool, else keep as string
        for convert in (int, float):
            try:
                v = convert(v); break
            except ValueError:
                pass
        save.set(k, v)
        log(f"set({k!r}, {v!r})")
        refresh_keys()

    def _get(_):
        k = key_field.value.strip()
        result = save.get(k, default="<not found>")
        log(f"get({k!r}) → {result!r}")

    def _delete(_):
        k = key_field.value.strip()
        existed = save.delete(k)
        log(f"delete({k!r}) → existed={existed}")
        refresh_keys()

    def _clear(_):
        save.clear()
        log("clear() — all keys removed from memory (not yet saved to disk)")
        refresh_keys()

    def _save(_):
        save.save()
        log(f"save() → {save.path}")

    def _load(_):
        loaded = save.load()
        log(f"load() → file_existed={loaded}")
        refresh_keys()

    def _delete_file(_):
        deleted = save.delete_file()
        log(f"delete_file() → {deleted}")
        save.load()   # reset in-memory data too
        refresh_keys()

    # ── Gameplay simulation ───────────────────────────────────────────────────
    score_field = ft.TextField(label="Score to submit", width=180,
                               bgcolor=ft.Colors.GREY_800, value="0")

    def _play(_):
        plays = save.increment("plays")
        score = int(score_field.value or "0")
        new_best = save.update_high_score("high_score", score)
        save.save()
        best = save.get("high_score")
        log(
            f"Played! plays={plays}  score={score}  "
            + ("NEW HIGH SCORE!" if new_best else f"best={best}")
        )
        refresh_keys()

    def _reset_game(_):
        save.delete("plays")
        save.delete("high_score")
        save.save()
        log("Game data reset (plays + high_score deleted & saved)")
        refresh_keys()

    # ── Auto-save toggle ──────────────────────────────────────────────────────
    auto_switch = ft.Switch(
        label="auto_save",
        value=False,
        on_change=lambda e: setattr(save, "_auto_save", e.control.value)
                            or log(f"auto_save = {e.control.value}"),
    )

    # ── Layout ────────────────────────────────────────────────────────────────
    page.add(
        ft.Text("SaveData — persistent key-value store", size=20,
                color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
        ft.Divider(),

        ft.Text("Manual key/value", color=ft.Colors.WHITE),
        ft.Row([key_field, value_field]),
        ft.Row([
            ft.FilledButton("Set",    on_click=_set),
            ft.TextButton ("Get",    on_click=_get),
            ft.TextButton ("Delete", on_click=_delete),
        ]),

        ft.Divider(),
        ft.Text("Persistence", color=ft.Colors.WHITE),
        ft.Row([
            ft.FilledButton ("Save to disk", on_click=_save),
            ft.TextButton  ("Reload from disk", on_click=_load),
            ft.TextButton  ("Clear (memory)",   on_click=_clear),
            ft.TextButton  ("Delete file",       on_click=_delete_file),
        ]),
        auto_switch,

        ft.Divider(),
        ft.Text("Gameplay simulation", color=ft.Colors.WHITE),
        ft.Row([score_field,
                ft.FilledButton("Play (increment + high score)", on_click=_play),
                ft.TextButton("Reset game data", on_click=_reset_game)]),

        ft.Divider(),
        log_text,
        keys_text,
    )
    refresh_keys()
    page.update()


ft.run(main)
