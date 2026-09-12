"""
Navigateur — contrôle via Playwright.

Sécurité :
- seuls les schémas http/https sont acceptés (pas de file://, data:, etc.
  qui pourraient lire des fichiers locaux ou exécuter du JS arbitraire) ;
- une seule instance de navigateur à la fois, ouverte à la demande
  (jamais à l'import) ;
- aucune fermeture d'onglet/navigateur automatique en arrière-plan sans
  appel explicite à fermer_navigateur().
"""

import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "0") != "0"
BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_TIMEOUT_MS", "15000"))

SCHEMAS_AUTORISES = {"http", "https"}

_playwright = None
_navigateur = None
_page = None


def _valider_url(url):
    schema = urlparse(url).scheme.lower()

    if schema not in SCHEMAS_AUTORISES:
        raise ValueError(
            f"Schéma d'URL non autorisé : '{schema}'. "
            f"Seuls http et https sont acceptés."
        )


def _obtenir_page():
    """Lance Playwright/le navigateur au premier besoin, réutilise ensuite."""

    global _playwright, _navigateur, _page

    if _page is not None:
        return _page

    from playwright.sync_api import sync_playwright

    _playwright = sync_playwright().start()

    _navigateur = _playwright.chromium.launch(
        headless=BROWSER_HEADLESS
    )

    _page = _navigateur.new_page()

    _page.set_default_timeout(BROWSER_TIMEOUT_MS)

    log_event("browser", "Navigateur Playwright démarré")

    return _page


def ouvrir_url(url):
    """Navigue vers l'URL donnée. Lance le navigateur si nécessaire."""

    _valider_url(url)

    try:
        page = _obtenir_page()
        page.goto(url, wait_until="domcontentloaded")

        log_event("browser", f"Page ouverte: {url}")

        return f"Page ouverte : {page.title()} ({url})"

    except Exception as e:
        log_error("browser", f"ouvrir_url échoué: {e}", exc_info=False)
        raise


def lire_titre():
    if _page is None:
        return "Aucune page ouverte."

    return _page.title()


def obtenir_texte_page(max_caracteres=3000):
    """Texte visible de la page courante, tronqué (évite de saturer le contexte)."""

    if _page is None:
        return "Aucune page ouverte."

    try:
        texte = _page.inner_text("body")
        return texte[:max_caracteres]

    except Exception as e:
        log_warning("browser", f"obtenir_texte_page échoué: {e}")
        return f"Impossible de lire le texte de la page : {e}"


def cliquer(selecteur):
    if _page is None:
        raise RuntimeError("Aucune page ouverte. Utilise ouvrir_url d'abord.")

    _page.click(selecteur)

    log_event("browser", f"Clic sur: {selecteur}")

    return f"Cliqué sur '{selecteur}'."


def remplir_champ(selecteur, texte):
    if _page is None:
        raise RuntimeError("Aucune page ouverte. Utilise ouvrir_url d'abord.")

    _page.fill(selecteur, texte)

    log_event("browser", f"Champ '{selecteur}' rempli")

    return f"Champ '{selecteur}' rempli."


def capturer_ecran_page(chemin="capture_page.png"):
    if _page is None:
        raise RuntimeError("Aucune page ouverte. Utilise ouvrir_url d'abord.")

    _page.screenshot(path=chemin, full_page=True)

    log_event("browser", f"Capture de page: {chemin}")

    return chemin


def fermer_navigateur():
    """Ferme proprement le navigateur et Playwright. Sûr à appeler plusieurs fois."""

    global _playwright, _navigateur, _page

    if _navigateur is not None:
        _navigateur.close()

    if _playwright is not None:
        _playwright.stop()

    _navigateur = None
    _playwright = None
    _page = None

    log_event("browser", "Navigateur fermé")

    return "Navigateur fermé."