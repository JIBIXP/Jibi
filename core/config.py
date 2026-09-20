"""
Configuration centrale de JIBI — PATCHÉ v2
Ajouts P0 : 4 profils PREDICT + 2 températures + fix threads/timeout
"""
import os
from pathlib import Path
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv optionnel
    def load_dotenv(*a, **kw):
        return False
load_dotenv(override=True)

def _env(name, default=""):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()

def _env_int(name, default):
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return int(default)

def _env_float(name, default):
    try:
        return float(_env(name, str(default)))
    except (TypeError, ValueError):
        return float(default)

def _env_bool(name, default=False):
    value = _env(name, "1" if default else "0").lower()
    return value in {"1", "true", "yes", "oui", "on"}

JIBI_PROJET_DIR = Path(_env("JIBI_PROJET_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WORKSPACE_DIR = JIBI_PROJET_DIR / "workspace"
LOGS_DIR = JIBI_PROJET_DIR / "logs"
CHROMA_DIR = JIBI_PROJET_DIR / "chroma_db"

LLM_API = _env("JIBI_LLM_API", "ollama").lower()
OLLAMA_HOST = _env("JIBI_LLM_URL", _env("OLLAMA_HOST", _env("OLLAMA_URL", "http://localhost:11434"))).rstrip("/")
MODEL = _env("JIBI_LLM_MODEL", _env("OLLAMA_MODEL", "llama3.2:3b"))
LLM_KEY = _env("JIBI_LLM_KEY", "")
TIMEOUT_OLLAMA = _env_int("JIBI_LLM_TIMEOUT", _env_int("TIMEOUT_OLLAMA", 120))
TIMEOUT_CODE = _env_int("JIBI_LLM_TIMEOUT_CODE", 300)

OLLAMA_KEEP_ALIVE = _env("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_THREADS = _env_int("OLLAMA_NUM_THREAD", 4)
OLLAMA_NUM_CTX = _env_int("OLLAMA_NUM_CTX", 4096)
# Legacy unique (rétrocompat)
OLLAMA_NUM_PREDICT = _env_int("OLLAMA_NUM_PREDICT", 1024)
# Nouveaux profils P0
OLLAMA_PREDICT_CHAT = _env_int("OLLAMA_PREDICT_CHAT", 128)
OLLAMA_PREDICT_QUESTION = _env_int("OLLAMA_PREDICT_QUESTION", 256)
OLLAMA_PREDICT_CODE = _env_int("OLLAMA_PREDICT_CODE", 768)
OLLAMA_PREDICT_COMPLEXE = _env_int("OLLAMA_PREDICT_COMPLEXE", 1024)
OLLAMA_TEMPERATURE = _env_float("OLLAMA_TEMPERATURE", 0.3)
OLLAMA_TEMPERATURE_CHAT = _env_float("OLLAMA_TEMPERATURE_CHAT", 0.4)
OLLAMA_TEMPERATURE_CODE = _env_float("OLLAMA_TEMPERATURE_CODE", 0.2)

OLLAMA_VULKAN = _env_bool("OLLAMA_VULKAN", False)
OLLAMA_GPU_LAYERS = _env_int("OLLAMA_GPU_LAYERS", 0)
USER_ID = _env("JIBI_USER_ID", "ulriche")
HISTORIQUE_MAX = _env_int("HISTORIQUE_MAX", 6)
HISTORIQUE_FENETRE_MINUTES = _env_int("HISTORIQUE_FENETRE_MINUTES", 15)
AUTO_AMELIORATION_ACTIVE = _env_bool("AUTO_AMELIORATION_ACTIVE", True)
MAX_PROPOSITIONS = _env_int("MAX_PROPOSITIONS", 100)
MAX_SESSIONS_LAB = _env_int("MAX_SESSIONS_LAB", 20)
RETENTION_SESSIONS_JOURS = _env_int("RETENTION_SESSIONS_JOURS", 7)
MAX_BACKUPS_PAR_FICHIER = _env_int("MAX_BACKUPS_PAR_FICHIER", 20)
RETENTION_BACKUPS_JOURS = _env_int("RETENTION_BACKUPS_JOURS", 30)
SEUIL_PATTERN_RECURRENT = _env_int("SEUIL_PATTERN_RECURRENT", 3)
LIMITE_LOGS_ANALYSE = _env_int("LIMITE_LOGS_ANALYSE", 1000)
ANALYSE_LOGS_HEURES = _env_int("ANALYSE_LOGS_HEURES", 24)
GITHUB_REPO_URL = _env("GITHUB_REPO_URL", "https://github.com/votre-user/jibi.git")
GITHUB_BRANCH = _env("GITHUB_BRANCH", "main")
MAX_SAUVEGARDES_UPDATER = _env_int("MAX_SAUVEGARDES_UPDATER", 10)
TESTS_AUTO_APRES_UPDATE = _env_bool("TESTS_AUTO_APRES_UPDATE", True)
MYSQL_HOST = _env("MYSQL_HOST", "localhost")
MYSQL_USER = _env("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = _env("MYSQL_DATABASE", "jibi_db")
MEMOIRE_CONTEXTE_AUTO = _env_bool("MEMOIRE_CONTEXTE_AUTO", False)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
EXA_API_KEY = os.getenv("EXA_API_KEY", "")
CHROMA_N_RESULTS = _env_int("CHROMA_N_RESULTS", 3)
FICHIERS_SENSIBLES = {"agent.py", "core/agent_core.py", "core/config.py", ".env", "database.py", "logging_jibi.py"}
# FIX (bug bloquant) : "tools" NE DOIT PAS être sensible — c'est le dossier où
# JIBI crée ses propres outils (tools/plugins/). Le laisser ici faisait échouer
# la validation sécurité de TOUTE création d'outil (propositions "tests_echoues"
# impossibles à appliquer). La vraie politique de zones est dans evolution.protege().
DOSSIERS_SENSIBLES = {"core"}
ACTIONS_CONFIRMATION_REQUISE = {"executer_commande", "fermer_application", "supprimer_fichier", "appliquer_mise_a_jour", "restaurer_derniere_sauvegarde", "appliquer_amelioration"}
LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()
RETENTION_LOGS_JOURS = _env_int("RETENTION_LOGS_JOURS", 30)
DEBUG = _env_bool("DEBUG", False)
ENVIRONMENT = _env("ENVIRONMENT", "dev")

def creer_repertoires_necessaires():
    for repertoire in [WORKSPACE_DIR, WORKSPACE_DIR / "self_improvement" / "propositions", WORKSPACE_DIR / "self_improvement" / "analyses", WORKSPACE_DIR / "self_improvement" / "backups", WORKSPACE_DIR / "jibi_lab" / "sessions", WORKSPACE_DIR / "updater_backups", WORKSPACE_DIR / "updater_logs", LOGS_DIR, CHROMA_DIR]:
        repertoire.mkdir(parents=True, exist_ok=True)

def valider_configuration():
    problemes = []
    if not JIBI_PROJET_DIR.exists():
        problemes.append(f"⚠️ JIBI_PROJET_DIR introuvable : {JIBI_PROJET_DIR}")
    if not MODEL:
        problemes.append("⚠️ Aucun modèle LLM défini.")
    if not OLLAMA_HOST:
        problemes.append("⚠️ Adresse du serveur LLM absente.")
    if TIMEOUT_OLLAMA <= 0:
        problemes.append("⚠️ TIMEOUT_OLLAMA doit être supérieur à 0.")
    if OLLAMA_NUM_THREADS <= 0:
        problemes.append("⚠️ OLLAMA_NUM_THREADS doit être supérieur à 0.")
    if OLLAMA_NUM_CTX <= 0:
        problemes.append("⚠️ OLLAMA_NUM_CTX doit être supérieur à 0.")
    if OLLAMA_NUM_PREDICT <= 0:
        problemes.append("⚠️ OLLAMA_NUM_PREDICT doit être supérieur à 0.")
    if OLLAMA_PREDICT_CHAT > OLLAMA_PREDICT_COMPLEXE:
        problemes.append("⚠️ PREDICT_CHAT doit être < PREDICT_COMPLEXE")
    if OLLAMA_TEMPERATURE < 0 or OLLAMA_TEMPERATURE > 2:
        problemes.append("⚠️ Température hors borne [0,2]")
    if not MYSQL_HOST or not MYSQL_DATABASE:
        problemes.append("⚠️ Configuration MySQL incomplète.")
    if not TAVILY_API_KEY:
        problemes.append("ℹ️ TAVILY_API_KEY non définie (recherche web limitée).")
    if not EXA_API_KEY:
        problemes.append("ℹ️ EXA_API_KEY non définie (recherche web alternative indisponible).")
    return problemes

def afficher_configuration():
    print("\n" + "=" * 60)
    print("⚙️  CONFIGURATION JIBI — PATCHÉ v2")
    print("=" * 60)
    print("\n📁 Projet :")
    print(f"   Répertoire : {JIBI_PROJET_DIR}")
    print(f"   Environnement : {ENVIRONMENT}")
    print(f"   Debug : {'✓' if DEBUG else '✗'}")
    print("\n🤖 Modèle :")
    print(f"   API : {LLM_API}")
    print(f"   Modèle : {MODEL}")
    print(f"   Host : {OLLAMA_HOST}")
    print(f"   Timeout : {TIMEOUT_OLLAMA}s (code: {TIMEOUT_CODE}s)")
    print(f"   Keep alive : {OLLAMA_KEEP_ALIVE}")
    print("\n⚡ Performance — PROFILS :")
    print(f"   Threads CPU : {OLLAMA_NUM_THREADS}")
    print(f"   Contexte : {OLLAMA_NUM_CTX}")
    print(f"   Chat max : {OLLAMA_PREDICT_CHAT} (temp {OLLAMA_TEMPERATURE_CHAT})")
    print(f"   Question : {OLLAMA_PREDICT_QUESTION}")
    print(f"   Code max : {OLLAMA_PREDICT_CODE} (temp {OLLAMA_TEMPERATURE_CODE})")
    print(f"   Complexe : {OLLAMA_PREDICT_COMPLEXE}")
    print(f"   Température défaut : {OLLAMA_TEMPERATURE}")
    print("\n🎮 Backend GPU :")
    print(f"   Vulkan demandé : {'✓' if OLLAMA_VULKAN else '✗'}")
    print(f"   GPU layers : {OLLAMA_GPU_LAYERS}")
    print("\n" + "=" * 60 + "\n")
    problemes = valider_configuration()
    if problemes:
        print("⚠️  Problèmes de configuration :\n")
        for p in problemes:
            print(f"   {p}")
        print()

creer_repertoires_necessaires()
if __name__ != "__main__":
    os.environ["JIBI_PROJET_DIR"] = str(JIBI_PROJET_DIR)
if __name__ == "__main__":
    afficher_configuration()