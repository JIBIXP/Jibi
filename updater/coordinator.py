"""
Coordinateur UPDATER ↔ SELF_IMPROVEMENT — PATCHÉ v2
- Branché sur core/config.py + timings
"""
import os
import time
from pathlib import Path
from datetime import datetime

try:
    from core.config import JIBI_PROJET_DIR as _DEPOT, WORKSPACE_DIR
    DEPOT_DIR = _DEPOT
except Exception:
    DEPOT_DIR = Path(__file__).resolve().parent.parent

try:
    from logging_jibi import log_event, log_warning, log_error
except Exception:
    def log_event(*a, **kw): pass
    def log_warning(*a, **kw): pass
    def log_error(*a, **kw): pass

def detecter_source_modification(fichiers_modifies=None):
    t0 = time.perf_counter()
    from . import git_manager
    status = git_manager.git_status_detaille()
    modifications_locales = status.get("modifies", [])
    non_suivis = status.get("non_suivis", [])
    commits = git_manager.obtenir_commits_ahead_behind()
    behind, ahead = commits.get("behind", 0), commits.get("ahead", 0)
    if behind > 0:
        log_event("coordinator", f"Source détectée : GitHub ({behind} commit(s) en attente) en {time.perf_counter()-t0:.3f}s")
        return "github"
    if fichiers_modifies:
        for fichier in fichiers_modifies:
            if "jibi_lab" in str(fichier) or "self_improvement" in str(fichier):
                log_event("coordinator", "Source détectée : self_improvement (jibi_lab)")
                return "self_improvement"
    if modifications_locales or non_suivis:
        log_event("coordinator", "Source détectée : manuelle (modifications locales)")
        return "manuelle"
    if ahead > 0:
        log_event("coordinator", f"Source détectée : manuelle ({ahead} commit(s) locaux)")
        return "manuelle"
    return "inconnue"

def choisir_strategie_backup(source):
    if source == "github":
        return {"module": "updater", "dossier": Path(DEPOT_DIR) / "workspace" / "updater_backups", "important": True, "etiquette": "update_github"}
    elif source == "self_improvement":
        return {"module": "self_improvement", "dossier": Path(DEPOT_DIR) / "workspace" / "jibi_lab" / "backups", "important": False, "etiquette": "auto_amelioration"}
    else:
        return {"module": "updater", "dossier": Path(DEPOT_DIR) / "workspace" / "updater_backups", "important": True, "etiquette": "modification_manuelle"}

def decider_tests(source, fichiers_modifies=None):
    if source == "github":
        return {"module": "updater", "tests": ["import_jibi", "syntaxe_core", "imports_modules", "configuration", "outils_essentiels", "dependances"]}
    elif source == "self_improvement":
        return {"module": "self_improvement", "tests": ["syntaxe", "imports", "securite"]}
    else:
        return {"module": "updater", "tests": ["import_jibi", "syntaxe_core"]}

def synchroniser_backups():
    try:
        from . import rollback
        nb_updater = len(rollback.lister_sauvegardes())
    except Exception:
        nb_updater = 0
    try:
        from self_improvement import versions
        nb_si = len(versions.lister_backups())
    except Exception:
        nb_si = 0
    log_event("coordinator", f"Backups : {nb_updater} (updater), {nb_si} (self_improvement)")
    return {"updater_backups": nb_updater, "self_improvement_backups": nb_si, "doublons_supprimes": 0}

def obtenir_etat_global():
    lignes = ["╔════════════════════════════════════════════════╗", "║     🚀 JIBI - ÉTAT GLOBAL                     ║", "╠════════════════════════════════════════════════╣"]
    try:
        from . import checker
        version = checker.version_locale()
        lignes.append(f"║  Version : {version}".ljust(49) + "║")
    except Exception:
        lignes.append("║  Version : ?".ljust(49) + "║")
    try:
        from . import checker
        rapport = checker.obtenir_rapport_complet() if hasattr(checker, "obtenir_rapport_complet") else checker.verifier_mise_a_jour()
        comp = rapport.get("comparaison", {})
        if comp.get("commits_en_retard", 0) > 0:
            lignes.append(f"║  📦 Update disponible : {comp['commits_en_retard']} commit(s)".ljust(49) + "║")
        else:
            lignes.append("║  ✅ À jour".ljust(49) + "║")
    except Exception:
        lignes.append("║  État update : ?".ljust(49) + "║")
    lignes.append("╠════════════════════════════════════════════════╣")
    try:
        from self_improvement import analyseur
        analyse = analyseur.analyser_logs()
        lignes.append(f"║  Santé : {analyse.get('niveau_sante', '?')} ({analyse.get('score_sante', 0)}/100)".ljust(49) + "║")
        lignes.append(f"║  Erreurs récentes : {analyse.get('nombre_erreurs', 0)}".ljust(49) + "║")
    except Exception:
        lignes.append("║  Santé : ?".ljust(49) + "║")
    lignes.append("╠════════════════════════════════════════════════╣")
    lignes.append("║  📦 UPDATER".ljust(49) + "║")
    try:
        from . import rollback
        backups = rollback.lister_sauvegardes()
        lignes.append(f"║    Sauvegardes : {len(backups)}".ljust(49) + "║")
        if backups:
            lignes.append(f"║    Dernière : {backups[0][:30]}...".ljust(49) + "║")
    except Exception:
        lignes.append("║    Sauvegardes : ?".ljust(49) + "║")
    lignes.append("╠════════════════════════════════════════════════╣")
    lignes.append("║  🧠 SELF-IMPROVEMENT".ljust(49) + "║")
    try:
        from self_improvement import propositions, laboratoire
        props = propositions.lister_propositions()
        sessions = laboratoire.compter_sessions()
        lignes.append(f"║    Propositions : {len(props)}".ljust(49) + "║")
        lignes.append(f"║    Sessions labo : {sessions}".ljust(49) + "║")
        en_cours = [p for p in props if p.get("statut") == "en_cours"]
        if en_cours:
            lignes.append(f"║    En cours : {len(en_cours)}".ljust(49) + "║")
    except Exception:
        lignes.append("║    État : ?".ljust(49) + "║")
    lignes.append("╠════════════════════════════════════════════════╣")
    lignes.append(f"║  Date : {datetime.now().strftime('%Y-%m-%d %H:%M')}".ljust(49) + "║")
    lignes.append("╚════════════════════════════════════════════════╝")
    log_event("coordinator", "État global généré")
    return "\n".join(lignes)

def verifier_conflits_updater_self_improvement():
    try:
        from . import git_manager
        modifies_git = set(git_manager.obtenir_fichiers_modifies())
        from self_improvement import laboratoire
        lab_root = laboratoire.LABORATOIRE_ROOT / "sessions"
        modifies_si = set()
        if lab_root.exists():
            for session in lab_root.iterdir():
                if session.is_dir():
                    for fichier in session.rglob("*.py"):
                        try:
                            modifies_si.add(str(fichier.relative_to(session)))
                        except ValueError:
                            pass
        conflits = modifies_git & modifies_si
        if conflits:
            log_warning("coordinator", f"Conflit détecté : {len(conflits)} fichier(s)")
            return {"conflit": True, "fichiers_conflits": list(conflits), "message": f"{len(conflits)} fichier(s) en conflit entre updater et self_improvement."}
        return {"conflit": False, "fichiers_conflits": [], "message": "Aucun conflit détecté."}
    except Exception as e:
        log_error("coordinator", f"Vérification conflits échouée : {e}", exc_info=False)
        return {"conflit": False, "erreur": str(e), "message": "Impossible de vérifier les conflits."}

def nettoyer_backups_anciens(jours=30):
    updater_supprimes = si_supprimes = 0
    try:
        from . import rollback
        rollback._purger_anciennes_sauvegardes()
    except Exception as e:
        log_warning("coordinator", f"Nettoyage updater échoué : {e}")
    try:
        from self_improvement import laboratoire, versions
        si_supprimes += laboratoire.nettoyer_vieilles_sessions(jours)
        si_supprimes += versions.nettoyer_vieux_backups(jours)
    except Exception as e:
        log_warning("coordinator", f"Nettoyage self_improvement échoué : {e}")
    total = updater_supprimes + si_supprimes
    log_event("coordinator", f"Nettoyage global : {total} éléments supprimés")
    return {"updater_supprimes": updater_supprimes, "self_improvement_supprimes": si_supprimes, "total": total}

def generer_rapport_coordination():
    lignes = ["🔗 RAPPORT DE COORDINATION\n", "=" * 50]
    source = detecter_source_modification()
    lignes.append(f"Source détectée : {source.upper()}\n")
    strategie = choisir_strategie_backup(source)
    lignes.append(f"Stratégie backup : {strategie['module']} ({strategie['etiquette']})")
    tests = decider_tests(source)
    lignes.append(f"Module de tests : {tests['module']}\n")
    sync = synchroniser_backups()
    lignes.append(f"Backups updater : {sync['updater_backups']}")
    lignes.append(f"Backups self_improvement : {sync['self_improvement_backups']}\n")
    conflits = verifier_conflits_updater_self_improvement()
    if conflits.get("conflit"):
        lignes.append(f"⚠️  {conflits['message']}")
        for fichier in conflits.get("fichiers_conflits", []):
            lignes.append(f"  • {fichier}")
    else:
        lignes.append("✅ Aucun conflit détecté.")
    return "\n".join(lignes)
