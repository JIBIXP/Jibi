# =========================================================
# gui_kit/rounded.py — Primitives graphiques "coins arrondis"
# =========================================================
# Tkinter n'a pas de border-radius : tout est dessiné au canvas.
# Ce module fournit :
#   * round_rect()    -> polygone lissé (le "border-radius" de Tk)
#   * RoundedFrame    -> carte arrondie avec bordure, corps enfant
#   * IconButton      -> bouton icône/label dessiné, avec hover animé
#   * draw_icon()     -> jeu d'icônes vectorielles minimales
#   * Avatar          -> pastille ronde (initiale ou halot accent)
# =========================================================
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from . import theme
from .rounded import draw_rounded_rect


# ---------------------------------------------------------
# Le "border-radius" de Tkinter : polygone à coins lissés.
# Les points doublés aux angles forcent smooth=True à produire
# un arrondi propre plutôt qu'une spline molle.
# ---------------------------------------------------------
def round_rect(canvas, *args, **kwargs):
    """Alias : le dessin réel vit dans gui_kit.rounded.draw_rounded_rect."""
    return draw_rounded_rect(canvas, *args, **kwargs)


class RoundedFrame(tk.Frame):
    """Carte à coins arrondis. Le contenu va dans self.body.

    Implémentation : un Frame normal dont la taille est pilotée par son
    corps (body). Le fond arrondi est peint par un canvas d'arrière-plan
    en place() — le canvas ne participe PAS à la géométrie, ce qui évite
    toute boucle de rétroaction sur la hauteur.
    """

    def __init__(self, master, *, radius=theme.RADIUS, card_bg=theme.PANEL,
                 border_color=None, border_width=1, hover_bg=None,
                 pad=None, highlight=False, **kw):
        self.radius = radius
        self.card_bg = card_bg
        self.border_color = border_color
        self.border_width = border_width
        self.hover_bg = hover_bg if hover_bg is not None else card_bg
        # Inset du corps : moitié du rayon, pour que l'arrondi reste visible.
        self.pad = (radius // 2 + border_width) if pad is None else pad
        bg = kw.pop("bg", None) or _master_bg(master)

        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kw)
        self._bg = bg
        self._hover = False
        self._highlight = highlight

        # Créé AVANT le corps : l'ordre de création détermine l'empilement,
        # le corps (pack) se retrouve donc au-dessus du fond peint.
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._canvas.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        self.body = tk.Frame(self, bg=card_bg)
        self.body.pack(fill="both", expand=True, padx=self.pad, pady=self.pad)
        self.bind("<Configure>", self._redraw)
        self._redraw()

    # -------------------------------------------------- rendu
    def _redraw(self, _evt=None):
        self._canvas.delete("all")
        w = max(2, int(self.winfo_width()))
        h = max(2, int(self.winfo_height()))
        fill = self.hover_bg if self._hover else self.card_bg
        round_rect(self._canvas, 0, 0, w, h, self.radius, fill=fill, outline=fill)
        if self.border_color or self._highlight:
            col = theme.ACCENT if self._highlight else self.border_color
            round_rect(self._canvas, self.border_width / 2, self.border_width / 2,
                       w - self.border_width / 2, h - self.border_width / 2,
                       self.radius, fill="", outline=col, width=self.border_width)

    def set_hover(self, on: bool):
        if self.hover_bg == self.card_bg:
            return
        self._hover = on
        self.body.configure(bg=self.hover_bg if on else self.card_bg)
        self._redraw()

    def set_highlight(self, on: bool):
        self._highlight = on
        self._redraw()

    def set_card_bg(self, color: str):
        self.card_bg = color
        self.body.configure(bg=color)
        self._redraw()


def _master_bg(master):
    try:
        return master["bg"]
    except Exception:
        return theme.BG


class IconButton(tk.Canvas):
    """Bouton dessiné : icône et/ou label, états hover/pressé/désactivé.

    kind:
      "ghost"  -> transparent, icône seule (barres d'outils)
      "soft"   -> fond discret (navigation)
      "accent" -> fond accent plein (action primaire)
    """

    def __init__(self, master, *, icon=None, text="", command=None, kind="ghost",
                 size=34, icon_size=17, pad_x=10, radius=theme.RADIUS,
                 fg=None, tooltip=None, **kw):
        self.kind = kind
        self.icon = icon
        self.text = text
        self.command = command
        self.size = size
        self.icon_size = icon_size
        self.radius = radius
        self.tooltip = tooltip
        self._enabled = True
        self._state = "normal"
        self._tip_win = None

        bg = kw.pop("bg", None) or master["bg"]
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=size, height=size, **kw)
        self._bg = bg
        self._font = theme.sans(10, bold=True)
        self._draw()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    # -------------------------------------------------- couleurs d'état
    def _palette(self):
        st, dis = self._state, not self._enabled
        if self.kind == "accent":
            if dis:
                return theme.lighten(self._bg, 0.06), theme.lighten(self._bg, 0.16)
            if st == "pressed":
                return theme.ACCENT_DARK, theme.ACCENT_ON
            if st == "hover":
                return theme.lighten(theme.ACCENT, 0.12), theme.ACCENT_ON
            return theme.ACCENT, theme.ACCENT_ON
        if self.kind == "soft":
            if dis:
                return self._bg, theme.TEXT_FAINT
            if st == "pressed":
                return theme.ELEVATED, theme.TEXT
            if st == "hover":
                return theme.lighten(self._bg, 0.09), theme.TEXT
            return theme.lighten(self._bg, 0.05), theme.TEXT_SUB
        # ghost
        if dis:
            return self._bg, theme.TEXT_FAINT
        if st == "pressed":
            return theme.lighten(self._bg, 0.12), theme.TEXT
        if st == "hover":
            return theme.lighten(self._bg, 0.08), theme.TEXT
        return self._bg, theme.TEXT_SUB

    def _draw(self):
        self.delete("all")
        bg, fg = self._palette()
        w, h = int(self["width"]), int(self["height"])
        if bg != self._bg:
            round_rect(self, 0, 0, w, h, self.radius, fill=bg, outline=bg)
        cx, cy = w / 2, h / 2
        if self.icon:
            draw_icon(self, self.icon, cx, cy, self.icon_size, fg)
        elif self.text:
            self.create_text(cx, cy, text=self.text, fill=fg, font=self._font)

    # -------------------------------------------------- API publique
    def set_enabled(self, on: bool):
        if self._enabled == on:
            return
        self._enabled = on
        self.configure(cursor="hand2" if on else "arrow")
        self._draw()

    def set_icon(self, icon: str | None):
        self.icon = icon
        self._draw()

    def set_state_visual(self, state: str):
        self._state = state
        self._draw()

    # -------------------------------------------------- événements
    def _on_enter(self, _e):
        if not self._enabled:
            return
        self._state = "hover"
        self.configure(cursor="hand2")
        self._draw()
        if self.tooltip:
            self._show_tip()

    def _on_leave(self, _e):
        self._state = "normal"
        self._draw()
        self._hide_tip()

    def _on_press(self, _e):
        if not self._enabled:
            return
        self._state = "pressed"
        self._draw()

    def _on_release(self, e):
        if not self._enabled:
            return
        inside = 0 <= e.x <= int(self["width"]) and 0 <= e.y <= int(self["height"])
        self._state = "hover" if inside else "normal"
        self._draw()
        if inside and self.command:
            self.command()

    # -------------------------------------------------- tooltip
    def _show_tip(self):
        self._hide_tip()
        try:
            x = self.winfo_rootx() + int(self["width"]) // 2
            y = self.winfo_rooty() + int(self["height"]) + 6
            self._tip_win = tk.Toplevel(self)
            self._tip_win.overrideredirect(True)
            self._tip_win.attributes("-topmost", True)
            f = tk.Frame(self._tip_win, bg=theme.ELEVATED,
                         highlightbackground=theme.BORDER, highlightthickness=1)
            tk.Label(f, text=self.tooltip, bg=theme.ELEVATED, fg=theme.TEXT,
                     font=theme.sans(9), padx=8, pady=4).pack()
            f.pack()
            self._tip_win.update_idletasks()
            self._tip_win.geometry(f"+{x - self._tip_win.winfo_reqwidth() // 2}+{y}")
        except Exception:
            self._tip_win = None

    def _hide_tip(self):
        if self._tip_win is not None:
            try:
                self._tip_win.destroy()
            except Exception:
                pass
            self._tip_win = None


# ---------------------------------------------------------
# Jeu d'icônes — traits normalisés dans un carré [-1, 1].
# Ajouter une icône = ajouter une entrée, rien d'autre.
# ---------------------------------------------------------
ICONS = {
    # 3 barres
    "menu": {"lines": [(-0.7, -0.45, 0.7, -0.45), (-0.7, 0.0, 0.7, 0.0), (-0.7, 0.45, 0.7, 0.45)]},
    "panel_left": {"lines": [(-0.75, -0.7, -0.75, 0.7), (-0.75, -0.7, 0.75, -0.7),
                             (0.75, -0.7, 0.75, 0.7), (0.75, 0.7, -0.75, 0.7),
                             (-0.2, -0.7, -0.2, 0.7)]},
    "chevron_left": {"lines": [(0.25, -0.6, -0.35, 0.0), (-0.35, 0.0, 0.25, 0.6)]},
    "chevron_right": {"lines": [(-0.25, -0.6, 0.35, 0.0), (0.35, 0.0, -0.25, 0.6)]},
    "chevron_down": {"lines": [(-0.6, -0.25, 0.0, 0.35), (0.0, 0.35, 0.6, -0.25)]},
    "plus": {"lines": [(0, -0.7, 0, 0.7), (-0.7, 0, 0.7, 0)]},
    "close": {"lines": [(-0.55, -0.55, 0.55, 0.55), (-0.55, 0.55, 0.55, -0.55)]},
    # flèche papier (envoi)
    "send": {"lines": [(-0.75, 0.0, 0.75, 0.0), (0.2, -0.5, 0.75, 0.0), (0.2, 0.5, 0.75, 0.0)]},
    "stop": {"rect": (-0.5, -0.5, 0.5, 0.5)},
    # micro : capsule + pied
    # micro : capsule (ovale) + support en U + pied
    "mic": {"ovals": [(-0.30, -0.85, 0.30, -0.05)],
            "arcs": [(-0.55, -0.20, 0.55, 0.40, 180, -180)],
            "lines": [(0.0, 0.40, 0.0, 0.78), (-0.28, 0.78, 0.28, 0.78)]},
    "paperclip": {"lines": [(-0.3, 0.55, 0.25, -0.35), (0.25, -0.35, 0.5, 0.05),
                            (0.5, 0.05, -0.1, 0.85), (-0.1, 0.85, -0.55, 0.25),
                            (-0.55, 0.25, 0.15, -0.6)]},
    "copy": {"rects": [(-0.6, -0.15, 0.25, 0.75), (-0.25, -0.75, 0.6, 0.15)]},
    "expand": {"lines": [(-0.7, -0.25, -0.7, -0.7), (-0.7, -0.7, -0.25, -0.7),
                         (0.25, 0.7, 0.7, 0.7), (0.7, 0.7, 0.7, 0.25),
                         (0.7, -0.25, 0.7, -0.7), (0.7, -0.7, 0.25, -0.7),
                         (-0.25, 0.7, -0.7, 0.7), (-0.7, 0.7, -0.7, 0.25)]},
    "code": {"lines": [(-0.35, -0.5, -0.75, 0.0), (-0.75, 0.0, -0.35, 0.5),
                       (0.35, -0.5, 0.75, 0.0), (0.75, 0.0, 0.35, 0.5)]},
    "chat": {"arcs": [(-0.75, -0.65, 0.75, 0.45, 0, 360)],
             "lines": [(-0.3, 0.4, -0.45, 0.85), (-0.45, 0.85, 0.05, 0.42)]},
    "bulb": {"arcs": [(-0.42, -0.8, 0.42, 0.05, 0, 360)],
             "lines": [(-0.22, 0.15, -0.22, 0.55), (0.22, 0.15, 0.22, 0.55),
                       (-0.22, 0.55, 0.22, 0.55)]},
    "trash": {"lines": [(-0.6, -0.45, 0.6, -0.45), (-0.25, -0.45, -0.25, -0.75),
                        (-0.25, -0.75, 0.25, -0.75), (0.25, -0.75, 0.25, -0.45),
                        (-0.45, -0.45, -0.35, 0.75), (-0.35, 0.75, 0.35, 0.75),
                        (0.35, 0.75, 0.45, -0.45)]},
    "refresh": {"arcs": [(-0.6, -0.6, 0.6, 0.6, 40, 260)],
                "lines": [(0.42, 0.5, 0.78, 0.62), (0.42, 0.5, 0.3, 0.86)]},
    "clock": {"arcs": [(-0.7, -0.7, 0.7, 0.7, 0, 360)],
              "lines": [(0, 0, 0, -0.42), (0, 0, 0.34, 0.12)]},
    "doc": {"lines": [(-0.5, -0.8, 0.2, -0.8), (0.2, -0.8, 0.5, -0.5), (0.5, -0.5, 0.5, 0.8),
                      (0.5, 0.8, -0.5, 0.8), (-0.5, 0.8, -0.5, -0.8),
                      (-0.25, -0.3, 0.25, -0.3), (-0.25, 0.05, 0.25, 0.05),
                      (-0.25, 0.4, 0.1, 0.4)]},
    "check": {"lines": [(-0.6, 0.0, -0.15, 0.5), (-0.15, 0.5, 0.65, -0.5)]},
    "brain": {"arcs": [(-0.6, -0.7, 0.6, 0.5, 0, 360)],
              "lines": [(0, -0.7, 0, 0.75), (-0.3, -0.25, 0.0, -0.25), (0.0, 0.1, 0.3, 0.1)]},
    # réglages : trois réglettes + curseurs (lisible, pas une "roue qui tourne")
    "settings": {"lines": [(-0.7, -0.45, 0.7, -0.45), (-0.7, 0.05, 0.7, 0.05),
                           (-0.7, 0.55, 0.7, 0.55)],
                 "ovals": [(-0.15, -0.60, 0.15, -0.30), (0.22, -0.10, 0.52, 0.20),
                           (-0.45, 0.40, -0.15, 0.70)]},
}


def draw_icon(canvas, name, cx, cy, size, color, width=2):
    """Dessine l'icône `name` centrée en (cx, cy) dans un carré de `size` px."""
    spec = ICONS.get(name)
    if not spec:
        return None
    h = size / 2.0
    ids = []
    for (x1, y1, x2, y2) in spec.get("lines", []):
        ids.append(canvas.create_line(cx + x1 * h, cy + y1 * h, cx + x2 * h, cy + y2 * h,
                                      fill=color, width=width, capstyle="round",
                                      joinstyle="round"))
    for (x1, y1, x2, y2) in spec.get("rects", []):
        ids.append(canvas.create_rectangle(cx + x1 * h, cy + y1 * h, cx + x2 * h, cy + y2 * h,
                                           outline=color, width=width))
    for (x1, y1, x2, y2) in spec.get("ovals", []):
        ids.append(canvas.create_oval(cx + x1 * h, cy + y1 * h, cx + x2 * h, cy + y2 * h,
                                      outline=color, width=width))
    r = spec.get("rect")
    if r:
        x1, y1, x2, y2 = r
        ids.append(canvas.create_rectangle(cx + x1 * h, cy + y1 * h, cx + x2 * h, cy + y2 * h,
                                           fill=color, outline=color))
    for (x1, y1, x2, y2, start, extent) in spec.get("arcs", []):
        ids.append(canvas.create_arc(cx + x1 * h, cy + y1 * h, cx + x2 * h, cy + y2 * h,
                                     start=start, extent=extent, style="arc",
                                     outline=color, width=width))
    return ids


class PillButton(tk.Canvas):
    """Bouton étendu (icône + label), coins arrondis, hover animé.

    kind: "primary" (accent plein) | "ghost" (fond discret) | "bare" (texte seul)
    """

    def __init__(self, master, *, text="", icon=None, command=None, kind="primary",
                 height=38, radius=theme.RADIUS, bg=None, align="left",
                 pad_x=12, gap=8, **kw):
        self._bg = bg or master["bg"]
        self.text = text
        self.icon = icon
        self.command = command
        self.kind = kind
        self.align = align
        self.pad_x = pad_x
        self.gap = gap
        self._state = "normal"
        self._enabled = True

        f = tkfont.Font(font=theme.sans(10, bold=(kind == "primary")))
        label_w = f.measure(text) if text else 0
        icon_w = 17 if icon else 0
        need = pad_x * 2 + icon_w + (gap if (icon and text) else 0) + label_w
        w = max(int(kw.pop("min_width", 0)), need, height)
        super().__init__(master, width=w, height=height, bg=self._bg,
                         highlightthickness=0, bd=0, **kw)
        self._radius = radius
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _palette(self):
        dis = not self._enabled
        if self.kind == "primary":
            if dis:
                return theme.lighten(self._bg, 0.07), theme.lighten(self._bg, 0.2)
            if self._state == "pressed":
                return theme.ACCENT_DARK, theme.ACCENT_ON
            if self._state == "hover":
                return theme.lighten(theme.ACCENT, 0.14), theme.ACCENT_ON
            return theme.ACCENT, theme.ACCENT_ON
        if dis:
            return self._bg, theme.TEXT_FAINT
        if self._state in ("pressed", "hover"):
            return theme.lighten(self._bg, 0.10 if self._state == "hover" else 0.14), theme.TEXT
        return theme.lighten(self._bg, 0.05), theme.TEXT_SUB

    def _draw(self, _evt=None):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        fill, fg = self._palette()
        if fill != self._bg:
            round_rect(self, 0, 0, w, h, self._radius, fill=fill, outline=fill)
        x = self.pad_x if self.align == "left" else (w - self.pad_x - (17 if self.icon else 0))
        if self.icon:
            draw_icon(self, self.icon, x + 8, h / 2, 17, fg)
            x += 17 + (self.gap if self.text else 0)
        if self.text:
            anchor = "w" if self.align == "left" else "center"
            self.create_text(x, h / 2, text=self.text, fill=fg, anchor=anchor,
                             font=theme.sans(10, bold=(self.kind == "primary")))

    def set_text(self, text: str):
        self.text = text
        self._draw()

    def set_enabled(self, on: bool):
        self._enabled = on
        self.configure(cursor="hand2" if on else "arrow")
        self._draw()

    def _on_enter(self, _e):
        if not self._enabled:
            return
        self._state = "hover"
        self.configure(cursor="hand2")
        self._draw()

    def _on_leave(self, _e):
        self._state = "normal"
        self._draw()

    def _on_press(self, _e):
        if self._enabled:
            self._state = "pressed"
            self._draw()

    def _on_release(self, e):
        if not self._enabled:
            return
        inside = 0 <= e.x <= int(self["width"]) and 0 <= e.y <= int(self["height"])
        self._state = "hover" if inside else "normal"
        self._draw()
        if inside and self.command:
            self.command()


class Avatar(tk.Canvas):
    """Pastille ronde : initiale (utilisateur) ou halot accent (JIBI)."""

    def __init__(self, master, *, kind="bot", label="J", size=30, bg=None, **kw):
        bg = bg or (master["bg"] if hasattr(master, "__getitem__") else theme.BG)
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self.size = size
        self.kind = kind
        self.label = label
        self._redraw()

    def _redraw(self):
        self.delete("all")
        s = self.size
        if self.kind == "bot":
            # Halot : cercle plein accent désaturé + anneau.
            round_rect(self, 1, 1, s - 1, s - 1, s / 2,
                       fill=theme.ACCENT_SOFT, outline=theme.ACCENT_DARK)
            draw_icon(self, "brain", s / 2, s / 2, int(s * 0.58), theme.ACCENT, width=2)
        else:
            round_rect(self, 1, 1, s - 1, s - 1, s / 2,
                       fill=theme.ELEVATED, outline=theme.BORDER)
            self.create_text(s / 2, s / 2, text=self.label[:1].upper(),
                             fill=theme.TEXT_SUB, font=theme.sans(max(9, s // 3), bold=True))


class TypingDots(tk.Canvas):
    """Trois points qui respirent — indicateur "JIBI réfléchit"."""

    def __init__(self, master, *, size=26, bg=None, **kw):
        bg = bg or master["bg"]
        super().__init__(master, width=size + 14, height=size, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self.size = size
        self._phase = 0.0
        self._dots = []
        self._redraw()

    def _redraw(self):
        self.delete("all")
        self._dots = []
        r = max(2.0, self.size / 9.0)
        cy = self.size / 2
        for i in range(3):
            cx = 8 + i * (r * 2.8)
            self._dots.append(self.create_oval(cx - r, cy - r, cx + r, cy + r,
                                               fill=theme.ACCENT, outline=theme.ACCENT))

    def set_phase(self, t: float):
        """t dans [0,1] : décale la respiration de chaque point."""
        for i, d in enumerate(self._dots):
            p = (t + i * 0.18) % 1.0
            k = 0.5 - 0.5 * __import__("math").cos(2 * 3.141592653589793 * p)
            col = theme.mix(theme.ACCENT_DARK, theme.ACCENT, 0.35 + 0.65 * k)
            try:
                self.itemconfigure(d, fill=col, outline=col)
            except Exception:
                return
