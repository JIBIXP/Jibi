# =========================================================
# JIBI GUI v10 — Intégration complète de gui_kit
# =========================================================
# Remplace l'ancienne interface ttk (JibiGUI v9, "Warm Studio") par
# un assemblage des composants de gui_kit/ : sidebar rétractable,
# zone de conversation à bulles markdown, panneau d'artefact,
# barre de saisie en pilule, indicateur de statut animé.
#
# La logique métier (routage, streaming, annulation, propositions,
# diagnostic) est reprise de la v9 et adaptée aux nouveaux widgets :
#   * chaque message est maintenant SON PROPRE widget Text
#     (gui_kit.chat_view.MessageRow) au lieu d'un unique tampon
#     partagé -> le bug de duplication/collage lors du streaming
#     (déjà corrigé "à la main" en v9) devient structurellement
#     impossible : append() n'ajoute que le delta, et la bascule
#     finale passe par un set_text() complet, pas par des
#     delete/insert répétés au même index.
#   * le statut affiché passe par gui_kit.status.StatusPill : on
#     étend son vocabulaire d'états (voir _EXTRA_STATES ci-dessous)
#     plutôt que de modifier le fichier partagé gui_kit/status.py.
# =========================================================
from __future__ import annotations

import sys
import threading
import inspect
from pathlib import Path
from queue import Queue, Empty
from datetime import datetime

import tkinter as tk
from tkinter import filedialog

from gui_kit import theme
from gui_kit.state import UIState
from gui_kit.sidebar import Sidebar
from gui_kit.chat_view import ChatView
from gui_kit.input_bar import InputBar
from gui_kit.artifact_panel import ArtifactPanel
from gui_kit.status import StatusPill, STATES as _STATUS_STATES
from gui_kit.controls import IconButton, PillButton, RoundedFrame
from gui_kit.scrollbar import ScrollArea, ThinScrollbar

try:
    from core.agent_core import AgentCore
    from core import evolution
    EV_OK = True
except Exception:
    class AgentCore:
        def traiter_message(self, msg, **kwargs):
            class R:
                texte = ("[MODE SIMULÉ] Le module core/agent_core.py est introuvable.\n"
                          "L'interface fonctionne, mais aucun agent n'est branché.")
                proposition_id = None
                action_requise = None
            return R()
    evolution = None
    EV_OK = False

# ---------------------------------------------------------
# gui_kit.status.STATES ne connaît que ready/thinking/listening/
# busy/offline/error. On y ajoute les états propres au routeur
# JIBI (confirmation, annulé, terminé) plutôt que de toucher au
# fichier partagé — ce sont des libellés d'affichage, pas de la
# logique, donc l'extension ici est sans risque pour les autres
# écrans qui utilisent gui_kit.status.
# ---------------------------------------------------------
_STATUS_STATES.setdefault("confirmation", ("Confirmation requise", theme.ACCENT, True))
_STATUS_STATES.setdefault("cancelled", ("Annulé", theme.TEXT_SUB, False))
_STATUS_STATES.setdefault("done", ("Terminé", theme.ACCENT, False))

STATE_PATH = Path(__file__).resolve().parent / "ui_state.json"

SUGGESTIONS = [
    "Explique-moi ce que tu sais faire",
    "Écris une fonction Python de tri",
    "Diagnostique mon projet",
    "Résume ma dernière recherche",
]


class JibiGUI:
    def __init__(self, agent=None):
        self.etat = "ready"
        self.root = tk.Tk()
        self.root.title("JIBI • Aurora")

        self.state = UIState(STATE_PATH)
        self.root.geometry(self.state.get("geometry", "1280x860+120+70"))
        self.root.minsize(1000, 680)
        self.root.configure(bg=theme.BG)
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.agent = agent or AgentCore()
        self.q = Queue()
        self.busy = False
        self.req_id = 0
        self.cancelled = False
        self.cancel_ev = None
        self._stream_buf = ""
        self._current_bot_row = None

        self.sessions: list[dict] = []
        self.current_session_id = None
        self._active_view = "chat"
        self._selected_prop = None
        self._prop_rows: dict = {}

        self._build_ui()
        self._new_session("Nouvelle discussion")
        self.root.after(200, self._refresh_model_status)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================== construction
    def _build_ui(self):
        root_frame = tk.Frame(self.root, bg=theme.BG)
        root_frame.pack(fill="both", expand=True)

        self._build_topbar(root_frame)
        tk.Frame(root_frame, bg=theme.BORDER_SOFT, height=1).pack(fill="x")

        body = tk.Frame(root_frame, bg=theme.BG)
        body.pack(fill="both", expand=True)

        self.sidebar = Sidebar(
            body, state=self.state,
            on_new_chat=self._new_chat_clicked,
            on_nav=self._on_nav,
            on_open_session=self._on_open_session,
            on_delete_session=self._on_delete_session,
        )
        self.sidebar.pack(side="left", fill="y")
        # Contournement : Sidebar.__init__ ne masque pas son contenu quand
        # l'état persisté est "fermé" (seul ArtifactPanel le fait). On force
        # le repli visuel une fois la fenêtre construite.
        if not self.sidebar.is_open:
            self.sidebar._open = True
            self.sidebar.collapse(animate=False)

        self.artifact_panel = ArtifactPanel(
            body, state=self.state, on_save=self._save_artifact,
            on_close=lambda: self.input_bar.focus_input(),
        )
        self.artifact_panel.pack(side="right", fill="y")
        if self.state.get("panel_open"):
            self.artifact_panel.restore()

        self.center = tk.Frame(body, bg=theme.BG)
        self.center.pack(side="left", fill="both", expand=True)
        self.center.grid_rowconfigure(0, weight=1)
        self.center.grid_columnconfigure(0, weight=1)

        self.chat_view = ChatView(
            self.center, on_expand_code=self._open_code_panel,
            on_suggestion=self._on_suggestion, bg=theme.BG,
        )
        self.proposals_view = self._build_proposals_view(self.center)

        self.input_bar = InputBar(
            self.center, on_send=self.send, on_attach=self._on_attach,
            on_mic=self._on_mic, on_stop=self.cancel, bg=theme.BG,
        )

        self.show_view("chat")

    def _build_topbar(self, parent):
        top = tk.Frame(parent, bg=theme.BG, height=56)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        left = tk.Frame(top, bg=theme.BG)
        left.pack(side="left", padx=theme.SPACE_LG)
        IconButton(left, icon="panel_left", kind="ghost", size=32, icon_size=16,
                   tooltip="Basculer la barre latérale",
                   command=lambda: self.sidebar.toggle(), bg=theme.BG).pack(
            side="left", pady=12)
        tk.Label(left, text="JIBI", bg=theme.BG, fg=theme.TEXT,
                 font=theme.serif(15, bold=True)).pack(side="left", padx=(10, 6))
        badge = RoundedFrame(left, radius=8, card_bg=theme.ACCENT_SOFT, bg=theme.BG, pad=0)
        badge.pack(side="left")
        tk.Label(badge.body, text="AURORA", bg=theme.ACCENT_SOFT, fg=theme.ACCENT,
                 font=theme.sans(8, bold=True)).pack(padx=8, pady=3)

        right = tk.Frame(top, bg=theme.BG)
        right.pack(side="right", padx=theme.SPACE_LG)
        self.status_pill = StatusPill(right, state="ready", bg=theme.BG)
        self.status_pill.pack(side="right", pady=12)
        IconButton(right, icon="settings", kind="ghost", size=32, icon_size=16,
                   tooltip="Paramètres", command=self._show_settings_stub,
                   bg=theme.BG).pack(side="right", padx=(0, 8), pady=12)
        return top

    def _build_proposals_view(self, master):
        v = tk.Frame(master, bg=theme.BG)
        v.grid_rowconfigure(0, weight=1)
        v.grid_columnconfigure(1, weight=1)

        left = tk.Frame(v, bg=theme.PANEL, width=300)
        left.grid(row=0, column=0, sticky="ns")
        left.grid_propagate(False)
        tk.Label(left, text="PROPOSITIONS", bg=theme.PANEL, fg=theme.TEXT_FAINT,
                 font=theme.sans(9, bold=True)).pack(
            anchor="w", padx=theme.SPACE_MD, pady=(theme.SPACE_LG, theme.SPACE_SM))
        self.props_area = ScrollArea(left, bg=theme.PANEL, auto_scroll=False)
        self.props_area.pack(fill="both", expand=True, padx=theme.SPACE_SM,
                             pady=(0, theme.SPACE_SM))

        right = tk.Frame(v, bg=theme.BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        head = tk.Frame(right, bg=theme.BG)
        head.grid(row=0, column=0, sticky="ew", padx=theme.SPACE_LG,
                 pady=(theme.SPACE_LG, theme.SPACE_SM))
        self.diff_title = tk.Label(head, text="Sélectionnez une proposition",
                                   bg=theme.BG, fg=theme.TEXT, font=theme.serif(15, bold=True))
        self.diff_title.pack(side="left")
        btns = tk.Frame(head, bg=theme.BG)
        btns.pack(side="right")
        PillButton(btns, text="Autoriser", icon="check", kind="primary", height=32,
                   command=self._auth_selected).pack(side="left", padx=(0, 6))
        PillButton(btns, text="Rejeter", icon="close", kind="ghost", height=32,
                   command=self._reject_selected).pack(side="left")

        diff_wrap = tk.Frame(right, bg=theme.PANEL)
        diff_wrap.grid(row=1, column=0, sticky="nsew", padx=theme.SPACE_LG,
                       pady=(0, theme.SPACE_LG))
        diff_wrap.grid_rowconfigure(0, weight=1)
        diff_wrap.grid_columnconfigure(0, weight=1)
        sb = ThinScrollbar(diff_wrap, bg=theme.PANEL)
        sb.grid(row=0, column=1, sticky="ns")
        self.diff_text = tk.Text(diff_wrap, wrap="none", bg=theme.PANEL, fg=theme.TEXT,
                                 font=theme.mono(10), bd=0, padx=14, pady=14,
                                 highlightthickness=0, relief="flat", state="disabled",
                                 insertbackground=theme.ACCENT)
        self.diff_text.grid(row=0, column=0, sticky="nsew")
        sb.attach(self.diff_text)
        self.diff_text.tag_configure("add", foreground=theme.ACCENT)
        self.diff_text.tag_configure("del", foreground=theme.DANGER)
        self.diff_text.tag_configure("hunk", foreground=theme.ACCENT, font=theme.mono(10, bold=True))
        return v

    # ================================================== vues
    def show_view(self, name: str):
        self._active_view = name
        if name == "chat":
            self.proposals_view.grid_forget()
            self.chat_view.grid(row=0, column=0, sticky="nsew")
            self.input_bar.grid(row=1, column=0, sticky="ew")
        else:
            self.chat_view.grid_forget()
            self.input_bar.grid_forget()
            self.proposals_view.grid(row=0, column=0, rowspan=2, sticky="nsew")
            self.refresh_props()
        self.sidebar.set_active_nav(name)

    def _on_nav(self, key: str):
        self.show_view(key)

    # ================================================== sessions
    def _new_session(self, title: str):
        sid = datetime.now().strftime("%Y%m%d_%H%M%S%f")
        self.sessions.insert(0, {"id": sid, "title": title,
                                 "meta": datetime.now().strftime("%H:%M")})
        self.current_session_id = sid
        self.sidebar.set_sessions(self.sessions)
        self.sidebar.select_session(sid)
        self.chat_view.clear()
        self.chat_view.set_suggestions(SUGGESTIONS)
        self.sidebar.set_nav_counts(chat=0)
        self.show_view("chat")

    def _new_chat_clicked(self):
        if self.busy:
            return
        self._new_session("Nouvelle discussion")

    def _on_open_session(self, session: dict):
        # Pas de persistance des messages par session pour l'instant
        # (comportement identique à la v9 : seul le libellé change).
        self.current_session_id = session.get("id")
        self.sidebar.select_session(self.current_session_id)

    def _on_delete_session(self, session: dict):
        self.sessions = [s for s in self.sessions if s.get("id") != session.get("id")]
        self.sidebar.set_sessions(self.sessions)

    # ================================================== statut
    def set_status(self, s: str):
        self.etat = s
        self.status_pill.set_state(s)

    def _refresh_model_status(self):
        # disponible() fait un appel réseau (jusqu'à 3s de timeout) : on
        # l'exécute dans un thread pour ne jamais geler l'UI, contrairement
        # à un appel direct sur le thread principal de Tk.
        def worker():
            try:
                from core import cerveau
                ok = bool(cerveau.disponible())
                name = cerveau.MODEL if EV_OK else "Mode simulé"
            except Exception:
                ok, name = False, "Mode simulé"
            self.root.after(0, lambda: self.sidebar.set_model(
                name, "Opérationnel" if ok else "Hors ligne", online=ok))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(15000, self._refresh_model_status)

    # ================================================== envoi / réception
    def send(self, text: str):
        if self.busy:
            return
        msg = (text or "").strip()
        if not msg:
            return
        self.busy = True
        self.cancelled = False
        self.req_id += 1
        req = self.req_id
        self.cancel_ev = threading.Event()
        self._stream_buf = ""
        self._current_bot_row = None

        self.set_status("thinking")
        self.input_bar.set_busy(True)
        self.chat_view.add_user(msg, meta=datetime.now().strftime("%H:%M"))
        self.chat_view.show_typing()

        def on_chunk(chunk: str):
            if self.cancelled or req != self.req_id:
                return
            def do():
                if self.etat != "busy" and not self.cancelled:
                    self.set_status("busy")
                    self.chat_view.hide_typing()
                    self._current_bot_row = self.chat_view.add_bot(
                        "", meta=datetime.now().strftime("%H:%M"))
                if not chunk or self._current_bot_row is None:
                    return
                # Le backend peut envoyer des deltas OU un cumulatif selon
                # l'API (Ollama envoie des deltas, certains relais renvoient
                # le texte complet à chaque chunk) : on ne pousse jamais que
                # la partie nouvelle dans le widget.
                if self._stream_buf and chunk.startswith(self._stream_buf):
                    delta = chunk[len(self._stream_buf):]
                    self._stream_buf = chunk
                else:
                    delta = chunk
                    self._stream_buf += chunk
                if delta:
                    self._current_bot_row.append(delta)
                    self.chat_view.scroll_to_bottom()
            self.root.after(0, do)

        def worker():
            try:
                sig = inspect.signature(self.agent.traiter_message)
                kw = {}
                if "on_chunk" in sig.parameters:
                    kw["on_chunk"] = on_chunk
                if "cancel_event" in sig.parameters:
                    kw["cancel_event"] = self.cancel_ev
                rep = self.agent.traiter_message(msg, **kw)
                self.q.put((req, "ok", rep))
            except Exception as e:
                self.q.put((req, "err", str(e)))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self.poll)

    def poll(self):
        try:
            while True:
                req, kind, payload = self.q.get_nowait()
                if req != self.req_id:
                    continue
                break
        except Empty:
            if self.busy and not self.cancelled:
                self.root.after(80, self.poll)
            return

        if self.cancelled:
            return

        self.chat_view.hide_typing()

        if kind == "ok":
            rep = payload
            txt = getattr(rep, "texte", str(rep))
            if self._current_bot_row is not None:
                self._current_bot_row.replace_streamed(txt)
            else:
                self._current_bot_row = self.chat_view.add_bot(
                    txt, meta=datetime.now().strftime("%H:%M"))
            self.chat_view.scroll_to_bottom()

            if getattr(rep, "proposition_id", None):
                self.refresh_props()
            act = getattr(rep, "action_requise", None) or {}
            if act.get("type") == "confirmation" and act.get("id"):
                self.input_bar.set_text(f"CONFIRME {act['id']}")
                self.set_status("confirmation")
            else:
                self.set_status("done")
                self.root.after(1200, lambda: self.set_status("ready") if not self.busy else None)
        else:
            err = f"❌ Erreur : {payload}"
            if self._current_bot_row is not None:
                self._current_bot_row.replace_streamed(err)
            else:
                self.chat_view.add_bot(err, meta=datetime.now().strftime("%H:%M"))
            self.chat_view.scroll_to_bottom()
            self.set_status("error")
            self.root.after(2000, lambda: self.set_status("ready") if not self.busy else None)

        self.busy = False
        self.cancel_ev = None
        self.input_bar.set_busy(False)
        self.input_bar.focus_input()

    def cancel(self):
        if not self.busy:
            return
        self.cancelled = True
        if self.cancel_ev:
            try:
                self.cancel_ev.set()
            except Exception:
                pass
        self.chat_view.hide_typing()
        final = (self._stream_buf + "\n\n(Annulé.)") if self._stream_buf else "(Annulé.)"
        if self._current_bot_row is not None:
            self._current_bot_row.replace_streamed(final)
        else:
            self.chat_view.add_bot(final, meta=datetime.now().strftime("%H:%M"))
        self.chat_view.scroll_to_bottom()
        self._current_bot_row = None
        self.busy = False
        self.input_bar.set_busy(False)
        self.set_status("cancelled")
        self.root.after(1500, lambda: self.set_status("ready") if not self.busy else None)
        self.input_bar.focus_input()

    # ================================================== propositions
    def refresh_props(self):
        self.props_area.clear()
        self._prop_rows = {}
        if not EV_OK or evolution is None:
            tk.Label(self.props_area.frame,
                     text="Module d'évolution indisponible\n(core/evolution.py introuvable).",
                     bg=theme.PANEL, fg=theme.TEXT_FAINT, font=theme.sans(9),
                     justify="left").pack(anchor="w", padx=10, pady=10)
            self.sidebar.set_nav_counts(proposals=0)
            return
        try:
            props = evolution.lister("en_attente") + evolution.lister("tests_echoues")
        except Exception:
            props = []
        self.sidebar.set_nav_counts(proposals=len(props))
        if not props:
            tk.Label(self.props_area.frame, text="Aucune proposition en attente.",
                     bg=theme.PANEL, fg=theme.TEXT_FAINT, font=theme.sans(9)).pack(
                anchor="w", padx=10, pady=10)
            return
        for p in props:
            row = self._make_prop_row(p)
            row.pack(fill="x", pady=1)
            self._prop_rows[p.get("id")] = row
        self.props_area.bind_wheel_recursive()

    def _make_prop_row(self, prop: dict) -> tk.Frame:
        statut = prop.get("statut", "?")
        color = {"appliquee": theme.ACCENT, "restauree": theme.ACCENT,
                 "rejetee": theme.DANGER, "tests_echoues": theme.DANGER}.get(
            statut, theme.TEXT_FAINT)
        row = tk.Frame(self.props_area.frame, bg=theme.PANEL, cursor="hand2")
        dot = tk.Canvas(row, width=8, height=8, bg=theme.PANEL, highlightthickness=0)
        dot.create_oval(0, 0, 8, 8, fill=color, outline=color)
        dot.pack(side="left", padx=(10, 8), pady=12)
        txt = tk.Frame(row, bg=theme.PANEL)
        txt.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(txt, text=prop.get("fichier", "?"), bg=theme.PANEL, fg=theme.TEXT,
                 font=theme.sans(10, bold=True), anchor="w").pack(fill="x")
        tk.Label(txt, text=f"{prop.get('id')} · {statut}", bg=theme.PANEL,
                 fg=theme.TEXT_FAINT, font=theme.sans(8), anchor="w").pack(fill="x")

        def click(_e=None, p=prop):
            self._select_prop(p)

        for w in (row, dot, txt, *txt.winfo_children()):
            w.bind("<Button-1>", click)
        return row

    def _select_prop(self, prop: dict):
        pid = prop.get("id")
        self._selected_prop = pid
        for k, row in self._prop_rows.items():
            bg = theme.ACCENT_SOFT if k == pid else theme.PANEL
            self._repaint_row(row, bg)
        self.diff_title.configure(text=f"{prop.get('fichier', '?')} — {pid}")

        diff = ""
        if EV_OK and evolution is not None:
            try:
                p = evolution.charger(pid) or {}
                diff = p.get("diff", "")
            except Exception:
                diff = ""
        self.diff_text.configure(state="normal")
        self.diff_text.delete("1.0", "end")
        if diff:
            for line in diff.splitlines(True):
                tag = None
                if line.startswith("+") and not line.startswith("+++"):
                    tag = "add"
                elif line.startswith("-") and not line.startswith("---"):
                    tag = "del"
                elif line.startswith("@@"):
                    tag = "hunk"
                self.diff_text.insert("end", line, tag if tag else ())
        else:
            self.diff_text.insert("end", "(Aucun diff disponible.)")
        self.diff_text.configure(state="disabled")

    @staticmethod
    def _repaint_row(widget, bg):
        try:
            widget.configure(bg=bg)
        except Exception:
            pass
        for c in widget.winfo_children():
            JibiGUI._repaint_row(c, bg)

    def _auth_selected(self):
        if not self._selected_prop:
            return
        pid = self._selected_prop
        self.show_view("chat")
        self.send(f"J'AUTORISE {pid}")

    def _reject_selected(self):
        if not self._selected_prop:
            return
        pid = self._selected_prop
        self.show_view("chat")
        self.send(f"JE REJETTE {pid}")

    # ================================================== panneau d'artefact
    def _open_code_panel(self, lang: str, code: str):
        self.artifact_panel.open_artifact(
            kind="code", title=f"Extrait {lang}", content=code,
            subtitle=f"{lang} · généré par JIBI")

    def _save_artifact(self, kind: str, title: str, content: str):
        ext = {"code": ".py", "tool": ".py", "doc": ".md"}.get(kind, ".txt")
        path = filedialog.asksaveasfilename(defaultextension=ext,
                                            initialfile=(title or "artefact"))
        if not path:
            return
        try:
            Path(path).write_text(content, encoding="utf-8")
        except Exception:
            pass

    def _show_settings_stub(self):
        content = (
            "Paramètres\n\n"
            "Cette section affichera bientôt le choix du modèle, le thème, "
            "les raccourcis clavier et l'emplacement des sauvegardes.\n\n"
            "Pour changer de modèle aujourd'hui : variables d'environnement "
            "JIBI_LLM_URL / JIBI_LLM_MODEL (voir cerveau.py)."
        )
        self.artifact_panel.open_artifact(kind="doc", title="Paramètres",
                                          content=content, subtitle="JIBI Aurora")

    # ================================================== saisie
    def _on_suggestion(self, label: str):
        self.send(label)

    def _on_attach(self):
        path = filedialog.askopenfilename()
        if path:
            # Pas encore relié à l'agent : indication visuelle seulement.
            self.input_bar.set_attach_badge(f"Joint : {Path(path).name}")

    def _on_mic(self, on: bool):
        self.input_bar.set_listening(on)
        # Intégration Parakeet (dictée) à brancher ici.

    # ================================================== cycle de vie
    def _on_close(self):
        try:
            self.state.set(geometry=self.root.geometry())
            self.state.save()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    print(">>> JIBI AURORA STARTING...")
    app = JibiGUI()
    app.run()