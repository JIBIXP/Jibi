# -*- coding: utf-8 -*-
"""
JIBI - Générateur de patch
==========================

Construit des objets Patch à partir de contenus candidats.

IMPORTANT :
    Ce module est PUREMENT génératif.

    Il ne :
        - modifie aucun fichier de production ;
        - n'applique aucun patch ;
        - ne crée aucune autorisation ;
        - ne décide pas si un patch est sûr.

La validation et l'application appartiennent aux autres modules.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class Patch:
    """Représente une modification proposée."""

    fichier: str
    ancien_contenu: str
    nouveau_contenu: str
    raison: str = ""
    source: str = "jibi"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def hash_avant(self) -> str:
        return hashlib.sha256(
            self.ancien_contenu.encode("utf-8")
        ).hexdigest()

    @property
    def hash_apres(self) -> str:
        return hashlib.sha256(
            self.nouveau_contenu.encode("utf-8")
        ).hexdigest()

    @property
    def nombre_lignes_ajoutees(self) -> int:
        diff = difflib.unified_diff(
            self.ancien_contenu.splitlines(),
            self.nouveau_contenu.splitlines(),
        )

        return sum(
            1
            for ligne in diff
            if ligne.startswith("+")
            and not ligne.startswith("+++")
        )

    @property
    def nombre_lignes_supprimees(self) -> int:
        diff = difflib.unified_diff(
            self.ancien_contenu.splitlines(),
            self.nouveau_contenu.splitlines(),
        )

        return sum(
            1
            for ligne in diff
            if ligne.startswith("-")
            and not ligne.startswith("---")
        )

    def to_dict(
        self,
        inclure_contenu: bool = True,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "fichier": self.fichier,
            "raison": self.raison,
            "source": self.source,
            "hash_avant": self.hash_avant,
            "hash_apres": self.hash_apres,
            "lignes_ajoutees": self.nombre_lignes_ajoutees,
            "lignes_supprimees": self.nombre_lignes_supprimees,
            "metadata": self.metadata,
        }

        if inclure_contenu:
            data["ancien_contenu"] = self.ancien_contenu
            data["nouveau_contenu"] = self.nouveau_contenu

        return data


def analyser_syntaxe(
    contenu: str,
    nom: str = "<patch>",
) -> tuple[bool, Optional[str]]:
    """Vérifie la syntaxe Python sans modifier quoi que ce soit."""

    try:
        ast.parse(
            contenu,
            filename=nom,
        )
        return True, None

    except SyntaxError as exc:
        ligne = exc.lineno or "?"
        return (
            False,
            f"ligne {ligne}: {exc.msg}",
        )


def lire_contenu_fichier(
    fichier: str | Path,
) -> str:
    """Lit un fichier Python sans le modifier."""

    path = Path(fichier)

    if not path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Le chemin n'est pas un fichier : {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )


def construire_patch(
    fichier: str | Path,
    ancien_contenu: str,
    nouveau_contenu: str,
    raison: str = "",
    source: str = "jibi",
    metadata: Optional[dict[str, Any]] = None,
) -> Patch:
    """
    Construit un patch depuis deux contenus.

    Aucune écriture disque.
    """

    if not isinstance(ancien_contenu, str):
        raise TypeError(
            "ancien_contenu doit être une chaîne."
        )

    if not isinstance(nouveau_contenu, str):
        raise TypeError(
            "nouveau_contenu doit être une chaîne."
        )

    if ancien_contenu == nouveau_contenu:
        raise ValueError(
            "Aucune modification détectée."
        )

    valide, erreur = analyser_syntaxe(
        nouveau_contenu,
        str(fichier),
    )

    if not valide:
        raise ValueError(
            f"Syntaxe invalide : {erreur}"
        )

    return Patch(
        fichier=str(Path(fichier)),
        ancien_contenu=ancien_contenu,
        nouveau_contenu=nouveau_contenu,
        raison=raison,
        source=source,
        metadata=metadata or {},
    )


def generer_patch(
    fichier: str | Path,
    nouveau_contenu: str,
    raison: str = "",
    source: str = "jibi",
    metadata: Optional[dict[str, Any]] = None,
) -> Patch:
    """
    Lit le contenu actuel et construit un patch candidat.

    Cette fonction ne modifie jamais le fichier.
    """

    ancien_contenu = lire_contenu_fichier(
        fichier
    )

    return construire_patch(
        fichier=fichier,
        ancien_contenu=ancien_contenu,
        nouveau_contenu=nouveau_contenu,
        raison=raison,
        source=source,
        metadata=metadata,
    )


def generer_diff(
    patch: Patch,
) -> str:
    """Produit le diff lisible du patch."""

    lignes = difflib.unified_diff(
        patch.ancien_contenu.splitlines(),
        patch.nouveau_contenu.splitlines(),
        fromfile=f"{patch.fichier} (avant)",
        tofile=f"{patch.fichier} (après)",
        lineterm="",
    )

    return "\n".join(lignes)


def verifier_coherence(
    patch: Patch,
) -> dict[str, Any]:
    """Effectue les contrôles de cohérence de base."""

    syntaxe_ok, erreur = analyser_syntaxe(
        patch.nouveau_contenu,
        patch.fichier,
    )

    modification = (
        patch.ancien_contenu
        != patch.nouveau_contenu
    )

    return {
        "ok": syntaxe_ok and modification,
        "syntaxe_ok": syntaxe_ok,
        "modification": modification,
        "erreur": erreur,
        "fichier": patch.fichier,
        "hash_avant": patch.hash_avant,
        "hash_apres": patch.hash_apres,
        "lignes_ajoutees": (
            patch.nombre_lignes_ajoutees
        ),
        "lignes_supprimees": (
            patch.nombre_lignes_supprimees
        ),
    }


def patch_depuis_contenu(
    fichier: str | Path,
    ancien_contenu: str,
    nouveau_contenu: str,
    raison: str = "",
    source: str = "jibi",
    metadata: Optional[dict[str, Any]] = None,
) -> Patch:
    """Construit un patch sans relire le fichier."""

    return construire_patch(
        fichier=fichier,
        ancien_contenu=ancien_contenu,
        nouveau_contenu=nouveau_contenu,
        raison=raison,
        source=source,
        metadata=metadata,
    )


__all__ = [
    "Patch",
    "analyser_syntaxe",
    "lire_contenu_fichier",
    "construire_patch",
    "generer_patch",
    "generer_diff",
    "verifier_coherence",
    "patch_depuis_contenu",
]