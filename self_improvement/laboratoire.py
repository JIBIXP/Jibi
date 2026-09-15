"""
Laboratoire d'expérimentation de JIBI — PATCHÉ v2
- Branché sur core/config.py (WORKSPACE_DIR, RETENTION_SESSIONS_JOURS)
- Timings [LABO] + diff corrigé + nettoyage compilé
"""

from pathlib import Path
from datetime import datetime, timedelta
import shutil
import uuid
import difflib
import time

try:
    from core.config import WORKSPACE_DIR, JIBI_PROJET_DIR
    PROJECT_ROOT = JIBI_PROJET_DIR
    LABORATOIRE_ROOT = WORKSPACE_DIR / "jibi_lab"
    from core.config import RETENTION_SESSIONS_JOURS as DUREE_VIE_SESSION_JOURS
except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    LABORATOIRE_ROOT = PROJECT_ROOT / "workspace" / "jibi_lab"
    DUREE_VIE_SESSION_JOURS = 7

try:
    from logging_jibi import log_event
except Exception:
    def log_event(*a, **kw): pass

def initialiser_laboratoire():
    t0 = time.perf_counter()
    for dossier in ["sessions", "backups", "propositions", "historique"]:
        (LABORATOIRE_ROOT / dossier).mkdir(parents=True, exist_ok=True)
    log_event("laboratoire", f"Labo init en {time.perf_counter()-t0:.3f}s")
    return LABORATOIRE_ROOT

def creer_session(nom=None):
    t0 = time.perf_counter()
    initialiser_laboratoire()
    session_id = uuid.uuid4().hex[:12]
    if nom:
        nom_propre = "".join(c if c.isalnum() or c in "-_" else "_" for c in nom)[:30]
        nom_dossier = f"session_{session_id}_{nom_propre}"
    else:
        nom_dossier = f"session_{session_id}"
    session = LABORATOIRE_ROOT / "sessions" / nom_dossier
    session.mkdir(parents=True, exist_ok=False)
    (session / "_session_info.txt").write_text(
        f"Session : {session_id}\nCréée : {datetime.now().isoformat()}\nNom : {nom or 'sans nom'}\n",
        encoding="utf-8",
    )
    log_event("laboratoire", f"Session {nom_dossier} créée en {time.perf_counter()-t0:.3f}s")
    return session

def compter_sessions():
    sessions_dir = LABORATOIRE_ROOT / "sessions"
    if not sessions_dir.exists():
        return 0
    return sum(1 for d in sessions_dir.iterdir() if d.is_dir())

def lister_sessions():
    sessions_dir = LABORATOIRE_ROOT / "sessions"
    if not sessions_dir.exists():
        return []
    sessions = []
    for dossier in sorted(sessions_dir.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True):
        if not dossier.is_dir():
            continue
        nb_fichiers = sum(1 for f in dossier.iterdir() if f.is_file() and f.name != "_session_info.txt")
        sessions.append({
            "chemin": str(dossier),
            "nom": dossier.name,
            "fichiers": nb_fichiers,
            "date": datetime.fromtimestamp(dossier.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return sessions

def supprimer_session(session):
    session = Path(session).resolve()
    laboratoire = LABORATOIRE_ROOT.resolve()
    try:
        session.relative_to(laboratoire)
    except ValueError:
        raise PermissionError("Suppression refusée : le chemin est hors du laboratoire JIBI.")
    if session.exists():
        shutil.rmtree(session)
        return True
    return False

def nettoyer_vieilles_sessions(jours=None):
    if jours is None:
        jours = DUREE_VIE_SESSION_JOURS
    sessions_dir = LABORATOIRE_ROOT / "sessions"
    if not sessions_dir.exists():
        return 0
    seuil = datetime.now() - timedelta(days=jours)
    supprimees = 0
    for dossier in sessions_dir.iterdir():
        if not dossier.is_dir():
            continue
        date_modif = datetime.fromtimestamp(dossier.stat().st_mtime)
        if date_modif < seuil:
            try:
                shutil.rmtree(dossier)
                supprimees += 1
            except Exception:
                continue
    return supprimees

def copier_fichier_dans_laboratoire(fichier_source, session):
    t0 = time.perf_counter()
    source = Path(fichier_source).resolve()
    session = Path(session).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Fichier introuvable : {source}")
    if not source.is_file():
        raise ValueError(f"Ce n'est pas un fichier : {source}")
    if not session.exists():
        raise FileNotFoundError(f"Session introuvable : {session}")
    try:
        relatif = source.relative_to(PROJECT_ROOT)
        destination = session / relatif
        destination.parent.mkdir(parents=True, exist_ok=True)
    except ValueError:
        destination = session / source.name
    shutil.copy2(source, destination)
    log_event("laboratoire", f"Copie {source.name} → labo en {time.perf_counter()-t0:.3f}s")
    return destination

def copier_dossier_dans_laboratoire(dossier_source, session):
    source = Path(dossier_source).resolve()
    session = Path(session).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Dossier introuvable : {source}")
    if not source.is_dir():
        raise ValueError(f"Ce n'est pas un dossier : {source}")
    destination = session / source.name
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return destination

def comparer_fichiers(fichier_original, fichier_modifie):
    original = Path(fichier_original)
    modifie = Path(fichier_modifie)
    if not original.exists():
        return {"ok": False, "message": f"Original introuvable : {original}"}
    if not modifie.exists():
        return {"ok": False, "message": f"Modifié introuvable : {modifie}"}
    try:
        lignes_orig = original.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        lignes_mod = modifie.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        diff = list(difflib.unified_diff(lignes_orig, lignes_mod, fromfile=str(original.name), tofile=str(modifie.name), lineterm=""))
        return {
            "ok": True,
            "identique": len(diff) == 0,
            "lignes_diff": len(diff),
            "diff": "\n".join(diff[:200]),
            "lignes_original": len(lignes_orig),
            "lignes_modifie": len(lignes_mod),
        }
    except Exception as e:
        return {"ok": False, "message": str(e)}
