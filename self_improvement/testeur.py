"""
Tests automatiques — PATCHÉ v2
- Regex compilées + détection AST pour eval/exec + timings
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

def formater_rapport(rapport):
    statut = "✅ PASSÉ" if rapport["ok"] else "❌ ÉCHOUÉ"
    lignes = [
        f"🧪 Rapport de test : {statut}",
        f"   Fichier : {rapport.get('fichier', '?')}",
        "",
        f"   Syntaxe : {'✅' if rapport['syntaxe']['ok'] else '❌'} {rapport['syntaxe']['message']}",
        f"   Sécurité : {'✅' if rapport['securite']['ok'] else '⚠️'} {rapport['securite']['message']}",
    ]
    if rapport["securite"].get("alertes"):
        for alerte in rapport["securite"]["alertes"]:
            lignes.append(f"     ⚠️  Ligne {alerte['ligne']} : {alerte['risque']}")
    if rapport["imports"].get("ok"):
        lignes.append(f"   Imports : {rapport['imports']['nombre']} trouvé(s)")
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
