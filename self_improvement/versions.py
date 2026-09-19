"""
JIBI — Gestion des versions, backups et restaurations
======================================================

Couche physique de sauvegarde/restauration.

Ne décide pas :
    - si une modification est sûre ;
    - si elle est autorisée ;
    - si elle doit être appliquée.

Garantit :
    - confinement des chemins ;
    - backups atomiques ;
    - métadonnées d'intégrité ;
    - vérification SHA-256 ;
    - restauration atomique ;
    - refus d'un backup vers une autre destination que sa cible déclarée.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from core.config import WORKSPACE_DIR, JIBI_PROJET_DIR
except Exception:
    JIBI_PROJET_DIR = Path(__file__).resolve().parent.parent
    WORKSPACE_DIR = JIBI_PROJET_DIR / "workspace"

PROJECT_DIR = Path(JIBI_PROJET_DIR).resolve()
WORKSPACE_DIR = Path(WORKSPACE_DIR).resolve()
BACKUPS_DIR = (WORKSPACE_DIR / "backups").resolve()

try:
    from core.config import MAX_BACKUPS_PAR_FICHIER
except Exception:
    try:
        from core.config import MAX_BACKUPS
    except Exception:
        MAX_BACKUPS_PAR_FICHIER = 10

try:
    MAX_BACKUPS_PAR_FICHIER = int(MAX_BACKUPS_PAR_FICHIER)
except Exception:
    MAX_BACKUPS_PAR_FICHIER = 10

MAX_BACKUPS_PAR_FICHIER = max(1, min(MAX_BACKUPS_PAR_FICHIER, 100))

VERSION_BACKUP = 3
EXTENSION_BACKUP = ".bak"
ENCODING = "utf-8"
ALGORITHME_HASH = "sha256"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nom_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_fichier(fichier: str | Path) -> str:
    path = Path(fichier)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    if not path.is_file():
        raise ValueError(f"Le chemin n'est pas un fichier : {path}")

    h = hashlib.sha256()
    with path.open("rb") as flux:
        while True:
            bloc = flux.read(1024 * 1024)
            if not bloc:
                break
            h.update(bloc)
    return h.hexdigest()


def _chemin_resolu(chemin: str | Path) -> Path:
    return Path(chemin).expanduser().resolve()


def _est_dans(chemin: Path, dossier: Path) -> bool:
    try:
        chemin.resolve().relative_to(dossier.resolve())
        return True
    except ValueError:
        return False


def _valider_fichier_source(fichier: str | Path) -> Path:
    original = Path(fichier)
    if original.is_symlink():
        raise ValueError(f"Les liens symboliques sont interdits : {fichier}")

    path = original.resolve()
    if not _est_dans(path, PROJECT_DIR):
        raise ValueError(f"Fichier hors du projet JIBI interdit : {fichier}")
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    if not path.is_file():
        raise ValueError(f"Le chemin n'est pas un fichier : {path}")
    return path


def _valider_backup(backup: str | Path) -> Path:
    original = Path(backup)
    if original.is_symlink():
        raise ValueError(f"Backup symbolique interdit : {backup}")

    path = original.resolve()
    if not _est_dans(path, BACKUPS_DIR):
        raise ValueError(f"Backup hors du répertoire autorisé : {backup}")
    if not path.exists():
        raise FileNotFoundError(f"Backup introuvable : {path}")
    if not path.is_file():
        raise ValueError(f"Le backup n'est pas un fichier : {path}")
    return path


def _valider_destination_restauration(destination: str | Path) -> Path:
    original = Path(destination)
    if original.exists() and original.is_symlink():
        raise ValueError(f"Destination symbolique interdite : {destination}")

    path = original.resolve()
    if not _est_dans(path, PROJECT_DIR):
        raise ValueError(f"Destination hors du projet interdite : {destination}")

    parent = path.parent.resolve()
    if not _est_dans(parent, PROJECT_DIR):
        raise ValueError(f"Répertoire parent hors du projet : {parent}")
    return path


def _metadata_path(backup_path: Path) -> Path:
    return backup_path.with_suffix(backup_path.suffix + ".json")


def _lire_metadata(backup_path: Path) -> dict[str, Any] | None:
    metadata_path = _metadata_path(backup_path)
    if not metadata_path.exists() or not metadata_path.is_file():
        return None
    try:
        with metadata_path.open("r", encoding=ENCODING) as fichier:
            data = json.load(fichier)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _ecrire_json_atomique(chemin: Path, data: dict[str, Any]) -> None:
    chemin = chemin.resolve()
    if not _est_dans(chemin, BACKUPS_DIR):
        raise ValueError("Écriture de métadonnées hors backups interdite.")

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".jibi_backup_",
        suffix=".tmp",
        dir=str(BACKUPS_DIR),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding=ENCODING) as fichier:
            json.dump(data, fichier, ensure_ascii=False, indent=2)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.replace(temp_name, chemin)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _chemin_relatif_projet(fichier: Path) -> str:
    try:
        return str(fichier.resolve().relative_to(PROJECT_DIR))
    except ValueError as exc:
        raise ValueError(f"Fichier hors projet : {fichier}") from exc


def _nom_backup(fichier: Path) -> str:
    return f"{_nom_timestamp()}_{fichier.name}{EXTENSION_BACKUP}"


def creer_backup(
    fichier: str | Path,
    raison: str = "",
    proposition_id: str | None = None,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    try:
        source = _valider_fichier_source(fichier)
        contenu = source.read_bytes()
        sha = _sha256_bytes(contenu)

        if source_sha256 and str(source_sha256).strip() != sha:
            return {
                "ok": False,
                "backup": None,
                "message": "Le SHA fourni ne correspond pas au fichier actuel.",
                "source_sha256": sha,
            }

        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = (BACKUPS_DIR / _nom_backup(source)).resolve()

        if not _est_dans(backup_path, BACKUPS_DIR):
            raise ValueError("Chemin de backup invalide.")

        fd, temp_name = tempfile.mkstemp(
            prefix=".jibi_backup_content_",
            suffix=".tmp",
            dir=str(BACKUPS_DIR),
        )
        try:
            with os.fdopen(fd, "wb") as flux:
                flux.write(contenu)
                flux.flush()
                os.fsync(flux.fileno())
            os.replace(temp_name, backup_path)
        finally:
            Path(temp_name).unlink(missing_ok=True)

        sha_backup = sha256_fichier(backup_path)
        if sha_backup != sha:
            backup_path.unlink(missing_ok=True)
            raise RuntimeError("Échec de vérification du backup.")

        metadata = {
            "version": VERSION_BACKUP,
            "algorithme_hash": ALGORITHME_HASH,
            "backup": str(backup_path),
            "backup_relatif": str(backup_path.relative_to(WORKSPACE_DIR)),
            "fichier": str(source),
            "fichier_relatif": _chemin_relatif_projet(source),
            "date": _timestamp(),
            "raison": str(raison or ""),
            "proposition_id": str(proposition_id) if proposition_id else None,
            "sha256": sha,
            "sha256_backup": sha_backup,
            "taille": len(contenu),
            "taille_backup": backup_path.stat().st_size,
            "integrite": True,
        }

        metadata_path = _metadata_path(backup_path)
        _ecrire_json_atomique(metadata_path, metadata)

        if not metadata_path.exists():
            backup_path.unlink(missing_ok=True)
            raise RuntimeError("Les métadonnées du backup n'ont pas été créées.")

        nettoyage = nettoyer_backups_anciens(source, MAX_BACKUPS_PAR_FICHIER)

        return {
            "ok": True,
            "backup": str(backup_path),
            "metadata": str(metadata_path),
            "fichier": str(source),
            "sha256": sha,
            "taille": len(contenu),
            "date": metadata["date"],
            "raison": raison,
            "proposition_id": proposition_id,
            "nettoyage": nettoyage,
            "message": f"Backup créé : {backup_path}",
        }

    except Exception as exc:
        return {"ok": False, "backup": None, "message": str(exc)}


def verifier_integrite_backup(
    backup: str | Path,
    exiger_metadata: bool = False,
) -> dict[str, Any]:
    try:
        backup_path = _valider_backup(backup)
        problemes: list[str] = []

        taille = backup_path.stat().st_size
        sha = sha256_fichier(backup_path)
        metadata = _lire_metadata(backup_path)

        if exiger_metadata and metadata is None:
            problemes.append("Métadonnées du backup absentes ou invalides.")

        sha_attendu = None
        if metadata:
            taille_attendue = metadata.get("taille")
            sha_attendu = metadata.get("sha256")

            if taille_attendue is not None:
                try:
                    if int(taille_attendue) != taille:
                        problemes.append("Taille du backup différente des métadonnées.")
                except (TypeError, ValueError):
                    problemes.append("Taille invalide dans les métadonnées.")

            if sha_attendu and str(sha_attendu) != sha:
                problemes.append("SHA-256 du backup différent des métadonnées.")

            sha_backup_metadata = metadata.get("sha256_backup")
            if sha_backup_metadata and str(sha_backup_metadata) != sha:
                problemes.append("SHA-256 backup différent de sha256_backup.")

            if metadata.get("integrite") is False:
                problemes.append("Les métadonnées déclarent le backup invalide.")

        ok = not problemes
        return {
            "ok": ok,
            "backup": str(backup_path),
            "sha256": sha,
            "sha256_attendu": sha_attendu,
            "taille": taille,
            "problemes": problemes,
            "metadata": metadata,
            "message": "Backup intègre" if ok else "Backup invalide",
        }

    except Exception as exc:
        return {
            "ok": False,
            "backup": str(backup),
            "problemes": [str(exc)],
            "message": "Impossible de vérifier le backup.",
        }


def restaurer_backup(
    backup: str | Path,
    destination: str | Path | None = None,
    force: bool = False,
) -> bool:
    backup_path = _valider_backup(backup)

    verification = verifier_integrite_backup(
        backup_path,
        exiger_metadata=True,
    )
    if not verification.get("ok", False):
        raise ValueError("Restauration refusée : backup invalide.")

    metadata = verification.get("metadata") or {}

    if destination is None:
        destination = metadata.get("fichier")
    if not destination:
        raise ValueError("Destination absente et impossible à déterminer.")

    destination_path = _valider_destination_restauration(destination)

    # Un backup JIBI ne peut être restauré que vers sa cible déclarée.
    cible_metadata = metadata.get("fichier")
    if cible_metadata:
        cible_path = _valider_destination_restauration(cible_metadata)
        if cible_path != destination_path:
            raise ValueError(
                "Restauration refusée : le backup ne correspond pas "
                "à la destination demandée."
            )
    elif destination is not None:
        raise ValueError(
            "Restauration refusée : cible du backup absente des métadonnées."
        )

    if destination_path.exists():
        if destination_path.is_symlink():
            raise ValueError("Restauration vers un lien symbolique interdite.")
        if not destination_path.is_file():
            raise ValueError(f"Destination invalide : {destination_path}")

    _ = force

    contenu = backup_path.read_bytes()
    sha_source = _sha256_bytes(contenu)

    if sha_source != verification.get("sha256"):
        raise RuntimeError("Le contenu du backup a changé pendant la vérification.")

    parent = destination_path.parent.resolve()
    if not _est_dans(parent, PROJECT_DIR):
        raise ValueError("Répertoire de restauration hors projet.")

    parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.jibi_restore_",
        suffix=".tmp",
        dir=str(parent),
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "wb") as flux:
            flux.write(contenu)
            flux.flush()
            os.fsync(flux.fileno())

        sha_temp = sha256_fichier(temp_path)
        if sha_temp != sha_source:
            raise RuntimeError("La copie temporaire ne correspond pas au backup.")

        if destination_path.exists():
            try:
                shutil.copystat(destination_path, temp_path)
            except Exception:
                pass

        os.replace(temp_path, destination_path)

        sha_final = sha256_fichier(destination_path)
        if sha_final != sha_source:
            raise RuntimeError(
                "La restauration finale échoue à la vérification SHA-256."
            )

        return True
    finally:
        temp_path.unlink(missing_ok=True)


def lister_backups(
    fichier: str | Path | None = None,
) -> list[dict[str, Any]]:
    resultat: list[dict[str, Any]] = []
    fichier_resolu: Path | None = None

    if fichier is not None:
        fichier_resolu = _valider_fichier_source(fichier)

    if not BACKUPS_DIR.exists():
        return resultat

    for backup_path in BACKUPS_DIR.glob(f"*{EXTENSION_BACKUP}"):
        try:
            backup_path = _valider_backup(backup_path)
        except Exception:
            continue

        metadata = _lire_metadata(backup_path)

        if metadata:
            fichier_meta = metadata.get("fichier")
            if fichier_resolu is not None:
                if not fichier_meta:
                    continue
                try:
                    if Path(fichier_meta).resolve() != fichier_resolu:
                        continue
                except Exception:
                    continue

            resultat.append({**metadata, "backup": str(backup_path)})
        elif fichier_resolu is not None:
            # Les anciens backups restent listables, mais ne sont pas
            # restaurables par restaurer_backup() sans métadonnées.
            if fichier_resolu.name not in backup_path.name:
                continue
            try:
                resultat.append({
                    "version": 1,
                    "backup": str(backup_path),
                    "fichier": str(fichier_resolu),
                    "date": datetime.fromtimestamp(
                        backup_path.stat().st_mtime,
                        tz=timezone.utc,
                    ).isoformat(),
                    "sha256": sha256_fichier(backup_path),
                    "taille": backup_path.stat().st_size,
                    "metadata_absentes": True,
                })
            except Exception:
                continue

    resultat.sort(
        key=lambda x: str(x.get("date", "")),
        reverse=True,
    )
    return resultat


def compter_backups(fichier: str | Path | None = None) -> int:
    return len(lister_backups(fichier))


def obtenir_dernier_backup(
    fichier: str | Path,
) -> dict[str, Any] | None:
    backups = lister_backups(fichier)
    return backups[0] if backups else None


def comparer_avec_backup(
    fichier: str | Path,
    backup: str | Path | None = None,
) -> dict[str, Any]:
    try:
        source = _valider_fichier_source(fichier)

        if backup is None:
            dernier = obtenir_dernier_backup(source)
            if not dernier:
                return {"ok": False, "message": "Aucun backup trouvé."}
            backup = dernier["backup"]

        backup_path = _valider_backup(backup)
        integrite = verifier_integrite_backup(backup_path)

        if not integrite.get("ok"):
            return {
                "ok": False,
                "message": "Backup invalide.",
                "integrite": integrite,
            }

        sha_fichier_actuel = sha256_fichier(source)
        sha_backup = sha256_fichier(backup_path)
        taille_fichier = source.stat().st_size
        taille_backup = backup_path.stat().st_size
        identiques = sha_fichier_actuel == sha_backup

        return {
            "ok": True,
            "fichier": str(source),
            "backup": str(backup_path),
            "sha256_fichier": sha_fichier_actuel,
            "sha256_backup": sha_backup,
            "taille_fichier": taille_fichier,
            "taille_backup": taille_backup,
            "identiques": identiques,
            "modifie": not identiques,
            "message": (
                "Fichier identique au backup."
                if identiques
                else "Fichier différent du backup."
            ),
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def nettoyer_backups_anciens(
    fichier: str | Path,
    max_backups: int | None = None,
) -> dict[str, Any]:
    try:
        source = _valider_fichier_source(fichier)

        if max_backups is None:
            max_backups = MAX_BACKUPS_PAR_FICHIER

        try:
            max_backups = int(max_backups)
        except (TypeError, ValueError):
            max_backups = MAX_BACKUPS_PAR_FICHIER

        max_backups = max(1, min(max_backups, 100))
        backups = lister_backups(source)

        if len(backups) <= max_backups:
            return {
                "ok": True,
                "supprimes": [],
                "nombre_supprime": 0,
                "conserves": len(backups),
            }

        anciens = backups[max_backups:]
        supprimes: list[str] = []

        for element in anciens:
            chemin = element.get("backup")
            if not chemin:
                continue

            try:
                backup_path = _valider_backup(chemin)
            except Exception:
                continue

            try:
                backup_path.unlink(missing_ok=True)
                _metadata_path(backup_path).unlink(missing_ok=True)
                supprimes.append(str(backup_path))
            except Exception:
                continue

        return {
            "ok": True,
            "supprimes": supprimes,
            "nombre_supprime": len(supprimes),
            "conserves": min(max_backups, len(backups)),
        }
    except Exception as exc:
        return {"ok": False, "supprimes": [], "message": str(exc)}


def obtenir_statistiques_backups() -> dict[str, Any]:
    backups = lister_backups()
    total_taille = 0
    integres = 0
    invalides = 0
    par_fichier: dict[str, int] = {}

    for backup in backups:
        try:
            total_taille += int(backup.get("taille", 0))
        except Exception:
            pass

        chemin = backup.get("backup")
        if chemin:
            verification = verifier_integrite_backup(chemin)
            if verification.get("ok"):
                integres += 1
            else:
                invalides += 1

        fichier = backup.get("fichier_relatif") or backup.get("fichier")
        if fichier:
            fichier = str(fichier)
            par_fichier[fichier] = par_fichier.get(fichier, 0) + 1

    return {
        "total": len(backups),
        "integres": integres,
        "invalides": invalides,
        "taille_totale": total_taille,
        "taille_totale_mo": round(total_taille / (1024 * 1024), 3),
        "par_fichier": par_fichier,
        "repertoire": str(BACKUPS_DIR),
        "max_backups_par_fichier": MAX_BACKUPS_PAR_FICHIER,
    }


__all__ = [
    "creer_backup",
    "restaurer_backup",
    "lister_backups",
    "compter_backups",
    "nettoyer_backups_anciens",
    "obtenir_dernier_backup",
    "comparer_avec_backup",
    "obtenir_statistiques_backups",
    "verifier_integrite_backup",
    "sha256_fichier",
]
