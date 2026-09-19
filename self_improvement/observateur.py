# -*- coding: utf-8 -*-
"""
JIBI - Observateur v3
=====================

Collecte uniquement des faits concernant JIBI.

IMPORTANT :
    - aucune modification du code de production ;
    - aucune décision de réparation ;
    - aucune interprétation causale ;
    - aucune exécution de code observé.

L'observateur collecte :
    - les erreurs ;
    - les warnings ;
    - les fichiers mentionnés dans les logs ;
    - l'état système ;
    - un état de santé synthétique ;
    - les patterns récurrents ;
    - les observations persistées dans workspace/jibi_lab/observations.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sys
import tempfile
import time

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

try:
    from core.config import (
        JIBI_PROJET_DIR,
        LOGS_DIR,
        WORKSPACE_DIR,
    )

    PROJECT_ROOT = Path(
        JIBI_PROJET_DIR
    ).resolve()

except Exception:
    PROJECT_ROOT = Path(
        __file__
    ).resolve().parents[1]

    LOGS_DIR = PROJECT_ROOT / "logs"
    WORKSPACE_DIR = PROJECT_ROOT / "workspace"


PROJECT_ROOT = Path(
    PROJECT_ROOT
).resolve()

LOGS_DIR = Path(
    LOGS_DIR
).resolve()

WORKSPACE_DIR = Path(
    WORKSPACE_DIR
).resolve()

OBSERVATIONS_DIR = (
    WORKSPACE_DIR
    / "jibi_lab"
    / "observations"
).resolve()


# ---------------------------------------------------------------------------
# LIMITES
# ---------------------------------------------------------------------------

MAX_LOG_FILES = 10
MAX_LOG_LINES = 5000
MAX_ERROR_LINES = 500
MAX_WARNING_LINES = 500
MAX_FAITS = 2000
MAX_FICHIERS_CONCERNES = 500
MAX_PATTERNS_RECURRENT = 100


# ---------------------------------------------------------------------------
# PATTERNS
# ---------------------------------------------------------------------------

_ERROR_PATTERNS = (
    re.compile(
        r"\bTraceback \(most recent call last\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bERROR\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bCRITICAL\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bException\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bError\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bFailed\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bFailure\b",
        re.IGNORECASE,
    ),
)

_WARNING_PATTERNS = (
    re.compile(
        r"\bWARNING\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bWARN\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bWarning\b",
        re.IGNORECASE,
    ),
)

_FILE_PATTERNS = (
    re.compile(
        r'([A-Za-z]:[\\/][^\s:"<>|]+\.py)',
        re.IGNORECASE,
    ),
    re.compile(
        r'(/[^\s:]+\.py)',
        re.IGNORECASE,
    ),
    re.compile(
        r'((?:core|self_improvement|tools|updater)'
        r'[\\/][^\s:]+\.py)',
        re.IGNORECASE,
    ),
)


# ---------------------------------------------------------------------------
# OUTILS
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    """Retourne un timestamp UTC ISO-8601."""
    return datetime.now(
        timezone.utc
    ).isoformat()


def _est_dans(
    chemin: Path,
    racine: Path,
) -> bool:
    """Vérifie qu'un chemin est contenu dans une racine."""
    try:
        chemin.resolve().relative_to(
            racine.resolve()
        )
        return True

    except ValueError:
        return False


def _est_symlink(
    chemin: Path,
) -> bool:
    """Détecte un lien symbolique sans le suivre."""
    try:
        return chemin.is_symlink()

    except OSError:
        return True


def _normaliser_chemin(
    chemin: str,
) -> str:
    """
    Normalise un chemin détecté dans un log.

    Objectif :
        transformer les chemins absolus appartenant au projet
        en chemins relatifs stables.

    Exemple :
        C:\\Projet\\core\\agent_core.py
        ->
        core/agent_core.py

    Les chemins externes restent inchangés.
    """

    valeur = str(chemin).strip()

    if not valeur:
        return valeur

    try:
        path = Path(valeur)

        if not path.is_absolute():
            path = Path(
                valeur.replace("\\", "/")
            )

            # Tentative de résolution depuis le projet.
            candidat = (
                PROJECT_ROOT / path
            ).resolve()

            if _est_dans(
                candidat,
                PROJECT_ROOT,
            ):
                path = candidat

        else:
            path = path.resolve()

        if _est_dans(
            path,
            PROJECT_ROOT,
        ):
            relatif = path.relative_to(
                PROJECT_ROOT
            )

            return relatif.as_posix()

    except (
        OSError,
        ValueError,
    ):
        pass

    return valeur.replace(
        "\\",
        "/",
    )


def _normaliser_fichiers(
    fichiers: list[str],
) -> list[str]:
    """Normalise et déduplique une liste de chemins."""

    resultat: list[str] = []
    vus: set[str] = set()

    for fichier in fichiers:

        normalise = _normaliser_chemin(
            fichier
        )

        if not normalise:
            continue

        cle = normalise.casefold()

        if cle in vus:
            continue

        vus.add(cle)
        resultat.append(normalise)

        if len(resultat) >= MAX_FICHIERS_CONCERNES:
            break

    return resultat


def _nettoyer_message(
    message: str,
) -> str:
    """
    Réduit les variations évidentes des messages
    pour permettre une détection simple de récurrence.

    Les timestamps et chemins absolus sont neutralisés.
    """

    texte = str(message).strip()

    texte = re.sub(
        r"\d{4}-\d{2}-\d{2}"
        r"[T ]\d{2}:\d{2}:\d{2}"
        r"(?:[.,]\d+)?",
        "<TIMESTAMP>",
        texte,
    )

    texte = re.sub(
        r"\b\d+\b",
        "<N>",
        texte,
    )

    texte = re.sub(
        r"[A-Za-z]:[\\/][^\s]+",
        "<PATH>",
        texte,
    )

    texte = re.sub(
        r"/(?:[^/\s]+/)+[^/\s]+",
        "<PATH>",
        texte,
    )

    texte = re.sub(
        r"\s+",
        " ",
        texte,
    )

    return texte.strip()


def _extraire_patterns_recurrents(
    lignes: list[str],
) -> list[dict[str, Any]]:
    """
    Détecte les messages qui reviennent plusieurs fois.

    Ce calcul est descriptif uniquement.
    Il ne constitue pas un diagnostic causal.
    """

    compte = Counter()

    exemples: dict[str, str] = {}

    for ligne in lignes:

        message = _nettoyer_message(
            ligne
        )

        if not message:
            continue

        compte[message] += 1

        if message not in exemples:
            exemples[message] = ligne

    resultats: list[dict[str, Any]] = []

    for pattern, occurrences in compte.most_common():

        if occurrences < 2:
            continue

        resultats.append(
            {
                "pattern": pattern,
                "occurrences": occurrences,
                "exemple": exemples.get(
                    pattern,
                    "",
                ),
            }
        )

        if len(resultats) >= MAX_PATTERNS_RECURRENT:
            break

    return resultats


# ---------------------------------------------------------------------------
# STRUCTURES DE DONNÉES
# ---------------------------------------------------------------------------

@dataclass
class FaitObservation:
    """Fait brut collecté par l'observateur."""

    type: str
    source: str
    message: str
    timestamp: str
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EtatSante:
    """
    État synthétique calculé à partir des faits observés.

    IMPORTANT :
        score et niveau sont des métriques dérivées.
        Ils ne constituent pas une cause ni un diagnostic.
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
    """Informations factuelles sur l'environnement JIBI."""

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
    """Rapport complet d'une observation."""

    ok: bool
    timestamp_debut: str
    timestamp_fin: str
    duree_ms: float
    sante: EtatSante
    systeme: ObservationSysteme

    faits: list[FaitObservation] = field(
        default_factory=list
    )

    erreurs: list[str] = field(
        default_factory=list
    )

    warnings: list[str] = field(
        default_factory=list
    )

    fichiers_concernes: list[str] = field(
        default_factory=list
    )

    logs_analyses: list[str] = field(
        default_factory=list
    )

    patterns_recurrents: list[dict[str, Any]] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "timestamp_debut": self.timestamp_debut,
            "timestamp_fin": self.timestamp_fin,
            "duree_ms": self.duree_ms,
            "sante": self.sante.to_dict(),
            "systeme": self.systeme.to_dict(),
            "faits": [
                fait.to_dict()
                for fait in self.faits
            ],
            "erreurs": self.erreurs,
            "warnings": self.warnings,
            "fichiers_concernes": self.fichiers_concernes,
            "logs_analyses": self.logs_analyses,
            "patterns_recurrents": self.patterns_recurrents,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# LECTURE DES LOGS
# ---------------------------------------------------------------------------

def _lire_log(
    path: Path,
) -> list[str]:
    """Lit les dernières lignes d'un fichier de log."""

    try:
        if not path.exists():
            return []

        if not path.is_file():
            return []

        if _est_symlink(path):
            return []

        if not _est_dans(
            path,
            LOGS_DIR,
        ):
            return []

        lignes = path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        ).splitlines()

        return lignes[
            -MAX_LOG_LINES:
        ]

    except (
        OSError,
        UnicodeError,
    ):
        return []


def _lister_logs() -> list[Path]:
    """Retourne les logs récents à analyser."""

    try:
        if not LOGS_DIR.exists():
            return []

        if not LOGS_DIR.is_dir():
            return []

        fichiers: list[Path] = []

        for path in LOGS_DIR.rglob("*"):

            try:
                if not path.is_file():
                    continue

                if _est_symlink(path):
                    continue

                if path.suffix.lower() not in {
                    ".log",
                    ".txt",
                }:
                    continue

                if not _est_dans(
                    path,
                    LOGS_DIR,
                ):
                    continue

                fichiers.append(path)

            except OSError:
                continue

        def _mtime(
            fichier: Path,
        ) -> float:

            try:
                return fichier.stat().st_mtime

            except OSError:
                return 0.0

        fichiers.sort(
            key=_mtime,
            reverse=True,
        )

        return fichiers[
            :MAX_LOG_FILES
        ]

    except OSError:
        return []


# ---------------------------------------------------------------------------
# EXTRACTION
# ---------------------------------------------------------------------------

def _extraire_fichiers(
    ligne: str,
) -> list[str]:
    """Extrait les chemins Python présents dans une ligne."""

    resultat: list[str] = []

    for pattern in _FILE_PATTERNS:

        try:
            correspondances = pattern.findall(
                ligne
            )

        except re.error:
            continue

        for match in correspondances:

            if isinstance(
                match,
                tuple,
            ):
                valeurs = match
            else:
                valeurs = (
                    match,
                )

            for valeur in valeurs:

                if not valeur:
                    continue

                valeur = _normaliser_chemin(
                    valeur
                )

                if valeur not in resultat:
                    resultat.append(
                        valeur
                    )

    return resultat


# ---------------------------------------------------------------------------
# OBSERVATION DES LOGS
# ---------------------------------------------------------------------------

def observer_logs() -> dict[str, Any]:
    """
    Observe les logs et retourne uniquement des faits.

    Aucune tentative de détermination de cause.
    """

    erreurs: list[str] = []
    warnings: list[str] = []
    fichiers_concernes: list[str] = []
    logs_analyses: list[str] = []
    faits: list[FaitObservation] = []

    lignes_evenements: list[str] = []

    for path in _lister_logs():

        lignes = _lire_log(
            path
        )

        if not lignes:
            continue

        logs_analyses.append(
            str(path)
        )

        for ligne in lignes:

            ligne = ligne.strip()

            if not ligne:
                continue

            fichiers = _extraire_fichiers(
                ligne
            )

            for fichier in fichiers:

                if (
                    fichier
                    not in fichiers_concernes
                    and len(fichiers_concernes)
                    < MAX_FICHIERS_CONCERNES
                ):
                    fichiers_concernes.append(
                        fichier
                    )

            est_erreur = any(
                pattern.search(ligne)
                for pattern in _ERROR_PATTERNS
            )

            est_warning = any(
                pattern.search(ligne)
                for pattern in _WARNING_PATTERNS
            )

            if est_erreur:

                if len(erreurs) < MAX_ERROR_LINES:
                    erreurs.append(
                        ligne
                    )

                if len(faits) < MAX_FAITS:
                    faits.append(
                        FaitObservation(
                            type="error",
                            source=str(path),
                            message=ligne,
                            timestamp=_timestamp(),
                            metadata={
                                "fichiers": fichiers,
                            },
                        )
                    )

                lignes_evenements.append(
                    ligne
                )

            elif est_warning:

                if len(warnings) < MAX_WARNING_LINES:
                    warnings.append(
                        ligne
                    )

                if len(faits) < MAX_FAITS:
                    faits.append(
                        FaitObservation(
                            type="warning",
                            source=str(path),
                            message=ligne,
                            timestamp=_timestamp(),
                            metadata={
                                "fichiers": fichiers,
                            },
                        )
                    )

                lignes_evenements.append(
                    ligne
                )

    patterns_recurrents = (
        _extraire_patterns_recurrents(
            lignes_evenements
        )
    )

    return {
        "erreurs": erreurs,
        "warnings": warnings,
        "fichiers_concernes": (
            _normaliser_fichiers(
                fichiers_concernes
            )
        ),
        "logs_analyses": logs_analyses,
        "faits": faits,
        "patterns_recurrents": patterns_recurrents,
    }


# ---------------------------------------------------------------------------
# OBSERVATION SYSTÈME
# ---------------------------------------------------------------------------

def observer_systeme() -> ObservationSysteme:
    """Collecte les informations factuelles du système."""

    return ObservationSysteme(
        plateforme=platform.platform(),
        systeme=platform.system(),
        version_systeme=platform.version(),
        architecture=platform.machine(),
        python=platform.python_version(),
        executable_python=sys.executable,
        repertoire_projet=str(
            PROJECT_ROOT
        ),
        pid=os.getpid(),
    )


# ---------------------------------------------------------------------------
# SANTÉ
# ---------------------------------------------------------------------------

def observer_sante(
    erreurs: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
) -> EtatSante:
    """
    Calcule une métrique synthétique.

    Ce score n'est pas un diagnostic causal.
    """

    erreurs = erreurs or []
    warnings = warnings or []

    nombre_erreurs = len(
        erreurs
    )

    nombre_warnings = len(
        warnings
    )

    score = 100.0

    score -= min(
        nombre_erreurs * 10.0,
        80.0,
    )

    score -= min(
        nombre_warnings * 2.0,
        20.0,
    )

    score = max(
        0.0,
        min(
            100.0,
            score,
        ),
    )

    if (
        nombre_erreurs == 0
        and nombre_warnings == 0
    ):
        niveau = "BON"

    elif score >= 80:
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


# ---------------------------------------------------------------------------
# OBSERVATION PRINCIPALE
# ---------------------------------------------------------------------------

def observer() -> RapportObservation:
    """Effectue une observation complète de JIBI."""

    debut = time.perf_counter()

    timestamp_debut = _timestamp()

    try:
        systeme = observer_systeme()

        logs = observer_logs()

        sante = observer_sante(
            logs["erreurs"],
            logs["warnings"],
        )

        sante.fichiers_logs = len(
            logs["logs_analyses"]
        )

        sante.patterns_recurrents = len(
            logs.get(
                "patterns_recurrents",
                [],
            )
        )

        rapport = RapportObservation(
            ok=True,
            timestamp_debut=timestamp_debut,
            timestamp_fin=_timestamp(),
            duree_ms=0.0,
            sante=sante,
            systeme=systeme,
            faits=logs["faits"],
            erreurs=logs["erreurs"],
            warnings=logs["warnings"],
            fichiers_concernes=logs[
                "fichiers_concernes"
            ],
            logs_analyses=logs[
                "logs_analyses"
            ],
            patterns_recurrents=logs.get(
                "patterns_recurrents",
                [],
            ),
            metadata={
                "version": "3.0",
                "mode": "observation_seule",
                "production_modifiee": False,
                "interpretation_causale": False,
            },
        )

    except Exception as exc:

        logger.exception(
            "Erreur observation JIBI"
        )

        try:
            systeme = observer_systeme()

        except Exception:

            systeme = ObservationSysteme(
                plateforme="inconnue",
                systeme="inconnu",
                version_systeme="inconnue",
                architecture="inconnue",
                python=sys.version.split()[0],
                executable_python=sys.executable,
                repertoire_projet=str(
                    PROJECT_ROOT
                ),
                pid=os.getpid(),
            )

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
                "version": "3.0",
                "mode": "observation_seule",
                "production_modifiee": False,
                "interpretation_causale": False,
                "erreur": str(exc),
                "type_erreur": type(exc).__name__,
            },
        )

    rapport.duree_ms = round(
        (
            time.perf_counter()
            - debut
        )
        * 1000,
        3,
    )

    rapport.timestamp_fin = _timestamp()

    return rapport


# ---------------------------------------------------------------------------
# RACCOURCIS
# ---------------------------------------------------------------------------

def observer_erreurs() -> list[str]:
    """Retourne les erreurs actuellement observées."""

    return observer_logs()[
        "erreurs"
    ]


def observer_warnings() -> list[str]:
    """Retourne les warnings actuellement observés."""

    return observer_logs()[
        "warnings"
    ]


def fichiers_concernes() -> list[str]:
    """Retourne les fichiers mentionnés dans les logs."""

    return observer_logs()[
        "fichiers_concernes"
    ]


# ---------------------------------------------------------------------------
# PERSISTANCE DES OBSERVATIONS
# ---------------------------------------------------------------------------

def sauvegarder_observation(
    rapport: RapportObservation,
    destination: Optional[Path | str] = None,
) -> Optional[Path]:
    """
    Sauvegarde un rapport dans la zone dédiée.

    Aucun fichier de production n'est modifié.
    """

    tmp: Optional[Path] = None

    try:
        OBSERVATIONS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        base = OBSERVATIONS_DIR.resolve()

        if destination is None:

            destination = (
                base
                / (
                    "observation_"
                    + datetime.now().strftime(
                        "%Y%m%d_%H%M%S_%f"
                    )
                    + ".json"
                )
            )

        destination = Path(
            destination
        )

        if (
            destination.exists()
            and destination.is_symlink()
        ):
            raise PermissionError(
                "Destination symbolique interdite."
            )

        destination = destination.resolve()

        if not _est_dans(
            destination,
            base,
        ):
            raise ValueError(
                "Destination hors zone observations."
            )

        if (
            destination.exists()
            and not destination.is_file()
        ):
            raise ValueError(
                "Destination invalide."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fd, temp_name = tempfile.mkstemp(
            prefix=".jibi_observation_",
            suffix=".tmp",
            dir=str(destination.parent),
        )

        os.close(fd)

        tmp = Path(
            temp_name
        )

        contenu = json.dumps(
            rapport.to_dict(),
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        tmp.write_text(
            contenu,
            encoding="utf-8",
        )

        os.replace(
            tmp,
            destination,
        )

        tmp = None

        return destination

    except Exception as exc:

        logger.exception(
            "Sauvegarde observation impossible: %s",
            exc,
        )

        if tmp is not None:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

        return None


# ---------------------------------------------------------------------------
# RÉSUMÉ
# ---------------------------------------------------------------------------

def resume_observation(
    rapport: RapportObservation,
) -> str:
    """Produit un résumé lisible du rapport."""

    score = (
        "inconnu"
        if rapport.sante.score is None
        else f"{rapport.sante.score:.1f}/100"
    )

    lignes = [
        "=== OBSERVATION JIBI ===",
        f"État : {rapport.sante.niveau}",
        f"Score : {score}",
        f"Erreurs : {len(rapport.erreurs)}",
        f"Warnings : {len(rapport.warnings)}",
        (
            "Patterns récurrents : "
            f"{len(rapport.patterns_recurrents)}"
        ),
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

        lignes.extend(
            [
                "",
                "Fichiers détectés :",
            ]
        )

        for fichier in rapport.fichiers_concernes[:20]:

            lignes.append(
                f"  - {fichier}"
            )

    if rapport.patterns_recurrents:

        lignes.extend(
            [
                "",
                "Patterns récurrents :",
            ]
        )

        for pattern in rapport.patterns_recurrents[:10]:

            lignes.append(
                "  - "
                f"{pattern['occurrences']}x : "
                f"{pattern['pattern']}"
            )

    if rapport.erreurs:

        lignes.extend(
            [
                "",
                "Erreurs :",
            ]
        )

        for erreur in rapport.erreurs[-10:]:

            lignes.append(
                f"  - {erreur}"
            )

    return "\n".join(
        lignes
    )


# ---------------------------------------------------------------------------
# API PUBLIQUE
# ---------------------------------------------------------------------------

__all__ = [
    "PROJECT_ROOT",
    "LOGS_DIR",
    "WORKSPACE_DIR",
    "OBSERVATIONS_DIR",
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


# ---------------------------------------------------------------------------
# TEST DIRECT
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    rapport = observer()

    print(
        resume_observation(
            rapport
        )
    )

    print(
        json.dumps(
            rapport.to_dict(),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )