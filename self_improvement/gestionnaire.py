"""
Gestionnaire — PATCHÉ v2
- Fix cohérence coherent→ok + config + timings + logs
"""
import os
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from self_improvement.autorisation import examiner_proposition, valider_proposition, rejeter_proposition, marquer_appliquee, autorisation_valide
from self_improvement.analyseur import lire_logs, analyser_logs, calculer_score_sante, detecter_patterns_recurrents, sauvegarder_analyse
from self_improvement.propositions import creer_proposition, sauvegarder_proposition, lister_propositions, charger_proposition, obtenir_statistiques
from self_improvement.laboratoire import creer_session, copier_fichier_dans_laboratoire, comparer_fichiers, compter_sessions
from self_improvement.testeur import tester_fichier
from self_improvement.validation import analyser_modification, est_fichier_sensible
from self_improvement.versions import creer_backup, restaurer_backup, compter_backups
from self_improvement.code_generator import generer_patch, appliquer_patch, verifier_coherence, generer_diff_lisible

try:
    from core.config import JIBI_PROJET_DIR as CFG_DEPOT
    DEPOT_DIR = CFG_DEPOT
except Exception:
    DEPOT_DIR = Path(os.getenv("JIBI_PROJET_DIR", Path(__file__).resolve().parent.parent)).resolve()

try:
    from logging_jibi import log_event, log_warning
except Exception:
    def log_event(*a, **kw): pass
    def log_warning(*a, **kw): pass

def analyser_jibi(limite_logs: int = 1000, depuis_heures: int = 24) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        analyse = analyser_logs(depuis_heures=depuis_heures, limite=limite_logs)
    except TypeError:
        analyse = analyser_logs(depuis_heures=depuis_heures)
    except Exception as e:
        return {"erreur": f"Analyse impossible : {e}"}
    score = analyse.get("score_sante", 100)
    patterns = analyse.get("patterns_recurrents", [])
    recommandations = []
    if score < 60:
        recommandations.append("⚠️  Score critique — révision prioritaire")
    if patterns:
        recommandations.append(f"🔁 {len(patterns)} patterns récurrents détectés")
    if not recommandations:
        recommandations.append("✅ Système stable")
    log_event("gestionnaire", f"Analyse JIBI en {time.perf_counter()-t0:.3f}s score={score}")
    return {"timestamp": datetime.now().isoformat(), "score_sante": score, "etat": analyse.get("niveau_sante", "Inconnu"), "erreurs": analyse.get("nombre_erreurs", 0), "warnings": analyse.get("nombre_warnings", 0), "patterns_recurrents": patterns, "logs_analyses": analyse.get("logs_lignes", 0), "recommandations": recommandations, "duree": round(time.perf_counter()-t0,3)}

def preparer_amelioration(fichier: str, probleme: str, solution: str, justification: str = "", priorite: str = "moyenne") -> Dict[str, Any]:
    t0 = time.perf_counter()
    raisons_blocage = []
    proposition = creer_proposition(fichier=fichier, probleme=probleme, solution=solution, justification=justification, priorite=priorite)
    sauvegarder_proposition(proposition)
    proposition_id = proposition["id"]
    try:
        session_path = creer_session(f"prop_{proposition_id}")
    except Exception as e:
        raisons_blocage.append(f"Impossible de créer le laboratoire : {e}")
        return _resultat_echec(proposition, raisons_blocage)
    validation = analyser_modification(fichier, solution)
    if validation.get("niveau") == "bloqué":
        raisons_blocage.append(f"Sécurité BLOQUÉE : {validation.get('action','')}")
        return _resultat_echec(proposition, raisons_blocage)
    fichier_original = DEPOT_DIR / fichier
    if not fichier_original.exists():
        raisons_blocage.append(f"Fichier source introuvable : {fichier_original}")
        return _resultat_echec(proposition, raisons_blocage)
    if est_fichier_sensible(str(fichier_original)):
        raisons_blocage.append(f"Fichier SENSIBLE : {fichier}")
        return _resultat_echec(proposition, raisons_blocage)
    fichier_lab = None
    try:
        fichier_lab = copier_fichier_dans_laboratoire(fichier_original, session_path)
    except Exception as e:
        raisons_blocage.append(f"Erreur copie labo : {e}")
        return _resultat_echec(proposition, raisons_blocage)
    patch = None
    try:
        patch = generer_patch(str(fichier_original), proposition)
        if patch and not patch.get("ok"):
            raisons_blocage.append(f"Patch échoué : {patch.get('message','')}")
            return _resultat_echec(proposition, raisons_blocage)
    except Exception as e:
        raisons_blocage.append(f"Génération patch : {e}")
        return _resultat_echec(proposition, raisons_blocage)
    fichier_modifie = None
    if patch and patch.get("ok") and fichier_lab:
        try:
            fichier_modifie = Path(appliquer_patch(str(fichier_lab), patch))
        except Exception as e:
            raisons_blocage.append(f"Application patch labo : {e}")
            return _resultat_echec(proposition, raisons_blocage)
    coherence = None
    if fichier_modifie:
        try:
            coherence = verifier_coherence(str(fichier_original), str(fichier_modifie))
            if not coherence.get("ok"):
                raisons_blocage.append(f"Incohérence : {coherence.get('message')}")
                return _resultat_echec(proposition, raisons_blocage)
        except Exception as e:
            raisons_blocage.append(f"Cohérence : {e}")
            return _resultat_echec(proposition, raisons_blocage)
    tests = None
    if fichier_modifie:
        try:
            tests = tester_fichier(str(fichier_modifie))
            if not tests.get("valide", tests.get("ok", False)):
                raisons_blocage.append("Tests labo échoués.")
                return _resultat_echec(proposition, raisons_blocage)
        except Exception as e:
            raisons_blocage.append(f"Tests : {e}")
            return _resultat_echec(proposition, raisons_blocage)
    backup = None
    try:
        backup = creer_backup(fichier_original, raison=f"Prep {proposition_id}")
    except Exception as e:
        log_warning("gestionnaire", f"Backup prep échoué : {e}")
    diff = None
    if fichier_modifie:
        try:
            diff = generer_diff_lisible(str(fichier_original), str(fichier_modifie))
        except Exception:
            pass
    log_event("gestionnaire", f"Prep {proposition_id} OK en {time.perf_counter()-t0:.3f}s")
    return {"proposition": proposition, "proposition_id": proposition_id, "session": str(session_path), "fichier_source": str(fichier_original), "fichier_labo": str(fichier_modifie), "validation": validation, "patch": patch, "coherence": coherence, "tests": tests, "backup": str(backup) if backup else None, "diff": diff, "pret_pour_application": False, "raisons_blocage": raisons_blocage, "duree": round(time.perf_counter()-t0,3)}

def _resultat_echec(proposition, raisons):
    return {"proposition": proposition, "proposition_id": proposition.get("id"), "pret_pour_application": False, "raisons_blocage": raisons}

def appliquer_amelioration(proposition_id: str, confirmation: str = "") -> Dict[str, Any]:
    proposition = charger_proposition(proposition_id)
    if not proposition:
        return {"succes": False, "erreur": f"Proposition '{proposition_id}' introuvable."}
    if proposition.get("statut") == "rejetee":
        return {"succes": False, "erreur": "Proposition déjà rejetée."}
    if not autorisation_valide(proposition_id, confirmation):
        return {"succes": False, "erreur": f"Autorisation invalide. Format attendu : J'AUTORISE {proposition_id}"}
    res_valid = valider_proposition(prop_id=proposition_id, confirmation=confirmation, commentaire="Validation avant application.")
    if not res_valid.get("ok"):
        return {"succes": False, "erreur": res_valid.get("message", "Validation refusée.")}
    fichier_cible_str = proposition.get("fichier", "")
    fichier_cible = DEPOT_DIR / fichier_cible_str
    if est_fichier_sensible(fichier_cible_str):
        return {"succes": False, "erreur": f"Fichier sensible : {fichier_cible_str}"}
    if not fichier_cible.exists():
        return {"succes": False, "erreur": f"Fichier absent : {fichier_cible}"}
    try:
        backup = creer_backup(fichier_cible, raison=f"Avant {proposition_id}")
    except Exception as e:
        return {"succes": False, "erreur": f"Backup impossible : {e}"}
    sessions_dir = DEPOT_DIR / "workspace" / "jibi_lab" / "sessions"
    session = None
    if sessions_dir.exists():
        for d in sorted(sessions_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if d.is_dir() and f"prop_{proposition_id}" in d.name:
                session = d
                break
    if not session:
        return {"succes": False, "erreur": "Session labo introuvable.", "backup": str(backup)}
    nom_fichier = Path(fichier_cible_str).name
    fichier_lab = session / nom_fichier
    if not fichier_lab.exists():
        candidats = list(session.rglob(nom_fichier))
        if candidats:
            fichier_lab = candidats[0]
    if not fichier_lab.exists():
        return {"succes": False, "erreur": "Fichier labo introuvable.", "backup": str(backup)}
    try:
        shutil.copy2(fichier_lab, fichier_cible)
    except Exception as e:
        return {"succes": False, "erreur": f"Copie impossible : {e}", "backup": str(backup)}
    try:
        tests_post = tester_fichier(str(fichier_cible))
    except Exception as e:
        tests_post = {"ok": False, "valide": False, "message": str(e)}
    if not tests_post.get("valide", tests_post.get("ok", False)):
        try:
            restaurer_backup(backup, destination=fichier_cible)
        except Exception:
            pass
        return {"succes": False, "erreur": "Tests post-échec. Rollback effectué.", "rollback": True, "backup": str(backup)}
    marquer_appliquee(proposition_id)
    return {"succes": True, "proposition_id": proposition_id, "fichier": str(fichier_cible), "backup": str(backup), "message": "Amélioration appliquée avec succès."}

def autoriser_et_appliquer(proposition_id: str, confirmation: str, commentaire: str = "") -> Dict[str, Any]:
    res_valid = valider_proposition(prop_id=proposition_id, confirmation=confirmation, commentaire=commentaire or "Accord utilisateur.")
    if not res_valid.get("ok"):
        return {"succes": False, "etape": "autorisation", "message": res_valid.get("message", "Validation refusée.")}
    return appliquer_amelioration(proposition_id=proposition_id, confirmation=confirmation)

def resoudre_probleme_persistant(depuis_heures: int = 24) -> Dict[str, Any]:
    try:
        analyse = analyser_jibi(depuis_heures=depuis_heures)
    except Exception as e:
        return {"erreur": str(e)}
    propositions = []
    for p in analyse.get("patterns_recurrents", [])[:3]:
        try:
            prep = preparer_amelioration(fichier="tools/", probleme=str(p.get("message",""))[:200], solution="Correction auto (à valider)", priorite="haute")
            if prep.get("proposition_id"):
                propositions.append(prep["proposition_id"])
        except Exception:
            pass
    return {"analyse": analyse, "propositions": propositions, "deploiement": False}

def workflow_complet_amelioration(fichier: str, probleme: str, solution: str, justification: str = "", priorite: str = "moyenne", appliquer_automatiquement: bool = False) -> Dict[str, Any]:
    if appliquer_automatiquement:
        print("⚠️  Auto-application IGNORÉE. Autorisation humaine obligatoire.")
    prep = preparer_amelioration(fichier=fichier, probleme=probleme, solution=solution, justification=justification, priorite=priorite)
    return {"preparation": prep, "deploiement": False, "proposition_id": prep.get("proposition_id")}

def tableau_de_bord() -> Dict[str, Any]:
    try:
        stats = obtenir_statistiques()
        sessions = compter_sessions()
        backups = compter_backups()
    except Exception:
        stats, sessions, backups = {}, 0, 0
    return {"propositions": stats, "sessions": sessions, "backups": backups}
