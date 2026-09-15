"""
Générateur — PATCHÉ v2
- Filtre sécurité eval/exec/os.system + fix ast.walk top-level + timings
"""
import ast
import re
import time
from pathlib import Path
from datetime import datetime
import difflib

try:
    from logging_jibi import log_event, log_warning, log_error
except Exception:
    def log_event(*a, **kw): pass
    def log_warning(*a, **kw): pass
    def log_error(*a, **kw): pass

INTERDITS = ("eval(", "exec(", "os.system", "subprocess", "shell=True", "__import__", "rm -rf", "DROP TABLE")

def analyser_fichier_python(fichier):
    fichier = Path(fichier)
    if not fichier.exists():
        return {"ok": False, "message": f"Fichier introuvable : {fichier}"}
    try:
        contenu = fichier.read_text(encoding="utf-8", errors="replace")
        lignes = contenu.splitlines()
        arbre = ast.parse(contenu)
        fonctions, classes, imports, variables_globales = [], [], [], []
        # Top-level only pour fonctions/classes pour éviter imbriquées
        for noeud in arbre.body:
            if isinstance(noeud, ast.FunctionDef):
                fonctions.append({"nom": noeud.name, "ligne_debut": noeud.lineno, "ligne_fin": noeud.end_lineno or noeud.lineno, "args": [arg.arg for arg in noeud.args.args], "decorateurs": [d.id if isinstance(d, ast.Name) else str(d) for d in noeud.decorator_list], "docstring": ast.get_docstring(noeud)})
            elif isinstance(noeud, ast.ClassDef):
                classes.append({"nom": noeud.name, "ligne_debut": noeud.lineno, "ligne_fin": noeud.end_lineno or noeud.lineno, "bases": [b.id if isinstance(b, ast.Name) else str(b) for b in noeud.bases], "docstring": ast.get_docstring(noeud)})
            elif isinstance(noeud, ast.Import):
                for alias in noeud.names:
                    imports.append({"type": "import", "module": alias.name, "alias": alias.asname, "ligne": noeud.lineno})
            elif isinstance(noeud, ast.ImportFrom):
                module = noeud.module or ""
                for alias in noeud.names:
                    imports.append({"type": "from_import", "module": module, "nom": alias.name, "alias": alias.asname, "ligne": noeud.lineno})
            elif isinstance(noeud, ast.Assign):
                for target in noeud.targets:
                    if isinstance(target, ast.Name):
                        variables_globales.append({"nom": target.id, "ligne": noeud.lineno})
            elif isinstance(noeud, ast.AnnAssign) and isinstance(noeud.target, ast.Name):
                variables_globales.append({"nom": noeud.target.id, "ligne": noeud.lineno})
        # Imports aussi via walk pour ceux dans try/except
        for noeud in ast.walk(arbre):
            if isinstance(noeud, (ast.Import, ast.ImportFrom)) and all(imp["ligne"] != noeud.lineno for imp in imports):
                if isinstance(noeud, ast.Import):
                    for alias in noeud.names:
                        imports.append({"type": "import", "module": alias.name, "alias": alias.asname, "ligne": noeud.lineno})
        return {"ok": True, "fichier": str(fichier), "lignes": lignes, "nombre_lignes": len(lignes), "fonctions": fonctions, "classes": classes, "imports": imports, "variables_globales": variables_globales, "arbre_ast": arbre}
    except SyntaxError as e:
        return {"ok": False, "message": f"Erreur de syntaxe ligne {e.lineno} : {e.msg}"}
    except Exception as e:
        log_error("code_generator", f"Erreur analyse fichier {fichier} : {e}", exc_info=True)
        return {"ok": False, "message": str(e)}

def generer_patch(fichier_original, proposition):
    t0 = time.perf_counter()
    analyse = analyser_fichier_python(fichier_original)
    if not analyse["ok"]:
        return {"ok": False, "message": f"Impossible d'analyser : {analyse.get('message')}"}
    solution = proposition.get("solution", "")
    # Filtre sécurité avant toute génération
    for interdit in INTERDITS:
        if interdit.lower() in solution.lower():
            return {"ok": False, "message": f"Patch bloqué : motif interdit '{interdit}' dans la solution"}
    patch = _detecter_strategie_patch(solution, analyse)
    if patch.get("code_nouveau"):
        for interdit in INTERDITS:
            if interdit in patch["code_nouveau"]:
                return {"ok": False, "message": f"Patch bloqué : motif interdit '{interdit}' dans le code généré"}
    log_event("code_generator", f"Patch généré : {patch.get('type')} pour {patch.get('cible','?')} en {time.perf_counter()-t0:.3f}s")
    return patch

def _detecter_strategie_patch(solution, analyse):
    solution_lower = solution.lower()
    # 1. Chercher fonction cible par nom direct dans solution
    for fonction in analyse["fonctions"]:
        if fonction["nom"].lower() in solution_lower:
            if any(k in solution_lower for k in ("modifier", "améliorer", "optimise", "corrige", "bug")):
                return {"ok": True, "type": "fonction_modifiee", "strategie": "modification", "cible": fonction["nom"], "fonction_existante": fonction, "code_nouveau": _generer_fonction_amelioree(fonction, solution, analyse), "ligne_insertion": fonction["ligne_debut"]}
    if any(k in solution_lower for k in ("ajouter", "créer", "nouvelle fonction")):
        m = re.search(r"fonction\s+([a-z_][a-z0-9_]*)", solution_lower)
        if m:
            nom = m.group(1)
            return {"ok": True, "type": "fonction_ajoutee", "strategie": "ajout", "cible": nom, "code_nouveau": _generer_nouvelle_fonction(nom, solution), "ligne_insertion": _trouver_ligne_insertion(analyse)}
        # fallback : nom générique
        if "outil" in solution_lower:
            m2 = re.search(r"outil\s+([a-z_][a-z0-9_]*)", solution_lower)
            if m2:
                nom = m2.group(1)
                return {"ok": True, "type": "fonction_ajoutee", "strategie": "ajout", "cible": nom, "code_nouveau": _generer_nouvelle_fonction(nom, solution), "ligne_insertion": _trouver_ligne_insertion(analyse)}
    if "import" in solution_lower:
        m = re.search(r"import\s+([a-z_][a-z0-9_.]*)", solution_lower)
        if m:
            mod = m.group(1)
            return {"ok": True, "type": "import_ajoute", "strategie": "import", "cible": mod, "code_nouveau": f"import {mod}\n", "ligne_insertion": _trouver_ligne_insertion_import(analyse)}
    return {"ok": True, "type": "modification_generique", "strategie": "generique", "cible": "fichier_complet", "code_nouveau": _generer_modification_generique(solution, analyse), "ligne_insertion": None, "message": "Stratégie générique : modification manuelle recommandée."}

def _generer_fonction_amelioree(fonction, solution, analyse):
    lignes = analyse["lignes"]
    ld, lf = fonction["ligne_debut"] - 1, fonction["ligne_fin"]
    code_actuel = "\n".join(lignes[ld:lf])
    solution_lower = solution.lower()
    code = code_actuel
    # Exemple générique : ajouter log si demandé, sinon retourner tel quel avec commentaire
    if "log" in solution_lower and "log_event" not in code_actuel:
        ls = code.split("\n")
        for i, ligne in enumerate(ls):
            if ligne.strip() and not ligne.strip().startswith("def ") and not ligne.strip().startswith('"""'):
                ls.insert(i, '    log_event("auto", f"Appel {fonction["nom"]}")')
                break
        code = "\n".join(ls)
    if code == code_actuel:
        code = code_actuel + f"\n    # TODO auto: {solution[:120]}"
    return code

def _generer_nouvelle_fonction(nom_fonction, solution):
    return f'''def {nom_fonction}():
    """Nouvelle fonction générée automatiquement."""
    # Basé sur : {solution[:100]}
    try:
        from logging_jibi import log_event
        log_event("self_improvement", "Nouvelle fonction {nom_fonction} appelée")
    except Exception:
        pass
    return True
'''.strip()

def _generer_correction_bug(fonction, solution, analyse):
    lignes = analyse["lignes"]
    code = "\n".join(lignes[fonction["ligne_debut"]-1:fonction["ligne_fin"]])
    if "none" in solution.lower():
        code += "\n    # patch: vérification None ajoutée"
    return code

def _generer_modification_generique(solution, analyse):
    return f"""# AUTO-AMÉLIORATION SUGGÉRÉE
# Problème : {solution[:200]}
# Action : révision manuelle recommandée.
"""

def _trouver_ligne_insertion(analyse):
    imports = analyse.get("imports", [])
    fonctions = analyse.get("fonctions", [])
    if imports:
        return max(imp["ligne"] for imp in imports) + 2
    if fonctions:
        return fonctions[0]["ligne_debut"] - 2
    return 10

def _trouver_ligne_insertion_import(analyse):
    imports = analyse.get("imports", [])
    if imports:
        return max(imp["ligne"] for imp in imports) + 1
    for i, ligne in enumerate(analyse.get("lignes", [])):
        s = ligne.strip()
        if s and not s.startswith('"""') and not s.startswith("'''") and not s.startswith("#"):
            return i
    return 1

def appliquer_patch(fichier, patch):
    fichier = Path(fichier)
    if not fichier.exists():
        raise FileNotFoundError(f"Fichier introuvable : {fichier}")
    if not patch.get("ok"):
        raise ValueError(f"Patch invalide : {patch.get('message')}")
    for interdit in INTERDITS:
        if interdit in patch.get("code_nouveau", ""):
            raise ValueError(f"Patch bloqué : motif interdit '{interdit}'")
    lignes = fichier.read_text(encoding="utf-8").splitlines()
    t, code, li = patch["type"], patch["code_nouveau"], patch.get("ligne_insertion")
    if t == "fonction_modifiee" or t == "bug_fix":
        f = patch["fonction_existante"]
        lignes = lignes[:f["ligne_debut"]-1] + code.splitlines() + lignes[f["ligne_fin"]:]
    elif t == "fonction_ajoutee":
        lignes = lignes[:li] + [""] + code.splitlines() + [""] + lignes[li:]
    elif t == "import_ajoute":
        lignes = lignes[:li] + [code.strip()] + lignes[li:]
    else:
        lignes = code.splitlines() + lignes
    fichier.write_text("\n".join(lignes), encoding="utf-8")
    log_event("code_generator", f"Patch appliqué : {t} dans {fichier.name}")
    return fichier

def verifier_coherence(fichier_original, fichier_modifie):
    orig = analyser_fichier_python(fichier_original)
    mod = analyser_fichier_python(fichier_modifie)
    if not mod["ok"]:
        return {"ok": False, "message": f"Fichier modifié invalide : {mod.get('message')}"}
    tests = {}
    tests["syntaxe"] = {"ok": mod["ok"], "message": "Syntaxe Python valide." if mod["ok"] else mod["message"]}
    tests["nombre_fonctions"] = {"ok": len(mod["fonctions"]) >= len(orig["fonctions"]), "avant": len(orig["fonctions"]), "apres": len(mod["fonctions"]), "message": f"{len(mod['fonctions'])} fonctions (avant: {len(orig['fonctions'])})"}
    imports_avant = set(imp["module"] for imp in orig["imports"])
    imports_apres = set(imp["module"] for imp in mod["imports"])
    manq = imports_avant - imports_apres
    tests["imports"] = {"ok": len(manq)==0, "manquants": list(manq), "message": "Tous les imports préservés." if not manq else f"Imports manquants : {', '.join(manq)}"}
    fa, fp = {f["nom"] for f in orig["fonctions"]}, {f["nom"] for f in mod["fonctions"]}
    sup = fa - fp
    tests["fonctions_preservees"] = {"ok": len(sup)==0, "supprimees": list(sup), "message": "Toutes les fonctions préservées." if not sup else f"Fonctions supprimées : {', '.join(sup)}"}
    ratio = len(mod["lignes"])/max(len(orig["lignes"]),1)
    tests["taille"] = {"ok": 0.5 <= ratio <= 3.0, "avant": len(orig["lignes"]), "apres": len(mod["lignes"]), "ratio": round(ratio,2), "message": f"Taille acceptable ({len(mod['lignes'])} lignes, ratio: {ratio:.2f})" if 0.5<=ratio<=3.0 else f"⚠️ Taille anormale (ratio: {ratio:.2f})"}
    ok_global = all(t["ok"] for t in tests.values())
    return {"ok": ok_global, "tests": tests, "message": "Cohérence vérifiée avec succès." if ok_global else "Des problèmes de cohérence ont été détectés."}

def generer_diff_lisible(fichier_original, fichier_modifie):
    try:
        orig = Path(fichier_original).read_text(encoding="utf-8").splitlines()
        mod = Path(fichier_modifie).read_text(encoding="utf-8").splitlines()
        diff = difflib.unified_diff(orig, mod, fromfile=str(fichier_original), tofile=str(fichier_modifie), lineterm="")
        return "\n".join(diff)
    except Exception as e:
        return f"Impossible de générer le diff : {e}"
