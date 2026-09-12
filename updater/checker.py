"""
Vérification des mises à jour de JIBI — LECTURE SEULE, aucune écriture.

Principe :
- JIBI est supposé être un dépôt git (comme le reste du projet, qui
  autorise déjà 'git' dans la liste blanche de tools/terminal.py) ;
- ce module ne fait QUE consulter l'état du dépôt distant ('git fetch'
  ne modifie jamais les fichiers de travail, seulement les références
  locales du dépôt distant) ;
- la décision d'appliquer une mise à jour appartient à updater.py,
  jamais à ce module.
"""

import os
import subprocess

from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

DEPOT_DIR = os.path.abspath(os.getenv("JIBI_PROJET_DIR", "."))
REMOTE = os.getenv("JIBI_GIT_REMOTE", "origin")
BRANCHE = os.getenv("JIBI_GIT_BRANCHE", "main")
TIMEOUT_GIT = int(os.getenv("JIBI_TIMEOUT_GIT", "20"))


def _executer_git(*args):
    """Exécute une commande git dans DEPOT_DIR, shell=False, avec timeout."""

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
            f"Commande git '{' '.join(args)}' a dépassé {TIMEOUT_GIT}s."
        )


def version_locale():
    """Renvoie le hash court du commit actuellement utilisé par JIBI."""

    resultat = _executer_git("rev-parse", "--short", "HEAD")

    if resultat.returncode != 0:
        raise RuntimeError(
            f"Impossible de lire le commit local : {resultat.stderr.strip()}"
        )

    return resultat.stdout.strip()


def verifier_mise_a_jour():
    """
    Consulte le dépôt distant et compare avec le commit local.

    Renvoie un dict :
        {
            "mise_a_jour_disponible": bool,
            "version_locale": str,
            "version_distante": str,
            "commits_en_retard": int,
            "resume_commits": list[str],  # messages des commits manqués
        }
    """

    fetch = _executer_git("fetch", REMOTE, BRANCHE)

    if fetch.returncode != 0:
        raise RuntimeError(
            f"Échec de 'git fetch' : {fetch.stderr.strip()}"
        )

    local = version_locale()

    distant_res = _executer_git(
        "rev-parse", "--short", f"{REMOTE}/{BRANCHE}"
    )

    if distant_res.returncode != 0:
        raise RuntimeError(
            f"Impossible de lire le commit distant : {distant_res.stderr.strip()}"
        )

    distant = distant_res.stdout.strip()

    if local == distant:
        log_event(
            "updater",
            f"Aucune mise à jour disponible (à jour: {local})."
        )

        return {
            "mise_a_jour_disponible": False,
            "version_locale": local,
            "version_distante": distant,
            "commits_en_retard": 0,
            "resume_commits": [],
        }

    compte_res = _executer_git(
        "rev-list", "--count", f"HEAD..{REMOTE}/{BRANCHE}"
    )

    commits_en_retard = (
        int(compte_res.stdout.strip())
        if compte_res.returncode == 0 else 0
    )

    log_res = _executer_git(
        "log", "--oneline", f"HEAD..{REMOTE}/{BRANCHE}"
    )

    resume_commits = (
        log_res.stdout.strip().splitlines()
        if log_res.returncode == 0 else []
    )

    log_event(
        "updater",
        f"Mise à jour disponible: {local} -> {distant} "
        f"({commits_en_retard} commit(s))"
    )

    return {
        "mise_a_jour_disponible": True,
        "version_locale": local,
        "version_distante": distant,
        "commits_en_retard": commits_en_retard,
        "resume_commits": resume_commits,
    }
