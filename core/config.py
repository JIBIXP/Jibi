"""
JIBI — Configuration centrale
=============================

Responsabilité :
    Centraliser les paramètres de JIBI.

Ce module :
    - lit les variables d'environnement ;
    - définit les chemins ;
    - définit les paramètres LLM ;
    - définit les paramètres d'auto-amélioration ;
    - expose les règles de sécurité de base.

Ce module ne :
    - lance aucun service ;
    - ne modifie aucun fichier métier ;
    - ne lance aucun LLM ;
    - ne prend aucune décision d'auto-réparation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# ============================================================
# ENVIRONNEMENT
# ============================================================

# Les variables système restent prioritaires.
load_dotenv(override=False)


def _env(name: str, default: Any = None) -> Any:
    value = os.getenv(name)
    return default if value is None else value


def _env_str(name: str, default: str = "") -> str:
    value = _env(name, default)
    return str(value).strip()


def _env_int(
    name: str,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        value = int(_env(name, default))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)

    if maximum is not None:
        value = min(maximum, value)

    return value


def _env_float(
    name: str,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        value = float(_env(name, default))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)

    if maximum is not None:
        value = min(maximum, value)

    return value


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(_env(name, str(default))).strip().lower()

    if value in {"1", "true", "yes", "on", "oui"}:
        return True

    if value in {"0", "false", "no", "off", "non"}:
        return False

    return default


# ============================================================
# PROJET
# ============================================================

PROJECT_ROOT = Path(
    _env_str(
        "JIBI_PROJET_DIR",
        str(Path(__file__).resolve().parent.parent),
    )
).resolve()

JIBI_PROJET_DIR = PROJECT_ROOT

WORKSPACE_DIR = (
    Path(
        _env_str(
            "JIBI_WORKSPACE_DIR",
            str(PROJECT_ROOT / "workspace"),
        )
    )
    .expanduser()
    .resolve()
)

LOGS_DIR = WORKSPACE_DIR / "logs"
CHROMA_DIR = WORKSPACE_DIR / "chroma"


# ============================================================
# LLM
# ============================================================

LLM_API = _env_str(
    "JIBI_LLM_API",
    "ollama",
).lower()

OLLAMA_HOST = _env_str(
    "JIBI_LLM_URL",
    "http://localhost:11434",
).rstrip("/")

MODEL = _env_str(
    "JIBI_LLM_MODEL",
    "qwen2.5-coder:7b",
)

MODEL_CODE = _env_str(
    "JIBI_LLM_MODEL_CODE",
    MODEL,
)

LLM_KEY = _env_str(
    "JIBI_LLM_KEY",
    "",
)

TIMEOUT_OLLAMA = _env_int(
    "JIBI_LLM_TIMEOUT",
    60,
    minimum=5,
    maximum=3600,
)

TIMEOUT_CODE = _env_int(
    "JIBI_LLM_TIMEOUT_CODE",
    300,
    minimum=10,
    maximum=3600,
)


# ============================================================
# OLLAMA — PERFORMANCE
# ============================================================

OLLAMA_KEEP_ALIVE = _env_str(
    "OLLAMA_KEEP_ALIVE",
    "30m",
)

OLLAMA_NUM_THREADS = _env_int(
    "OLLAMA_NUM_THREAD",
    4,
    minimum=1,
    maximum=64,
)

OLLAMA_NUM_CTX = _env_int(
    "OLLAMA_NUM_CTX",
    4096,
    minimum=512,
    maximum=131072,
)


# ============================================================
# OLLAMA — SORTIES
# ============================================================

OLLAMA_PREDICT_CHAT = _env_int(
    "OLLAMA_PREDICT_CHAT",
    512,
    minimum=64,
    maximum=16384,
)

OLLAMA_PREDICT_QUESTION = _env_int(
    "OLLAMA_PREDICT_QUESTION",
    512,
    minimum=64,
    maximum=16384,
)

OLLAMA_PREDICT_CODE = _env_int(
    "OLLAMA_PREDICT_CODE",
    1024,
    minimum=128,
    maximum=32768,
)

OLLAMA_PREDICT_COMPLEXE = _env_int(
    "OLLAMA_PREDICT_COMPLEXE",
    1024,
    minimum=128,
    maximum=32768,
)

OLLAMA_PREDICT_RECHERCHE = _env_int(
    "OLLAMA_PREDICT_RECHERCHE",
    512,
    minimum=64,
    maximum=16384,
)


# ============================================================
# TEMPÉRATURES
# ============================================================

OLLAMA_TEMPERATURE = _env_float(
    "OLLAMA_TEMPERATURE",
    0.5,
    minimum=0.0,
    maximum=2.0,
)

OLLAMA_TEMPERATURE_CHAT = _env_float(
    "OLLAMA_TEMPERATURE_CHAT",
    0.7,
    minimum=0.0,
    maximum=2.0,
)

OLLAMA_TEMPERATURE_QUESTION = _env_float(
    "OLLAMA_TEMPERATURE_QUESTION",
    0.5,
    minimum=0.0,
    maximum=2.0,
)

OLLAMA_TEMPERATURE_CODE = _env_float(
    "OLLAMA_TEMPERATURE_CODE",
    0.2,
    minimum=0.0,
    maximum=2.0,
)

OLLAMA_TEMPERATURE_COMPLEXE = _env_float(
    "OLLAMA_TEMPERATURE_COMPLEXE",
    0.5,
    minimum=0.0,
    maximum=2.0,
)

OLLAMA_TEMPERATURE_RECHERCHE = _env_float(
    "OLLAMA_TEMPERATURE_RECHERCHE",
    0.3,
    minimum=0.0,
    maximum=2.0,
)


# ============================================================
# GPU
# ============================================================

OLLAMA_VULKAN = _env_bool(
    "OLLAMA_VULKAN",
    True,
)

OLLAMA_GPU_LAYERS = _env_int(
    "OLLAMA_GPU_LAYERS",
    -1,
    minimum=-1,
    maximum=9999,
)

LLM_GPU_BACKEND = _env_str(
    "LLM_GPU_BACKEND",
    "auto",
).lower()


# ============================================================
# HISTORIQUE
# ============================================================

MAX_HISTORY = _env_int(
    "JIBI_MAX_HISTORY",
    20,
    minimum=1,
    maximum=500,
)


# ============================================================
# AUTO-AMÉLIORATION
# ============================================================

AUTO_IMPROVEMENT = _env_bool(
    "JIBI_AUTO_IMPROVEMENT",
    True,
)

AUTO_REPAIR_LEVEL = _env_int(
    "JIBI_AUTO_REPAIR_LEVEL",
    3,
    minimum=0,
    maximum=7,
)


# ============================================================
# LABORATOIRE
# ============================================================

LAB_ENABLED = _env_bool(
    "JIBI_LAB_ENABLED",
    True,
)

LAB_DIR = WORKSPACE_DIR / "jibi_lab"

LAB_MAX_SESSIONS = _env_int(
    "JIBI_LAB_MAX_SESSIONS",
    50,
    minimum=1,
    maximum=1000,
)


# ============================================================
# VALIDATION
# ============================================================

VALIDATION_ENABLED = _env_bool(
    "JIBI_VALIDATION_ENABLED",
    True,
)

VALIDATION_TIMEOUT = _env_int(
    "JIBI_VALIDATION_TIMEOUT",
    120,
    minimum=5,
    maximum=3600,
)


# ============================================================
# BACKUP / ROLLBACK
# ============================================================

BACKUP_ENABLED = _env_bool(
    "JIBI_BACKUP_ENABLED",
    True,
)

ROLLBACK_ENABLED = _env_bool(
    "JIBI_ROLLBACK_ENABLED",
    True,
)

BACKUP_DIR = WORKSPACE_DIR / "backups"

# Nombre maximum de backups conservés par fichier avant rotation.
# Lu par self_improvement/versions.py.
MAX_BACKUPS_PAR_FICHIER = _env_int(
    "JIBI_MAX_BACKUPS_PAR_FICHIER",
    10,
    minimum=1,
    maximum=100,
)


# ============================================================
# AUTORISATION
# ============================================================

REQUIRE_AUTHORIZATION = _env_bool(
    "JIBI_REQUIRE_AUTHORIZATION",
    True,
)

# Niveau 0-3 : observation / proposition / validation humaine.
# Niveau 4+ : ne doit jamais contourner les garde-fous.
# Les niveaux élevés restent soumis à backup, validation,
# politique de risque et autorisation explicite.
AUTO_REPAIR_REQUIRE_HUMAN = _env_bool(
    "JIBI_AUTO_REPAIR_REQUIRE_HUMAN",
    True,
)

AUTO_REPAIR_MAX_DIFF_LINES = _env_int(
    "JIBI_AUTO_REPAIR_MAX_DIFF_LINES",
    80,
    minimum=1,
    maximum=10000,
)

AUTO_REPAIR_MAX_FILE_SIZE = _env_int(
    "JIBI_AUTO_REPAIR_MAX_FILE_SIZE",
    2_000_000,
    minimum=1024,
    maximum=100_000_000,
)

AUTO_REPAIR_MAX_CHANGED_FILES = _env_int(
    "JIBI_AUTO_REPAIR_MAX_CHANGED_FILES",
    1,
    minimum=1,
    maximum=100,
)

AUTO_REPAIR_ALLOW_CRITICAL_FILES = _env_bool(
    "JIBI_AUTO_REPAIR_ALLOW_CRITICAL_FILES",
    False,
)

AUTO_REPAIR_ALLOW_NEW_FILES = _env_bool(
    "JIBI_AUTO_REPAIR_ALLOW_NEW_FILES",
    False,
)

AUTO_REPAIR_ALLOW_DELETE = _env_bool(
    "JIBI_AUTO_REPAIR_ALLOW_DELETE",
    False,
)

POST_APPLY_TEST_ENABLED = _env_bool(
    "JIBI_POST_APPLY_TEST_ENABLED",
    True,
)

POST_APPLY_TEST_TIMEOUT = _env_int(
    "JIBI_POST_APPLY_TEST_TIMEOUT",
    120,
    minimum=5,
    maximum=3600,
)

AUTO_ROLLBACK_ON_FAILURE = _env_bool(
    "JIBI_AUTO_ROLLBACK_ON_FAILURE",
    True,
)

PROPOSITION_TTL_DAYS = _env_int(
    "JIBI_PROPOSITION_TTL_DAYS",
    30,
    minimum=1,
    maximum=3650,
)


# ============================================================
# PROTECTION
# ============================================================

SECRET_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "secrets.json",
    "credentials.json",
    "authorized_keys",
}

PROTECTED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".ssh",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
}

FICHIERS_CRITIQUES = {
    "core/agent_core.py",
    "core/cerveau.py",
    "core/config.py",
    "core/router.py",
    "core/securite.py",
    "self_improvement/orchestrateur.py",
    "self_improvement/gestionnaire.py",
    "self_improvement/validateur.py",
    "self_improvement/risk_engine.py",
    "self_improvement/propositions.py",
    "self_improvement/laboratoire.py",
    "self_improvement/autorisation.py",
    "self_improvement/rollback.py",
    "self_improvement/evolution.py",
}
FICHIERS_CRITIQUES = {
    str(Path(nom).as_posix())
    for nom in FICHIERS_CRITIQUES
}

ACTIONS_CONFIRMATION_REQUISE = {
    "modifier_fichier",
    "creer_outil",
    "installer_outil",
    "appliquer_patch",
    "supprimer_fichier",
    "executer_action_sensible",
}


# ============================================================
# MÉMOIRE
# ============================================================

MEMORY_DIR = WORKSPACE_DIR / "memory"

MEMORY_FILE = MEMORY_DIR / "memoire.jsonl"

MAX_MEMORY_ENTRIES = _env_int(
    "JIBI_MAX_MEMORY_ENTRIES",
    5000,
    minimum=100,
    maximum=100000,
)


# ============================================================
# MISES À JOUR / GITHUB
# ============================================================

GITHUB_ENABLED = _env_bool(
    "JIBI_GITHUB_ENABLED",
    True,
)

AUTO_UPDATE = _env_bool(
    "JIBI_AUTO_UPDATE",
    False,
)


# ============================================================
# RECHERCHE
# ============================================================

TAVILY_API_KEY = _env_str(
    "TAVILY_API_KEY",
    "",
)

EXA_API_KEY = _env_str(
    "EXA_API_KEY",
    "",
)


# ============================================================
# MYSQL
# ============================================================

MYSQL_HOST = _env_str(
    "MYSQL_HOST",
    "localhost",
)

MYSQL_PORT = _env_int(
    "MYSQL_PORT",
    3306,
    minimum=1,
    maximum=65535,
)

MYSQL_DATABASE = _env_str(
    "MYSQL_DATABASE",
    "",
)

MYSQL_USER = _env_str(
    "MYSQL_USER",
    "",
)

MYSQL_PASSWORD = _env_str(
    "MYSQL_PASSWORD",
    "",
)


# ============================================================
# ENVIRONNEMENT
# ============================================================

ENVIRONMENT = _env_str(
    "JIBI_ENVIRONMENT",
    "production",
).lower()

DEBUG = _env_bool(
    "JIBI_DEBUG",
    False,
)


# ============================================================
# SÉCURITÉ DES CHEMINS
# ============================================================

def chemin_projet(fichier: str | Path) -> Path:
    """
    Transforme un chemin relatif en chemin absolu dans le projet.
    """

    chemin = Path(fichier)

    if chemin.is_absolute():
        return chemin.resolve()

    return (PROJECT_ROOT / chemin).resolve()


def chemin_relatif(fichier: str | Path) -> str:
    """
    Retourne un chemin relatif au projet.
    """

    cible = chemin_projet(fichier)

    try:
        return str(cible.relative_to(PROJECT_ROOT)).replace(
            "\\",
            "/",
        )
    except ValueError:
        return str(cible).replace("\\", "/")


def chemin_dans_projet(fichier: str | Path) -> bool:
    """
    Vérifie qu'un chemin appartient au projet.
    """

    try:
        chemin_projet(fichier).relative_to(PROJECT_ROOT)
        return True
    except ValueError:
        return False


def est_fichier_secret(fichier: str | Path) -> bool:
    """
    Détecte les fichiers contenant potentiellement des secrets.
    """

    chemin = Path(fichier)

    if chemin.name.lower() in {
        nom.lower()
        for nom in SECRET_FILE_NAMES
    }:
        return True

    return any(
        partie.lower() in {
            dossier.lower()
            for dossier in PROTECTED_DIRECTORIES
        }
        for partie in chemin.parts
    )


def est_fichier_critique(fichier: str | Path) -> bool:
    """
    Détermine si le fichier appartient aux composants critiques.
    """

    relatif = chemin_relatif(fichier)

    return relatif in {
        nom.replace("\\", "/")
        for nom in FICHIERS_CRITIQUES
    }


def peut_lire_fichier(fichier: str | Path) -> bool:
    """
    Autorise une lecture non sensible.
    """

    if not chemin_dans_projet(fichier):
        return False

    return not est_fichier_secret(fichier)


def peut_modifier_fichier(fichier: str | Path) -> bool:
    """
    Autorise une modification préliminaire.

    La décision finale appartient à l'orchestrateur.
    """

    if not chemin_dans_projet(fichier):
        return False

    if est_fichier_secret(fichier):
        return False

    if Path(fichier).suffix.lower() != ".py":
        return False

    return True


def valider_securite_fichier(
    fichier: str | Path,
    modification: bool = False,
) -> bool:
    """
    Vérification de sécurité de base.
    """

    if not chemin_dans_projet(fichier):
        return False

    if est_fichier_secret(fichier):
        return False

    if modification:
        return peut_modifier_fichier(fichier)

    return peut_lire_fichier(fichier)


# ============================================================
# SYNTAXE / AUTO-CORRECTION
# ============================================================

SYNTAX_AUTO_CORRECTION = _env_bool(
    "JIBI_SYNTAX_AUTO_CORRECTION",
    True,
)


# ============================================================
# VALIDATION CONFIGURATION
# ============================================================

def valider_configuration() -> dict[str, Any]:
    """
    Vérifie la cohérence globale de la configuration.

    Cette fonction ne modifie aucun fichier et ne lance aucun service.
    """
    erreurs: list[str] = []
    avertissements: list[str] = []

    if LLM_API not in {
        "ollama",
        "openai",
        "openai_compatible",
    }:
        erreurs.append(
            f"API LLM inconnue : {LLM_API}"
        )

    if not OLLAMA_HOST:
        erreurs.append(
            "OLLAMA_HOST est vide."
        )

    if not MODEL:
        erreurs.append(
            "MODEL est vide."
        )

    if not MODEL_CODE:
        erreurs.append(
            "MODEL_CODE est vide."
        )

    if OLLAMA_NUM_CTX < 512:
        erreurs.append(
            "OLLAMA_NUM_CTX trop faible."
        )

    if OLLAMA_NUM_THREADS < 1:
        erreurs.append(
            "OLLAMA_NUM_THREADS invalide."
        )

    for nom, valeur in (
        ("OLLAMA_TEMPERATURE", OLLAMA_TEMPERATURE),
        ("OLLAMA_TEMPERATURE_CHAT", OLLAMA_TEMPERATURE_CHAT),
        ("OLLAMA_TEMPERATURE_QUESTION", OLLAMA_TEMPERATURE_QUESTION),
        ("OLLAMA_TEMPERATURE_CODE", OLLAMA_TEMPERATURE_CODE),
        ("OLLAMA_TEMPERATURE_COMPLEXE", OLLAMA_TEMPERATURE_COMPLEXE),
        ("OLLAMA_TEMPERATURE_RECHERCHE", OLLAMA_TEMPERATURE_RECHERCHE),
    ):
        if not 0.0 <= valeur <= 2.0:
            erreurs.append(
                f"{nom} invalide."
            )

    if not PROJECT_ROOT.exists():
        erreurs.append(
            f"Projet introuvable : {PROJECT_ROOT}"
        )

    if AUTO_REPAIR_LEVEL >= 4 and not BACKUP_ENABLED:
        erreurs.append(
            "Auto-réparation élevée sans backup."
        )

    if AUTO_REPAIR_LEVEL >= 4 and not VALIDATION_ENABLED:
        erreurs.append(
            "Auto-réparation élevée sans validation."
        )

    if AUTO_REPAIR_LEVEL >= 4 and not REQUIRE_AUTHORIZATION:
        erreurs.append(
            "Auto-réparation élevée sans autorisation humaine."
        )

    if AUTO_REPAIR_LEVEL >= 4 and not AUTO_REPAIR_REQUIRE_HUMAN:
        erreurs.append(
            "Auto-réparation élevée avec garde-fou humain désactivé."
        )

    if AUTO_REPAIR_LEVEL >= 5 and not ROLLBACK_ENABLED:
        erreurs.append(
            "Auto-réparation très élevée sans rollback."
        )

    if AUTO_ROLLBACK_ON_FAILURE and not ROLLBACK_ENABLED:
        erreurs.append(
            "AUTO_ROLLBACK_ON_FAILURE activé alors que ROLLBACK_ENABLED est désactivé."
        )

    if POST_APPLY_TEST_ENABLED and POST_APPLY_TEST_TIMEOUT < 5:
        erreurs.append(
            "POST_APPLY_TEST_TIMEOUT trop faible."
        )

    if AUTO_REPAIR_MAX_DIFF_LINES < 1:
        erreurs.append(
            "AUTO_REPAIR_MAX_DIFF_LINES invalide."
        )

    if AUTO_REPAIR_MAX_CHANGED_FILES < 1:
        erreurs.append(
            "AUTO_REPAIR_MAX_CHANGED_FILES invalide."
        )

    if not AUTO_REPAIR_ALLOW_CRITICAL_FILES:
        avertissements.append(
            "Les fichiers critiques restent interdits d'auto-application."
        )

    if not AUTO_REPAIR_ALLOW_NEW_FILES:
        avertissements.append(
            "La création automatique de nouveaux fichiers est désactivée."
        )

    if not AUTO_REPAIR_ALLOW_DELETE:
        avertissements.append(
            "La suppression automatique de fichiers est désactivée."
        )

    if not BACKUP_ENABLED:
        avertissements.append(
            "Les backups sont désactivés."
        )

    if not ROLLBACK_ENABLED:
        avertissements.append(
            "Le rollback est désactivé."
        )

    if not LAB_ENABLED:
        avertissements.append(
            "Le laboratoire est désactivé."
        )

    if not VALIDATION_ENABLED:
        avertissements.append(
            "La validation est désactivée."
        )

    return {
        "ok": not erreurs,
        "erreurs": erreurs,
        "avertissements": avertissements,
    }


# ============================================================
# RÉPERTOIRES
# ============================================================

def creer_repertoires_necessaires() -> None:
    """
    Crée uniquement les répertoires techniques nécessaires.
    """

    for repertoire in (
        WORKSPACE_DIR,
        LOGS_DIR,
        CHROMA_DIR,
        LAB_DIR,
        BACKUP_DIR,
        MEMORY_DIR,
    ):
        repertoire.mkdir(
            parents=True,
            exist_ok=True,
        )


# ============================================================
# AFFICHAGE
# ============================================================

def afficher_configuration() -> None:
    """
    Affiche une configuration non sensible.
    """

    print(
        "=== CONFIGURATION JIBI ==="
    )

    print(
        f"Projet       : {PROJECT_ROOT}"
    )

    print(
        f"Workspace    : {WORKSPACE_DIR}"
    )

    print(
        f"API          : {LLM_API}"
    )

    print(
        f"LLM          : {OLLAMA_HOST}"
    )

    print(
        f"Modèle       : {MODEL}"
    )

    print(
        f"Modèle code  : {MODEL_CODE}"
    )

    print(
        f"GPU backend  : {LLM_GPU_BACKEND}"
    )

    print(
        f"GPU Vulkan   : {OLLAMA_VULKAN}"
    )

    print(
        f"GPU layers   : {OLLAMA_GPU_LAYERS}"
    )

    print(
        f"Context      : {OLLAMA_NUM_CTX}"
    )

    print(
        f"Threads      : {OLLAMA_NUM_THREADS}"
    )

    print(
        f"Auto-repair  : niveau {AUTO_REPAIR_LEVEL}"
    )

    print(
        f"Autorisation : {REQUIRE_AUTHORIZATION}"
    )

    print(
        f"Validation   : {VALIDATION_ENABLED}"
    )

    print(
        f"Laboratoire  : {LAB_ENABLED}"
    )

    print(
        f"Backup       : {BACKUP_ENABLED}"
    )

    print(
        f"Rollback     : {ROLLBACK_ENABLED}"
    )

    print(
        f"Test post-app: {POST_APPLY_TEST_ENABLED}"
    )


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "PROJECT_ROOT",
    "JIBI_PROJET_DIR",
    "WORKSPACE_DIR",
    "LOGS_DIR",
    "CHROMA_DIR",
    "LLM_API",
    "OLLAMA_HOST",
    "MODEL",
    "MODEL_CODE",
    "LLM_KEY",
    "TIMEOUT_OLLAMA",
    "TIMEOUT_CODE",
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_NUM_THREADS",
    "OLLAMA_NUM_CTX",
    "OLLAMA_PREDICT_CHAT",
    "OLLAMA_PREDICT_QUESTION",
    "OLLAMA_PREDICT_CODE",
    "OLLAMA_PREDICT_COMPLEXE",
    "OLLAMA_PREDICT_RECHERCHE",
    "OLLAMA_TEMPERATURE",
    "OLLAMA_TEMPERATURE_CHAT",
    "OLLAMA_TEMPERATURE_QUESTION",
    "OLLAMA_TEMPERATURE_CODE",
    "OLLAMA_TEMPERATURE_COMPLEXE",
    "OLLAMA_TEMPERATURE_RECHERCHE",
    "OLLAMA_VULKAN",
    "OLLAMA_GPU_LAYERS",
    "LLM_GPU_BACKEND",
    "MAX_HISTORY",
    "AUTO_IMPROVEMENT",
    "AUTO_REPAIR_LEVEL",
    "LAB_ENABLED",
    "LAB_DIR",
    "LAB_MAX_SESSIONS",
    "VALIDATION_ENABLED",
    "VALIDATION_TIMEOUT",
    "BACKUP_ENABLED",
    "ROLLBACK_ENABLED",
    "BACKUP_DIR",
    "MAX_BACKUPS_PAR_FICHIER",
    "REQUIRE_AUTHORIZATION",
    "AUTO_REPAIR_REQUIRE_HUMAN",
    "AUTO_REPAIR_MAX_DIFF_LINES",
    "AUTO_REPAIR_MAX_FILE_SIZE",
    "AUTO_REPAIR_MAX_CHANGED_FILES",
    "AUTO_REPAIR_ALLOW_CRITICAL_FILES",
    "AUTO_REPAIR_ALLOW_NEW_FILES",
    "AUTO_REPAIR_ALLOW_DELETE",
    "POST_APPLY_TEST_ENABLED",
    "POST_APPLY_TEST_TIMEOUT",
    "AUTO_ROLLBACK_ON_FAILURE",
    "PROPOSITION_TTL_DAYS",
    "SECRET_FILE_NAMES",
    "PROTECTED_DIRECTORIES",
    "FICHIERS_CRITIQUES",
    "ACTIONS_CONFIRMATION_REQUISE",
    "MEMORY_DIR",
    "MEMORY_FILE",
    "MAX_MEMORY_ENTRIES",
    "GITHUB_ENABLED",
    "AUTO_UPDATE",
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "ENVIRONMENT",
    "DEBUG",
    "SYNTAX_AUTO_CORRECTION",
    "chemin_projet",
    "chemin_relatif",
    "chemin_dans_projet",
    "est_fichier_secret",
    "est_fichier_critique",
    "peut_lire_fichier",
    "peut_modifier_fichier",
    "valider_securite_fichier",
    "valider_configuration",
    "creer_repertoires_necessaires",
    "afficher_configuration",
]