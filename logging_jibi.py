"""
Logging centralisé pour JIBI - fichier + console + DB (optionnel).

Usage:
    from logging_jibi import log_event, log_error, log_warning
    
    log_event("utilisateur", "message envoyé")
    log_warning("ollama", "timeout détecté")
    log_error("base_de_donnees", "connexion échouée", exc_info=True)
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / f"jibi_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

# Niveau de log (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL = os.getenv("JIBI_LOG_LEVEL", "INFO")


# ============================================================
# SETUP LOGGING
# ============================================================

def _setup_logging():
    """Configure logging fichier + console."""
    
    logger = logging.getLogger("JIBI")
    logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # Éviter les duplicates
    if logger.handlers:
        return logger
    
    # Format
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler fichier
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Handler console (WARNING+ seulement, pour pas spammer)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


logger = _setup_logging()


# ============================================================
# API DE LOGGING
# ============================================================

def log_event(component: str, message: str):
    """Log un événement normal."""
    logger.info(f"[{component}] {message}")


def log_warning(component: str, message: str):
    """Log un avertissement."""
    logger.warning(f"[{component}] {message}")


def log_error(component: str, message: str, exc_info=False):
    """Log une erreur."""
    logger.error(f"[{component}] {message}", exc_info=exc_info)


def log_debug(component: str, message: str):
    """Log un message debug (seulement si JIBI_LOG_LEVEL=DEBUG)."""
    logger.debug(f"[{component}] {message}")


# ============================================================
# CONTEXTE STRUCTURÉ
# ============================================================

def log_timing(component: str, stage: str, duration_ms: float):
    """Log la durée d'une opération."""
    logger.debug(f"[{component}] {stage} took {duration_ms:.1f}ms")


def log_stats(component: str, **stats):
    """Log des statistiques (dict)."""
    stats_str = " | ".join(f"{k}={v}" for k, v in stats.items())
    logger.info(f"[{component}] {stats_str}")
