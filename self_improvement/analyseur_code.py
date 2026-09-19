# -*- coding: utf-8 -*-
"""
JIBI - Analyseur de code
========================

Analyse structurellement un projet Python.

Responsabilités :
    - analyser un fichier Python ;
    - analyser récursivement un répertoire ;
    - analyser un projet complet ;
    - construire une cartographie des modules et dépendances ;
    - produire des rapports structurés.

Sécurité :
    - aucune modification de fichier ;
    - aucune exécution de code analysé ;
    - répertoires techniques ignorés ;
    - liens symboliques ignorés.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------

@dataclass
class FonctionInfo:
    nom: str
    ligne: int
    ligne_fin: Optional[int]
    async_: bool
    arguments: list[str]
    decorators: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClasseInfo:
    nom: str
    ligne: int
    ligne_fin: Optional[int]
    bases: list[str]
    methodes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalyseCode:
    fichier: str
    existe: bool
    syntaxe_valide: bool
    hash_sha256: Optional[str]
    lignes: int
    fonctions: list[FonctionInfo] = field(
        default_factory=list
    )
    classes: list[ClasseInfo] = field(
        default_factory=list
    )
    imports: list[str] = field(
        default_factory=list
    )
    erreurs: list[str] = field(
        default_factory=list
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fichier": self.fichier,
            "existe": self.existe,
            "syntaxe_valide": self.syntaxe_valide,
            "hash_sha256": self.hash_sha256,
            "lignes": self.lignes,
            "fonctions": [
                fonction.to_dict()
                for fonction in self.fonctions
            ],
            "classes": [
                classe.to_dict()
                for classe in self.classes
            ],
            "imports": self.imports,
            "erreurs": self.erreurs,
        }


@dataclass
class AnalyseProjet:
    """
    Vue globale d'un projet Python.

    Cette structure ne modifie jamais le projet.
    """

    repertoire: str
    existe: bool
    fichiers_python: list[str] = field(
        default_factory=list
    )
    analyses: list[AnalyseCode] = field(
        default_factory=list
    )
    modules: list[str] = field(
        default_factory=list
    )
    dependances_internes: dict[str, list[str]] = field(
        default_factory=dict
    )
    imports_externes: dict[str, list[str]] = field(
        default_factory=dict
    )
    erreurs: list[str] = field(
        default_factory=list
    )

    @property
    def nombre_fichiers(self) -> int:
        return len(self.fichiers_python)

    @property
    def nombre_modules(self) -> int:
        return len(self.modules)

    @property
    def nombre_fonctions(self) -> int:
        return sum(
            len(analyse.fonctions)
            for analyse in self.analyses
        )

    @property
    def nombre_classes(self) -> int:
        return sum(
            len(analyse.classes)
            for analyse in self.analyses
        )

    @property
    def nombre_imports(self) -> int:
        return sum(
            len(analyse.imports)
            for analyse in self.analyses
        )

    @property
    def nombre_erreurs(self) -> int:
        return sum(
            len(analyse.erreurs)
            for analyse in self.analyses
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repertoire": self.repertoire,
            "existe": self.existe,
            "fichiers_python": list(
                self.fichiers_python
            ),
            "analyses": [
                analyse.to_dict()
                for analyse in self.analyses
            ],
            "modules": list(self.modules),
            "dependances_internes": {
                module: list(dependances)
                for module, dependances
                in self.dependances_internes.items()
            },
            "imports_externes": {
                module: list(imports)
                for module, imports
                in self.imports_externes.items()
            },
            "erreurs": list(self.erreurs),
            "statistiques": {
                "fichiers": self.nombre_fichiers,
                "modules": self.nombre_modules,
                "fonctions": self.nombre_fonctions,
                "classes": self.nombre_classes,
                "imports": self.nombre_imports,
                "erreurs": self.nombre_erreurs,
            },
        }


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

REPERTOIRES_IGNORES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "workspace",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash(contenu: str) -> str:
    """Calcule le SHA-256 du contenu analysé."""

    return hashlib.sha256(
        contenu.encode("utf-8")
    ).hexdigest()


def _nom_expr(node: ast.AST) -> str:
    """Convertit une expression AST en texte."""

    try:
        return ast.unparse(node)

    except Exception:
        return "<expression>"


def _chemin_ignore(path: Path) -> bool:
    """Indique si un chemin appartient à un répertoire ignoré."""

    return any(
        partie in REPERTOIRES_IGNORES
        for partie in path.parts
    )


def _normaliser_path(path: Path) -> str:
    """Normalise un chemin pour les rapports."""

    return str(path).replace("\\", "/")


def _nom_module(
    fichier: Path,
    racine: Path,
) -> str:
    """
    Transforme :

        core/agent_core.py

    en :

        core.agent_core

    Et :

        core/__init__.py

    en :

        core
    """

    try:
        relatif = fichier.resolve().relative_to(
            racine.resolve()
        )
    except ValueError:
        return fichier.stem

    morceaux = list(
        relatif.with_suffix("").parts
    )

    if not morceaux:
        return ""

    if morceaux[-1] == "__init__":
        morceaux.pop()

    if not morceaux:
        return ""

    return ".".join(morceaux)


def _racine_import(import_name: str) -> str:
    """Retourne la racine d'un import."""

    return import_name.split(".", 1)[0].strip()


def _est_module_interne(
    import_name: str,
    modules: set[str],
) -> Optional[str]:
    """
    Vérifie si un import correspond à un module
    présent dans le projet.

    Accepte par exemple :

        core
        core.router
        core.agent_core
    """

    if not import_name:
        return None

    candidats = [
        import_name,
    ]

    morceaux = import_name.split(".")

    for index in range(
        len(morceaux) - 1,
        0,
        -1,
    ):
        candidats.append(
            ".".join(morceaux[:index])
        )

    for candidat in candidats:
        if candidat in modules:
            return candidat

    racine = morceaux[0]

    for module in modules:
        if (
            module == racine
            or module.startswith(
                racine + "."
            )
        ):
            return module

    return None


# ---------------------------------------------------------------------------
# Analyse d'un fichier
# ---------------------------------------------------------------------------

def analyser_fichier(
    fichier: str | Path,
) -> AnalyseCode:
    """
    Analyse un fichier Python.

    Ne modifie jamais le fichier et n'exécute jamais son contenu.
    """

    path = Path(fichier)

    if not path.exists():
        return AnalyseCode(
            fichier=str(path),
            existe=False,
            syntaxe_valide=False,
            hash_sha256=None,
            lignes=0,
            erreurs=[
                "Fichier inexistant."
            ],
        )

    if not path.is_file():
        return AnalyseCode(
            fichier=str(path),
            existe=False,
            syntaxe_valide=False,
            hash_sha256=None,
            lignes=0,
            erreurs=[
                "Le chemin n'est pas un fichier."
            ],
        )

    try:
        contenu = path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        lignes = len(
            contenu.splitlines()
        )

        digest = _hash(contenu)

    except Exception as exc:
        return AnalyseCode(
            fichier=str(path),
            existe=True,
            syntaxe_valide=False,
            hash_sha256=None,
            lignes=0,
            erreurs=[
                f"Lecture impossible : {exc}"
            ],
        )

    try:
        arbre = ast.parse(
            contenu,
            filename=str(path),
        )

    except SyntaxError as exc:
        ligne = exc.lineno or "?"

        return AnalyseCode(
            fichier=str(path),
            existe=True,
            syntaxe_valide=False,
            hash_sha256=digest,
            lignes=lignes,
            erreurs=[
                (
                    f"SyntaxError ligne "
                    f"{ligne}: {exc.msg}"
                )
            ],
        )

    fonctions: list[FonctionInfo] = []
    classes: list[ClasseInfo] = []
    imports: list[str] = []

    for node in ast.walk(arbre):

        # ---------------------------------------------------------------
        # Fonctions
        # ---------------------------------------------------------------

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            arguments = [
                argument.arg
                for argument in node.args.args
            ]

            arguments.extend(
                argument.arg
                for argument
                in node.args.posonlyargs
            )

            arguments.extend(
                argument.arg
                for argument
                in node.args.kwonlyargs
            )

            if node.args.vararg:
                arguments.append(
                    f"*{node.args.vararg.arg}"
                )

            if node.args.kwarg:
                arguments.append(
                    f"**{node.args.kwarg.arg}"
                )

            decorators = [
                _nom_expr(decorateur)
                for decorateur in node.decorator_list
            ]

            fonctions.append(
                FonctionInfo(
                    nom=node.name,
                    ligne=node.lineno,
                    ligne_fin=getattr(
                        node,
                        "end_lineno",
                        None,
                    ),
                    async_=isinstance(
                        node,
                        ast.AsyncFunctionDef,
                    ),
                    arguments=arguments,
                    decorators=decorators,
                )
            )

        # ---------------------------------------------------------------
        # Classes
        # ---------------------------------------------------------------

        elif isinstance(
            node,
            ast.ClassDef,
        ):
            methodes = [
                enfant.name
                for enfant in node.body
                if isinstance(
                    enfant,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                )
            ]

            classes.append(
                ClasseInfo(
                    nom=node.name,
                    ligne=node.lineno,
                    ligne_fin=getattr(
                        node,
                        "end_lineno",
                        None,
                    ),
                    bases=[
                        _nom_expr(base)
                        for base in node.bases
                    ],
                    methodes=methodes,
                )
            )

        # ---------------------------------------------------------------
        # Imports
        # ---------------------------------------------------------------

        elif isinstance(
            node,
            ast.Import,
        ):
            for alias in node.names:
                imports.append(
                    alias.name
                )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            module = node.module or ""

            if node.level:
                prefix = "." * node.level
                module = (
                    prefix + module
                    if module
                    else prefix
                )

            for alias in node.names:

                if alias.name == "*":
                    imports.append(
                        f"from {module} import *"
                    )
                else:
                    imports.append(
                        f"from {module} import {alias.name}"
                    )

    return AnalyseCode(
        fichier=str(path),
        existe=True,
        syntaxe_valide=True,
        hash_sha256=digest,
        lignes=lignes,
        fonctions=sorted(
            fonctions,
            key=lambda fonction: (
                fonction.ligne,
                fonction.nom,
            ),
        ),
        classes=sorted(
            classes,
            key=lambda classe: (
                classe.ligne,
                classe.nom,
            ),
        ),
        imports=sorted(
            set(imports)
        ),
    )


# ---------------------------------------------------------------------------
# Analyse d'un répertoire
# ---------------------------------------------------------------------------

def analyser_repertoire(
    repertoire: str | Path,
) -> list[AnalyseCode]:
    """
    Analyse récursivement les fichiers Python d'un répertoire.

    Les environnements, caches et dépôts Git sont ignorés.
    """

    root = Path(repertoire)

    if not root.exists():
        return []

    if not root.is_dir():
        return []

    resultats: list[AnalyseCode] = []

    try:
        chemins = root.rglob("*.py")
    except Exception:
        return []

    for path in chemins:

        if path.is_symlink():
            continue

        if _chemin_ignore(path):
            continue

        try:
            resultat = analyser_fichier(path)
            resultats.append(resultat)

        except Exception as exc:
            resultats.append(
                AnalyseCode(
                    fichier=str(path),
                    existe=True,
                    syntaxe_valide=False,
                    hash_sha256=None,
                    lignes=0,
                    erreurs=[
                        f"Analyse impossible : {exc}"
                    ],
                )
            )

    return sorted(
        resultats,
        key=lambda analyse: analyse.fichier.lower(),
    )


# ---------------------------------------------------------------------------
# Cartographie des dépendances
# ---------------------------------------------------------------------------

def cartographier_dependances(
    repertoire: str | Path,
    analyses: Optional[list[AnalyseCode]] = None,
) -> tuple[
    list[str],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    """
    Construit la cartographie des modules.

    Retourne :

        modules
        dependances_internes
        imports_externes
    """

    root = Path(repertoire).resolve()

    if analyses is None:
        analyses = analyser_repertoire(root)

    modules: set[str] = set()

    for analyse in analyses:
        path = Path(analyse.fichier)

        if path.suffix.lower() != ".py":
            continue

        module = _nom_module(
            path,
            root,
        )

        if module:
            modules.add(module)

    dependances_internes: dict[
        str,
        list[str],
    ] = {}

    imports_externes: dict[
        str,
        list[str],
    ] = {}

    for analyse in analyses:

        path = Path(analyse.fichier)

        module_source = _nom_module(
            path,
            root,
        )

        if not module_source:
            continue

        internes: set[str] = set()
        externes: set[str] = set()

        for import_text in analyse.imports:

            if import_text.startswith("from "):
                contenu = import_text[5:]

                if " import " in contenu:
                    contenu = contenu.split(
                        " import ",
                        1,
                    )[0]

                import_name = contenu.strip()

            else:
                import_name = import_text.strip()

            # Imports relatifs :
            # on les conserve dans les imports externes
            # tant qu'on ne peut pas les résoudre sans
            # ambiguïté par AST complet.
            if import_name.startswith("."):
                externes.add(
                    import_name
                )
                continue

            interne = _est_module_interne(
                import_name,
                modules,
            )

            if interne is not None:
                if interne != module_source:
                    internes.add(interne)
            else:
                externe = _racine_import(
                    import_name
                )

                if externe:
                    externes.add(externe)

        dependances_internes[
            module_source
        ] = sorted(
            internes
        )

        imports_externes[
            module_source
        ] = sorted(
            externes
        )

    return (
        sorted(modules),
        dependances_internes,
        imports_externes,
    )


# ---------------------------------------------------------------------------
# Analyse complète du projet
# ---------------------------------------------------------------------------

def analyser_projet(
    repertoire: str | Path,
) -> AnalyseProjet:
    """
    Analyse complète d'un projet Python.

    Effectue uniquement de la lecture :

        - scan récursif ;
        - AST ;
        - fonctions ;
        - classes ;
        - imports ;
        - modules ;
        - dépendances internes ;
        - imports externes.

    Aucun fichier n'est modifié.
    """

    root = Path(repertoire).resolve()

    if not root.exists():
        return AnalyseProjet(
            repertoire=str(root),
            existe=False,
            erreurs=[
                f"Répertoire inexistant : {root}"
            ],
        )

    if not root.is_dir():
        return AnalyseProjet(
            repertoire=str(root),
            existe=False,
            erreurs=[
                f"Le chemin n'est pas un répertoire : {root}"
            ],
        )

    analyses = analyser_repertoire(root)

    fichiers_python = sorted(
        {
            _normaliser_path(
                Path(analyse.fichier)
            )
            for analyse in analyses
            if analyse.fichier
        },
        key=str.lower,
    )

    (
        modules,
        dependances_internes,
        imports_externes,
    ) = cartographier_dependances(
        root,
        analyses,
    )

    erreurs: list[str] = []

    for analyse in analyses:
        erreurs.extend(
            f"{analyse.fichier}: {erreur}"
            for erreur in analyse.erreurs
        )

    return AnalyseProjet(
        repertoire=str(root),
        existe=True,
        fichiers_python=fichiers_python,
        analyses=analyses,
        modules=modules,
        dependances_internes=dependances_internes,
        imports_externes=imports_externes,
        erreurs=erreurs,
    )


# ---------------------------------------------------------------------------
# Recherche de fonction
# ---------------------------------------------------------------------------

def trouver_fonction(
    fichier: str | Path,
    nom: str,
) -> Optional[FonctionInfo]:
    """Recherche une fonction par son nom."""

    analyse = analyser_fichier(fichier)

    for fonction in analyse.fonctions:
        if fonction.nom == nom:
            return fonction

    return None


# ---------------------------------------------------------------------------
# Résumé d'un fichier
# ---------------------------------------------------------------------------

def resume_analyse(
    analyse: AnalyseCode,
) -> str:
    """Produit un résumé humain de l'analyse."""

    return "\n".join(
        [
            "=== ANALYSE CODE ===",
            f"Fichier : {analyse.fichier}",
            f"Existe : {analyse.existe}",
            (
                "Syntaxe : "
                + (
                    "OK"
                    if analyse.syntaxe_valide
                    else "ERREUR"
                )
            ),
            f"Lignes : {analyse.lignes}",
            (
                "SHA256 : "
                f"{analyse.hash_sha256 or 'inconnu'}"
            ),
            f"Fonctions : {len(analyse.fonctions)}",
            f"Classes : {len(analyse.classes)}",
            f"Imports : {len(analyse.imports)}",
            f"Erreurs : {len(analyse.erreurs)}",
        ]
    )


# ---------------------------------------------------------------------------
# Résumé du projet
# ---------------------------------------------------------------------------

def resume_projet(
    analyse: AnalyseProjet,
) -> str:
    """Produit un résumé humain du projet."""

    lignes = [
        "=== ANALYSE PROJET JIBI ===",
        f"Répertoire : {analyse.repertoire}",
        f"Existe : {analyse.existe}",
        "",
        f"Fichiers Python : {analyse.nombre_fichiers}",
        f"Modules : {analyse.nombre_modules}",
        f"Fonctions : {analyse.nombre_fonctions}",
        f"Classes : {analyse.nombre_classes}",
        f"Imports : {analyse.nombre_imports}",
        f"Erreurs d'analyse : {analyse.nombre_erreurs}",
    ]

    if analyse.modules:
        lignes.extend(
            [
                "",
                "=== MODULES ===",
            ]
        )

        lignes.extend(
            f"• {module}"
            for module in analyse.modules
        )

    if analyse.dependances_internes:
        lignes.extend(
            [
                "",
                "=== DÉPENDANCES INTERNES ===",
            ]
        )

        for module in sorted(
            analyse.dependances_internes
        ):
            dependances = (
                analyse.dependances_internes[
                    module
                ]
            )

            if dependances:
                lignes.append(
                    f"• {module} → "
                    f"{', '.join(dependances)}"
                )
            else:
                lignes.append(
                    f"• {module} → aucune"
                )

    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "FonctionInfo",
    "ClasseInfo",
    "AnalyseCode",
    "AnalyseProjet",
    "REPERTOIRES_IGNORES",
    "analyser_fichier",
    "analyser_repertoire",
    "cartographier_dependances",
    "analyser_projet",
    "trouver_fonction",
    "resume_analyse",
    "resume_projet",
]