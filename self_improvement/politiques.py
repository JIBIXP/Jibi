from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# ============================================================================
# CONSTANTES
# ============================================================================

NIVEAUX_RISQUE = (
    "faible",
    "moyen",
    "élevé",
    "critique",
)

LIMITE_DIFF_AUTO = 50
LIMITE_DIFF_ELEVE = 100


# ============================================================================
# POLITIQUE
# ============================================================================

@dataclass(frozen=True)
class PolitiqueFichier:
    niveau: str
    auto_application: bool = False
    confirmation_humaine: bool = True
    raisons: tuple[str, ...] = field(default_factory=tuple)


# ============================================================================
# PROTECTIONS
# ============================================================================

DOSSIERS_BLOQUES = {
    ".git",
    ".ssh",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
}

FICHIERS_BLOQUES = {
    ".env",
    "secrets.json",
}

# Fichiers dont la modification doit toujours être traitée comme critique.
# La liste doit rester cohérente avec l'architecture réelle de JIBI.
FICHIERS_CRITIQUES = {
    "core/agent_core.py",
    "core/cerveau.py",
    "core/config.py",
    "self_improvement/autorisation.py",
    "self_improvement/gestionnaire.py",
    "self_improvement/orchestrateur.py",
    "self_improvement/propositions.py",
    "self_improvement/risk_engine.py",
    "self_improvement/validateur.py",
    "self_improvement/laboratoire.py",
    "updater/updater.py",
}


# Extensions pouvant bénéficier de l'auto-application.
# La politique reste volontairement restrictive.
EXTENSIONS_AUTO = {
    ".py",
}


# ============================================================================
# NORMALISATION
# ============================================================================

def normaliser_chemin(fichier: str | Path) -> str:
    """
    Normalise un chemin relatif pour les comparaisons de politique.

    Cette fonction ne résout PAS le chemin sur disque.
    La validation physique du chemin appartient à la couche sécurité.
    """
    texte = str(fichier).strip()

    texte = texte.replace("\\", "/")

    while texte.startswith("./"):
        texte = texte[2:]

    return texte


# ============================================================================
# POLITIQUE PAR FICHIER
# ============================================================================

def politique_fichier(fichier: str | Path) -> PolitiqueFichier:
    """
    Retourne la politique applicable à un fichier.

    Cette fonction ne lit et ne modifie aucun fichier.
    """
    rel = normaliser_chemin(fichier)
    path = Path(rel)

    # Chemin absolu : toujours interdit en auto-application.
    if path.is_absolute():
        return PolitiqueFichier(
            niveau="critique",
            auto_application=False,
            confirmation_humaine=True,
            raisons=("chemin absolu interdit",),
        )

    # Protection contre les chemins contenant .. .
    if ".." in path.parts:
        return PolitiqueFichier(
            niveau="critique",
            auto_application=False,
            confirmation_humaine=True,
            raisons=("traversée de répertoire interdite",),
        )

    # Dossiers protégés.
    if any(part.lower() in DOSSIERS_BLOQUES for part in path.parts):
        return PolitiqueFichier(
            niveau="critique",
            auto_application=False,
            confirmation_humaine=True,
            raisons=("dossier protégé",),
        )

    # Fichiers secrets.
    if path.name.lower() in {
        nom.lower() for nom in FICHIERS_BLOQUES
    }:
        return PolitiqueFichier(
            niveau="critique",
            auto_application=False,
            confirmation_humaine=True,
            raisons=("fichier secret",),
        )

    # Fichiers critiques.
    if rel.lower() in {
        nom.lower() for nom in FICHIERS_CRITIQUES
    }:
        return PolitiqueFichier(
            niveau="critique",
            auto_application=False,
            confirmation_humaine=True,
            raisons=("fichier critique JIBI",),
        )

    # Type de fichier non autorisé pour l'auto-application.
    if path.suffix.lower() not in EXTENSIONS_AUTO:
        return PolitiqueFichier(
            niveau="élevé",
            auto_application=False,
            confirmation_humaine=True,
            raisons=(
                "type de fichier non autorisé en auto-application",
            ),
        )

    # Cas nominal : petit fichier Python non critique.
    return PolitiqueFichier(
        niveau="faible",
        auto_application=True,
        confirmation_humaine=False,
        raisons=(),
    )


# ============================================================================
# AUTO-APPLICATION
# ============================================================================

def peut_auto_appliquer(
    fichier: str | Path,
    *,
    lignes_diff: int = 0,
    limite_diff: int = LIMITE_DIFF_AUTO,
) -> tuple[bool, str]:
    """
    Détermine si une proposition peut être auto-appliquée.

    La fonction ne fait aucune modification.
    """
    if lignes_diff < 0:
        return False, "nombre de lignes de diff invalide"

    if limite_diff < 0:
        return False, "limite de diff invalide"

    politique = politique_fichier(fichier)

    if not politique.auto_application:
        return (
            False,
            "; ".join(politique.raisons)
            or "auto-application interdite",
        )

    if lignes_diff > limite_diff:
        return (
            False,
            f"diff trop important : {lignes_diff} > {limite_diff}",
        )

    return True, ""


# ============================================================================
# NIVEAU DE RISQUE
# ============================================================================

def niveau_risque(
    fichier: str | Path,
    *,
    lignes_diff: int = 0,
    touches_imports: bool = False,
    touches_dependances: bool = False,
) -> str:
    """
    Calcule le niveau de risque structurel d'une proposition.

    Cette fonction ne décide pas de l'application finale.
    L'orchestrateur utilise ensuite cette information avec
    les règles d'autorisation et de validation.
    """
    if lignes_diff < 0:
        return "critique"

    politique = politique_fichier(fichier)

    # Protection absolue.
    if politique.niveau == "critique":
        return "critique"

    # Toute modification de dépendance est critique.
    if touches_dependances:
        return "critique"

    # Modification d'import : risque supérieur au niveau nominal.
    if touches_imports:
        if politique.niveau == "faible":
            return "moyen"

        if politique.niveau == "moyen":
            return "élevé"

    # Taille du patch.
    if lignes_diff > LIMITE_DIFF_ELEVE:
        return "élevé"

    if lignes_diff > LIMITE_DIFF_AUTO:
        return "moyen"

    return politique.niveau


# ============================================================================
# HELPERS
# ============================================================================

def est_niveau_risque_valide(niveau: str) -> bool:
    """Vérifie qu'un niveau de risque appartient aux niveaux connus."""
    return niveau in NIVEAUX_RISQUE


def seuil_diff_auto() -> int:
    """Retourne le seuil utilisé pour l'auto-application."""
    return LIMITE_DIFF_AUTO


def seuil_diff_eleve() -> int:
    """Retourne le seuil à partir duquel le risque devient élevé."""
    return LIMITE_DIFF_ELEVE