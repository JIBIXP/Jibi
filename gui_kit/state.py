# =========================================================
# gui_kit/state.py — Persistance légère de l'état d'interface
# =========================================================
# Ne stocke QUE des préférences de présentation (largeurs, état
# ouvert/fermé des panneaux, géométrie de fenêtre). Aucune donnée
# métier : la logique reste entièrement dans core/.
# =========================================================
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

from . import theme

DEFAULT_STATE: Dict[str, Any] = {
    "sidebar_open": True,
    "sidebar_width": theme.SIDEBAR_DEFAULT,
    "panel_open": False,
    "panel_width": theme.PANEL_DEFAULT,
    "geometry": "1280x860+120+70",
}


class UIState:
    """Petit magasin clé/valeur sauvegardé en JSON à côté de gui.py."""

    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, Any] = dict(DEFAULT_STATE)
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
        except Exception:
            # Fichier corrompu/absent : on retombe silencieusement sur les défauts.
            pass

    def save(self) -> None:
        try:
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, **kwargs: Any) -> None:
        self.data.update(kwargs)
