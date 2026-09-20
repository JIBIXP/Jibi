"""
JIBI GUI Kit — UI State
=======================

Stocke uniquement les préférences d'interface.
Aucune logique métier.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_STATE = {
    "theme": "moderne",
    "sidebar_collapsed": False,
    "panel_open": False,
    "panel_width": None,
    "window_width": 1200,
    "window_height": 760,
    "geometry": None,
}


class UIState:
    def __init__(
        self,
        path: str | Path | None = None,
    ) -> None:
        self.path = (
            Path(path)
            if path
            else Path.home() / ".jibi_ui_state.json"
        )

        self.data = dict(DEFAULT_STATE)
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(self.data)

        try:
            raw = self.path.read_text(
                encoding="utf-8"
            )

            loaded = json.loads(raw)

            if isinstance(loaded, dict):
                self.data.update(loaded)

        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
        ):
            pass

        return dict(self.data)

    def save(self) -> bool:
        temp_name: str | None = None
        try:
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            fd, temp_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=str(self.path.parent),
                text=True,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fichier:
                json.dump(self.data, fichier, ensure_ascii=False, indent=2)
                fichier.flush()
                os.fsync(fichier.fileno())
            os.replace(temp_name, self.path)
            temp_name = None

            return True

        except OSError:
            return False

        finally:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        return self.data.get(key, default)

    def set(
        self,
        key: str | None = None,
        value: Any = None,
        **kwargs,
    ) -> None:
        """Accepte set('key', value) ou set(key=value, key2=value2, ...)."""

        if key is not None:
            self.data[key] = value

        for k, v in kwargs.items():
            self.data[k] = v
