# -*- coding: utf-8 -*-
"""
JIBI - Mémoire d'auto-amélioration
==================================

Mémoire d'audit des observations, diagnostics,
patchs, validations, applications et rollbacks.

Format :
    JSONL

Une ligne = un événement.

IMPORTANT :
    Cette mémoire est une mémoire d'audit.
    Elle ne donne jamais automatiquement
    l'autorisation de modifier JIBI.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


try:
    from core.config import WORKSPACE_DIR
except Exception:
    WORKSPACE_DIR = (
        Path(__file__).resolve().parents[1]
        / "workspace"
    )


WORKSPACE_DIR = Path(WORKSPACE_DIR).resolve()

MEMORY_DIR = (
    WORKSPACE_DIR
    / "jibi_lab"
    / "memory"
).resolve()

MEMORY_FILE = (
    MEMORY_DIR
    / "evolution.jsonl"
).resolve()

MAX_MEMORY_ENTRIES = 5000


# ============================================================
# OUTILS INTERNES
# ============================================================

def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(data: Any) -> str:
    texte = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    return hashlib.sha256(
        texte.encode("utf-8")
    ).hexdigest()


def _verifier_chemin() -> None:
    """
    Vérifie que la mémoire reste dans son répertoire autorisé.
    """

    MEMORY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    memory_dir = MEMORY_DIR.resolve()
    memory_file = MEMORY_FILE.resolve()

    try:
        memory_file.relative_to(memory_dir)
    except ValueError as exc:
        raise PermissionError(
            "Fichier mémoire hors zone autorisée."
        ) from exc


def _dernier_hash() -> str | None:
    """
    Retourne le hash du dernier événement valide.

    Les anciens événements sans prev_hash restent compatibles.
    """

    if not MEMORY_FILE.exists():
        return None

    try:
        with MEMORY_FILE.open(
            "r",
            encoding="utf-8",
        ) as fichier:

            dernier: str | None = None

            for ligne in fichier:
                ligne = ligne.strip()

                if not ligne:
                    continue

                try:
                    evenement = json.loads(ligne)
                except json.JSONDecodeError:
                    continue

                hash_evenement = evenement.get("hash")

                if isinstance(
                    hash_evenement,
                    str,
                ):
                    dernier = hash_evenement

            return dernier

    except Exception:
        return None


def _construire_evenement(
    type_evenement: str,
    donnees: dict[str, Any],
    statut: str,
) -> dict[str, Any]:

    evenement: dict[str, Any] = {
        "timestamp": _timestamp(),
        "type": str(type_evenement),
        "statut": str(statut),
        "donnees": donnees,
    }

    precedent = _dernier_hash()

    if precedent:
        evenement["prev_hash"] = precedent

    evenement["hash"] = _hash(
        evenement
    )

    return evenement


def _ecrire_evenement(
    evenement: dict[str, Any],
) -> None:
    """
    Écriture append.

    Le fichier reste volontairement en JSONL :
    une corruption d'une ligne ne doit pas rendre
    tout l'historique illisible.
    """

    _verifier_chemin()

    ligne = (
        json.dumps(
            evenement,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
        + "\n"
    )

    with MEMORY_FILE.open(
        "a",
        encoding="utf-8",
    ) as fichier:
        fichier.write(ligne)
        fichier.flush()

        try:
            os.fsync(
                fichier.fileno()
            )
        except OSError:
            pass


def _hash_evenement_sans_hash(
    evenement: dict[str, Any],
) -> str:

    copie = dict(evenement)
    copie.pop("hash", None)

    return _hash(copie)


def _evenement_valide(
    evenement: dict[str, Any],
) -> bool:

    hash_stocke = evenement.get("hash")

    if not isinstance(
        hash_stocke,
        str,
    ):
        return False

    hash_calcule = _hash_evenement_sans_hash(
        evenement
    )

    return hash_stocke == hash_calcule


# ============================================================
# ENREGISTREMENT
# ============================================================

def enregistrer(
    type_evenement: str,
    donnees: dict[str, Any],
    *,
    statut: str = "INFO",
) -> dict[str, Any]:

    if not isinstance(
        donnees,
        dict,
    ):
        donnees = {
            "valeur": donnees,
        }

    evenement = _construire_evenement(
        type_evenement,
        donnees,
        statut,
    )

    _ecrire_evenement(
        evenement
    )

    nettoyer()

    return evenement


def enregistrer_observation(
    rapport: Any,
) -> dict[str, Any]:

    donnees = (
        rapport.to_dict()
        if hasattr(
            rapport,
            "to_dict",
        )
        else rapport
    )

    return enregistrer(
        "observation",
        donnees,
    )


def enregistrer_diagnostic(
    rapport: Any,
) -> dict[str, Any]:

    donnees = (
        rapport.to_dict()
        if hasattr(
            rapport,
            "to_dict",
        )
        else rapport
    )

    return enregistrer(
        "diagnostic",
        donnees,
    )


def enregistrer_patch(
    patch: Any,
) -> dict[str, Any]:

    if hasattr(
        patch,
        "to_dict",
    ):
        try:
            donnees = patch.to_dict(
                inclure_contenu=False
            )
        except TypeError:
            donnees = patch.to_dict()
    else:
        donnees = patch

    return enregistrer(
        "patch",
        donnees,
    )


def enregistrer_validation(
    resultat: Any,
) -> dict[str, Any]:

    donnees = (
        resultat.to_dict()
        if hasattr(
            resultat,
            "to_dict",
        )
        else resultat
    )

    return enregistrer(
        "validation",
        donnees,
    )


def enregistrer_application(
    donnees: dict[str, Any],
    *,
    statut: str = "INFO",
) -> dict[str, Any]:

    return enregistrer(
        "application",
        donnees,
        statut=statut,
    )


def enregistrer_rollback(
    donnees: dict[str, Any],
) -> dict[str, Any]:

    return enregistrer(
        "rollback",
        donnees,
        statut="ROLLBACK",
    )


# ============================================================
# LECTURE
# ============================================================

def lire(
    limite: int = 100,
) -> list[dict[str, Any]]:

    _verifier_chemin()

    if limite <= 0:
        return []

    if not MEMORY_FILE.exists():
        return []

    resultats: list[dict[str, Any]] = []

    try:
        with MEMORY_FILE.open(
            "r",
            encoding="utf-8",
        ) as fichier:

            for ligne in fichier:
                ligne = ligne.strip()

                if not ligne:
                    continue

                try:
                    evenement = json.loads(
                        ligne
                    )
                except json.JSONDecodeError:
                    continue

                if isinstance(
                    evenement,
                    dict,
                ):
                    resultats.append(
                        evenement
                    )

    except OSError:
        return []

    return resultats[-limite:]


def rechercher(
    terme: str,
    limite: int = 50,
) -> list[dict[str, Any]]:

    if limite <= 0:
        return []

    terme = str(terme).lower()

    resultats: list[dict[str, Any]] = []

    for evenement in lire(
        limite=MAX_MEMORY_ENTRIES
    ):

        texte = json.dumps(
            evenement,
            ensure_ascii=False,
            default=str,
        ).lower()

        if terme in texte:
            resultats.append(
                evenement
            )

            if len(resultats) >= limite:
                break

    return resultats


# ============================================================
# INTÉGRITÉ
# ============================================================

def verifier_integrite() -> dict[str, Any]:
    """
    Vérifie les hashes des événements.

    Les événements historiques sans hash sont signalés,
    mais ne font pas échouer toute la vérification.

    Le chaînage prev_hash est vérifié lorsqu'il existe.
    """

    _verifier_chemin()

    if not MEMORY_FILE.exists():
        return {
            "ok": True,
            "total": 0,
            "valides": 0,
            "invalides": 0,
            "orphelins": 0,
        }

    total = 0
    valides = 0
    invalides = 0
    orphelins = 0

    hash_precedent: str | None = None

    try:
        with MEMORY_FILE.open(
            "r",
            encoding="utf-8",
        ) as fichier:

            for ligne in fichier:
                ligne = ligne.strip()

                if not ligne:
                    continue

                total += 1

                try:
                    evenement = json.loads(
                        ligne
                    )
                except json.JSONDecodeError:
                    invalides += 1
                    continue

                if not isinstance(
                    evenement,
                    dict,
                ):
                    invalides += 1
                    continue

                if not _evenement_valide(
                    evenement
                ):
                    invalides += 1
                    continue

                prev_hash = evenement.get(
                    "prev_hash"
                )

                if (
                    prev_hash is not None
                    and hash_precedent is not None
                    and prev_hash != hash_precedent
                ):
                    orphelins += 1
                    invalides += 1
                    hash_precedent = evenement.get(
                        "hash"
                    )
                    continue

                valides += 1

                hash_precedent = evenement.get(
                    "hash"
                )

    except OSError:
        return {
            "ok": False,
            "total": total,
            "valides": valides,
            "invalides": invalides,
            "orphelins": orphelins,
        }

    return {
        "ok": invalides == 0,
        "total": total,
        "valides": valides,
        "invalides": invalides,
        "orphelins": orphelins,
    }


# ============================================================
# STATISTIQUES
# ============================================================

def compter() -> int:

    if not MEMORY_FILE.exists():
        return 0

    try:
        with MEMORY_FILE.open(
            "r",
            encoding="utf-8",
        ) as fichier:

            return sum(
                1
                for ligne in fichier
                if ligne.strip()
            )

    except OSError:
        return 0


def nettoyer(
    limite: int = MAX_MEMORY_ENTRIES,
) -> None:

    if limite <= 0:
        return

    if not MEMORY_FILE.exists():
        return

    try:
        lignes = MEMORY_FILE.read_text(
            encoding="utf-8"
        ).splitlines()

        if len(lignes) <= limite:
            return

        lignes = lignes[-limite:]

        fd, temp_name = tempfile.mkstemp(
            prefix=".jibi_memory_",
            suffix=".tmp",
            dir=str(MEMORY_DIR),
        )

        os.close(fd)

        temp = Path(
            temp_name
        )

        try:
            temp.write_text(
                "\n".join(lignes)
                + "\n",
                encoding="utf-8",
            )

            os.replace(
                temp,
                MEMORY_FILE,
            )

        finally:
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    pass

    except Exception:
        # La mémoire ne doit jamais empêcher JIBI
        # de fonctionner.
        return


def statistiques() -> dict[str, Any]:

    evenements = lire(
        limite=MAX_MEMORY_ENTRIES
    )

    par_type: dict[str, int] = {}

    for evenement in evenements:

        type_evenement = evenement.get(
            "type",
            "inconnu",
        )

        par_type[type_evenement] = (
            par_type.get(
                type_evenement,
                0,
            )
            + 1
        )

    integrite = verifier_integrite()

    return {
        "fichier": str(MEMORY_FILE),
        "total": len(evenements),
        "par_type": par_type,
        "limite": MAX_MEMORY_ENTRIES,
        "integrite": integrite,
    }


__all__ = [
    "enregistrer",
    "enregistrer_observation",
    "enregistrer_diagnostic",
    "enregistrer_patch",
    "enregistrer_validation",
    "enregistrer_application",
    "enregistrer_rollback",
    "lire",
    "rechercher",
    "verifier_integrite",
    "compter",
    "nettoyer",
    "statistiques",
]