"""
memory_manager.py  (v3)
========================

Couche de mémoire sémantique pour JIBI, branchée sur la table `memoire`
existante (user_id, cle, valeur, embedding) de database.py.

Ne remplace PAS remember_memory_db / recall_db : les complète.
  - remember_memory_db / recall_db  -> lecture/écriture exacte par clé
  - memory_manager                  -> embedding par souvenir + recherche par SENS

Prérequis :
    pip install numpy requests python-dotenv
    ollama pull nomic-embed-text

v3 :
- charge le .env (OLLAMA_URL / modèles cohérents avec core/cerveau.py)
- cache LRU maison : les échecs (timeout) ne sont JAMAIS mis en cache
- EXTRACT_MODEL = JIBI_LLM_MODEL (un seul LLM chargé dans Ollama → pas de OOM)
- verifier_modele_embeddings() tolère le suffixe ":latest"
- statistiques cache exactes (hits / misses)
"""

import os
import json
import time
import threading
import queue
import concurrent.futures
from collections import OrderedDict
from typing import List, Dict

import requests
import numpy as np
from dotenv import load_dotenv

load_dotenv(override=True)

from database import (
    remember_memory_db,
    sauvegarder_embedding,
    obtenir_memoires_avec_embeddings,
)
from logging_jibi import log_event, log_warning, log_error

# ============================================================
# CONFIGURATION
# ============================================================

OLLAMA_URL = os.getenv("JIBI_LLM_URL") or os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
# Même modèle que le cerveau JIBI → un seul LLM résident dans Ollama
EXTRACT_MODEL = os.getenv("JIBI_LLM_MODEL") or os.getenv("OLLAMA_MODEL", "llama3.2:3b")

SIMILARITY_THRESHOLD = float(os.getenv("MEMOIRE_SEUIL_SIMILARITE", "0.55"))
MAX_MEMOIRE_CONTEXTE = int(os.getenv("MAX_MEMOIRE_CONTEXTE", "5"))
TIMEOUT_EMBEDDING = int(os.getenv("TIMEOUT_EMBEDDING", "10"))
TIMEOUT_EXTRACTION = int(os.getenv("TIMEOUT_EXTRACTION", "20"))

CACHE_EMBEDDINGS_ACTIVE = os.getenv("CACHE_EMBEDDINGS_ACTIVE", "1") == "1"
CACHE_EMBEDDINGS_TAILLE = int(os.getenv("CACHE_EMBEDDINGS_TAILLE", "500"))
EXTRACTION_ASYNC = os.getenv("EXTRACTION_ASYNC", "1") == "1"
NORMALISER_EMBEDDINGS = os.getenv("NORMALISER_EMBEDDINGS", "1") == "1"

# ============================================================
# STATISTIQUES
# ============================================================

_stats_memoire = {
    "embeddings_total": 0,
    "embeddings_cache_hits": 0,
    "embeddings_cache_misses": 0,
    "embeddings_echecs": 0,
    "embeddings_temps_total": 0.0,
    "extractions_total": 0,
    "extractions_memorisees": 0,
    "extractions_temps_total": 0.0,
    "recherches_total": 0,
    "recherches_resultats_total": 0,
    "recherches_temps_total": 0.0,
    "indexations_total": 0,
    "indexations_async": 0,
}

_extraction_queue: "queue.Queue" = queue.Queue()
_extraction_thread = None
_extraction_thread_active = False


# ============================================================
# CACHE LRU (succès uniquement)
# ============================================================

class _CacheLRU:
    def __init__(self, taille: int):
        self.taille = taille
        self._d: "OrderedDict[str, list]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, cle: str):
        with self._lock:
            if cle in self._d:
                self._d.move_to_end(cle)
                return self._d[cle]
            return None

    def put(self, cle: str, valeur: list):
        if not valeur:
            return  # jamais de cache pour un échec
        with self._lock:
            self._d[cle] = valeur
            self._d.move_to_end(cle)
            while len(self._d) > self.taille:
                self._d.popitem(last=False)

    def clear(self):
        with self._lock:
            self._d.clear()

    def __len__(self):
        return len(self._d)


_cache_embeddings = _CacheLRU(CACHE_EMBEDDINGS_TAILLE)


# ============================================================
# EMBEDDINGS
# ============================================================

def _appeler_ollama_embedding(texte: str) -> list:
    """Appel brut Ollama ; renvoie [] en cas d'échec (jamais d'exception)."""
    debut = time.perf_counter()
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": texte},
            timeout=TIMEOUT_EMBEDDING,
        )
        if r.status_code == 404:
            log_warning("memoire_semantique", f"Modèle {EMBED_MODEL} absent : ollama pull {EMBED_MODEL}")
            return []
        r.raise_for_status()
        embedding = r.json().get("embedding") or []
        if NORMALISER_EMBEDDINGS and embedding:
            v = np.array(embedding, dtype=float)
            n = np.linalg.norm(v)
            if n > 0:
                embedding = (v / n).tolist()
        _stats_memoire["embeddings_temps_total"] += time.perf_counter() - debut
        return embedding
    except requests.Timeout:
        log_warning("memoire_semantique", f"Embedding timeout ({TIMEOUT_EMBEDDING}s)")
    except Exception as e:
        log_warning("memoire_semantique", f"Embedding échoué : {e}")
    _stats_memoire["embeddings_echecs"] += 1
    return []


def embed_text(texte: str) -> list:
    """
    Embedding d'un texte avec cache (hits ~0.001 ms, miss ~50-200 ms).
    Les échecs ne sont pas mis en cache : le prochain appel réessaiera.
    """
    if not texte or not texte.strip():
        return []
    _stats_memoire["embeddings_total"] += 1
    cle = " ".join(texte.strip().lower().split())

    if CACHE_EMBEDDINGS_ACTIVE:
        hit = _cache_embeddings.get(cle)
        if hit is not None:
            _stats_memoire["embeddings_cache_hits"] += 1
            return list(hit)

    _stats_memoire["embeddings_cache_misses"] += 1
    emb = _appeler_ollama_embedding(cle)
    if emb and CACHE_EMBEDDINGS_ACTIVE:
        _cache_embeddings.put(cle, emb)
    return list(emb)


def embed_batch(textes: List[str]) -> List[list]:
    """Embeddings en parallèle (dédoublonnage + threads)."""
    if not textes:
        return []
    uniques: Dict[str, List[int]] = {}
    for i, t in enumerate(textes):
        k = " ".join((t or "").strip().lower().split())
        uniques.setdefault(k, []).append(i)

    resultats_map: Dict[str, list] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(embed_text, k): k for k in uniques if k}
        for f in concurrent.futures.as_completed(futures):
            k = futures[f]
            try:
                resultats_map[k] = f.result()
            except Exception as e:
                log_warning("memoire_semantique", f"Batch embedding échoué : {e}")
                resultats_map[k] = []

    out = [[] for _ in textes]
    for k, idx in uniques.items():
        for i in idx:
            out[i] = resultats_map.get(k, [])
    return out


def _similarite_cosinus(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    a_np, b_np = np.array(a, dtype=float), np.array(b, dtype=float)
    if NORMALISER_EMBEDDINGS:
        return float(np.dot(a_np, b_np))
    denom = np.linalg.norm(a_np) * np.linalg.norm(b_np)
    return float(np.dot(a_np, b_np) / denom) if denom else 0.0


# ============================================================
# INDEXATION
# ============================================================

def indexer_memoire(user_id: str, cle: str, valeur: str, async_mode: bool = True):
    """À appeler après remember_memory_db : attache l'embedding en base."""
    _stats_memoire["indexations_total"] += 1
    if async_mode and EXTRACTION_ASYNC:
        _demarrer_thread_indexation()
        _extraction_queue.put(("indexer", user_id, cle, valeur))
        _stats_memoire["indexations_async"] += 1
    else:
        _indexer_memoire_sync(user_id, cle, valeur)


def _indexer_memoire_sync(user_id: str, cle: str, valeur: str):
    try:
        embedding = embed_text(f"{cle}: {valeur}")
        if embedding:
            sauvegarder_embedding(user_id, cle, json.dumps(embedding))
            log_event("memoire_semantique", f"Embedding indexé pour '{cle}'")
        else:
            log_warning("memoire_semantique", f"Embedding vide pour '{cle}' (sera retenté plus tard)")
    except Exception as e:
        log_error("memoire_semantique", f"Erreur indexation '{cle}' : {e}")


def indexer_memoires_batch(user_id: str, memoires: List[Dict[str, str]]):
    if not memoires:
        return
    log_event("memoire_semantique", f"Indexation batch : {len(memoires)} mémoires")
    embeddings = embed_batch([f"{m['cle']}: {m['valeur']}" for m in memoires])
    for m, emb in zip(memoires, embeddings):
        if emb:
            try:
                sauvegarder_embedding(user_id, m["cle"], json.dumps(emb))
                _stats_memoire["indexations_total"] += 1
            except Exception as e:
                log_error("memoire_semantique", f"Erreur sauvegarde embedding '{m['cle']}' : {e}")


def _worker_indexation_async():
    global _extraction_thread_active
    while _extraction_thread_active:
        try:
            item = _extraction_queue.get(timeout=1.0)
            if item is None:
                break
            op, user_id, cle, valeur = item
            if op == "indexer":
                _indexer_memoire_sync(user_id, cle, valeur)
            _extraction_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            log_error("memoire_semantique", f"Erreur worker indexation : {e}")


def _demarrer_thread_indexation():
    global _extraction_thread, _extraction_thread_active
    if _extraction_thread is None or not _extraction_thread.is_alive():
        _extraction_thread_active = True
        _extraction_thread = threading.Thread(target=_worker_indexation_async, daemon=True)
        _extraction_thread.start()
        log_event("memoire_semantique", "Thread indexation asynchrone démarré")


# ============================================================
# EXTRACTION AUTOMATIQUE
# ============================================================

EXTRACTION_PROMPT = """Analyse ce message d'un utilisateur qui parle à un assistant personnel.

Message : "{message}"

Si le message contient une information personnelle durable à retenir
(projet, études, préférence, objectif, langue, métier, hobby, localisation, famille, etc.),
réponds UNIQUEMENT avec ce JSON, rien d'autre :
{{"a_memoriser": true, "cle": "...", "valeur": "...", "importance": 0.8}}

Sinon (question, salutation, small talk, demande ponctuelle) :
{{"a_memoriser": false}}

Règles :
- "cle" : court identifiant en minuscules avec underscores (ex: "projet_etudes", "preference_musique")
- "valeur" : info concrète et factuelle
- "importance" : 0.0-1.0
- Ne mémorise JAMAIS le prénom (géré ailleurs)
- Ignore les questions et les demandes d'action ("Ouvre...", "Cherche...", "Améliore...")

Exemples :
- "Je fais des études d'ingénierie" → {{"a_memoriser": true, "cle": "etudes", "valeur": "ingénierie", "importance": 0.8}}
- "J'aime le jazz" → {{"a_memoriser": true, "cle": "preference_musicale", "valeur": "jazz", "importance": 0.6}}
- "Comment ça va ?" → {{"a_memoriser": false}}
"""


def analyser_message(message: str) -> dict:
    if not message or len(message) < 10:
        return {"a_memoriser": False}
    _stats_memoire["extractions_total"] += 1
    debut = time.perf_counter()
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": EXTRACT_MODEL,
                "prompt": EXTRACTION_PROMPT.format(message=message.replace('"', "'")),
                "stream": False,
                "format": "json",
                "options": {"temperature": 0, "num_predict": 120},
            },
            timeout=TIMEOUT_EXTRACTION,
        )
        r.raise_for_status()
        temps = time.perf_counter() - debut
        _stats_memoire["extractions_temps_total"] += temps
        resultat = json.loads(r.json().get("response") or "{}")
        if not isinstance(resultat, dict):
            resultat = {"a_memoriser": False}
        log_event("memoire_semantique",
                  f"Analyse message en {temps:.2f}s : {'MÉMORISABLE' if resultat.get('a_memoriser') else 'NON'}")
        return resultat
    except requests.Timeout:
        log_warning("memoire_semantique", f"Analyse timeout ({TIMEOUT_EXTRACTION}s)")
    except Exception as e:
        log_warning("memoire_semantique", f"Analyse échouée : {e}")
    return {"a_memoriser": False}


def traiter_message_semantique(user_id: str, message: str) -> bool:
    analyse = analyser_message(message)
    if analyse.get("a_memoriser") and analyse.get("cle") and analyse.get("valeur"):
        cle, valeur = str(analyse["cle"]), str(analyse["valeur"])
        remember_memory_db(user_id, cle, valeur)
        indexer_memoire(user_id, cle, valeur, async_mode=True)
        _stats_memoire["extractions_memorisees"] += 1
        log_event("memoire_semantique",
                  f"Mémorisé automatiquement : {cle}={valeur} (importance={analyse.get('importance', 0.5)})")
        return True
    return False


# ============================================================
# RECHERCHE SÉMANTIQUE
# ============================================================

def rechercher_semantique(user_id: str, question: str, top_k: int = None, seuil: float = None) -> List[Dict]:
    top_k = top_k or MAX_MEMOIRE_CONTEXTE
    seuil = SIMILARITY_THRESHOLD if seuil is None else seuil
    _stats_memoire["recherches_total"] += 1
    debut = time.perf_counter()

    q_emb = embed_text(question)
    if not q_emb:
        return []

    resultats = []
    try:
        lignes = obtenir_memoires_avec_embeddings(user_id)
    except Exception as e:
        log_error("memoire_semantique", f"Lecture mémoires échouée : {e}")
        return []

    for cle, valeur, embedding_json in lignes:
        try:
            emb = json.loads(embedding_json) if embedding_json else None
        except (TypeError, json.JSONDecodeError):
            log_warning("memoire_semantique", f"Embedding JSON invalide pour '{cle}'")
            continue
        if not emb:
            continue
        score = _similarite_cosinus(q_emb, emb)
        if score >= seuil:
            resultats.append({"cle": cle, "valeur": valeur, "score": round(score, 3)})

    resultats.sort(key=lambda r: r["score"], reverse=True)
    resultats = resultats[:top_k]
    temps = time.perf_counter() - debut
    _stats_memoire["recherches_temps_total"] += temps
    _stats_memoire["recherches_resultats_total"] += len(resultats)
    log_event("memoire_semantique", f"Recherche '{question[:40]}' : {len(resultats)} résultat(s) en {temps:.2f}s")
    return resultats


def construire_contexte_memoire(user_id: str, question: str, max_resultats: int = None) -> str:
    souvenirs = rechercher_semantique(user_id, question, top_k=max_resultats)
    if not souvenirs:
        return ""
    lignes = [f"- {s['cle']}: {s['valeur']} (pertinence: {s['score']:.2f})" for s in souvenirs]
    return ("Informations pertinentes connues sur l'utilisateur "
            "(à utiliser seulement si utile à la réponse) :\n" + "\n".join(lignes))


# ============================================================
# UTILITAIRES
# ============================================================

def obtenir_statistiques_memoire() -> dict:
    s = _stats_memoire.copy()
    total = s["embeddings_cache_hits"] + s["embeddings_cache_misses"]
    s["embeddings_cache_hit_rate"] = round(s["embeddings_cache_hits"] / total * 100, 2) if total else 0.0
    s["embeddings_temps_moyen"] = round(s["embeddings_temps_total"] / s["embeddings_cache_misses"], 3) \
        if s["embeddings_cache_misses"] else 0.0
    s["cache_taille"] = len(_cache_embeddings)
    if s["extractions_total"]:
        s["extractions_temps_moyen"] = round(s["extractions_temps_total"] / s["extractions_total"], 3)
        s["extractions_taux_memorisation"] = round(s["extractions_memorisees"] / s["extractions_total"] * 100, 2)
    else:
        s["extractions_temps_moyen"] = s["extractions_taux_memorisation"] = 0.0
    if s["recherches_total"]:
        s["recherches_temps_moyen"] = round(s["recherches_temps_total"] / s["recherches_total"], 3)
        s["recherches_resultats_moyens"] = round(s["recherches_resultats_total"] / s["recherches_total"], 2)
    else:
        s["recherches_temps_moyen"] = s["recherches_resultats_moyens"] = 0.0
    s["indexations_async_percent"] = round(s["indexations_async"] / s["indexations_total"] * 100, 2) \
        if s["indexations_total"] else 0.0
    return s


def reinitialiser_cache_embeddings():
    _cache_embeddings.clear()
    log_event("memoire_semantique", "Cache embeddings réinitialisé")
    return "Cache embeddings vidé."


def _modele_present(nom: str, disponibles: List[str]) -> bool:
    base = nom.split(":")[0]
    return any(m == nom or m.split(":")[0] == base for m in disponibles)


def verifier_modele_embeddings() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        modeles = [m.get("name", "") for m in r.json().get("models", [])]
        if _modele_present(EMBED_MODEL, modeles):
            log_event("memoire_semantique", f"Modèle {EMBED_MODEL} disponible")
            return True
        log_warning("memoire_semantique", f"Modèle {EMBED_MODEL} non trouvé. Installer : ollama pull {EMBED_MODEL}")
        return False
    except Exception as e:
        log_error("memoire_semantique", f"Erreur vérification modèle : {e}")
        return False


def tester_memoire_semantique(user_id: str = "test_user") -> dict:
    rapport = {"modele_disponible": False, "embedding_test": False, "extraction_test": False,
               "recherche_test": False, "erreurs": []}
    print("🧠 Test mémoire sémantique JIBI\n")
    print(f"   Ollama   : {OLLAMA_URL}\n   Embed    : {EMBED_MODEL}\n   Extract  : {EXTRACT_MODEL}\n")

    print("1. Modèle embeddings...")
    rapport["modele_disponible"] = verifier_modele_embeddings()
    if not rapport["modele_disponible"]:
        rapport["erreurs"].append("Modèle embeddings non disponible")
        return rapport

    print("2. Embedding...")
    d = time.perf_counter()
    emb = embed_text("test de mémoire sémantique")
    if emb:
        rapport["embedding_test"] = True
        print(f"   ✓ {len(emb)}D en {time.perf_counter() - d:.2f}s")
        d = time.perf_counter(); embed_text("test de mémoire sémantique")
        print(f"   ✓ cache : {(time.perf_counter() - d) * 1000:.2f} ms")
    else:
        rapport["erreurs"].append("Embedding vide")

    print("3. Extraction automatique...")
    d = time.perf_counter()
    analyse = analyser_message("Je suis passionné de robotique")
    if analyse.get("a_memoriser"):
        rapport["extraction_test"] = True
        print(f"   ✓ {time.perf_counter() - d:.2f}s : {analyse}")
    else:
        print(f"   ⚠️ pas de mémorisation détectée ({time.perf_counter() - d:.2f}s) : {analyse}")

    print("4. Recherche sémantique...")
    try:
        remember_memory_db(user_id, "test_projet", "intelligence artificielle")
        indexer_memoire(user_id, "test_projet", "intelligence artificielle", async_mode=False)
        d = time.perf_counter()
        res = rechercher_semantique(user_id, "mon objectif professionnel")
        rapport["recherche_test"] = True
        print(f"   ✓ {len(res)} résultat(s) en {time.perf_counter() - d:.2f}s")
        for r in res:
            print(f"      - {r['cle']}: {r['valeur']} (score {r['score']})")
    except Exception as e:
        rapport["erreurs"].append(f"Erreur recherche : {e}")

    rapport["stats"] = obtenir_statistiques_memoire()
    return rapport


def nettoyer_ressources_memoire() -> bool:
    global _extraction_thread_active
    try:
        _extraction_thread_active = False
        if _extraction_thread and _extraction_thread.is_alive():
            _extraction_queue.put(None)
            _extraction_thread.join(timeout=2)
        log_event("memoire_semantique", "Ressources mémoire sémantique libérées")
        return True
    except Exception as e:
        log_error("memoire_semantique", f"Erreur nettoyage : {e}")
        return False


if __name__ == "__main__":
    rapport = tester_memoire_semantique()
    print("\n" + "=" * 60)
    for k in ("modele_disponible", "embedding_test", "extraction_test", "recherche_test"):
        print(f"{k:<20}: {'✅' if rapport[k] else '❌'}")
    if rapport["erreurs"]:
        print("\n⚠️ Erreurs :")
        for e in rapport["erreurs"]:
            print(f"  - {e}")
    s = rapport.get("stats", {})
    if s:
        print(f"\nCache hit rate : {s['embeddings_cache_hit_rate']}%  |  temps moyen embedding : {s['embeddings_temps_moyen']}s")
    print("=" * 60)