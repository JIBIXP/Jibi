from __future__ import annotations

import ast
import py_compile
import tempfile
from pathlib import Path


# ============================================================================
# SYNTAXE
# ============================================================================

def valider_syntaxe(
    contenu: str,
    nom: str = "<string>",
) -> dict:
    """
    Vérifie uniquement la syntaxe Python.
    Aucun fichier source n'est modifié.
    """
    try:
        ast.parse(contenu, filename=nom)

        return {
            "ok": True,
            "message": "Syntaxe valide.",
        }

    except SyntaxError as exc:
        return {
            "ok": False,
            "message": str(exc),
            "ligne": exc.lineno,
            "colonne": exc.offset,
            "type": "SyntaxError",
        }


# ============================================================================
# AST
# ============================================================================

def valider_ast(
    contenu: str,
    nom: str = "<string>",
) -> dict:
    """
    Parse le code et vérifie que l'AST peut être construit.
    """
    try:
        arbre = ast.parse(contenu, filename=nom)

        return {
            "ok": True,
            "message": "AST valide.",
            "noeuds": sum(1 for _ in ast.walk(arbre)),
        }

    except SyntaxError as exc:
        return {
            "ok": False,
            "message": str(exc),
            "ligne": exc.lineno,
            "colonne": exc.offset,
            "type": "SyntaxError",
        }


# ============================================================================
# FICHIER
# ============================================================================

def valider_fichier_python(
    path: str | Path,
) -> dict:
    """
    Valide la syntaxe d'un fichier Python existant.
    """
    fichier = Path(path)

    if not fichier.exists():
        return {
            "ok": False,
            "message": "Fichier introuvable.",
        }

    if not fichier.is_file():
        return {
            "ok": False,
            "message": "Le chemin n'est pas un fichier.",
        }

    try:
        contenu = fichier.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

    except OSError as exc:
        return {
            "ok": False,
            "message": f"Lecture impossible : {exc}",
            "type": type(exc).__name__,
        }

    return valider_contenu_python(
        contenu,
        str(fichier),
    )


# ============================================================================
# REPERTOIRE
# ============================================================================

_PARTIES_IGNOREES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
}

_MAX_FICHIERS_REPERTOIRE = 5000


def trouver_fichiers_python(
    path: str | Path,
) -> list[Path]:
    """
    Retourne la liste des fichiers Python du répertoire.

    Les répertoires générés/inutiles sont ignorés.
    """
    dossier = Path(path)

    if not dossier.exists() or not dossier.is_dir():
        return []

    fichiers: list[Path] = []

    try:
        for fichier in dossier.rglob("*.py"):
            if any(
                partie in _PARTIES_IGNOREES
                for partie in fichier.parts
            ):
                continue

            try:
                if fichier.is_file():
                    fichiers.append(fichier)
            except OSError:
                continue

            if len(fichiers) >= _MAX_FICHIERS_REPERTOIRE:
                break

    except OSError:
        return []

    return sorted(fichiers)


def valider_repertoire_python(
    path: str | Path,
) -> dict:
    """
    Valide tous les fichiers Python d'un répertoire.
    """
    dossier = Path(path)

    if not dossier.exists():
        return {
            "ok": False,
            "message": "Dossier introuvable.",
            "fichiers_testes": 0,
            "erreurs": [],
        }

    if not dossier.is_dir():
        return {
            "ok": False,
            "message": "Le chemin n'est pas un dossier.",
            "fichiers_testes": 0,
            "erreurs": [],
        }

    fichiers = trouver_fichiers_python(dossier)
    erreurs: list[dict] = []

    for fichier in fichiers:
        resultat = valider_fichier_python(fichier)

        if not resultat.get("ok"):
            erreurs.append(
                {
                    "fichier": str(fichier),
                    "resultat": resultat,
                }
            )

    return {
        "ok": not erreurs,
        "fichiers_testes": len(fichiers),
        "erreurs": erreurs,
    }


# ============================================================================
# COMPILATION
# ============================================================================

def valider_compilation_repertoire(
    path: str | Path,
) -> bool:
    """
    Vérifie la compilation Python sans créer de __pycache__ dans le projet.

    Le bytecode temporaire est écrit dans un répertoire temporaire système,
    puis supprimé automatiquement.
    """
    dossier = Path(path)

    if not dossier.exists() or not dossier.is_dir():
        return False

    fichiers = trouver_fichiers_python(dossier)

    if not fichiers:
        return True

    with tempfile.TemporaryDirectory(prefix="jibi_validation_") as temp_dir:
        temp_root = Path(temp_dir)

        for index, fichier in enumerate(fichiers):
            try:
                contenu = fichier.read_text(
                    encoding="utf-8-sig",
                    errors="replace",
                )

                resultat = valider_contenu_python(
                    contenu,
                    str(fichier),
                )

                if not resultat.get("ok"):
                    return False

                cible = temp_root / f"{index}.py"
                cible.write_text(contenu, encoding="utf-8")

                pyc = temp_root / f"{index}.pyc"

                py_compile.compile(
                    str(cible),
                    cfile=str(pyc),
                    doraise=True,
                )

            except (OSError, py_compile.PyCompileError):
                return False

    return True


# ============================================================================
# VALIDATION COMPLETE
# ============================================================================

def valider_contenu_python(
    contenu: str,
    nom: str = "<string>",
) -> dict:
    """
    Validation complète d'un contenu Python en mémoire.

    Utile pour tester un patch AVANT toute écriture.
    """
    if not isinstance(contenu, str):
        return {
            "ok": False,
            "syntaxe": {
                "ok": False,
                "message": "Le contenu doit être une chaîne de caractères.",
                "type": "TypeError",
            },
            "ast": None,
        }

    syntaxe = valider_syntaxe(contenu, nom)

    if not syntaxe["ok"]:
        return {
            "ok": False,
            "syntaxe": syntaxe,
            "ast": None,
        }

    ast_resultat = valider_ast(contenu, nom)

    return {
        "ok": bool(ast_resultat["ok"]),
        "syntaxe": syntaxe,
        "ast": ast_resultat,
    }


__all__ = [
    "valider_syntaxe",
    "valider_ast",
    "valider_fichier_python",
    "trouver_fichiers_python",
    "valider_repertoire_python",
    "valider_compilation_repertoire",
    "valider_contenu_python",
]
