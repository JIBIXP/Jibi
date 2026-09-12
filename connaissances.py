"""
connaissances.py
=================

Base de connaissances élargie pour JIBI, séparée de la mémoire
personnelle (memory_manager.py / table `memoire`).

Différence avec memory_manager.py :
  - memory_manager.py -> souvenirs COURTS sur l'UTILISATEUR
                          (son prénom, son projet, ses préférences...).
  - connaissances.py  -> DOCUMENTS plus longs que tu choisis de donner
                          à JIBI (cours, notes, PDF texte, pages web
                          sauvegardées...), découpés en morceaux et
                          cherchables par le sens.

Stockage : chromadb en local, persistant sur disque (dossier
`chroma_jibi/`, créé automatiquement). Pas de serveur à lancer.

Prérequis :
    pip install chromadb
    (nomic-embed-text doit déjà être tiré via Ollama, comme pour
    memory_manager.py : `ollama pull nomic-embed-text`)
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import chromadb

from memory_manager import embed_text
from logging_jibi import log_event, log_warning

CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_jibi")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "connaissances_jibi")

TAILLE_MORCEAU = 800       # caractères par morceau
CHEVAUCHEMENT = 100        # caractères répétés entre deux morceaux consécutifs
TOP_K_DEFAUT = 4
EMBED_WORKERS = int(os.getenv("CONNAISSANCES_EMBED_WORKERS", "6"))

_client = None
_collection = None


def _obtenir_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = _client.get_or_create_collection(COLLECTION_NAME)
    return _collection


# ============================================================
# DÉCOUPAGE EN MORCEAUX
# ============================================================

def decouper_texte(texte, taille=TAILLE_MORCEAU, chevauchement=CHEVAUCHEMENT):
    """Découpe un texte long en morceaux avec un léger chevauchement,
    pour ne pas couper une idée exactement à la frontière entre deux morceaux."""
    texte = texte.strip()
    if not texte:
        return []

    morceaux = []
    debut = 0
    longueur = len(texte)

    while debut < longueur:
        fin = min(debut + taille, longueur)
        morceaux.append(texte[debut:fin])
        if fin == longueur:
            break
        debut = fin - chevauchement

    return morceaux


# ============================================================
# LECTURE DE FICHIERS
# ============================================================

def _lire_fichier(chemin):
    extension = os.path.splitext(chemin)[1].lower()

    if extension in (".txt", ".md"):
        with open(chemin, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError(
                "Lecture PDF: installe 'pypdf' (pip install pypdf) pour ingérer des PDF."
            )
        lecteur = PdfReader(chemin)
        return "\n".join((page.extract_text() or "") for page in lecteur.pages)

    raise ValueError(f"Extension non supportée: {extension} (utilise .txt, .md ou .pdf)")


# ============================================================
# INGESTION
# ============================================================

def ingerer_texte(source, texte, categorie="general"):
    """
    Découpe `texte` et l'ajoute à la base de connaissances.
    `source` est un nom libre (ex: nom du fichier) utilisé comme référence
    dans les résultats de recherche.

    Les embeddings sont calculés en parallèle (ThreadPoolExecutor) : ce
    sont des appels HTTP vers Ollama, donc de l'attente réseau, pas du
    calcul CPU local — les paralléliser accélère nettement l'ingestion
    des gros dossiers sans changer le résultat.
    """
    morceaux = decouper_texte(texte)
    if not morceaux:
        log_warning("connaissances", f"Rien à ingérer pour la source '{source}' (texte vide).")
        return 0

    collection = _obtenir_collection()

    embeddings_par_index = {}
    with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as executor:
        futures = {
            executor.submit(embed_text, morceau): i
            for i, morceau in enumerate(morceaux)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                embeddings_par_index[i] = future.result()
            except Exception as e:
                log_warning("connaissances", f"Embedding échoué pour un morceau de '{source}': {e}")
                embeddings_par_index[i] = None

    documents, embeddings, ids, metadonnees = [], [], [], []
    for i, morceau in enumerate(morceaux):
        embedding = embeddings_par_index.get(i)
        if not embedding:
            log_warning("connaissances", f"Embedding échoué pour un morceau de '{source}' (ignoré).")
            continue
        documents.append(morceau)
        embeddings.append(embedding)
        ids.append(f"{source}-{uuid.uuid4().hex[:8]}-{i}")
        metadonnees.append({"source": source, "categorie": categorie})

    if not documents:
        return 0

    collection.add(
        documents=documents,
        embeddings=embeddings,
        ids=ids,
        metadatas=metadonnees,
    )

    log_event("connaissances", f"{len(documents)} morceau(x) ingéré(s) depuis '{source}'")
    return len(documents)


def ingerer_fichier(chemin, categorie="general"):
    """Lit un fichier (.txt, .md, .pdf) et l'ajoute à la base de connaissances."""
    texte = _lire_fichier(chemin)
    source = os.path.basename(chemin)
    return ingerer_texte(source, texte, categorie=categorie)


def ingerer_dossier(dossier, categorie="general", recursif=True):
    """
    Ingère tous les fichiers supportés (.txt, .md, .pdf) d'un dossier.
    Récursif par défaut : parcourt aussi les sous-dossiers.
    Affiche une progression simple, utile pour de gros volumes de fichiers.
    """
    fichiers = []
    if recursif:
        for racine, _, noms in os.walk(dossier):
            for nom in noms:
                if os.path.splitext(nom)[1].lower() in (".txt", ".md", ".pdf"):
                    fichiers.append(os.path.join(racine, nom))
    else:
        for nom in os.listdir(dossier):
            chemin = os.path.join(dossier, nom)
            if os.path.isfile(chemin) and os.path.splitext(nom)[1].lower() in (".txt", ".md", ".pdf"):
                fichiers.append(chemin)

    total = 0
    dejas_connues = sources_deja_ingerees()

    for i, chemin in enumerate(fichiers, start=1):
        nom_fichier = os.path.basename(chemin)
        if nom_fichier in dejas_connues:
            print(f"[{i}/{len(fichiers)}] {nom_fichier} — déjà ingéré, ignoré")
            continue
        try:
            n = ingerer_fichier(chemin, categorie=categorie)
            total += n
            print(f"[{i}/{len(fichiers)}] {nom_fichier} — {n} morceau(x)")
        except Exception as e:
            log_warning("connaissances", f"Ingestion échouée pour {nom_fichier}: {e}")
            print(f"[{i}/{len(fichiers)}] {nom_fichier} — échec: {e}")

    return total


def sources_deja_ingerees():
    """Renvoie l'ensemble des noms de fichiers déjà présents dans la base
    (sert à ne pas réingérer un fichier déjà traité lors d'un nouveau passage)."""
    collection = _obtenir_collection()
    if collection.count() == 0:
        return set()
    donnees = collection.get(include=["metadatas"])
    return {m.get("source") for m in donnees.get("metadatas", []) if m}


def statistiques():
    """Petit résumé de ce que contient la base — pratique pour vérifier
    que l'ingestion a bien fonctionné, sans tout ré-imprimer."""
    collection = _obtenir_collection()
    total = collection.count()
    if total == 0:
        return {"morceaux": 0, "sources": []}
    donnees = collection.get(include=["metadatas"])
    sources = sorted({m.get("source") for m in donnees.get("metadatas", []) if m})
    return {"morceaux": total, "sources": sources}


# ============================================================
# RECHERCHE
# ============================================================

def rechercher_connaissances(question, top_k=TOP_K_DEFAUT):
    """
    Renvoie les morceaux les plus proches du sens de `question`.
    Utilisé comme tool par agent.py : à la différence de web_search,
    ça cherche dans TES documents, pas sur internet.
    """
    q_embedding = embed_text(question)
    if not q_embedding:
        return {"error": "Embedding de la question impossible (Ollama indisponible ?)."}

    collection = _obtenir_collection()

    if collection.count() == 0:
        return {"resultats": [], "info": "Base de connaissances vide. Utilise ingerer_fichier() d'abord."}

    resultats = collection.query(query_embeddings=[q_embedding], n_results=top_k)

    sorties = []
    documents = resultats.get("documents", [[]])[0]
    metadonnees = resultats.get("metadatas", [[]])[0]
    distances = resultats.get("distances", [[]])[0]

    for doc, meta, dist in zip(documents, metadonnees, distances):
        sorties.append({
            "extrait": doc,
            "source": (meta or {}).get("source", "inconnue"),
            "pertinence": round(1 - dist, 3),  # approximatif, pour info seulement
        })

    return {"resultats": sorties}


def contexte_connaissances(question, top_k=TOP_K_DEFAUT, pertinence_min=0.35):
    """
    Version prête pour agent.py : renvoie directement un bloc de texte à
    ajouter au system prompt (comme memory_manager.construire_contexte_memoire),
    ou une chaîne vide s'il n'y a rien d'assez pertinent. Filtre les
    résultats trop faibles pour éviter de polluer le prompt avec du bruit.
    """
    resultat = rechercher_connaissances(question, top_k=top_k)
    extraits = [
        r for r in resultat.get("resultats", [])
        if r.get("pertinence", 0) >= pertinence_min
    ]
    if not extraits:
        return ""

    lignes = [f"- (source: {e['source']}) {e['extrait']}" for e in extraits]
    return (
        "Extraits pertinents trouvés dans les documents ingérés par "
        "l'utilisateur (utilise-les si utiles, ignore-les sinon) :\n"
        + "\n".join(lignes)
    )