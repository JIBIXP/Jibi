"""
JIBI — Évolution
================

Façade de compatibilité historique.

IMPORTANT
---------
evolution.py n'est plus le centre décisionnel de JIBI.

La logique centrale est :

    cerveau
        ↓
    generateur_patch
        ↓
    propositions
        ↓
    laboratoire
        ↓
    validateur / testeur
        ↓
    risk_engine
        ↓
    politiques
        ↓
    orchestrateur
        ↓
    versions
        ↓
    application
        ↓
    rollback

Ce module conserve uniquement les anciennes fonctions publiques
pour éviter de casser les appels historiques.

Il ne doit pas :
    - générer du code ;
    - décider seul d'une réparation ;
    - écrire directement en production ;
    - gérer sa propre logique de sécurité ;
    - gérer ses propres backups ;
    - gérer son propre rollback ;
    - contourner l'orchestrateur.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ============================================================================
# CONFIGURATION
# ============================================================================

try:
    from core.config import JIBI_PROJET_DIR

    DEPOT = Path(
        JIBI_PROJET_DIR
    ).resolve()

except Exception:
    DEPOT = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )


# ============================================================================
# MODULES CENTRAUX
# ============================================================================

from . import laboratoire
from . import propositions
from . import rollback
from . import testeur
from . import versions

try:
    from . import politiques
except Exception:
    politiques = None

try:
    from . import orchestrateur
except Exception:
    orchestrateur = None


# ============================================================================
# COMPATIBILITÉ — CHEMINS
# ============================================================================

DIR = (
    DEPOT
    / "workspace"
    / "jibi_lab"
    / "evolutions"
)

BACKUPS = (
    DEPOT
    / "workspace"
    / "backups"
    / "evolutions"
)


# ============================================================================
# COMPATIBILITÉ — POLITIQUES
# ============================================================================

FICHIERS_CRITIQUES = {
    "core/agent_core.py",
    "core/cerveau.py",
    "core/config.py",
    "self_improvement/evolution.py",
    "self_improvement/gestionnaire.py",
    "self_improvement/orchestrateur.py",
    "self_improvement/validateur.py",
    "self_improvement/risk_engine.py",
}

# Volontairement vide :
# l'auto-application appartient à l'orchestrateur + politiques.
FICHIERS_AUTO_APPLICABLES: set[str] = set()

SEUIL_DIFF_AUTO_LIGNES = 30


# ============================================================================
# LOG
# ============================================================================

def _log(
    message: str,
) -> None:
    """Journalise sans rendre le logger obligatoire."""

    try:
        from logging_jibi import log_event

        log_event(
            "evolution",
            message,
        )

    except Exception:
        pass


# ============================================================================
# CHEMINS
# ============================================================================

def _normaliser_chemin(
    fichier: str | Path,
) -> str:
    """Normalise un chemin pour les comparaisons internes."""

    return (
        str(fichier)
        .replace("\\", "/")
        .strip()
        .lstrip("./")
    )


def _chemin_depot(
    fichier: str | Path,
) -> Path:
    """Résout un chemin relativement au dépôt."""

    return (
        DEPOT
        / _normaliser_chemin(fichier)
    ).resolve()


# ============================================================================
# PROTECTION — COMPATIBILITÉ
# ============================================================================

def protege(
    fichier: str,
) -> tuple[bool, str]:
    """
    Compatibilité historique.

    Retour :
        (True, raison)  -> fichier bloqué
        (False, "")      -> pas de blocage détecté

    La politique centrale reste prioritaire.
    """

    fichier = _normaliser_chemin(
        fichier
    )

    if not fichier:
        return True, "Chemin vide."

    if politiques is not None:

        try:
            fonction = getattr(
                politiques,
                "politique_fichier",
                None,
            )

            if callable(fonction):

                politique = fonction(
                    fichier
                )

                niveau = str(
                    getattr(
                        politique,
                        "niveau",
                        "",
                    )
                ).lower()

                raisons = list(
                    getattr(
                        politique,
                        "raisons",
                        (),
                    )
                )

                if niveau in {
                    "bloqué",
                    "bloque",
                }:

                    return (
                        True,
                        raisons[0]
                        if raisons
                        else "Fichier bloqué par la politique.",
                    )

        except Exception as exc:
            _log(
                f"Politique indisponible pour "
                f"{fichier}: {exc}"
            )

    # Barrière minimale de compatibilité.

    path = Path(fichier)

    if path.is_absolute():
        return True, "Chemin absolu interdit."

    if ".." in path.parts:
        return True, "Traversal '..' interdit."

    if path.suffix.lower() != ".py":
        return (
            True,
            "Seuls les fichiers Python .py sont gérés.",
        )

    try:
        cible = _chemin_depot(
            fichier
        )

        cible.relative_to(
            DEPOT
        )

    except (
        OSError,
        ValueError,
    ):
        return (
            True,
            "Chemin hors du dépôt.",
        )

    parties = {
        partie.lower()
        for partie in path.parts
    }

    dossiers_bloques = {
        ".git",
        ".ssh",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
    }

    bloques = (
        parties
        & dossiers_bloques
    )

    if bloques:

        return (
            True,
            f"Dossier protégé : "
            f"{sorted(bloques)[0]}/",
        )

    fichiers_bloques = {
        ".env",
        "secrets.json",
        "authorized_keys",
    }

    if path.name.lower() in {
        nom.lower()
        for nom in fichiers_bloques
    }:

        return (
            True,
            f"Fichier protégé : {path.name}",
        )

    return False, ""


def est_critique(
    fichier: str,
) -> bool:
    """
    Compatibilité historique.

    La politique centrale est prioritaire lorsqu'elle est disponible.
    """

    fichier = _normaliser_chemin(
        fichier
    )

    if politiques is not None:

        try:
            fonction = getattr(
                politiques,
                "politique_fichier",
                None,
            )

            if callable(fonction):

                politique = fonction(
                    fichier
                )

                niveau = str(
                    getattr(
                        politique,
                        "niveau",
                        "",
                    )
                ).lower()

                if niveau == "critique":
                    return True

        except Exception:
            pass

    return (
        fichier
        in FICHIERS_CRITIQUES
    )


# ============================================================================
# PROPOSITIONS
# ============================================================================

def charger(
    proposition_id: str,
) -> dict[str, Any] | None:
    """Charge une proposition via propositions.py."""

    try:
        return propositions.charger_proposition(
            proposition_id
        )

    except Exception as exc:
        _log(
            f"Chargement proposition "
            f"{proposition_id} impossible: {exc}"
        )
        return None


def lister(
    statut: str | None = None,
) -> list[dict[str, Any]]:
    """Liste les propositions via propositions.py."""

    try:

        fonction = getattr(
            propositions,
            "lister_propositions",
            None,
        )

        if not callable(fonction):
            return []

        try:
            resultats = fonction(
                statut=statut
            )

        except TypeError:
            resultats = fonction()

        if not isinstance(
            resultats,
            list,
        ):
            return []

        if statut is not None:

            resultats = [
                proposition
                for proposition in resultats
                if proposition.get(
                    "statut"
                ) == statut
            ]

        return resultats

    except Exception as exc:
        _log(
            f"Listing propositions impossible: {exc}"
        )
        return []


# ============================================================================
# VALIDATION
# ============================================================================

def tester_contenu(
    fichier: str,
    contenu: str,
) -> dict[str, Any]:
    """
    Compatibilité historique vers testeur.py.

    Aucun fichier de production n'est modifié.
    """

    try:

        fonction = getattr(
            testeur,
            "tester_fichier",
            None,
        )

        if not callable(fonction):

            return {
                "ok": False,
                "details": [
                    "testeur.tester_fichier indisponible."
                ],
                "risques": [
                    "testeur_indisponible"
                ],
            }

        try:

            resultat = fonction(
                fichier,
                contenu,
            )

        except TypeError:

            resultat = fonction(
                fichier
            )

        if isinstance(
            resultat,
            dict,
        ):
            return resultat

        return {
            "ok": bool(resultat),
            "details": [],
            "risques": [],
        }

    except Exception as exc:

        return {
            "ok": False,
            "details": [
                f"❌ Test impossible : {exc}"
            ],
            "risques": [
                "test_exception"
            ],
        }


# ============================================================================
# PROPOSITION
# ============================================================================

def proposer(
    fichier: str,
    demande: str,
    nouveau_contenu: str,
    origine: str = "agent",
    priorite: str = "moyenne",
) -> dict[str, Any]:
    """
    Compatibilité historique.

    Crée uniquement une proposition.
    Ne modifie jamais la production.
    """

    fichier = _normaliser_chemin(
        fichier
    )

    bloque, raison = protege(
        fichier
    )

    if bloque:

        return {
            "ok": False,
            "message": f"🚫 {raison}",
        }

    cible = _chemin_depot(
        fichier
    )

    try:

        if not cible.exists():

            return {
                "ok": False,
                "message": (
                    "Fichier cible introuvable."
                ),
            }

        if not cible.is_file():

            return {
                "ok": False,
                "message": (
                    "La cible n'est pas un fichier."
                ),
            }

        ancien = cible.read_text(
            encoding="utf-8-sig"
        )

        fonction = getattr(
            propositions,
            "creer_proposition",
            None,
        )

        if not callable(fonction):

            return {
                "ok": False,
                "message": (
                    "propositions.creer_proposition "
                    "indisponible."
                ),
            }

        proposition = fonction(
            fichier=fichier,
            probleme=demande,
            ancien=ancien,
            nouveau=nouveau_contenu,
            origine=origine,
            priorite=priorite,
        )

        if not isinstance(
            proposition,
            dict,
        ):

            return {
                "ok": False,
                "message": (
                    "Proposition invalide."
                ),
            }

        return {
            "ok": True,
            "proposition": proposition,
            "production_modifiee": False,
        }

    except Exception as exc:

        _log(
            f"Création proposition impossible: {exc}"
        )

        return {
            "ok": False,
            "message": str(exc),
            "type_erreur": type(exc).__name__,
        }


# ============================================================================
# REJET
# ============================================================================

def rejeter(
    proposition_id: str,
    raison: str = "",
) -> dict[str, Any]:
    """
    Rejette une proposition.

    La décision passe par l'orchestrateur lorsqu'il est disponible.
    """

    if orchestrateur is not None:

        fonction = getattr(
            orchestrateur,
            "rejeter",
            None,
        )

        if callable(fonction):

            try:
                return fonction(
                    proposition_id,
                    raison,
                )

            except TypeError:
                return fonction(
                    proposition_id
                )

            except Exception as exc:

                return {
                    "ok": False,
                    "succes": False,
                    "message": str(exc),
                }

    # Compatibilité minimale si l'orchestrateur
    # n'est temporairement pas importable.

    try:

        fonction = getattr(
            propositions,
            "marquer_rejete",
            None,
        )

        if callable(fonction):

            return fonction(
                proposition_id,
                raison,
            )

    except Exception:
        pass

    return {
        "ok": False,
        "succes": False,
        "message": (
            "Rejet indisponible : "
            "orchestrateur non disponible."
        ),
    }


# ============================================================================
# APPLICATION
# ============================================================================

def appliquer(
    proposition_id: str,
    confirmation: str | None = None,
) -> dict[str, Any]:
    """
    Applique une proposition via l'orchestrateur.

    IMPORTANT :
        aucune écriture directe ici.
    """

    if confirmation is None:

        return {
            "ok": False,
            "succes": False,
            "message": (
                "Confirmation explicite requise."
            ),
        }

    if orchestrateur is None:

        return {
            "ok": False,
            "succes": False,
            "message": (
                "Orchestrateur indisponible."
            ),
        }

    fonction = getattr(
        orchestrateur,
        "appliquer",
        None,
    )

    if not callable(fonction):

        return {
            "ok": False,
            "succes": False,
            "message": (
                "orchestrateur.appliquer "
                "indisponible."
            ),
        }

    try:

        return fonction(
            proposition_id,
            confirmation,
        )

    except Exception as exc:

        return {
            "ok": False,
            "succes": False,
            "message": str(exc),
            "type_erreur": type(exc).__name__,
        }


def appliquer_auto(
    proposition_id: str,
) -> dict[str, Any]:
    """
    Demande une auto-application à l'orchestrateur.

    Le gestionnaire de compatibilité ne décide jamais
    si la proposition est réellement auto-applicable.
    """

    if orchestrateur is None:

        return {
            "ok": False,
            "succes": False,
            "message": (
                "Orchestrateur indisponible."
            ),
        }

    fonction = getattr(
        orchestrateur,
        "appliquer_auto",
        None,
    )

    if not callable(fonction):

        return {
            "ok": False,
            "succes": False,
            "message": (
                "Auto-application indisponible."
            ),
        }

    try:
        return fonction(
            proposition_id
        )

    except Exception as exc:

        return {
            "ok": False,
            "succes": False,
            "message": str(exc),
            "type_erreur": type(exc).__name__,
        }


# ============================================================================
# RESTAURATION
# ============================================================================

def restaurer(
    proposition_id: str,
    force: bool = False,
) -> dict[str, Any]:
    """
    Restaure une proposition via rollback.py.

    `force` est conservé uniquement pour compatibilité.
    Il ne contourne aucune sécurité.
    """

    try:

        fonction = getattr(
            rollback,
            "restaurer_proposition",
            None,
        )

        if not callable(fonction):

            return {
                "ok": False,
                "succes": False,
                "message": (
                    "rollback.restauration "
                    "indisponible."
                ),
            }

        return fonction(
            proposition_id,
            force=force,
        )

    except TypeError:

        try:
            return fonction(
                proposition_id
            )

        except Exception as exc:

            return {
                "ok": False,
                "succes": False,
                "message": str(exc),
            }

    except Exception as exc:

        return {
            "ok": False,
            "succes": False,
            "message": str(exc),
            "type_erreur": type(exc).__name__,
        }


# ============================================================================
# STATISTIQUES
# ============================================================================

def statistiques() -> dict[str, Any]:
    """
    Retourne les statistiques disponibles.

    Aucun calcul décisionnel.
    """

    resultat: dict[str, Any] = {}

    try:

        fonction = getattr(
            propositions,
            "obtenir_statistiques",
            None,
        )

        if callable(fonction):

            resultat[
                "propositions"
            ] = fonction()

    except Exception:
        resultat[
            "propositions"
        ] = {}

    try:

        resultat[
            "sessions_labo"
        ] = laboratoire.compter_sessions()

    except Exception:

        resultat[
            "sessions_labo"
        ] = 0

    try:

        resultat[
            "versions"
        ] = {
            "en_attente": len(
                lister("en_attente")
            ),
            "appliquees": len(
                lister("appliquee")
            ),
        }

    except Exception:

        resultat[
            "versions"
        ] = {}

    resultat[
        "depot"
    ] = str(
        DEPOT
    )

    return resultat


# ============================================================================
# API PUBLIQUE
# ============================================================================

__all__ = [
    "DEPOT",
    "DIR",
    "BACKUPS",
    "FICHIERS_CRITIQUES",
    "FICHIERS_AUTO_APPLICABLES",
    "SEUIL_DIFF_AUTO_LIGNES",
    "protege",
    "est_critique",
    "charger",
    "lister",
    "tester_contenu",
    "proposer",
    "rejeter",
    "appliquer",
    "appliquer_auto",
    "restaurer",
    "statistiques",
]