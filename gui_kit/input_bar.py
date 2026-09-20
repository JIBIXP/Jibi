"""
JIBI GUI Kit — Input Bar
========================
"""

from __future__ import annotations

import tkinter as tk

from .controls import IconButton, RoundedButton, RoundedFrame
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
        self._placeholder = "Écris un message… (Shift+Entrée pour nouvelle ligne)"
        self._placeholder_active = True

        self.entry_frame = RoundedFrame(
            self,
            radius=24,
            card_bg=COLORS["surface"],
            bg=COLORS["bg"],
            outline=COLORS["border"],
            border_width=1,
            pad=4,
        )

        self.entry_frame.pack(
            fill="x",
            padx=24,
            pady=16,
        )

        self.attach_button = IconButton(
            self.entry_frame.body,
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
            self.entry_frame.body,
            height=2,
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=COLORS["surface"],
            fg=COLORS["text_dim"],
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

        # Placeholder initial
        self._show_placeholder()

        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)

        self.entry.bind(
            "<Return>",
            self._return,
        )

        self.mic_button = IconButton(
            self.entry_frame.body,
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
            self.entry_frame.body,
            text="Annuler",
            command=self._stop,
            bg=COLORS["danger"],
            hover_bg="#ef5a78",
        )

        self.send_button = RoundedButton(
            self.entry_frame.body,
            text="Envoyer ➤",
            command=self._send,
        )

        self.send_button.pack(
            side="right",
            padx=8,
            pady=7,
        )

        self._set_busy(False)

    # ----------------------------------------------------------------
    # Placeholder

    def _show_placeholder(self):
        self._placeholder_active = True
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", self._placeholder)
        self.entry.configure(fg=COLORS["text_dim"])

    def _hide_placeholder(self):
        if self._placeholder_active:
            self.entry.delete("1.0", "end")
            self.entry.configure(fg=COLORS["text"])
            self._placeholder_active = False

    def _on_focus_in(self, _event=None):
        if self._placeholder_active:
            self._hide_placeholder()

    def _on_focus_out(self, _event=None):
        content = self.entry.get("1.0", "end-1c").strip()
        if not content:
            self._show_placeholder()

    # ----------------------------------------------------------------
    # Events

    def _return(self, event):
        # Shift+Entrée = nouvelle ligne
        if event.state & 0x0001:
            return
        self._send()
        return "break"

    def _send(self):
        if self._placeholder_active:
            return

        text = self.entry.get(
            "1.0",
            "end-1c",
        ).strip()

        if not text:
            return

        # FIX BUG 2 : vider le champ AVANT d'appeler on_send
        self.clear()
        self._show_placeholder()

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
        self._placeholder_active = False

    def focus_input(self):
        self.entry.focus_set()

    def get_text(self) -> str:
        if self._placeholder_active:
            return ""
        return self.entry.get(
            "1.0",
            "end-1c",
        )

    def set_text(
        self,
        text: str,
    ):
        self.clear()
        self._placeholder_active = False
        self.entry.configure(fg=COLORS["text"])
        self.entry.insert(
            "1.0",
            text,
        )

    def insert_text(
        self,
        text: str,
    ):
        """Insère du texte à la position du curseur, sans vider le champ."""
        if self._placeholder_active:
            self._hide_placeholder()
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