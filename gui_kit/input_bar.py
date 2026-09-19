"""
JIBI GUI Kit — Input Bar
========================
"""

from __future__ import annotations

import tkinter as tk

from .controls import IconButton, RoundedButton
from .theme import COLORS, FONT


class InputBar(tk.Frame):
    """
    Barre de saisie JIBI.

    Callbacks :

        on_send(text)
        on_stop()
        on_attach()
        on_mic(listening: bool)
    """

    def __init__(
        self,
        master,
        on_send=None,
        on_stop=None,
        on_attach=None,
        on_mic=None,
        **kwargs,
    ):
        super().__init__(
            master,
            bg=kwargs.pop(
                "bg",
                COLORS["bg"],
            ),
            **kwargs,
        )

        self.on_send = on_send
        self.on_stop = on_stop
        self.on_attach = on_attach
        self.on_mic = on_mic

        self._listening = False

        self.entry_frame = tk.Frame(
            self,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )

        self.entry_frame.pack(
            fill="x",
            padx=16,
            pady=12,
        )

        self.attach_button = IconButton(
            self.entry_frame,
            text="＋",
            command=self._attach,
            bg=COLORS["surface"],
            activebackground=COLORS["accent_soft"],
        )

        self.attach_button.pack(
            side="left",
            padx=(8, 4),
        )

        self.entry = tk.Text(
            self.entry_frame,
            height=2,
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            font=FONT["body"],
        )

        self.entry.pack(
            side="left",
            fill="both",
            expand=True,
            padx=6,
            pady=7,
        )

        self.entry.bind(
            "<Return>",
            self._return,
        )

        self.mic_button = IconButton(
            self.entry_frame,
            text="🎙",
            command=self._mic,
            bg=COLORS["surface"],
            activebackground=COLORS["accent_soft"],
        )

        self.mic_button.pack(
            side="left",
            padx=4,
        )

        self.stop_button = RoundedButton(
            self.entry_frame,
            text="Annuler",
            command=self._stop,
            bg=COLORS["danger"],
            hover_bg="#ef5a78",
        )

        self.send_button = RoundedButton(
            self.entry_frame,
            text="Envoyer ➤",
            command=self._send,
        )

        self.send_button.pack(
            side="right",
            padx=8,
            pady=7,
        )

        self._set_busy(False)

    def _return(self, event):
        if event.state & 0x0001:
            return

        self._send()

        return "break"

    def _send(self):
        text = self.entry.get(
            "1.0",
            "end-1c",
        ).strip()

        if not text:
            return

        if self.on_send:
            self.on_send(text)

    def _stop(self):
        if self.on_stop:
            self.on_stop()

    def _attach(self):
        if self.on_attach:
            self.on_attach()

    def _mic(self):
        listening = not self._listening
        self.set_listening(listening)

        if self.on_mic:
            self.on_mic(listening)

    def clear(self):
        self.entry.delete(
            "1.0",
            "end",
        )

    def focus_input(self):
        self.entry.focus_set()

    def get_text(self) -> str:
        return self.entry.get(
            "1.0",
            "end-1c",
        )

    def set_text(
        self,
        text: str,
    ):
        self.clear()

        self.entry.insert(
            "1.0",
            text,
        )

    def insert_text(
        self,
        text: str,
    ):
        """Insère du texte à la position du curseur, sans vider le champ."""
        self.entry.insert(
            "insert",
            text,
        )
        self.focus_input()

    def set_listening(
        self,
        listening: bool,
    ):
        """Reflète visuellement l'état d'écoute du micro."""
        self._listening = bool(listening)

        self.mic_button.configure(
            fg=(
                COLORS["accent"]
                if self._listening
                else self.mic_button._normal_fg
            ),
        )

    def set_busy(
        self,
        busy: bool,
    ):
        self._set_busy(busy)

    def _set_busy(
        self,
        busy: bool,
    ):
        if busy:
            self.send_button.pack_forget()

            self.stop_button.pack(
                side="right",
                padx=8,
                pady=7,
            )
        else:
            self.stop_button.pack_forget()

            self.send_button.pack(
                side="right",
                padx=8,
                pady=7,
            )