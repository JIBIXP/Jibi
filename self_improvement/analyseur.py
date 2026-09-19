# -*- coding: utf-8 -*-
"""
JIBI - Analyseur de santé
=========================

Analyse les logs et produit un état de santé de JIBI.

Ce module :
    - lit les logs ;
    - détecte erreurs et warnings ;
    - détecte les problèmes critiques ;
    - détecte les patterns récurrents ;
    - calcule un score de santé ;
    - produit des résumés.

La modification du code de production ne relève PAS de ce module.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from core.config import (
        LIMITE_LOGS_ANALYSE,
        LOGS_DIR,
        SEUIL_PATTERN_RECURRENT,
        WORKSPACE_DIR,
    )

    LOG_DIR = Path(LOGS_DIR)
    HISTORIQUE_DIR = (
        Path(WORKSPACE_DIR)
        / "jibi_lab"
        / "historique"
    )

    SEUIL_DEFAUT = int(
        SEUIL_PATTERN_RECURRENT
    )
    LIMITE_DEFAUT = int(
        LIMITE_LOGS_ANALYSE
    )

except Exception:
    PROJECT_ROOT = (
        Path(__file__).resolve().parent.parent
    )

    LOG_DIR = PROJECT_ROOT / "logs"
    HISTORIQUE_DIR = (
        PROJECT_ROOT
        / "workspace"
        / "jibi_lab"
        / "historique"
    )

    SEUIL_DEFAUT = 3
    LIMITE_DEFAUT = 1000


# ---------------------------------------------------------------------------
# Motifs
# ---------------------------------------------------------------------------

MOTIFS_ERREURS = [
    r"\berror\b",
    r"\bexception\b",
    r"\btraceback\b",
    r"\bfailed\b",
    r"\bfailure\b",
    r"\béchec\b",
    r"\berreur\b",
    r"\bfatal\b",
    r"\bcritical\b",
]

MOTIFS_WARNINGS = [
    r"\bwarning\b",
    r"\bavertissement\b",
    r"\bdeprecated\b",
    r"\bobsolete\b",
]

MOTIFS_CRITIQUES = [
    r"\bpermission\s*denied\b",
    r"\baccess\s*denied\b",
    r"\bout\s*of\s*memory\b",
    r"\bdisk\s*full\b",
    r"\bsegfault\b",
    r"\bcorrupt",
    r"\blost\s*connection\b",
]


RE_ERREURS = [
    re.compile(motif, re.IGNORECASE)
    for motif in MOTIFS_ERREURS
]

RE_WARNINGS = [
    re.compile(motif, re.IGNORECASE)
    for motif in MOTIFS_WARNINGS
]

RE_CRITIQUES = [
    re.compile(motif, re.IGNORECASE)
    for motif in MOTIFS_CRITIQUES
]

RE_TIMESTAMP = re.compile(
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"
)

RE_PID = re.compile(
    r"PID\s*\d+",
    re.IGNORECASE,
)

RE_HEX = re.compile(
    r"0x[0-9a-fA-F]+"
)

RE_IP = re.compile(
    r"\d+\.\d+\.\d+\.\d+"
)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

CACHE_TTL = 60.0

_cache: dict[str, Any] = {
    "t": 0.0,
    "key": None,
    "val": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _limiter(
    valeur: Any,
    minimum: int,
    maximum: int,
    defaut: int,
) -> int:
    try:
        valeur = int(valeur)
    except (TypeError, ValueError):
        return defaut

    return max(
        minimum,
        min(maximum, valeur),
    )


def _est_critique(
    ligne: str,
) -> bool:
    """Détermine si une ligne contient un motif critique."""

    return any(
        regex.search(ligne)
        for regex in RE_CRITIQUES
    )


def _normaliser_message(
    texte: str,
) -> str:
    """Normalise un message pour détecter les répétitions."""

    texte = RE_TIMESTAMP.sub(
        "",
        texte,
    )

    texte = RE_PID.sub(
        "PID XXX",
        texte,
    )

    texte = RE_HEX.sub(
        "0xXXX",
        texte,
    )

    texte = RE_IP.sub(
        "IP",
        texte,
    )

    return texte.strip()


# ---------------------------------------------------------------------------
# Lecture des logs
# ---------------------------------------------------------------------------

def lire_logs(
    limite: int = LIMITE_DEFAUT,
    depuis_heures: float | None = None,
) -> str:
    """
    Lit les derniers logs utiles.

    La quantité de données est volontairement limitée.
    """

    t0 = time.perf_counter()

    limite = _limiter(
        limite,
        minimum=1,
        maximum=10000,
        defaut=LIMITE_DEFAUT,
    )

    if depuis_heures is not None:
        try:
            depuis_heures = float(
                depuis_heures
            )
        except (TypeError, ValueError):
            depuis_heures = None

        if (
            depuis_heures is not None
            and depuis_heures < 0
        ):
            depuis_heures = None

    if not LOG_DIR.exists():
        return ""

    try:
        fichiers = sorted(
            LOG_DIR.glob("*.log"),
            key=lambda fichier: fichier.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ""

    if not fichiers:
        return ""

    seuil: datetime | None = None

    if depuis_heures is not None:
        seuil = (
            datetime.now()
            - timedelta(
                hours=depuis_heures
            )
        )

        fichiers_filtrés = []

        for fichier in fichiers:
            try:
                date_modification = datetime.fromtimestamp(
                    fichier.stat().st_mtime
                )
            except OSError:
                continue

            if date_modification >= seuil:
                fichiers_filtrés.append(
                    fichier
                )

        fichiers = fichiers_filtrés

    lignes: list[str] = []

    # Limite volontaire du nombre de fichiers analysés.
    for fichier in fichiers[:5]:

        try:
            with fichier.open(
                "r",
                encoding="utf-8",
                errors="replace",
            ) as handle:

                # Lecture bornée.
                contenu = handle.read()

        except (OSError, UnicodeError):
            continue

        lignes.extend(
            contenu.splitlines()[-2000:]
        )

    if seuil is not None:

        lignes_filtrees: list[str] = []

        for ligne in lignes:

            match = RE_TIMESTAMP.search(
                ligne
            )

            if not match:
                lignes_filtrees.append(
                    ligne
                )
                continue

            try:
                timestamp = datetime.strptime(
                    match.group(1),
                    "%Y-%m-%d %H:%M:%S",
                )

                if timestamp >= seuil:
                    lignes_filtrees.append(
                        ligne
                    )

            except ValueError:
                lignes_filtrees.append(
                    ligne
                )

        lignes = lignes_filtrees

    resultat = "\n".join(
        lignes[-limite:]
    )

    _ = time.perf_counter() - t0

    return resultat


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extraire_erreurs(
    texte: str,
) -> list[dict[str, Any]]:
    """Extrait les lignes contenant des erreurs."""

    if not texte:
        return []

    erreurs: list[dict[str, Any]] = []

    for ligne in texte.splitlines():

        ligne = ligne.strip()

        if not ligne:
            continue

        ligne_lower = ligne.lower()

        if any(
            regex.search(ligne_lower)
            for regex in RE_ERREURS
        ):
            erreurs.append(
                {
                    "texte": ligne,
                    "type": "erreur",
                    "critique": _est_critique(
                        ligne_lower
                    ),
                }
            )

    return erreurs


def extraire_warnings(
    texte: str,
) -> list[dict[str, Any]]:
    """Extrait les lignes contenant des warnings."""

    if not texte:
        return []

    warnings: list[dict[str, Any]] = []

    for ligne in texte.splitlines():

        ligne = ligne.strip()

        if not ligne:
            continue

        ligne_lower = ligne.lower()

        if any(
            regex.search(ligne_lower)
            for regex in RE_WARNINGS
        ):
            warnings.append(
                {
                    "texte": ligne,
                    "type": "warning",
                    "critique": False,
                }
            )

    return warnings


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def compter_types_erreurs(
    erreurs: list[dict[str, Any]],
) -> dict[str, int]:
    """Classe les erreurs par catégorie."""

    resultats = {
        "critique": 0,
        "exception": 0,
        "traceback": 0,
        "erreur": 0,
        "warning": 0,
        "autres": 0,
    }

    for erreur in erreurs:

        texte = str(
            erreur.get(
                "texte",
                "",
            )
        ).lower()

        type_erreur = erreur.get(
            "type",
            "erreur",
        )

        if erreur.get("critique"):
            resultats["critique"] += 1

        elif "exception" in texte:
            resultats["exception"] += 1

        elif "traceback" in texte:
            resultats["traceback"] += 1

        elif type_erreur == "warning":
            resultats["warning"] += 1

        elif (
            "error" in texte
            or "erreur" in texte
        ):
            resultats["erreur"] += 1

        else:
            resultats["autres"] += 1

    return resultats


# ---------------------------------------------------------------------------
# Patterns récurrents
# ---------------------------------------------------------------------------

def detecter_patterns_recurrents(
    erreurs: list[dict[str, Any]],
    seuil: int = SEUIL_DEFAUT,
) -> list[dict[str, Any]]:
    """Détecte les erreurs répétées."""

    if not erreurs:
        return []

    seuil = _limiter(
        seuil,
        minimum=1,
        maximum=1000,
        defaut=SEUIL_DEFAUT,
    )

    messages: list[str] = []

    for erreur in erreurs:

        texte = str(
            erreur.get(
                "texte",
                "",
            )
        )

        texte = _normaliser_message(
            texte
        )

        if texte:
            messages.append(
                texte
            )

    compteur = Counter(messages)

    return [
        {
            "message": message,
            "frequence": frequence,
        }
        for message, frequence
        in compteur.most_common(20)
        if frequence >= seuil
    ]


# ---------------------------------------------------------------------------
# Santé
# ---------------------------------------------------------------------------

def calculer_score_sante(
    analyse: dict[str, Any],
) -> int:
    """Calcule un score de santé de 0 à 100."""

    types = analyse.get(
        "types",
        {},
    )

    score = 100

    score -= (
        types.get("critique", 0)
        * 25
    )

    score -= (
        types.get("exception", 0)
        * 10
    )

    score -= (
        types.get("traceback", 0)
        * 8
    )

    score -= (
        types.get("erreur", 0)
        * 3
    )

    score -= (
        types.get("warning", 0)
        * 1
    )

    nombre_erreurs = int(
        analyse.get(
            "nombre_erreurs",
            0,
        )
        or 0
    )

    if nombre_erreurs > 50:
        score -= 15

    elif nombre_erreurs > 20:
        score -= 5

    return max(
        0,
        min(100, score),
    )


def obtenir_niveau_sante(
    score: int,
) -> str:
    """Convertit le score en niveau lisible."""

    score = max(
        0,
        min(100, int(score)),
    )

    if score >= 90:
        return "🟢 Excellent"

    if score >= 70:
        return "🟡 Bon"

    if score >= 50:
        return "🟠 Moyen"

    if score >= 25:
        return "🔴 Mauvais"

    return "💀 Critique"


# ---------------------------------------------------------------------------
# Analyse principale
# ---------------------------------------------------------------------------

def analyser_logs(
    depuis_heures: float | None = None,
    limite: int = LIMITE_DEFAUT,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Analyse les logs et retourne l'état de santé."""

    limite = _limiter(
        limite,
        minimum=1,
        maximum=10000,
        defaut=LIMITE_DEFAUT,
    )

    key = (
        depuis_heures,
        limite,
    )

    maintenant = time.time()

    if (
        use_cache
        and _cache["key"] == key
        and maintenant - _cache["t"]
        < CACHE_TTL
    ):
        return _cache["val"]

    t0 = time.perf_counter()

    logs = lire_logs(
        limite=limite,
        depuis_heures=depuis_heures,
    )

    erreurs = extraire_erreurs(
        logs
    )

    warnings = extraire_warnings(
        logs
    )

    toutes = (
        erreurs
        + warnings
    )

    types = compter_types_erreurs(
        toutes
    )

    patterns = detecter_patterns_recurrents(
        erreurs
    )

    analyse: dict[str, Any] = {
        "date": datetime.now().isoformat(),
        "logs_lignes": (
            len(logs.splitlines())
            if logs
            else 0
        ),
        "nombre_erreurs": len(
            erreurs
        ),
        "nombre_warnings": len(
            warnings
        ),
        "erreurs": [
            erreur["texte"]
            for erreur in erreurs[:50]
        ],
        "erreurs_critiques": [
            erreur["texte"]
            for erreur in erreurs
            if erreur.get("critique")
        ][:10],
        "types": types,
        "patterns_recurrents": patterns,
    }

    analyse["score_sante"] = (
        calculer_score_sante(
            analyse
        )
    )

    analyse["niveau_sante"] = (
        obtenir_niveau_sante(
            analyse["score_sante"]
        )
    )

    analyse["duree"] = round(
        time.perf_counter() - t0,
        4,
    )

    _cache.update(
        t=time.time(),
        key=key,
        val=analyse,
    )

    return analyse


# ---------------------------------------------------------------------------
# Résumé
# ---------------------------------------------------------------------------

def obtenir_resume(
    depuis_heures: float | None = None,
) -> str:
    """Produit un résumé lisible de la santé."""

    analyse = analyser_logs(
        depuis_heures=depuis_heures
    )

    lignes = [
        (
            f"🩺 Santé JIBI : "
            f"{analyse['niveau_sante']} "
            f"({analyse['score_sante']}/100) "
            f"[{analyse.get('duree', 0)}s]"
        ),
        (
            f"   Erreurs : "
            f"{analyse['nombre_erreurs']}"
        ),
        (
            f"   Warnings : "
            f"{analyse['nombre_warnings']}"
        ),
    ]

    if analyse["erreurs_critiques"]:
        lignes.append(
            "   🔴 Critiques : "
            f"{len(analyse['erreurs_critiques'])}"
        )

    if analyse["patterns_recurrents"]:
        lignes.append(
            "   Patterns récurrents :"
        )

        for pattern in analyse[
            "patterns_recurrents"
        ][:5]:
            lignes.append(
                "     • "
                f"[{pattern['frequence']}x] "
                f"{pattern['message'][:80]}"
            )

    return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Persistance de l'analyse
# ---------------------------------------------------------------------------

def sauvegarder_analyse(
    analyse: dict[str, Any] | None = None,
) -> str | None:
    """
    Sauvegarde une copie de l'analyse.

    Cette fonction ne modifie aucun fichier de production.
    Elle écrit uniquement dans l'historique prévu.
    """

    if analyse is None:
        analyse = analyser_logs()

    try:
        HISTORIQUE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError:
        return None

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    fichier = (
        HISTORIQUE_DIR
        / f"analyse_{timestamp}.json"
    )

    try:
        analyse_copy = dict(
            analyse
        )

        analyse_copy.pop(
            "erreurs",
            None,
        )

        analyse_copy[
            "nombre_erreurs_total"
        ] = analyse.get(
            "nombre_erreurs",
            0,
        )

        fichier.write_text(
            json.dumps(
                analyse_copy,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return str(fichier)

    except (
        OSError,
        TypeError,
        ValueError,
    ):
        return None


__all__ = [
    "MOTIFS_ERREURS",
    "MOTIFS_WARNINGS",
    "MOTIFS_CRITIQUES",
    "lire_logs",
    "extraire_erreurs",
    "extraire_warnings",
    "compter_types_erreurs",
    "detecter_patterns_recurrents",
    "calculer_score_sante",
    "obtenir_niveau_sante",
    "analyser_logs",
    "obtenir_resume",
    "sauvegarder_analyse",
]