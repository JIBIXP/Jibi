"""
Application des mises à jour de JIBI.

Principe (sécurité avant tout, cohérent avec le reste du projet) :
- checker.py décide SEULEMENT s'il y a une mise à jour disponible
  (lecture seule) ;
- ce module NE modifie le code QUE si l'utilisateur a explicitement
  confirmé (confirmer=True), exactement comme executer_commande ou
  supprimer_fichier dans tools/ ;
- une sauvegarde (rollback.creer_sauvegarde) est TOUJOURS créée avant
  toute modification, et un rollback automatique est déclenché si la
  mise à jour échoue en cours de route.
"""

import os
import subprocess

from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

from . import checker
from . import rollback

load_dotenv(override=True)

DEPOT_DIR = os.path.abspath(os.getenv("JIBI_PROJET_DIR", "."))
REMOTE = os.getenv("JIBI_GIT_REMOTE", "origin")
BRANCHE = os.getenv("JIBI_GIT_BRANCHE", "main")
TIMEOUT_GIT = int(os.getenv("JIBI_TIMEOUT_GIT", "20"))


def _executer_git(*args):

    try:
        return subprocess.run(
            ["git", *args],
            cwd=DEPOT_DIR,
            shell=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_GIT,
        )

    except FileNotFoundError:
        raise RuntimeError(
            "git n'est pas installé ou introuvable dans le PATH."
        )

    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Commande git a dépassé {TIMEOUT_GIT}s."
        )


def appliquer_mise_a_jour(confirmer=False):
    """
    Applique la dernière version disponible sur la branche suivie.

    Étapes :
    1. Vérifie qu'une mise à jour est bien disponible (sinon, ne fait
       rien et le signale).
    2. Exige confirmer=True (sinon PermissionError — même logique que
       les autres actions destructrices du projet).
    3. Crée une sauvegarde complète AVANT toute modification.
    4. Applique 'git reset --hard <remote>/<branche>'.
    5. En cas d'échec à l'étape 4, restaure automatiquement la
       sauvegarde créée à l'étape 3.
    """

    etat = checker.verifier_mise_a_jour()

    if not etat["mise_a_jour_disponible"]:
        return "JIBI est déjà à jour."

    if not confirmer:
        raise PermissionError(
            "Mise à jour refusée sans confirmation explicite "
            f"(confirmer=True) — {etat['commits_en_retard']} commit(s) "
            f"en attente ({etat['version_locale']} -> "
            f"{etat['version_distante']})."
        )

    chemin_sauvegarde = rollback.creer_sauvegarde(
        etiquette=f"avant_maj_{etat['version_locale']}"
    )

    log_event(
        "updater",
        f"Sauvegarde avant mise à jour : {chemin_sauvegarde}"
    )

    resultat = _executer_git(
        "reset", "--hard", f"{REMOTE}/{BRANCHE}"
    )

    if resultat.returncode != 0:

        log_error(
            "updater",
            "Mise à jour échouée, rollback automatique déclenché : "
            f"{resultat.stderr.strip()}"
        )

        try:
            rollback.restaurer_derniere_sauvegarde(confirmer=True)

        except Exception as e:
            log_error(
                "updater",
                f"Rollback automatique lui-même échoué : {e}"
            )

            raise RuntimeError(
                f"La mise à jour a échoué ET le rollback automatique "
                f"aussi : {e}. Sauvegarde manuelle disponible dans : "
                f"{chemin_sauvegarde}"
            )

        raise RuntimeError(
            "La mise à jour a échoué, le code a été restauré à l'état "
            f"précédent ({etat['version_locale']}). Détail : "
            f"{resultat.stderr.strip()[:200]}"
        )

    log_event(
        "updater",
        f"Mise à jour appliquée : {etat['version_locale']} -> "
        f"{etat['version_distante']}"
    )

    return (
        "Mise à jour appliquée avec succès "
        f"({etat['version_locale']} -> {etat['version_distante']}, "
        f"{etat['commits_en_retard']} commit(s)). "
        "Redémarre JIBI pour prendre en compte les changements."
    )
