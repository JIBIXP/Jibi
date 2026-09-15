"""
Recherche web pour JIBI (tools/web_search.py).

Ordre de priorité :
  1. Tavily  (si TAVILY_API_KEY dans .env)  → résultats propres + extraits
  2. DuckDuckGo HTML (sans clé)             → secours automatique

lire_page() : ouvre l'URL avec tools/browser.py (Playwright) ; secours requests.
Aucune exception ne remonte : toutes les fonctions renvoient un dict avec "ok".
"""

import os
import re
import html
from urllib.parse import unquote, urlparse, parse_qs

from dotenv import load_dotenv

load_dotenv(override=True)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from logging_jibi import log_event, log_warning
except Exception:  # pragma: no cover
    def log_event(cat, msg): print(f"[{cat}] {msg}")
    def log_warning(cat, msg): print(f"[{cat}] ⚠️ {msg}")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JIBI/3.0"}
TIMEOUT = int(os.getenv("WEB_SEARCH_TIMEOUT", "20"))
TAVILY_KEY = os.getenv("TAVILY_API_KEY", "").strip()
SITES_VIDEOS = ["youtube.com", "dailymotion.com", "vimeo.com"]


# ============================================================
# MOTEURS
# ============================================================

def _tavily(requete: str, max_resultats: int, type_contenu: str) -> list:
    if not TAVILY_KEY or TAVILY_KEY.lower() == "xxx":
        return []
    body = {"api_key": TAVILY_KEY, "query": requete, "max_results": max_resultats,
            "search_depth": "basic"}
    if type_contenu == "videos":
        body["include_domains"] = SITES_VIDEOS
    r = requests.post("https://api.tavily.com/search", json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return [{
        "titre": (x.get("title") or "").strip(),
        "url": x.get("url", ""),
        "extrait": (x.get("content") or "").strip()[:300],
        "source": "tavily",
    } for x in r.json().get("results", []) if x.get("url")]


def _duckduckgo(requete: str, max_resultats: int, type_contenu: str) -> list:
    q = requete + (" site:youtube.com" if type_contenu == "videos" else "")
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": q}, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    resultats = []
    motif = re.compile(
        r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
    for m in motif.finditer(r.text):
        url = m.group(1)
        if "uddg=" in url:
            url = unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0])
        resultats.append({
            "titre": html.unescape(re.sub(r"<.*?>", "", m.group(2))).strip(),
            "url": url,
            "extrait": html.unescape(re.sub(r"<.*?>", "", m.group(3))).strip()[:300],
            "source": "duckduckgo",
        })
        if len(resultats) >= max_resultats:
            break
    return resultats


# ============================================================
# API PUBLIQUE
# ============================================================

def rechercher(requete: str, max_resultats: int = 8, type_contenu: str = "web") -> dict:
    """
    Recherche sur internet.
    Args:
        requete: texte à chercher
        max_resultats: 1-20
        type_contenu: "web" ou "videos"
    Returns:
        {"ok": bool, "moteur": str, "requete": str, "resultats": [{"titre","url","extrait"}], "erreur"?: str}
    """
    if requests is None:
        return {"ok": False, "erreur": "Module 'requests' manquant : pip install requests"}
    requete = (requete or "").strip()
    if not requete:
        return {"ok": False, "erreur": "Requête vide"}
    max_resultats = max(1, min(int(max_resultats or 8), 20))
    type_contenu = "videos" if str(type_contenu).lower().startswith("vid") else "web"

    erreurs = []
    for nom, moteur in (("tavily", _tavily), ("duckduckgo", _duckduckgo)):
        try:
            res = moteur(requete, max_resultats, type_contenu)
            if res:
                log_event("web_search", f"{nom} : {len(res)} résultat(s) pour « {requete} »")
                return {"ok": True, "moteur": nom, "requete": requete, "resultats": res}
            if nom == "duckduckgo":
                erreurs.append("duckduckgo : aucun résultat")
        except Exception as e:
            erreurs.append(f"{nom} : {e}")
            log_warning("web_search", f"{nom} échoué : {e}")

    return {"ok": False, "requete": requete, "resultats": [], "erreur": " | ".join(erreurs) or "Aucun résultat"}


def rechercher_videos(requete: str, max_resultats: int = 8) -> dict:
    """Raccourci : recherche de vidéos (YouTube, Dailymotion, Vimeo)."""
    return rechercher(requete, max_resultats, "videos")


def lire_page(url: str, max_caracteres: int = 4000) -> dict:
    """
    Lit le texte visible d'une page. Playwright (tools/browser.py) d'abord, requests en secours.
    Returns: {"ok": bool, "url": str, "titre"?: str, "texte": str, "methode": str}
    """
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "erreur": "URL invalide : http(s) uniquement"}
    max_caracteres = max(200, min(int(max_caracteres or 4000), 20000))

    # 1) Navigateur JIBI
    try:
        from tools import browser
        msg = browser.ouvrir_url(url)
        if isinstance(msg, str) and msg.startswith("✓"):
            return {"ok": True, "url": url, "titre": browser.lire_titre(),
                    "texte": browser.obtenir_texte_page(max_caracteres), "methode": "playwright"}
        log_warning("web_search", f"navigateur : {msg}")
    except Exception as e:
        log_warning("web_search", f"navigateur indisponible : {e}")

    # 2) Secours requests
    if requests is None:
        return {"ok": False, "url": url, "erreur": "Ni Playwright ni requests disponibles"}
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        brut = r.text
        titre = re.search(r"<title[^>]*>(.*?)</title>", brut, re.I | re.S)
        txt = re.sub(r"<(script|style|noscript).*?</\1>", " ", brut, flags=re.S | re.I)
        txt = html.unescape(re.sub(r"<.*?>", " ", txt))
        txt = re.sub(r"\s+", " ", txt).strip()
        return {"ok": True, "url": url, "titre": html.unescape(titre.group(1)).strip() if titre else "",
                "texte": txt[:max_caracteres], "methode": "requests"}
    except Exception as e:
        return {"ok": False, "url": url, "erreur": str(e)}


def formater_resultats(resultat: dict) -> str:
    """Texte lisible pour le chat."""
    if not resultat.get("ok"):
        return f"❌ Recherche impossible : {resultat.get('erreur', '?')}"
    lignes = [f"🌐 {len(resultat['resultats'])} résultat(s) via {resultat.get('moteur')} pour « {resultat['requete']} » :\n"]
    for i, x in enumerate(resultat["resultats"], 1):
        lignes.append(f"{i}. {x['titre']}\n   {x['url']}")
        if x.get("extrait"):
            lignes.append(f"   {x['extrait']}")
    return "\n".join(lignes)


# ============================================================
# ENREGISTREMENT (lu par tools/__init__.py)
# ============================================================

_S, _I = {"type": "string"}, {"type": "integer"}

OUTILS = {
    "rechercher_web": {
        "fonction": rechercher,
        "description": "Recherche des sites ou vidéos sur internet (Tavily ou DuckDuckGo).",
        "parametres": {"type": "object",
                       "properties": {"requete": _S, "max_resultats": _I,
                                      "type_contenu": {"type": "string", "enum": ["web", "videos"]}},
                       "required": ["requete"]},
    },
    "rechercher_videos": {
        "fonction": rechercher_videos,
        "description": "Recherche des vidéos (YouTube, Dailymotion, Vimeo).",
        "parametres": {"type": "object", "properties": {"requete": _S, "max_resultats": _I}, "required": ["requete"]},
    },
    "lire_page": {
        "fonction": lire_page,
        "description": "Lit le texte visible d'une page web.",
        "parametres": {"type": "object", "properties": {"url": _S, "max_caracteres": _I}, "required": ["url"]},
    },
}

__all__ = ["rechercher", "rechercher_videos", "lire_page", "formater_resultats", "OUTILS"]


if __name__ == "__main__":
    print(formater_resultats(rechercher("tkinter design moderne", 5)))
    print()
    print(formater_resultats(rechercher_videos("tkinter tutoriel français", 3)))