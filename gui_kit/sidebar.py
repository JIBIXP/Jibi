"""
JIBI GUI Kit — Sidebar
======================

Design premium : barre d'accent latérale pour nav active,
hover élégant, modèle visible dans le footer.
"""

from __future__ import annotations

import tkinter as tk

from .controls import Divider, IconButton, RoundedButton
from .theme import COLORS, FONT, LAYOUT, ACCENT, ACCENT_SOFT, TEXT, TEXT_DIM, TEXT_FAINT, PANEL, ELEVATED, BORDER_SOFT


class Sidebar(tk.Frame):
    """
    Sidebar JIBI.

    Compatible avec gui.py v12.

    Callbacks supportés :
        on_new
        on_chat
        on_proposals
        on_quit
        on_session

    API gui.py v12 :
        on_new_chat
        on_nav
        on_open_session
        on_delete_session
        state
    """

    def __init__(
        self,
        master,
        on_new=None,
        on_chat=None,
        on_proposals=None,
        on_quit=None,
        on_session=None,
        on_new_chat=None,
        on_nav=None,
        on_open_session=None,
        on_delete_session=None,
        state=None,
        **kwargs,
    ):
        # État GUI transmis par gui.py
        self.state = state

        # État interne
        self.collapsed = False
        self.is_open = True
        self.sessions = {}
        self._active_nav = "chat"

        # Compatibilité callbacks
        self.on_new = on_new or on_new_chat
        self.on_chat = on_chat
        self.on_proposals = on_proposals
        self.on_quit = on_quit

        self.on_session = on_session or on_open_session

        self.on_nav = on_nav
        self.on_open_session = on_open_session
        self.on_delete_session = on_delete_session

        # IMPORTANT :
        # state et les callbacks ne doivent PAS être envoyés à tk.Frame.
        super().__init__(
            master,
            bg=COLORS["sidebar"],
            width=LAYOUT["sidebar_width"],
            **kwargs,
        )

        self.pack_propagate(False)

        self._build()

    # ------------------------------------------------------------------
    # CONSTRUCTION
    # ------------------------------------------------------------------

    def _build(self):
        """Construit l'interface de la sidebar."""

        # Header
        header = tk.Frame(
            self,
            bg=COLORS["sidebar"],
        )
        header.pack(
            fill="x",
            padx=24,
            pady=(24, 12),
        )

        self.title = tk.Label(
            header,
            text="JIBI",
            bg=COLORS["sidebar"],
            fg=COLORS["text_inverse"],
            font=("Segoe UI", 24, "bold"),
        )
        self.title.pack(anchor="w")

        self.subtitle = tk.Label(
            header,
            text="local · outils · labo",
            bg=COLORS["sidebar"],
            fg=TEXT_FAINT,
            font=FONT["small"],
        )
        self.subtitle.pack(
            anchor="w",
            pady=(2, 0),
        )

        # Nouvelle discussion
        self.new_button = RoundedButton(
            self,
            text="＋  Nouvelle discussion",
            command=self._new,
            bg=COLORS["accent"],
        )
        self.new_button.pack(
            fill="x",
            padx=20,
            pady=(16, 16),
        )

        Divider(
            self,
            color=COLORS["border_dark"],
        ).pack(
            fill="x",
            padx=20,
        )

        # Navigation
        self.nav = tk.Frame(
            self,
            bg=COLORS["sidebar"],
        )
        self.nav.pack(
            fill="x",
            padx=0,
            pady=10,
        )

        self.chat_button, self.chat_indicator = self._nav_button(
            "💬  Assistant Chat",
            self._chat,
            nav_key="chat",
        )

        self.proposals_button, self.proposals_indicator = self._nav_button(
            "🧠  Auto-Amélioration",
            self._proposals,
            nav_key="proposals",
        )

        self.tools_button, self.tools_indicator = self._nav_button(
            "🛠️  Catalogue Outils",
            self._tools,
            nav_key="tools",
        )

        self.diag_button, self.diag_indicator = self._nav_button(
            "📊  Diagnostics",
            self._diag,
            nav_key="diag",
        )

        # Discussions
        tk.Label(
            self,
            text="DISCUSSIONS",
            bg=COLORS["sidebar"],
            fg=TEXT_FAINT,
            font=FONT["small_bold"],
        ).pack(
            anchor="w",
            padx=18,
            pady=(12, 6),
        )

        self.session_frame = tk.Frame(
            self,
            bg=COLORS["sidebar"],
        )
        self.session_frame.pack(
            fill="both",
            expand=True,
            padx=8,
        )

        # Footer avec modèle
        footer = tk.Frame(
            self,
            bg=COLORS["sidebar"],
        )
        footer.pack(
            fill="x",
            padx=10,
            pady=(4, 0),
        )

        # Indicateur modèle
        self._model_frame = tk.Frame(footer, bg=COLORS["sidebar"])
        self._model_frame.pack(fill="x", padx=8, pady=(4, 4))

        self._model_lbl = tk.Label(
            self._model_frame,
            text="● Modèle : chargement…",
            bg=COLORS["sidebar"],
            fg=TEXT_FAINT,
            font=FONT["small"],
            anchor="w",
        )
        self._model_lbl.pack(side="left")

        Divider(
            footer,
            color=BORDER_SOFT,
        ).pack(fill="x", padx=4, pady=(4, 0))

        self.quit_button, _ = self._nav_button(
            "🚪  Quitter",
            self._quit,
            parent=footer,
            nav_key=None,
        )

        # Active chat par défaut
        self._update_nav_visual("chat")

    # ------------------------------------------------------------------
    # NAVIGATION — Boutons avec accent indicator
    # ------------------------------------------------------------------

    def _nav_button(
        self,
        text,
        command,
        parent=None,
        nav_key=None,
    ):
        parent = parent or self.nav

        row = tk.Frame(parent, bg=COLORS["sidebar"])
        row.pack(fill="x", pady=1)

        # Barre d'accent colorée à gauche
        indicator = tk.Frame(row, bg=COLORS["sidebar"], width=3)
        indicator.pack(side="left", fill="y")
        indicator.pack_propagate(False)

        button = tk.Button(
            row,
            text=text,
            command=command,
            anchor="w",
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=COLORS["sidebar"],
            fg="#d8d5df",
            activebackground=COLORS["sidebar_alt"],
            activeforeground=COLORS["text_inverse"],
            font=FONT["body"],
            padx=12,
            pady=9,
            cursor="hand2",
        )

        button.pack(
            side="left",
            fill="x",
            expand=True,
        )

        # Hover effects
        def _on_enter(_e, btn=button, row_=row, ind=indicator, key=nav_key):
            if self._active_nav != key:
                btn.configure(bg=COLORS["sidebar_alt"], fg=TEXT)
                row_.configure(bg=COLORS["sidebar_alt"])

        def _on_leave(_e, btn=button, row_=row, ind=indicator, key=nav_key):
            if self._active_nav != key:
                btn.configure(bg=COLORS["sidebar"], fg="#d8d5df")
                row_.configure(bg=COLORS["sidebar"])

        button.bind("<Enter>", _on_enter)
        button.bind("<Leave>", _on_leave)
        row.bind("<Enter>", _on_enter)
        row.bind("<Leave>", _on_leave)

        return button, indicator

    def _new(self):
        if self.on_new:
            self.on_new()

    def _chat(self):
        if self.on_chat:
            self.on_chat()
        elif self.on_nav:
            self.on_nav("chat")

    def _proposals(self):
        if self.on_proposals:
            self.on_proposals()
        elif self.on_nav:
            self.on_nav("proposals")

    def _tools(self):
        if self.on_nav:
            self.on_nav("tools")

    def _diag(self):
        if self.on_nav:
            self.on_nav("diag")

    def _quit(self):
        if self.on_quit:
            self.on_quit()

    # ------------------------------------------------------------------
    # FIX BUG 3 : set_active_nav met à jour TOUS les boutons
    # ------------------------------------------------------------------

    def _update_nav_visual(self, view_name: str):
        """Met à jour visuellement les boutons de navigation."""

        nav_map = {
            "chat": (self.chat_button, self.chat_indicator),
            "proposals": (self.proposals_button, self.proposals_indicator),
            "tools": (self.tools_button, self.tools_indicator),
            "diag": (self.diag_button, self.diag_indicator),
        }

        for key, (btn, ind) in nav_map.items():
            if key == view_name:
                # Actif : accent cyan
                btn.configure(
                    bg=ELEVATED,
                    fg=ACCENT,
                    font=("Segoe UI", 12, "bold"),
                )
                ind.configure(bg=ACCENT)
            else:
                # Inactif
                btn.configure(
                    bg=COLORS["sidebar"],
                    fg="#d8d5df",
                    font=FONT["body"],
                )
                ind.configure(bg=COLORS["sidebar"])

    def set_active_nav(self, view_name: str):
        """Active le bouton de navigation correspondant (API publique)."""
        self._active_nav = view_name
        self._update_nav_visual(view_name)

    # ------------------------------------------------------------------
    # SESSIONS
    # ------------------------------------------------------------------

    def set_sessions(
        self,
        sessions,
        active_session_id=None,
    ):
        """
        Remplace complètement la liste des discussions.
        """

        self.clear_sessions()

        if not sessions:
            return

        for session in sessions:

            session_id = None
            title = "Discussion"

            # Tuple / liste
            if isinstance(session, (tuple, list)):
                if len(session) >= 2:
                    session_id = session[0]
                    title = session[1]

            # Dictionnaire
            elif isinstance(session, dict):
                session_id = (
                    session.get("id")
                    or session.get("session_id")
                )

                title = (
                    session.get("title")
                    or session.get("name")
                    or "Discussion"
                )

            # Objet avec attributs
            else:
                session_id = getattr(
                    session,
                    "id",
                    None,
                )

                if session_id is None:
                    session_id = getattr(
                        session,
                        "session_id",
                        None,
                    )

                title = (
                    getattr(
                        session,
                        "title",
                        None,
                    )
                    or getattr(
                        session,
                        "name",
                        None,
                    )
                    or "Discussion"
                )

            if session_id is None:
                continue

            self.add_session(
                session_id,
                str(title),
                active=(
                    session_id == active_session_id
                ),
            )

    def add_session(
        self,
        session_id,
        title,
        active=False,
    ):
        """Ajoute une discussion."""

        if session_id in self.sessions:
            self.update_session(
                session_id,
                title,
                active,
            )
            return

        row = tk.Frame(
            self.session_frame,
            bg=(
                COLORS["sidebar_alt"]
                if active
                else COLORS["sidebar"]
            ),
        )

        row.pack(
            fill="x",
            pady=1,
        )

        button = tk.Button(
            row,
            text=title,
            anchor="w",
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=row["bg"],
            fg=COLORS["text_inverse"],
            activebackground=COLORS["sidebar_alt"],
            activeforeground=COLORS["text_inverse"],
            font=FONT["small"],
            padx=12,
            pady=8,
            cursor="hand2",
            command=lambda sid=session_id:
                self._select_session(sid),
        )

        button.pack(
            side="left",
            fill="x",
            expand=True,
        )

        delete_button = IconButton(
            row,
            text="✕",
            kind="ghost",
            size=22,
            icon_size=10,
            tooltip="Supprimer la discussion",
            bg=row["bg"],
            command=lambda sid=session_id:
                self._delete_session(sid),
        )

        delete_button.pack(
            side="right",
            padx=(0, 6),
        )

        self.sessions[session_id] = {
            "row": row,
            "button": button,
            "delete": delete_button,
        }

    def update_session(
        self,
        session_id,
        title,
        active=False,
    ):
        """Met à jour une discussion."""

        entry = self.sessions.get(
            session_id
        )

        if not entry:
            self.add_session(
                session_id,
                title,
                active,
            )
            return

        bg = (
            COLORS["sidebar_alt"]
            if active
            else COLORS["sidebar"]
        )

        entry["row"].configure(bg=bg)
        entry["button"].configure(text=title, bg=bg)
        entry["delete"].configure(bg=bg)

    def remove_session(
        self,
        session_id,
    ):
        """Supprime une discussion."""

        entry = self.sessions.pop(
            session_id,
            None,
        )

        if entry:
            entry["row"].destroy()

    def clear_sessions(self):
        """Supprime toutes les discussions."""

        for entry in self.sessions.values():
            entry["row"].destroy()

        self.sessions.clear()

    def set_active(
        self,
        session_id,
    ):
        """Active visuellement une discussion."""

        for sid, entry in self.sessions.items():
            bg = (
                COLORS["sidebar_alt"]
                if sid == session_id
                else COLORS["sidebar"]
            )
            entry["row"].configure(bg=bg)
            entry["button"].configure(bg=bg)
            entry["delete"].configure(bg=bg)

    def select_session(self, session_id):
        """
        Méthode publique pour sélectionner une discussion.
        Appelle _select_session en interne.
        """
        self._select_session(session_id)

    def _select_session(
        self,
        session_id,
    ):
        """Sélectionne une discussion."""

        self.set_active(session_id)

        if self.on_session:
            self.on_session(session_id)

        elif self.on_open_session:
            self.on_open_session(session_id)

    def _delete_session(
        self,
        session_id,
    ):
        """Supprime une discussion via le bouton ✕ de la ligne."""

        if self.on_delete_session:
            self.on_delete_session(session_id)

    # ------------------------------------------------------------------
    # NAV COUNTS
    # ------------------------------------------------------------------

    def set_nav_counts(self, chat=None, proposals=None):
        """
        Met à jour les compteurs de navigation.
        Peut afficher un badge numérique sur les boutons nav.
        """
        pass

    def set_model(self, name, detail, online=True):
        """
        Affiche les informations du modèle dans le footer de la sidebar.
        """
        try:
            color = "#00e676" if online else "#ff9100"
            dot = "●"
            display = f"{dot} {name}"
            if detail:
                display += f"  —  {detail}"
            self._model_lbl.configure(
                text=display,
                fg=color,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # OUVERTURE / FERMETURE
    # ------------------------------------------------------------------

    def set_collapsed(
        self,
        collapsed: bool,
    ):
        """Réduit ou ouvre la sidebar."""

        self.collapsed = bool(collapsed)
        self.is_open = not self.collapsed

        if self.collapsed:

            self.configure(
                width=LAYOUT["sidebar_collapsed"]
            )

            self.subtitle.pack_forget()

        else:

            self.configure(
                width=LAYOUT["sidebar_width"]
            )

            if not self.subtitle.winfo_manager():
                self.subtitle.pack(
                    anchor="w",
                    pady=(2, 0),
                )

    def toggle(self):
        """Inverse l'état ouvert/fermé."""

        self.set_collapsed(
            not self.is_open
        )

    def open(self):
        """Ouvre la sidebar."""

        self.set_collapsed(False)

    def close(self):
        """Ferme la sidebar."""

        self.set_collapsed(True)