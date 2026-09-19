# -*- coding: utf-8 -*-
"""
JIBI - Observateur
==================

Collecte les faits nécessaires au système d'auto-diagnostic de JIBI.

Responsabilités :
    - observer les logs ;
    - récupérer l'état de santé ;
    - récupérer les erreurs et warnings ;
    - identifier les fichiers potentiellement concernés ;
    - récupérer quelques informations système/processus ;
    - produire un rapport structuré ;
    - ne jamais modifier le code de production.

Architecture :

    observateur
         ↓
    diagnostiqueur
         ↓
    analyseur_code
         ↓
    orchestrateur
         ↓
    générateur de patch
         ↓
    laboratoire
         ↓
    validateur
         ↓
    politique / risque
         ↓
    application / rollback
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ============================================================================
# LOGGING
# ============================================================================

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

try:
    from core.config import (
        LOGS_DIR,
        WORKSPACE_DIR,
    )
except Exception:
    # Fallback uniquement pour permettre l'import du module
    # dans un environnement incomplet.
    PROJECT_ROOT = Path(__file__).resolve().parents[1]

    LOGS_DIR = PROJECT_ROOT / "logs"
    WORKSPACE_DIR = PROJECT_ROOT / "workspace"


LOGS_DIR = Path(LOGS_DIR)
WORKSPACE_DIR = Path(WORKSPACE_DIR)


# ============================================================================
# CONSTANTES
# ============================================================================

MAX_LOG_FILES = 10
MAX_LOG_LINES = 5000
MAX_ERROR_LINES = 500

DEFAULT_HEALTH = {
    "score": None,
    "niveau": "INCONNU",
}


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class FaitObservation:
    """
    Un fait observé par JIBI.

    Un fait doit rester descriptif.

    Exemple :
        type = "error"
        source = "jibi.log"
        message = "ModuleNotFoundError..."
    """

    type: str
    source: str
    message: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EtatSante:
    """
    État de santé observé.

    Ce n'est pas encore un diagnostic.
    """

    score: Optional[float] = None
    niveau: str = "INCONNU"
    erreurs: int = 0
    warnings: int = 0
    fichiers_logs: int = 0
    patterns_recurrents: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ObservationSysteme:
    """
    Informations système minimales.

    Ces informations servent au diagnostic mais ne déclenchent
    aucune modification.
    """

    plateforme: str
    systeme: str
    version_systeme: str
    architecture: str
    python: str
    executable_python: str
    repertoire_projet: str
    pid: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RapportObservation:
    """
    Rapport complet produit par l'observateur.
    """

    ok: bool
    timestamp_debut: str
    timestamp_fin: str
    duree_ms: float

    sante: EtatSante
    systeme: ObservationSysteme

    faits: list[FaitObservation] = field(default_factory=list)

    erreurs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    fichiers_concernes: list[str] = field(default_factory=list)
    logs_analyses: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "timestamp_debut": self.timestamp_debut,
            "timestamp_fin": self.timestamp_fin,
            "duree_ms": self.duree_ms,
            "sante": self.sante.to_dict(),
            "systeme": self.systeme.to_dict(),
            "faits": [fait.to_dict() for fait in self.faits],
            "erreurs": self.erreurs,
            "warnings": self.warnings,
            "fichiers_concernes": self.fichiers_concernes,
            "logs_analyses": self.logs_analyses,
            "metadata": self.metadata,
        }


# ============================================================================
# OUTILS INTERNES
# ============================================================================

def _timestamp() -> str:
    """Retourne un timestamp UTC ISO 8601."""

    return datetime.now(timezone.utc).isoformat()


def _safe_string(value: Any) -> str:
    """Convertit proprement une valeur en texte."""

    if value is None:
        return ""

    try:
        return str(value)
    except Exception:
        return "<valeur_inaccessible>"


def _tail_lines(
    texte: str,
    limite: int = MAX_LOG_LINES,
) -> list[str]:
    """
    Retourne les dernières lignes d'un texte.

    Permet d'éviter de charger inutilement d'immenses logs.
    """

    lignes = texte.splitlines()

    if len(lignes) <= limite:
        return lignes

    return lignes[-limite:]


def _lire_fichier_log(path: Path) -> list[str]:
    """
    Lit un fichier de log de façon tolérante.

    Aucun fichier n'est modifié.
    """

    try:
        if not path.exists() or not path.is_file():
            return []

        if path.is_symlink():
            return []

        texte = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        return _tail_lines(texte)

    except Exception as exc:
        logger.debug(
            "Impossible de lire le log %s : %s",
            path,
            exc,
        )
        return []


def _lister_logs() -> list[Path]:
    """
    Retourne les fichiers de logs candidats.

    On limite volontairement le nombre de fichiers.
    """

    try:
        if not LOGS_DIR.exists() or not LOGS_DIR.is_dir():
            return []

        fichiers = [
            p
            for p in LOGS_DIR.rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and p.suffix.lower() in {
                ".log",
                ".txt",
            }
        ]

        fichiers.sort(
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        return fichiers[:MAX_LOG_FILES]

    except Exception as exc:
        logger.debug(
            "Impossible de lister les logs : %s",
            exc,
        )
        return []


# ============================================================================
# DÉTECTION DES ERREURS
# ============================================================================

_ERROR_PATTERNS = (
    re.compile(r"\bTraceback \(most recent call last\)", re.I),
    re.compile(r"\bERROR\b", re.I),
    re.compile(r"\bCRITICAL\b", re.I),
    re.compile(r"\bException\b", re.I),
    re.compile(r"\bError\b", re.I),
    re.compile(r"\bFailed\b", re.I),
    re.compile(r"\bFailure\b", re.I),
)

_WARNING_PATTERNS = (
    re.compile(r"\bWARNING\b", re.I),
    re.compile(r"\bWARN\b", re.I),
    re.compile(r"\bWarning\b", re.I),
)

_FILE_PATTERNS = (
    # Windows
    re.compile(
        r'([A-Za-z]:[\\/][^\s:"<>|]+\.py)',
        re.I,
    ),

    # Linux / Unix
    re.compile(
        r'(/[^\s:]+\.py)',
        re.I,
    ),

    # Chemins relatifs
    re.compile(
        r'((?:core|self_improvement|tools|updater)[\\/][^\s:]+\.py)',
        re.I,
    ),
)


def _est_erreur(ligne: str) -> bool:
    """Détermine si une ligne ressemble à une erreur."""

    return any(
        pattern.search(ligne)
        for pattern in _ERROR_PATTERNS
    )


def _est_warning(ligne: str) -> bool:
    """Détermine si une ligne ressemble à un warning."""

    return any(
        pattern.search(ligne)
        for pattern in _WARNING_PATTERNS
    )


def _extraire_fichiers(ligne: str) -> list[str]:
    """Extrait les chemins Python visibles dans une ligne."""

    resultat: list[str] = []

    for pattern in _FILE_PATTERNS:
        for match in pattern.findall(ligne):
            if match and match not in resultat:
                resultat.append(match)

    return resultat


# ============================================================================
# OBSERVATION DES LOGS
# ============================================================================

def observer_logs() -> dict[str, Any]:
    """
    Analyse les logs disponibles.

    Retourne uniquement des faits observés.
    """

    erreurs: list[str] = []
    warnings: list[str] = []
    fichiers_concernes: list[str] = []
    logs_analyses: list[str] = []

    faits: list[FaitObservation] = []

    fichiers_logs = _lister_logs()

    for log_path in fichiers_logs:
        lignes = _lire_fichier_log(log_path)

        if not lignes:
            continue

        logs_analyses.append(str(log_path))

        for ligne in lignes:
            ligne = ligne.strip()

            if not ligne:
                continue

            fichiers = _extraire_fichiers(ligne)

            for fichier in fichiers:
                if fichier not in fichiers_concernes:
                    fichiers_concernes.append(fichier)

            if _est_erreur(ligne):
                if len(erreurs) < MAX_ERROR_LINES:
                    erreurs.append(ligne)

                faits.append(
                    FaitObservation(
                        type="error",
                        source=str(log_path),
                        message=ligne,
                        timestamp=_timestamp(),
                        metadata={
                            "fichiers": fichiers,
                        },
                    )
                )

            elif _est_warning(ligne):
                if len(warnings) < MAX_ERROR_LINES:
                    warnings.append(ligne)

                faits.append(
                    FaitObservation(
                        type="warning",
                        source=str(log_path),
                        message=ligne,
                        timestamp=_timestamp(),
                        metadata={
                            "fichiers": fichiers,
                        },
                    )
                )

    return {
        "erreurs": erreurs,
        "warnings": warnings,
        "fichiers_concernes": fichiers_concernes,
        "logs_analyses": logs_analyses,
        "faits": faits,
    }


# ============================================================================
# OBSERVATION DU SYSTÈME
# ============================================================================

def observer_systeme() -> ObservationSysteme:
    """
    Retourne les informations système utiles au diagnostic.
    """

    try:
        repertoire = Path.cwd().resolve()
    except Exception:
        repertoire = Path.cwd()

    return ObservationSysteme(
        plateforme=platform.platform(),
        systeme=platform.system(),
        version_systeme=platform.version(),
        architecture=platform.machine(),
        python=platform.python_version(),
        executable_python=sys.executable,
        repertoire_projet=str(repertoire),
        pid=os.getpid(),
    )


# ============================================================================
# OBSERVATION DE LA SANTÉ
# ============================================================================

def observer_sante(
    erreurs: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
) -> EtatSante:
    """
    Calcule un état de santé basique à partir des faits observés.

    Important :
        Ce calcul est descriptif et simple.

    Le diagnostic réel sera effectué par diagnostiqueur.py.
    """

    erreurs = erreurs or []
    warnings = warnings or []

    nombre_erreurs = len(erreurs)
    nombre_warnings = len(warnings)

    # Aucun événement observé.
    if nombre_erreurs == 0 and nombre_warnings == 0:
        score = 100.0
        niveau = "BON"

    else:
        # Score volontairement conservateur.
        score = 100.0
        score -= min(nombre_erreurs * 10.0, 80.0)
        score -= min(nombre_warnings * 2.0, 20.0)

        score = max(0.0, min(100.0, score))

        if score >= 80:
            niveau = "BON"
        elif score >= 60:
            niveau = "MOYEN"
        elif score >= 40:
            niveau = "DEGRADE"
        else:
            niveau = "CRITIQUE"

    return EtatSante(
        score=score,
        niveau=niveau,
        erreurs=nombre_erreurs,
        warnings=nombre_warnings,
    )


# ============================================================================
# OBSERVATION GLOBALE
# ============================================================================

def observer() -> RapportObservation:
    """
    Effectue une observation complète de JIBI.

    Cette fonction est le point d'entrée principal.

    Elle ne :
        - modifie aucun fichier ;
        - ne génère aucun patch ;
        - n'exécute aucune correction ;
        - ne demande aucune autorisation.

    Elle collecte uniquement les faits.
    """

    debut = time.perf_counter()
    timestamp_debut = _timestamp()

    try:
        systeme = observer_systeme()

        logs = observer_logs()

        erreurs = logs["erreurs"]
        warnings = logs["warnings"]

        sante = observer_sante(
            erreurs=erreurs,
            warnings=warnings,
        )

        sante.fichiers_logs = len(
            logs["logs_analyses"]
        )

        rapport = RapportObservation(
            ok=True,
            timestamp_debut=timestamp_debut,
            timestamp_fin=_timestamp(),
            duree_ms=0.0,
            sante=sante,
            systeme=systeme,
            faits=logs["faits"],
            erreurs=erreurs,
            warnings=warnings,
            fichiers_concernes=logs[
                "fichiers_concernes"
            ],
            logs_analyses=logs[
                "logs_analyses"
            ],
            metadata={
                "version_observateur": "1.0",
                "mode": "observation_seule",
            },
        )

    except Exception as exc:
        logger.exception(
            "Erreur pendant l'observation JIBI"
        )

        systeme = observer_systeme()

        rapport = RapportObservation(
            ok=False,
            timestamp_debut=timestamp_debut,
            timestamp_fin=_timestamp(),
            duree_ms=0.0,
            sante=EtatSante(
                score=None,
                niveau="ERREUR_OBSERVATION",
            ),
            systeme=systeme,
            metadata={
                "version_observateur": "1.0",
                "mode": "observation_seule",
                "erreur": _safe_string(exc),
                "type_erreur": type(exc).__name__,
            },
        )

    duree = (
        time.perf_counter() - debut
    ) * 1000.0

    rapport.duree_ms = round(
        duree,
        3,
    )

    rapport.timestamp_fin = _timestamp()

    return rapport


# ============================================================================
# FONCTIONS DE COMPATIBILITÉ
# ============================================================================

def observer_erreurs() -> list[str]:
    """
    Retourne uniquement les erreurs observées.
    """

    resultat = observer_logs()

    return resultat["erreurs"]


def observer_warnings() -> list[str]:
    """
    Retourne uniquement les warnings observés.
    """

    resultat = observer_logs()

    return resultat["warnings"]


def fichiers_concernes() -> list[str]:
    """
    Retourne les fichiers Python mentionnés dans les logs.
    """

    resultat = observer_logs()

    return resultat[
        "fichiers_concernes"
    ]


# ============================================================================
# EXPORT / PERSISTANCE DU RAPPORT
# ============================================================================

def sauvegarder_observation(
    rapport: RapportObservation,
    destination: Optional[Path | str] = None,
) -> Optional[Path]:
    """
    Sauvegarde un rapport d'observation en JSON.

    Par défaut :
        workspace/jibi_lab/observations/

    Cette fonction écrit uniquement dans la zone de travail prévue
    pour les données d'auto-amélioration.

    Elle ne modifie jamais les fichiers Python de production.
    """

    try:
        if destination is None:
            destination = (
                WORKSPACE_DIR
                / "jibi_lab"
                / "observations"
                / (
                    "observation_"
                    + datetime.now().strftime(
                        "%Y%m%d_%H%M%S_%f"
                    )
                    + ".json"
                )
            )
        else:
            destination = Path(destination)

        destination = destination.resolve()

        observations_dir = (
            WORKSPACE_DIR
            / "jibi_lab"
            / "observations"
        ).resolve()

        observations_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Protection contre une destination située
        # hors de la zone d'observation.
        try:
            destination.relative_to(
                observations_dir
            )
        except ValueError:
            raise ValueError(
                "Destination d'observation "
                "hors de la zone autorisée."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        contenu = json.dumps(
            rapport.to_dict(),
            ensure_ascii=False,
            indent=2,
        )

        temporaire = destination.with_suffix(
            destination.suffix + ".tmp"
        )

        temporaire.write_text(
            contenu,
            encoding="utf-8",
        )

        os.replace(
            temporaire,
            destination,
        )

        return destination

    except Exception as exc:
        logger.exception(
            "Impossible de sauvegarder "
            "l'observation : %s",
            exc,
        )
        return None


# ============================================================================
# RÉSUMÉ HUMAIN
# ============================================================================

def resume_observation(
    rapport: RapportObservation,
) -> str:
    """
    Produit un résumé lisible par l'utilisateur.
    """

    score = rapport.sante.score

    if score is None:
        score_txt = "inconnu"
    else:
        score_txt = f"{score:.1f}/100"

    lignes = [
        "=== OBSERVATION JIBI ===",
        f"État : {rapport.sante.niveau}",
        f"Score : {score_txt}",
        f"Erreurs : {len(rapport.erreurs)}",
        f"Warnings : {len(rapport.warnings)}",
        (
            "Fichiers concernés : "
            f"{len(rapport.fichiers_concernes)}"
        ),
        (
            "Logs analysés : "
            f"{len(rapport.logs_analyses)}"
        ),
        f"Durée : {rapport.duree_ms:.3f} ms",
    ]

    if rapport.fichiers_concernes:
        lignes.append("")
        lignes.append(
            "Fichiers détectés :"
        )

        for fichier in rapport.fichiers_concernes[:20]:
            lignes.append(
                f"  - {fichier}"
            )

    if rapport.erreurs:
        lignes.append("")
        lignes.append(
            "Dernières erreurs observées :"
        )

        for erreur in rapport.erreurs[-10:]:
            lignes.append(
                f"  - {erreur}"
            )

    return "\n".join(lignes)


# ============================================================================
# API PUBLIQUE
# ============================================================================

__all__ = [
    "FaitObservation",
    "EtatSante",
    "ObservationSysteme",
    "RapportObservation",
    "observer",
    "observer_logs",
    "observer_systeme",
    "observer_sante",
    "observer_erreurs",
    "observer_warnings",
    "fichiers_concernes",
    "sauvegarder_observation",
    "resume_observation",
]


# ============================================================================
# TEST DIRECT
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s"
        ),
    )

    rapport = observer()

    print(
        resume_observation(rapport)
    )

    print("\n--- JSON ---")

    print(
        json.dumps(
            rapport.to_dict(),
            ensure_ascii=False,
            indent=2,
        )
    )