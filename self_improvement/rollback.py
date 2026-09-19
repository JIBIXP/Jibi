"""
JIBI — Rollback des modifications d'auto-réparation
====================================================

Orchestre uniquement les contrôles de rollback.
La restauration physique appartient à versions.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from core.config import JIBI_PROJET_DIR
except Exception:
    JIBI_PROJET_DIR = Path(__file__).resolve().parent.parent

PROJECT_DIR = Path(JIBI_PROJET_DIR).resolve()

try:
    from . import versions
except Exception:
    from self_improvement import versions

try:
    from .propositions import charger_proposition
except Exception:
    from self_improvement.propositions import charger_proposition

VERSION_ROLLBACK = 4

STATUT_PREPARE = "prepare"
STATUT_RESTAURE = "restaure"
STATUT_ECHEC = "echec"
STATUT_REFUSE = "refuse"

ALGORITHME_HASH = "sha256"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_fichier(fichier: str | Path) -> str:
    return versions.sha256_fichier(fichier)


def _normaliser_id(proposition_id: str) -> str:
    valeur = str(proposition_id or "").strip()
    if not valeur:
        raise ValueError("Identifiant de proposition vide.")
    if len(valeur) > 128:
        raise ValueError("Identifiant de proposition trop long.")
    if not all(c.isalnum() or c in "_-" for c in valeur):
        raise ValueError("Identifiant de proposition invalide.")
    return valeur


def _resoudre_fichier(fichier: str | Path) -> Path:
    original = Path(fichier)
    if original.is_symlink():
        raise ValueError(f"Fichier symbolique interdit : {fichier}")

    path = original.resolve()
    try:
        path.relative_to(PROJECT_DIR)
    except ValueError as exc:
        raise ValueError(f"Fichier hors du projet JIBI : {fichier}") from exc

    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    if not path.is_file():
        raise ValueError(f"Le chemin n'est pas un fichier : {path}")
    return path


def _chemins_identiques(
    chemin_a: str | Path,
    chemin_b: str | Path,
) -> bool:
    try:
        return Path(chemin_a).resolve() == Path(chemin_b).resolve()
    except Exception:
        return str(chemin_a) == str(chemin_b)


def trouver_backup_proposition(
    proposition_id: str,
) -> dict[str, Any] | None:
    pid = _normaliser_id(proposition_id)
    proposition = charger_proposition(pid)
    if not proposition:
        return None

    fichier = proposition.get("fichier")
    source_sha = str(proposition.get("source_sha256", "")).strip()

    candidats_directs: list[dict[str, Any]] = []
    candidats_fallback: list[dict[str, Any]] = []

    for backup in versions.lister_backups():
        if not isinstance(backup, dict):
            continue

        backup_pid = str(backup.get("proposition_id", "")).strip()
        backup_fichier = backup.get("fichier")
        backup_sha = str(backup.get("sha256", "")).strip()

        if backup_pid == pid:
            candidats_directs.append(backup)
            continue

        if not fichier or not backup_fichier:
            continue

        if (
            _chemins_identiques(fichier, backup_fichier)
            and source_sha
            and backup_sha
            and source_sha == backup_sha
        ):
            candidats_fallback.append(backup)

    def _date_cle(element: dict[str, Any]) -> str:
        return str(element.get("date", ""))

    candidats_directs.sort(key=_date_cle, reverse=True)
    candidats_fallback.sort(key=_date_cle, reverse=True)

    return (
        candidats_directs[0]
        if candidats_directs
        else candidats_fallback[0]
        if candidats_fallback
        else None
    )


def verifier_backup_proposition(
    proposition_id: str,
) -> dict[str, Any]:
    try:
        pid = _normaliser_id(proposition_id)
        proposition = charger_proposition(pid)

        if not proposition:
            return {
                "ok": False,
                "valide": False,
                "message": f"Proposition introuvable : {pid}",
            }

        backup = trouver_backup_proposition(pid)
        if not backup:
            return {
                "ok": False,
                "valide": False,
                "message": f"Aucun backup associé à la proposition {pid}.",
            }

        backup_path = backup.get("backup")
        if not backup_path:
            return {
                "ok": False,
                "valide": False,
                "message": "Le backup trouvé ne possède pas de chemin.",
            }

        integrite = versions.verifier_integrite_backup(
            backup_path,
            exiger_metadata=True,
        )
        if not integrite.get("ok", False):
            return {
                "ok": False,
                "valide": False,
                "message": "Le backup est corrompu, incomplet ou invalide.",
                "backup": backup,
                "integrite": integrite,
            }

        metadata = integrite.get("metadata") or {}
        erreurs: list[str] = []

        proposition_fichier = proposition.get("fichier")
        backup_fichier = backup.get("fichier") or metadata.get("fichier")

        proposition_sha = str(
            proposition.get("source_sha256", "")
        ).strip()
        backup_sha = str(
            backup.get("sha256", "")
        ).strip()
        sha_reel = str(
            integrite.get("sha256", "")
        ).strip()

        if not proposition_fichier:
            erreurs.append("La proposition ne possède aucun fichier cible.")
        if not backup_fichier:
            erreurs.append("Le backup ne possède aucun fichier source.")

        if (
            proposition_fichier
            and backup_fichier
            and not _chemins_identiques(
                proposition_fichier,
                backup_fichier,
            )
        ):
            erreurs.append("Le fichier du backup ne correspond pas au fichier de la proposition.")

        if not proposition_sha:
            erreurs.append("SHA source absent de la proposition.")
        if not backup_sha:
            erreurs.append("SHA source absent du backup.")

        if proposition_sha and backup_sha and proposition_sha != backup_sha:
            erreurs.append("Le SHA source de la proposition ne correspond pas au SHA du backup.")

        if backup_sha and sha_reel and backup_sha != sha_reel:
            erreurs.append("Le SHA déclaré du backup ne correspond pas à son contenu réel.")

        metadata_pid = str(metadata.get("proposition_id") or "").strip()
        if metadata_pid and metadata_pid != pid:
            erreurs.append("Le proposition_id du backup ne correspond pas à la proposition.")

        metadata_sha = str(metadata.get("sha256") or "").strip()
        if metadata_sha and proposition_sha and metadata_sha != proposition_sha:
            erreurs.append("Le SHA des métadonnées ne correspond pas au SHA source.")

        if erreurs:
            return {
                "ok": False,
                "valide": False,
                "message": "Le backup ne correspond pas exactement à la proposition.",
                "erreurs": erreurs,
                "backup": backup,
                "integrite": integrite,
            }

        return {
            "ok": True,
            "valide": True,
            "message": "Backup valide et correspondant à la proposition.",
            "proposition_id": pid,
            "backup": backup,
            "integrite": integrite,
        }

    except Exception as exc:
        return {"ok": False, "valide": False, "message": str(exc)}


def preparer_rollback(proposition_id: str) -> dict[str, Any]:
    try:
        pid = _normaliser_id(proposition_id)
        proposition = charger_proposition(pid)

        if not proposition:
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "message": f"Proposition introuvable : {pid}",
            }

        verification = verifier_backup_proposition(pid)
        if not verification.get("valide", False):
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "proposition_id": pid,
                "message": "Rollback refusé : backup non valide.",
                "verification": verification,
            }

        fichier = proposition.get("fichier")
        if not fichier:
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "proposition_id": pid,
                "message": "Rollback refusé : fichier cible absent.",
            }

        fichier_path = _resoudre_fichier(fichier)
        backup = verification["backup"]

        return {
            "ok": True,
            "statut": STATUT_PREPARE,
            "proposition_id": pid,
            "fichier": str(fichier_path),
            "backup": backup.get("backup"),
            "source_sha256": proposition.get("source_sha256"),
            "nouveau_sha256": proposition.get("nouveau_sha256"),
            "backup_sha256": backup.get("sha256"),
            "date": _timestamp(),
            "version": VERSION_ROLLBACK,
            "message": "Rollback préparé. Aucune modification effectuée.",
            "verification": verification,
        }

    except Exception as exc:
        return {
            "ok": False,
            "statut": STATUT_ECHEC,
            "message": str(exc),
        }


def verifier_etat_avant_rollback(
    proposition_id: str,
) -> dict[str, Any]:
    try:
        pid = _normaliser_id(proposition_id)
        proposition = charger_proposition(pid)

        if not proposition:
            return {"ok": False, "message": f"Proposition introuvable : {pid}"}

        fichier = proposition.get("fichier")
        if not fichier:
            return {"ok": False, "message": "Aucun fichier associé à la proposition."}

        path = _resoudre_fichier(fichier)
        sha_actuel = _sha256_fichier(path)
        sha_source = str(proposition.get("source_sha256", "")).strip()
        sha_nouveau = str(proposition.get("nouveau_sha256", "")).strip()

        return {
            "ok": True,
            "existe": True,
            "fichier": str(path),
            "sha256_actuel": sha_actuel,
            "sha256_source": sha_source,
            "sha256_nouveau": sha_nouveau,
            "correspond_nouveau": bool(sha_nouveau) and sha_actuel == sha_nouveau,
            "correspond_source": bool(sha_source) and sha_actuel == sha_source,
            "message": "État actuel récupéré.",
        }

    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def restaurer_proposition(
    proposition_id: str,
    force: bool = False,
) -> dict[str, Any]:
    try:
        pid = _normaliser_id(proposition_id)

        preparation = preparer_rollback(pid)
        if not preparation.get("ok", False):
            return preparation

        backup = preparation.get("backup")
        fichier = preparation.get("fichier")

        if not backup or not fichier:
            return {
                "ok": False,
                "statut": STATUT_ECHEC,
                "proposition_id": pid,
                "message": "Backup ou fichier cible absent.",
            }

        avant = verifier_etat_avant_rollback(pid)
        if not avant.get("ok", False):
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "proposition_id": pid,
                "message": "Rollback refusé : état actuel indéterminable.",
                "avant": avant,
            }

        integrite = versions.verifier_integrite_backup(
            backup,
            exiger_metadata=True,
        )
        if not integrite.get("ok", False):
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "proposition_id": pid,
                "message": "Rollback refusé : backup devenu invalide.",
                "integrite": integrite,
            }

        sha_backup = str(integrite.get("sha256", "")).strip()
        sha_actuel = str(avant.get("sha256_actuel", "")).strip()
        sha_source = str(avant.get("sha256_source", "")).strip()
        sha_nouveau = str(avant.get("sha256_nouveau", "")).strip()

        if not sha_backup:
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "proposition_id": pid,
                "message": "Rollback refusé : SHA du backup absent.",
            }

        if sha_source and sha_backup != sha_source:
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "proposition_id": pid,
                "message": "Rollback refusé : backup différent de l'état source.",
                "sha_source": sha_source,
                "sha_backup": sha_backup,
            }

        if sha_source and sha_actuel == sha_source:
            return {
                "ok": True,
                "statut": STATUT_PREPARE,
                "proposition_id": pid,
                "fichier": fichier,
                "backup": backup,
                "sha_avant": sha_actuel,
                "sha_backup": sha_backup,
                "date": _timestamp(),
                "message": "Rollback inutile : fichier déjà dans son état source.",
                "avant": avant,
            }

        # Protection contre l'écrasement d'une modification étrangère.
        # Un rollback automatique n'écrase que l'état produit par la proposition.
        if not sha_nouveau:
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "proposition_id": pid,
                "message": (
                    "Rollback refusé : nouveau_sha256 absent de la proposition ; "
                    "impossible de confirmer l'état attendu."
                ),
                "avant": avant,
            }

        if sha_actuel != sha_nouveau:
            return {
                "ok": False,
                "statut": STATUT_REFUSE,
                "proposition_id": pid,
                "message": (
                    "Rollback refusé : le fichier actuel ne correspond pas "
                    "à l'état produit par la proposition. Une modification "
                    "externe aurait pu intervenir."
                ),
                "sha_actuel": sha_actuel,
                "sha_nouveau": sha_nouveau,
                "avant": avant,
            }

        _ = force

        resultat_restore = versions.restaurer_backup(
            backup,
            destination=fichier,
            force=False,
        )

        if resultat_restore is not True:
            return {
                "ok": False,
                "statut": STATUT_ECHEC,
                "proposition_id": pid,
                "message": "La restauration physique a échoué.",
                "avant": avant,
            }

        fichier_path = _resoudre_fichier(fichier)
        sha_final = _sha256_fichier(fichier_path)

        if sha_final != sha_backup:
            return {
                "ok": False,
                "statut": STATUT_ECHEC,
                "proposition_id": pid,
                "message": (
                    "Échec de vérification du rollback : "
                    "le SHA final ne correspond pas au backup."
                ),
                "sha_backup": sha_backup,
                "sha_final": sha_final,
                "avant": avant,
            }

        return {
            "ok": True,
            "statut": STATUT_RESTAURE,
            "proposition_id": pid,
            "fichier": str(fichier_path),
            "backup": str(backup),
            "sha_avant": sha_actuel,
            "sha_apres": sha_final,
            "sha_backup": sha_backup,
            "date": _timestamp(),
            "version": VERSION_ROLLBACK,
            "algorithme_hash": ALGORITHME_HASH,
            "message": "Rollback effectué et vérifié.",
            "avant": avant,
        }

    except Exception as exc:
        return {
            "ok": False,
            "statut": STATUT_ECHEC,
            "proposition_id": proposition_id,
            "message": str(exc),
        }


def rollback_proposition(
    proposition_id: str,
    force: bool = False,
) -> dict[str, Any]:
    return restaurer_proposition(proposition_id, force=force)


def effectuer_rollback(
    proposition_id: str,
    force: bool = False,
) -> dict[str, Any]:
    return restaurer_proposition(proposition_id, force=force)


def rollback(
    proposition_id: str,
    force: bool = False,
) -> dict[str, Any]:
    return restaurer_proposition(proposition_id, force=force)


def formater_resultat_rollback(
    resultat: dict[str, Any] | None,
) -> str:
    if not resultat:
        return "Aucun résultat de rollback."

    lignes = [
        "=== ROLLBACK JIBI ===",
        f"Proposition : {resultat.get('proposition_id', '?')}",
        f"Statut      : {resultat.get('statut', '?')}",
        f"Fichier     : {resultat.get('fichier', '?')}",
        f"Backup      : {resultat.get('backup', '?')}",
    ]

    if resultat.get("sha_avant"):
        lignes.append(f"SHA avant   : {resultat['sha_avant']}")
    if resultat.get("sha_apres"):
        lignes.append(f"SHA après   : {resultat['sha_apres']}")
    if resultat.get("sha_backup"):
        lignes.append(f"SHA backup  : {resultat['sha_backup']}")
    if resultat.get("message"):
        lignes.append(f"Message     : {resultat['message']}")

    return "\n".join(lignes)


__all__ = [
    "trouver_backup_proposition",
    "verifier_backup_proposition",
    "preparer_rollback",
    "verifier_etat_avant_rollback",
    "restaurer_proposition",
    "rollback_proposition",
    "effectuer_rollback",
    "rollback",
    "formater_resultat_rollback",
]
