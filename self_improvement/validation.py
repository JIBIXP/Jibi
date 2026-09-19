from __future__ import annotations

from .validateur import valider_syntaxe
from .politiques import politique_fichier


def analyser_modification(fichier: str, contenu: str) -> dict:
    securite = politique_fichier(fichier)
    syntaxe = valider_syntaxe(contenu, fichier)

    risques = list(securite.raisons)

    if not syntaxe.get("ok"):
        risques.append("syntaxe invalide")

    niveau = securite.niveau

    if not syntaxe.get("ok"):
        niveau = "bloqué"

    return {
        "ok": syntaxe.get("ok", False) and niveau != "critique",
        "niveau": niveau,
        "risques": risques,
        "syntaxe": syntaxe,
    }


def valider_modification(fichier: str, contenu: str) -> dict:
    return analyser_modification(fichier, contenu)


def securite_ok(fichier: str, contenu: str) -> bool:
    return analyser_modification(fichier, contenu).get("ok", False)