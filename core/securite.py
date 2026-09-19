"""
SÉCURITÉ JIBI

Responsabilité :
    Centraliser les contrôles de sécurité concernant
    les fichiers, chemins et actions.

Ce module ne :
    - modifie aucun fichier ;
    - ne crée aucun backup ;
    - n'applique aucun patch ;
    - n'autorise pas une modification à lui seul.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional


try:
    from core import config
except Exception:
    config = None


# ============================================================
# MOTIFS SENSIBLES
# ============================================================

MOTIFS_SENSIBLES = (
    "mot de passe",
    "password",
    "token",
    "api key",
    "apikey",
    "clé privée",
    "cle privee",
    "private key",
    ".env",
    "secret",
    "credential",
    "credentials",
)


EXTENSIONS_SENSIBLES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
}


REPERTOIRES_SENSIBLES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
}


# ============================================================
# TEXTE
# ============================================================

def est_texte_sensible(texte: Any) -> bool:
    """Détecte les références évidentes à des secrets."""

    if texte is None:
        return False

    valeur = str(texte).lower()

    return any(
        motif in valeur
        for motif in MOTIFS_SENSIBLES
    )


# ============================================================
# FICHIER
# ============================================================

def est_fichier_secret(
    chemin: Any,
) -> bool:
    """Détermine si un chemin correspond à un secret."""

    if chemin is None:
        return False

    try:
        path = Path(str(chemin))
    except Exception:
        return True

    nom = path.name.lower()

    if nom.startswith(".env"):
        return True

    if path.suffix.lower() in EXTENSIONS_SENSIBLES:
        return True

    if any(
        partie.lower() in REPERTOIRES_SENSIBLES
        for partie in path.parts
    ):
        return True

    return False


def est_fichier_critique(
    chemin: Any,
) -> bool:
    """Utilise la configuration centrale pour les fichiers critiques."""

    if chemin is None:
        return True

    if config is not None:

        try:
            fonction = getattr(
                config,
                "est_fichier_critique",
                None,
            )

            if callable(fonction):
                return bool(
                    fonction(chemin)
                )

        except Exception:
            pass

    return False


# ============================================================
# CHEMINS
# ============================================================

def chemin_dans_projet(
    chemin: Any,
    projet: Optional[Any] = None,
) -> bool:
    """
    Vérifie qu'un chemin se trouve réellement dans le projet.

    Les chemins absolus extérieurs au projet sont refusés.
    """

    if chemin is None:
        return False

    try:

        if projet is None:

            if config is not None:
                projet = getattr(
                    config,
                    "PROJECT_ROOT",
                    None,
                )

                if projet is None:
                    projet = getattr(
                        config,
                        "JIBI_PROJET_DIR",
                        None,
                    )

        if projet is None:
            return False

        root = Path(projet).resolve()
        cible = Path(chemin)

        if not cible.is_absolute():
            cible = root / cible

        cible = cible.resolve()

        try:
            cible.relative_to(root)
            return True
        except ValueError:
            return False

    except Exception:
        return False


def normaliser_chemin(
    chemin: Any,
) -> Optional[str]:
    """Retourne un chemin relatif normalisé si possible."""

    if chemin is None:
        return None

    try:

        valeur = str(chemin).strip()

        if not valeur:
            return None

        path = Path(valeur)

        if path.is_absolute():
            return None

        # Refuse explicitement les traversées.
        if ".." in path.parts:
            return None

        return path.as_posix()

    except Exception:
        return None


# ============================================================
# LECTURE
# ============================================================

def peut_lire_fichier(
    chemin: Any,
) -> bool:
    """
    Vérifie si JIBI peut lire un fichier.

    Les secrets restent interdits par défaut.
    """

    if est_fichier_secret(chemin):
        return False

    if not chemin_dans_projet(chemin):
        return False

    if config is not None:

        try:
            fonction = getattr(
                config,
                "peut_lire_fichier",
                None,
            )

            if callable(fonction):
                return bool(
                    fonction(chemin)
                )

        except Exception:
            return False

    return True


# ============================================================
# MODIFICATION
# ============================================================

def peut_modifier_fichier(
    chemin: Any,
) -> bool:
    """
    Vérification préliminaire uniquement.

    L'autorisation finale appartient à l'orchestrateur
    et au moteur d'autorisation.
    """

    if est_fichier_secret(chemin):
        return False

    if est_fichier_critique(chemin):
        return False

    if not chemin_dans_projet(chemin):
        return False

    normalise = normaliser_chemin(chemin)

    if normalise is None:
        return False

    if not normalise.lower().endswith(".py"):
        return False

    if config is not None:

        try:
            fonction = getattr(
                config,
                "peut_modifier_fichier",
                None,
            )

            if callable(fonction):
                return bool(
                    fonction(chemin)
                )

        except Exception:
            return False

    return True


# ============================================================
# VALIDATION GÉNÉRALE
# ============================================================

def valider_securite_fichier(
    chemin: Any,
    modification: bool = False,
) -> bool:
    """Contrôle global d'un fichier."""

    if modification:
        return peut_modifier_fichier(chemin)

    return peut_lire_fichier(chemin)


def est_action_dangereuse(
    action: Any,
) -> bool:
    """
    Détecte les actions nécessitant un contrôle renforcé.
    """

    if action is None:
        return False

    texte = str(action).lower()

    motifs = (
        "supprimer",
        "delete",
        "effacer",
        "format",
        "désinstaller",
        "desinstaller",
        "exécuter commande",
        "executer commande",
        "shell",
        "powershell",
        "cmd ",
    )

    return any(
        motif in texte
        for motif in motifs
    )


__all__ = [
    "MOTIFS_SENSIBLES",
    "EXTENSIONS_SENSIBLES",
    "REPERTOIRES_SENSIBLES",
    "est_texte_sensible",
    "est_fichier_secret",
    "est_fichier_critique",
    "chemin_dans_projet",
    "normaliser_chemin",
    "peut_lire_fichier",
    "peut_modifier_fichier",
    "valider_securite_fichier",
    "est_action_dangereuse",
]