"""
CERVEAU — PATCHÉ v2.2
- Optimisé pour llama3.2:3b (rapide)
- num_predict réduits (512-1024 au lieu de 2048)
- Rétrocompatible : profil par défaut CONVERSATION
"""
import json
import os
import re
import time
import threading
from typing import Any, Dict, List, Optional
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv optionnel
    def load_dotenv(*a, **kw):
        return False
load_dotenv(override=True)

try:
    import requests
except ImportError:
    requests = None

try:
    from core import config as _cfg
except Exception:
    _cfg = None

def _cfg_value(name: str, default: Any) -> Any:
    if _cfg is None:
        return default
    return getattr(_cfg, name, default)

def _env_int(name: str, default: int, config_name: Optional[str] = None) -> int:
    if config_name is None:
        config_name = name
    value = os.getenv(name)
    if value is None:
        value = _cfg_value(config_name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _env_float(name: str, default: float, config_name: Optional[str] = None) -> float:
    if config_name is None:
        config_name = name
    value = os.getenv(name)
    if value is None:
        value = _cfg_value(config_name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

API = os.getenv("JIBI_LLM_API", "ollama").strip().lower()
URL = os.getenv("JIBI_LLM_URL", _cfg_value("OLLAMA_HOST", os.getenv("OLLAMA_URL", "http://localhost:11434"))).rstrip("/")
MODEL = os.getenv("JIBI_LLM_MODEL", _cfg_value("MODEL", os.getenv("OLLAMA_MODEL", "llama3.2:3b"))).strip()
KEY = os.getenv("JIBI_LLM_KEY", "").strip()
TIMEOUT = _env_int("JIBI_LLM_TIMEOUT", 60, "TIMEOUT_OLLAMA")  # ✅ Réduit
TIMEOUT_CODE = _env_int("JIBI_LLM_TIMEOUT_CODE", 120, "TIMEOUT_CODE")  # ✅ Réduit
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", _cfg_value("OLLAMA_KEEP_ALIVE", "24h"))  # ✅ 24h
OLLAMA_NUM_CTX = _env_int("OLLAMA_NUM_CTX", 4096, "OLLAMA_NUM_CTX")
OLLAMA_NUM_THREADS = _env_int("OLLAMA_NUM_THREAD", 4, "OLLAMA_NUM_THREADS")
OLLAMA_TEMPERATURE = _env_float("OLLAMA_TEMPERATURE", 0.5, "OLLAMA_TEMPERATURE")

# ✅ Profils P0 — num_predict OPTIMISÉS (plus rapide)
PROFILS = {
    "CONVERSATION":   {"num_predict": _env_int("OLLAMA_PREDICT_CHAT", 512, "OLLAMA_PREDICT_CHAT"), "temperature": _env_float("OLLAMA_TEMPERATURE_CHAT", 0.7, "OLLAMA_TEMPERATURE_CHAT")},
    "QUESTION":       {"num_predict": _env_int("OLLAMA_PREDICT_QUESTION", 512, "OLLAMA_PREDICT_QUESTION"), "temperature": 0.5},
    "CODE":           {"num_predict": _env_int("OLLAMA_PREDICT_CODE", 1024, "OLLAMA_PREDICT_CODE"), "temperature": _env_float("OLLAMA_TEMPERATURE_CODE", 0.2, "OLLAMA_TEMPERATURE_CODE")},
    "TACHE_COMPLEXE": {"num_predict": _env_int("OLLAMA_PREDICT_COMPLEXE", 1024, "OLLAMA_PREDICT_COMPLEXE"), "temperature": 0.5},
    "RECHERCHE":      {"num_predict": 512, "temperature": 0.3},
}

try:
    from core.prompts import PROMPT_SYSTEME
    SYSTEME_JIBI = PROMPT_SYSTEME.strip()
except Exception:
    SYSTEME_JIBI = ("Tu es JIBI, un assistant IA local écrit en Python. Tu peux aider l'utilisateur à utiliser son ordinateur, chercher des informations, travailler avec ses fichiers et proposer des améliorations de ton propre code. Toute modification du code doit être proposée puis validée explicitement par l'utilisateur avec J'AUTORISE <id>. Réponds en français, de façon concise, claire et concrète.")

def _system_for(profil: str) -> str:
    try:
        from core.prompts import PROMPT_BASE, PROMPT_CONVERSATION, PROMPT_CODE, PROMPT_RECHERCHE, PROMPT_ACTION
        m = {"CONVERSATION": PROMPT_CONVERSATION, "QUESTION": PROMPT_CONVERSATION, "CODE": PROMPT_CODE, "RECHERCHE": PROMPT_RECHERCHE, "TACHE_COMPLEXE": PROMPT_ACTION}
        return m.get(profil, PROMPT_BASE)
    except Exception:
        return SYSTEME_JIBI


def systeme_avec_memoire(profil: str = "CONVERSATION") -> str:
    """Prompt système enrichi des faits mémorisés (SQLite, zéro config).

    C'est ce qui donne à JIBI une vraie continuité : il se souvient de
    l'utilisateur d'une session à l'autre, sans serveur MySQL.
    """
    base = _system_for(profil)
    try:
        import memoire_locale
        faits = memoire_locale.formater_faits()
    except Exception:
        faits = ""
    if faits:
        return base + "\n\n" + faits + "\n(Utilise ces souvenirs quand c'est pertinent.)"
    return base

_cache_dispo: Optional[bool] = None
_cache_t = 0

def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if KEY:
        headers["Authorization"] = f"Bearer {KEY}"
    return headers

def disponible(force: bool = False) -> bool:
    global _cache_dispo, _cache_t
    if _cache_dispo is not None and not force and time.time() - _cache_t < 10:
        return bool(_cache_dispo)
    if requests is None:
        _cache_dispo = False
        _cache_t = time.time()
        return False
    try:
        if API == "ollama":
            response = requests.get(f"{URL}/api/tags", timeout=3)
        else:
            response = requests.get(f"{URL}/models", headers=_headers(), timeout=3)
        _cache_dispo = response.status_code == 200
    except Exception:
        _cache_dispo = False
    _cache_t = time.time()
    return bool(_cache_dispo)

def completer(user: str, system: str = None, profil: str = "CONVERSATION", stream: bool = False, on_chunk=None, cancel_event: threading.Event = None, json_mode: bool = False, temperature: Optional[float] = None) -> str:
    if requests is None:
        raise RuntimeError("Le module 'requests' est requis. pip install requests")

    # ✅ OPTION C — Modèle selon profil (pour futur qwen2.5-coder:7b)
    global MODEL
    if profil == "CODE":
        model_to_use = os.getenv("JIBI_LLM_MODEL_CODE", MODEL)  # Permet modèle différent pour code
    else:
        model_to_use = MODEL

    cfg = PROFILS.get(profil, PROFILS["CONVERSATION"])
    if temperature is None:
        temperature = cfg["temperature"]
    if system is None:
        system = systeme_avec_memoire(profil)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    timeout = TIMEOUT_CODE if profil in ("CODE", "TACHE_COMPLEXE") else TIMEOUT

    if API == "ollama":
        options = {"temperature": temperature, "num_ctx": OLLAMA_NUM_CTX, "num_predict": cfg["num_predict"], "num_thread": OLLAMA_NUM_THREADS}
        body = {"model": model_to_use, "messages": messages, "stream": stream, "keep_alive": OLLAMA_KEEP_ALIVE, "options": options}
        if json_mode:
            body["format"] = "json"
        if not stream:
            t0 = time.perf_counter()
            response = requests.post(f"{URL}/api/chat", json=body, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            try:
                txt = data["message"]["content"]
            except (KeyError, TypeError) as exc:
                raise RuntimeError(f"Réponse Ollama invalide : {data!r}") from exc
            return txt
        # streaming
        full = []
        t0 = time.perf_counter()
        ttft = None
        with requests.post(f"{URL}/api/chat", json=body, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if cancel_event and cancel_event.is_set():
                    try:
                        r.close()
                    except Exception:
                        pass
                    break
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    full.append(chunk)
                    if on_chunk:
                        try:
                            on_chunk(chunk)
                        except Exception:
                            pass
                if data.get("done"):
                    break
        return "".join(full)
    # OpenAI compatible
    body = {"model": model_to_use, "messages": messages, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    response = requests.post(f"{URL}/chat/completions", json=body, headers=_headers(), timeout=timeout)
    response.raise_for_status()
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Réponse OpenAI-compatible invalide : {data!r}") from exc

def completer_json(user: str, system: str = None, profil: str = "TACHE_COMPLEXE") -> dict:
    txt = completer(user, system=system, profil=profil, json_mode=True)
    try:
        data = json.loads(txt)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}

def extraire_code(txt: str) -> str:
    if not txt:
        return ""
    m = re.search(r"```(?:python|py)?\s*\n?(.*?)```", txt, re.DOTALL | re.IGNORECASE)
    code = m.group(1) if m else txt
    return code.strip() + "\n"

def planifier(message: str, contexte: str = "") -> dict:
    prompt = f"""
Analyse la demande de l'utilisateur et renvoie UNIQUEMENT un JSON.
Format obligatoire :
{{
  "intention": "modifier_fichier | creer_outil | diagnostic | rechercher_web | executer_outil | etat | liste | discussion",
  "fichier": "chemin relatif si modifier_fichier, sinon null",
  "nom_outil": "nom_snake_case si creer_outil ou executer_outil, sinon null",
  "arguments": {{}},
  "description": "ce qu'il faut faire, reformulé précisément",
  "requete": "requête de recherche si rechercher_web, sinon null",
  "reponse": "réponse courte si discussion, sinon null"
}}
Contexte : {contexte}
Demande utilisateur : {message}
"""
    return completer_json(prompt, profil="TACHE_COMPLEXE")

def _budget_caracteres_fichier() -> int:
    """
    Calcule combien de caractères de code on peut se permettre d'envoyer dans le prompt
    sans dépasser OLLAMA_NUM_CTX (au lieu d'une limite fixe de 15000 caractères qui,
    sur un num_ctx=4096, sature/tronque silencieusement la fenêtre de contexte).
    Approximation : ~3.5 caractères/token pour du code Python.
    """
    marge_reponse = PROFILS["CODE"]["num_predict"] * 4       # place réservée à la génération
    marge_prompt = 400                                        # instructions + nom fichier + demande
    tokens_dispo = max(500, OLLAMA_NUM_CTX - marge_reponse // 4 - marge_prompt // 4)
    return max(2000, int(tokens_dispo * 3.5))

def reecrire_fichier(fichier: str, contenu_actuel: str, demande: str) -> str:
    budget = _budget_caracteres_fichier()
    contenu_envoye = contenu_actuel[:budget]
    tronque = len(contenu_actuel) > budget
    prompt = f"""
Tu dois modifier le fichier "{fichier}" de JIBI selon cette demande : {demande}
Contraintes : garde les fonctionnalités existantes, ne casse pas les imports, code Python 3.10+ valide.
Renvoie le fichier COMPLET dans un seul bloc Markdown Python.
{"⚠️ Le contenu ci-dessous est tronqué (fichier trop long pour le contexte disponible) — ne réécris que ce que tu vois, sans supposer le reste." if tronque else ""}
Contenu actuel :
--- DEBUT ---
{contenu_envoye}
--- FIN ---
"""
    return extraire_code(completer(prompt, profil="CODE", temperature=0.2))

def creer_outil(nom: str, description: str) -> str:
    prompt = f"""
Crée un nouvel outil Python pour JIBI.
Nom : {nom}
Description : {description}
Contraintes : Python 3.10+, code simple et robuste, respecte l'architecture des outils de JIBI.
Renvoie uniquement le code Python complet dans un seul bloc Markdown Python.
"""
    return extraire_code(completer(prompt, profil="CODE", temperature=0.2))

def diagnostiquer(analyse: dict, fichiers: dict) -> list:
    contenu = ["ANALYSE :", json.dumps(analyse or {}, ensure_ascii=False, indent=2), "\nFICHIERS :"]
    for nom, texte in list((fichiers or {}).items())[:3]:
        contenu.append(f"\n===== {nom} =====\n{texte[:1500]}")
    prompt = f"""
Tu es chargé du diagnostic technique de JIBI.
Analyse et propose des améliorations réalistes et sûres.
{chr(10).join(contenu)}
Renvoie UNIQUEMENT un JSON : {{"idees": [{{"fichier": "...", "titre": "...", "description": "...", "priorite": "basse|moyenne|haute"}}]}}
"""
    resultat = completer_json(prompt, profil="TACHE_COMPLEXE")
    if isinstance(resultat, dict):
        idees = resultat.get("idees", [])
        if isinstance(idees, list):
            return idees
    return []

def resumer_recherche(requete: str, resultats: str) -> str:
    prompt = f"""Résume les résultats suivants en français.
Requête : {requete}
Résultats : {resultats[:4000]}
Contraintes : réponse claire et concise."""
    return completer(prompt, profil="RECHERCHE", temperature=0.2)