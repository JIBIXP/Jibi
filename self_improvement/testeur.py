"""
Tests automatiques — PATCHÉ v3.1 (corrigé)
- Regex compilées + détection AST pour eval/exec + timings + gestion syntaxe

CORRECTIFS APPLIQUÉS :
- Suppression de l'appel à `corriger_erreur_syntaxe()`, qui n'existait
  nulle part dans le projet (ni ici, ni dans propositions.py) et faisait
  planter tester_et_corriger_syntaxe() dès la première erreur détectée.
- L'import de `self_improvement.propositions` est de nouveau protégé
  par un try/except avec fallback, comme dans la v4 d'origine, pour
  éviter un ImportError bloquant si ce module est indisponible.
- tester_et_corriger_syntaxe() et generer_propositions_correction()
  utilisent maintenant `creer_proposition_correction_syntaxe(fichier,
  erreur, solution=None)`, conformément à la règle d'architecture :
  ce module TESTE et PROPOSE, il ne modifie JAMAIS un fichier de
  production directement.
"""

from pathlib import Path
import py_compile
import subprocess
import sys
import re
import ast
import time

try:
    from logging_jibi import log_event
except Exception:
    def log_event(*a, **kw): pass

def detecter_erreurs_syntaxe(fichier):
    """Détecte les erreurs de syntaxe sans modifier le fichier."""
    path = Path(fichier)

    if not path.exists():
        return [{
            "type": "fichier_introuvable",
            "message": "Fichier introuvable.",
            "line": 0,
            "colonne": 0,
        }]

    if not path.is_file():
        return [{
            "type": "chemin_invalide",
            "message": "Le chemin n'est pas un fichier.",
            "line": 0,
            "colonne": 0,
        }]

    try:
        contenu = path.read_text(encoding="utf-8-sig", errors="replace")
        compile(contenu, str(path), "exec")
        return []
    except SyntaxError as erreur:
        return [{
            "type": "SyntaxError",
            "message": str(erreur),
            "line": erreur.lineno or 0,
            "colonne": erreur.offset or 0,
            "text": erreur.text or "",
        }]
    except Exception as erreur:
        return [{
            "type": type(erreur).__name__,
            "message": str(erreur),
            "line": 0,
            "colonne": 0,
        }]

# ----------------------------------------------------------------------------
# Import protégé : si self_improvement.propositions est indisponible,
# des stubs sûrs prennent le relais au lieu de faire planter tout le module.
# ----------------------------------------------------------------------------
try:
    from self_improvement.propositions import (
        creer_proposition_correction_syntaxe,
        sauvegarder_proposition
    )
except Exception:
    def creer_proposition_correction_syntaxe(fichier, erreur, solution=None):
        raise RuntimeError("self_improvement.propositions est indisponible.")

    def sauvegarder_proposition(proposition):
        raise RuntimeError("self_improvement.propositions est indisponible.")

PATTERNS_DANGEREUX = [
    (r"os\.system\s*\(", "os.system() — exécution de commande"),
    (r"subprocess\.call\s*\(\s*[^,\]]*shell\s*=\s*True", "subprocess avec shell=True"),
    (r"eval\s*\(", "eval() — exécution de code arbitraire"),
    (r"exec\s*\(", "exec() — exécution de code arbitraire"),
    (r"__import__\s*\(", "__import__() dynamique"),
    (r"shutil\.rmtree\s*\(\s*['\"]/['\"]", "rmtree sur racine système"),
    (r"os\.remove\s*\(\s*['\"]/", "suppression de fichier absolu"),
    (r"open\s*\(\s*['\"]/etc/", "accès aux fichiers système"),
    (r"open\s*\(\s*['\"]/proc/", "accès à /proc"),
]
RE_DANGEREUX = [(re.compile(p), desc) for p, desc in PATTERNS_DANGEREUX]

def tester_syntaxe(fichier):
    fichier = Path(fichier)
    if not fichier.exists():
        return {"ok": False, "message": "Fichier introuvable."}
    if fichier.suffix != ".py":
        return {"ok": True, "message": "Fichier non-Python, syntaxe ignorée."}
    try:
        py_compile.compile(str(fichier), doraise=True)
        return {"ok": True, "message": "Syntaxe Python valide."}
    except py_compile.PyCompileError as erreur:
        return {"ok": False, "message": str(erreur)}

def tester_securite(fichier):
    t0 = time.perf_counter()
    fichier = Path(fichier)
    if not fichier.exists():
        return {"ok": False, "message": "Fichier introuvable.", "alertes": []}
    if fichier.suffix != ".py":
        return {"ok": True, "message": "Fichier non-Python.", "alertes": []}
    try:
        contenu = fichier.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "message": f"Impossible de lire : {e}", "alertes": []}
    alertes = []
    # 1. Scan ligne à ligne avec regex compilées
    for ligne_num, ligne in enumerate(contenu.splitlines(), 1):
        for rx, description in RE_DANGEREUX:
            if rx.search(ligne):
                alertes.append({"ligne": ligne_num, "code": ligne.strip()[:100], "risque": description})
    # 2. Scan AST pour eval/exec même sur plusieurs lignes
    try:
        tree = ast.parse(contenu)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if func_name in ("eval", "exec", "__import__"):
                    alertes.append({"ligne": getattr(node, "lineno", 0), "code": func_name + "()", "risque": f"{func_name}() détecté via AST"})
    except Exception:
        pass
    dt = time.perf_counter() - t0
    return {
        "ok": len(alertes) == 0,
        "nombre_alertes": len(alertes),
        "alertes": alertes,
        "message": "Aucun code dangereux détecté." if not alertes else f"{len(alertes)} alerte(s) de sécurité.",
        "duree": round(dt, 4),
    }

def tester_imports(fichier):
    fichier = Path(fichier)
    if not fichier.exists() or fichier.suffix != ".py":
        return {"ok": False, "message": "Fichier introuvable ou non-Python.", "imports": [], "erreurs": []}
    try:
        contenu = fichier.read_text(encoding="utf-8", errors="replace")
        arbre = ast.parse(contenu)
        imports = []
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                for alias in noeud.names:
                    imports.append(alias.name)
            elif isinstance(noeud, ast.ImportFrom):
                module = noeud.module or ""
                for alias in noeud.names:
                    imports.append(f"{module}.{alias.name}")
        return {"ok": True, "imports": imports, "nombre": len(imports), "erreurs": [], "message": f"{len(imports)} import(s) trouvé(s)."}
    except SyntaxError as e:
        return {"ok": False, "message": f"Erreur de syntaxe : {e}", "imports": [], "erreurs": [str(e)]}

def tester_fichier(fichier):
    t0 = time.perf_counter()
    fichier = Path(fichier)
    syntaxe = tester_syntaxe(fichier)
    securite = tester_securite(fichier)
    imports = tester_imports(fichier)
    ok_global = syntaxe["ok"] and securite["ok"]
    log_event("testeur", f"Test {fichier.name} → {'OK' if ok_global else 'ECHEC'} en {time.perf_counter()-t0:.3f}s")
    return {"ok": ok_global, "valide": ok_global, "fichier": str(fichier), "syntaxe": syntaxe, "securite": securite, "imports": imports, "duree": round(time.perf_counter()-t0, 3)}

def tester_et_corriger_syntaxe(fichier: str) -> dict:
    """
    Teste la syntaxe d'un fichier et crée des propositions de correction
    pour chaque erreur détectée.

    IMPORTANT : cette fonction ne modifie JAMAIS le fichier de production.
    Elle ne fait que détecter et proposer — l'application éventuelle d'un
    correctif appartient au laboratoire / à l'orchestrateur, en aval.
    """
    t0 = time.perf_counter()
    fichier_path = Path(fichier)

    # 1. Vérification initiale
    erreurs = detecter_erreurs_syntaxe(fichier_path)
    if not erreurs:
        return {
            "ok": True,
            "message": "Aucune erreur de syntaxe détectée",
            "erreurs_initiales": [],
            "propositions": [],
            "erreurs_restantes": [],
            "modification_appliquee": False,
            "duree": round(time.perf_counter() - t0, 3)
        }

    # 2. Création de propositions (aucune modification directe)
    propositions = []
    for erreur in erreurs:
        try:
            proposition = creer_proposition_correction_syntaxe(
                str(fichier_path), erreur, solution=None
            )
            sauvegarder_proposition(proposition)
            propositions.append(proposition.get("id", proposition))
        except Exception as exc:
            log_event("testeur", f"Échec création proposition {fichier_path}: {exc}")

    return {
        "ok": False,
        "message": (
            f"{len(erreurs)} erreur(s) de syntaxe détectée(s). "
            f"{len(propositions)} proposition(s) créée(s). "
            "Aucune modification de production effectuée."
        ),
        "erreurs_initiales": erreurs,
        "propositions": propositions,
        "erreurs_restantes": erreurs,
        "modification_appliquee": False,
        "duree": round(time.perf_counter() - t0, 3)
    }

def tester_fichier_avec_correction(fichier: str) -> dict:
    """
    Teste un fichier et génère des propositions de correction de syntaxe
    si nécessaire. Ne modifie jamais le fichier de production.
    """
    t0 = time.perf_counter()

    # 1. Détection + propositions de correction de syntaxe
    correction_result = tester_et_corriger_syntaxe(fichier)

    # 2. Tests normaux
    test_result = tester_fichier(fichier)

    # 3. Génération de propositions supplémentaires si nécessaire
    propositions = list(correction_result.get("propositions", []))
    if not test_result["ok"] and not propositions:
        propositions = generer_propositions_correction(fichier)

    return {
        "ok": test_result["ok"] and correction_result["ok"],
        "valide": test_result["ok"] and correction_result["ok"],
        "fichier": fichier,
        "correction_syntaxe": correction_result,
        "tests": test_result,
        "propositions": propositions,
        "modification_appliquee": False,
        "duree": round(time.perf_counter() - t0, 3)
    }

def generer_propositions_correction(fichier: str) -> list:
    """
    Génère des propositions de correction pour les erreurs de syntaxe.
    Ne modifie jamais le fichier de production.
    """
    fichier_path = Path(fichier)
    erreurs = detecter_erreurs_syntaxe(fichier_path)

    propositions = []
    for erreur in erreurs:
        try:
            proposition = creer_proposition_correction_syntaxe(
                str(fichier_path), erreur, solution=None
            )
            sauvegarder_proposition(proposition)
            propositions.append(proposition.get("id", proposition))
        except Exception as exc:
            log_event("testeur", f"Échec création proposition {fichier_path}: {exc}")

    return propositions

def workflow_test_complet(fichier: str) -> dict:
    """
    Workflow complet de test avec propositions de correction de syntaxe.
    Ne modifie jamais le fichier de production.
    """
    t0 = time.perf_counter()

    # 1. Détection + propositions de correction de syntaxe
    correction_result = tester_et_corriger_syntaxe(fichier)

    # 2. Tests de sécurité et syntaxe
    test_result = tester_fichier(fichier)

    # 3. Génération de propositions supplémentaires si nécessaire
    propositions = list(correction_result.get("propositions", []))
    if not test_result["ok"] and not propositions:
        propositions = generer_propositions_correction(fichier)

    return {
        "ok": test_result["ok"] and correction_result["ok"],
        "valide": test_result["ok"] and correction_result["ok"],
        "fichier": fichier,
        "correction_syntaxe": correction_result,
        "tests": test_result,
        "propositions": propositions,
        "modification_appliquee": False,
        "duree": round(time.perf_counter() - t0, 3)
    }

def formater_rapport(rapport):
    statut = "✅ PASSÉ" if rapport["ok"] else "❌ ÉCHOUÉ"
    lignes = [
        f"🧪 Rapport de test : {statut}",
        f"   Fichier : {rapport.get('fichier', '?')}",
        f"   Durée : {rapport.get('duree', 0)}s",
        "",
    ]

    # Correction syntaxe
    if "correction_syntaxe" in rapport:
        correction = rapport["correction_syntaxe"]
        lignes.append(f"   Correction syntaxe : {'✅' if correction['ok'] else '⚠️'} {correction['message']}")
        if correction.get("erreurs_restantes"):
            lignes.append("     Erreurs restantes :")
            for erreur in correction["erreurs_restantes"][:3]:
                lignes.append(f"       • Ligne {erreur['line']}: {erreur['message']}")
        if correction.get("propositions"):
            lignes.append(f"     Propositions créées : {len(correction['propositions'])}")

    # Tests principaux
    lignes.append(f"   Syntaxe : {'✅' if rapport['tests']['syntaxe']['ok'] else '❌'} {rapport['tests']['syntaxe']['message']}")
    lignes.append(f"   Sécurité : {'✅' if rapport['tests']['securite']['ok'] else '⚠️'} {rapport['tests']['securite']['message']}")

    if rapport["tests"]["securite"].get("alertes"):
        for alerte in rapport["tests"]["securite"]["alertes"][:3]:
            lignes.append(f"     ⚠️  Ligne {alerte['ligne']} : {alerte['risque']}")

    if rapport["tests"]["imports"].get("ok"):
        lignes.append(f"   Imports : {rapport['tests']['imports']['nombre']} trouvé(s)")

    # Propositions
    if rapport.get("propositions"):
        lignes.append(f"\n   Propositions générées : {len(rapport['propositions'])}")
        for prop_id in rapport["propositions"][:3]:
            lignes.append(f"     • {prop_id}")

    lignes.append("")
    lignes.append("   🔒 Production modifiée : NON")

    return "\n".join(lignes)

def executer_tests_pytest(dossier, timeout=120):
    dossier = Path(dossier).resolve()
    if not dossier.exists():
        return {"ok": False, "message": "Dossier de test introuvable."}
    try:
        resultat = subprocess.run([sys.executable, "-m", "pytest", str(dossier), "-q", "--tb=short"], cwd=str(dossier), capture_output=True, text=True, timeout=timeout)
        return {"ok": resultat.returncode == 0, "code": resultat.returncode, "stdout": resultat.stdout[-5000:], "stderr": resultat.stderr[-5000:], "message": "Tests réussis." if resultat.returncode == 0 else "Des tests ont échoué."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"Timeout après {timeout} secondes."}
    except FileNotFoundError:
        return {"ok": False, "message": "pytest n'est pas installé. pip install pytest"}
    except Exception as erreur:
        return {"ok": False, "message": str(erreur)}

__all__ = [
    "tester_syntaxe", "tester_securite", "tester_imports", "tester_fichier",
    "formater_rapport", "executer_tests_pytest",
    "tester_et_corriger_syntaxe", "tester_fichier_avec_correction",
    "generer_propositions_correction", "workflow_test_complet"
]