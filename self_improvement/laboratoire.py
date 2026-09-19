"""
Laboratoire d'expérimentation de JIBI — v3

Responsabilités :
- créer et gérer les sessions de laboratoire ;
- copier des fichiers/dossiers dans un environnement isolé ;
- comparer les versions originales/modifiées ;
- nettoyer les anciennes sessions.

Sécurité :
- aucune modification de la production ;
- refus des chemins hors laboratoire pour les opérations de session ;
- exclusion des secrets et répertoires sensibles ;
- refus des liens symboliques ;
- exclusion des environnements et caches inutiles.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import difflib
import shutil
import time
import uuid


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

try:
    from core.config import (
        JIBI_PROJET_DIR,
        RETENTION_SESSIONS_JOURS,
        WORKSPACE_DIR,
    )

    PROJECT_ROOT = Path(JIBI_PROJET_DIR).resolve()
    LABORATOIRE_ROOT = Path(WORKSPACE_DIR).resolve() / "jibi_lab"
    DUREE_VIE_SESSION_JOURS = int(RETENTION_SESSIONS_JOURS)

except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    LABORATOIRE_ROOT = PROJECT_ROOT / "workspace" / "jibi_lab"
    DUREE_VIE_SESSION_JOURS = 7


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

try:
    from logging_jibi import log_event
except Exception:

    def log_event(*args, **kwargs):
        pass


# ---------------------------------------------------------------------------
# CONSTANTES DE SÉCURITÉ
# ---------------------------------------------------------------------------

DOSSIERS_EXCLUS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

FICHIERS_SECRETS = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
}

EXTENSIONS_SECRETS = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
}

NOM_SESSION_INFO = "_session_info.txt"


# ---------------------------------------------------------------------------
# OUTILS INTERNES
# ---------------------------------------------------------------------------

def _est_dans(chemin: Path, racine: Path) -> bool:
    """Retourne True si chemin est contenu dans racine."""
    try:
        chemin.resolve().relative_to(racine.resolve())
        return True
    except ValueError:
        return False


def _est_secret(chemin: Path) -> bool:
    """Détermine si un fichier doit être exclu du laboratoire."""
    nom = chemin.name.lower()

    if nom in FICHIERS_SECRETS:
        return True

    if nom.startswith(".env"):
        return True

    if chemin.suffix.lower() in EXTENSIONS_SECRETS:
        return True

    return False


def _est_dossier_exclu(chemin: Path) -> bool:
    """Détermine si un dossier doit être exclu."""
    return chemin.name.lower() in {x.lower() for x in DOSSIERS_EXCLUS}


def _verifier_source_fichier(source: Path) -> None:
    """Valide une source avant copie."""
    if not source.exists():
        raise FileNotFoundError(f"Fichier introuvable : {source}")

    if not source.is_file():
        raise ValueError(f"Ce n'est pas un fichier : {source}")

    if source.is_symlink():
        raise PermissionError(
            f"Copie refusée : lien symbolique détecté : {source}"
        )

    if _est_secret(source):
        raise PermissionError(
            f"Copie refusée : fichier sensible : {source.name}"
        )


def _verifier_session(session: Path) -> Path:
    """Vérifie qu'un chemin correspond à une session du laboratoire."""
    session = session.resolve()
    laboratoire = LABORATOIRE_ROOT.resolve()

    if not _est_dans(session, laboratoire):
        raise PermissionError(
            "Opération refusée : la session est hors du laboratoire JIBI."
        )

    if not session.exists():
        raise FileNotFoundError(f"Session introuvable : {session}")

    if not session.is_dir():
        raise ValueError(f"Ce n'est pas un dossier de session : {session}")

    # Une session doit être directement sous sessions/
    sessions_root = (laboratoire / "sessions").resolve()

    try:
        relatif = session.relative_to(sessions_root)
    except ValueError:
        raise PermissionError(
            "Opération refusée : le chemin n'est pas une session JIBI."
        )

    if len(relatif.parts) != 1:
        raise PermissionError(
            "Opération refusée : sous-dossier de session interdit."
        )

    return session


def _nom_propre(nom: str) -> str:
    """Nettoie un nom de session fourni par l'utilisateur."""
    propre = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in str(nom)
    )

    return propre[:30].strip("_") or "sans_nom"


# ---------------------------------------------------------------------------
# INITIALISATION
# ---------------------------------------------------------------------------

def initialiser_laboratoire() -> Path:
    """Crée l'arborescence du laboratoire si nécessaire."""
    t0 = time.perf_counter()

    for dossier in (
        "sessions",
        "backups",
        "propositions",
        "historique",
    ):
        (LABORATOIRE_ROOT / dossier).mkdir(
            parents=True,
            exist_ok=True,
        )

    log_event(
        "laboratoire",
        f"[LABO] Initialisation en "
        f"{time.perf_counter() - t0:.3f}s",
    )

    return LABORATOIRE_ROOT


# ---------------------------------------------------------------------------
# SESSIONS
# ---------------------------------------------------------------------------

def creer_session(nom: str | None = None) -> Path:
    """Crée une nouvelle session isolée."""
    t0 = time.perf_counter()

    initialiser_laboratoire()

    session_id = uuid.uuid4().hex[:12]

    if nom:
        nom_dossier = (
            f"session_{session_id}_{_nom_propre(nom)}"
        )
    else:
        nom_dossier = f"session_{session_id}"

    session = (
        LABORATOIRE_ROOT
        / "sessions"
        / nom_dossier
    )

    session.mkdir(
        parents=True,
        exist_ok=False,
    )

    (session / NOM_SESSION_INFO).write_text(
        (
            f"Session : {session_id}\n"
            f"Créée : {datetime.now().isoformat()}\n"
            f"Nom : {nom or 'sans nom'}\n"
        ),
        encoding="utf-8",
    )

    log_event(
        "laboratoire",
        f"[LABO] Session créée : {nom_dossier} "
        f"({time.perf_counter() - t0:.3f}s)",
    )

    return session


def compter_sessions() -> int:
    """Retourne le nombre de sessions existantes."""
    sessions_dir = LABORATOIRE_ROOT / "sessions"

    if not sessions_dir.exists():
        return 0

    return sum(
        1
        for dossier in sessions_dir.iterdir()
        if dossier.is_dir() and not dossier.is_symlink()
    )


def lister_sessions() -> list[dict]:
    """Liste les sessions du laboratoire."""
    sessions_dir = LABORATOIRE_ROOT / "sessions"

    if not sessions_dir.exists():
        return []

    sessions = []

    for dossier in sorted(
        sessions_dir.iterdir(),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    ):
        if not dossier.is_dir():
            continue

        if dossier.is_symlink():
            continue

        try:
            nb_fichiers = sum(
                1
                for fichier in dossier.rglob("*")
                if (
                    fichier.is_file()
                    and not fichier.is_symlink()
                    and fichier.name != NOM_SESSION_INFO
                )
            )

            sessions.append(
                {
                    "chemin": str(dossier),
                    "nom": dossier.name,
                    "fichiers": nb_fichiers,
                    "date": datetime.fromtimestamp(
                        dossier.stat().st_mtime
                    ).strftime("%Y-%m-%d %H:%M"),
                }
            )

        except OSError:
            continue

    return sessions


def supprimer_session(session: str | Path) -> bool:
    """Supprime une session après vérification stricte."""
    session = _verifier_session(Path(session))

    if not session.exists():
        return False

    shutil.rmtree(session)

    log_event(
        "laboratoire",
        f"[LABO] Session supprimée : {session.name}",
    )

    return True


def nettoyer_vieilles_sessions(jours: int | None = None) -> int:
    """Supprime les sessions dépassant leur durée de rétention."""
    if jours is None:
        jours = DUREE_VIE_SESSION_JOURS

    try:
        jours = int(jours)
    except (TypeError, ValueError):
        jours = DUREE_VIE_SESSION_JOURS

    if jours < 0:
        jours = 0

    sessions_dir = LABORATOIRE_ROOT / "sessions"

    if not sessions_dir.exists():
        return 0

    seuil = datetime.now() - timedelta(days=jours)
    supprimees = 0

    for dossier in sessions_dir.iterdir():

        if not dossier.is_dir():
            continue

        if dossier.is_symlink():
            continue

        try:
            date_modif = datetime.fromtimestamp(
                dossier.stat().st_mtime
            )

            if date_modif < seuil:
                shutil.rmtree(dossier)
                supprimees += 1

        except (OSError, PermissionError):
            continue

    if supprimees:
        log_event(
            "laboratoire",
            f"[LABO] Sessions nettoyées : {supprimees}",
        )

    return supprimees


# ---------------------------------------------------------------------------
# COPIE DE FICHIERS
# ---------------------------------------------------------------------------

def copier_fichier_dans_laboratoire(
    fichier_source: str | Path,
    session: str | Path,
) -> Path:
    """
    Copie un fichier dans une session.

    Le fichier source doit appartenir au projet JIBI.
    Les secrets et liens symboliques sont refusés.
    """
    t0 = time.perf_counter()

    source = Path(fichier_source).resolve()
    session = _verifier_session(Path(session))

    _verifier_source_fichier(source)

    # Les fichiers automatisés doivent venir du projet.
    if not _est_dans(source, PROJECT_ROOT):
        raise PermissionError(
            "Copie refusée : fichier source hors du projet JIBI."
        )

    relatif = source.relative_to(PROJECT_ROOT)
    destination = session / relatif

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Protection supplémentaire contre une destination externe.
    if not _est_dans(destination, session):
        raise PermissionError(
            "Copie refusée : destination hors de la session."
        )

    shutil.copy2(source, destination)

    log_event(
        "laboratoire",
        f"[LABO] Copie : {source.name} → "
        f"{destination} "
        f"({time.perf_counter() - t0:.3f}s)",
    )

    return destination


# ---------------------------------------------------------------------------
# COPIE DE DOSSIERS
# ---------------------------------------------------------------------------

def copier_dossier_dans_laboratoire(
    dossier_source: str | Path,
    session: str | Path,
) -> Path:
    """
    Copie un dossier du projet vers une session.

    Les répertoires sensibles, secrets et liens symboliques sont exclus.
    """
    t0 = time.perf_counter()

    source = Path(dossier_source).resolve()
    session = _verifier_session(Path(session))

    if not source.exists():
        raise FileNotFoundError(
            f"Dossier introuvable : {source}"
        )

    if not source.is_dir():
        raise ValueError(
            f"Ce n'est pas un dossier : {source}"
        )

    if source.is_symlink():
        raise PermissionError(
            f"Copie refusée : lien symbolique : {source}"
        )

    if not _est_dans(source, PROJECT_ROOT):
        raise PermissionError(
            "Copie refusée : dossier source hors du projet JIBI."
        )

    if _est_dossier_exclu(source):
        raise PermissionError(
            f"Copie refusée : dossier sensible : {source.name}"
        )

    destination = session / source.name

    if not _est_dans(destination, session):
        raise PermissionError(
            "Copie refusée : destination hors de la session."
        )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    fichiers_copies = 0
    fichiers_ignores = 0

    for element in source.rglob("*"):

        relatif = element.relative_to(source)

        # Vérification de chaque composant du chemin.
        if any(
            partie.lower() in {
                x.lower() for x in DOSSIERS_EXCLUS
            }
            for partie in relatif.parts
            if partie in DOSSIERS_EXCLUS
        ):
            fichiers_ignores += 1
            continue

        if element.is_symlink():
            fichiers_ignores += 1
            continue

        if element.is_dir():
            if _est_dossier_exclu(element):
                fichiers_ignores += 1
                continue

            (destination / relatif).mkdir(
                parents=True,
                exist_ok=True,
            )
            continue

        if not element.is_file():
            fichiers_ignores += 1
            continue

        if _est_secret(element):
            fichiers_ignores += 1
            continue

        cible = destination / relatif

        if not _est_dans(cible, session):
            raise PermissionError(
                "Copie refusée : destination hors de la session."
            )

        cible.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(element, cible)
        fichiers_copies += 1

    log_event(
        "laboratoire",
        f"[LABO] Dossier copié : {source.name} "
        f"(copies={fichiers_copies}, "
        f"ignores={fichiers_ignores}, "
        f"{time.perf_counter() - t0:.3f}s)",
    )

    return destination


# ---------------------------------------------------------------------------
# COMPARAISON
# ---------------------------------------------------------------------------

def comparer_fichiers(
    fichier_original: str | Path,
    fichier_modifie: str | Path,
) -> dict:
    """Compare deux fichiers et retourne leur diff."""
    original = Path(fichier_original)
    modifie = Path(fichier_modifie)

    if not original.exists():
        return {
            "ok": False,
            "message": f"Original introuvable : {original}",
        }

    if not modifie.exists():
        return {
            "ok": False,
            "message": f"Modifié introuvable : {modifie}",
        }

    if original.is_symlink() or modifie.is_symlink():
        return {
            "ok": False,
            "message": "Comparaison refusée : lien symbolique détecté.",
        }

    try:
        lignes_orig = original.read_text(
            encoding="utf-8-sig",
            errors="replace",
        ).splitlines(keepends=True)

        lignes_mod = modifie.read_text(
            encoding="utf-8-sig",
            errors="replace",
        ).splitlines(keepends=True)

        diff = list(
            difflib.unified_diff(
                lignes_orig,
                lignes_mod,
                fromfile=original.name,
                tofile=modifie.name,
                lineterm="",
            )
        )

        return {
            "ok": True,
            "identique": len(diff) == 0,
            "lignes_diff": len(diff),
            "diff": "\n".join(diff[:200]),
            "lignes_original": len(lignes_orig),
            "lignes_modifie": len(lignes_mod),
        }

    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
        }


# ---------------------------------------------------------------------------
# API PUBLIQUE
# ---------------------------------------------------------------------------

__all__ = [
    "PROJECT_ROOT",
    "LABORATOIRE_ROOT",
    "DUREE_VIE_SESSION_JOURS",
    "initialiser_laboratoire",
    "creer_session",
    "compter_sessions",
    "lister_sessions",
    "supprimer_session",
    "nettoyer_vieilles_sessions",
    "copier_fichier_dans_laboratoire",
    "copier_dossier_dans_laboratoire",
    "comparer_fichiers",
]