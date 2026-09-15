"""
Sauvegardes et restauration — PATCHÉ v2
- Branché sur core/config.py (WORKSPACE_DIR) + timings
"""
import os
import shutil
import json
import time
from pathlib import Path
from datetime import datetime, timezone

try:
    from core.config import JIBI_PROJET_DIR as _DEPOT, WORKSPACE_DIR
    DEPOT_DIR = str(_DEPOT)
    DOSSIER_SAUVEGARDES = str(WORKSPACE_DIR / "updater_backups")
    from core.config import MAX_SAUVEGARDES_UPDATER as NOMBRE_MAX_SAUVEGARDES
except Exception:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    DEPOT_DIR = os.path.abspath(os.getenv("JIBI_PROJET_DIR", "."))
    DOSSIER_SAUVEGARDES = os.path.abspath(os.getenv("JIBI_SAUVEGARDES_DIR", os.path.join(DEPOT_DIR, "workspace", "updater_backups")))
    NOMBRE_MAX_SAUVEGARDES = int(os.getenv("JIBI_MAX_SAUVEGARDES", "10"))

try:
    from logging_jibi import log_event, log_warning, log_error
except Exception:
    def log_event(*a, **kw): pass
    def log_warning(*a, **kw): pass
    def log_error(*a, **kw): pass

os.makedirs(DOSSIER_SAUVEGARDES, exist_ok=True)
EXCLUS_BACKUP = {".git", "__pycache__", ".vscode", "logs", "venv", ".venv", "node_modules"}
EXCLUS_RESTAURATION = {"workspace", "logs"}

def _ignorer_backup(dossier, contenu):
    return [nom for nom in contenu if nom in EXCLUS_BACKUP]

def _ignorer_restauration(dossier, contenu):
    return [nom for nom in contenu if nom in EXCLUS_RESTAURATION]

def _creer_metadonnees(nom_sauvegarde, etiquette="", fichiers_sauvegardes=None):
    meta = {"nom": nom_sauvegarde, "date": datetime.now(timezone.utc).isoformat(), "etiquette": etiquette, "version": "", "nombre_fichiers": len(fichiers_sauvegardes) if fichiers_sauvegardes else 0, "important": False}
    try:
        from . import checker
        meta["version"] = checker.version_locale()
    except Exception:
        pass
    chemin_meta = Path(DOSSIER_SAUVEGARDES) / nom_sauvegarde / "_backup_meta.json"
    try:
        chemin_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log_warning("updater", f"Impossible de créer métadonnées : {e}")
    return meta

def _charger_metadonnees(nom_sauvegarde):
    chemin_meta = Path(DOSSIER_SAUVEGARDES) / nom_sauvegarde / "_backup_meta.json"
    if not chemin_meta.exists():
        return None
    try:
        return json.loads(chemin_meta.read_text(encoding="utf-8"))
    except Exception:
        return None

def marquer_backup_important(nom_sauvegarde):
    meta = _charger_metadonnees(nom_sauvegarde)
    if not meta:
        return False
    meta["important"] = True
    chemin_meta = Path(DOSSIER_SAUVEGARDES) / nom_sauvegarde / "_backup_meta.json"
    try:
        chemin_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        log_event("updater", f"Backup marqué important : {nom_sauvegarde}")
        return True
    except Exception as e:
        log_warning("updater", f"Impossible de marquer important : {e}")
        return False

def creer_sauvegarde(etiquette=""):
    t0 = time.perf_counter()
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    nom_dossier = f"{horodatage}_{etiquette}".rstrip("_")
    chemin_sauvegarde = os.path.join(DOSSIER_SAUVEGARDES, nom_dossier)
    shutil.copytree(DEPOT_DIR, chemin_sauvegarde, ignore=_ignorer_backup)
    fichiers = [f for f in Path(chemin_sauvegarde).rglob("*") if f.is_file()]
    _creer_metadonnees(nom_dossier, etiquette, fichiers)
    log_event("updater", f"Sauvegarde créée : {nom_dossier} ({len(fichiers)} fichiers) en {time.perf_counter()-t0:.3f}s")
    _purger_anciennes_sauvegardes()
    return chemin_sauvegarde

def lister_sauvegardes():
    if not os.path.isdir(DOSSIER_SAUVEGARDES):
        return []
    return sorted(os.listdir(DOSSIER_SAUVEGARDES), reverse=True)

def lister_sauvegardes_detaillees():
    sauvegardes = lister_sauvegardes()
    if not sauvegardes:
        return "Aucune sauvegarde disponible."
    lignes = [f"💾 SAUVEGARDES DISPONIBLES ({len(sauvegardes)}) :\n"]
    for nom in sauvegardes:
        meta = _charger_metadonnees(nom)
        if meta:
            date = meta.get("date", "?")[:16]
            version = meta.get("version", "?")
            etiquette = meta.get("etiquette", "")
            important = "⭐ " if meta.get("important") else ""
            lignes.append(f"{important}[{date}] {nom}\n  Version : {version}")
            if etiquette:
                lignes.append(f"  Étiquette : {etiquette}")
            lignes.append("")
        else:
            lignes.append(f"  • {nom} (métadonnées manquantes)\n")
    return "\n".join(lignes)

def analyser_backup(nom_sauvegarde):
    chemin = Path(DOSSIER_SAUVEGARDES) / nom_sauvegarde
    if not chemin.exists():
        return {"existe": False, "message": f"Sauvegarde '{nom_sauvegarde}' introuvable."}
    meta = _charger_metadonnees(nom_sauvegarde)
    fichiers = [f for f in chemin.rglob("*") if f.is_file() and f.name != "_backup_meta.json"]
    taille_totale = sum(f.stat().st_size for f in fichiers)
    return {"existe": True, "nom": nom_sauvegarde, "metadonnees": meta, "nombre_fichiers": len(fichiers), "taille_totale": taille_totale}

def restaurer_sauvegarde_specifique(nom_sauvegarde, confirmer=False, supprimer_nouveaux=False):
    if not confirmer:
        raise PermissionError("Restauration refusée sans confirmation explicite (confirmer=True).")
    chemin_source = Path(DOSSIER_SAUVEGARDES) / nom_sauvegarde
    if not chemin_source.exists():
        raise FileNotFoundError(f"Sauvegarde '{nom_sauvegarde}' introuvable.")
    log_event("updater", f"Restauration depuis : {nom_sauvegarde}")
    fichiers_actuels = set()
    if supprimer_nouveaux:
        for f in Path(DEPOT_DIR).rglob("*"):
            if f.is_file():
                try:
                    relatif = f.relative_to(DEPOT_DIR)
                    if not any(part in EXCLUS_RESTAURATION for part in relatif.parts):
                        fichiers_actuels.add(str(relatif))
                except ValueError:
                    pass
    fichiers_restaures = 0
    for element in chemin_source.iterdir():
        if element.name in EXCLUS_RESTAURATION or element.name == "_backup_meta.json":
            continue
        source, destination = element, Path(DEPOT_DIR) / element.name
        try:
            if source.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
            fichiers_restaures += 1
        except Exception as e:
            log_warning("updater", f"Impossible de restaurer {element.name} : {e}")
    fichiers_supprimes = 0
    if supprimer_nouveaux:
        fichiers_backup = {str(f.relative_to(chemin_source)) for f in chemin_source.rglob("*") if f.is_file() and f.name != "_backup_meta.json"}
        for fichier_relatif in fichiers_actuels - fichiers_backup:
            try:
                p = Path(DEPOT_DIR) / fichier_relatif
                if p.exists():
                    p.unlink()
                    fichiers_supprimes += 1
            except Exception as e:
                log_warning("updater", f"Impossible de supprimer {fichier_relatif} : {e}")
    log_event("updater", f"Restauration terminée : {fichiers_restaures} fichiers restaurés")
    message = f"✅ Code restauré depuis '{nom_sauvegarde}'\nFichiers restaurés : {fichiers_restaures}"
    if supprimer_nouveaux:
        message += f"\nFichiers nouveaux supprimés : {fichiers_supprimes}"
    return message

def restaurer_derniere_sauvegarde(confirmer=False, supprimer_nouveaux=False):
    if not confirmer:
        raise PermissionError("Restauration refusée sans confirmation explicite (confirmer=True).")
    sauvegardes = lister_sauvegardes()
    if not sauvegardes:
        raise FileNotFoundError("Aucune sauvegarde disponible.")
    return restaurer_sauvegarde_specifique(sauvegardes[0], confirmer=True, supprimer_nouveaux=supprimer_nouveaux)

def verifier_integrite_post_rollback():
    log_event("updater", "Vérification intégrité post-rollback...")
    try:
        from . import test_runner
        tests = test_runner.executer_suite_tests()
        return {"ok": tests.get("ok", False), "tests": tests}
    except Exception as e:
        log_error("updater", f"Vérification intégrité échouée : {e}", exc_info=True)
        return {"ok": False, "erreur": str(e)}

def _purger_anciennes_sauvegardes():
    sauvegardes = lister_sauvegardes()
    compteur = 0
    for nom in sauvegardes:
        meta = _charger_metadonnees(nom)
        if meta and meta.get("important"):
            continue
        compteur += 1
        if compteur > NOMBRE_MAX_SAUVEGARDES:
            try:
                shutil.rmtree(Path(DOSSIER_SAUVEGARDES) / nom)
                log_event("updater", f"Ancienne sauvegarde supprimée : {nom}")
            except Exception as e:
                log_warning("updater", f"Purge de '{nom}' échouée : {e}")

def obtenir_points_restauration():
    points = []
    for nom in lister_sauvegardes():
        meta = _charger_metadonnees(nom)
        if meta:
            points.append({"nom": nom, "date": meta.get("date", "?")[:16], "version": meta.get("version", "?"), "important": meta.get("important", False), "etiquette": meta.get("etiquette", "")})
        else:
            points.append({"nom": nom, "date": "?", "version": "?", "important": False, "etiquette": ""})
    return points
