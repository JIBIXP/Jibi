"""
Application sécurisée des mises à jour — PATCHÉ v2
- Branché sur core/config.py
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

try:
    from core.config import JIBI_PROJET_DIR as _DEPOT, WORKSPACE_DIR
    DEPOT_DIR = str(_DEPOT)
    JOURNAL_DIR = WORKSPACE_DIR / "updater_logs"
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    from core.config import GITHUB_BRANCH as BRANCHE
    REMOTE = "origin"
except Exception:
    from dotenv import load_dotenv
    load_dotenv(override=True)
    DEPOT_DIR = os.path.abspath(os.getenv("JIBI_PROJET_DIR", "."))
    REMOTE = os.getenv("JIBI_GIT_REMOTE", "origin")
    BRANCHE = os.getenv("JIBI_GIT_BRANCHE", "main")
    JOURNAL_DIR = Path(DEPOT_DIR) / "workspace" / "updater_logs"
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

try:
    from logging_jibi import log_event, log_warning, log_error
except Exception:
    def log_event(*a, **kw): pass
    def log_warning(*a, **kw): pass
    def log_error(*a, **kw): pass

from . import checker, rollback, git_manager, test_runner

def _journaliser_update(resultat):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fichier = JOURNAL_DIR / f"update_{timestamp}.log"
    try:
        lignes = [f"Date : {datetime.now().isoformat()}", f"Succès : {resultat.get('succes', False)}", f"Version avant : {resultat.get('version_avant', '?')}", f"Version après : {resultat.get('version_apres', '?')}", f"Commits appliqués : {resultat.get('commits_appliques', 0)}", "", "Détails :"]
        for cle, valeur in resultat.items():
            if cle not in ["succes", "version_avant", "version_apres", "commits_appliques"]:
                lignes.append(f"  {cle} : {valeur}")
        fichier.write_text("\n".join(lignes), encoding="utf-8")
    except Exception as e:
        log_warning("updater", f"Impossible de journaliser : {e}")

def pre_verification_complete():
    log_event("updater", "Pré-vérifications...")
    rapport = checker.obtenir_rapport_complet() if hasattr(checker, "obtenir_rapport_complet") else {}
    # fallback si checker n'a pas cette fonction
    if not rapport:
        try:
            maj = checker.verifier_mise_a_jour()
            rapport = {"mise_a_jour_disponible": maj.get("mise_a_jour_disponible"), "comparaison": {"local": maj.get("version_locale"), "distant": maj.get("version_distante"), "commits_en_retard": maj.get("commits_en_retard")}, "preparation": {"pret": True, "bloquants": []}}
        except Exception as e:
            return {"ok": False, "rapport": {}, "bloquants": [str(e)]}
    if not rapport.get("mise_a_jour_disponible"):
        return {"ok": False, "rapport": rapport, "bloquants": ["Aucune mise à jour disponible."]}
    preparation = rapport.get("preparation", {})
    if preparation and not preparation.get("pret", True):
        return {"ok": False, "rapport": rapport, "bloquants": preparation.get("bloquants", [])}
    return {"ok": True, "rapport": rapport, "bloquants": [], "avertissements": preparation.get("avertissements", [])}

def creer_backup_intelligent(version_locale):
    log_event("updater", "Création de la sauvegarde...")
    etiquette = f"avant_update_{version_locale}"
    chemin = rollback.creer_sauvegarde(etiquette=etiquette)
    log_event("updater", f"Sauvegarde créée : {chemin}")
    return chemin

def mettre_a_jour_git():
    log_event("updater", "Application de la mise à jour Git...")
    try:
        resultat = git_manager.git_pull(BRANCHE)
        if not resultat.get("ok"):
            return {"ok": False, "message": resultat.get("message", "Échec git pull")}
        version_apres = checker.version_locale()
        log_event("updater", f"Mise à jour Git réussie → {version_apres}")
        return {"ok": True, "version_apres": version_apres, "message": "Mise à jour Git appliquée."}
    except Exception as e:
        log_error("updater", f"Erreur lors de la mise à jour Git : {e}", exc_info=True)
        return {"ok": False, "message": str(e)}

def installer_dependances():
    requirements_path = Path(DEPOT_DIR) / "requirements.txt"
    if not requirements_path.exists():
        return {"ok": True, "installe": False, "message": "Aucun requirements.txt trouvé."}
    log_event("updater", "Installation des dépendances...")
    try:
        resultat = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_path), "--quiet"], cwd=DEPOT_DIR, capture_output=True, text=True, timeout=300)
        if resultat.returncode != 0:
            log_warning("updater", f"Installation dépendances échouée : {resultat.stderr[:500]}")
            return {"ok": False, "installe": False, "message": f"Échec pip install : {resultat.stderr[:200]}"}
        log_event("updater", "Dépendances installées avec succès.")
        return {"ok": True, "installe": True, "message": "Dépendances installées."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "installe": False, "message": "Installation dépendances : timeout."}
    except Exception as e:
        log_error("updater", f"Erreur installation dépendances : {e}", exc_info=False)
        return {"ok": False, "installe": False, "message": str(e)}

def executer_tests_post_update():
    log_event("updater", "Lancement des tests post-update...")
    rapport = test_runner.executer_suite_tests()
    if rapport.get("ok"):
        log_event("updater", "✅ Tous les tests sont passés.")
    else:
        log_error("updater", f"❌ Tests échoués : {rapport.get('echecs', 0)}", exc_info=False)
    return rapport

def valider_update_ou_rollback(tests_ok, chemin_sauvegarde):
    if tests_ok:
        log_event("updater", "✅ Mise à jour validée.")
        return {"valide": True, "rollback": False, "message": "Mise à jour validée avec succès."}
    log_warning("updater", "⚠️  Tests échoués, rollback automatique...")
    try:
        rollback.restaurer_sauvegarde_specifique(Path(chemin_sauvegarde).name, confirmer=True)
        log_event("updater", "✅ Rollback automatique réussi.")
        return {"valide": False, "rollback": True, "message": "Mise à jour annulée (tests échoués). Code restauré à l'état précédent."}
    except Exception as e:
        log_error("updater", f"❌ Rollback automatique échoué : {e}", exc_info=True)
        return {"valide": False, "rollback": False, "message": f"ERREUR CRITIQUE : mise à jour échouée ET rollback échoué ({e}). Restauration manuelle nécessaire depuis : {chemin_sauvegarde}"}

def appliquer_mise_a_jour_securisee(confirmer=False):
    if not confirmer:
        raise PermissionError("Mise à jour refusée sans confirmation explicite (confirmer=True).")
    log_event("updater", "=" * 60 + "\nDÉMARRAGE MISE À JOUR SÉCURISÉE JIBI\n" + "=" * 60)
    resultat_final = {"succes": False, "etape_echec": None}
    pre_verif = pre_verification_complete()
    if not pre_verif["ok"]:
        message = "❌ Mise à jour bloquée :\n" + "\n".join(f"  • {b}" for b in pre_verif["bloquants"])
        resultat_final["etape_echec"] = "pre_verification"
        resultat_final["message"] = message
        _journaliser_update(resultat_final)
        return message
    rapport = pre_verif["rapport"]
    comparaison = rapport.get("comparaison", {})
    version_avant = comparaison.get("local", "?")
    version_distante = comparaison.get("distant", "?")
    commits_appliques = comparaison.get("commits_en_retard", 0)
    resultat_final["version_avant"] = version_avant
    resultat_final["version_apres"] = version_distante
    resultat_final["commits_appliques"] = commits_appliques
    try:
        chemin_sauvegarde = creer_backup_intelligent(version_avant)
        resultat_final["sauvegarde"] = str(chemin_sauvegarde)
    except Exception as e:
        message = f"❌ Échec création sauvegarde : {e}"
        resultat_final["etape_echec"] = "sauvegarde"
        resultat_final["message"] = message
        _journaliser_update(resultat_final)
        log_error("updater", message, exc_info=True)
        return message
    maj_git = mettre_a_jour_git()
    if not maj_git["ok"]:
        message = f"❌ Échec mise à jour Git : {maj_git['message']}\nCode restauré depuis : {chemin_sauvegarde}"
        resultat_final["etape_echec"] = "git"
        resultat_final["message"] = maj_git["message"]
        try:
            rollback.restaurer_sauvegarde_specifique(Path(chemin_sauvegarde).name, confirmer=True)
        except Exception:
            pass
        _journaliser_update(resultat_final)
        return message
    resultat_final["version_apres"] = maj_git.get("version_apres", version_distante)
    deps = installer_dependances()
    resultat_final["dependances"] = deps
    tests = executer_tests_post_update()
    resultat_final["tests"] = tests
    validation = valider_update_ou_rollback(tests.get("ok", False), chemin_sauvegarde)
    resultat_final["valide"] = validation["valide"]
    resultat_final["rollback"] = validation["rollback"]
    resultat_final["succes"] = validation["valide"]
    _journaliser_update(resultat_final)
    if validation["valide"]:
        message = f"✅ MISE À JOUR RÉUSSIE\n\nVersion : {version_avant} → {resultat_final['version_apres']}\nCommits appliqués : {commits_appliques}\nTests : ✅ Passés ({tests.get('reussis', 0)}/{tests.get('total', 0)})\nSauvegarde : {chemin_sauvegarde}\n\n🔄 Redémarre JIBI pour appliquer les changements."
        log_event("updater", "MISE À JOUR RÉUSSIE")
    elif validation["rollback"]:
        message = f"⚠️  MISE À JOUR ANNULÉE (tests échoués)\n\nCode restauré à : {version_avant}\nTests échoués : {tests.get('echecs', 0)}/{tests.get('total', 0)}\nSauvegarde conservée : {chemin_sauvegarde}\n\nConsulte les logs pour plus de détails."
        log_warning("updater", "MISE À JOUR ANNULÉE (rollback auto)")
    else:
        message = validation["message"]
        log_error("updater", "ERREUR CRITIQUE MISE À JOUR", exc_info=False)
    return message

def appliquer_mise_a_jour(confirmer=False):
    return appliquer_mise_a_jour_securisee(confirmer=confirmer)
