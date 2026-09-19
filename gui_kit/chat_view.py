"""
JIBI GUI Kit — Chat View
========================

Vue de conversation : bulles utilisateur/assistant, blocs de code
détectés (```lang ... ```) avec bouton "Ouvrir" vers le panneau
d'artefacts, indicateur "en train d'écrire", et suggestions.
"""

from __future__ import annotations

import re
import tkinter as tk

from . import theme
from .controls import RoundedButton
from .scrollbar import ScrollArea


_CODE_RE = re.compile(r"```(\w*)\n?(.*?)```", re.S)


class _MessageRow(tk.Frame):
    def __init__(self, master, *, role, meta, bg, on_expand_code=None):
        super().__init__(master, bg=bg)

        self.role = role
        self.on_expand_code = on_expand_code
        self.current_text = ""

        is_user = role == "user"

        header = tk.Frame(self, bg=bg)
        header.pack(fill="x", padx=4, pady=(10, 2))

        tk.Label(
            header,
            text="Vous" if is_user else "JIBI",
            bg=bg,
            fg=theme.ACCENT if not is_user else theme.TEXT_SUB,
            font=theme.sans(9, bold=True),
        ).pack(side="left")

        if meta:
            tk.Label(
                header,
                text=meta,
                bg=bg,
                fg=theme.TEXT_FAINT,
                font=theme.sans(8),
            ).pack(side="left", padx=(8, 0))

        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill="x", padx=4, pady=(0, 4))

    def set_text(self, text: str):
        self.current_text = text or ""

        for child in self.body.winfo_children():
            child.destroy()

        parts = _CODE_RE.split(self.current_text)

        # parts = [text, lang, code, text, lang, code, ..., text]
        leading = parts[0]
        if leading.strip():
            self._add_text(leading)
        elif not parts[1:]:
            # message vide (streaming en cours) : rien à afficher encore
            pass

        k = 1
        while k < len(parts) - 1:
            lang = parts[k]
            code = parts[k + 1]
            self._add_code(lang, code)

            trailing = parts[k + 2] if k + 2 < len(parts) else ""
            if trailing.strip():
                self._add_text(trailing)

            k += 3

    def _add_text(self, text: str):
        tk.Label(
            self.body,
            text=text.strip("\n"),
            bg=self["bg"],
            fg=theme.TEXT,
            font=theme.sans(10),
            justify="left",
            anchor="w",
            wraplength=560,
        ).pack(fill="x", pady=(2, 2))

    def _add_code(self, lang: str, code: str):
        wrap = tk.Frame(
            self.body,
            bg=theme.COLORS["surface"],
            highlightbackground=theme.BORDER,
            highlightthickness=1,
        )
        wrap.pack(fill="x", pady=(4, 4))

        head = tk.Frame(wrap, bg=theme.COLORS["surface"])
        head.pack(fill="x", padx=8, pady=(6, 0))

        tk.Label(
            head,
            text=(lang or "code").upper(),
            bg=theme.COLORS["surface"],
            fg=theme.TEXT_FAINT,
            font=theme.sans(7, bold=True),
        ).pack(side="left")

        if self.on_expand_code:
            RoundedButton(
                head,
                text="Ouvrir ↗",
                bg=theme.COLORS["surface_alt"],
                fg=theme.TEXT_SUB,
                hover_bg=theme.ELEVATED,
                command=lambda: self.on_expand_code(lang, code.rstrip("\n")),
            ).pack(side="right")

        preview = code.strip("\n")
        lines = preview.splitlines()
        if len(lines) > 8:
            preview = "\n".join(lines[:8]) + "\n…"

        tk.Label(
            wrap,
            text=preview or " ",
            bg=theme.COLORS["surface"],
            fg=theme.TEXT_DIM,
            font=theme.mono(9),
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=8, pady=(4, 8))


class _BotRowHandle:
    """Contrôleur renvoyé par ChatView.add_bot() pour le streaming."""

    def __init__(self, row: _MessageRow):
        self._row = row
        self._text = row.current_text

    def append(self, delta: str):
        if not delta:
            return
        self._text += delta
        self._row.set_text(self._text)

    def replace_streamed(self, full_text: str):
        self._text = full_text or ""
        self._row.set_text(self._text)


class _TypingRow(tk.Frame):
    def __init__(self, master, bg):
        super().__init__(master, bg=bg)

        self._phase = 0
        self.label = tk.Label(
            self,
            text="JIBI réfléchit…",
            bg=bg,
            fg=theme.TEXT_DIM,
            font=theme.sans(9),
        )
        self.label.pack(anchor="w", padx=8, pady=(6, 6))

        self._running = True
        self._animate()

    def _animate(self):
        if not self._running:
            return

        self._phase = (self._phase + 1) % 4
        dots = "." * self._phase

        try:
            self.label.configure(text=f"JIBI réfléchit{dots}")
            self.after(400, self._animate)
        except Exception:
            self._running = False

    def destroy(self):
        self._running = False
        super().destroy()


class ChatView(tk.Frame):
    """
    Vue conversation.

    API :
        add_user(text, meta="")
        add_bot(text, meta="") -> handle avec .append(delta) / .replace_streamed(text)
        show_typing() / hide_typing()
        set_suggestions(list_of_str)
        clear()
        scroll_to_bottom()
    """

    def __init__(
        self,
        master,
        on_expand_code=None,
        on_suggestion=None,
        bg=None,
        **kwargs,
    ):
        bg = bg or theme.BG

        super().__init__(master, bg=bg, **kwargs)

        self.on_expand_code = on_expand_code
        self.on_suggestion = on_suggestion
        self._bg = bg

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ---- Suggestions -------------------------------------------------

        self.suggestions_frame = tk.Frame(self, bg=bg)
        self.suggestions_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))

        # ---- Zone de messages ---------------------------------------------

        self.area = ScrollArea(self, bg=bg, auto_scroll=True)
        self.area.grid(row=1, column=0, sticky="nsew")

        self._typing_row: _TypingRow | None = None

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_user(self, text: str, meta: str = ""):
        row = _MessageRow(
            self.area.frame,
            role="user",
            meta=meta,
            bg=self._bg,
        )
        row.pack(fill="x")
        row.set_text(text)
        self.area.bind_wheel_recursive()
        return row

    def add_bot(self, text: str, meta: str = ""):
        row = _MessageRow(
            self.area.frame,
            role="bot",
            meta=meta,
            bg=self._bg,
            on_expand_code=self.on_expand_code,
        )
        row.pack(fill="x")
        row.set_text(text)
        self.area.bind_wheel_recursive()
        return _BotRowHandle(row)

    def clear(self):
        self.hide_typing()
        self.area.clear()

    def scroll_to_bottom(self):
        self.area.stick_to_bottom()

    # ------------------------------------------------------------------
    # Indicateur "en train d'écrire"
    # ------------------------------------------------------------------

    def show_typing(self):
        if self._typing_row is not None:
            return

        self._typing_row = _TypingRow(self.area.frame, bg=self._bg)
        self._typing_row.pack(fill="x")
        self.scroll_to_bottom()

    def hide_typing(self):
        if self._typing_row is None:
            return

        try:
            self._typing_row.destroy()
        except Exception:
            pass

        self._typing_row = None

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------

    def set_suggestions(self, suggestions):
        for child in self.suggestions_frame.winfo_children():
            child.destroy()

        for text in suggestions or []:
            RoundedButton(
                self.suggestions_frame,
                text=text,
                bg=theme.COLORS["surface"],
                fg=theme.TEXT_SUB,
                hover_bg=theme.ELEVATED,
                command=lambda t=text: self._pick_suggestion(t),
            ).pack(side="left", padx=(0, 8), pady=(0, 10))

    def _pick_suggestion(self, text):
        if self.on_suggestion:
            self.on_suggestion(text)
