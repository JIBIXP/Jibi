"""
Vision — analyse d'images via un modèle multimodal Ollama en local.

Deux sources d'images supportées :
- captures d'écran du PC (capturer_ecran) ;
- fichiers image fournis par l'utilisateur (analyser_image directement
  sur un chemin existant).

Tout reste local (aucun appel à une API vision externe), cohérent avec
le reste de JIBI. Nécessite un modèle multimodal tiré via Ollama, ex :
    ollama pull llava
    ollama pull llava:13b  (meilleur mais plus lourd)
    ollama pull bakllava   (alternative rapide)

Performance :
- Capture écran : ~100ms
- Analyse image : 2-10s selon taille modèle et résolution
- Cache des captures dans workspace/screenshots/
"""

import os
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from ollama import Client
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)


# ============================================================
# CONFIGURATION
# ============================================================

VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava")
TIMEOUT_VISION = int(os.getenv("TIMEOUT_VISION", "120"))

# Extensions d'images supportées
EXTENSIONS_AUTORISEES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

# Dossier pour sauvegarder les captures d'écran
PROJET_DIR = Path(os.getenv("JIBI_PROJET_DIR", "."))
SCREENSHOTS_DIR = PROJET_DIR / "workspace" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Client Ollama pour vision
_client_vision = Client(timeout=TIMEOUT_VISION)

# Taille maximale d'image (en octets) pour éviter saturation mémoire
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


# ============================================================
# VALIDATION
# ============================================================

def _valider_chemin_image(chemin):
    """
    Valide qu'un chemin d'image existe et a une extension supportée.
    
    Args:
        chemin: Chemin du fichier image
        
    Raises:
        FileNotFoundError: Si le fichier n'existe pas
        ValueError: Si l'extension n'est pas supportée ou fichier trop gros
    """
    if not os.path.isfile(chemin):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    extension = os.path.splitext(chemin)[1].lower()

    if extension not in EXTENSIONS_AUTORISEES:
        raise ValueError(
            f"Extension non supportée : '{extension}'. "
            f"Formats acceptés : {', '.join(sorted(EXTENSIONS_AUTORISEES))}"
        )
    
    # Vérifier la taille du fichier
    taille = os.path.getsize(chemin)
    
    if taille > MAX_IMAGE_SIZE:
        raise ValueError(
            f"Image trop volumineuse : {taille / 1024 / 1024:.1f} MB "
            f"(max : {MAX_IMAGE_SIZE / 1024 / 1024:.1f} MB)"
        )


def verifier_modele_vision():
    """
    Vérifie que le modèle vision est disponible.
    
    Returns:
        dict: Informations sur le modèle ou erreur
    """
    try:
        models = _client_vision.list()
        
        model_names = [m['name'] for m in models.get('models', [])]
        
        # Vérifier si le modèle exact ou une variante existe
        modele_trouve = any(
            VISION_MODEL in name 
            for name in model_names
        )
        
        return {
            "disponible": modele_trouve,
            "modele_demande": VISION_MODEL,
            "modeles_installes": model_names
        }
    
    except Exception as e:
        return {
            "disponible": False,
            "erreur": str(e)
        }


# ============================================================
# CAPTURE D'ÉCRAN
# ============================================================

def capturer_ecran(
    chemin=None,
    moniteur=1,
    avec_timestamp=True
):
    """
    Capture l'écran courant et l'enregistre sur disque.

    Utilise mss (multi-plateforme : Windows, macOS, Linux/X11) plutôt que
    PIL.ImageGrab, qui ne fonctionne pas de façon fiable sous Linux.
    
    Args:
        chemin: Chemin de sauvegarde (auto-généré si None)
        moniteur: Numéro du moniteur à capturer (1 = principal, 0 = tous)
        avec_timestamp: Ajouter timestamp au nom du fichier
        
    Returns:
        str: Chemin du fichier créé
        
    Raises:
        ImportError: Si mss n'est pas installé
        RuntimeError: Si la capture échoue
        
    Nécessite : pip install mss
    """
    try:
        import mss
        import mss.tools

        # Générer un nom de fichier si non fourni
        if chemin is None:
            if avec_timestamp:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nom_fichier = f"capture_ecran_{timestamp}.png"
            else:
                nom_fichier = "capture_ecran.png"
            
            chemin = str(SCREENSHOTS_DIR / nom_fichier)

        with mss.mss() as sct:
            
            # Vérifier que le moniteur existe
            if moniteur >= len(sct.monitors):
                moniteur = 1  # Fallback sur moniteur principal
                log_warning(
                    "vision",
                    f"Moniteur {moniteur} inexistant, utilisation du moniteur 1"
                )
            
            moniteur_obj = sct.monitors[moniteur]

            capture = sct.grab(moniteur_obj)

            mss.tools.to_png(capture.rgb, capture.size, output=chemin)

        log_event(
            "vision",
            f"Capture d'écran enregistrée : {chemin} "
            f"({capture.width}×{capture.height})"
        )

        return chemin

    except ImportError:
        log_error(
            "vision",
            "Module 'mss' non installé",
            exc_info=False
        )
        raise ImportError(
            "Le paquet 'mss' est requis pour capturer l'écran. "
            "Installe-le avec : pip install mss"
        )

    except Exception as e:
        log_error("vision", f"capturer_ecran échoué : {e}", exc_info=True)
        raise RuntimeError(f"Impossible de capturer l'écran : {e}")


def lister_moniteurs():
    """
    Liste tous les moniteurs disponibles.
    
    Returns:
        list: Liste des moniteurs avec leurs dimensions
    """
    try:
        import mss

        with mss.mss() as sct:
            moniteurs = []
            
            for i, mon in enumerate(sct.monitors):
                moniteurs.append({
                    "index": i,
                    "largeur": mon["width"],
                    "hauteur": mon["height"],
                    "x": mon["left"],
                    "y": mon["top"],
                    "nom": f"Moniteur {i}" if i > 0 else "Tous les écrans"
                })
            
            return moniteurs
    
    except ImportError:
        return {"error": "Module 'mss' non installé"}
    
    except Exception as e:
        log_warning("vision", f"lister_moniteurs échoué : {e}")
        return {"error": str(e)}


def capturer_zone(x, y, largeur, hauteur, chemin=None):
    """
    Capture une zone spécifique de l'écran.
    
    Args:
        x: Position X du coin supérieur gauche
        y: Position Y du coin supérieur gauche
        largeur: Largeur de la zone
        hauteur: Hauteur de la zone
        chemin: Chemin de sauvegarde (auto-généré si None)
        
    Returns:
        str: Chemin du fichier créé
    """
    try:
        import mss
        import mss.tools

        if chemin is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            chemin = str(SCREENSHOTS_DIR / f"capture_zone_{timestamp}.png")

        with mss.mss() as sct:
            zone = {
                "left": x,
                "top": y,
                "width": largeur,
                "height": hauteur
            }
            
            capture = sct.grab(zone)
            
            mss.tools.to_png(capture.rgb, capture.size, output=chemin)

        log_event(
            "vision",
            f"Zone capturée : {chemin} ({largeur}×{hauteur})"
        )

        return chemin

    except Exception as e:
        log_error("vision", f"capturer_zone échoué : {e}", exc_info=False)
        raise


# ============================================================
# ANALYSE D'IMAGE
# ============================================================

def analyser_image(chemin, question=None, detaille=False):
    """
    Décrit une image ou répond à une question précise à son sujet,
    via un modèle multimodal Ollama local.

    `chemin` peut venir d'une capture d'écran (capturer_ecran) ou d'un
    fichier fourni par l'utilisateur — traité de la même façon ici.
    
    Args:
        chemin: Chemin du fichier image à analyser
        question: Question spécifique (optionnel)
        detaille: Si True, demande une description plus détaillée
        
    Returns:
        str: Description ou réponse du modèle
        
    Raises:
        FileNotFoundError: Si l'image n'existe pas
        ValueError: Si le format n'est pas supporté
    """
    _valider_chemin_image(chemin)

    # Construire le prompt
    if question:
        prompt = question
    elif detaille:
        prompt = (
            "Décris cette image de façon très détaillée en français. "
            "Inclus tous les éléments visibles, les couleurs, le contexte, "
            "et toute information pertinente."
        )
    else:
        prompt = (
            "Décris cette image de façon claire et concise, en français."
        )

    try:
        with open(chemin, "rb") as f:
            image_bytes = f.read()

        log_event(
            "vision",
            f"Analyse image : {chemin} ({len(image_bytes) / 1024:.1f} KB)"
        )

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

        contenu = reponse["message"]["content"].strip()

        log_event(
            "vision",
            f"Image analysée, réponse : {len(contenu)} caractères"
        )

        return contenu

    except ConnectionError:
        log_warning("vision", "Ollama non disponible pour la vision")
        return (
            "❌ Je suis déconnecté d'Ollama. "
            "Assure-toi que 'ollama serve' est lancé."
        )

    except Exception as e:
        message_erreur = str(e).lower()

        if "not found" in message_erreur or "model" in message_erreur:
            log_error("vision", f"Modèle vision manquant : {e}", exc_info=False)
            return (
                f"❌ Le modèle vision '{VISION_MODEL}' n'est pas disponible.\n\n"
                f"Pour l'installer :\n"
                f"  ollama pull {VISION_MODEL}\n\n"
                f"Modèles vision recommandés :\n"
                f"  - llava (rapide, 4GB)\n"
                f"  - llava:13b (meilleur, 8GB)\n"
                f"  - bakllava (alternatif, 5GB)"
            )

        log_error("vision", f"analyser_image échoué : {e}", exc_info=False)
        return f"❌ Erreur lors de l'analyse de l'image : {str(e)[:150]}"


def comparer_images(chemin1, chemin2):
    """
    Compare deux images et décrit leurs différences.
    
    Args:
        chemin1: Chemin de la première image
        chemin2: Chemin de la seconde image
        
    Returns:
        str: Description des différences
    """
    _valider_chemin_image(chemin1)
    _valider_chemin_image(chemin2)

    try:
        with open(chemin1, "rb") as f1, open(chemin2, "rb") as f2:
            image1_bytes = f1.read()
            image2_bytes = f2.read()

        prompt = (
            "Compare ces deux images et décris leurs différences principales "
            "de façon claire et concise, en français."
        )

        reponse = _client_vision.chat(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image1_bytes, image2_bytes],
                }
            ],
        )

        return reponse["message"]["content"].strip()

    except Exception as e:
        log_error("vision", f"comparer_images échoué : {e}", exc_info=False)
        return f"❌ Erreur lors de la comparaison : {str(e)[:150]}"


# ============================================================
# RACCOURCIS
# ============================================================

def capturer_et_analyser(question=None, moniteur=1, detaille=False):
    """
    Raccourci : capture l'écran puis l'analyse immédiatement.
    
    Args:
        question: Question spécifique (optionnel)
        moniteur: Numéro du moniteur à capturer
        detaille: Si True, description détaillée
        
    Returns:
        str: Analyse de la capture d'écran
    """
    try:
        chemin = capturer_ecran(moniteur=moniteur)
        return analyser_image(chemin, question=question, detaille=detaille)
    
    except Exception as e:
        log_error("vision", f"capturer_et_analyser échoué : {e}", exc_info=False)
        return f"❌ Erreur : {str(e)[:150]}"


def lire_texte_image(chemin):
    """
    Extrait le texte visible dans une image (OCR via vision).
    
    Args:
        chemin: Chemin de l'image
        
    Returns:
        str: Texte extrait
    """
    prompt = (
        "Extrais TOUT le texte visible dans cette image, "
        "en conservant la structure et la mise en forme. "
        "Si aucun texte n'est visible, dis-le clairement."
    )
    
    return analyser_image(chemin, question=prompt)


def identifier_elements(chemin):
    """
    Identifie et liste tous les éléments présents dans une image.
    
    Args:
        chemin: Chemin de l'image
        
    Returns:
        str: Liste des éléments identifiés
    """
    prompt = (
        "Liste tous les éléments, objets et détails visibles dans cette image. "
        "Sois exhaustif et précis."
    )
    
    return analyser_image(chemin, question=prompt)


# ============================================================
# UTILITAIRES
# ============================================================

def obtenir_infos_image(chemin):
    """
    Obtient les métadonnées d'une image.
    
    Args:
        chemin: Chemin de l'image
        
    Returns:
        dict: Informations sur l'image
    """
    _valider_chemin_image(chemin)
    
    try:
        from PIL import Image
        
        with Image.open(chemin) as img:
            return {
                "format": img.format,
                "mode": img.mode,
                "largeur": img.width,
                "hauteur": img.height,
                "taille_fichier": os.path.getsize(chemin),
                "taille_lisible": f"{os.path.getsize(chemin) / 1024:.1f} KB",
                "chemin": chemin
            }
    
    except ImportError:
        # Fallback sans PIL
        return {
            "taille_fichier": os.path.getsize(chemin),
            "taille_lisible": f"{os.path.getsize(chemin) / 1024:.1f} KB",
            "chemin": chemin,
            "note": "Installe Pillow pour plus d'infos : pip install Pillow"
        }
    
    except Exception as e:
        return {"error": str(e)}


def nettoyer_anciennes_captures(jours=7):
    """
    Supprime les captures d'écran plus anciennes que N jours.
    
    Args:
        jours: Nombre de jours à conserver
        
    Returns:
        int: Nombre de fichiers supprimés
    """
    from datetime import timedelta
    
    seuil = datetime.now() - timedelta(days=jours)
    supprimes = 0
    
    try:
        for fichier in SCREENSHOTS_DIR.glob("capture_*.png"):
            timestamp_fichier = datetime.fromtimestamp(fichier.stat().st_mtime)
            
            if timestamp_fichier < seuil:
                fichier.unlink()
                supprimes += 1
        
        if supprimes > 0:
            log_event("vision", f"Nettoyage : {supprimes} captures supprimées")
        
        return supprimes
    
    except Exception as e:
        log_warning("vision", f"nettoyer_anciennes_captures échoué : {e}")
        return 0


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    'capturer_ecran',
    'lister_moniteurs',
    'capturer_zone',
    'analyser_image',
    'comparer_images',
    'capturer_et_analyser',
    'lire_texte_image',
    'identifier_elements',
    'obtenir_infos_image',
    'verifier_modele_vision',
    'nettoyer_anciennes_captures',
]