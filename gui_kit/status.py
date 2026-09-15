# =========================================================
# gui_kit/status.py — Indicateur d'état animé
# =========================================================
# Pastille qui "respire" + libellé d'état. Remplace le texte
# statique de l'ancienne GUI : l'animation porte l'information
# (immobile = prêt, respiration = activité).
# La respiration est une simple boucle after() locale : le moteur
# gui_kit.animation ne fait que les interpolations one-shot.
# =========================================================
from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont

from . import theme
from .controls import round_rect

# état -> (libellé, couleur du point, respire ?)
STATES = {
    "ready":     ("Prêt", theme.ACCENT, True),
    "thinking":  ("Réfléchit…", theme.ACCENT, True),
    "listening": ("En train d'écouter", theme.ACCENT, True),
    "busy":      ("Génération…", theme.ACCENT, True),
    "offline":   ("Modèle indisponible", theme.TEXT_FAINT, False),
    "error":     ("Erreur", theme.DANGER, False),
}


def _pulse01(t: float) -> float:
    """Oscillation douce [0,1] sur une période normalisée."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * t)


class _Breathing:
    """Boucle after() autonome pour faire respirer un widget."""

    def __init__(self, widget, period_ms: int, on_frame):
        self._w = widget
        self._period = max(1, period_ms) / 1000.0
        self._on_frame = on_frame
        self._id = None
        self._t0 = None

    def start(self):
        import time
        self.stop()
        self._t0 = time.monotonic()
        self._id = self._w.after(16, self._tick)

    def _tick(self):
        import time
        try:
            if not self._w.winfo_exists():
                self._id = None
                return
        except Exception:
            self._id = None
            return
        t = ((time.monotonic() - self._t0) / self._period) % 1.0
        try:
            self._on_frame(_pulse01(t))
        except Exception:
            self._id = None
            return
        self._id = self._w.after(16, self._tick)

    def stop(self):
        if self._id is not None:
            try:
                self._w.after_cancel(self._id)
            except Exception:
                pass
            self._id = None


class StatusIndicator(tk.Frame):
    def __init__(self, master, *, state="ready", bg=None, compact=False, **kw):
        self._bg = bg or master["bg"]
        self.compact = compact
        super().__init__(master, bg=self._bg, **kw)

        size = 12 if compact else 16
        self.dot = tk.Canvas(self, width=size + 8, height=size + 8,
                             bg=self._bg, highlightthickness=0, bd=0)
        self.dot.pack(side="left", padx=(0, 6))
        self._size = size

        self.label = tk.Label(self, text=STATES[state][0], bg=self._bg,
                              fg=theme.TEXT_SUB, font=theme.sans(9))
        self.label.pack(side="left")

        self._state = None
        self._breath = _Breathing(self, theme.PULSE_PERIOD_MS,
                                  lambda k: self._draw_dot(k, self._color))
        self.set_state(state)

    def _draw_dot(self, k: float = 1.0, color: str = None, halo: bool = True):
        self.dot.delete("all")
        s = self._size
        cx = cy = (s + 8) / 2
        color = color or theme.ACCENT
        if halo:
            r = s / 2 + 1.5 + 2.0 * k
            self.dot.create_oval(cx - r, cy - r, cx + r, cy + r,
                                 fill=theme.mix(self._bg, color, 0.10 + 0.16 * k),
                                 outline=theme.mix(self._bg, color, 0.10 + 0.16 * k))
        r = s / 2 * (0.82 + 0.18 * k)
        self.dot.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline=color)

    def set_state(self, state: str, animate: bool = True):
        state = state if state in STATES else "ready"
        label, color, breathes = STATES[state]
        if state == self._state:
            return
        self._state = state
        self._color = color
        self.label.configure(text=label,
                             fg=theme.TEXT_SUB if breathes else theme.TEXT_FAINT)
        self._breath.stop()
        if breathes and animate:
            self._breath.start()
            self._draw_dot(0.5, color)
        else:
            self._draw_dot(1.0 if breathes else 0.2, color, halo=breathes)

    def set_label(self, text: str):
        self.label.configure(text=text)


class StatusPill(tk.Canvas):
    """Variante "pilule" pour la barre supérieure : fond discret + point."""

    def __init__(self, master, *, state="ready", height=30, bg=None, **kw):
        self._bg = bg or master["bg"]
        super().__init__(master, height=height, width=150, bg=self._bg,
                         highlightthickness=0, bd=0, **kw)
        self._state = None
        self._color = theme.ACCENT
        self._k = 1.0
        self._label = STATES[state][0]
        self._height = height
        self.bind("<Configure>", lambda _e: self._redraw())
        self._breath = _Breathing(self, theme.PULSE_PERIOD_MS, self._breathe)
        self.set_state(state)

    def set_state(self, state: str, animate: bool = True):
        state = state if state in STATES else "ready"
        label, color, breathes = STATES[state]
        if state == self._state:
            return
        self._state = state
        self._label = label
        self._color = color
        self._breath.stop()
        if breathes and animate:
            self._breath.start()
            self._k = 0.6
        else:
            self._k = 0.15
        self._redraw()

    def _breathe(self, t):
        self._k = t
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        need = 34 + tkfont.Font(font=theme.sans(9)).measure(self._label) + 14
        if need != w:
            self.configure(width=need)
            w = need
        round_rect(self, 0, 0, w, h, h / 2,
                   fill=theme.lighten(self._bg, 0.05),
                   outline=theme.BORDER_SOFT)
        cx, cy = 18, h / 2
        r = 3.2 + 1.4 * self._k
        halo = theme.mix(theme.lighten(self._bg, 0.05), self._color, 0.12 + 0.2 * self._k)
        self.create_oval(cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3,
                         fill=halo, outline=halo)
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill=self._color, outline=self._color)
        self.create_text(cx + 14, cy, text=self._label, anchor="w",
                         fill=theme.TEXT_SUB, font=theme.sans(9))
