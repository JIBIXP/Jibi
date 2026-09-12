"""
Vision — analyse d'images via un modèle multimodal Ollama en local.

Deux sources d'images supportées :
- captures d'écran du PC (capturer_ecran) ;
- fichiers image fournis par l'utilisateur (analyser_image directement
  sur un chemin existant).

Tout reste local (aucun appel à une API vision externe), cohérent avec
le reste de JIBI. Nécessite un modèle multimodal tiré via Ollama, ex :
    ollama pull llava
"""

import os
import base64

from dotenv import load_dotenv
from ollama import Client
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava")
TIMEOUT_VISION = int(os.getenv("TIMEOUT_VISION", "120"))

_client_vision = Client(timeout=TIMEOUT_VISION)

EXTENSIONS_AUTORISEES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _valider_chemin_image(chemin):

    if not os.path.isfile(chemin):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    extension = os.path.splitext(chemin)[1].lower()

    if extension not in EXTENSIONS_AUTORISEES:
        raise ValueError(
            f"Extension non supportée : '{extension}'. "
            f"Formats acceptés : {', '.join(sorted(EXTENSIONS_AUTORISEES))}"
        )


def capturer_ecran(chemin="capture_ecran.png"):
    """
    Capture l'écran courant et l'enregistre sur disque.

    Utilise mss (multi-plateforme : Windows, macOS, Linux/X11) plutôt que
    PIL.ImageGrab, qui ne fonctionne pas de façon fiable sous Linux.
    Nécessite : pip install mss
    """

    try:
        import mss
        import mss.tools

        with mss.mss() as sct:

            moniteur = sct.monitors[1]  # écran principal (0 = tous les écrans combinés)

            capture = sct.grab(moniteur)

            mss.tools.to_png(capture.rgb, capture.size, output=chemin)

        log_event("vision", f"Capture d'écran enregistrée: {chemin}")

        return chemin

    except ImportError:
        raise ImportError(
            "Le paquet 'mss' est requis pour capturer l'écran : "
            "pip install mss"
        )

    except Exception as e:
        log_error("vision", f"capturer_ecran échoué: {e}", exc_info=False)
        raise


def analyser_image(chemin, question=None):
    """
    Décrit une image ou répond à une question précise à son sujet,
    via un modèle multimodal Ollama local.

    `chemin` peut venir d'une capture d'écran (capturer_ecran) ou d'un
    fichier fourni par l'utilisateur — traité de la même façon ici.
    """

    _valider_chemin_image(chemin)

    prompt = question or (
        "Décris cette image de façon claire et concise, en français."
    )

    try:
        with open(chemin, "rb") as f:
            image_bytes = f.read()

        reponse = _client_vision.chat(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_bytes],
                }
            ],
        )

        contenu = reponse["message"]["content"]

        log_event(
            "vision",
            f"Image analysée ({chemin}), réponse: {len(contenu)} chars"
        )

        return contenu

    except ConnectionError:
        log_warning("vision", "Ollama non disponible pour la vision")
        return (
            "Je suis déconnecté d'Ollama. "
            "Assure-toi que 'ollama serve' est lancé."
        )

    except Exception as e:
        message_erreur = str(e).lower()

        if "not found" in message_erreur or "model" in message_erreur:
            log_error("vision", f"Modèle vision manquant: {e}", exc_info=False)
            return (
                f"Le modèle vision '{VISION_MODEL}' n'est pas disponible. "
                f"Essaie : ollama pull {VISION_MODEL}"
            )

        log_error("vision", f"analyser_image échoué: {e}", exc_info=False)
        return f"Erreur lors de l'analyse de l'image : {str(e)[:150]}"


def capturer_et_analyser(question=None):
    """Raccourci : capture l'écran puis l'analyse immédiatement."""

    chemin = capturer_ecran()
    return analyser_image(chemin, question=question)