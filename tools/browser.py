
# AUTO-AMÉLIORATION SUGGÉRÉE
# ===========================
# Problème identifié :
# Correction de : Améliore tools/browser.py : ajouter une gestion des timeouts
#
# Action recommandée :
# Révision manuelle nécessaire pour cette amélioration.
# Consulte les logs pour plus de détails.
"""
Navigateur — contrôle via Playwright.

Sécurité :
- seuls les schémas http/https sont acceptés (pas de file://, data:, etc.
  qui pourraient lire des fichiers locaux ou exécuter du JS arbitraire) ;
- une seule instance de navigateur à la fois, ouverte à la demande
  (jamais à l'import) ;
- aucune fermeture d'onglet/navigateur automatique en arrière-plan sans
  appel explicite à fermer_navigateur() ;
- timeout configurable pour éviter les blocages infinis ;
- validation stricte des URLs et sélecteurs CSS.

Performance :
- Navigateur lancé uniquement à la première utilisation (lazy loading) ;
- Réutilisation de l'instance pour les appels suivants ;
- Headless par défaut pour économiser les ressources.
"""

import os
from urllib.parse import urlparse
from pathlib import Path

from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)


# ============================================================
# CONFIGURATION
# ============================================================

BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "0") != "0"
BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_TIMEOUT_MS", "15000"))

# Schémas d'URL autorisés (sécurité)
SCHEMAS_AUTORISES = {"http", "https"}

# Dossier pour les captures d'écran
SCREENSHOTS_DIR = Path(os.getenv("JIBI_PROJET_DIR", ".")) / "workspace" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# ÉTAT GLOBAL (instance unique)
# ============================================================

_playwright = None
_navigateur = None
_page = None


# ============================================================
# VALIDATION
# ============================================================

def _valider_url(url):
    """
    Valide qu'une URL utilise un schéma autorisé (http/https).
    
    Args:
        url: URL à valider
        
    Raises:
        ValueError: Si le schéma n'est pas autorisé
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL invalide : doit être une chaîne non vide")
    
    schema = urlparse(url).scheme.lower()

    if schema not in SCHEMAS_AUTORISES:
        raise ValueError(
            f"Schéma d'URL non autorisé : '{schema}'. "
            f"Seuls http et https sont acceptés."
        )


def _valider_selecteur(selecteur):
    """
    Valide qu'un sélecteur CSS est sûr.
    
    Args:
        selecteur: Sélecteur CSS à valider
        
    Raises:
        ValueError: Si le sélecteur est invalide
    """
    if not selecteur or not isinstance(selecteur, str):
        raise ValueError("Sélecteur invalide : doit être une chaîne non vide")
    
    # Interdire les sélecteurs potentiellement dangereux
    selecteur_lower = selecteur.lower()
    
    interdits = [
        "javascript:",
        "data:",
        "<script",
        "onclick",
        "onerror",
    ]
    
    for interdit in interdits:
        if interdit in selecteur_lower:
            raise ValueError(
                f"Sélecteur potentiellement dangereux : contient '{interdit}'"
            )


# ============================================================
# GESTION DU NAVIGATEUR
# ============================================================

def _obtenir_page():
    """
    Lance Playwright/le navigateur au premier besoin, réutilise ensuite.
    
    Returns:
        Page: Instance Playwright de la page active
        
    Raises:
        RuntimeError: Si Playwright ne peut pas démarrer
    """
    global _playwright, _navigateur, _page

    if _page is not None:
        return _page

    try:
        from playwright.sync_api import sync_playwright

        _playwright = sync_playwright().start()

        _navigateur = _playwright.chromium.launch(
            headless=BROWSER_HEADLESS
        )

        _page = _navigateur.new_page()

        _page.set_default_timeout(BROWSER_TIMEOUT_MS)

        log_event(
            "browser",
            f"Navigateur Playwright démarré (headless={BROWSER_HEADLESS})"
        )

        return _page

    except ImportError:
        log_error(
            "browser",
            "Playwright non installé. Installe-le avec : pip install playwright && playwright install chromium",
            exc_info=False
        )
        raise RuntimeError(
            "Playwright non disponible. "
            "Installe-le avec : pip install playwright && playwright install chromium"
        )

    except Exception as e:
        log_error(
            "browser",
            f"Impossible de démarrer Playwright : {e}",
            exc_info=True
        )
        raise RuntimeError(f"Échec du démarrage du navigateur : {e}")


def est_navigateur_ouvert():
    """
    Vérifie si le navigateur est actuellement ouvert.
    
    Returns:
        bool: True si le navigateur est ouvert
    """
    return _page is not None


# ============================================================
# NAVIGATION
# ============================================================

def ouvrir_url(url):
    """
    Navigue vers l'URL donnée. Lance le navigateur si nécessaire.
    
    Args:
        url: URL à ouvrir (http/https uniquement)
        
    Returns:
        str: Message de confirmation avec titre de la page
        
    Raises:
        ValueError: Si l'URL n'est pas valide
        RuntimeError: Si la navigation échoue
    """
    _valider_url(url)

    try:
        page = _obtenir_page()
        
        # Navigation avec stratégie de chargement optimisée
        page.goto(url, wait_until="domcontentloaded")

        titre = page.title() or "Sans titre"
        
        log_event("browser", f"Page ouverte : {titre} ({url})")

        return f"✓ Page ouverte : {titre} ({url})"

    except Exception as e:
        log_error(
            "browser",
            f"ouvrir_url échoué pour {url} : {e}",
            exc_info=False
        )
        
        # Message d'erreur user-friendly
        if "timeout" in str(e).lower():
            return f"✗ Timeout lors du chargement de {url} (délai max : {BROWSER_TIMEOUT_MS}ms)"
        elif "net::" in str(e).lower():
            return f"✗ Impossible d'accéder à {url} (vérifier la connexion Internet)"
        else:
            return f"✗ Erreur lors de l'ouverture de {url} : {str(e)[:200]}"


def lire_titre():
    """
    Lit le titre de la page actuellement ouverte.
    
    Returns:
        str: Titre de la page ou message d'erreur
    """
    if _page is None:
        return "Aucune page ouverte."

    try:
        titre = _page.title()
        return titre or "Page sans titre"
    
    except Exception as e:
        log_warning("browser", f"lire_titre échoué : {e}")
        return "Impossible de lire le titre de la page"


def obtenir_url_courante():
    """
    Obtient l'URL de la page actuellement ouverte.
    
    Returns:
        str: URL de la page ou message d'erreur
    """
    if _page is None:
        return "Aucune page ouverte."

    try:
        return _page.url
    
    except Exception as e:
        log_warning("browser", f"obtenir_url_courante échoué : {e}")
        return "Impossible d'obtenir l'URL"


# ============================================================
# LECTURE DU CONTENU
# ============================================================

def obtenir_texte_page(max_caracteres=3000):
    """
    Texte visible de la page courante, tronqué (évite de saturer le contexte).
    
    Args:
        max_caracteres: Nombre maximum de caractères à retourner
        
    Returns:
        str: Texte de la page (tronqué) ou message d'erreur
    """
    if _page is None:
        return "Aucune page ouverte."

    try:
        texte = _page.inner_text("body")
        
        if len(texte) > max_caracteres:
            texte = texte[:max_caracteres] + f"\n\n... (tronqué à {max_caracteres} caractères)"
        
        return texte

    except Exception as e:
        log_warning("browser", f"obtenir_texte_page échoué : {e}")
        return f"Impossible de lire le texte de la page : {str(e)[:100]}"


def obtenir_liens():
    """
    Obtient tous les liens (balises <a>) de la page.
    
    Returns:
        list: Liste de dicts {'texte': str, 'url': str}
    """
    if _page is None:
        return {"error": "Aucune page ouverte."}

    try:
        liens = _page.evaluate("""
            () => {
                const anchors = Array.from(document.querySelectorAll('a'));
                return anchors.map(a => ({
                    texte: a.innerText.trim(),
                    url: a.href
                })).filter(l => l.url && l.texte);
            }
        """)
        
        return liens[:50]  # Limiter à 50 liens pour éviter surcharge
    
    except Exception as e:
        log_warning("browser", f"obtenir_liens échoué : {e}")
        return {"error": str(e)}


# ============================================================
# INTERACTION
# ============================================================

def cliquer(selecteur):
    """
    Clique sur un élément de la page via un sélecteur CSS.
    
    Args:
        selecteur: Sélecteur CSS de l'élément
        
    Returns:
        str: Message de confirmation ou d'erreur
        
    Raises:
        RuntimeError: Si aucune page n'est ouverte
    """
    if _page is None:
        raise RuntimeError("Aucune page ouverte. Utilise ouvrir_url d'abord.")

    _valider_selecteur(selecteur)

    try:
        _page.click(selecteur)

        log_event("browser", f"Clic sur : {selecteur}")

        return f"✓ Cliqué sur '{selecteur}'"

    except Exception as e:
        log_warning("browser", f"cliquer échoué : {e}")
        
        if "timeout" in str(e).lower():
            return f"✗ Élément '{selecteur}' non trouvé (timeout)"
        else:
            return f"✗ Impossible de cliquer sur '{selecteur}' : {str(e)[:100]}"


def remplir_champ(selecteur, texte):
    """
    Remplit un champ de formulaire via un sélecteur CSS.
    
    Args:
        selecteur: Sélecteur CSS du champ
        texte: Texte à saisir
        
    Returns:
        str: Message de confirmation ou d'erreur
        
    Raises:
        RuntimeError: Si aucune page n'est ouverte
    """
    if _page is None:
        raise RuntimeError("Aucune page ouverte. Utilise ouvrir_url d'abord.")

    _valider_selecteur(selecteur)

    try:
        _page.fill(selecteur, str(texte))

        log_event("browser", f"Champ '{selecteur}' rempli")

        return f"✓ Champ '{selecteur}' rempli avec '{texte[:50]}...'"

    except Exception as e:
        log_warning("browser", f"remplir_champ échoué : {e}")
        
        if "timeout" in str(e).lower():
            return f"✗ Champ '{selecteur}' non trouvé (timeout)"
        else:
            return f"✗ Impossible de remplir '{selecteur}' : {str(e)[:100]}"


def appuyer_touche(touche):
    """
    Simule l'appui sur une touche (Enter, Tab, Escape, etc.).
    
    Args:
        touche: Nom de la touche (voir doc Playwright)
        
    Returns:
        str: Message de confirmation ou d'erreur
    """
    if _page is None:
        raise RuntimeError("Aucune page ouverte. Utilise ouvrir_url d'abord.")

    try:
        _page.keyboard.press(touche)
        
        log_event("browser", f"Touche pressée : {touche}")
        
        return f"✓ Touche '{touche}' pressée"
    
    except Exception as e:
        log_warning("browser", f"appuyer_touche échoué : {e}")
        return f"✗ Impossible de presser '{touche}' : {str(e)[:100]}"


# ============================================================
# CAPTURE D'ÉCRAN
# ============================================================

def capturer_ecran_page(nom_fichier=None):
    """
    Capture une image de la page actuellement ouverte.
    
    Args:
        nom_fichier: Nom du fichier (optionnel, auto-généré si absent)
        
    Returns:
        str: Chemin du fichier créé
        
    Raises:
        RuntimeError: Si aucune page n'est ouverte
    """
    if _page is None:
        raise RuntimeError("Aucune page ouverte. Utilise ouvrir_url d'abord.")

    try:
        from datetime import datetime
        
        if nom_fichier is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nom_fichier = f"capture_page_{timestamp}.png"
        
        chemin = SCREENSHOTS_DIR / nom_fichier
        
        _page.screenshot(path=str(chemin), full_page=True)

        log_event("browser", f"Capture de page : {chemin}")

        return str(chemin)

    except Exception as e:
        log_error("browser", f"capturer_ecran_page échoué : {e}", exc_info=False)
        raise


# ============================================================
# FERMETURE
# ============================================================

def fermer_navigateur():
    """
    Ferme proprement le navigateur et Playwright.
    Sûr à appeler plusieurs fois (idempotent).
    
    Returns:
        str: Message de confirmation
    """
    global _playwright, _navigateur, _page

    try:
        if _navigateur is not None:
            _navigateur.close()

        if _playwright is not None:
            _playwright.stop()

    except Exception as e:
        log_warning("browser", f"Erreur lors de la fermeture : {e}")

    finally:
        _navigateur = None
        _playwright = None
        _page = None

        log_event("browser", "Navigateur fermé")

    return "✓ Navigateur fermé"


# ============================================================
# UTILITAIRES
# ============================================================

def attendre(ms):
    """
    Attend un certain nombre de millisecondes.
    
    Args:
        ms: Nombre de millisecondes à attendre
        
    Returns:
        str: Message de confirmation
    """
    if _page is None:
        raise RuntimeError("Aucune page ouverte.")
    
    _page.wait_for_timeout(ms)
    
    return f"✓ Attendu {ms}ms"


def executer_javascript(code):
    """
    Exécute du code JavaScript dans la page.
    
    ATTENTION : Fonction avancée, à utiliser avec précaution.
    
    Args:
        code: Code JavaScript à exécuter
        
    Returns:
        any: Résultat de l'exécution
    """
    if _page is None:
        raise RuntimeError("Aucune page ouverte.")
    
    try:
        resultat = _page.evaluate(code)
        
        log_event("browser", "JavaScript exécuté")
        
        return resultat
    
    except Exception as e:
        log_warning("browser", f"executer_javascript échoué : {e}")
        return {"error": str(e)}


# ============================================================
# ÉTAT
# ============================================================

def obtenir_etat_navigateur():
    """
    Obtient l'état actuel du navigateur.
    
    Returns:
        dict: Informations sur l'état du navigateur
    """
    return {
        "ouvert": est_navigateur_ouvert(),
        "url": obtenir_url_courante() if _page else None,
        "titre": lire_titre() if _page else None,
        "headless": BROWSER_HEADLESS,
        "timeout_ms": BROWSER_TIMEOUT_MS
    }


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    'ouvrir_url',
    'lire_titre',
    'obtenir_url_courante',
    'obtenir_texte_page',
    'obtenir_liens',
    'cliquer',
    'remplir_champ',
    'appuyer_touche',
    'capturer_ecran_page',
    'fermer_navigateur',
    'attendre',
    'executer_javascript',
    'est_navigateur_ouvert',
    'obtenir_etat_navigateur',
]