"""
ROUTER JIBI

Responsabilité :
    Identifier rapidement l'intention d'un message
    avant de solliciter le LLM.

Le router ne :
    - modifie aucun fichier ;
    - n'exécute aucun outil ;
    - ne prend aucune décision de sécurité.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


INTENTIONS = {
    "DISCUSSION",
    "QUESTION",
    "DIAGNOSTIC",
    "ANALYSE_CODE",
    "ETAT",
    "LISTE",
    "RECHERCHE",
    "OUVRIR_URL",
    "CONFIRMATION",
    "REJET",
    "MODIFIER_FICHIER",
    "CREER_OUTIL",
    "EXECUTER_OUTIL",
    "TACHE_COMPLEXE",
}


def normaliser_message(message: Any) -> str:
    """Normalise un message utilisateur."""
    return str(message).strip() if message is not None else ""


def classification_locale(message: Any) -> Optional[str]:
    """
    Classification rapide sans LLM.

    Retourne None lorsque le message nécessite
    une classification plus poussée.
    """

    texte = normaliser_message(message)
    low = texte.lower()

    if not low:
        return "DISCUSSION"

    # --------------------------------------------------------
    # DISCUSSION
    # --------------------------------------------------------

    if low in {
        "bonjour",
        "salut",
        "hello",
        "bonsoir",
        "coucou",
        "hey",
        "yo",
    }:
        return "DISCUSSION"

    # --------------------------------------------------------
    # DIAGNOSTIC (santé du système uniquement)
    # --------------------------------------------------------

    if low in {
        "diagnostic",
        "diagnostique",
        "diagnostiquer",
        "analyse jibi",
        "analyser jibi",
        "diagnostic jibi",
        "diagnostiquer jibi",
        "diagnostic système",
        "diagnostic systeme",
    }:
        return "DIAGNOSTIC"

    # --------------------------------------------------------
    # ANALYSE CODE (fichiers/modules Python)
    # --------------------------------------------------------

    if (
        re.search(
            r"\b(analyse|analyser|inspecte|inspecter|examine|examiner)\b",
            low,
        )
        and (
            ".py" in low
            or "fichier" in low
            or "code" in low
            or "projet" in low
            or "architecture" in low
            or "module" in low
        )
    ):
        return "ANALYSE_CODE"

    # --------------------------------------------------------
    # ETAT
    # --------------------------------------------------------

    if low in {
        "état",
        "etat",
        "état jibi",
        "etat jibi",
        "status",
        "statut",
        "état du système",
        "etat du systeme",
    }:
        return "ETAT"

    # --------------------------------------------------------
    # LISTE
    # --------------------------------------------------------

    if low in {
        "liste",
        "propositions",
        "propositions en attente",
        "améliorations",
        "ameliorations",
        "liste des propositions",
    }:
        return "LISTE"

    # --------------------------------------------------------
    # RECHERCHE
    # --------------------------------------------------------

    if low.startswith(
        (
            "recherche ",
            "cherche ",
            "cherche sur le web ",
            "recherche sur le web ",
            "google ",
        )
    ):
        return "RECHERCHE"

    # --------------------------------------------------------
    # URL
    # --------------------------------------------------------

    if re.search(
        r"https?://[^\s]+",
        texte,
        re.IGNORECASE,
    ):
        if low.startswith(
            (
                "ouvre ",
                "ouvrir ",
                "va sur ",
                "aller sur ",
                "lance ",
            )
        ):
            return "OUVRIR_URL"

    # --------------------------------------------------------
    # CONFIRMATION
    # --------------------------------------------------------

    if re.match(
        r"^(confirme|autorise|j'autorise|je confirme)\b",
        low,
    ):
        return "CONFIRMATION"

    # --------------------------------------------------------
    # REJET
    # --------------------------------------------------------

    if re.match(
        r"^(rejette|refuse|je rejette|je refuse)\b",
        low,
    ):
        return "REJET"

    # --------------------------------------------------------
    # MODIFICATION
    # --------------------------------------------------------

    if re.match(
        r"^(modifie|modifier|change|changer|corrige|corriger)\b",
        low,
    ):
        return "MODIFIER_FICHIER"

    if any(
        motif in low
        for motif in (
            "modifie le fichier",
            "modifier le fichier",
            "corrige le fichier",
            "corriger le fichier",
            "répare le fichier",
            "repare le fichier",
            "répare jibi",
            "repare jibi",
        )
    ):
        return "MODIFIER_FICHIER"

    # --------------------------------------------------------
    # CREATION OUTIL
    # --------------------------------------------------------

    if re.match(
        r"^(crée|cree|créé|creer|créer)\b",
        low,
    ):
        if any(
            mot in low
            for mot in (
                "outil",
                "fonction",
                "tool",
            )
        ):
            return "CREER_OUTIL"

    if any(
        motif in low
        for motif in (
            "créer un outil",
            "creer un outil",
            "crée un outil",
            "cree un outil",
            "nouvel outil",
            "nouvelle fonction",
        )
    ):
        return "CREER_OUTIL"

    # --------------------------------------------------------
    # EXECUTION OUTIL
    # --------------------------------------------------------

    if any(
        motif in low
        for motif in (
            "exécute l'outil",
            "execute l'outil",
            "exécuter l'outil",
            "executer l'outil",
            "lance l'outil",
            "lancer l'outil",
        )
    ):
        return "EXECUTER_OUTIL"

    # --------------------------------------------------------
    # QUESTION SIMPLE
    # --------------------------------------------------------

    if (
        low.endswith("?")
        or low.startswith(
            (
                "qui ",
                "quoi ",
                "que ",
                "quel ",
                "quelle ",
                "quels ",
                "quelles ",
                "comment ",
                "pourquoi ",
                "quand ",
                "où ",
                "ou ",
                "est-ce ",
            )
        )
    ):
        return "QUESTION"

    return None


def normaliser_intention(
    intention: Any,
) -> Optional[str]:
    """Normalise et vérifie une intention."""

    if intention is None:
        return None

    valeur = str(intention).strip().upper()

    aliases = {
        "RECHERCHER_WEB": "RECHERCHE",
        "RECHERCHE_WEB": "RECHERCHE",
        "SEARCH": "RECHERCHE",
        "OPEN_URL": "OUVRIR_URL",
        "OPEN": "OUVRIR_URL",
        "CREATE_TOOL": "CREER_OUTIL",
        "EXECUTE_TOOL": "EXECUTER_OUTIL",
        "EDIT_FILE": "MODIFIER_FICHIER",
        "MODIFY_FILE": "MODIFIER_FICHIER",
        "CHAT": "DISCUSSION",
        "ANALYZE_CODE": "ANALYSE_CODE",
        "CODE_ANALYSIS": "ANALYSE_CODE",
    }

    valeur = aliases.get(
        valeur,
        valeur,
    )

    if valeur not in INTENTIONS:
        return None

    return valeur


def extraire_plan(plan: Any) -> Dict[str, Any]:
    """
    Nettoie un plan provenant du cerveau.

    Aucun effet de bord.
    """

    if not isinstance(plan, dict):
        return {}

    resultat = dict(plan)

    intention = normaliser_intention(
        resultat.get("intention")
    )

    if intention is not None:
        resultat["intention"] = intention

    return resultat


def router_message(
    message: Any,
) -> Optional[str]:
    """Point d'entrée principal pour la classification locale."""

    return classification_locale(message)


__all__ = [
    "INTENTIONS",
    "normaliser_message",
    "classification_locale",
    "normaliser_intention",
    "extraire_plan",
    "router_message",
]
