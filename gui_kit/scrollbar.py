# =========================================================
# gui_kit/scrollbar.py — Scrollbar fine et discrète
# =========================================================
# La scrollbar système (tk.Scrollbar / ttk) est grise, épaisse et
# jure avec le thème. On la remplace par un curseur dessiné :
#   * 6 px au repos, 9 px au survol (transition de couleur)
#   * pouce arrondi, piste invisible
#   * clic sur la piste = page up/down, glisser = moveto
# Interface compatible : .set(first, last) + command("moveto"/"scroll").
# =========================================================
from __future__ import annotations

import tkinter as tk

from . import theme


class ThinScrollbar(tk.Canvas):
    def __init__(self, master, *, command=None, width=8, orient="vertical",
                 bg=None, **kw):
        self._bg = bg or master["bg"]
        self.orient = orient
        self.command = command
        self._width = width
        self._first, self._last = 0.0, 1.0
        self._hover = False
        self._dragging = False
        self._drag_offset = 0

        super().__init__(master, width=width, bg=self._bg,
                         highlightthickness=0, bd=0, **kw)
        self._thumb = None
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    # -------------------------------------------------- API tk-compatible
    def set(self, first, last):
        try:
            self._first, self._last = float(first), float(last)
        except (TypeError, ValueError):
            return
        self._draw()

    def attach(self, widget):
        """Branche la scrollbar sur un widget scrollable (Text/Canvas/Frame)."""
        if self.orient == "vertical":
            widget.configure(yscrollcommand=self.set)
        else:
            widget.configure(xscrollcommand=self.set)
        self.command = getattr(widget, "yview" if self.orient == "vertical" else "xview")

    # -------------------------------------------------- rendu
    def _geom(self):
        if self.orient == "vertical":
            L = max(1, int(self.winfo_height()))
            return L
        return max(1, int(self.winfo_width()))

    def _draw(self):
        self.delete("all")
        if self.command is None:
            return
        L = self._geom()
        span = max(0.0, self._last - self._first)
        if span >= 0.999:
            return  # tout tient à l'écran : pas de pouce
        thumb_len = max(28.0, span * L)
        start = self._first * (L - thumb_len)
        end = start + thumb_len
        w = self._width + (3 if (self._hover or self._dragging) else 0)
        pad = max(1, (self._width + 4 - w) // 2)
        col = theme.TEXT_SUB if (self._hover or self._dragging) else theme.lighten(self._bg, 0.14)
        if self.orient == "vertical":
            x0, x1 = self.winfo_width() - pad - w, self.winfo_width() - pad
            self._thumb = self.create_rectangle(x0, start, x1, end, fill=col, outline=col)
        else:
            y0, y1 = pad, pad + w
            self._thumb = self.create_rectangle(start, y0, end, y1, fill=col, outline=col)

    # -------------------------------------------------- interactions
    def _on_enter(self, _e):
        self._hover = True
        self._draw()

    def _on_leave(self, _e):
        self._hover = False
        self._draw()

    def _frac(self, e):
        L = self._geom()
        pos = e.y if self.orient == "vertical" else e.x
        return min(1.0, max(0.0, pos / L))

    def _thumb_bounds(self):
        L = self._geom()
        span = max(0.0, self._last - self._first)
        thumb_len = max(28.0, span * L)
        start = self._first * (L - thumb_len)
        return start, start + thumb_len

    def _on_press(self, e):
        if self.command is None:
            return
        pos = e.y if self.orient == "vertical" else e.x
        start, end = self._thumb_bounds()
        if start <= pos <= end:
            self._dragging = True
            self._drag_offset = pos - start
            self._draw()
        else:
            # Clic sur la piste : saut d'une page dans la direction du clic.
            direction = 1 if pos > end else -1
            try:
                self.command("scroll", direction, "pages")
            except Exception:
                pass

    def _on_drag(self, e):
        if not self._dragging or self.command is None:
            return
        L = self._geom()
        span = max(0.0, self._last - self._first)
        thumb_len = max(28.0, span * L)
        pos = e.y if self.orient == "vertical" else e.x
        free = max(1.0, L - thumb_len)
        frac = min(1.0, max(0.0, (pos - self._drag_offset) / free))
        try:
            self.command("moveto", frac)
        except Exception:
            pass

    def _on_release(self, _e):
        self._dragging = False
        self._draw()


# =========================================================
# ScrollArea — zone défilante générique (canvas + frame enfant)
# =========================================================
# Utilisée par la conversation et par l'historique de la sidebar.
# Deux comportements importants :
#   * la largeur du contenu suit celle du canvas (wraplength correct)
#   * le défilement auto ne s'accroche en bas QUE si l'utilisateur
#     y était déjà, sinon on lui vole le scroll pendant qu'il lit.
# =========================================================
class ScrollArea(tk.Frame):
    def __init__(self, master, *, bg, with_scrollbar=True, auto_scroll=True, **kw):
        super().__init__(master, bg=bg, **kw)
        self._bg = bg
        self.auto_scroll = auto_scroll

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.frame = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        self.sb = None
        if with_scrollbar:
            self.sb = ThinScrollbar(self, bg=bg)
            self.sb.attach(self.canvas)
            self.sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<Configure>", self._on_canvas)
        self.frame.bind("<Configure>", self._on_frame)
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.frame)
        self._stick = True

    # -------------------------------------------------- câblage molette
    def _bind_wheel(self, w):
        w.bind("<MouseWheel>", self._on_wheel)            # Windows / macOS
        w.bind("<Button-4>", self._on_wheel)              # Linux (haut)
        w.bind("<Button-5>", self._on_wheel)              # Linux (bas)
        for child in w.winfo_children():
            try:
                self._bind_wheel(child)
            except Exception:
                pass

    def bind_wheel_recursive(self):
        """À rappeler après avoir ajouté des enfants dynamiquement."""
        self._bind_wheel(self.frame)

    def _on_wheel(self, e):
        if getattr(e, "num", None) == 4:
            delta = -3
        elif getattr(e, "num", None) == 5:
            delta = 3
        else:
            delta = -1 if e.delta > 0 else 1
            delta *= 3
        self._stick = self.is_at_bottom()
        self.canvas.yview_scroll(delta, "units")

    # -------------------------------------------------- géométrie
    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        if self.auto_scroll and self._stick:
            self.stick_to_bottom()

    def _on_frame(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
        if self.auto_scroll and self._stick:
            self.stick_to_bottom()

    def inner_width(self) -> int:
        return max(120, int(self.canvas.winfo_width()))

    def is_at_bottom(self, tol: float = 0.955) -> bool:
        try:
            return self.canvas.yview()[1] >= tol
        except Exception:
            return True

    def stick_to_bottom(self):
        self._stick = True
        self.canvas.update_idletasks()
        try:
            self.canvas.yview_moveto(1.0)
        except Exception:
            pass

    def release_stick(self):
        self._stick = False

    def clear(self):
        for w in self.frame.winfo_children():
            w.destroy()
