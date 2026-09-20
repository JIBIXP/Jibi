"""
JIBI GUI Kit — Controls
=======================

Boutons et contrôles visuels.
"""

from __future__ import annotations

import tkinter as tk

from .rounded import draw_rounded_rect
from . import theme


def round_rect(canvas, x1, y1, x2, y2, radius=12, fill="", outline="", width=1, tags=None):
    return draw_rounded_rect(canvas, x1, y1, x2, y2, radius, fill, outline, width, tags)


# Glyphes utilisés par icon=... (IconButton / PillButton)
ICONS = {
    "panel_left": "☰",
    "settings": "⚙",
    "check": "✓",
    "close": "✕",
    "trash": "🗑",
    "plus": "＋",
    "mic": "🎙",
    "send": "➤",
    "chat": "💬",
    "flask": "🧪",
    "edit": "✎",
    "back": "‹",
}


# Palettes par "kind" pour les boutons
_KIND_STYLES = {
    "ghost": {
        "bg": None,  # utilise le bg fourni / celui du parent
        "hover": theme.COLORS["elevated"],
        "fg": theme.TEXT_SUB,
        "fg_hover": theme.TEXT,
    },
    "primary": {
        "bg": theme.ACCENT,
        "hover": theme.COLORS["accent_hover"],
        "fg": theme.ACCENT_ON,
        "fg_hover": theme.ACCENT_ON,
    },
    "danger": {
        "bg": theme.DANGER,
        "hover": theme.darken(theme.DANGER, 0.12),
        "fg": theme.TEXT,
        "fg_hover": theme.TEXT,
    },
    "soft": {
        "bg": theme.ACCENT_SOFT,
        "hover": theme.lighten(theme.ACCENT_SOFT, 0.08),
        "fg": theme.ACCENT,
        "fg_hover": theme.ACCENT,
    },
}


class _Tooltip:
    """Petite bulle d'aide affichée au survol prolongé."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        self._after_id = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._after_id = self.widget.after(550, self._show)

    def _show(self):
        if self.tip is not None or not self.text:
            return

        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self.tip,
            text=self.text,
            bg=theme.ELEVATED,
            fg=theme.TEXT,
            font=theme.sans(8),
            padx=8,
            pady=4,
            relief="flat",
        )
        label.pack()

    def _hide(self, _event=None):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


class RoundedFrame(tk.Canvas):
    """
    Petite carte à coins arrondis.

    Le contenu se place dans `.body` (un tk.Frame de fond `card_bg`),
    entouré de `pad` pixels de marge par rapport au bord arrondi.
    """

    def __init__(
        self,
        master,
        radius=12,
        card_bg=None,
        bg=None,
        pad=0,
        outline="",
        border_width=0,
        **kwargs,
    ):
        outer_bg = bg or (
            master.cget("bg") if hasattr(master, "cget") else theme.BG
        )

        super().__init__(
            master,
            highlightthickness=0,
            bd=0,
            bg=outer_bg,
            **kwargs,
        )

        self.radius = radius
        self.card_bg = card_bg or theme.COLORS["surface"]
        self.pad = pad
        self.outline = outline
        self.border_width = border_width

        self.body = tk.Frame(self, bg=self.card_bg)

        self._window = self.create_window(
            pad, pad, window=self.body, anchor="nw"
        )

        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, _event=None):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())

        self.delete("background")

        draw_rounded_rect(
            self,
            1,
            1,
            width - 1,
            height - 1,
            self.radius,
            fill=self.card_bg,
            outline=self.outline,
            width=self.border_width,
            tags="background",
        )

        self.tag_lower("background")

        inner_w = max(1, width - 2 * self.pad)
        inner_h = max(1, height - 2 * self.pad)

        self.coords(self._window, self.pad, self.pad)
        self.itemconfigure(self._window, width=inner_w, height=inner_h)

    def configure_body(self, **kwargs):
        self.body.configure(**kwargs)


class IconButton(tk.Button):
    """
    Bouton icône seul, avec variantes de style ("kind") et tooltip.

    Accepte soit icon="nom_connu" (voir ICONS), soit text="glyphe direct".
    """

    def __init__(
        self,
        master,
        icon=None,
        text=None,
        command=None,
        tooltip=None,
        kind="ghost",
        size=30,
        icon_size=13,
        **kwargs,
    ):
        style = _KIND_STYLES.get(kind, _KIND_STYLES["ghost"])

        parent_bg = kwargs.pop(
            "bg",
            master.cget("bg") if hasattr(master, "cget") else theme.BG,
        )

        base_bg = style["bg"] or parent_bg
        fg = kwargs.pop("fg", style["fg"])

        glyph = text if text is not None else ICONS.get(icon, icon or "•")

        options = {
            "text": glyph,
            "command": command,
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "bg": base_bg,
            "fg": fg,
            "activebackground": style["hover"],
            "activeforeground": style["fg_hover"],
            "cursor": "hand2",
            "font": ("Segoe UI Symbol", icon_size),
            "width": 2,
        }

        options.update(kwargs)

        super().__init__(master, **options)

        try:
            self.configure(
                height=1,
            )
        except Exception:
            pass

        self._normal_bg = base_bg
        self._hover_bg = style["hover"]
        self._normal_fg = fg
        self._hover_fg = style["fg_hover"]
        self.size = size

        self.bind("<Enter>", self._hover_on)
        self.bind("<Leave>", self._hover_off)

        self.tooltip = tooltip
        if tooltip:
            _Tooltip(self, tooltip)

    def _hover_on(self, _event=None):
        self.configure(bg=self._hover_bg, fg=self._hover_fg)

    def _hover_off(self, _event=None):
        self.configure(bg=self._normal_bg, fg=self._normal_fg)


class RoundedButton(tk.Button):
    """Bouton texte plein (utilisé en interne par gui_kit)."""

    def __init__(
        self,
        master,
        text="",
        command=None,
        width=None,
        height=None,
        bg=None,
        fg=None,
        hover_bg=None,
        active_bg=None,
        **kwargs,
    ):
        self.normal_bg = bg or theme.ACCENT
        self.hover_bg = hover_bg or theme.COLORS["accent_hover"]
        self.active_bg = active_bg or self.hover_bg

        options = {
            "text": text,
            "command": command,
            "bg": self.normal_bg,
            "fg": fg or theme.ACCENT_ON,
            "activebackground": self.active_bg,
            "activeforeground": fg or theme.ACCENT_ON,
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "font": theme.sans(10, bold=True),
            "padx": 16,
            "pady": 10,
        }

        if width is not None:
            options["width"] = width
        if height is not None:
            options["height"] = height

        options.update(kwargs)

        super().__init__(master, **options)

        self.bind("<Enter>", self._hover_on)
        self.bind("<Leave>", self._hover_off)

    def _hover_on(self, _event=None):
        self.configure(bg=self.hover_bg)

    def _hover_off(self, _event=None):
        self.configure(bg=self.normal_bg)


class PillButton(tk.Button):
    """
    Bouton pilule avec texte + icône optionnelle, coloré selon `kind`.
    """

    def __init__(
        self,
        master,
        text="",
        icon=None,
        kind="primary",
        command=None,
        height=32,
        **kwargs,
    ):
        style = _KIND_STYLES.get(kind, _KIND_STYLES["primary"])

        parent_bg = kwargs.pop(
            "bg",
            master.cget("bg") if hasattr(master, "cget") else theme.BG,
        )

        base_bg = style["bg"] or parent_bg
        fg = style["fg"]

        label = text
        if icon:
            glyph = ICONS.get(icon, icon)
            label = f"{glyph}  {text}" if text else glyph

        options = {
            "text": label,
            "command": command,
            "bg": base_bg,
            "fg": fg,
            "activebackground": style["hover"],
            "activeforeground": style["fg_hover"],
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "font": theme.sans(10, bold=True),
            "padx": 18,
            "pady": 8,
        }

        options.update(kwargs)

        super().__init__(master, **options)

        try:
            px_height = max(1, int(height) // 14)
            self.configure(height=px_height if px_height > 0 else 1)
        except Exception:
            pass

        self._normal_bg = base_bg
        self._hover_bg = style["hover"]

        self.bind("<Enter>", lambda _e: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._normal_bg))


class Divider(tk.Frame):
    """Ligne de séparation."""

    def __init__(self, master, color=None, height=1, **kwargs):
        super().__init__(
            master,
            height=height,
            bg=color or theme.BORDER,
            **kwargs,
        )

        self.pack_propagate(False)
        self.grid_propagate(False)