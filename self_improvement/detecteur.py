# -*- coding: utf-8 -*-
"""
JIBI - Détecteur de problèmes v3
================================

Transforme une AnalyseProjet en problèmes techniques exploitables.

Principes :
    - lecture uniquement ;
    - aucune exécution du code analysé ;
    - aucune modification du projet ;
    - distinction entre faits certains et heuristiques ;
    - réduction des faux positifs.

Niveaux de confiance :
    CERTAIN
        Fait directement identifiable par AST ou syntaxe.

    FORT
        Signal technique très fiable, mais nécessitant
        encore une vérification du contexte.

    HEURISTIQUE
        Signal utile pour le refactoring ou l'analyse,
        mais qui ne constitue pas automatiquement un bug.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from self_improvement.analyseur_code import (
    AnalyseCode,
    AnalyseProjet,
)


# ============================================================================
# MODÈLE
# ============================================================================

@dataclass
class Probleme:
    """Problème ou signal détecté."""

    id: str
    type: str
    gravite: str
    fichier: str
    ligne: Optional[int]
    message: str

    preuve: str = ""
    suggestion: str = ""

    confiance: float = 1.0
    niveau_confiance: str = "FORT"

    risque: str = "faible"
    auto_reparable: bool = False

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# CONFIGURATION
# ============================================================================

SEUIL_FONCTION_LIGNES = 80
SEUIL_CLASSE_LIGNES = 250
SEUIL_COMPLEXITE = 10
SEUIL_NIVEAU_IMBRICATION = 5

GRAVITES = {
    "critique",
    "important",
    "qualite",
    "refactoring",
}

RISQUES = {
    "faible",
    "moyen",
    "eleve",
    "critique",
}

NIVEAUX_CONFIANCE = {
    "CERTAIN",
    "FORT",
    "HEURISTIQUE",
}

# Répertoires techniques que l'analyse du projet
# ne doit pas considérer comme code métier.
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

# Les __init__.py peuvent volontairement réexporter
# des symboles et ne doivent donc pas produire
# automatiquement des imports inutilisés.
FICHIERS_REEXPORT_AUTORISES = {
    "__init__.py",
}


# ============================================================================
# NORMALISATION
# ============================================================================

def _clamp(
    valeur: float,
) -> float:
    try:
        return max(
            0.0,
            min(
                1.0,
                float(valeur),
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def _normaliser_gravite(
    valeur: str,
) -> str:
    valeur = str(
        valeur
    ).strip().lower()

    if valeur in GRAVITES:
        return valeur

    return "qualite"


def _normaliser_risque(
    valeur: str,
) -> str:
    valeur = str(
        valeur
    ).strip().lower()

    if valeur in RISQUES:
        return valeur

    return "faible"


def _normaliser_confiance(
    valeur: str,
) -> str:
    valeur = str(
        valeur
    ).strip().upper()

    if valeur in NIVEAUX_CONFIANCE:
        return valeur

    return "HEURISTIQUE"


def _normaliser_fichier(
    fichier: str | Path,
) -> str:
    return str(
        fichier
    ).replace(
        "\\",
        "/",
    )


def _est_ignore(
    fichier: str | Path,
) -> bool:
    path = Path(fichier)

    return any(
        partie in REPERTOIRES_IGNORES
        for partie in path.parts
    )


def _creer_probleme(
    *,
    compteur: int,
    type_: str,
    gravite: str,
    fichier: str,
    ligne: Optional[int],
    message: str,
    preuve: str = "",
    suggestion: str = "",
    confiance: float = 1.0,
    niveau_confiance: str = "FORT",
    risque: str = "faible",
    auto_reparable: bool = False,
    metadata: Optional[
        dict[str, Any]
    ] = None,
) -> Probleme:

    return Probleme(
        id=f"PB-{compteur:05d}",
        type=type_,
        gravite=_normaliser_gravite(
            gravite
        ),
        fichier=_normaliser_fichier(
            fichier
        ),
        ligne=ligne,
        message=message,
        preuve=preuve,
        suggestion=suggestion,
        confiance=_clamp(
            confiance
        ),
        niveau_confiance=_normaliser_confiance(
            niveau_confiance
        ),
        risque=_normaliser_risque(
            risque
        ),
        auto_reparable=bool(
            auto_reparable
        ),
        metadata=metadata or {},
    )


# ============================================================================
# SOURCES / AST
# ============================================================================

def _lire_source(
    fichier: str | Path,
) -> Optional[str]:

    path = Path(
        fichier
    )

    if _est_ignore(path):
        return None

    if not path.exists():
        return None

    if not path.is_file():
        return None

    try:
        return path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )
    except Exception:
        return None


def _parse_ast(
    fichier: str | Path,
) -> Optional[ast.AST]:

    contenu = _lire_source(
        fichier
    )

    if contenu is None:
        return None

    try:
        return ast.parse(
            contenu,
            filename=str(fichier),
        )
    except (
        SyntaxError,
        ValueError,
        TypeError,
    ):
        return None


def _iter_fichiers(
    analyse_projet: AnalyseProjet,
) -> Iterable[AnalyseCode]:

    for analyse in analyse_projet.analyses:

        if _est_ignore(
            analyse.fichier
        ):
            continue

        yield analyse


def _nom_cible(
    node: ast.AST,
) -> str:

    if isinstance(
        node,
        ast.Name,
    ):
        return node.id

    if isinstance(
        node,
        ast.Attribute,
    ):
        morceaux: list[str] = []

        courant: Optional[
            ast.AST
        ] = node

        while isinstance(
            courant,
            ast.Attribute,
        ):
            morceaux.append(
                courant.attr
            )
            courant = courant.value

        if isinstance(
            courant,
            ast.Name,
        ):
            morceaux.append(
                courant.id
            )

        return ".".join(
            reversed(morceaux)
        )

    return ""


def _nom_appel(node) -> str:
    """
    Reconstruit le nom complet d'un appel.
    
    Exemples :
        os.system      → "os.system"
        platform.system → "platform.system"
        system         → "system"
    """
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = _nom_appel(node.value)

        if parent:
            return f"{parent}.{node.attr}"

        return node.attr

    return ""


def _lignes_noeud(
    node: ast.AST,
) -> Optional[int]:
    debut = getattr(
        node,
        "lineno",
        None,
    )

    fin = getattr(
        node,
        "end_lineno",
        None,
    )

    if debut is None or fin is None:
        return None

    return max(
        0,
        fin - debut + 1,
    )


# ============================================================================
# COMPLEXITÉ
# ============================================================================

class _ComplexiteVisitor(
    ast.NodeVisitor
):
    """
    Calcule une complexité locale.

    IMPORTANT :
    les fonctions/classes imbriquées sont ignorées.
    Leur complexité ne pollue donc pas celle de la fonction parent.
    """

    def __init__(self) -> None:
        self.score = 1
        self.profondeur = 0
        self.maximum_profondeur = 0

    def _ouvrir_structure(
        self,
    ) -> None:
        self.profondeur += 1
        self.maximum_profondeur = max(
            self.maximum_profondeur,
            self.profondeur,
        )

    def _fermer_structure(
        self,
    ) -> None:
        self.profondeur = max(
            0,
            self.profondeur - 1,
        )

    def visit_If(
        self,
        node: ast.If,
    ) -> None:
        self.score += 1
        self._ouvrir_structure()

        for enfant in ast.iter_child_nodes(
            node
        ):
            self.visit(enfant)

        self._fermer_structure()

    def visit_For(
        self,
        node: ast.For,
    ) -> None:
        self.score += 1
        self._ouvrir_structure()

        for enfant in ast.iter_child_nodes(
            node
        ):
            self.visit(enfant)

        self._fermer_structure()

    def visit_AsyncFor(
        self,
        node: ast.AsyncFor,
    ) -> None:
        self.score += 1
        self._ouvrir_structure()

        for enfant in ast.iter_child_nodes(
            node
        ):
            self.visit(enfant)

        self._fermer_structure()

    def visit_While(
        self,
        node: ast.While,
    ) -> None:
        self.score += 1
        self._ouvrir_structure()

        for enfant in ast.iter_child_nodes(
            node
        ):
            self.visit(enfant)

        self._fermer_structure()

    def visit_Try(
        self,
        node: ast.Try,
    ) -> None:

        # try lui-même
        self.score += 1
        self._ouvrir_structure()

        for enfant in ast.iter_child_nodes(
            node
        ):
            self.visit(enfant)

        self._fermer_structure()

    def visit_IfExp(
        self,
        node: ast.IfExp,
    ) -> None:
        self.score += 1

        for enfant in ast.iter_child_nodes(
            node
        ):
            self.visit(enfant)

    def visit_BoolOp(
        self,
        node: ast.BoolOp,
    ) -> None:

        self.score += max(
            0,
            len(node.values) - 1,
        )

        for enfant in ast.iter_child_nodes(
            node
        ):
            self.visit(enfant)

    def visit_ExceptHandler(
        self,
        node: ast.ExceptHandler,
    ) -> None:

        self.score += 1

        self._ouvrir_structure()

        for enfant in ast.iter_child_nodes(
            node
        ):
            self.visit(enfant)

        self._fermer_structure()

    def visit_Match(
        self,
        node: ast.Match,
    ) -> None:

        # Un match est au minimum une décision.
        self.score += max(
            1,
            len(node.cases),
        )

        self._ouvrir_structure()

        self.visit(
            node.subject
        )

        for case in node.cases:
            for enfant in case.body:
                self.visit(enfant)

            if case.guard is not None:
                self.visit(
                    case.guard
                )

        self._fermer_structure()

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef,
    ) -> None:
        # Fonction imbriquée :
        # on ne descend pas dedans.
        return

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        # Fonction imbriquée :
        # on ne descend pas dedans.
        return

    def visit_ClassDef(
        self,
        node: ast.ClassDef,
    ) -> None:
        # Classe imbriquée :
        # on ne descend pas dedans.
        return


def _analyser_complexite_fonction(
    fonction: (
        ast.FunctionDef
        | ast.AsyncFunctionDef
    ),
) -> tuple[int, int]:

    visitor = _ComplexiteVisitor()

    for enfant in fonction.body:
        visitor.visit(
            enfant
        )

    return (
        visitor.score,
        visitor.maximum_profondeur,
    )


def _iter_fonctions_racine(
    arbre: ast.AST,
) -> Iterable[
    ast.FunctionDef
    | ast.AsyncFunctionDef
]:

    for node in ast.walk(
        arbre
    ):

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            yield node


# ============================================================================
# 1. SYNTAXE
# ============================================================================

def detecter_erreurs_syntaxe(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        if analyse.syntaxe_valide:
            continue

        if not analyse.erreurs:
            erreurs = [
                "Syntaxe invalide."
            ]
        else:
            erreurs = analyse.erreurs

        for erreur in erreurs:

            ligne = None

            match = re.search(
                r"ligne\s+(\d+)",
                erreur,
                re.IGNORECASE,
            )

            if match:
                try:
                    ligne = int(
                        match.group(1)
                    )
                except ValueError:
                    ligne = None

            problemes.append(
                _creer_probleme(
                    compteur=compteur,
                    type_="syntaxe",
                    gravite="critique",
                    fichier=analyse.fichier,
                    ligne=ligne,
                    message=(
                        "Erreur de syntaxe détectée."
                    ),
                    preuve=erreur,
                    suggestion=(
                        "Corriger la syntaxe avant "
                        "toute autre modification."
                    ),
                    confiance=1.0,
                    niveau_confiance="CERTAIN",
                    risque="critique",
                    auto_reparable=False,
                )
            )

            compteur += 1

    return problemes


# ============================================================================
# 2. IMPORTS DUPLIQUÉS
# ============================================================================

def detecter_imports_dupliques(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        if Path(
            analyse.fichier
        ).name == "__init__.py":
            continue

        vus: set[str] = set()

        for import_name in analyse.imports:

            cle = (
                import_name
                .strip()
                .lower()
            )

            if not cle:
                continue

            if cle in vus:

                problemes.append(
                    _creer_probleme(
                        compteur=compteur,
                        type_="import_duplique",
                        gravite="qualite",
                        fichier=analyse.fichier,
                        ligne=None,
                        message=(
                            "Import dupliqué détecté."
                        ),
                        preuve=import_name,
                        suggestion=(
                            "Supprimer le doublon "
                            "après vérification."
                        ),
                        confiance=0.98,
                        niveau_confiance="CERTAIN",
                        risque="faible",
                        auto_reparable=True,
                    )
                )

                compteur += 1

            vus.add(
                cle
            )

    return problemes


# ============================================================================
# 3. IMPORTS INUTILISÉS
# ============================================================================

def _collecter_imports(
    arbre: ast.AST,
) -> dict[
    str,
    tuple[str, int],
]:

    imports: dict[
        str,
        tuple[str, int],
    ] = {}

    for node in ast.iter_child_nodes(
        arbre
    ):

        if isinstance(
            node,
            ast.ImportFrom,
        ):

            if node.module == "__future__":
                continue

            for alias in node.names:

                if alias.name == "*":
                    continue

                nom = (
                    alias.asname
                    or alias.name
                )

                imports[nom] = (
                    (
                        f"from "
                        f"{node.module or ''} "
                        f"import "
                        f"{alias.name}"
                    ),
                    node.lineno,
                )

        elif isinstance(
            node,
            ast.Import,
        ):

            for alias in node.names:

                nom = (
                    alias.asname
                    or alias.name.split(
                        "."
                    )[0]
                )

                imports[nom] = (
                    alias.name,
                    node.lineno,
                )

    return imports


def _collecter_noms_utilises(
    arbre: ast.AST,
) -> set[str]:

    resultat: set[str] = set()

    for node in ast.walk(
        arbre
    ):

        if isinstance(
            node,
            ast.Name,
        ) and isinstance(
            node.ctx,
            ast.Load,
        ):
            resultat.add(
                node.id
            )

    return resultat


def detecter_imports_inutilises(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        if (
            Path(
                analyse.fichier
            ).name
            in FICHIERS_REEXPORT_AUTORISES
        ):
            continue

        arbre = _parse_ast(
            analyse.fichier
        )

        if arbre is None:
            continue

        imports = _collecter_imports(
            arbre
        )

        if not imports:
            continue

        utilises = _collecter_noms_utilises(
            arbre
        )

        for nom, (
            import_name,
            ligne,
        ) in imports.items():

            if nom in utilises:
                continue

            problemes.append(
                _creer_probleme(
                    compteur=compteur,
                    type_="import_inutilise",
                    gravite="qualite",
                    fichier=analyse.fichier,
                    ligne=ligne,
                    message=(
                        f"Import potentiellement "
                        f"inutilisé : {import_name}"
                    ),
                    preuve=(
                        f"Le symbole '{nom}' "
                        "n'a pas été trouvé dans "
                        "un contexte de lecture AST."
                    ),
                    suggestion=(
                        "Vérifier l'usage réel avant "
                        "de supprimer l'import."
                    ),
                    confiance=0.80,
                    niveau_confiance="HEURISTIQUE",
                    risque="faible",
                    auto_reparable=False,
                )
            )

            compteur += 1

    return problemes


# ============================================================================
# 4. FONCTIONS TROP LONGUES
# ============================================================================

def detecter_fonctions_trop_longues(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        for fonction in analyse.fonctions:

            if fonction.ligne_fin is None:
                continue

            longueur = (
                fonction.ligne_fin
                - fonction.ligne
                + 1
            )

            if (
                longueur
                <= SEUIL_FONCTION_LIGNES
            ):
                continue

            problemes.append(
                _creer_probleme(
                    compteur=compteur,
                    type_="fonction_trop_longue",
                    gravite="refactoring",
                    fichier=analyse.fichier,
                    ligne=fonction.ligne,
                    message=(
                        f"La fonction "
                        f"'{fonction.nom}' contient "
                        f"{longueur} lignes."
                    ),
                    preuve=(
                        f"lignes={longueur}, "
                        f"seuil={SEUIL_FONCTION_LIGNES}"
                    ),
                    suggestion=(
                        "Examiner si plusieurs "
                        "responsabilités pourraient "
                        "être séparées."
                    ),
                    confiance=0.97,
                    niveau_confiance="HEURISTIQUE",
                    risque="moyen",
                    auto_reparable=False,
                    metadata={
                        "fonction": fonction.nom,
                        "lignes": longueur,
                    },
                )
            )

            compteur += 1

    return problemes


# ============================================================================
# 5. CLASSES TROP LONGUES
# ============================================================================

def detecter_classes_trop_longues(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        for classe in analyse.classes:

            if classe.ligne_fin is None:
                continue

            longueur = (
                classe.ligne_fin
                - classe.ligne
                + 1
            )

            if (
                longueur
                <= SEUIL_CLASSE_LIGNES
            ):
                continue

            problemes.append(
                _creer_probleme(
                    compteur=compteur,
                    type_="classe_trop_longue",
                    gravite="refactoring",
                    fichier=analyse.fichier,
                    ligne=classe.ligne,
                    message=(
                        f"La classe "
                        f"'{classe.nom}' contient "
                        f"{longueur} lignes."
                    ),
                    preuve=(
                        f"lignes={longueur}, "
                        f"seuil={SEUIL_CLASSE_LIGNES}"
                    ),
                    suggestion=(
                        "Examiner la séparation "
                        "des responsabilités."
                    ),
                    confiance=0.96,
                    niveau_confiance="HEURISTIQUE",
                    risque="moyen",
                    auto_reparable=False,
                )
            )

            compteur += 1

    return problemes


# ============================================================================
# 6. COMPLEXITÉ
# ============================================================================

def detecter_complexite(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        arbre = _parse_ast(
            analyse.fichier
        )

        if arbre is None:
            continue

        for fonction in _iter_fonctions_racine(
            arbre
        ):

            score, profondeur = (
                _analyser_complexite_fonction(
                    fonction
                )
            )

            if (
                score
                > SEUIL_COMPLEXITE
            ):
                problemes.append(
                    _creer_probleme(
                        compteur=compteur,
                        type_="complexite",
                        gravite="important",
                        fichier=analyse.fichier,
                        ligne=fonction.lineno,
                        message=(
                            f"La fonction "
                            f"'{fonction.name}' présente "
                            f"une complexité estimée "
                            f"à {score}."
                        ),
                        preuve=(
                            f"complexite={score}, "
                            f"seuil={SEUIL_COMPLEXITE}"
                        ),
                        suggestion=(
                            "Envisager de simplifier "
                            "les branches ou d'extraire "
                            "des responsabilités."
                        ),
                        confiance=0.92,
                        niveau_confiance="HEURISTIQUE",
                        risque="moyen",
                        auto_reparable=False,
                        metadata={
                            "fonction": fonction.name,
                            "complexite": score,
                        },
                    )
                )

                compteur += 1

            if (
                profondeur
                > SEUIL_NIVEAU_IMBRICATION
            ):
                problemes.append(
                    _creer_probleme(
                        compteur=compteur,
                        type_="imbrication",
                        gravite="qualite",
                        fichier=analyse.fichier,
                        ligne=fonction.lineno,
                        message=(
                            f"La fonction "
                            f"'{fonction.name}' possède "
                            f"une imbrication profonde."
                        ),
                        preuve=(
                            f"profondeur={profondeur}, "
                            f"seuil={SEUIL_NIVEAU_IMBRICATION}"
                        ),
                        suggestion=(
                            "Réduire l'imbrication "
                            "si cela améliore la lisibilité."
                        ),
                        confiance=0.90,
                        niveau_confiance="HEURISTIQUE",
                        risque="faible",
                        auto_reparable=False,
                    )
                )

                compteur += 1

    return problemes


# ============================================================================
# 7. APPELS DANGEREUX
# ============================================================================

def detecter_appels_sensibles(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        arbre = _parse_ast(
            analyse.fichier
        )

        if arbre is None:
            continue

        for node in ast.walk(
            arbre
        ):

            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            nom = _nom_appel(node.func)

            gravite: Optional[str] = None
            risque: Optional[str] = None
            message: Optional[str] = None
            suggestion = ""

            if nom == "eval":
                gravite = "critique"
                risque = "critique"
                message = (
                    "Appel eval() détecté."
                )
                suggestion = (
                    "Vérifier impérativement "
                    "la provenance et le contrôle "
                    "de la donnée exécutée."
                )

            elif nom == "exec":
                gravite = "critique"
                risque = "critique"
                message = (
                    "Appel exec() détecté."
                )
                suggestion = (
                    "Éviter l'exécution dynamique "
                    "de code lorsque cela est possible."
                )

            elif nom == "os.system":
                gravite = "important"
                risque = "eleve"
                message = (
                    "Appel os.system() détecté."
                )
                suggestion = (
                    "Vérifier les arguments et "
                    "éviter d'injecter une entrée "
                    "utilisateur non contrôlée."
                )

            elif nom == "os.popen":
                gravite = "important"
                risque = "eleve"
                message = (
                    "Appel os.popen() détecté."
                )
                suggestion = (
                    "Examiner une API de processus "
                    "plus contrôlée."
                )

            if message is None:
                continue

            problemes.append(
                _creer_probleme(
                    compteur=compteur,
                    type_="appel_sensible",
                    gravite=gravite or "qualite",
                    fichier=analyse.fichier,
                    ligne=getattr(
                        node,
                        "lineno",
                        None,
                    ),
                    message=message,
                    preuve=(
                        f"cible={nom}"
                    ),
                    suggestion=suggestion,
                    confiance=0.99,
                    niveau_confiance="FORT",
                    risque=risque or "moyen",
                    auto_reparable=False,
                )
            )

            compteur += 1

    return problemes


# ============================================================================
# 8. SUBPROCESS AVEC SHELL
# ============================================================================

def detecter_subprocess_dangereux(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    noms_supportes = {
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
    }

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        arbre = _parse_ast(
            analyse.fichier
        )

        if arbre is None:
            continue

        for node in ast.walk(
            arbre
        ):

            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            nom = _nom_cible(
                node.func
            )

            if nom not in noms_supportes:
                continue

            shell_true = False

            for keyword in node.keywords:

                if (
                    keyword.arg == "shell"
                    and isinstance(
                        keyword.value,
                        ast.Constant,
                    )
                    and keyword.value.value is True
                ):
                    shell_true = True
                    break

            if not shell_true:
                continue

            problemes.append(
                _creer_probleme(
                    compteur=compteur,
                    type_="subprocess_shell",
                    gravite="important",
                    fichier=analyse.fichier,
                    ligne=getattr(
                        node,
                        "lineno",
                        None,
                    ),
                    message=(
                        "subprocess avec shell=True détecté."
                    ),
                    preuve="shell=True",
                    suggestion=(
                        "Vérifier les entrées utilisées "
                        "et éviter shell=True lorsqu'il "
                        "n'est pas nécessaire."
                    ),
                    confiance=0.99,
                    niveau_confiance="CERTAIN",
                    risque="eleve",
                    auto_reparable=False,
                )
            )

            compteur += 1

    return problemes


# ============================================================================
# 9. IMPORTS SENSIBLES
# ============================================================================

def detecter_imports_sensibles(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    modules = {
        "ctypes": (
            "Import ctypes détecté.",
            "important",
            "eleve",
        ),
        "pickle": (
            "Import pickle détecté.",
            "qualite",
            "moyen",
        ),
    }

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        for import_name in analyse.imports:

            racine = import_name

            if racine.startswith(
                "from "
            ):
                racine = racine[5:].strip()

            racine = racine.split(
                ".",
                1,
            )[0]

            if racine not in modules:
                continue

            (
                message,
                gravite,
                risque,
            ) = modules[racine]

            problemes.append(
                _creer_probleme(
                    compteur=compteur,
                    type_="import_sensible",
                    gravite=gravite,
                    fichier=analyse.fichier,
                    ligne=None,
                    message=message,
                    preuve=import_name,
                    suggestion=(
                        "Vérifier le contexte d'utilisation "
                        "et les données concernées."
                    ),
                    confiance=0.95,
                    niveau_confiance="FORT",
                    risque=risque,
                    auto_reparable=False,
                )
            )

            compteur += 1

    return problemes


# ============================================================================
# 10. SECRETS POTENTIELS
# ============================================================================

def detecter_secrets_potentiels(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    motifs = [
        re.compile(
            r"\b("
            r"api[_-]?key|"
            r"secret|"
            r"token|"
            r"password|"
            r"passwd|"
            r"motdepasse"
            r")\b"
            r"\s*=\s*"
            r"[\"'][^\"'\n]{8,}[\"']",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bAKIA[0-9A-Z]{16}\b"
        ),
        re.compile(
            r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"
        ),
    ]

    for analyse in _iter_fichiers(
        analyse_projet
    ):

        source = _lire_source(
            analyse.fichier
        )

        if source is None:
            continue

        for numero, ligne in enumerate(
            source.splitlines(),
            start=1,
        ):

            trouve = False

            for motif in motifs:

                if motif.search(
                    ligne
                ):
                    trouve = True
                    break

            if not trouve:
                continue

            problemes.append(
                _creer_probleme(
                    compteur=compteur,
                    type_="secret_potentiel",
                    gravite="critique",
                    fichier=analyse.fichier,
                    ligne=numero,
                    message=(
                        "Secret potentiellement "
                        "codé en dur détecté."
                    ),
                    preuve=(
                        "Motif sensible détecté ; "
                        "la valeur n'est pas conservée."
                    ),
                    suggestion=(
                        "Déplacer la valeur vers "
                        "un mécanisme de configuration "
                        "sécurisé."
                    ),
                    confiance=0.90,
                    niveau_confiance="FORT",
                    risque="critique",
                    auto_reparable=False,
                )
            )

            compteur += 1

    return problemes


# ============================================================================
# 11. ARCHITECTURE
# ============================================================================

def detecter_incoherences_architecture(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:

    problemes: list[
        Probleme
    ] = []

    compteur = 1

    for source, dependances in (
        analyse_projet.dependances_internes.items()
    ):

        source = str(
            source
        )

        source_core = (
            source == "core"
            or source.startswith(
                "core."
            )
        )

        source_gui = (
            source == "gui"
            or source.startswith(
                "gui."
            )
            or source.startswith(
                "gui_kit."
            )
        )

        source_self = (
            source == "self_improvement"
            or source.startswith(
                "self_improvement."
            )
        )

        for cible in dependances:

            cible = str(
                cible
            )

            # --------------------------------------------------------
            # self_improvement -> GUI
            # --------------------------------------------------------

            if (
                source_self
                and (
                    cible.startswith("gui.")
                    or cible.startswith("gui_kit.")
                )
            ):
                problemes.append(
                    _creer_probleme(
                        compteur=compteur,
                        type_="architecture",
                        gravite="important",
                        fichier=source,
                        ligne=None,
                        message=(
                            "Dépendance self_improvement → GUI détectée."
                        ),
                        preuve=(
                            f"{source} → {cible}"
                        ),
                        suggestion=(
                            "self_improvement ne devrait pas "
                            "dépendre de l'interface graphique."
                        ),
                        confiance=0.98,
                        niveau_confiance="FORT",
                        risque="moyen",
                        auto_reparable=False,
                    )
                )

                compteur += 1

            # --------------------------------------------------------
            # core -> GUI
            # --------------------------------------------------------

            if (
                source_core
                and (
                    cible.startswith("gui.")
                    or cible.startswith("gui_kit.")
                )
            ):
                problemes.append(
                    _creer_probleme(
                        compteur=compteur,
                        type_="architecture",
                        gravite="important",
                        fichier=source,
                        ligne=None,
                        message=(
                            "Dépendance core → GUI détectée."
                        ),
                        preuve=(
                            f"{source} → {cible}"
                        ),
                        suggestion=(
                            "La couche core doit rester indépendante "
                            "de l'interface graphique."
                        ),
                        confiance=0.98,
                        niveau_confiance="FORT",
                        risque="moyen",
                        auto_reparable=False,
                    )
                )

                compteur += 1

    return problemes


# ============================================================================
# REGROUPEMENT ET NORMALISATION
# ============================================================================

def _normaliser_texte_groupe(valeur) -> str:
    """Normalise le texte pour le regroupement déterministe."""
    return " ".join(
        str(valeur or "")
        .lower()
        .strip()
        .split()
    )


def _cle_groupe_probleme(probleme) -> str:
    """
    Regroupe les problèmes par cause technique contextuelle.
    
    Stratégie :
        - Problèmes structurels : type + fichier
        - Problèmes de sécurité : type + message + ligne
    
    Exemples :
        complexite|core/cerveau.py
        complexite|core/agent_core.py
        appel_sensible|appel os.system() détecté.|245
    """
    if isinstance(probleme, dict):
        type_probleme = probleme.get("type", "")
        fichier = probleme.get("fichier", "")
        ligne = probleme.get("ligne", "")
        message = probleme.get("message", "")
    else:
        type_probleme = getattr(probleme, "type", "")
        fichier = getattr(probleme, "fichier", "")
        ligne = getattr(probleme, "ligne", "")
        message = getattr(probleme, "message", "")

    type_probleme = str(type_probleme).strip().lower()
    fichier = str(fichier).strip().lower()

    # Pour les problèmes structurels, on conserve le fichier.
    if type_probleme in {
        "complexite",
        "fonction_trop_longue",
        "classe_trop_longue",
        "imbrication",
        "import_inutilise",
        "import_duplique",
    }:
        return f"{type_probleme}|{fichier}"

    # Pour les problèmes de sécurité/appels sensibles,
    # le message permet de distinguer les appels.
    message = " ".join(
        str(message).lower().split()
    )

    return f"{type_probleme}|{message}|{ligne}"


def _selectionner_groupes_equilibres(
    groupes,
    max_groupes=5,
):
    """
    Sélectionne les groupes de manière équilibrée.
    
    Stratégie :
        1. Un groupe par type en priorité (diversité)
        2. Compléter avec les groupes les plus importants
    
    Cela garantit qu'on voit plusieurs catégories de problèmes,
    pas uniquement la catégorie la plus fréquente.
    """
    resultat = []
    types_vus = set()

    # PHASE 1 : Un groupe par type en priorité
    for groupe in groupes:
        type_pb = groupe.get("type", "")

        if type_pb not in types_vus:
            resultat.append(groupe)
            types_vus.add(type_pb)

        if len(resultat) >= max_groupes:
            return resultat

    # PHASE 2 : Compléter avec les groupes les plus importants
    for groupe in groupes:
        if groupe in resultat:
            continue

        resultat.append(groupe)

        if len(resultat) >= max_groupes:
            break

    return resultat


def regrouper_problemes(
    problemes,
    max_groupes: int = 5,
) -> list:
    """
    Transforme une liste de problèmes individuels
    en quelques causes racines compactes.

    Aucun appel LLM.
    
    Args:
        problemes: Liste de Probleme ou dict
        max_groupes: Nombre maximum de groupes à retourner
        
    Returns:
        Liste de groupes de problèmes consolidés
    """

    groupes = defaultdict(list)

    for probleme in problemes or []:

        if isinstance(probleme, dict):
            info = dict(probleme)
        else:
            info = getattr(
                probleme,
                "__dict__",
                {},
            )

        if not info:
            continue

        cle = _cle_groupe_probleme(
            info
        )

        groupes[cle].append(
            info
        )

    resultat = []

    gravites = {
        "critique": 0,
        "important": 1,
        "qualite": 2,
        "refactoring": 3,
    }

    niveaux = {
        "CERTAIN": 0,
        "FORT": 1,
        "HEURISTIQUE": 2,
    }

    for cle, elements in groupes.items():

        if not elements:
            continue

        def gravite(item):
            return gravites.get(
                str(
                    item.get(
                        "gravite",
                        "",
                    )
                ).lower(),
                9,
            )

        def confiance(item):
            try:
                return float(
                    item.get(
                        "confiance",
                        0.0,
                    )
                    or 0.0
                )
            except (
                TypeError,
                ValueError,
            ):
                return 0.0

        def niveau(item):
            return niveaux.get(
                str(
                    item.get(
                        "niveau_confiance",
                        "",
                    )
                ).upper(),
                9,
            )

        elements_tries = sorted(
            elements,
            key=lambda x: (
                gravite(x),
                niveau(x),
                -confiance(x),
            ),
        )

        principal = elements_tries[0]

        fichiers = []
        ids = []
        preuves = []

        for item in elements_tries:

            fichier = item.get(
                "fichier"
            )

            if fichier and fichier not in fichiers:
                fichiers.append(
                    str(fichier)
                )

            identifiant = item.get(
                "id"
            )

            if identifiant is not None:
                ids.append(
                    identifiant
                )

            preuve = str(
                item.get(
                    "preuve",
                    "",
                )
            ).strip()

            if preuve and preuve not in preuves:
                preuves.append(
                    preuve[:180]
                )

        resultat.append(
            {
                "type": principal.get("type"),
                "gravite": principal.get(
                    "gravite"
                ),
                "titre": str(
                    principal.get(
                        "message",
                        cle,
                    )
                )[:180],
                "description": (
                    f"{len(elements)} problème(s) similaire(s)."
                ),
                "ids": ids[:50],
                "fichiers": fichiers[:20],
                "preuve": "; ".join(
                    preuves[:3]
                ),
                "confiance": max(
                    (
                        confiance(x)
                        for x in elements
                    ),
                    default=0.0,
                ),
                "niveau_confiance": str(
                    principal.get(
                        "niveau_confiance",
                        "HEURISTIQUE",
                    )
                ).upper(),
                "nombre": len(
                    elements
                ),
            }
        )

    resultat.sort(
        key=lambda x: (
            gravites.get(
                str(
                    x.get(
                        "gravite",
                        "",
                    )
                ).lower(),
                9,
            ),
            -x.get(
                "nombre",
                0,
            ),
            -float(
                x.get(
                    "confiance",
                    0.0,
                )
                or 0.0
            ),
        )
    )

    return _selectionner_groupes_equilibres(
        resultat,
        max_groupes=max_groupes,
    )


def _renumeroter_problemes(
    problemes
) -> list:
    """
    Assure des IDs uniques et séquentiels.
    
    Corrige le problème de compteurs multiples indépendants.
    """

    resultat = []

    for index, probleme in enumerate(
        problemes,
        start=1,
    ):

        if isinstance(
            probleme,
            dict,
        ):
            probleme["id"] = f"PB-{index:05d}"
        else:
            try:
                probleme.id = f"PB-{index:05d}"
            except Exception:
                pass

        resultat.append(
            probleme
        )

    return resultat


# ============================================================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================================================

def detecter_problemes(
    analyse_projet: AnalyseProjet,
) -> list[Probleme]:
    """
    Point d'entrée unique pour la détection de problèmes.

    Args:
        analyse_projet: Résultat de l'analyse du projet

    Returns:
        Liste de problèmes détectés avec IDs uniques
    """

    problemes: list[Probleme] = []

    # Exécution de tous les détecteurs
    problemes.extend(
        detecter_erreurs_syntaxe(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_imports_dupliques(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_imports_inutilises(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_fonctions_trop_longues(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_classes_trop_longues(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_complexite(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_appels_sensibles(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_subprocess_dangereux(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_imports_sensibles(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_secrets_potentiels(
            analyse_projet
        )
    )

    problemes.extend(
        detecter_incoherences_architecture(
            analyse_projet
        )
    )

    # CRITIQUE : Renumérotation globale pour éviter les IDs dupliqués
    problemes = _renumeroter_problemes(
        problemes
    )

    return problemes


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "Probleme",
    "detecter_problemes",
    "regrouper_problemes",
    "SEUIL_FONCTION_LIGNES",
    "SEUIL_CLASSE_LIGNES",
    "SEUIL_COMPLEXITE",
    "SEUIL_NIVEAU_IMBRICATION",
]