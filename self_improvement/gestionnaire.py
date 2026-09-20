from __future__ import annotations

from pathlib import Path
from typing import Any

from . import analyseur
from . import laboratoire
from . import orchestrateur
from . import propositions


try:
    from core.config import JIBI_PROJET_DIR
except Exception:
    JIBI_PROJET_DIR = Path(__file__).resolve().parent.parent


DEPOT_DIR = Path(JIBI_PROJET_DIR).resolve()


# ---------------------------------------------------------------------------
# ORCHESTRATEUR
# ---------------------------------------------------------------------------

def _obtenir_orchestrateur() -> Any:
    """
    Retourne l'orchestrateur central.

    Compatible avec :
        - une fonction obtenir_orchestrateur()
        - une classe Orchestrateur
        - une instance globale orchestrateur
    """

    getter = getattr(
        orchestrateur,
        "obtenir_orchestrateur",
        None,
    )

    if callable(getter):
        return getter()

    classe = getattr(
        orchestrateur,
        "Orchestrateur",
        None,
    )

    if classe is not None:
        return classe()

    factory = getattr(orchestrateur, "creer_orchestrateur", None)
    if callable(factory):
        return factory(depot=DEPOT_DIR)

    return orchestrateur


# ---------------------------------------------------------------------------
# ANALYSE
# ---------------------------------------------------------------------------

def analyser_jibi(
    limite_logs: int | None = None,
    depuis_heures: float | None = None,
    **_: Any,
) -> dict:
    """
    Compatibilité historique.

    L'analyse reste descriptive.
    """
    kwargs: dict[str, Any] = {}
    if limite_logs is not None:
        kwargs["limite"] = limite_logs
    if depuis_heures is not None:
        kwargs["depuis_heures"] = depuis_heures
    return analyseur.analyser_logs(**kwargs)


# ---------------------------------------------------------------------------
# PRÉPARATION D'UNE AMÉLIORATION
# ---------------------------------------------------------------------------

def preparer_amelioration(
    fichier: str,
    probleme: str = "",
    ancien: str = "",
    nouveau: str = "",
    *,
    origine: str = "agent",
    priorite: str = "moyenne",
    solution: str = "",
    justification: str = "",
    demande: str = "",
) -> dict:
    """
    Prépare une proposition de réparation.

    IMPORTANT :
        aucune modification de production.
    """

    orch = _obtenir_orchestrateur()

    fonction = getattr(
        orch,
        "preparer_reparation",
        None,
    )

    if not callable(fonction):
        return {
            "ok": False,
            "succes": False,
            "message": (
                "L'orchestrateur ne fournit pas "
                "preparer_reparation()."
            ),
        }

    demande_finale = demande.strip() or "\n".join(
        element for element in (
            probleme.strip(), solution.strip(), justification.strip(),
            f"Ancien comportement : {ancien.strip()}" if ancien.strip() else "",
            f"Nouveau comportement attendu : {nouveau.strip()}" if nouveau.strip() else "",
        ) if element
    )
    if not demande_finale:
        return {"ok": False, "succes": False, "message": "Décris l'amélioration demandée."}

    try:
        resultat = fonction(fichier=fichier, demande=demande_finale)

    except TypeError:
        # Compatibilité avec une signature plus ancienne.
        try:
            resultat = fonction(
                fichier,
                probleme,
                ancien,
                nouveau,
            )

        except Exception as exc:
            return {
                "ok": False,
                "succes": False,
                "message": str(exc),
                "type_erreur": type(exc).__name__,
            }

    except Exception as exc:
        return {
            "ok": False,
            "succes": False,
            "message": str(exc),
            "type_erreur": type(exc).__name__,
        }

    if hasattr(resultat, "to_dict"):
        resultat = resultat.to_dict()
    if not isinstance(resultat, dict):
        return {"ok": False, "succes": False, "message": "Réponse d'orchestrateur invalide."}
    resultat.setdefault("succes", bool(resultat.get("ok", False)))
    resultat.setdefault("origine", origine)
    resultat.setdefault("priorite", priorite)
    return resultat


# ---------------------------------------------------------------------------
# PROPOSITIONS
# ---------------------------------------------------------------------------

def lister_propositions(
    statut: str | None = None,
) -> list[dict[str, Any]]:
    """Retourne les propositions existantes."""

    orch = _obtenir_orchestrateur()

    fonction = getattr(
        orch,
        "lister_propositions",
        None,
    )

    if callable(fonction):
        try:
            resultat = fonction(
                statut
            )
        except TypeError:
            resultat = fonction()

        if isinstance(
            resultat,
            dict,
        ):
            propositions_resultat = resultat.get(
                "propositions"
            )

            if isinstance(
                propositions_resultat,
                list,
            ):
                return propositions_resultat

        if isinstance(
            resultat,
            list,
        ):
            return resultat

    try:
        return propositions.lister_propositions(
            statut=statut
        )
    except Exception:
        return []


# ---------------------------------------------------------------------------
# AUTORISATION
# ---------------------------------------------------------------------------

def autoriser(
    proposition_id: str,
) -> dict:
    """
    Autorise une proposition.

    La décision est confiée à l'orchestrateur.
    """

    orch = _obtenir_orchestrateur()

    fonction = getattr(
        orch,
        "autoriser",
        None,
    )

    if not callable(fonction):
        return {
            "ok": False,
            "succes": False,
            "message": (
                "L'orchestrateur ne fournit pas "
                "autoriser()."
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


# ---------------------------------------------------------------------------
# REJET
# ---------------------------------------------------------------------------

def rejeter(
    proposition_id: str,
    raison: str = "",
) -> dict:
    """Rejette une proposition via l'orchestrateur."""

    orch = _obtenir_orchestrateur()

    fonction = getattr(
        orch,
        "rejeter",
        None,
    )

    if not callable(fonction):
        return {
            "ok": False,
            "succes": False,
            "message": (
                "L'orchestrateur ne fournit pas "
                "rejeter()."
            ),
        }

    try:
        return fonction(
            proposition_id,
            raison,
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
                "type_erreur": type(exc).__name__,
            }

    except Exception as exc:
        return {
            "ok": False,
            "succes": False,
            "message": str(exc),
            "type_erreur": type(exc).__name__,
        }


# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------

def appliquer_amelioration(
    proposition_id: str,
    confirmation: str | None = None,
) -> dict:
    """
    Applique une proposition via l'orchestrateur.

    Aucune modification directe par gestionnaire.py.
    """

    if confirmation is None:
        return {
            "ok": False,
            "succes": False,
            "message": (
                "Confirmation explicite requise."
            ),
        }

    orch = _obtenir_orchestrateur()

    fonction = getattr(
        orch,
        "appliquer",
        None,
    )

    if not callable(fonction):
        return {
            "ok": False,
            "succes": False,
            "message": (
                "L'orchestrateur ne fournit pas "
                "appliquer()."
            ),
        }

    try:
        # L'orchestrateur actuel vérifie l'autorisation persistée et ne prend
        # que l'identifiant. Certaines anciennes implémentations acceptaient
        # aussi la confirmation : ne l'utiliser qu'en solution de repli.
        return fonction(proposition_id)

    except TypeError:
        try:
            return fonction(proposition_id, confirmation)

        except Exception as exc:
            return {
                "ok": False,
                "succes": False,
                "message": str(exc),
                "type_erreur": type(exc).__name__,
            }

    except Exception as exc:
        return {
            "ok": False,
            "succes": False,
            "message": str(exc),
            "type_erreur": type(exc).__name__,
        }


def autoriser_et_appliquer(
    proposition_id: str,
) -> dict:
    """
    Autorisation + application contrôlée.

    L'orchestrateur reste responsable de toutes
    les vérifications de sécurité.
    """

    orch = _obtenir_orchestrateur()

    fonction = getattr(
        orch,
        "autoriser",
        None,
    )

    if not callable(fonction):
        return {
            "ok": False,
            "succes": False,
            "message": (
                "Orchestrateur incomplet."
            ),
        }

    autorisation = fonction(
        proposition_id
    )

    if not isinstance(
        autorisation,
        dict,
    ):
        return {
            "ok": False,
            "succes": False,
            "message": (
                "Réponse d'autorisation invalide."
            ),
        }

    if not autorisation.get(
        "ok",
        False,
    ):
        return autorisation

    confirmation = (
        f"J'AUTORISE {proposition_id}"
    )

    return appliquer_amelioration(
        proposition_id,
        confirmation,
    )


# ---------------------------------------------------------------------------
# PROBLÈME PERSISTANT
# ---------------------------------------------------------------------------

def resoudre_probleme_persistant(
    depuis_heures: int = 24,
) -> dict:
    """
    Prépare l'analyse d'un problème persistant.

    Aucun correctif n'est appliqué automatiquement ici.
    """

    orch = _obtenir_orchestrateur()

    fonction = getattr(
        orch,
        "diagnostiquer",
        None,
    )

    if callable(fonction):

        try:
            diagnostic = fonction()

            return {
                "ok": True,
                "analyse": diagnostic,
                "propositions": [],
                "message": (
                    "Diagnostic préparé. "
                    "Aucune modification automatique."
                ),
            }

        except Exception as exc:
            return {
                "ok": False,
                "succes": False,
                "message": str(exc),
                "type_erreur": type(exc).__name__,
            }

    analyse = analyser_jibi()

    return {
        "ok": True,
        "analyse": analyse,
        "propositions": [],
        "depuis_heures": depuis_heures,
        "message": (
            "Diagnostic persistant préparé. "
            "Aucune modification automatique."
        ),
    }


# ---------------------------------------------------------------------------
# WORKFLOW
# ---------------------------------------------------------------------------

def workflow_complet_amelioration(
    fichier: str,
    probleme: str,
    ancien: str,
    nouveau: str,
    *,
    appliquer_automatiquement: bool = False,
) -> dict:
    """
    Lance le workflow centralisé.

    Le gestionnaire ne prend aucune décision de sécurité.
    """

    orch = _obtenir_orchestrateur()

    workflow = getattr(
        orch,
        "workflow",
        None,
    )

    if callable(workflow):

        try:
            return workflow(
                fichier=fichier,
                probleme=probleme,
                ancien=ancien,
                nouveau=nouveau,
                appliquer_automatiquement=(
                    appliquer_automatiquement
                ),
            )

        except TypeError:
            pass

        except Exception as exc:
            return {
                "ok": False,
                "succes": False,
                "message": str(exc),
                "type_erreur": type(exc).__name__,
            }

    # Compatibilité si workflow() n'existe pas encore.
    preparation = preparer_amelioration(
        fichier=fichier,
        probleme=probleme,
        ancien=ancien,
        nouveau=nouveau,
    )

    if not preparation.get(
        "ok",
        False,
    ):
        return preparation

    return {
        "ok": True,
        "succes": False,
        "requiert_autorisation": True,
        "proposition": preparation.get(
            "proposition"
        ),
        "risque": preparation.get(
            "risque",
            {},
        ),
        "message": (
            "Proposition préparée. "
            "Autorisation requise."
        ),
    }


# ---------------------------------------------------------------------------
# TABLEAU DE BORD
# ---------------------------------------------------------------------------

def tableau_de_bord() -> dict:
    """
    Retourne une vue synthétique de JIBI.

    Aucune décision de réparation.
    """

    orch = _obtenir_orchestrateur()

    dashboard = getattr(
        orch,
        "tableau_de_bord",
        None,
    )

    if callable(dashboard):

        try:
            resultat = dashboard()

            if isinstance(
                resultat,
                dict,
            ):
                return resultat

        except Exception:
            pass

    return {
        "sante": analyser_jibi(),
        "propositions": (
            propositions.obtenir_statistiques()
        ),
        "sessions_labo": (
            laboratoire.compter_sessions()
        ),
        "depot": str(
            DEPOT_DIR
        ),
    }


# ---------------------------------------------------------------------------
# API PUBLIQUE
# ---------------------------------------------------------------------------

__all__ = [
    "DEPOT_DIR",
    "analyser_jibi",
    "preparer_amelioration",
    "lister_propositions",
    "autoriser",
    "rejeter",
    "appliquer_amelioration",
    "autoriser_et_appliquer",
    "resoudre_probleme_persistant",
    "workflow_complet_amelioration",
    "tableau_de_bord",
]
