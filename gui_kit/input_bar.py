# =========================================================
# gui_kit/input_bar.py — Barre de saisie flottante "en pilule"
# =========================================================
# Un seul champ arrondi qui contient : pièce jointe, zone de texte
# auto-agrandissante, micro (Parakeet) et envoi. Plus de boutons
# disjoints sous le champ comme dans l'ancienne GUI.
#
#   Entrée          -> envoyer
#   Maj + Entrée    -> retour à la ligne
#   Échap           -> couper la génération en cours
# =========================================================
from __future__ import annotations

import tkinter as tk

from . import theme
from .controls import IconButton, RoundedFrame


class InputBar(tk.Frame):
    MAX_LINES = 9

    def __init__(self, master, *, on_send=None, on_attach=None, on_mic=None,
                 on_stop=None, bg=theme.BG):
        super().__init__(master, bg=bg)
        self.on_send = on_send
        self.on_attach = on_attach
        self.on_mic = on_mic
        self.on_stop = on_stop
        self._bg = bg
        self._busy = False
        self._listening = False

        # Marge extérieure : la barre "flotte" au-dessus du fond.
        outer = tk.Frame(self, bg=bg)
        outer.pack(fill="x", padx=theme.SPACE_XL, pady=(theme.SPACE_SM, theme.SPACE_LG))

        self.pill = RoundedFrame(outer, radius=theme.RADIUS_PILL, card_bg=theme.INPUT_BG,
                                 border_color=theme.BORDER, border_width=1,
                                 pad=6, bg=bg)
        self.pill.pack(fill="x")
        self.pill.body.configure(bg=theme.INPUT_BG)

        row = tk.Frame(self.pill.body, bg=theme.INPUT_BG)
        row.pack(fill="x", padx=6, pady=4)

        # ---- pièce jointe
        self.attach_btn = IconButton(row, icon="paperclip", kind="ghost", size=34,
                                     icon_size=17, tooltip="Joindre un fichier",
                                     command=self._fire_attach, bg=theme.INPUT_BG)
        self.attach_btn.pack(side="left", padx=(2, 4), pady=2)

        # ---- zone de texte
        wrap = tk.Frame(row, bg=theme.INPUT_BG)
        wrap.pack(side="left", fill="x", expand=True, pady=2)
        self.entry = tk.Text(wrap, height=1, width=4, wrap="word", bg=theme.INPUT_BG,
                             fg=theme.TEXT, insertbackground=theme.ACCENT,
                             insertwidth=2, font=theme.sans(11), bd=0,
                             highlightthickness=0, relief="flat", padx=2, pady=8,
                             undo=True, maxundo=64, spacing1=1, spacing3=1)
        self.entry.pack(fill="x")
        self.placeholder = tk.Label(wrap, text="Écrivez à JIBI…", bg=theme.INPUT_BG,
                                    fg=theme.TEXT_FAINT, font=theme.sans(11))
        self.placeholder.place(x=4, y=9)
        self.placeholder.lower()

        # ---- micro (dictée Parakeet)
        self.mic_btn = IconButton(row, icon="mic", kind="ghost", size=34, icon_size=17,
                                  tooltip="Dicter (Parakeet)", command=self._fire_mic,
                                  bg=theme.INPUT_BG)
        self.mic_btn.pack(side="right", padx=(4, 2), pady=2)

        # ---- envoi / stop
        self.send_btn = IconButton(row, icon="send", kind="accent", size=34, icon_size=16,
                                   radius=17, tooltip="Envoyer (Entrée)",
                                   command=self._fire_send, bg=theme.INPUT_BG)
        self.send_btn.pack(side="right", padx=(2, 4), pady=2)

        # ---- compteur discret sous la barre
        self.hint = tk.Label(outer, text="", bg=bg, fg=theme.TEXT_FAINT,
                             font=theme.sans(8))
        self.hint.pack(anchor="e", padx=6)

        # ---- liaisons
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<<Modified>>", self._on_modified)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Shift-Return>", lambda _e: "break")
        self.entry.bind("<FocusIn>", lambda _e: (self.pill.set_highlight(True),
                                                 self._hide_placeholder())[1])
        self.entry.bind("<FocusOut>", lambda _e: (self.pill.set_highlight(False),
                                                  self._sync_placeholder())[1])
        self.bind_all("<Escape>", self._on_escape)
        self._autogrow()

    # -------------------------------------------------- placeholder
    def _hide_placeholder(self):
        try:
            self.placeholder.place_forget()
        except Exception:
            pass

    def _sync_placeholder(self):
        if self.get_text():
            self._hide_placeholder()
        else:
            try:
                self.placeholder.place(x=4, y=9)
            except Exception:
                pass

    # -------------------------------------------------- texte
    def get_text(self) -> str:
        return self.entry.get("1.0", "end-1c")

    def set_text(self, text: str):
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", text)
        self._sync_placeholder()
        self._autogrow()

    def insert_text(self, text: str):
        self.entry.insert("insert", text)
        self._sync_placeholder()
        self._autogrow()

    def clear(self):
        self.entry.delete("1.0", "end")
        self._sync_placeholder()
        self._autogrow()

    def focus_input(self):
        try:
            self.entry.focus_set()
        except Exception:
            pass

    def _autogrow(self):
        try:
            n = self.entry.count("1.0", "end-1c", "displaylines")
            lines = int(n[0]) if n else 1
        except Exception:
            lines = int(self.entry.index("end-1c").split(".")[0])
        lines = max(1, min(self.MAX_LINES, lines))
        if int(self.entry["height"]) != lines:
            self.entry.configure(height=lines)

    # -------------------------------------------------- événements
    def _on_key(self, _e):
        self._autogrow()
        self._sync_placeholder()

    def _on_modified(self, _e):
        if self.entry.edit_modified():
            self.entry.edit_modified(False)
            self._autogrow()

    def _on_return(self, _e):
        # Maj+Entrée est intercepté plus haut ; ici on envoie.
        self._fire_send()
        return "break"

    def _on_escape(self, _e):
        if self._busy and self.on_stop:
            self.on_stop()
            return "break"
        return None

    # -------------------------------------------------- états
    def set_busy(self, busy: bool):
        self._busy = busy
        self.send_btn.set_icon("stop" if busy else "send")
        self.send_btn.tooltip = "Interrompre (Échap)" if busy else "Envoyer (Entrée)"
        self.send_btn.set_enabled(True)
        self.hint.configure(text="Échap pour interrompre" if busy else "")

    def set_listening(self, on: bool):
        self._listening = on
        self.mic_btn.set_state_visual("pressed" if on else "normal")
        self.mic_btn.tooltip = "Arrêter la dictée" if on else "Dicter (Parakeet)"
        self.hint.configure(text="Écoute en cours…" if on else "")

    def set_attach_badge(self, label: str):
        self.hint.configure(text=label)

    # -------------------------------------------------- callbacks
    def _fire_send(self):
        text = self.get_text().strip()
        if not text:
            return
        if self._busy:
            if self.on_stop:
                self.on_stop()
            return
        if self.on_send:
            self.on_send(text)

    def _fire_attach(self):
        if self.on_attach:
            self.on_attach()

    def _fire_mic(self):
        if self.on_mic:
            self.on_mic(not self._listening)
