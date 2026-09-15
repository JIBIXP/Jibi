"""
Gestion des sauvegardes — PATCHÉ v2
- Branché sur core/config.py (WORKSPACE_DIR, MAX_BACKUPS, RETENTION)
- Garde-fou path traversal + timings
"""

from pathlib import Path
from datetime import datetime, timedelta
import shutil
import json
import time

try:
    from core.config import WORKSPACE_DIR, JIBI_PROJET_DIR, MAX_BACKUPS_PAR_FICHIER, RETENTION_BACKUPS_JOURS
    PROJECT_ROOT = JIBI_PROJET_DIR
    BACKUP_ROOT = WORKSPACE_DIR / "jibi_lab" / "backups"
except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    BACKUP_ROOT = PROJECT_ROOT / "workspace" / "jibi_lab" / "backups"
    MAX_BACKUPS_PAR_FICHIER = 20
    DUREE_CONSERVATION_JOURS = 30
    RETENTION_BACKUPS_JOURS = DUREE_CONSERVATION_JOURS

try:
    from logging_jibi import log_event
except Exception:
    def log_event(*a, **kw): pass

def creer_backup(fichier, raison=""):
    t0 = time.perf_counter()
    fichier = Path(fichier).resolve()
    # garde-fou : ne backuper que dans le projet
    try:
        fichier.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        raise PermissionError(f"Backup refusé hors projet : {fichier}")
    if not fichier.exists():
        raise FileNotFoundError(f"Fichier introuvable : {fichier}")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        relatif = fichier.relative_to(PROJECT_ROOT)
        nom_dossier = str(relatif).replace("/", "_").replace("\\", "_")
    except ValueError:
        nom_dossier = fichier.stem
    dossier_backup = BACKUP_ROOT / nom_dossier
    dossier_backup.mkdir(parents=True, exist_ok=True)
    destination = dossier_backup / f"{fichier.stem}_{timestamp}{fichier.suffix}"
    shutil.copy2(fichier, destination)
    meta = {"fichier_original": str(fichier), "backup": str(destination), "date": datetime.now().isoformat(), "taille": fichier.stat().st_size, "raison": raison}
    try:
        destination.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    _limiter_backups(dossier_backup)
    log_event("versions", f"Backup {fichier.name} → {destination.name} en {time.perf_counter()-t0:.3f}s")
    return destination

def _limiter_backups(dossier):
    if not dossier.exists():
        return
    backups = sorted([f for f in dossier.iterdir() if f.is_file() and not f.name.endswith(".meta.json")], key=lambda f: f.stat().st_mtime, reverse=True)
    for backup in backups[MAX_BACKUPS_PAR_FICHIER:]:
        try:
            backup.unlink()
            meta = backup.with_suffix(".meta.json")
            if meta.exists():
                meta.unlink()
        except Exception:
            continue

def restaurer_backup(backup, destination=None):
    backup = Path(backup).resolve()
    try:
        backup.relative_to(BACKUP_ROOT.resolve())
    except ValueError:
        raise PermissionError(f"Restauration refusée hors backup : {backup}")
    if not backup.exists():
        raise FileNotFoundError(f"Sauvegarde introuvable : {backup}")
    if destination is None:
        meta_file = backup.with_suffix(".meta.json")
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                destination = meta.get("fichier_original")
            except Exception:
                pass
    if destination is None:
        raise ValueError("Destination inconnue. Fournis un chemin de destination explicite.")
    destination = Path(destination).resolve()
    try:
        destination.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        raise PermissionError(f"Restauration refusée hors projet : {destination}")
    if destination.exists():
        creer_backup(destination, raison="Avant restauration")
    shutil.copy2(backup, destination)
    log_event("versions", f"Restauration {backup.name} → {destination}")
    return destination

def lister_backups(fichier=None):
    if not BACKUP_ROOT.exists():
        return []
    backups = []
    for dossier in BACKUP_ROOT.iterdir():
        if not dossier.is_dir():
            continue
        for fichier_backup in sorted(dossier.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
            if fichier_backup.name.endswith(".meta.json") or not fichier_backup.is_file():
                continue
            meta_file = fichier_backup.with_suffix(".meta.json")
            raison, original = "", ""
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    raison, original = meta.get("raison", ""), meta.get("fichier_original", "")
                except Exception:
                    pass
            if fichier and original and str(fichier) not in original:
                continue
            backups.append({"chemin": str(fichier_backup), "nom": fichier_backup.name, "taille": fichier_backup.stat().st_size, "date": datetime.fromtimestamp(fichier_backup.stat().st_mtime).strftime("%Y-%m-%d %H:%M"), "original": original, "raison": raison})
    return backups

def compter_backups():
    if not BACKUP_ROOT.exists():
        return 0
    return sum(1 for d in BACKUP_ROOT.rglob("*") if d.is_file() and not d.name.endswith(".meta.json"))

def nettoyer_vieux_backups(jours=None):
    if jours is None:
        jours = RETENTION_BACKUPS_JOURS if 'RETENTION_BACKUPS_JOURS' in globals() else 30
    if not BACKUP_ROOT.exists():
        return 0
    seuil = datetime.now() - timedelta(days=jours)
    supprimes = 0
    for fichier in BACKUP_ROOT.rglob("*"):
        if not fichier.is_file():
            continue
        if datetime.fromtimestamp(fichier.stat().st_mtime) < seuil:
            try:
                fichier.unlink()
                supprimes += 1
            except Exception:
                continue
    return supprimes

def formater_liste_backups(backups=None, limite=15):
    if backups is None:
        backups = lister_backups()
    if not backups:
        return "Aucune sauvegarde disponible."
    lignes = [f"💾 Sauvegardes ({len(backups)} au total) :"]
    for b in backups[:limite]:
        raison = f" — {b['raison']}" if b['raison'] else ""
        lignes.append(f"  • [{b['date']}] {b['nom']}{raison}")
    if len(backups) > limite:
        lignes.append(f"  ... et {len(backups) - limite} autres")
    return "\n".join(lignes)
