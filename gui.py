"""
JIBI GUI v12 — CENTRE DE CONTRÔLE

- Interface Tkinter non bloquante
- Streaming LLM
- État réel Core / LLM
- Centre de propositions
- Diff + tests + risque
- Autorisation / rejet via AgentCore
- Annulation propre des requêtes
- Intégration AgentCore + orchestrateur + self_improvement
- Pièces jointes / artifacts
- Diagnostic technique de la GUI
"""

from __future__ import annotations

import inspect
import re
import threading
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue

import tkinter as tk
from tkinter import filedialog, messagebox

from gui_kit import theme
from gui_kit.state import UIState
from gui_kit.sidebar import Sidebar
from gui_kit.chat_view import ChatView
from gui_kit.input_bar import InputBar
from gui_kit.artifact_panel import ArtifactPanel
from gui_kit.status import StatusPill, STATES as _STATUS_STATES
from gui_kit.controls import IconButton, PillButton, RoundedFrame
from gui_kit.scrollbar import ScrollArea, ThinScrollbar


# ============================================================================
# IMPORTS CORE
# ============================================================================

CORE_IMPORT_ERROR = None
EVOLUTION_IMPORT_ERROR = None

try:
    from core.agent_core import AgentCore
except Exception as exc:
    CORE_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

    class AgentCore:
        """Fallback permettant à la GUI de rester ouverte pour diagnostic."""

        def traiter_message(self, msg, **kwargs):
            class Resultat:
                texte = (
                    "⚠️ JIBI n'a pas pu charger AgentCore.\n\n"
                    f"Erreur d'intégration : {CORE_IMPORT_ERROR}"
                )
                proposition_id = None
                action_requise = None
                metadata = {
                    "core_import_error": CORE_IMPORT_ERROR,
                    "mode": "degrade",
                }

            return Resultat()


# Le GUI utilise evolution uniquement comme façade de compatibilité.
try:
    from self_improvement import evolution
except Exception as exc:
    evolution = None
    EVOLUTION_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


EV_OK = evolution is not None


# ============================================================================
# ÉTATS GUI
# ============================================================================

_STATUS_STATES.setdefault(
    "confirmation",
    ("Confirmation requise", theme.ACCENT, True),
)

_STATUS_STATES.setdefault(
    "cancelled",
    ("Annulé", theme.TEXT_SUB, False),
)

_STATUS_STATES.setdefault(
    "done",
    ("Terminé", theme.ACCENT, False),
)


# ============================================================================
# CONFIGURATION GUI
# ============================================================================

STATE_PATH = Path(__file__).resolve().parent / "ui_state.json"

SUGGESTIONS = [
    "Explique-moi ce que tu sais faire",
    "Écris une fonction Python de tri",
    "Diagnostique mon projet",
    "Résume ma dernière recherche",
]


# ============================================================================
# LIGNE PROPOSITION
# ============================================================================

class _PropRow(tk.Frame):
    """Ligne graphique représentant une proposition."""

    def __init__(
        self,
        master,
        prop: dict,
        *,
        on_select,
        bg=theme.PANEL,
    ):
        super().__init__(
            master,
            bg=bg,
            cursor="hand2",
        )

        self.prop = prop
        self._on_select = on_select
        self._hover = False
        self._active = False
        self._bg = bg

        priorite = prop.get("priorite", "moyenne")

        emoji = {
            "critique": "🔴",
            "haute": "🟠",
            "moyenne": "🟡",
            "basse": "🟢",
        }.get(priorite, "🟡")

        nom_fichier = Path(
            prop.get("fichier", "?")
        ).name

        # ------------------------------------------------------------------
        # En-tête
        # ------------------------------------------------------------------

        self.head = tk.Frame(
            self,
            bg=bg,
        )
        self.head.pack(
            fill="x",
            padx=10,
            pady=(8, 2),
        )

        self.title_lbl = tk.Label(
            self.head,
            text=f"{emoji} {nom_fichier}",
            bg=bg,
            fg=theme.TEXT,
            font=theme.sans(10, bold=True),
            anchor="w",
        )
        self.title_lbl.pack(
            side="left",
            fill="x",
            expand=True,
        )

        self.crit_lbl = None

        if prop.get("fichier_critique"):
            self.crit_lbl = tk.Label(
                self.head,
                text="⚠️ CRITIQUE",
                bg=bg,
                fg=theme.DANGER,
                font=theme.sans(7, bold=True),
            )
            self.crit_lbl.pack(side="right")

        # ------------------------------------------------------------------
        # Problème
        # ------------------------------------------------------------------

        self.sub_lbl = tk.Label(
            self,
            text=(prop.get("probleme", "") or "")[:100],
            bg=bg,
            fg=theme.TEXT_FAINT,
            font=theme.sans(8),
            anchor="w",
            justify="left",
            wraplength=260,
        )
        self.sub_lbl.pack(
            fill="x",
            padx=10,
        )

        # ------------------------------------------------------------------
        # Statut
        # ------------------------------------------------------------------

        statut_map = {
            "en_attente": "En attente",
            "tests_echoues": "⚠️ Tests labo échoués",
            "testee": "Testée",
            "validee": "Validée",
            "rejetee": "Rejetée",
            "appliquee": "Appliquée",
        }

        statut = prop.get("statut", "?")

        self.statut_lbl = tk.Label(
            self,
            text=statut_map.get(statut, statut),
            bg=bg,
            fg=(
                theme.DANGER
                if statut == "tests_echoues"
                else theme.TEXT_DIM
            ),
            font=theme.sans(8),
            anchor="w",
        )
        self.statut_lbl.pack(
            fill="x",
            padx=10,
            pady=(0, 8),
        )

        self._painted = [
            self,
            self.head,
            self.title_lbl,
            self.sub_lbl,
            self.statut_lbl,
        ]

        if self.crit_lbl:
            self._painted.append(self.crit_lbl)

        for widget in self._painted:
            widget.bind(
                "<Enter>",
                self._on_enter,
            )
            widget.bind(
                "<Leave>",
                self._on_leave,
            )
            widget.bind(
                "<Button-1>",
                self._clicked,
            )

    def _clicked(self, _event):
        pid = self.prop.get("id")
        if pid:
            self._on_select(pid)

    def set_active(self, on: bool):
        self._active = bool(on)
        self._paint()

    def _on_enter(self, _event):
        self._hover = True
        self._paint()

    def _on_leave(self, _event):
        self._hover = False
        self._paint()

    def _paint(self):
        if self._active:
            bg = theme.ACCENT_SOFT
        elif self._hover:
            bg = theme.ELEVATED
        else:
            bg = self._bg

        for widget in self._painted:
            try:
                widget.configure(bg=bg)
            except Exception:
                pass


# ============================================================================
# GUI PRINCIPALE
# ============================================================================

class JibiGUI:

    def __init__(self, agent=None):
        self.etat = "ready"

        self.root = tk.Tk()
        self.root.title("JIBI • Aurora")

        # ------------------------------------------------------------------
        # État UI
        # ------------------------------------------------------------------

        self.state = UIState(STATE_PATH)

        self.root.geometry(
            self.state.get(
                "geometry",
                "1280x860+120+70",
            )
        )

        self.root.minsize(
            1000,
            680,
        )

        self.root.configure(
            bg=theme.BG
        )

        try:
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Core
        # ------------------------------------------------------------------

        self.agent = agent or AgentCore()

        # ------------------------------------------------------------------
        # Files / queues
        # ------------------------------------------------------------------

        self.q = Queue()
        self.q_prop = Queue()

        # ------------------------------------------------------------------
        # Requêtes
        # ------------------------------------------------------------------

        self.busy = False
        self.req_id = 0

        self.cancelled = False
        self.cancel_ev = None

        self._stream_buf = ""
        self._current_bot_row = None

        # ------------------------------------------------------------------
        # Sessions
        # ------------------------------------------------------------------

        self.sessions: list[dict] = []
        self.current_session_id = None

        # ------------------------------------------------------------------
        # Navigation
        # ------------------------------------------------------------------

        self._active_view = "chat"

        # ------------------------------------------------------------------
        # Propositions
        # ------------------------------------------------------------------

        self._selected_prop = None
        self._prop_rows: dict = {}

        # ------------------------------------------------------------------
        # Fermeture
        # ------------------------------------------------------------------

        self._closing = False

        # ------------------------------------------------------------------
        # Construction
        # ------------------------------------------------------------------

        self._build_ui()

        self._new_session(
            "Nouvelle discussion"
        )

        # ------------------------------------------------------------------
        # Diagnostic import
        # ------------------------------------------------------------------

        if CORE_IMPORT_ERROR:
            self.root.after(
                300,
                self._show_core_import_error,
            )

        if EVOLUTION_IMPORT_ERROR:
            self.root.after(
                500,
                self._show_evolution_import_error,
            )

        # ------------------------------------------------------------------
        # Status
        # ------------------------------------------------------------------

        self.root.after(
            200,
            self._refresh_model_status,
        )

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self._on_close,
        )

    # ======================================================================
    # UI
    # ======================================================================

    def _build_ui(self):
        root_frame = tk.Frame(
            self.root,
            bg=theme.BG,
        )
        root_frame.pack(
            fill="both",
            expand=True,
        )

        self._build_topbar(
            root_frame
        )

        tk.Frame(
            root_frame,
            bg=theme.BORDER_SOFT,
            height=1,
        ).pack(fill="x")

        body = tk.Frame(
            root_frame,
            bg=theme.BG,
        )
        body.pack(
            fill="both",
            expand=True,
        )

        # ------------------------------------------------------------------
        # Sidebar
        # ------------------------------------------------------------------

        self.sidebar = Sidebar(
            body,
            state=self.state,
            on_new_chat=self._new_chat_clicked,
            on_nav=self._on_nav,
            on_open_session=self._on_open_session,
            on_delete_session=self._on_delete_session,
        )

        self.sidebar.pack(
            side="left",
            fill="y",
        )

        if self.state.get("sidebar_collapsed", False):
            self.sidebar.set_collapsed(True)

        # ------------------------------------------------------------------
        # Artifact panel
        # ------------------------------------------------------------------

        self.artifact_panel = ArtifactPanel(
            body,
            state=self.state,
            on_save=self._save_artifact,
            on_close=lambda: self.input_bar.focus_input(),
        )

        # Ne pas pack par défaut - sera affiché à la demande
        # self.artifact_panel.pack(
        #     side="right",
        #     fill="y",
        # )

        # ------------------------------------------------------------------
        # Centre
        # ------------------------------------------------------------------

        self.center = tk.Frame(
            body,
            bg=theme.BG,
        )

        self.center.pack(
            side="left",
            fill="both",
            expand=True,
        )

        self.center.grid_rowconfigure(
            0,
            weight=1,
        )

        self.center.grid_columnconfigure(
            0,
            weight=1,
        )

        # ------------------------------------------------------------------
        # Chat
        # ------------------------------------------------------------------

        self.chat_view = ChatView(
            self.center,
            on_expand_code=self._open_code_panel,
            on_suggestion=self._on_suggestion,
            bg=theme.BG,
        )

        # ------------------------------------------------------------------
        # Propositions
        # ------------------------------------------------------------------

        self.proposals_view = self._build_proposals_view(
            self.center
        )

        # ------------------------------------------------------------------
        # Input
        # ------------------------------------------------------------------

        self.input_bar = InputBar(
            self.center,
            on_send=self.send,
            on_attach=self._on_attach,
            on_mic=self._on_mic,
            on_stop=self.cancel,
            bg=theme.BG,
        )

        self.show_view(
            "chat"
        )

    def _build_topbar(self, parent):
        top = tk.Frame(
            parent,
            bg=theme.BG,
            height=56,
        )

        top.pack(
            fill="x",
            side="top",
        )

        top.pack_propagate(False)

        left = tk.Frame(
            top,
            bg=theme.BG,
        )

        left.pack(
            side="left",
            padx=theme.SPACE_LG,
        )

        IconButton(
            left,
            icon="panel_left",
            kind="ghost",
            size=32,
            icon_size=16,
            tooltip="Basculer la barre latérale",
            command=self._toggle_sidebar,
            bg=theme.BG,
        ).pack(
            side="left",
            pady=12,
        )

        tk.Label(
            left,
            text="JIBI",
            bg=theme.BG,
            fg=theme.TEXT,
            font=theme.serif(
                15,
                bold=True,
            ),
        ).pack(
            side="left",
            padx=(10, 6),
        )

        badge = RoundedFrame(
            left,
            radius=8,
            card_bg=theme.ACCENT_SOFT,
            bg=theme.BG,
            pad=0,
        )

        badge.pack(
            side="left"
        )

        tk.Label(
            badge.body,
            text="AURORA",
            bg=theme.ACCENT_SOFT,
            fg=theme.ACCENT,
            font=theme.sans(
                8,
                bold=True,
            ),
        ).pack(
            padx=8,
            pady=3,
        )

        right = tk.Frame(
            top,
            bg=theme.BG,
        )

        right.pack(
            side="right",
            padx=theme.SPACE_LG,
        )

        self.status_pill = StatusPill(
            right,
            state="ready",
            bg=theme.BG,
        )

        self.status_pill.pack(
            side="right",
            pady=12,
        )

        self.integration_lbl = tk.Label(
            right,
            text=(
                "● CORE OK"
                if CORE_IMPORT_ERROR is None
                else "● CORE ERREUR"
            ),
            bg=theme.BG,
            fg=(
                theme.ACCENT
                if CORE_IMPORT_ERROR is None
                else theme.DANGER
            ),
            font=theme.sans(
                8,
                bold=True,
            ),
        )

        self.integration_lbl.pack(
            side="right",
            padx=(0, 12),
            pady=18,
        )

        IconButton(
            right,
            icon="settings",
            kind="ghost",
            size=32,
            icon_size=16,
            tooltip="Paramètres",
            command=self._show_settings_stub,
            bg=theme.BG,
        ).pack(
            side="right",
            padx=(0, 8),
            pady=12,
        )

    def _build_proposals_view(self, master):
        view = tk.Frame(
            master,
            bg=theme.BG,
        )

        view.grid_rowconfigure(
            0,
            weight=1,
        )

        view.grid_columnconfigure(
            1,
            weight=1,
        )

        # ------------------------------------------------------------------
        # Liste
        # ------------------------------------------------------------------

        left = tk.Frame(
            view,
            bg=theme.PANEL,
            width=300,
        )

        left.grid(
            row=0,
            column=0,
            sticky="ns",
        )

        left.grid_propagate(False)

        tk.Label(
            left,
            text="PROPOSITIONS",
            bg=theme.PANEL,
            fg=theme.TEXT_FAINT,
            font=theme.sans(
                9,
                bold=True,
            ),
        ).pack(
            anchor="w",
            padx=theme.SPACE_MD,
            pady=(
                theme.SPACE_LG,
                theme.SPACE_SM,
            ),
        )

        self.props_area = ScrollArea(
            left,
            bg=theme.PANEL,
            auto_scroll=False,
        )

        self.props_area.pack(
            fill="both",
            expand=True,
            padx=theme.SPACE_SM,
            pady=(0, theme.SPACE_SM),
        )

        # ------------------------------------------------------------------
        # Diff
        # ------------------------------------------------------------------

        right = tk.Frame(
            view,
            bg=theme.BG,
        )

        right.grid(
            row=0,
            column=1,
            sticky="nsew",
        )

        right.grid_rowconfigure(
            1,
            weight=1,
        )

        right.grid_columnconfigure(
            0,
            weight=1,
        )

        head = tk.Frame(
            right,
            bg=theme.BG,
        )

        head.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=theme.SPACE_LG,
            pady=(
                theme.SPACE_LG,
                theme.SPACE_SM,
            ),
        )

        self.diff_title = tk.Label(
            head,
            text="Sélectionnez une proposition",
            bg=theme.BG,
            fg=theme.TEXT,
            font=theme.serif(
                15,
                bold=True,
            ),
        )

        self.diff_title.pack(
            side="left"
        )

        btns = tk.Frame(
            head,
            bg=theme.BG,
        )

        btns.pack(
            side="right"
        )

        PillButton(
            btns,
            text="Autoriser",
            icon="check",
            kind="primary",
            height=32,
            command=self._auth_selected,
        ).pack(
            side="left",
            padx=(0, 6),
        )

        PillButton(
            btns,
            text="Rejeter",
            icon="close",
            kind="ghost",
            height=32,
            command=self._reject_selected,
        ).pack(
            side="left"
        )

        diff_wrap = tk.Frame(
            right,
            bg=theme.PANEL,
        )

        diff_wrap.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=theme.SPACE_LG,
            pady=(0, theme.SPACE_LG),
        )

        diff_wrap.grid_rowconfigure(
            0,
            weight=1,
        )

        diff_wrap.grid_columnconfigure(
            0,
            weight=1,
        )

        scrollbar = ThinScrollbar(
            diff_wrap,
            bg=theme.PANEL,
        )

        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.diff_text = tk.Text(
            diff_wrap,
            wrap="none",
            bg=theme.PANEL,
            fg=theme.TEXT,
            font=theme.mono(10),
            bd=0,
            padx=14,
            pady=14,
            highlightthickness=0,
            relief="flat",
            state="disabled",
            insertbackground=theme.ACCENT,
        )

        self.diff_text.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar.attach(
            self.diff_text
        )

        self.diff_text.tag_configure(
            "add",
            foreground=theme.ACCENT,
        )

        self.diff_text.tag_configure(
            "del",
            foreground=theme.DANGER,
        )

        self.diff_text.tag_configure(
            "hunk",
            foreground=theme.ACCENT,
            font=theme.mono(
                10,
                bold=True,
            ),
        )

        return view

    # ======================================================================
    # NAVIGATION
    # ======================================================================

    def show_view(self, name: str):
        if name not in {"chat", "proposals"}:
            name = "chat"

        self._active_view = name

        if name == "chat":
            self.proposals_view.grid_forget()

            self.chat_view.grid(
                row=0,
                column=0,
                sticky="nsew",
            )

            self.input_bar.grid(
                row=1,
                column=0,
                sticky="ew",
            )

        else:
            self.chat_view.grid_forget()
            self.input_bar.grid_forget()

            self.proposals_view.grid(
                row=0,
                column=0,
                rowspan=2,
                sticky="nsew",
            )

            self.refresh_props()

        self.sidebar.set_active_nav(
            name
        )

    def _toggle_sidebar(self):
        self.sidebar.toggle()

        self.state.set(
            "sidebar_collapsed",
            self.sidebar.collapsed,
        )
        self.state.save()

    def _on_nav(self, key: str):
        self.show_view(
            key
        )

    # ======================================================================
    # SESSIONS
    # ======================================================================

    def _new_session(self, title: str):
        sid = datetime.now().strftime(
            "%Y%m%d_%H%M%S%f"
        )

        self.sessions.insert(
            0,
            {
                "id": sid,
                "title": title,
                "meta": datetime.now().strftime("%H:%M"),
            },
        )

        self.current_session_id = sid

        self.sidebar.set_sessions(
            self.sessions,
            active_session_id=sid
        )

        # Pas besoin de rappeler select_session ici car set_sessions
        # active déjà la bonne session via active_session_id

        self.chat_view.clear()

        self.chat_view.set_suggestions(
            SUGGESTIONS
        )

        self.sidebar.set_nav_counts(
            chat=0
        )

        self.show_view(
            "chat"
        )

    def _new_chat_clicked(self):
        if self.busy:
            return

        self._new_session(
            "Nouvelle discussion"
        )

    def _on_open_session(self, session_id: str):
        """
        Callback appelé par la sidebar quand l'utilisateur clique sur une session.
        NE PAS rappeler sidebar.select_session ici - on est déjà dedans !
        """
        if not session_id:
            return

        # Met à jour l'état interne uniquement
        self.current_session_id = session_id
        
        # TODO: Charger les messages de cette session
        # self.chat_view.clear()
        # messages = self._load_session_messages(session_id)
        # for msg in messages:
        #     if msg['role'] == 'user':
        #         self.chat_view.add_user(msg['content'])
        #     else:
        #         self.chat_view.add_bot(msg['content'])

    def _on_delete_session(self, session_id: str):
        """Callback when a session is deleted from sidebar."""
        self.sessions = [
            s
            for s in self.sessions
            if s.get("id") != session_id
        ]

        self.sidebar.set_sessions(
            self.sessions,
            active_session_id=self.current_session_id if self.sessions else None
        )

        if self.current_session_id == session_id:
            if self.sessions:
                self.current_session_id = self.sessions[0].get("id")
                # La sidebar va automatiquement activer la première session
            else:
                self._new_session(
                    "Nouvelle discussion"
                )

    # ======================================================================
    # STATUS
    # ======================================================================

    def set_status(self, state: str):
        self.etat = state

        try:
            self.status_pill.set_state(
                state
            )
        except Exception:
            pass

    # ======================================================================
    # CORE / LLM STATUS
    # ======================================================================

    def _refresh_model_status(self):
        if self._closing:
            return

        def worker():
            try:
                from core import cerveau

                ok = bool(
                    cerveau.disponible()
                )

                name = getattr(
                    cerveau,
                    "MODEL",
                    "LLM",
                )

            except Exception:
                ok = False
                name = "Mode simulé"

            if self._closing:
                return

            def apply_status():
                if self._closing:
                    return

                detail = (
                    "Opérationnel"
                    if ok
                    else "Hors ligne"
                )

                if CORE_IMPORT_ERROR and not ok:
                    detail = "Erreur d'intégration"

                try:
                    self.sidebar.set_model(
                        name,
                        detail,
                        online=ok,
                    )
                except Exception:
                    pass

                if hasattr(
                    self,
                    "integration_lbl",
                ):
                    self.integration_lbl.configure(
                        text=(
                            "● CORE OK"
                            if CORE_IMPORT_ERROR is None
                            else "● CORE ERREUR"
                        ),
                        fg=(
                            theme.ACCENT
                            if CORE_IMPORT_ERROR is None
                            else theme.DANGER
                        ),
                    )

            try:
                self.root.after(
                    0,
                    apply_status,
                )
            except Exception:
                pass

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

        if not self._closing:
            self.root.after(
                15000,
                self._refresh_model_status,
            )

    # ======================================================================
    # VALIDATION PROPOSITION
    # ======================================================================

    def _get_active_proposition_ids(self) -> list[str]:
        if not EV_OK or evolution is None:
            return []

        try:
            propositions = (
                evolution.lister("en_attente")
                + evolution.lister("tests_echoues")
            )

            return [
                p.get("id")
                for p in propositions
                if p.get("id")
            ]

        except Exception:
            return []

    def _validate_input(
        self,
        text: str,
    ) -> tuple[bool, str]:

        # --------------------------------------------------------------
        # Confirmation
        # --------------------------------------------------------------

        match = re.match(
            r"^(?:confirme|oui)\s+(\S+)\s*$",
            text,
            re.I,
        )

        if match:
            pid = match.group(1)

            if pid not in self._get_active_proposition_ids():
                return (
                    False,
                    f"Proposition '{pid}' introuvable.",
                )

            return True, ""

        # --------------------------------------------------------------
        # Autorisation
        # --------------------------------------------------------------

        match = re.match(
            r"^j(?:[''])?autorise\s+(\S+)\s*$",
            text,
            re.I,
        )

        if match:
            pid = match.group(1)

            active = self._get_active_proposition_ids()

            if not active:
                return (
                    False,
                    "Aucune proposition en attente.",
                )

            if pid not in active:
                return (
                    False,
                    f"Proposition '{pid}' introuvable.\n\n"
                    f"Propositions actives : "
                    f"{', '.join(active[:5])}",
                )

        # --------------------------------------------------------------
        # Rejet
        # --------------------------------------------------------------

        match = re.match(
            r"^(?:je\s+)?rejet(?:te|e|er)\s+(\S+)\s*$",
            text,
            re.I,
        )

        if match:
            pid = match.group(1)

            active = self._get_active_proposition_ids()

            if pid not in active:
                return (
                    False,
                    f"Proposition '{pid}' introuvable.\n\n"
                    f"Propositions actives : "
                    f"{', '.join(active[:5])}",
                )

        return True, ""

    # ======================================================================
    # ENVOI
    # ======================================================================

    def send(self, text: str):
        if self.busy or self._closing:
            return

        msg = (text or "").strip()

        if not msg:
            return

        ok, warning = self._validate_input(
            msg
        )

        if not ok:
            self.chat_view.add_bot(
                f"⚠️ {warning}",
                meta=datetime.now().strftime("%H:%M"),
            )
            return

        self.busy = True
        self.cancelled = False

        self.req_id += 1
        request_id = self.req_id

        self.cancel_ev = threading.Event()

        self._stream_buf = ""
        self._current_bot_row = None

        self.set_status(
            "thinking"
        )

        self.input_bar.set_busy(
            True
        )

        self.chat_view.add_user(
            msg,
            meta=datetime.now().strftime("%H:%M"),
        )

        self.chat_view.show_typing()

        def on_chunk(chunk: str):
            if (
                self.cancelled
                or request_id != self.req_id
                or self._closing
            ):
                return

            def update_ui():
                if (
                    self.cancelled
                    or request_id != self.req_id
                    or self._closing
                ):
                    return

                if self.etat != "busy":
                    self.set_status(
                        "busy"
                    )

                    self.chat_view.hide_typing()

                    self._current_bot_row = (
                        self.chat_view.add_bot(
                            "",
                            meta=datetime.now().strftime("%H:%M"),
                        )
                    )

                if (
                    not chunk
                    or self._current_bot_row is None
                ):
                    return

                # Certains moteurs renvoient le buffer complet,
                # d'autres uniquement le delta.
                if (
                    self._stream_buf
                    and chunk.startswith(self._stream_buf)
                ):
                    delta = chunk[
                        len(self._stream_buf):
                    ]

                    self._stream_buf = chunk

                else:
                    delta = chunk

                    self._stream_buf += chunk

                if delta:
                    self._current_bot_row.append(
                        delta
                    )

                    self.chat_view.scroll_to_bottom()

            try:
                self.root.after(
                    0,
                    update_ui,
                )
            except Exception:
                pass

        def worker():
            try:
                signature = inspect.signature(
                    self.agent.traiter_message
                )

                kwargs = {}

                if "on_chunk" in signature.parameters:
                    kwargs["on_chunk"] = on_chunk

                if "cancel_event" in signature.parameters:
                    kwargs["cancel_event"] = self.cancel_ev

                result = self.agent.traiter_message(
                    msg,
                    **kwargs,
                )

                self.q.put(
                    (
                        request_id,
                        "ok",
                        result,
                    )
                )

            except Exception as exc:
                self.q.put(
                    (
                        request_id,
                        "err",
                        f"{type(exc).__name__}: {exc}",
                    )
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

        self.root.after(
            80,
            self.poll,
        )

    # ======================================================================
    # POLL RÉSULTAT
    # ======================================================================

    def poll(self):
        if self._closing:
            return

        try:
            while True:
                request_id, kind, payload = (
                    self.q.get_nowait()
                )

                if request_id != self.req_id:
                    continue

                break

        except Empty:
            if (
                self.busy
                and not self.cancelled
                and not self._closing
            ):
                self.root.after(
                    80,
                    self.poll,
                )

            return

        if self.cancelled:
            return

        self.chat_view.hide_typing()

        if kind == "ok":
            self._handle_result(
                payload
            )
        else:
            self._handle_error(
                payload
            )

        self.busy = False
        self.cancel_ev = None

        self.input_bar.set_busy(
            False
        )

        self.input_bar.focus_input()

    def _handle_result(self, result):
        txt = getattr(
            result,
            "texte",
            str(result),
        )

        metadata = getattr(
            result,
            "metadata",
            {},
        )

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        # --------------------------------------------------------------
        # Sécurité
        # --------------------------------------------------------------

        validation = metadata.get(
            "validation_securite",
            {},
        )

        if isinstance(
            validation,
            dict,
        ):
            if validation.get("niveau") == "attention":
                risques = validation.get(
                    "risques",
                    [],
                )

                if risques:
                    txt += (
                        "\n\n⚠️ **Avertissements sécurité :**\n"
                        + "\n".join(
                            f"• {r}"
                            for r in risques[:3]
                        )
                    )

        # --------------------------------------------------------------
        # Affichage
        # --------------------------------------------------------------

        if self._current_bot_row is not None:
            self._current_bot_row.replace_streamed(
                txt
            )
        else:
            self._current_bot_row = (
                self.chat_view.add_bot(
                    txt,
                    meta=datetime.now().strftime("%H:%M"),
                )
            )

        self.chat_view.scroll_to_bottom()

        # --------------------------------------------------------------
        # Proposition créée
        # --------------------------------------------------------------

        proposition_id = getattr(
            result,
            "proposition_id",
            None,
        )

        if proposition_id:
            self.root.after(
                100,
                self.refresh_props,
            )

        # --------------------------------------------------------------
        # Action requise
        # --------------------------------------------------------------

        action = getattr(
            result,
            "action_requise",
            None,
        )

        if not isinstance(
            action,
            dict,
        ):
            action = {}

        action_type = action.get(
            "type"
        )

        action_id = action.get(
            "id"
        )

        if (
            action_type == "confirmation"
            and action_id
        ):
            self.input_bar.set_text(
                f"CONFIRME {action_id}"
            )

            self.set_status(
                "confirmation"
            )

        else:
            self.set_status(
                "done"
            )

            self.root.after(
                1200,
                lambda: (
                    self.set_status("ready")
                    if not self.busy
                    else None
                ),
            )

    def _handle_error(self, error):
        message = f"❌ Erreur : {error}"

        if self._current_bot_row is not None:
            self._current_bot_row.replace_streamed(
                message
            )
        else:
            self.chat_view.add_bot(
                message,
                meta=datetime.now().strftime("%H:%M"),
            )

        self.chat_view.scroll_to_bottom()

        self.set_status(
            "error"
        )

        self.root.after(
            2000,
            lambda: (
                self.set_status("ready")
                if not self.busy
                else None
            ),
        )

    # ======================================================================
    # ANNULATION
    # ======================================================================

    def cancel(self):
        if (
            not self.busy
            or self._closing
        ):
            return

        self.cancelled = True

        # Invalide immédiatement toute ancienne réponse.
        self.req_id += 1

        if self.cancel_ev:
            try:
                self.cancel_ev.set()
            except Exception:
                pass

        self.chat_view.hide_typing()

        final = (
            self._stream_buf
            + "\n\n(Annulé.)"
            if self._stream_buf
            else "(Annulé.)"
        )

        if self._current_bot_row is not None:
            self._current_bot_row.replace_streamed(
                final
            )
        else:
            self.chat_view.add_bot(
                final,
                meta=datetime.now().strftime("%H:%M"),
            )

        self.chat_view.scroll_to_bottom()

        self._current_bot_row = None

        self.busy = False
        self.cancel_ev = None

        self.input_bar.set_busy(
            False
        )

        self.set_status(
            "cancelled"
        )

        self.root.after(
            1500,
            lambda: (
                self.set_status("ready")
                if not self.busy
                else None
            ),
        )

        self.input_bar.focus_input()

    # ======================================================================
    # PROPOSITIONS
    # ======================================================================

    def refresh_props(self):
        if self._closing:
            return

        if not EV_OK or evolution is None:
            self.props_area.clear()

            tk.Label(
                self.props_area.frame,
                text=(
                    "Module self_improvement indisponible."
                ),
                bg=theme.PANEL,
                fg=theme.TEXT_FAINT,
                font=theme.sans(9),
                wraplength=260,
                justify="left",
            ).pack(
                anchor="w",
                padx=10,
                pady=10,
            )

            self.sidebar.set_nav_counts(
                proposals=0
            )

            return

        try:
            propositions = (
                evolution.lister("en_attente")
                + evolution.lister("tests_echoues")
            )

        except Exception:
            propositions = []

        self.props_area.clear()

        self._prop_rows = {}

        if not propositions:
            tk.Label(
                self.props_area.frame,
                text="Aucune proposition en attente.",
                bg=theme.PANEL,
                fg=theme.TEXT_FAINT,
                font=theme.sans(9),
            ).pack(
                anchor="w",
                padx=10,
                pady=10,
            )

        else:
            for proposition in propositions:
                row = _PropRow(
                    self.props_area.frame,
                    proposition,
                    on_select=self._select_prop,
                )

                row.pack(
                    fill="x",
                    pady=1,
                )

                pid = proposition.get(
                    "id"
                )

                if pid:
                    self._prop_rows[pid] = row

        try:
            self.props_area.bind_wheel_recursive()
        except Exception:
            pass

        self.sidebar.set_nav_counts(
            proposals=len(propositions)
        )

        if (
            self._selected_prop
            and self._selected_prop in self._prop_rows
        ):
            self._prop_rows[
                self._selected_prop
            ].set_active(True)

        elif self._selected_prop:
            self._selected_prop = None
            self._clear_diff()

    def _select_prop(self, pid: str):
        if not pid:
            return

        self._selected_prop = pid

        for key, row in self._prop_rows.items():
            row.set_active(
                key == pid
            )

        if not EV_OK or evolution is None:
            self._clear_diff()
            return

        try:
            proposition = evolution.charger(
                pid
            )
        except Exception:
            proposition = None

        if not proposition:
            self._clear_diff()
            return

        critique = (
            "  ⚠️ CRITIQUE"
            if proposition.get("fichier_critique")
            else ""
        )

        self.diff_title.configure(
            text=(
                f"{proposition.get('fichier', '?')}"
                f"{critique}"
            )
        )

        self._render_diff(
            proposition
        )

    def _clear_diff(self):
        self.diff_title.configure(
            text="Sélectionnez une proposition"
        )

        self.diff_text.configure(
            state="normal"
        )

        self.diff_text.delete(
            "1.0",
            "end",
        )

        self.diff_text.configure(
            state="disabled"
        )

    def _render_diff(self, proposition: dict):
        self.diff_text.configure(
            state="normal"
        )

        self.diff_text.delete(
            "1.0",
            "end",
        )

        diff = proposition.get(
            "diff"
        ) or (
            "(Aucun diff disponible — nouveau fichier)"
        )

        for line in diff.splitlines():

            if line.startswith(
                ("+++", "---", "@@")
            ):
                self.diff_text.insert(
                    "end",
                    line + "\n",
                    "hunk",
                )

            elif line.startswith("+"):
                self.diff_text.insert(
                    "end",
                    line + "\n",
                    "add",
                )

            elif line.startswith("-"):
                self.diff_text.insert(
                    "end",
                    line + "\n",
                    "del",
                )

            else:
                self.diff_text.insert(
                    "end",
                    line + "\n",
                )

        tests = proposition.get(
            "tests",
            {},
        )

        if isinstance(
            tests,
            dict,
        ):
            details = tests.get(
                "details"
            )

            if details:
                self.diff_text.insert(
                    "end",
                    "\n" + "\n".join(
                        str(x)
                        for x in details
                    ) + "\n",
                    "hunk",
                )

        self.diff_text.configure(
            state="disabled"
        )

    # ======================================================================
    # AUTORISATION / REJET
    # ======================================================================

    def _auth_selected(self):
        self._run_prop_action(
            "autoriser"
        )

    def _reject_selected(self):
        self._run_prop_action(
            "rejeter"
        )

    def _run_prop_action(self, action: str):
        pid = self._selected_prop

        if (
            not pid
            or self.busy
            or self._closing
        ):
            return

        if action == "autoriser":
            command = f"J'AUTORISE {pid}"
        else:
            command = f"Rejette {pid}"

        self.busy = True

        self.set_status(
            "thinking"
        )

        def worker():
            try:
                result = self.agent.traiter_message(
                    command
                )

                self.q_prop.put(
                    (
                        "ok",
                        result,
                    )
                )

            except Exception as exc:
                self.q_prop.put(
                    (
                        "err",
                        f"{type(exc).__name__}: {exc}",
                    )
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

        self.root.after(
            80,
            self._poll_prop_action,
        )

    def _poll_prop_action(self):
        if self._closing:
            return

        try:
            kind, payload = (
                self.q_prop.get_nowait()
            )

        except Empty:
            if self.busy and not self._closing:
                self.root.after(
                    80,
                    self._poll_prop_action,
                )
            return

        self.busy = False

        if kind == "ok":
            texte = getattr(
                payload,
                "texte",
                str(payload),
            )

            ok = texte.strip().startswith(
                "✅"
            )

            self.set_status(
                "done" if ok else "error"
            )

        else:
            texte = (
                f"❌ Erreur : {payload}"
            )

            self.set_status(
                "error"
            )

        self.chat_view.add_bot(
            texte,
            meta=datetime.now().strftime("%H:%M"),
        )

        self.root.after(
            1500,
            lambda: (
                self.set_status("ready")
                if not self.busy
                else None
            ),
        )

        self.refresh_props()

    # ======================================================================
    # PIÈCES JOINTES
    # ======================================================================

    def _on_attach(self):
        path = filedialog.askopenfilename(
            title="Joindre un fichier"
        )

        if not path:
            return

        file_path = Path(path)

        try:
            if (
                file_path.suffix.lower()
                in {
                    ".py",
                    ".txt",
                    ".md",
                    ".json",
                    ".csv",
                    ".log",
                }
                and file_path.stat().st_size < 200_000
            ):
                content = file_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                self.artifact_panel.open_artifact(
                    kind="doc",
                    title=file_path.name,
                    content=content,
                    subtitle="Document joint",
                )

            self.input_bar.insert_text(
                f"[Fichier joint : {file_path.name}]\n"
            )

        except Exception as exc:
            self.chat_view.add_bot(
                f"⚠️ Impossible de lire le fichier : {exc}",
                meta=datetime.now().strftime("%H:%M"),
            )

    # ======================================================================
    # MICRO
    # ======================================================================

    def _on_mic(self, listening: bool):
        # Le moteur vocal sera branché séparément.
        self.input_bar.set_listening(
            False
        )

        if listening:
            self.chat_view.add_bot(
                (
                    "🎙️ La dictée vocale n'est pas encore "
                    "configurée sur cette installation."
                ),
                meta=datetime.now().strftime("%H:%M"),
            )

    # ======================================================================
    # CODE / ARTIFACT
    # ======================================================================

    def _open_code_panel(
        self,
        lang: str,
        code: str,
    ):
        self.artifact_panel.open_artifact(
            kind="code",
            title=(
                f"Code ({lang})"
                if lang
                else "Code"
            ),
            content=code,
            subtitle=(
                lang.upper()
                if lang
                else ""
            ),
        )

    def _on_suggestion(self, text: str):
        self.send(
            text
        )

    def _save_artifact(
        self,
        kind: str,
        title: str,
        content: str,
    ):
        extensions = {
            "code": ".py",
            "tool": ".py",
            "doc": ".md",
        }

        extension = extensions.get(
            kind,
            ".txt",
        )

        name = (
            title or "artifact"
        ).strip() or "artifact"

        if not name.lower().endswith(
            extension
        ):
            name += extension

        path = filedialog.asksaveasfilename(
            title="Enregistrer",
            initialfile=name,
            defaultextension=extension,
        )

        if not path:
            return

        try:
            Path(path).write_text(
                content or "",
                encoding="utf-8",
            )

        except Exception as exc:
            self.chat_view.add_bot(
                f"⚠️ Échec de l'enregistrement : {exc}",
                meta=datetime.now().strftime("%H:%M"),
            )

    # ======================================================================
    # DIAGNOSTIC
    # ======================================================================

    def diagnostic_ui(self) -> dict:
        """Retourne l'état technique actuel de la GUI."""

        try:
            from core import cerveau

            llm_ok = bool(
                cerveau.disponible()
            )

            model = getattr(
                cerveau,
                "MODEL",
                "?",
            )

        except Exception as exc:
            llm_ok = False

            model = (
                f"ERREUR: "
                f"{type(exc).__name__}: {exc}"
            )

        return {
            "gui": "ok",
            "core_import": CORE_IMPORT_ERROR is None,
            "core_error": CORE_IMPORT_ERROR,
            "evolution": EV_OK,
            "evolution_error": EVOLUTION_IMPORT_ERROR,
            "llm": llm_ok,
            "model": model,
            "busy": self.busy,
            "cancelled": self.cancelled,
            "view": self._active_view,
            "proposition_selectionnee": self._selected_prop,
            "sessions": len(self.sessions),
        }

    # ======================================================================
    # ERREURS D'INTÉGRATION
    # ======================================================================

    def _show_core_import_error(self):
        if self._closing:
            return

        self.chat_view.add_bot(
            (
                "⚠️ **Intégration JIBI à vérifier**\n\n"
                f"{CORE_IMPORT_ERROR}\n\n"
                "La GUI reste ouverte afin de permettre "
                "le diagnostic."
            ),
            meta=datetime.now().strftime("%H:%M"),
        )

    def _show_evolution_import_error(self):
        if self._closing:
            return

        self.chat_view.add_bot(
            (
                "⚠️ **Self-improvement indisponible**\n\n"
                f"{EVOLUTION_IMPORT_ERROR}\n\n"
                "Le chat reste disponible."
            ),
            meta=datetime.now().strftime("%H:%M"),
        )

    # ======================================================================
    # PARAMÈTRES
    # ======================================================================

    def _show_settings_stub(self):
        messagebox.showinfo(
            "Paramètres",
            (
                "Les paramètres avancés arrivent dans une "
                "prochaine version.\n\n"
                "En attendant, JIBI se configure via le fichier "
                ".env à la racine du projet : modèle LLM "
                "(JIBI_LLM_MODEL), sécurité et "
                "auto-amélioration (core/config.py)."
            ),
        )

    # ======================================================================
    # FERMETURE
    # ======================================================================

    def _on_close(self):
        if self._closing:
            return

        self._closing = True

        try:
            if self.cancel_ev:
                self.cancel_ev.set()
        except Exception:
            pass

        try:
            self.state.set(
                geometry=self.root.geometry()
            )

            self.state.save()

        except Exception:
            pass

        try:
            self.root.destroy()
        except Exception:
            pass


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    gui = JibiGUI()
    gui.root.mainloop()