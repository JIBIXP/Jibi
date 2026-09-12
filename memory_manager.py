"""
memory_manager.py
==================

Couche de mémoire sémantique pour JIBI, branchée sur la table `memoire`
existante (user_id, cle, valeur, embedding) de database.py.

Ne remplace PAS remember_memory_db / recall_db : les complète.
  - remember_memory_db / recall_db  -> lecture/écriture exacte par clé
                                        (rapide, déjà utilisé par le tool
                                        "remember"/"recall" et par
                                        extraire_prenom/memoire_directe).
  - memory_manager                  -> en plus, calcule un embedding pour
                                        chaque souvenir et permet de le
                                        retrouver par SENS, même si la
                                        question ne contient pas le même
                                        mot-clé ("mon objectif" retrouve
                                        "projet: ingénierie mécanique").

Prérequis :
    pip install numpy requests
    ollama pull nomic-embed-text
"""

import os
import json
import requests
import numpy as np

from database import (
    remember_memory_db,
    sauvegarder_embedding,
    obtenir_memoires_avec_embeddings,
)
from logging_jibi import log_event, log_warning

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EXTRACT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")  # même modèle que le reste de JIBI par défaut

SIMILARITY_THRESHOLD = float(os.getenv("MEMOIRE_SEUIL_SIMILARITE", "0.55"))


# ============================================================
# EMBEDDINGS
# ============================================================

def embed_text(texte: str) -> list:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": texte},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["embedding"]
    except Exception as e:
        log_warning("memoire_semantique", f"Embedding échoué: {e}")
        return []


def _similarite_cosinus(a: list, b: list) -> float:
    if not a or not b:
        return 0.0
    a, b = np.array(a), np.array(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


# ============================================================
# ENREGISTREMENT (utilisé après un remember_memory_db)
# ============================================================

def indexer_memoire(user_id: str, cle: str, valeur: str):
    """
    À appeler juste après remember_memory_db(user_id, cle, valeur) :
    calcule l'embedding du souvenir et l'attache en base pour qu'il
    devienne trouvable par recherche sémantique.
    """
    embedding = embed_text(f"{cle}: {valeur}")
    if embedding:
        sauvegarder_embedding(user_id, cle, json.dumps(embedding))
        log_event("memoire_semantique", f"Embedding indexé pour la clé '{cle}'")


# ============================================================
# EXTRACTION AUTOMATIQUE (remplace les règles "if ... in texte")
# ============================================================

EXTRACTION_PROMPT = """Analyse ce message d'un utilisateur qui parle à un assistant personnel.

Message : "{message}"

Si le message contient une information personnelle durable à retenir
(prénom, projet, études, préférence, objectif, langue, métier, etc.),
réponds UNIQUEMENT avec ce JSON, rien d'autre :
{{"a_memoriser": true, "cle": "...", "valeur": "...", "importance": 0.8}}

Sinon (question, salutation, small talk, demande ponctuelle) :
{{"a_memoriser": false}}

"cle" doit être un court identifiant en minuscules (ex: "projet", "apprentissage", "preference_musicale").
Ne mémorise jamais le prénom ici (déjà géré ailleurs).
"""


def analyser_message(message: str) -> dict:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": EXTRACT_MODEL,
                "prompt": EXTRACTION_PROMPT.format(message=message),
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
            timeout=20,
        )
        r.raise_for_status()
        return json.loads(r.json()["response"])
    except Exception as e:
        log_warning("memoire_semantique", f"Analyse échouée: {e}")
        return {"a_memoriser": False}


def traiter_message_semantique(user_id: str, message: str) -> bool:
    """
    Détection générique (LLM) de faits à mémoriser, en complément des
    règles rapides existantes (extraire_prenom, memoire_directe).
    Fait UN appel Ollama : à réserver aux messages qui ont passé les
    raccourcis rapides pour ne pas ralentir chaque question.
    """
    analyse = analyser_message(message)
    if analyse.get("a_memoriser") and analyse.get("cle") and analyse.get("valeur"):
        cle, valeur = analyse["cle"], analyse["valeur"]
        remember_memory_db(user_id, cle, valeur)
        indexer_memoire(user_id, cle, valeur)
        log_event("memoire_semantique", f"Mémorisé automatiquement: {cle}")
        return True
    return False


# ============================================================
# RECHERCHE SÉMANTIQUE
# ============================================================

def rechercher_semantique(user_id: str, question: str, top_k: int = 3) -> list:
    q_embedding = embed_text(question)
    if not q_embedding:
        return []

    lignes = obtenir_memoires_avec_embeddings(user_id)
    resultats = []
    for cle, valeur, embedding_json in lignes:
        try:
            embedding = json.loads(embedding_json)
        except (TypeError, json.JSONDecodeError):
            continue
        score = _similarite_cosinus(q_embedding, embedding)
        if score >= SIMILARITY_THRESHOLD:
            resultats.append({"cle": cle, "valeur": valeur, "score": score})

    resultats.sort(key=lambda r: r["score"], reverse=True)
    return resultats[:top_k]


def construire_contexte_memoire(user_id: str, question: str) -> str:
    """Bloc de contexte prêt à ajouter au system prompt Ollama."""
    souvenirs = rechercher_semantique(user_id, question)
    if not souvenirs:
        return ""
    lignes = [f"- {s['cle']}: {s['valeur']}" for s in souvenirs]
    return (
        "Informations pertinentes connues sur l'utilisateur "
        "(à utiliser seulement si utile à la réponse) :\n" + "\n".join(lignes)
    )