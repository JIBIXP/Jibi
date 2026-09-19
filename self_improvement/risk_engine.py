from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass
from pathlib import Path

from .politiques import niveau_risque, peut_auto_appliquer


@dataclass
class EvaluationRisque:
    fichier: str
    niveau: str
    lignes_diff: int
    touches_imports: bool
    touches_dependances: bool
    auto_applicable: bool
    raisons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# DIFF
# ---------------------------------------------------------------------------

def compter_lignes_diff(diff: str) -> int:
    """Compte uniquement les lignes réellement ajoutées/supprimées."""
    return sum(
        1
        for ligne in diff.splitlines()
        if ligne.startswith(("+", "-"))
        and not ligne.startswith(("+++", "---"))
    )


def _lignes_modifiees(diff: str) -> list[str]:
    """Retourne les lignes ajoutées/supprimées d'un diff."""
    return [
        ligne
        for ligne in diff.splitlines()
        if ligne.startswith(("+", "-"))
        and not ligne.startswith(("+++", "---"))
    ]


# ---------------------------------------------------------------------------
# IMPORTS
# ---------------------------------------------------------------------------

def detecter_imports(diff: str) -> bool:
    """Détecte une modification d'import Python."""
    for ligne in _lignes_modifiees(diff):
        contenu = ligne[1:].strip()

        if contenu.startswith("import "):
            return True

        if contenu.startswith("from "):
            return True

    return False


# ---------------------------------------------------------------------------
# DEPENDANCES
# ---------------------------------------------------------------------------

_FICHIERS_DEPENDANCES = {
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "pyproject.toml",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
    "uv.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


def detecter_dependances(fichier: str, diff: str) -> bool:
    """Détecte une modification pouvant affecter les dépendances."""
    nom = Path(fichier).name.lower()

    if nom in _FICHIERS_DEPENDANCES:
        return True

    for ligne in _lignes_modifiees(diff):
        contenu = ligne[1:].strip().lower()

        if "pip install" in contenu:
            return True

        if "poetry add" in contenu:
            return True

        if "uv add" in contenu:
            return True

        if "npm install" in contenu:
            return True

        if "npm i " in contenu:
            return True

        if "pnpm add" in contenu:
            return True

        if "yarn add" in contenu:
            return True

    return False


# ---------------------------------------------------------------------------
# EVALUATION
# ---------------------------------------------------------------------------

def evaluer_proposition(proposition: dict) -> dict:
    """
    Évalue le risque d'une proposition.

    Ce module ne modifie jamais le projet.
    Il produit uniquement une évaluation destinée à l'orchestrateur.
    """
    fichier = str(proposition.get("fichier", "") or "")
    diff = str(proposition.get("diff", "") or "")

    lignes = compter_lignes_diff(diff)
    imports = detecter_imports(diff)
    dependances = detecter_dependances(fichier, diff)

    niveau = niveau_risque(
        fichier,
        lignes_diff=lignes,
        touches_imports=imports,
        touches_dependances=dependances,
    )

    auto_ok, raison = peut_auto_appliquer(
        fichier,
        lignes_diff=lignes,
    )

    raisons: list[str] = []

    if raison:
        raisons.append(str(raison))

    if imports:
        raisons.append("modification d'import")

    if dependances:
        raisons.append("modification de dépendances")

    if lignes > 50:
        raisons.append("diff supérieur au seuil automatique")

    if niveau == "critique":
        raisons.append("niveau critique")

    # Une modification de dépendance ou d'import ne doit pas
    # être auto-appliquée sans validation supplémentaire.
    if imports:
        auto_ok = False

    if dependances:
        auto_ok = False

    if niveau in {"élevé", "critique"}:
        auto_ok = False

    return EvaluationRisque(
        fichier=fichier,
        niveau=niveau,
        lignes_diff=lignes,
        touches_imports=imports,
        touches_dependances=dependances,
        auto_applicable=bool(auto_ok),
        raisons=raisons,
    ).to_dict()


# ---------------------------------------------------------------------------
# EVALUATION D'UN PATCH
# ---------------------------------------------------------------------------

def evaluer_patch(
    fichier: str,
    ancien: str,
    nouveau: str,
) -> dict:
    """
    Construit un diff entre deux versions puis évalue son risque.
    Aucun fichier n'est écrit.
    """
    diff = "".join(
        difflib.unified_diff(
            ancien.splitlines(True),
            nouveau.splitlines(True),
            fromfile=f"a/{fichier}",
            tofile=f"b/{fichier}",
        )
    )

    return evaluer_proposition(
        {
            "fichier": fichier,
            "diff": diff,
        }
    )