"""
serveur_api.py — Alias ASGI pour uvicorn
=========================================

Ce fichier résout l'erreur répétée :
    ERROR: Could not import module "serveur_api"

uvicorn est lancé avec :
    uvicorn serveur_api:app

Il cherche ce fichier et récupère l'objet `app` (FastAPI).
L'app réelle est définie dans serveur_modeles.py — on l'importe ici.

Pour démarrer le serveur de modèles (optionnel, garde Ollama en mémoire) :
    python serveur_modeles.py
    ou
    uvicorn serveur_api:app --host 127.0.0.1 --port 8765
"""

from serveur_modeles import app  # noqa: F401

__all__ = ["app"]
