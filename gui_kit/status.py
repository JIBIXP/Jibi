"""
JIBI GUI Kit — Status
=====================

Les états sont stockés sous forme de tuples :
    (label, couleur, pulse)
où `pulse` indique si l'indicateur doit respirer (état en cours).

gui.py peut ajouter/compléter des états via :
    STATES.setdefault("mon_etat", ("Label", couleur, False))
"""

from __future__ import annotations

import math
import tkinter as tk

from . import theme


STATES: dict[str, tuple[str, str, bool]] = {
    "ready": ("Prêt", theme.ACCENT, False),
    "thinking": ("Réflexion…", theme.ACCENT, True),
    "busy": ("En cours…", theme.ACCENT, True),
    "working": ("Travail…", theme.ACCENT, True),
    "success": ("Terminé", theme.ACCENT, False),
    "done": ("Terminé", theme.ACCENT, False),
    "error": ("Erreur", theme.DANGER, False),
    "warning": ("Attention", theme.DANGER, False),
    "confirmation": ("Confirmation requise", theme.ACCENT, True),
    "cancelled": ("Annulé", theme.TEXT_SUB, False),
    "offline": ("Hors ligne", theme.TEXT_SUB, False),
}


def _pulse01(value: float) -> float:
    return (math.sin(value * math.pi * 2) + 1) / 2


class _Breathing:
    def __init__(self, widget, callback):
        self.widget = widget
        self.callback = callback
        self.running = False
        self.after_id = None
        self.phase = 0.0

    def start(self):
        if self.running:
            return
        self.running = True
        self._tick()

    def _tick(self):
        if not self.running:
            return
        self.phase += 0.045
        try:
            self.callback(_pulse01(self.phase))
        except Exception:
            self.stop()
            return
        self.after_id = self.widget.after(40, self._tick)

    def stop(self):
        self.running = False
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None


class StatusIndicator(tk.Canvas):
    """Petit point circulaire, respire lorsque l'état est actif."""

    def __init__(self, master, size=12, state="ready", **kwargs):
        super().__init__(
            master,
            width=size,
            height=size,
            highlightthickness=0,
            bd=0,
            bg=kwargs.pop("bg", theme.COLORS["surface"]),
            **kwargs,
        )

        self.size = size
        self.state = state
        self._breathing = _Breathing(self, self._animate)

        self._draw()

    def set_state(self, state: str):
        if state not in STATES:
            state = "ready"

        self.state = state
        self._draw()

        _, _, pulse = STATES[state]

        if pulse:
            self._breathing.start()
        else:
            self._breathing.stop()

    def _draw(self, pulse=0.0):
        self.delete("all")

        _, color, is_pulsing = STATES.get(self.state, STATES["ready"])

        margin = 2
        if is_pulsing:
            margin = 2 - pulse * 1.2

        self.create_oval(
            margin,
            margin,
            self.size - margin,
            self.size - margin,
            fill=color,
            outline="",
        )

    def _animate(self, value):
        self._draw(value)

    def destroy(self):
        self._breathing.stop()
        super().destroy()


class StatusPill(tk.Frame):
    """
    Indicateur :
        ● Prêt
    """

    def __init__(self, master, state="ready", compact=False, **kwargs):
        super().__init__(
            master,
            bg=kwargs.pop("bg", theme.COLORS["surface"]),
            **kwargs,
        )

        self.compact = compact
        self.state = state

        self.indicator = StatusIndicator(
            self,
            size=11,
            state=state,
            bg=self.cget("bg"),
        )

        self.indicator.pack(side="left", padx=(0, 7))

        label, _color, _pulse = STATES.get(state, STATES["ready"])

        self.label = tk.Label(
            self,
            text=label,
            bg=self.cget("bg"),
            fg=theme.TEXT,
            font=theme.sans(9, bold=True),
        )

        self.label.pack(side="left")

    def set_state(self, state: str, text: str | None = None):
        if state not in STATES:
            state = "ready"

        self.state = state
        self.indicator.set_state(state)

        if text is None:
            text = STATES[state][0]

        self.label.configure(text=text)
