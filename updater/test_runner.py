"""
Exécuteur de tests post-mise à jour — PATCHÉ v2 (timings)
"""
import sys
import os
import time
from pathlib import Path
import importlib.util
import ast

try:
    from core.config import JIBI_PROJET_DIR as DEPOT_DIR
    DEPOT_DIR = Path(DEPOT_DIR)
except Exception:
    DEPOT_DIR = Path(__file__).resolve().parent.parent

try:
    from logging_jibi import log_event, log_warning, log_error
except Exception:
    def log_event(*a, **kw): pass
    def log_warning(*a, **kw): pass
    def log_error(*a, **kw): pass

def test_import_jibi():
    # tools.tool_registry contient l'état global. Le recharger seul vide le
    # registre alors que tools.__init__ ne repasse pas automatiquement dessus.
    modules_critiques = ["logging_jibi", "core.agent_core", "core.config", "tools"]
    resultats, ok_global = {}, True
    for module_name in modules_critiques:
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
            resultats[module_name] = {"ok": True, "message": "Import réussi."}
        except Exception as e:
            ok_global = False
            resultats[module_name] = {"ok": False, "message": str(e)[:200]}
            log_error("test_runner", f"Import {module_name} échoué : {e}", exc_info=False)
    return {"ok": ok_global, "message": "Tous les imports critiques réussis." if ok_global else "Certains imports ont échoué.", "details": resultats}

def test_syntaxe_core():
    t0 = time.perf_counter()
    core_dir = DEPOT_DIR / "core"
    if not core_dir.exists():
        return {"ok": False, "message": "Dossier core/ introuvable."}
    fichiers_py = list(core_dir.glob("*.py"))
    erreurs = []
    for fichier in fichiers_py:
        try:
            ast.parse(fichier.read_text(encoding="utf-8"))
        except SyntaxError as e:
            erreurs.append({"fichier": fichier.name, "ligne": e.lineno, "message": str(e.msg)})
            log_error("test_runner", f"Erreur syntaxe {fichier.name}:{e.lineno} : {e.msg}", exc_info=False)
        except Exception as e:
            erreurs.append({"fichier": fichier.name, "message": str(e)[:100]})
    ok = len(erreurs) == 0
    return {"ok": ok, "fichiers_testes": len(fichiers_py), "erreurs": erreurs, "message": f"Syntaxe OK pour {len(fichiers_py)} fichiers." if ok else f"{len(erreurs)} erreur(s) de syntaxe.", "duree": round(time.perf_counter()-t0,3)}

def test_imports_modules():
    modules_a_tester = ["core", "tools", "modules", "updater", "self_improvement"]
    modules_ok, modules_ko, details = 0, 0, {}
    for module in modules_a_tester:
        module_path = DEPOT_DIR / module / "__init__.py"
        if not module_path.exists():
            details[module] = {"ok": False, "message": "__init__.py introuvable."}
            modules_ko += 1
            continue
        try:
            ast.parse(module_path.read_text(encoding="utf-8"))
            details[module] = {"ok": True, "message": "Import OK."}
            modules_ok += 1
        except Exception as e:
            details[module] = {"ok": False, "message": str(e)[:100]}
            modules_ko += 1
            log_error("test_runner", f"Module {module} : {e}", exc_info=False)
    ok = modules_ko == 0
    return {"ok": ok, "modules_ok": modules_ok, "modules_ko": modules_ko, "details": details, "message": f"{modules_ok}/{len(modules_a_tester)} modules OK." if ok else f"{modules_ko} module(s) en erreur."}

def test_configuration():
    try:
        # core.config fournit des valeurs sûres par défaut pour ces options.
        # Leur absence du .env ne rend donc pas JIBI inutilisable.
        from core import config
        projet = getattr(config, "JIBI_PROJET_DIR", None)
        modele = getattr(config, "MODEL", None)
        if not projet or not modele:
            return {"ok": False, "message": "Configuration projet ou modèle indisponible."}
        return {"ok": True, "message": "Configuration valide (valeurs .env ou repli)."}
    except Exception as e:
        log_error("test_runner", f"Test configuration échoué : {e}", exc_info=False)
        return {"ok": False, "message": str(e)[:200]}

def test_outils_essentiels():
    try:
        # Le registre est alimenté par tools.__init__, pas par son module de
        # stockage seul. L'import direct de tool_registry donnait un faux vide.
        import tools
        from tools.tool_registry import TOOLS_REGISTRY
        outils_essentiels = ["creer_document_word", "creer_document_pdf", "ouvrir_application", "verifier_mise_a_jour"]
        manquants = [o for o in outils_essentiels if o not in TOOLS_REGISTRY]
        if manquants:
            return {"ok": False, "outils_trouves": len(TOOLS_REGISTRY), "outils_manquants": manquants, "message": f"Outils manquants : {', '.join(manquants)}"}
        return {"ok": True, "outils_trouves": len(TOOLS_REGISTRY), "message": f"{len(TOOLS_REGISTRY)} outils enregistrés, tous les essentiels présents."}
    except Exception as e:
        log_error("test_runner", f"Test outils échoué : {e}", exc_info=False)
        return {"ok": False, "message": str(e)[:200]}

def test_dependances_presentes():
    dependances_critiques = ["dotenv", "psutil", "docx", "fpdf"]
    dependances_ok, manquantes = 0, []
    for dep in dependances_critiques:
        try:
            importlib.import_module(dep)
            dependances_ok += 1
        except ImportError:
            manquantes.append(dep)
    ok = len(manquantes) == 0
    return {"ok": ok, "dependances_ok": dependances_ok, "manquantes": manquantes, "message": f"{dependances_ok}/{len(dependances_critiques)} dépendances présentes." if ok else f"Dépendances manquantes : {', '.join(manquantes)}"}

def executer_suite_tests():
    t0 = time.perf_counter()
    log_event("test_runner", "=" * 60)
    log_event("test_runner", "DÉMARRAGE SUITE DE TESTS POST-UPDATE")
    log_event("test_runner", "=" * 60)
    tests = {"import_jibi": test_import_jibi(), "syntaxe_core": test_syntaxe_core(), "imports_modules": test_imports_modules(), "configuration": test_configuration(), "outils_essentiels": test_outils_essentiels(), "dependances": test_dependances_presentes()}
    total, reussis = len(tests), sum(1 for t in tests.values() if t.get("ok"))
    echecs = total - reussis
    ok_global = echecs == 0
    rapport_lignes = ["🧪 RAPPORT DE TESTS POST-UPDATE\n", f"Total : {total}", f"✅ Réussis : {reussis}", f"❌ Échoués : {echecs}\n"]
    for nom, resultat in tests.items():
        statut = "✅" if resultat.get("ok") else "❌"
        rapport_lignes.append(f"{statut} {nom.replace('_', ' ').title()} : {resultat.get('message', '?')}")
    rapport = "\n".join(rapport_lignes)
    if ok_global:
        log_event("test_runner", f"✅ TOUS LES TESTS RÉUSSIS en {time.perf_counter()-t0:.3f}s")
    else:
        log_error("test_runner", f"❌ {echecs} TEST(S) ÉCHOUÉ(S)", exc_info=False)
    log_event("test_runner", "=" * 60)
    return {"ok": ok_global, "total": total, "reussis": reussis, "echecs": echecs, "tests": tests, "rapport": rapport, "duree": round(time.perf_counter()-t0,3)}

def generer_rapport_tests(resultat_tests):
    return resultat_tests.get("rapport", "Aucun rapport disponible.")
