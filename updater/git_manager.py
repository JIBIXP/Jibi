"""
Gestionnaire Git — PATCHÉ v2
- Branché sur core/config.py + timings + shell=False conservé
"""
import os
import subprocess
import time
from pathlib import Path

try:
    from core.config import JIBI_PROJET_DIR as DEPOT_DIR, GITHUB_BRANCH
    DEPOT_DIR = str(DEPOT_DIR)
    REMOTE = "origin"
    BRANCHE = GITHUB_BRANCH
    TIMEOUT_GIT = 20
except Exception:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    DEPOT_DIR = os.path.abspath(os.getenv("JIBI_PROJET_DIR", "."))
    REMOTE = os.getenv("JIBI_GIT_REMOTE", "origin")
    BRANCHE = os.getenv("JIBI_GIT_BRANCHE", "main")
    TIMEOUT_GIT = int(os.getenv("JIBI_TIMEOUT_GIT", "20"))

try:
    from logging_jibi import log_event, log_warning, log_error
except Exception:
    def log_event(*a, **kw): pass
    def log_warning(*a, **kw): pass
    def log_error(*a, **kw): pass

def _executer_git(*args):
    try:
        return subprocess.run(["git", *args], cwd=DEPOT_DIR, shell=False, capture_output=True, text=True, timeout=TIMEOUT_GIT)
    except FileNotFoundError:
        raise RuntimeError("git n'est pas installé ou introuvable.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Commande git timeout ({TIMEOUT_GIT}s).")

def verifier_git_installe():
    try:
        return _executer_git("--version").returncode == 0
    except Exception:
        return False

def git_fetch():
    t0 = time.perf_counter()
    log_event("git_manager", f"git fetch {REMOTE} {BRANCHE}")
    resultat = _executer_git("fetch", REMOTE, BRANCHE)
    if resultat.returncode != 0:
        log_error("git_manager", f"git fetch échoué : {resultat.stderr.strip()}", exc_info=False)
        return {"ok": False, "message": resultat.stderr.strip(), "duree": round(time.perf_counter()-t0,3)}
    return {"ok": True, "message": "Fetch réussi.", "duree": round(time.perf_counter()-t0,3)}

def git_pull(branche=None):
    if branche is None:
        branche = BRANCHE
    log_event("git_manager", f"git pull {REMOTE} {branche}")
    t0 = time.perf_counter()
    resultat = _executer_git("reset", "--hard", f"{REMOTE}/{branche}")
    if resultat.returncode != 0:
        log_error("git_manager", f"git reset --hard échoué : {resultat.stderr.strip()}", exc_info=False)
        return {"ok": False, "message": resultat.stderr.strip(), "strategie": "reset", "duree": round(time.perf_counter()-t0,3)}
    log_event("git_manager", f"git pull réussi (reset --hard) en {time.perf_counter()-t0:.3f}s")
    return {"ok": True, "message": "Pull réussi (reset --hard).", "strategie": "reset", "duree": round(time.perf_counter()-t0,3)}

def git_merge(branche):
    log_event("git_manager", f"git merge {branche}")
    resultat = _executer_git("merge", branche)
    if resultat.returncode != 0:
        if "CONFLICT" in resultat.stdout or "CONFLICT" in resultat.stderr:
            return {"ok": False, "message": "Conflits détectés lors du merge.", "conflits": True}
        return {"ok": False, "message": resultat.stderr.strip(), "conflits": False}
    return {"ok": True, "message": "Merge réussi.", "conflits": False}

def git_status_detaille():
    branche_res = _executer_git("branch", "--show-current")
    branche = branche_res.stdout.strip() if branche_res.returncode == 0 else "?"
    status_res = _executer_git("status", "--porcelain")
    if status_res.returncode != 0:
        return {"branche": branche, "erreur": status_res.stderr.strip()}
    modifies, non_suivis, conflits = [], [], []
    for ligne in status_res.stdout.strip().splitlines():
        if not ligne:
            continue
        code, fichier = ligne[:2], ligne[3:]
        if code in ("DD", "AU", "UD", "UA", "DU", "AA", "UU"):
            conflits.append(fichier)
        elif code.strip() in ("M", "A", "D", "R", "C"):
            modifies.append(fichier)
        elif code == "??":
            non_suivis.append(fichier)
    return {"branche": branche, "modifies": modifies, "non_suivis": non_suivis, "conflits": conflits, "propre": len(modifies)==0 and len(non_suivis)==0 and len(conflits)==0}

def obtenir_diff_local_distant():
    diff_names = _executer_git("diff", "--name-only", f"HEAD..{REMOTE}/{BRANCHE}")
    fichiers = diff_names.stdout.strip().splitlines() if diff_names.returncode == 0 else []
    diff_complet_res = _executer_git("diff", f"HEAD..{REMOTE}/{BRANCHE}")
    diff_complet = diff_complet_res.stdout[:5000] if diff_complet_res.returncode == 0 else ""
    return {"fichiers_modifies": fichiers, "diff_complet": diff_complet}

def obtenir_commits_ahead_behind():
    behind_res = _executer_git("rev-list", "--count", f"HEAD..{REMOTE}/{BRANCHE}")
    behind = int(behind_res.stdout.strip()) if behind_res.returncode == 0 else 0
    ahead_res = _executer_git("rev-list", "--count", f"{REMOTE}/{BRANCHE}..HEAD")
    ahead = int(ahead_res.stdout.strip()) if ahead_res.returncode == 0 else 0
    return {"ahead": ahead, "behind": behind}

def obtenir_fichiers_modifies():
    r = _executer_git("diff", "--name-only")
    return r.stdout.strip().splitlines() if r.returncode == 0 else []

def obtenir_fichiers_non_suivis():
    r = _executer_git("ls-files", "--others", "--exclude-standard")
    return r.stdout.strip().splitlines() if r.returncode == 0 else []

def detecter_conflits():
    s = git_status_detaille()
    return {"conflits": len(s.get("conflits", [])) > 0, "fichiers_conflits": s.get("conflits", [])}

def resoudre_conflits_simples(strategie="theirs"):
    if strategie not in ("theirs", "ours"):
        return {"ok": False, "message": f"Stratégie inconnue : {strategie}"}
    log_event("git_manager", f"Résolution conflits avec stratégie : {strategie}")
    r = _executer_git("checkout", f"--{strategie}", ".")
    if r.returncode != 0:
        return {"ok": False, "message": r.stderr.strip()}
    add_res = _executer_git("add", ".")
    if add_res.returncode != 0:
        return {"ok": False, "message": "Impossible de stage les fichiers résolus."}
    return {"ok": True, "message": f"Conflits résolus avec '{strategie}'."}

def initialiser_repo_si_absent():
    git_dir = os.path.join(DEPOT_DIR, ".git")
    if os.path.exists(git_dir):
        return {"ok": True, "message": "Dépôt Git déjà initialisé."}
    log_event("git_manager", "Initialisation dépôt Git...")
    r = _executer_git("init")
    if r.returncode != 0:
        return {"ok": False, "message": r.stderr.strip()}
    return {"ok": True, "message": "Dépôt Git initialisé."}
