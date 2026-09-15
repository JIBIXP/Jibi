# =========================================================
# gui_kit/chat_view.py — Zone de conversation
# =========================================================
# Chaque message est une ligne : avatar + bulle. Le corps de la
# bulle est un tk.Text en lecture seule (pas un Label) : c'est ce
# qui permet le rendu markdown léger (gras, code inline, blocs de
# code) ET la sélection/copie par l'utilisateur.
#
# Streaming : on n'ajoute que le morceau nouveau (append), jamais
# un re-rendu complet du tampon — l'ancienne GUI réinsérait tout le
# texte à chaque chunk, d'où un coût en O(n²) sur la longueur de la
# réponse. Le re-rendu riche (markdown) n'a lieu qu'à la fin.
# =========================================================
from __future__ import annotations

import math
import re
import time
import tkinter as tk
import tkinter.font as tkfont

from . import theme
from .controls import Avatar, IconButton, PillButton, round_rect
from .scrollbar import ScrollArea

CODE_BG = "#121215"          # fond des blocs de code (plus profond que la bulle)
INLINE_BG = "#202024"        # fond du code inline

RE_FENCE = re.compile(r"```(\w*)\n?(.*?)```", re.S)
RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
RE_INLINE = re.compile(r"`([^`\n]+)`")


def extract_code_blocks(text: str):
    """[(lang, code), ...] dans l'ordre d'apparition."""
    return [(m.group(1) or "python", m.group(2).strip("\n"))
            for m in RE_FENCE.finditer(text or "")]


def strip_code_blocks(text: str) -> str:
    return RE_FENCE.sub("", text or "").strip()


class MessageRow(tk.Frame):
    """Un message : avatar à gauche (JIBI) ou bulle à droite (utilisateur)."""

    def __init__(self, master, role: str, text: str = "", *, max_px: int = 620,
                 name: str | None = None, meta: str = "",
                 on_expand=None, on_copy=None, bg=theme.BG):
        super().__init__(master, bg=bg)
        self.role = role
        self.max_px = max_px
        self.on_expand = on_expand
        self.on_copy = on_copy
        self._bg = bg
        self._plain = ""            # texte brut reçu (pour le rendu final)
        self._streamed = 0          # nb de caractères déjà insérés

        is_user = role == "user"
        self._card = theme.BUBBLE_USER if is_user else theme.BUBBLE_BOT

        holder = tk.Frame(self, bg=bg)
        holder.pack(fill="x", padx=theme.SPACE_LG, pady=(theme.SPACE_SM, 0))

        if not is_user:
            self.avatar = Avatar(holder, kind="bot", size=30, bg=bg)
            self.avatar.pack(side="left", anchor="n", pady=(2, 0))
            body_wrap = tk.Frame(holder, bg=bg)
            body_wrap.pack(side="left", fill="x", expand=True, padx=(12, 40))
        else:
            body_wrap = tk.Frame(holder, bg=bg)
            body_wrap.pack(side="right", fill="x", expand=True, padx=(60, 0))
            self.avatar = Avatar(holder, kind="user", label=name or "V",
                                 size=30, bg=bg)
            self.avatar.pack(side="right", anchor="n", padx=(12, 0), pady=(2, 0))

        # ---- en-tête de bulle (nom + heure)
        head = tk.Frame(body_wrap, bg=bg)
        head.pack(fill="x", padx=2, pady=(0, 5))
        tk.Label(head, text=("Vous" if is_user else (name or "JIBI")),
                 bg=bg, fg=theme.TEXT_SUB, font=theme.sans(9, bold=True),
                 anchor="e" if is_user else "w").pack(
            side="right" if is_user else "left")
        if meta:
            tk.Label(head, text=meta, bg=bg, fg=theme.TEXT_FAINT,
                     font=theme.sans(8), anchor="e" if is_user else "w").pack(
                side="left" if is_user else "right", padx=(8, 0))

        # ---- bulle
        self.bubble = tk.Frame(body_wrap, bg=self._card)
        self.bubble.pack(anchor="e" if is_user else "w")
        self._bubble_inner = tk.Frame(self.bubble, bg=self._card)
        self._bubble_inner.pack(padx=14, pady=11)

        # ---- corps texte
        self.text = self._make_text()
        self.text.pack(fill="x")

        # ---- actions (bouton copier / ouvrir le code)
        self.actions = tk.Frame(self.bubble, bg=self._card)
        self._action_packed = False

        # ---- hauteur de bulle calculée à partir du contenu
        self.text.bind("<Configure>", lambda _e: self._fit_height())
        if text:
            self.set_text(text)

    # -------------------------------------------------- factory texte
    def _make_text(self) -> tk.Text:
        f = tkfont.Font(font=theme.sans(11))
        chars = max(24, int(self.max_px / max(1, f.measure("n"))))
        t = tk.Text(self._bubble_inner, wrap="word", width=chars, height=1,
                    bg=self._card, fg=theme.TEXT, insertbackground=theme.TEXT,
                    selectbackground=theme.ACCENT_SOFT, selectforeground=theme.TEXT,
                    font=f, bd=0, padx=0, pady=0, spacing1=1, spacing3=5,
                    cursor="xterm", state="disabled", highlightthickness=0,
                    relief="flat", tabs=(), undo=False)
        t.tag_configure("bold", font=theme.sans(11, bold=True), foreground=theme.TEXT)
        t.tag_configure("h", font=theme.serif(13, bold=True), foreground=theme.TEXT,
                        spacing1=6, spacing3=4)
        t.tag_configure("inline", font=theme.mono(10), background=INLINE_BG,
                        foreground=theme.ACCENT)
        t.tag_configure("code", font=theme.mono(10), background=CODE_BG,
                        foreground=theme.TEXT, lmargin1=8, lmargin2=8,
                        spacing1=4, spacing3=4)
        t.tag_configure("codelang", font=theme.sans(8, bold=True),
                        foreground=theme.TEXT_FAINT, background=CODE_BG,
                        lmargin1=8, lmargin2=8)
        t.tag_configure("li", lmargin1=10, lmargin2=24)
        t.tag_configure("dim", foreground=theme.TEXT_DIM)
        return t

    # -------------------------------------------------- hauteur auto
    def _fit_height(self):
        try:
            n = self.text.count("1.0", "end-1c", "displaylines")
            lines = int(n[0]) if n else 1
        except Exception:
            lines = int(self.text.index("end-1c").split(".")[0])
        lines = max(1, lines)
        if int(self.text["height"]) != lines:
            self.text.configure(height=lines)

    # -------------------------------------------------- rendu complet
    def set_text(self, text: str):
        """Rendu riche (markdown léger). Utilisé pour le message final."""
        self._plain = text or ""
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._streamed = 0
        self._render_markdown(self._plain)
        t.configure(state="disabled")
        self._fit_height()
        self._refresh_actions()

    def _render_markdown(self, text: str):
        t = self.text
        pos = 0
        for m in RE_FENCE.finditer(text):
            if m.start() > pos:
                self._render_inline(text[pos:m.start()])
            lang, code = m.group(1) or "", m.group(2).strip("\n")
            t.insert("end", "\n")
            if lang:
                t.insert("end", f" {lang.upper()} \n", "codelang")
            t.insert("end", code + "\n", "code")
            t.insert("end", "\n")
            pos = m.end()
        if pos < len(text):
            self._render_inline(text[pos:])

    def _render_inline(self, chunk: str):
        """Gras, code inline, titres # et listes - / 1."""
        t = self.text
        for i, line in enumerate(chunk.split("\n")):
            if i:
                t.insert("end", "\n")
            stripped = line.strip()
            if stripped.startswith(("#", "##", "###")):
                t.insert("end", stripped.lstrip("# ").strip(), "h")
                continue
            if stripped.startswith(("- ", "* ", "• ")):
                t.insert("end", "  •  ", "li")
                self._render_spans(stripped[2:], "li")
                continue
            if re.match(r"^\d+[.)]\s", stripped):
                t.insert("end", "  " + stripped[:3], "li")
                self._render_spans(stripped[3:], "li")
                continue
            self._render_spans(line)

    def _render_spans(self, line: str, base_tag: str = ""):
        """Applique **gras** et `code` à l'intérieur d'une ligne."""
        t = self.text
        tags = (base_tag,) if base_tag else ()
        idx = 0
        # On traite gras puis code inline en une passe sur les positions.
        events = []
        for m in RE_BOLD.finditer(line):
            events.append((m.start(), m.end(), "bold", m.group(1)))
        for m in RE_INLINE.finditer(line):
            if not any(s <= m.start() < e for s, e, *_ in events):
                events.append((m.start(), m.end(), "inline", m.group(1)))
        events.sort()
        for start, end, tag, content in events:
            if start > idx:
                t.insert("end", line[idx:start], tags)
            t.insert("end", content, tags + (tag,))
            idx = end
        if idx < len(line):
            t.insert("end", line[idx:], tags)

    # -------------------------------------------------- streaming
    def append(self, chunk: str):
        """Ajoute uniquement le texte nouveau — pas de re-rendu complet."""
        if not chunk:
            return
        self._plain += chunk
        t = self.text
        t.configure(state="normal")
        t.insert("end", chunk)
        t.configure(state="disabled")
        self._streamed = len(self._plain)
        self._fit_height()

    def replace_streamed(self, full: str):
        """Bascule streaming -> rendu riche (appelé à la fin de la réponse)."""
        self.set_text(full)

    def set_plain(self, text: str):
        self._plain = text or ""

    # -------------------------------------------------- actions
    def _refresh_actions(self):
        codes = extract_code_blocks(self._plain)
        want = bool(codes) or (self.role == "assistant" and len(self._plain) > 40)
        if not want:
            if self._action_packed:
                self.actions.pack_forget()
                self._action_packed = False
            return
        if not self._action_packed:
            self.actions.pack(fill="x", pady=(8, 0))
            self._action_packed = True
        for w in self.actions.winfo_children():
            w.destroy()
        if codes:
            IconButton(self.actions, icon="code", kind="ghost", size=26,
                       icon_size=14, bg=self._card, tooltip="Ouvrir dans le panneau",
                       command=lambda: self._expand(codes[0])).pack(side="left")
        IconButton(self.actions, icon="copy", kind="ghost", size=26, icon_size=14,
                   bg=self._card, tooltip="Copier la réponse",
                   command=self._copy).pack(side="left", padx=(4, 0))

    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self._plain)
            if self.on_copy:
                self.on_copy()
        except Exception:
            pass

    def _expand(self, code):
        if self.on_expand:
            self.on_expand(code[0], code[1])

    def set_width(self, max_px: int):
        if max_px == self.max_px:
            return
        self.max_px = max_px
        f = tkfont.Font(font=theme.sans(11))
        chars = max(24, int(max_px / max(1, f.measure("n"))))
        self.text.configure(width=chars)
        self._fit_height()


class TypingRow(tk.Frame):
    """Ligne "JIBI réfléchit" : avatar + trois points qui respirent."""

    def __init__(self, master, *, bg=theme.BG):
        super().__init__(master, bg=bg)
        holder = tk.Frame(self, bg=bg)
        holder.pack(fill="x", padx=theme.SPACE_LG, pady=(theme.SPACE_SM, 0))
        Avatar(holder, kind="bot", size=30, bg=bg).pack(side="left", anchor="n", pady=(2, 0))
        self.bubble = tk.Frame(holder, bg=theme.BUBBLE_BOT)
        self.bubble.pack(side="left", padx=(12, 0), pady=0)
        inner = tk.Frame(self.bubble, bg=theme.BUBBLE_BOT)
        inner.pack(padx=14, pady=12)
        self.dots = tk.Canvas(inner, width=46, height=16, bg=theme.BUBBLE_BOT,
                              highlightthickness=0, bd=0)
        self.dots.pack()
        self._ids = [self.dots.create_oval(4 + i * 16, 4, 12 + i * 16, 12,
                                           fill=theme.ACCENT, outline=theme.ACCENT)
                     for i in range(3)]
        self._t0 = time.monotonic()
        self._loop()

    def _loop(self):
        # Boucle after() locale : décale la respiration de chaque point.
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        t = ((time.monotonic() - self._t0) / 1.4) % 1.0
        for i, d in enumerate(self._ids):
            p = (t + i * 0.2) % 1.0
            k = 0.5 - 0.5 * math.cos(2 * math.pi * p)
            col = theme.mix(theme.ACCENT_DARK, theme.ACCENT, 0.3 + 0.7 * k)
            try:
                self.dots.itemconfigure(d, fill=col, outline=col)
            except Exception:
                return
        self._after_id = self.after(16, self._loop)

    def stop(self):
        try:
            self.after_cancel(getattr(self, "_after_id", None))
        except Exception:
            pass


class ChatView(tk.Frame):
    def __init__(self, master, *,
                 on_expand_code=None, on_suggestion=None, bg=theme.BG):
        super().__init__(master, bg=bg)
        self.on_expand_code = on_expand_code
        self.on_suggestion = on_suggestion
        self._bg = bg
        self.rows: list[MessageRow] = []
        self._typing: TypingRow | None = None

        self.area = ScrollArea(self, bg=bg)
        self.area.pack(fill="both", expand=True)
        self._max_px = 620
        self.area.canvas.bind("<Configure>", self._on_resize)

        self._empty = tk.Frame(self.area.frame, bg=bg)
        self._build_empty()
        self._show_empty(True)   # état d'accueil au démarrage

    # -------------------------------------------------- état vide
    def _build_empty(self):
        e = self._empty
        inner = tk.Frame(e, bg=self._bg)
        inner.pack(pady=(90, 0))
        self.empty_title = tk.Label(inner, text="Comment puis-je vous aider ?",
                                    bg=self._bg, fg=theme.TEXT,
                                    font=theme.serif(24, bold=True))
        self.empty_title.pack()
        tk.Label(inner, text="Posez une question, demandez du code, ou lancez un diagnostic.",
                 bg=self._bg, fg=theme.TEXT_DIM, font=theme.sans(11)).pack(pady=(10, 26))
        self.chips = tk.Frame(inner, bg=self._bg)
        self.chips.pack()

    def set_suggestions(self, items):
        for w in self.chips.winfo_children():
            w.destroy()
        for label in (items or [])[:4]:
            PillButton(self.chips, text=label, kind="ghost", height=32, radius=16,
                       bg=self._bg,
                       command=lambda l=label: self.on_suggestion and self.on_suggestion(l)
                       ).pack(side="left", padx=4, pady=4)

    def _show_empty(self, on: bool):
        if on:
            self._empty.pack(fill="x")
        else:
            self._empty.pack_forget()

    # -------------------------------------------------- messages
    def add_user(self, text: str, meta: str = "") -> MessageRow:
        self._show_empty(False)
        row = MessageRow(self.area.frame, "user", text, max_px=self._max_px,
                         meta=meta, bg=self._bg)
        row.pack(fill="x", anchor="e")
        self.rows.append(row)
        self.after_add()
        return row

    def add_bot(self, text: str = "", meta: str = "") -> MessageRow:
        self._show_empty(False)
        row = MessageRow(self.area.frame, "assistant", text, max_px=self._max_px,
                         meta=meta, bg=self._bg,
                         on_expand=self.on_expand_code,
                         on_copy=lambda: self._flash_copied())
        row.pack(fill="x", anchor="w")
        self.rows.append(row)
        self.after_add()
        return row

    def after_add(self):
        self.area.bind_wheel_recursive()
        self.area.stick_to_bottom()

    def clear(self):
        self.hide_typing()
        for r in self.rows:
            r.destroy()
        self.rows = []
        self.area.clear()
        self._show_empty(True)

    # -------------------------------------------------- typing
    def show_typing(self):
        if self._typing is not None:
            return
        self._show_empty(False)
        self._typing = TypingRow(self.area.frame, bg=self._bg)
        self._typing.pack(fill="x", anchor="w")
        self.area.bind_wheel_recursive()
        self.area.stick_to_bottom()

    def hide_typing(self):
        if self._typing is not None:
            self._typing.stop()
            self._typing.destroy()
            self._typing = None

    # -------------------------------------------------- largeur
    def _on_resize(self, e):
        # La bulle occupe ~82% de la zone, bornée pour rester lisible.
        new = int(min(720, max(320, (e.width - 120) * 0.86)))
        if abs(new - self._max_px) < 8:
            return
        self._max_px = new
        for r in self.rows:
            r.set_width(new)
        self.area.stick_to_bottom()

    def _flash_copied(self):
        try:
            self.area.canvas.bell()
        except Exception:
            pass

    def scroll_to_bottom(self):
        self.area.stick_to_bottom()