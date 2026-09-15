# =========================================================
# gui_kit/rounded.py — Primitives "coins arrondis" pour Tk
# =========================================================
# Tkinter ne sait pas arrondir un widget nativement : on dessine
# un polygone lissé sur un Canvas dont le fond correspond au fond
# du parent, de sorte que les coins "coupés" du rectangle arrondi
# laissent voir le fond du parent plutôt qu'un carré disgracieux.
# =========================================================
from __future__ import annotations
import tkinter as tk
from typing import Optional

from . import theme


def rounded_rect_points(x1, y1, x2, y2, r):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


def draw_rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    pts = rounded_rect_points(x1, y1, x2, y2, r)
    return canvas.create_polygon(pts, smooth=True, splinesteps=24, **kwargs)


class RoundedFrame(tk.Canvas):
    """Un conteneur à coins arrondis pouvant héberger un unique widget enfant.

    Utilisation :
        card = RoundedFrame(parent, bg_outer=C_PARENT, fill=C_CARD, radius=10)
        inner = tk.Label(card, text="...", bg=C_CARD, ...)
        card.set_content(inner, padx=16, pady=12)
    """

    def __init__(self, parent, bg_outer: str, fill: str, radius: int = theme.RADIUS,
                 outline: str = "", outline_width: int = 0, **kwargs):
        super().__init__(parent, bg=bg_outer, highlightthickness=0, bd=0, **kwargs)
        self._fill = fill
        self._outline = outline
        self._outline_width = outline_width
        self._radius = radius
        self._rect_id = None
        self._content = None
        self._content_win = None
        self._pad = (0, 0)
        self.bind("<Configure>", self._redraw)

    def set_fill(self, fill: str):
        self._fill = fill
        if self._rect_id:
            self.itemconfig(self._rect_id, fill=fill)
            if self._content is not None:
                try:
                    self._content.configure(bg=fill)
                except Exception:
                    pass

    def set_content(self, widget, padx: int = 12, pady: int = 10):
        self._content = widget
        self._pad = (padx, pady)
        self._content_win = self.create_window(0, 0, window=widget, anchor="nw")
        self._redraw()

    def _redraw(self, *_):
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return
        if self._rect_id:
            self.delete(self._rect_id)
        self._rect_id = draw_rounded_rect(
            self, 1, 1, w - 1, h - 1, self._radius,
            fill=self._fill, outline=self._outline, width=self._outline_width,
        )
        self.tag_lower(self._rect_id)
        if self._content is not None and self._content_win is not None:
            padx, pady = self._pad
            self.coords(self._content_win, padx, pady)


class IconButton(tk.Canvas):
    """Bouton icône rond/arrondi avec transition douce de couleur au survol."""

    def __init__(self, parent, text: str, command=None, size: int = 34,
                 bg: str = theme.PANEL, fg: str = theme.TEXT_SUB,
                 hover_bg: str = theme.ELEVATED, hover_fg: str = theme.ACCENT,
                 font=None, radius: Optional[int] = None, tooltip: str = ""):
        super().__init__(parent, width=size, height=size, bg=bg,
                          highlightthickness=0, bd=0, cursor="hand2")
        self._size = size
        self._bg = bg
        self._fg = fg
        self._hover_bg = hover_bg
        self._hover_fg = hover_fg
        self._command = command
        self._radius = radius if radius is not None else size // 2
        self._font = font or theme.sans(13)
        self._disabled = False
        self._rect = draw_rounded_rect(self, 1, 1, size - 1, size - 1, self._radius,
                                        fill=bg, outline="")
        self._text = self.create_text(size / 2, size / 2, text=text, fill=fg, font=self._font)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def set_state(self, disabled: bool):
        self._disabled = disabled
        self.configure(cursor="arrow" if disabled else "hand2")
        fg = theme.TEXT_FAINT if disabled else self._fg
        self.itemconfig(self._text, fill=fg)

    def set_active(self, active: bool):
        """Bascule un état 'sélectionné' persistant (ex. micro activé)."""
        if active:
            self.itemconfig(self._rect, fill=self._hover_bg)
            self.itemconfig(self._text, fill=self._hover_fg)
        else:
            self.itemconfig(self._rect, fill=self._bg)
            self.itemconfig(self._text, fill=self._fg)

    def _on_enter(self, _):
        if self._disabled:
            return
        self.itemconfig(self._rect, fill=self._hover_bg)
        self.itemconfig(self._text, fill=self._hover_fg)

    def _on_leave(self, _):
        if self._disabled:
            return
        self.itemconfig(self._rect, fill=self._bg)
        self.itemconfig(self._text, fill=self._fg)

    def _on_click(self, _):
        if self._disabled or not self._command:
            return
        self._command()
