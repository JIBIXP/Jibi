# =========================================================
# gui_kit/sidebar.py — Barre latérale rétractable + redimensionnable
# =========================================================
# Trois rôles : navigation (Discussion / Propositions), historique
# des sessions, et pied de page (modèle + état).
#
# Rétractation : on anime la LARGEUR du contenu vers 0 puis on
# pack_forget le bloc. Animer place(x=...) produirait un glissement
# haché sous Tk (recalcul géométrique complet à chaque frame) ; la
# largeur, elle, reste fluide.
#
# Redimensionnement : poignée de 6 px sur le bord droit, curseur
# sb_h_double_arrow, bornes theme.SIDEBAR_MIN..MAX.
# =========================================================
from __future__ import annotations

import tkinter as tk

from . import theme
from .animation import Animation, animate as _animate
from .controls import Avatar, IconButton, PillButton, draw_icon, round_rect
from .scrollbar import ScrollArea, ThinScrollbar


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    """Conversion tolérante + bornage (le state ne fait aucune validation)."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


class _SessionRow(tk.Frame):
    """Une ligne d'historique : titre + bouton supprimer au survol."""

    def __init__(self, master, session, *, on_open, on_delete, bg=theme.PANEL):
        super().__init__(master, bg=bg)
        self.session = session
        self._on_open = on_open
        self._on_delete = on_delete
        self._hover = False
        self._active = False

        self.title = tk.Label(self, text=session.get("title", "Sans titre"),
                              bg=bg, fg=theme.TEXT_SUB, font=theme.sans(10),
                              anchor="w", cursor="hand2")
        self.title.pack(side="left", fill="x", expand=True, padx=(10, 2), pady=7)
        self.meta = tk.Label(self, text=session.get("meta", ""), bg=bg,
                             fg=theme.TEXT_FAINT, font=theme.sans(8),
                             anchor="w", cursor="hand2")
        self.meta.pack(side="left", padx=(0, 6))

        self.del_btn = tk.Canvas(self, width=24, height=24, bg=bg,
                                 highlightthickness=0, bd=0, cursor="hand2")
        draw_icon(self.del_btn, "trash", 12, 12, 13, theme.TEXT_FAINT, width=2)
        self.del_btn.pack(side="right", padx=(0, 6))

        for w in (self, self.title, self.meta, self.del_btn):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
        self.title.bind("<Button-1>", lambda _e: self._on_open(self.session))
        self.meta.bind("<Button-1>", lambda _e: self._on_open(self.session))
        self.del_btn.bind("<Button-1>", lambda _e: self._on_delete(self.session))
        self._paint()

    def set_active(self, on: bool):
        self._active = on
        self._paint()

    def _paint(self):
        if self._active:
            bg, fg = theme.ACCENT_SOFT, theme.TEXT
        elif self._hover:
            bg, fg = theme.ELEVATED, theme.TEXT
        else:
            bg, fg = theme.PANEL, theme.TEXT_SUB
        for w in (self, self.title, self.meta, self.del_btn):
            w.configure(bg=bg)
        self.title.configure(fg=fg)
        self.del_btn.delete("all")
        draw_icon(self.del_btn, "trash", 12, 12, 13,
                  theme.TEXT_FAINT if not self._hover else theme.DANGER, width=2)

    def _on_enter(self, _e):
        self._hover = True
        self._paint()

    def _on_leave(self, _e):
        self._hover = False
        self._paint()


class Sidebar(tk.Frame):
    NAV = (("chat", "Discussion", "chat"), ("proposals", "Propositions", "bulb"))

    def __init__(self, master, *, state,
                 on_new_chat=None, on_nav=None, on_open_session=None,
                 on_delete_session=None, on_collapse=None):
        # Le wrapper prend le fond principal : la poignée y "colle" visuellement.
        super().__init__(master, bg=theme.BG)
        self._anim: Animation | None = None
        self.state = state
        self._on_new_chat = on_new_chat
        self._on_nav = on_nav
        self._on_open_session = on_open_session
        self._on_delete_session = on_delete_session
        self._on_collapse = on_collapse

        self._target_w = _clamp_int(state.get("sidebar_width"),
                                    theme.SIDEBAR_DEFAULT,
                                    theme.SIDEBAR_MIN, theme.SIDEBAR_MAX)
        self._open = bool(state.get("sidebar_open", True))
        self._active_nav = "chat"
        self._selected_session = None
        self._dragging = False
        self._drag_x0 = 0
        self._drag_w0 = 0
        self._nav_buttons = {}
        self._counts = {"chat": 0, "proposals": 0}

        # ---------------- contenu ----------------
        self.content = tk.Frame(self, bg=theme.PANEL, width=self._target_w)
        self.content.pack(side="left", fill="y")
        self.content.pack_propagate(False)
        self._build()

        # ---------------- poignée de redimensionnement ----------------
        self.handle = tk.Canvas(self, width=theme.RESIZE_HANDLE_W, bg=theme.BG,
                                highlightthickness=0, bd=0, cursor="sb_h_double_arrow")
        self.handle.pack(side="left", fill="y")
        self._handle_line = None
        self.handle.bind("<Configure>", self._draw_handle)
        self.handle.bind("<Enter>", lambda _e: self._handle_hot(True))
        self.handle.bind("<Leave>", lambda _e: self._handle_hot(False))
        self.handle.bind("<Button-1>", self._drag_start)
        self.handle.bind("<B1-Motion>", self._drag_move)
        self.handle.bind("<ButtonRelease-1>", self._drag_end)
        self._draw_handle()

    # ================================================== construction
    def _build(self):
        c = self.content

        # ---- en-tête : logo + nom + bouton de repli
        head = tk.Frame(c, bg=theme.PANEL)
        head.pack(fill="x", padx=theme.SPACE_MD, pady=(theme.SPACE_LG, theme.SPACE_SM))

        self.logo = tk.Canvas(head, width=30, height=30, bg=theme.PANEL,
                              highlightthickness=0, bd=0)
        round_rect(self.logo, 1, 1, 29, 29, 9, fill=theme.ACCENT_SOFT, outline=theme.ACCENT_DARK)
        draw_icon(self.logo, "brain", 15, 15, 18, theme.ACCENT, width=2)
        self.logo.pack(side="left")

        tk.Label(head, text="JIBI", bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.serif(13, bold=True)).pack(side="left", padx=(10, 0))

        IconButton(head, icon="chevron_left", command=self.collapse, kind="ghost",
                   size=28, icon_size=15, tooltip="Masquer la barre latérale",
                   bg=theme.PANEL).pack(side="right")

        # ---- action primaire
        pad = tk.Frame(c, bg=theme.PANEL)
        pad.pack(fill="x", padx=theme.SPACE_MD, pady=(theme.SPACE_SM, theme.SPACE_MD))
        PillButton(pad, text="Nouvelle discussion", icon="plus", kind="primary",
                   height=38, command=self._fire_new_chat).pack(fill="x")

        # ---- navigation
        nav = tk.Frame(c, bg=theme.PANEL)
        nav.pack(fill="x", padx=theme.SPACE_SM, pady=(0, theme.SPACE_MD))
        for key, label, icon in self.NAV:
            row = _NavRow(nav, label, icon,
                          command=lambda k=key: self._fire_nav(k),
                          bg=theme.PANEL)
            row.pack(fill="x", pady=1)
            self._nav_buttons[key] = row

        # ---- historique
        sep = tk.Frame(c, bg=theme.PANEL)
        sep.pack(fill="x", padx=theme.SPACE_MD, pady=(theme.SPACE_SM, 4))
        tk.Label(sep, text="HISTORIQUE", bg=theme.PANEL, fg=theme.TEXT_FAINT,
                 font=theme.sans(8, bold=True)).pack(anchor="w")

        wrap = tk.Frame(c, bg=theme.PANEL)
        wrap.pack(fill="both", expand=True, padx=theme.SPACE_SM,
                  pady=(0, theme.SPACE_SM))
        self.sessions_area = ScrollArea(wrap, bg=theme.PANEL, auto_scroll=False)
        self.sessions_area.pack(fill="both", expand=True)
        self._session_rows = {}

        # ---- pied de page : modèle + état
        foot = tk.Frame(c, bg=theme.PANEL)
        foot.pack(fill="x", side="bottom", padx=theme.SPACE_MD,
                  pady=(theme.SPACE_SM, theme.SPACE_LG))
        tk.Frame(foot, bg=theme.BORDER_SOFT, height=1).pack(fill="x", pady=(0, 10))

        info = tk.Frame(foot, bg=theme.PANEL)
        info.pack(fill="x")
        self.dot = tk.Canvas(info, width=12, height=12, bg=theme.PANEL,
                             highlightthickness=0, bd=0)
        self.dot.pack(side="left", pady=2)
        self._set_dot(theme.TEXT_FAINT)

        txt = tk.Frame(info, bg=theme.PANEL)
        txt.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.model_lbl = tk.Label(txt, text="Modèle local", bg=theme.PANEL,
                                  fg=theme.TEXT_SUB, font=theme.sans(9, bold=True),
                                  anchor="w")
        self.model_lbl.pack(fill="x")
        self.status_lbl = tk.Label(txt, text="Connexion…", bg=theme.PANEL,
                                   fg=theme.TEXT_FAINT, font=theme.sans(8),
                                   anchor="w")
        self.status_lbl.pack(fill="x")

    def _cancel_anim(self):
        if self._anim is not None:
            self._anim.cancel()
            self._anim = None

    # ================================================== poignée
    def _draw_handle(self, _e=None):
        self.handle.delete("all")
        h = int(self.handle.winfo_height())
        x = theme.RESIZE_HANDLE_W / 2
        hot = self._dragging or getattr(self, "_handle_hover", False)
        col = theme.ACCENT if self._dragging else (theme.BORDER if hot else theme.BORDER_SOFT)
        self.handle.create_line(x, 0, x, h, fill=col, width=1)

    def _handle_hot(self, on: bool):
        self._handle_hover = on
        self._draw_handle()

    def _drag_start(self, e):
        self._dragging = True
        self._drag_x0 = e.x_root
        self._drag_w0 = self.width_current
        self._cancel_anim()
        self._draw_handle()

    def _drag_move(self, e):
        if not self._dragging:
            return
        w = self._drag_w0 + (e.x_root - self._drag_x0)
        self.set_width(w)

    def _drag_end(self, _e):
        if not self._dragging:
            return
        self._dragging = False
        self._target_w = self.width_current
        self.state.set(sidebar_width=self._target_w)
        self.state.save()
        self._draw_handle()

    # ================================================== largeur / repli
    @property
    def width_current(self) -> int:
        """Largeur visible : 0 quand la sidebar est repliée."""
        return self._content_width() if self._open else 0

    def _content_width(self) -> int:
        """Largeur réelle du contenu, même pendant/avant une transition."""
        return max(0, int(self.content.winfo_width()))

    @property
    def is_open(self) -> bool:
        return self._open

    def set_width(self, w: int, persist: bool = False):
        w = int(max(theme.SIDEBAR_MIN, min(theme.SIDEBAR_MAX, w)))
        self._target_w = w
        self.content.configure(width=w)
        if persist:
            self.state.set(sidebar_width=w)
            self.state.save()

    def expand(self, animate: bool = True):
        """Réaffiche la sidebar.

        On ne joue JAMAIS avec pack/pack_forget ici : l'ordre de pack
        détermine l'ordre d'allocation, et repacker ferait passer la sidebar
        à droite de la zone centrale. On pilote uniquement les largeurs.
        """
        if self._open:
            return
        self._open = True
        self.state.set(sidebar_open=True)
        self.state.save()
        self.handle.configure(width=theme.RESIZE_HANDLE_W)
        # Réancrage EXPLICITE avant la poignée : sans `before`, le contenu
        # repacké passerait derrière elle et inverserait les deux.
        self.content.pack(side="left", fill="y", before=self.handle)
        self._draw_handle()
        if animate:
            self.content.configure(width=0)
            self._anim = _animate(self.content, 0, self._target_w, theme.MOTION_MS,
                                 lambda v: self.content.configure(width=int(v)))
        else:
            self.content.configure(width=self._target_w)
        if self._on_collapse:
            self._on_collapse(True)

    def collapse(self, animate: bool = True):
        if not self._open:
            return
        self._open = False
        self.state.set(sidebar_open=False)
        self.state.save()
        if animate:
            # _content_width() et non width_current : _open vient de passer
            # à False, width_current vaudrait déjà 0 et l'animation serait nulle.
            self._anim = _animate(
                self.content, self._content_width(), 0, theme.MOTION_MS,
                lambda v: self.content.configure(width=int(v)),
                on_done=self._hide_handle)
        else:
            self._hide_handle()
        if self._on_collapse:
            self._on_collapse(False)

    def toggle(self, animate: bool = True):
        self.collapse(animate) if self._open else self.expand(animate)

    def _hide_handle(self):
        """Fin de repli : le contenu est démonté (Tk arrondit width=0 à 1 px)."""
        self.content.configure(width=0)
        self.content.pack_forget()
        self.handle.configure(width=0)

    @property
    def is_collapsed(self) -> bool:
        return not self._open

    # ================================================== contenu dynamique
    def set_nav_counts(self, *, chat: int | None = None, proposals: int | None = None):
        if chat is not None:
            self._counts["chat"] = chat
        if proposals is not None:
            self._counts["proposals"] = proposals
        for key, row in self._nav_buttons.items():
            row.set_count(self._counts.get(key, 0))

    def set_active_nav(self, view: str):
        self._active_nav = view
        for key, row in self._nav_buttons.items():
            row.set_active(key == view)

    def set_sessions(self, sessions):
        self.sessions_area.clear()
        self._session_rows = {}
        for s in sessions:
            row = _SessionRow(self.sessions_area.frame, s,
                              on_open=self._fire_open, on_delete=self._fire_delete)
            row.pack(fill="x", pady=1)
            self._session_rows[s.get("id")] = row
            row.set_active(s.get("id") == self._selected_session)
        if not sessions:
            tk.Label(self.sessions_area.frame,
                     text="Aucune conversation\npour l'instant.",
                     bg=theme.PANEL, fg=theme.TEXT_FAINT,
                     font=theme.sans(9), justify="left").pack(
                anchor="w", padx=10, pady=(10, 0))
        self.sessions_area.bind_wheel_recursive()

    def select_session(self, sid):
        self._selected_session = sid
        for k, row in self._session_rows.items():
            row.set_active(k == sid)

    def set_model(self, name: str, status: str = "", online: bool | None = None):
        if name:
            self.model_lbl.configure(text=name)
        if status:
            self.status_lbl.configure(text=status)
        if online is not None:
            self._set_dot(theme.ACCENT if online else theme.DANGER)

    def _set_dot(self, color: str):
        self.dot.delete("all")
        self.dot.create_oval(2, 2, 10, 10, fill=color, outline=color)

    # ================================================== callbacks
    def _fire_new_chat(self):
        if self._on_new_chat:
            self._on_new_chat()

    def _fire_nav(self, key):
        self.set_active_nav(key)
        if self._on_nav:
            self._on_nav(key)

    def _fire_open(self, session):
        self.select_session(session.get("id"))
        if self._on_open_session:
            self._on_open_session(session)

    def _fire_delete(self, session):
        if self._on_delete_session:
            self._on_delete_session(session)


class _NavRow(tk.Frame):
    """Entrée de navigation : icône + libellé + compteur."""

    def __init__(self, master, label, icon, *, command=None, bg=theme.PANEL):
        super().__init__(master, bg=bg, cursor="hand2")
        self._bg = bg
        self.command = command
        self._active = False
        self._hover = False

        self.cv = tk.Canvas(self, width=18, height=18, bg=bg,
                            highlightthickness=0, bd=0, cursor="hand2")
        self.cv.pack(side="left", padx=(10, 9), pady=8)
        self.lbl = tk.Label(self, text=label, bg=bg, fg=theme.TEXT_SUB,
                            font=theme.sans(10), anchor="w", cursor="hand2")
        self.lbl.pack(side="left", fill="x", expand=True, pady=8)
        self.count = tk.Label(self, text="", bg=bg, fg=theme.TEXT_FAINT,
                              font=theme.sans(8, bold=True), cursor="hand2")
        self.count.pack(side="right", padx=(0, 10))

        self._icon = icon
        for w in (self, self.cv, self.lbl, self.count):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)
        self._paint()

    def _paint(self):
        if self._active:
            bg, fg = theme.ACCENT_SOFT, theme.TEXT
        elif self._hover:
            bg, fg = theme.ELEVATED, theme.TEXT
        else:
            bg, fg = self._bg, theme.TEXT_SUB
        for w in (self, self.cv, self.lbl, self.count):
            w.configure(bg=bg)
        self.lbl.configure(fg=fg)
        self.count.configure(fg=theme.ACCENT if self._active else theme.TEXT_FAINT)
        self.cv.delete("all")
        draw_icon(self.cv, self._icon, 9, 9, 15,
                  theme.ACCENT if self._active else fg, width=2)

    def set_active(self, on: bool):
        self._active = on
        self._paint()

    def set_count(self, n: int):
        self.count.configure(text=str(n) if n else "")

    def _on_enter(self, _e):
        self._hover = True
        self._paint()

    def _on_leave(self, _e):
        self._hover = False
        self._paint()

    def _on_click(self, _e):
        if self.command:
            self.command()
