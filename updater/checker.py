"""
Vérification des mises à jour — PATCHÉ v2
- Branché sur core/config.py + timings
"""
import subprocess
import time
from pathlib import Path

try:
    from core.config import JIBI_PROJET_DIR as DEPOT_DIR, GITHUB_REPO_URL, GITHUB_BRANCH
    DEPOT_DIR = str(DEPOT_DIR)
    REMOTE = "origin"
    BRANCHE = GITHUB_BRANCH
    TIMEOUT_GIT = 20
except Exception:
    import os
    from dotenv import load_dotenv
    load_dotenv(override=True)
    DEPOT_DIR = os.path.abspath(os.getenv("JIBI_PROJET_DIR", "."))
    REMOTE = os.getenv("JIBI_GIT_REMOTE", "origin")
    BRANCHE = os.getenv("JIBI_GIT_BRANCHE", "main")
    TIMEOUT_GIT = int(os.getenv("JIBI_TIMEOUT_GIT", "20"))

try:
    from logging_jibi import log_event
except Exception:
    def log_event(*a, **kw): pass

def _executer_git(*args):
    try:
        return subprocess.run(["git", *args], cwd=DEPOT_DIR, shell=False, capture_output=True, text=True, timeout=TIMEOUT_GIT)
    except FileNotFoundError:
        raise RuntimeError("git n'est pas installé ou introuvable dans le PATH.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Commande git '{' '.join(args)}' a dépassé {TIMEOUT_GIT}s.")

def version_locale():
    t0 = time.perf_counter()
    resultat = _executer_git("rev-parse", "--short", "HEAD")
    if resultat.returncode != 0:
        raise RuntimeError(f"Impossible de lire le commit local : {resultat.stderr.strip()}")
    # print(f"[GIT version_locale] {time.perf_counter()-t0:.3f}s")
    return resultat.stdout.strip()

def verifier_mise_a_jour():
    t0 = time.perf_counter()
    fetch = _executer_git("fetch", REMOTE, BRANCHE)
    if fetch.returncode != 0:
        raise RuntimeError(f"Échec de 'git fetch' : {fetch.stderr.strip()}")
    local = version_locale()
    distant_res = _executer_git("rev-parse", "--short", f"{REMOTE}/{BRANCHE}")
    if distant_res.returncode != 0:
        raise RuntimeError(f"Impossible de lire le commit distant : {distant_res.stderr.strip()}")
    distant = distant_res.stdout.strip()
    if local == distant:
        log_event("updater", f"Aucune mise à jour disponible (à jour: {local}).")
        return {"mise_a_jour_disponible": False, "version_locale": local, "version_distante": distant, "commits_en_retard": 0, "resume_commits": [], "duree": round(time.perf_counter()-t0,3)}
    compte_res = _executer_git("rev-list", "--count", f"HEAD..{REMOTE}/{BRANCHE}")
    commits_en_retard = int(compte_res.stdout.strip()) if compte_res.returncode == 0 else 0
    log_res = _executer_git("log", "--oneline", f"HEAD..{REMOTE}/{BRANCHE}")
    resume_commits = log_res.stdout.strip().splitlines() if log_res.returncode == 0 else []
    log_event("updater", f"Mise à jour disponible: {local} -> {distant} ({commits_en_retard} commit(s)) en {time.perf_counter()-t0:.3f}s")
    return {"mise_a_jour_disponible": True, "version_locale": local, "version_distante": distant, "commits_en_retard": commits_en_retard, "resume_commits": resume_commits, "duree": round(time.perf_counter()-t0,3)}

