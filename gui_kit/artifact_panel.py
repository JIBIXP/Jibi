# =========================================================
# gui_kit/artifact_panel.py — Panneau latéral droit extensible
# =========================================================
# L'équivalent des "Artifacts" : code généré, fichier, note de
# mémoire… affiché en grand à droite de la conversation.
#
# Trois largeurs :
#   fermé        -> pack_forget (aucune place prise)
#   normal       -> largeur mémorisée, redimensionnable à la souris
#   plein écran  -> recouvre la conversation (bouton d'agrandissement)
#
# Même mécanique que la sidebar : on anime la largeur du contenu,
# pas la position — c'est ce qui reste fluide sous Tk.
# =========================================================
from __future__ import annotations

import tkinter as tk

from . import theme
from .animation import Animation, animate as _animate
from .controls import IconButton, draw_icon, round_rect
from .scrollbar import ThinScrollbar


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


KINDS = {
    "code":   ("code", "Code", theme.mono(10)),
    "doc":    ("doc", "Document", theme.sans(11)),
    "memory": ("brain", "Mémoire", theme.sans(11)),
    "tool":   ("settings", "Outil", theme.mono(10)),
}


class ArtifactPanel(tk.Frame):
    def __init__(self, master, *, state, on_close=None,
                 on_save=None):
        super().__init__(master, bg=theme.BG)
        self._anim: Animation | None = None
        self.state = state
        self.on_close = on_close
        self.on_save = on_save

        self._target_w = _clamp_int(state.get("panel_width"),
                                    theme.PANEL_DEFAULT,
                                    theme.PANEL_MIN, theme.PANEL_MAX)
        self._open = False
        self._fullscreen = False
        self._dragging = False
        self._kind = "code"
        self._content = ""

        # ---------------- poignée (bord GAUCHE du panneau) ----------------
        self.handle = tk.Canvas(self, width=theme.RESIZE_HANDLE_W, bg=theme.BG,
                                highlightthickness=0, bd=0, cursor="sb_h_double_arrow")
        self.handle.pack(side="left", fill="y")
        self.handle.bind("<Configure>", self._draw_handle)
        self.handle.bind("<Enter>", lambda _e: (setattr(self, "_hot", True), self._draw_handle())[1])
        self.handle.bind("<Leave>", lambda _e: (setattr(self, "_hot", False), self._draw_handle())[1])
        self.handle.bind("<Button-1>", self._drag_start)
        self.handle.bind("<B1-Motion>", self._drag_move)
        self.handle.bind("<ButtonRelease-1>", self._drag_end)
        self._hot = False

        # ---------------- contenu ----------------
        self.content = tk.Frame(self, bg=theme.PANEL, width=self._target_w)
        self.content.pack(side="left", fill="y")
        self.content.pack_propagate(False)
        self._build()
        if not self._open:
            # Fermé au départ : contenu démonté, poignée réduite.
            self.content.pack_forget()
            self.content.configure(width=0)
            self.handle.configure(width=0)
        self._draw_handle()

    # ================================================== construction
    def _build(self):
        c = self.content

        # ---- en-tête
        head = tk.Frame(c, bg=theme.PANEL)
        head.pack(fill="x", padx=theme.SPACE_MD, pady=(theme.SPACE_LG, theme.SPACE_SM))

        self.kind_icon = tk.Canvas(head, width=22, height=22, bg=theme.PANEL,
                                   highlightthickness=0, bd=0)
        self.kind_icon.pack(side="left", pady=2)

        titles = tk.Frame(head, bg=theme.PANEL)
        titles.pack(side="left", fill="x", expand=True, padx=(10, 6))
        self.title_lbl = tk.Label(titles, text="Panneau", bg=theme.PANEL, fg=theme.TEXT,
                                  font=theme.sans(11, bold=True), anchor="w")
        self.title_lbl.pack(fill="x")
        self.sub_lbl = tk.Label(titles, text="", bg=theme.PANEL, fg=theme.TEXT_FAINT,
                                font=theme.sans(8), anchor="w")
        self.sub_lbl.pack(fill="x")

        IconButton(head, icon="expand", kind="ghost", size=28, icon_size=15,
                   tooltip="Agrandir", command=self.toggle_fullscreen,
                   bg=theme.PANEL).pack(side="right", padx=(2, 0))
        IconButton(head, icon="close", kind="ghost", size=28, icon_size=15,
                   tooltip="Fermer le panneau", command=self.close,
                   bg=theme.PANEL).pack(side="right")

        tk.Frame(c, bg=theme.BORDER_SOFT, height=1).pack(fill="x")

        # ---- corps
        body = tk.Frame(c, bg=theme.PANEL)
        body.pack(fill="both", expand=True, padx=(theme.SPACE_MD, 0),
                  pady=(theme.SPACE_SM, 0))
        self.sb = ThinScrollbar(body, bg=theme.PANEL)
        self.sb.pack(side="right", fill="y")
        self.viewer = tk.Text(body, wrap="none", bg=theme.PANEL, fg=theme.TEXT,
                              font=theme.mono(10), bd=0, padx=10, pady=10,
                              insertbackground=theme.ACCENT, state="disabled",
                              highlightthickness=0, relief="flat", undo=False,
                              selectbackground=theme.ACCENT_SOFT,
                              selectforeground=theme.TEXT, tabs=("1c",),
                              spacing1=1, spacing3=1)
        self.viewer.pack(side="left", fill="both", expand=True)
        self.sb.attach(self.viewer)

        # ---- pied : stats + actions
        foot = tk.Frame(c, bg=theme.PANEL)
        foot.pack(fill="x", side="bottom", padx=theme.SPACE_MD,
                  pady=(theme.SPACE_SM, theme.SPACE_LG))
        tk.Frame(c, bg=theme.BORDER_SOFT, height=1).pack(fill="x", side="bottom")
        self.stats_lbl = tk.Label(foot, text="", bg=theme.PANEL, fg=theme.TEXT_FAINT,
                                  font=theme.sans(8))
        self.stats_lbl.pack(side="left")
        IconButton(foot, icon="copy", kind="ghost", size=28, icon_size=14,
                   tooltip="Copier le contenu", command=self._copy,
                   bg=theme.PANEL).pack(side="right")
        self.save_btn = IconButton(foot, icon="doc", kind="ghost", size=28, icon_size=14,
                                   tooltip="Enregistrer…", command=self._save,
                                   bg=theme.PANEL)
        self.save_btn.pack(side="right", padx=(0, 4))

    def _cancel_anim(self):
        if self._anim is not None:
            self._anim.cancel()
            self._anim = None

    # ================================================== poignée
    def _draw_handle(self, _e=None):
        self.handle.delete("all")
        h = int(self.handle.winfo_height())
        x = theme.RESIZE_HANDLE_W / 2
        col = theme.ACCENT if self._dragging else (theme.BORDER if self._hot else theme.BORDER_SOFT)
        self.handle.create_line(x, 0, x, h, fill=col, width=1)

    def _drag_start(self, e):
        self._dragging = True
        self._drag_x0 = e.x_root
        self._drag_w0 = self.width_current
        self._cancel_anim()
        self._draw_handle()

    def _drag_move(self, e):
        if not self._dragging:
            return
        # Le panneau est à droite : glisser vers la gauche l'élargit.
        self.set_width(self._drag_w0 - (e.x_root - self._drag_x0))

    def _drag_end(self, _e):
        if not self._dragging:
            return
        self._dragging = False
        self._target_w = self.width_current
        self.state.set(panel_width=self._target_w)
        self.state.save()
        self._draw_handle()

    # ================================================== largeur
    @property
    def width_current(self) -> int:
        """Largeur visible : 0 quand le panneau est fermé."""
        return self._content_width() if self._open else 0

    def _content_width(self) -> int:
        return max(0, int(self.content.winfo_width()))

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def is_fullscreen(self) -> bool:
        return self._fullscreen

    def set_width(self, w: int):
        w = int(max(theme.PANEL_MIN, min(theme.PANEL_MAX, w)))
        self._target_w = w
        self.content.configure(width=w)

    def _full_width(self) -> int:
        try:
            total = int(self.master.winfo_width())
        except Exception:
            total = 1200
        return int(max(theme.PANEL_MIN, min(theme.PANEL_MAX, total - 420)))

    # ================================================== ouverture / fermeture
    def open_artifact(self, kind: str = "code", title: str = "",
                      content: str = "", subtitle: str = "", animate: bool = True):
        self._kind = kind if kind in KINDS else "code"
        self._content = content or ""
        icon, label, font = KINDS[self._kind]

        self.title_lbl.configure(text=title or label)
        self.sub_lbl.configure(text=subtitle or label)
        self.kind_icon.delete("all")
        draw_icon(self.kind_icon, icon, 11, 11, 16, theme.ACCENT, width=2)

        self.viewer.configure(state="normal", font=font)
        self.viewer.delete("1.0", "end")
        self.viewer.insert("1.0", self._content)
        self.viewer.configure(state="disabled")

        lines = self._content.count("\n") + 1 if self._content else 0
        self.stats_lbl.configure(text=f"{lines} lignes · {len(self._content)} caractères")
        self.save_btn.set_enabled(self._kind in ("code", "tool", "doc"))

        if not self._open:
            self._open = True
            self.state.set(panel_open=True)
            self.state.save()
            self.handle.configure(width=theme.RESIZE_HANDLE_W)
            # La poignée est packée en premier : le contenu vient après, naturellement.
            self.content.pack(side="left", fill="y")
            self._draw_handle()
            target = self._full_width() if self._fullscreen else self._target_w
            if animate:
                self.content.configure(width=0)
                self._anim = _animate(self.content, 0, target, theme.MOTION_MS,
                                     lambda v: self.content.configure(width=int(v)))
            else:
                self.content.configure(width=target)

    def close(self, animate: bool = True):
        if not self._open:
            return
        self._open = False
        self._fullscreen = False
        self.state.set(panel_open=False)
        self.state.save()
        if animate:
            # voir Sidebar.collapse : width_current vaudrait déjà 0 ici.
            self._anim = _animate(
                self.content, self._content_width(), 0, theme.MOTION_MS,
                lambda v: self.content.configure(width=int(v)),
                on_done=self._hide_handle)
        else:
            self._hide_handle()
        if self.on_close:
            self.on_close()

    def _hide_handle(self):
        """Fin de fermeture : contenu démonté (Tk arrondit width=0 à 1 px)."""
        self.content.configure(width=0)
        self.content.pack_forget()
        self.handle.configure(width=0)

    def restore(self, animate: bool = False):
        """Réouvre le panneau à sa largeur mémorisée (reprise de session)."""
        if self._open:
            return
        self._open = True
        self.handle.configure(width=theme.RESIZE_HANDLE_W)
        self.content.pack(side="left", fill="y")
        self.content.configure(width=self._full_width() if self._fullscreen
                               else self._target_w)
        self._draw_handle()

    def toggle_fullscreen(self, animate: bool = True):
        if not self._open:
            return
        self._fullscreen = not self._fullscreen
        target = self._full_width() if self._fullscreen else self._target_w
        if animate:
            self._anim = _animate(self.content, self.width_current, target, theme.MOTION_MS,
                                 lambda v: self.content.configure(width=int(v)))
        else:
            self.set_width(target)

    # ================================================== actions
    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self._content)
        except Exception:
            pass

    def _save(self):
        if self.on_save:
            self.on_save(self._kind, self.title_lbl["text"], self._content)

    def get_content(self) -> str:
        return self._content
