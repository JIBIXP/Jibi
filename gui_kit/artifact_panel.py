"""
JIBI GUI Kit — Artifact Panel
=============================
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox

from .controls import Divider, RoundedButton
from .theme import COLORS, FONT


class ArtifactPanel(tk.Frame):
    """
    Panneau d'affichage des artefacts JIBI.

    Compatible avec gui.py v12.

    Callbacks :
        on_save(title, content)
        on_close()
    """

    def __init__(
        self,
        master,
        on_save=None,
        on_close=None,
        state=None,
        **kwargs,
    ):
        # --------------------------------------------------------------
        # Paramètres applicatifs
        # --------------------------------------------------------------

        self.state = state
        self.on_save = on_save
        self.on_close = on_close

        # --------------------------------------------------------------
        # Paramètres Tkinter
        # --------------------------------------------------------------

        background = kwargs.pop(
            "bg",
            COLORS["surface"],
        )

        # Aucun callback applicatif ne doit arriver ici.
        super().__init__(
            master,
            bg=background,
            **kwargs,
        )

        # --------------------------------------------------------------
        # Données
        # --------------------------------------------------------------

        self.current_title = ""
        self.current_content = ""
        self.current_kind = ""
        self.is_visible = False

        self._build()

    # ==================================================================
    # BUILD
    # ==================================================================

    def _build(self):
        header = tk.Frame(
            self,
            bg=COLORS["surface"],
        )

        header.pack(
            fill="x",
            padx=14,
            pady=(12, 8),
        )

        self.title_label = tk.Label(
            header,
            text="Artefact",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=FONT["body_bold"],
        )

        self.title_label.pack(
            side="left",
        )

        # --------------------------------------------------------------
        # Bouton fermer
        # --------------------------------------------------------------

        self.close_button = tk.Button(
            header,
            text="×",
            command=self.close,
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=COLORS["surface"],
            fg=COLORS["text_dim"],
            activebackground=COLORS["surface"],
            activeforeground=COLORS["text"],
            font=("Segoe UI", 16),
            cursor="hand2",
            padx=8,
            pady=2,
        )

        self.close_button.pack(
            side="right",
        )

        # --------------------------------------------------------------
        # Bouton enregistrer
        # --------------------------------------------------------------

        self.save_button = RoundedButton(
            header,
            text="Enregistrer",
            command=self.save,
            bg=COLORS["accent"],
        )

        self.save_button.pack(
            side="right",
            padx=(0, 8),
        )

        Divider(
            self,
            color=COLORS["border"],
        ).pack(
            fill="x",
        )

        # --------------------------------------------------------------
        # Zone texte
        # --------------------------------------------------------------

        self.text = tk.Text(
            self,
            wrap="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=COLORS["surface_alt"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"],
            font=FONT["code"],
            padx=14,
            pady=14,
        )

        self.text.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10,
        )

        self.text.configure(
            state="disabled",
        )

    # ==================================================================
    # OPEN ARTIFACT
    # ==================================================================

    def open_artifact(
        self,
        kind: str,
        title: str,
        content: str,
        subtitle: str = "",
    ):
        """Ouvre le panneau avec un artefact."""
        
        self.current_kind = kind
        self.current_title = title or "Artefact"
        self.current_content = content or ""

        display_title = self.current_title
        if subtitle:
            display_title = f"{subtitle} • {self.current_title}"

        self.title_label.configure(
            text=display_title,
        )

        self.text.configure(
            state="normal",
        )

        self.text.delete(
            "1.0",
            "end",
        )

        self.text.insert(
            "1.0",
            self.current_content,
        )

        self.text.configure(
            state="disabled",
        )

        if not self.is_visible:
            self.restore()

    # ==================================================================
    # CONTENT
    # ==================================================================

    def set_content(
        self,
        title: str,
        content: str,
    ):
        self.current_title = (
            title or "Artefact"
        )

        self.current_content = (
            content or ""
        )

        self.title_label.configure(
            text=self.current_title,
        )

        self.text.configure(
            state="normal",
        )

        self.text.delete(
            "1.0",
            "end",
        )

        self.text.insert(
            "1.0",
            self.current_content,
        )

        self.text.configure(
            state="disabled",
        )

    def get_content(self) -> str:
        self.text.configure(
            state="normal",
        )

        value = self.text.get(
            "1.0",
            "end-1c",
        )

        self.text.configure(
            state="disabled",
        )

        return value

    def clear(self):
        self.current_title = ""
        self.current_content = ""
        self.current_kind = ""

        self.title_label.configure(
            text="Artefact",
        )

        self.text.configure(
            state="normal",
        )

        self.text.delete(
            "1.0",
            "end",
        )

        self.text.configure(
            state="disabled",
        )

    # ==================================================================
    # VISIBILITY
    # ==================================================================

    def restore(self):
        """Affiche le panneau."""
        if not self.is_visible:
            self.pack(
                side="right",
                fill="y",
            )
            self.is_visible = True

    # ==================================================================
    # CLOSE
    # ==================================================================

    def close(self):
        """Ferme le panneau via le callback fourni par gui.py."""

        if self.on_close:
            self.on_close()
            return

        # Fallback : masquer le panneau.
        try:
            self.pack_forget()
            self.is_visible = False
        except tk.TclError:
            pass

    # ==================================================================
    # SAVE
    # ==================================================================

    def save(self):
        content = self.get_content()

        if not content:
            messagebox.showinfo(
                "Artefact",
                "Aucun contenu à enregistrer.",
            )
            return

        # --------------------------------------------------------------
        # Callback gui.py
        # --------------------------------------------------------------

        if self.on_save:
            result = self.on_save(
                self.current_kind,
                self.current_title,
                content,
            )

            if result:
                return

        # --------------------------------------------------------------
        # Sauvegarde locale
        # --------------------------------------------------------------

        path = filedialog.asksaveasfilename(
            title="Enregistrer l'artefact",
            defaultextension=".txt",
            filetypes=[
                (
                    "Fichiers texte",
                    "*.txt",
                ),
                (
                    "Python",
                    "*.py",
                ),
                (
                    "Tous les fichiers",
                    "*.*",
                ),
            ],
        )

        if not path:
            return

        try:
            with open(
                path,
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(content)

            messagebox.showinfo(
                "Artefact",
                "Artefact enregistré.",
            )

        except OSError as exc:
            messagebox.showerror(
                "Erreur",
                f"Impossible d'enregistrer :\n{exc}",
            )