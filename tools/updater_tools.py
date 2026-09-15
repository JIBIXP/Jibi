"""
Outils Updater pour JIBI — Interface sécurisée vers le module updater.

Ce module expose les fonctions du système de mise à jour
avec les protections habituelles (confirmation requise).
"""

import os
from pathlib import Path

# Import sécurisé du vérificateur (peut ne pas exister encore)
try:
    from updater.checker import (
        verifier_mise_a_jour,
        version_locale,
    )
    UPDATER_CORE_OK = True
except (ImportError, AttributeError) as e:
    UPDATER_CORE_OK = False
    # Stubs pour éviter les crashs
    def verifier_mise_a_jour():
        return {"mise_a_jour_disponible": False, "message": "Module checker introuvable."}
    
    def version_locale():
        return "inconnu"


# Import sécurisé de l'appliqueur
try:
    from updater.updater import appliquer_mise_a_jour_securisee
    UPDATER_APPLY_OK = True
except (ImportError, AttributeError):
    appliquer_mise_a_jour_securisee = lambda **kw: {"succes": False, "message": "Module updater introuvable."}
    UPDATER_APPLY_OK = False


# Import sécurisé du rollback
try:
    from updater.rollback import restaurer_derniere_sauvegarde
    ROLLBACK_OK = True
except (ImportError, AttributeError):
    def restaurer_derniere_sauvegarde(**kwargs):
        return {"succes": False, "message": "Module rollback introuvable."}
    ROLLBACK_OK = False


DEPOT_DIR = Path(os.getenv("JIBI_PROJET_DIR", "."))


def verifier_mise_a_jour_tool():
    """
    Vérifie si une mise à jour JIBI est disponible sur GitHub.
    """
    if not UPDATER_CORE_OK:
        return {
            "ok": False,
            "message": (
                "Le module de vérification des mises à jour est "
                "indisponible (updater/checker)."
            ),
        }

    try:
        rapport = verifier_mise_a_jour()
        
        return {
            "ok": True,
            "mise_a_jour_disponible": rapport.get(
                "mise_a_jour_disponible", False
            ),
            "version_locale": rapport.get("version_locale", "?"),
            "version_distante": rapport.get("version_distante", "?"),
            "commits_en_retard": rapport.get("commits_en_retard", 0),
            "resume_commits": rapport.get("resume_commits", []),
            "message": rapport.get("message", ""),
        }

    except Exception as e:
        return {
            "ok": False,
            "message": f"Erreur lors de la vérification : {str(e)[:150]}",
        }


def appliquer_mise_a_jour_tool(confirmer=False):
    """
    Applique la dernière mise à jour JIBI (sauvegarde auto + confirmation requise).
    
    ⚠️  confirmer=True obligatoire.
    """
    if not confirmer:
        return {
            "ok": False,
            "message": "Application refusée sans confirmation explicite.",
        }

    if not UPDATER_APPLY_OK:
        return {
            "ok": False,
            "message": "Module d'application indisponible (updater/updater.py).",
        }

    try:
        resultat = appliquer_mise_a_jour_securisee(confirmer=confirmer)
        
        # Normaliser le résultat
        if isinstance(resultat, str):
            return {"ok": True, "message": resultat}
        
        return resultat

    except Exception as e:
        return {
            "ok": False,
            "message": f"Erreur application mise à jour : {str(e)[:200]}",
        }


def restaurer_derniere_sauvegarde_tool(confirmer=False):
    """
    Restaure JIBI à partir de la dernière sauvegarde (rollback).
    
    ⚠️  confirmer=True obligatoire.
    """
    if not confirmer:
        return {
            "ok": False,
            "message": "Restauration refusée sans confirmation explicite.",
        }

    if not ROLLBACK_OK:
        return {
            "ok": False,
            "message": "Module de restauration indisponible (updater/rollback.py).",
        }

    try:
        result = restaurer_derniere_sauvegarde(confirmer=confirmer)
        
        if isinstance(result, str):
            return {"ok": True, "message": result}
        
        return result

    except Exception as e:
        return {
            "ok": False,
            "message": f"Erreur restauration : {str(e)[:200]}",
        }


def lister_sauvegardes_tool():
    """Liste toutes les sauvegardes disponibles."""
    try:
        from updater.rollback import lister_sauvegardes
        
        sauvegardes = lister_sauvegardes()
        
        if isinstance(sauvegardes, str):
            return sauvegardes
        
        if isinstance(sauvegardes, list):
            return {
                "total": len(sauvegardes),
                "liste": sauvegardes[:20],  # Limiter affichage
                "message": f"{len(sauvegardes)} sauvegardes disponibles."
            }
        
        return str(sauvegardes)

    except ImportError:
        return "Module rollback indisponible."
    except Exception as e:
        return f"Erreur liste sauvegardes : {str(e)[:150]}"


def obtenir_etat_global_jibi_tool():
    """État global : version, modifications locales, mise à jour dispo."""
    infos = {}
    
    # Version actuelle (si disponible)
    if UPDATER_CORE_OK:
        try:
            ver = version_locale()
            infos["version"] = ver
        except Exception:
            infos["version"] = "inconnue"
    else:
        infos["version"] = "inconnue (module checker absent)"
    
    # Mise à jour disponible ?
    check = verifier_mise_a_jour_tool()
    infos["mise_a_jour"] = check
    
    # Sauvegardes
    infos["sauvegardes"] = lister_sauvegardes_tool()
    
    # Modifications locales Git (si git dispo)
    try:
        from updater.git_manager import git_status_detaille
        status = git_status_detaille()
        infos["git_status"] = status
    except Exception:
        infos["git_status"] = {"propre": True, "modifies": []}
    
    return infos


# ===========================================================================
# Fonctions utilitaires internes
# ===========================================================================

def _format_date(dt_str):
    """Formate un ISO date en lisible."""
    if not dt_str:
        return "?"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return dt_str[:16]