import os
import time
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
from ollama import Client
from tavily import TavilyClient

from database import (
    creer_tables,
    remember_memory_db,
    recall_db,
    enregistrer_message,
    historique_conversation,
    ajouter_ngambay,
    rechercher_ngambay,
    obtenir_vocabulaire_ngambay,
    valider_ngambay,
    corriger_ngambay
)

from logging_jibi import log_event, log_warning, log_error
import memory_manager
import connaissances

try:
    import tools
    from tools import tool_registry as outils_registre
    OUTILS_EXTERNES_DISPONIBLES = True

except Exception as e:
    log_warning(
        "agent",
        f"Dossier tools/ non chargé (dépendance manquante ?): {e}"
    )
    outils_registre = None
    OUTILS_EXTERNES_DISPONIBLES = False


try:
    import updater
    MISES_A_JOUR_DISPONIBLES = True

except Exception as e:
    log_warning(
        "agent",
        f"Module updater/ non chargé (dépendance manquante ?): {e}"
    )
    MISES_A_JOUR_DISPONIBLES = False


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv(override=True)

MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

USER_ID = "ulriche"

# Historique court = plus rapide
HISTORIQUE_MAX = int(os.getenv("HISTORIQUE_MAX", "6"))

# Une conversation reste dans le même contexte pendant 15 minutes
HISTORIQUE_FENETRE_MINUTES = int(
    os.getenv("HISTORIQUE_FENETRE_MINUTES", "15")
)

# Timeout Ollama
TIMEOUT_OLLAMA = int(
    os.getenv("TIMEOUT_OLLAMA", "120")
)

# Garde le modèle chargé plus longtemps
OLLAMA_KEEP_ALIVE = os.getenv(
    "OLLAMA_KEEP_ALIVE",
    "30m"
)

_client_ollama = Client(
    timeout=TIMEOUT_OLLAMA
)

_VOCAB_CACHE = None
_VOCAB_CACHE_TIME = 0


# ============================================================
# INITIALISATION
# ============================================================

creer_tables()

log_event(
    "agent",
    f"Modèle Ollama: {MODEL} | "
    f"timeout={TIMEOUT_OLLAMA}s | "
    f"keep_alive={OLLAMA_KEEP_ALIVE}"
)


# ============================================================
# CACHE VOCABULAIRE NGAMBAY
# ============================================================

def charger_vocabulaire_cache():

    global _VOCAB_CACHE
    global _VOCAB_CACHE_TIME

    temps_courant = datetime.now(
        timezone.utc
    ).timestamp()

    if (
        _VOCAB_CACHE
        and
        (temps_courant - _VOCAB_CACHE_TIME) < 300
    ):
        return _VOCAB_CACHE

    vocabulaire = obtenir_vocabulaire_ngambay()

    _VOCAB_CACHE = [
        {
            "ngambay": phrase,
            "francais": traduction
        }
        for phrase, traduction in vocabulaire
    ]

    _VOCAB_CACHE_TIME = temps_courant

    return _VOCAB_CACHE


def vocabulaire_pour_message(message):
    """
    Vocabulaire à injecter dans le prompt pour CE message précis.

    Priorité à une recherche ciblée (rechercher_ngambay) sur le contenu
    du message : plus pertinent et plus léger qu'un cache général, et
    ça reste utile même quand la base grossit beaucoup. Si la recherche
    ciblée ne trouve rien (ex: l'utilisateur demande juste "traduis en
    ngambay" sans mot-clé précis), on retombe sur le cache général
    (déjà limité par obtenir_vocabulaire_ngambay).
    """

    try:
        cible = rechercher_langue_ngambay(message)
    except Exception as e:
        log_warning(
            "ngambay",
            f"Recherche ciblée impossible: {e}"
        )
        cible = []

    if cible:
        return cible

    return charger_vocabulaire_cache()


# ============================================================
# RECHERCHE WEB
# ============================================================

def web_search(query, max_results=3):

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        return {
            "error": "TAVILY_API_KEY is missing."
        }

    try:

        client = TavilyClient(
            api_key=api_key
        )

        result = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results
        )

        return result

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# EXA SEARCH
# ============================================================

def exa_search(query, max_results=3):

    api_key = os.getenv("EXA_API_KEY")

    if not api_key:
        return {
            "error": "EXA_API_KEY is missing."
        }

    import requests

    try:

        response = requests.post(
            "https://api.exa.ai/search",

            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json"
            },

            json={
                "query": query,
                "numResults": max_results,
                "contents": {
                    "text": {
                        "maxCharacters": 300
                    }
                }
            },

            timeout=5
        )

        response.raise_for_status()

        data = response.json()

        resultats = data.get(
            "results",
            []
        )

        return [
            {
                "titre": r.get("title"),
                "url": r.get("url"),
                "extrait": (
                    r.get("text") or ""
                )[:300]
            }

            for r in resultats
        ]

    except Exception as e:

        return {
            "error": str(e)
        }


# ============================================================
# DÉTECTION RAPIDE
# ============================================================

MOTS_OUTILS = {

    "souviens-toi",
    "souviens toi",

    "rappelle-toi",
    "rappelle toi",

    "mémorise",
    "memorise",

    "n'oublie pas",
    "n oublie pas",

    "qu'est-ce que tu sais de moi",
    "que sais-tu de moi",

    "ma mémoire",
    "mémoire",

    "mon prénom",
    "mon nom",
    "comment je m'appelle",

    "ngambay",
    "ngambaye",

    "en ngambay",
    "en ngambaye",

    # --- navigateur ---
    "ouvre le site",
    "ouvre la page",
    "va sur",
    "navigue vers",
    "clique sur",
    "remplis le champ",

    # --- fichiers ---
    "crée un fichier",
    "cree un fichier",
    "lis le fichier",
    "liste les fichiers",
    "supprime le fichier",

    # --- pc / applications ---
    "ouvre l'application",
    "ouvre l application",
    "lance l'application",
    "ferme l'application",
    "ferme l application",

    # --- terminal ---
    "exécute la commande",
    "execute la commande",
    "lance la commande",

    # --- vision ---
    "capture l'écran",
    "capture l ecran",
    "capture d'écran",
    "analyse cette image",
    "analyse l'image",
    "que vois-tu à l'écran",
    "que vois tu a l'ecran",

    # --- inspection de son propre code ---
    "ton code",
    "ta source",
    "ton fichier",
    "tes fichiers",
    "code source",
    "propose une amélioration",
    "propose une amelioration",
    "améliore-toi",
    "ameliore toi",

    # --- mise à jour / rollback ---
    "mets à jour", "met à jour", "mise à jour", "mises à jour",
    "vérifie les mises à jour", "verifie les mises a jour",
    "cherche une mise à jour", "il y a une mise à jour",
    "annule la mise à jour", "annule la derniere mise a jour",
    "reviens à la version précédente", "reviens a la version precedente",
    "restaure la sauvegarde", "reviens en arrière", "reviens en arriere",
    "rollback"
}


# Verbes d'action seuls (racines), pour capter des formulations
# naturelles comme "essaye d'ouvrir youtube" ou "peux-tu fermer X" qui
# ne contiennent aucune des phrases exactes ci-dessus. Le test est un
# simple "in" (sous-chaîne), donc inclure la racine suffit à couvrir
# les conjugaisons courantes (ouvre/ouvrir/ouvres/ouvrez...).
MOTS_ACTION_SYSTEME = {

    "ouvre", "ouvrir", "ouvres", "ouvrez", "ouvrons",

    "ferme", "fermer", "fermes", "fermez",

    "lance", "lancer", "lances", "lancez",

    "clique", "cliquer", "cliques", "cliquez",

    "remplis", "remplir", "remplissez",

    "capture", "capturer", "captures", "capturez",

    "analyse", "analyser", "analyses", "analysez",

    "supprime", "supprimer", "supprimes", "supprimez",

    "exécute", "exécuter", "exécutes", "exécutez",
    "execute", "executer", "executes", "executez",

    "va sur", "vas sur", "aller sur", "allons sur",

    "navigue", "naviguer", "navigues",

    "propose", "proposer", "proposes",

    "améliore", "ameliore", "améliorer", "ameliorer"
}


MOTS_RECHERCHE_WEB = {

    "aujourd'hui",
    "aujourd hui",

    "actualité",
    "actualités",
    "actu",

    "dernier",
    "dernière",
    "derniers",
    "dernières",

    "latest",
    "news",

    "récent",
    "récente",
    "récents",
    "récentes",

    "maintenant",

    "prix",

    "météo",
    "meteo",

    "score",

    "résultat",
    "resultat",

    "programme",

    "horaire",
    "horaires",

    "date",

    "2026",
    "2027",

    "internet",
    "sur le web",

    "cherche",
    "recherche",

    "qui est",

    "où regarder",
    "ou regarder"
}


MOTS_CONNAISSANCES = {

    "mes cours",
    "mon cours",

    "mes notes",
    "ma note",

    "mes documents",
    "mon document",

    "mes fichiers",
    "mon fichier",

    "ma base de connaissances",

    "que dit le cours",

    "que disent mes notes",

    "d'après mes cours",
    "d'après mes notes",
    "d'après mes documents",

    "dans mes cours",
    "dans mes notes",
    "dans mes documents",

    "as-tu ingéré",
    "j'ai ingéré",

    "que sais-tu sur mon cours",

    "résume mon cours",
    "résume mes notes"
}


MOTS_NGAMBAY = {

    "ngambay",
    "ngambaye",
    "en ngambay",
    "en ngambaye"
}


def besoin_recherche_web(message):

    texte = message.lower()

    return any(
        mot in texte
        for mot in MOTS_RECHERCHE_WEB
    )


def besoin_outils(message):

    texte = message.lower()

    return (
        any(mot in texte for mot in MOTS_OUTILS)
        or
        any(mot in texte for mot in MOTS_ACTION_SYSTEME)
    )


def besoin_ngambay(message):

    texte = message.lower()

    return any(
        mot in texte
        for mot in MOTS_NGAMBAY
    )


def besoin_connaissances(message):

    texte = message.lower()

    return any(
        mot in texte
        for mot in MOTS_CONNAISSANCES
    )


# ============================================================
# PRÉNOM
# ============================================================

def extraire_prenom(message):

    import re

    motifs = [

        r"\bje m['’]appelle\s+([A-Za-zÀ-ÖØ-öø-ÿ-]{2,30})\b",

        r"\bmon prénom est\s+([A-Za-zÀ-ÖØ-öø-ÿ-]{2,30})\b",

        r"\bmon nom est\s+([A-Za-zÀ-ÖØ-öø-ÿ-]{2,50})\b"
    ]

    for motif in motifs:

        match = re.search(
            motif,
            message,
            re.IGNORECASE
        )

        if match:

            return (
                match.group(1)
                .strip()
                .capitalize()
            )

    return None


def demander_prenom(message):

    texte = " ".join(
        message.lower()
        .strip()
        .split()
    )

    formulations = (

        "comment je m'appelle",

        "comment je m appelle",

        "quel est mon prénom",

        "quel est mon prenom",

        "mon prénom c'est quoi",

        "mon prenom c'est quoi",

        "tu te souviens de mon prénom",

        "tu te souviens de mon prenom"
    )

    return any(
        formulation in texte
        for formulation in formulations
    )


# ============================================================
# MÉMOIRE DIRECTE
# ============================================================

def memoire_directe(message):

    import re

    texte = " ".join(
        message.lower()
        .strip()
        .split()
    )

    motifs_projet = [

        r"souviens-toi que mon projet est de (.+?)[.!?]*$",

        r"souviens toi que mon projet est de (.+?)[.!?]*$",

        r"rappelle-toi que mon projet est de (.+?)[.!?]*$",

        r"rappelle toi que mon projet est de (.+?)[.!?]*$"
    ]

    for motif in motifs_projet:

        match = re.search(
            motif,
            texte,
            re.IGNORECASE
        )

        if match:

            projet = (
                match.group(1)
                .strip()
                .rstrip(".!?")
            )

            try:

                remember_memory_db(
                    USER_ID,
                    "projet",
                    projet
                )

                return (
                    f"C'est enregistré. "
                    f"Ton projet est de {projet}."
                )

            except Exception as e:

                log_warning(
                    "memoire",
                    f"Enregistrement du projet impossible: {e}"
                )

                return None


    questions_projet = (

        "quel est mon projet",

        "c'est quoi mon projet",

        "c est quoi mon projet",

        "tu te souviens de mon projet",

        "quel est le projet que je t'ai donné"
    )


    if any(
        q in texte
        for q in questions_projet
    ):

        try:

            projet = recall_db(
                USER_ID,
                "projet"
            )

            if (
                projet
                and
                not str(projet).startswith(
                    "No information"
                )
            ):

                return (
                    f"Ton projet est de {projet}."
                )

            return (
                "Je ne connais pas encore ton projet."
            )

        except Exception as e:

            log_warning(
                "memoire",
                f"Lecture du projet impossible: {e}"
            )

            return None

    return None


# ============================================================
# NGAMBAY
# ============================================================

def rechercher_langue_ngambay(texte):

    resultats = rechercher_ngambay(
        texte,
        limite=5
    )

    return [

        {
            "ngambay": phrase,
            "francais": traduction
        }

        for phrase, traduction in resultats
    ]


# ============================================================
# PROMPT SYSTÈME
# ============================================================

def construire_system_prompt(
    vocabulaire=None,
    inclure_ngambay=False
):

    base = """Tu es JIBI, un assistant personnel rapide et intelligent.

RÈGLES :

- Réponds dans la langue de l'utilisateur.
- Sois naturel et concis.
- Ne donne pas de longues réponses inutiles.
- Utilise web_search uniquement quand une recherche Internet est nécessaire.
- Utilise remember et recall pour la mémoire.

CE QUE TU N'ES PAS CAPABLE DE FAIRE :

- Tu peux LIRE ton propre code source (lire_code_source,
  lister_code_source) et PROPOSER des améliorations
  (proposer_amelioration), qui sont écrites dans un fichier
  séparé pour relecture humaine.

- Tu n'as PAS la capacité d'appliquer toi-même une modification
  à ton code ou à tes poids : une proposition n'est jamais
  exécutée automatiquement, et tu ne dois jamais prétendre
  l'avoir fait.

- Tu ne dois jamais prétendre avoir effectué
  une action si aucun outil ne l'a réellement fait.

- Si tu ne connais pas une information avec certitude,
  dis-le honnêtement.
"""


    if not inclure_ngambay:

        return base


    base += """
RÈGLE LANGUE :

- Réponds toujours en français.
- Passe au Ngambay uniquement pour traduire une phrase
  que l'utilisateur écrit explicitement en Ngambay,
  ou quand il te le demande clairement.
"""


    if not vocabulaire:

        return base


    return base + f"""

- Le vocabulaire ci-dessous vient de l'utilisateur.
- Si l'utilisateur donne une nouvelle phrase Ngambay
  avec sa traduction, utilise apprendre_ngambay.
- Si l'utilisateur confirme qu'une traduction est correcte,
  utilise valider_ngambay.
- Si l'utilisateur corrige une traduction existante,
  utilise corriger_ngambay.
- Si tu ne connais pas une phrase demandée,
  dis-le honnêtement plutôt que d'inventer une traduction.

VOCABULAIRE :

{str(vocabulaire)}
"""


# ============================================================
# OUTILS EXISTANTS
# ============================================================

TOOLS = [

    {
        "type": "function",

        "function": {

            "name": "remember",

            "description":
                "Save information in JIBI memory.",

            "parameters": {

                "type": "object",

                "properties": {

                    "key": {
                        "type": "string"
                    },

                    "value": {
                        "type": "string"
                    }
                },

                "required": [
                    "key",
                    "value"
                ]
            }
        }
    },


    {
        "type": "function",

        "function": {

            "name": "recall",

            "description":
                "Retrieve saved information.",

            "parameters": {

                "type": "object",

                "properties": {

                    "key": {
                        "type": "string"
                    }
                },

                "required": [
                    "key"
                ]
            }
        }
    },


    {
        "type": "function",

        "function": {

            "name": "web_search",

            "description":
                "Search the internet only when necessary.",

            "parameters": {

                "type": "object",

                "properties": {

                    "query": {
                        "type": "string"
                    }
                },

                "required": [
                    "query"
                ]
            }
        }
    },


    {
        "type": "function",

        "function": {

            "name": "exa_search",

            "description":
                "Recherche web alternative.",

            "parameters": {

                "type": "object",

                "properties": {

                    "query": {
                        "type": "string"
                    }
                },

                "required": [
                    "query"
                ]
            }
        }
    },


    {
        "type": "function",

        "function": {

            "name": "current_time_utc",

            "description":
                "Get current UTC time.",

            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },


    {
        "type": "function",

        "function": {

            "name": "apprendre_ngambay",

            "description":
                "Save a Ngambay phrase and its French translation.",

            "parameters": {

                "type": "object",

                "properties": {

                    "phrase_ngambay": {
                        "type": "string"
                    },

                    "traduction_fr": {
                        "type": "string"
                    }
                },

                "required": [
                    "phrase_ngambay",
                    "traduction_fr"
                ]
            }
        }
    },


    {
        "type": "function",

        "function": {

            "name": "rechercher_ngambay",

            "description":
                "Search Ngambay vocabulary.",

            "parameters": {

                "type": "object",

                "properties": {

                    "texte": {
                        "type": "string"
                    }
                },

                "required": [
                    "texte"
                ]
            }
        }
    },


    {
        "type": "function",

        "function": {

            "name": "valider_ngambay",

            "description":
                "Confirme qu'une traduction Ngambay est correcte.",

            "parameters": {

                "type": "object",

                "properties": {

                    "id_phrase": {
                        "type": "integer"
                    }
                },

                "required": [
                    "id_phrase"
                ]
            }
        }
    },


    {
        "type": "function",

        "function": {

            "name": "corriger_ngambay",

            "description":
                "Corrige une traduction Ngambay existante.",

            "parameters": {

                "type": "object",

                "properties": {

                    "id_phrase": {
                        "type": "integer"
                    },

                    "nouvelle_traduction_fr": {
                        "type": "string"
                    }
                },

                "required": [
                    "id_phrase",
                    "nouvelle_traduction_fr"
                ]
            }
        }
    }
]


# Ajoute les outils du dossier tools/ (navigateur, fichiers, PC,
# terminal, vision) à la liste statique ci-dessus, s'ils ont pu être
# chargés (dépendances optionnelles : playwright, mss, psutil).
if OUTILS_EXTERNES_DISPONIBLES:

    TOOLS = TOOLS + outils_registre.tools_ollama_format()

    log_event(
        "agent",
        f"{len(outils_registre.TOOLS_REGISTRY)} outils externes ajoutés à TOOLS"
    )


# ============================================================
# SÉLECTION DES OUTILS PERTINENTS SELON LE MESSAGE
# ============================================================
# Avec ~20 outils dans TOOLS, un petit modèle (llama3.2:1b) choisit mal
# l'outil juste sur la description. On réduit la liste envoyée à Ollama
# selon des mots-clés du message : moins de choix = bien plus fiable.

CATEGORIES_OUTILS = [
    (
        ("va sur", "vas sur", "rentre sur", "ouvre le site", "ouvre la page",
         "navigue vers", "sur google", "sur youtube", "sur internet",
         "ouvre google", "ouvre youtube", "clique sur", "remplis le champ",
         "ferme le navigateur"),
        ["ouvrir_url", "obtenir_texte_page", "cliquer", "remplir_champ", "fermer_navigateur"]
    ),
    (
        ("lis le fichier", "lire le fichier", "liste les fichiers",
         "crée un fichier", "cree un fichier", "supprime le fichier"),
        ["creer_fichier", "lire_fichier", "lister_fichiers", "supprimer_fichier"]
    ),
    (
        ("ton code", "ta source", "ton fichier", "tes fichiers", "code source",
         "lis ton code", "regarde ton code", "montre ton code", "inspecte ton code",
         "propose une amélioration", "propose une amelioration",
         "améliore-toi", "ameliore toi"),
        ["lire_code_source", "lister_code_source", "proposer_amelioration"]
    ),
    (
        ("ouvre l'application", "ouvre l application", "lance l'application",
         "lance l application", "ferme l'application", "ferme l application",
         "ouvre vscode", "ouvre vs code", "ouvre le terminal", "ouvre l'explorateur"),
        ["ouvrir_application", "fermer_application"]
    ),
    (
        ("exécute la commande", "execute la commande", "lance la commande",
         "dans le terminal"),
        ["executer_commande"]
    ),
    (
        ("capture l'écran", "capture l ecran", "capture d'écran", "capture d ecran",
         "analyse cette image", "analyse l'image", "que vois-tu à l'écran",
         "que vois tu a l'ecran", "regarde mon écran", "regarde mon ecran"),
        ["analyser_image", "capturer_ecran", "capturer_et_analyser"]
    ),
    (
        ("souviens-toi", "souviens toi", "rappelle-toi", "rappelle toi",
         "mémorise", "memorise", "n'oublie pas", "n oublie pas",
         "qu'est-ce que tu sais de moi", "que sais-tu de moi",
         "ma mémoire", "mémoire", "mon prénom", "mon nom",
         "comment je m'appelle"),
        ["remember", "recall"]
    ),
    (
        ("ngambay", "ngambaye", "en ngambay", "en ngambaye"),
        ["apprendre_ngambay", "rechercher_ngambay", "valider_ngambay", "corriger_ngambay"]
    ),
    (
        ("mets à jour", "met à jour", "mise à jour", "mises à jour",
         "vérifie les mises à jour", "verifie les mises a jour",
         "cherche une mise à jour", "il y a une mise à jour",
         "annule la mise à jour", "annule la derniere mise a jour",
         "reviens à la version précédente", "reviens a la version precedente",
         "restaure la sauvegarde", "reviens en arrière", "reviens en arriere",
         "rollback"),
        ["verifier_mise_a_jour", "appliquer_mise_a_jour", "restaurer_derniere_sauvegarde"]
    ),
]


def outils_pour_message(message):
    """
    Restreint la liste d'outils envoyée à Ollama selon des mots-clés
    du message, pour aider un petit modèle à choisir le bon outil
    parmi un choix réduit plutôt que parmi les ~20 disponibles.

    Si aucune catégorie précise n'est détectée (ex: verbe générique
    seul via MOTS_ACTION_SYSTEME), on ne restreint rien et le modèle
    garde accès à tous les outils.
    """

    texte = " ".join(message.lower().strip().split())

    noms_retenus = set()

    for mots_cles, noms_outils in CATEGORIES_OUTILS:
        if any(mot in texte for mot in mots_cles):
            noms_retenus.update(noms_outils)

    if not noms_retenus:
        return TOOLS

    return [
        outil for outil in TOOLS
        if outil["function"]["name"] in noms_retenus
    ]


# ============================================================
# RACCOURCI DÉTERMINISTE : SITES CONNUS
# ============================================================
# Un modèle de 1B paramètres décide de façon peu fiable QUAND appeler
# un outil sur une phrase courte sans URL explicite ("va sur google").
# Pour les sites les plus courants, on résout nous-mêmes l'URL et on
# appelle directement ouvrir_url, sans dépendre de la décision
# (faillible) du modèle. Le modèle garde la main pour tout le reste
# (sites non listés, actions plus complexes, etc.).

SITES_CONNUS = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "wikipedia": "https://www.wikipedia.org",
    "facebook": "https://www.facebook.com",
    "twitter": "https://twitter.com",
    "instagram": "https://www.instagram.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
}

MOTS_DECLENCHEURS_NAVIGATION = (
    "va sur", "vas sur", "rentre sur", "navigue vers", "aller sur",
    "ouvre google", "ouvre youtube", "ouvre gmail", "ouvre wikipedia",
    "ouvre facebook", "ouvre twitter", "ouvre instagram", "ouvre github",
    "ouvre chatgpt",
)


def url_directe_pour_message(message):
    """
    Si le message mentionne un site connu ET un verbe de navigation,
    renvoie directement son URL http(s) — sans passer par le modèle.
    Renvoie None si rien de fiable n'est détecté (le modèle prend le
    relais via _reponse_avec_tools, comme avant).
    """

    texte = " ".join(message.lower().strip().split())

    if not any(mot in texte for mot in MOTS_DECLENCHEURS_NAVIGATION):
        return None

    for nom_site, url in SITES_CONNUS.items():
        if nom_site in texte:
            return url

    return None


# ============================================================
# MÉMOIRE ASYNCHRONE
# ============================================================

def _indexer_memoire_async(
    user_id,
    cle,
    valeur
):

    threading.Thread(

        target=memory_manager.indexer_memoire,

        args=(
            user_id,
            cle,
            valeur
        ),

        daemon=True

    ).start()


# ============================================================
# EXÉCUTION DES OUTILS
# ============================================================

def run_tool(
    name,
    arguments
):

    if name == "remember":

        resultat = remember_memory_db(
            USER_ID,
            arguments["key"],
            arguments["value"]
        )

        _indexer_memoire_async(
            USER_ID,
            arguments["key"],
            arguments["value"]
        )

        return resultat


    if name == "recall":

        return recall_db(
            USER_ID,
            arguments["key"]
        )


    if name == "web_search":

        return web_search(
            arguments["query"]
        )


    if name == "exa_search":

        return exa_search(
            arguments["query"]
        )


    if name == "current_time_utc":

        return datetime.now(
            timezone.utc
        ).isoformat()


    if name == "apprendre_ngambay":

        return ajouter_ngambay(
            arguments["phrase_ngambay"],
            arguments["traduction_fr"]
        )


    if name == "rechercher_ngambay":

        return rechercher_langue_ngambay(
            arguments["texte"]
        )


    if name == "valider_ngambay":

        return valider_ngambay(
            arguments["id_phrase"]
        )


    if name == "corriger_ngambay":

        return corriger_ngambay(
            arguments["id_phrase"],
            arguments["nouvelle_traduction_fr"]
        )


    # --------------------------------------------------------
    # OUTILS DU DOSSIER tools/ (navigateur, fichiers, PC, terminal, vision)
    # --------------------------------------------------------
    if OUTILS_EXTERNES_DISPONIBLES:

        fonction_outil = outils_registre.get_tool(name)

        if fonction_outil:

            try:
                return fonction_outil(**arguments)

            except Exception as e:
                log_error(
                    "tools",
                    f"{name} échoué: {e}",
                    exc_info=False
                )

                return {"error": str(e)[:200]}


    return {
        "error":
            f"Outil inconnu : {name}"
    }


# ============================================================
# CONFIGURATION MÉMOIRE
# ============================================================

MEMOIRE_CONTEXTE_AUTO = (
    os.getenv(
        "MEMOIRE_CONTEXTE_AUTO",
        "0"
    ) != "0"
)


# ============================================================
# HISTORIQUE
# ============================================================

def _historique_messages(message):

    vocabulaire = (
        vocabulaire_pour_message(message)
        if besoin_ngambay(message)
        else None
    )

    historique = historique_conversation(

        USER_ID,

        limite=HISTORIQUE_MAX,

        minutes_max=HISTORIQUE_FENETRE_MINUTES

    )

    system_prompt = construire_system_prompt(
        vocabulaire,
        inclure_ngambay=besoin_ngambay(message)
    )


    # Mémoire sémantique optionnelle
    if MEMOIRE_CONTEXTE_AUTO:

        try:

            contexte_memoire = (
                memory_manager
                .construire_contexte_memoire(
                    USER_ID,
                    message
                )
            )

        except Exception as e:

            log_warning(
                "memoire_semantique",
                f"Contexte mémoire indisponible: {e}"
            )

            contexte_memoire = ""


        if contexte_memoire:

            system_prompt += (
                "\n\n" +
                contexte_memoire
            )


    messages = [

        {
            "role": "system",
            "content": system_prompt
        }

    ]


    for role, contenu in historique:

        if role in (
            "user",
            "assistant"
        ):

            messages.append(
                {
                    "role": role,
                    "content": contenu
                }
            )


    messages.append(
        {
            "role": "user",
            "content": message
        }
    )


    return messages


# ============================================================
# OPTIONS OLLAMA
# ============================================================

def _ollama_options():

    return {

        "temperature":
            float(
                os.getenv(
                    "OLLAMA_TEMPERATURE",
                    "0.7"
                )
            ),

        "num_ctx":
            int(
                os.getenv(
                    "OLLAMA_NUM_CTX",
                    "1536"
                )
            ),

        "num_predict":
            int(
                os.getenv(
                    "OLLAMA_NUM_PREDICT",
                    "180"
                )
            ),

        "num_thread":
            int(
                os.getenv(
                    "OLLAMA_NUM_THREAD",
                    str(os.cpu_count() or 4)
                )
            )
    }


# ============================================================
# RÉPONSE OLLAMA DIRECTE
# ============================================================

def _reponse_ollama_directe(
    messages,
    on_chunk=None
):

    options = _ollama_options()


    # CLI
    if on_chunk is None:

        response = _client_ollama.chat(

            model=MODEL,

            messages=messages,

            tools=[],

            keep_alive=OLLAMA_KEEP_ALIVE,

            options=options
        )

        return (
            response["message"]
            .get("content", "")
            .strip()
        )


    # GUI / streaming
    reponse_complete = ""


    for fragment in _client_ollama.chat(

        model=MODEL,

        messages=messages,

        tools=[],

        keep_alive=OLLAMA_KEEP_ALIVE,

        options=options,

        stream=True

    ):

        morceau = (
            fragment["message"]
            .get("content", "")
        )


        if morceau:

            reponse_complete += morceau

            on_chunk(morceau)


    return reponse_complete.strip()


# ============================================================
# RECHERCHE WEB
# ============================================================

def _reponse_avec_recherche(

    message,
    messages,
    on_chunk=None

):

    resultat_web = web_search(
        message,
        max_results=3
    )


    messages_web = list(
        messages
    )


    messages_web[0] = {

        "role": "system",

        "content":
            messages[0]["content"]

            +

            "\n\nVoici les résultats "
            "Internet récupérés par JIBI. "

            "Utilise-les pour répondre. "

            "Ne prétends pas avoir vérifié "
            "une information qui n'apparaît "
            "pas dans les résultats.\n"

            +

            str(resultat_web)
    }


    return _reponse_ollama_directe(

        messages_web,

        on_chunk=on_chunk

    )


# ============================================================
# CONNAISSANCES / CHROMA
# ============================================================

def _reponse_avec_connaissances(

    message,
    messages,
    on_chunk=None

):

    contexte = (
        connaissances
        .contexte_connaissances(
            message
        )
    )


    messages_doc = list(
        messages
    )


    if contexte:

        messages_doc[0] = {

            "role": "system",

            "content":
                messages[0]["content"]

                +

                "\n\n"

                +

                contexte

        }


    return _reponse_ollama_directe(

        messages_doc,

        on_chunk=on_chunk

    )


# ============================================================
# CONFIRMATION AVANT ACTION SENSIBLE
# ============================================================

# Outils qui ne doivent JAMAIS s'exécuter directement sur simple décision
# du modèle : une confirmation explicite de l'utilisateur est requise
# avant l'appel réel à run_tool. Complète les garde-fous déjà présents
# dans chaque module (liste blanche, dossier confiné, etc.) par une
# étape humaine dans la boucle, car un modèle 3B peut se tromper sur
# l'opportunité d'agir.
OUTILS_SENSIBLES = {
    "executer_commande",
    "fermer_application",
    "supprimer_fichier",
    "appliquer_mise_a_jour",
    "restaurer_derniere_sauvegarde",
}

MOTS_CONFIRMATION_OUI = {
    "oui", "ok", "d'accord", "daccord", "vas-y", "vas y",
    "confirme", "confirmé", "je confirme", "yes", "yep"
}

MOTS_CONFIRMATION_NON = {
    "non", "annule", "annulé", "stop", "no", "laisse tomber"
}

# Une seule confirmation en attente par utilisateur à la fois.
_CONFIRMATION_EN_ATTENTE = {}


def _decrire_action(nom, arguments):

    if nom == "executer_commande":
        return f"exécuter la commande : {arguments.get('commande', '')}"

    if nom == "fermer_application":
        return f"fermer l'application '{arguments.get('nom', '')}'"

    if nom == "supprimer_fichier":
        return f"supprimer le fichier '{arguments.get('chemin', '')}'"

    if nom == "appliquer_mise_a_jour":
        return "appliquer la dernière mise à jour de JIBI (une sauvegarde sera créée avant)"

    if nom == "restaurer_derniere_sauvegarde":
        return "restaurer JIBI à partir de la dernière sauvegarde (annuler la dernière mise à jour)"

    return f"exécuter l'outil '{nom}'"


def _demander_confirmation(nom, arguments):

    _CONFIRMATION_EN_ATTENTE[USER_ID] = {
        "nom": nom,
        "arguments": arguments
    }

    log_event(
        "securite",
        f"Confirmation demandée pour: {nom}"
    )

    return (
        f"⚠️ Je m'apprête à {_decrire_action(nom, arguments)}. "
        f"Confirmes-tu ? (oui/non)"
    )


def _traiter_confirmation(message):
    """
    Si une action sensible attend confirmation, interprète ce message
    comme la réponse à cette confirmation plutôt que comme une nouvelle
    question. Renvoie None si rien n'est en attente : le traitement
    normal doit alors continuer.
    """

    en_attente = _CONFIRMATION_EN_ATTENTE.get(USER_ID)

    if not en_attente:
        return None

    texte = " ".join(message.strip().lower().split())

    if texte in MOTS_CONFIRMATION_OUI:

        del _CONFIRMATION_EN_ATTENTE[USER_ID]

        arguments_confirmes = dict(en_attente["arguments"])

        # supprimer_fichier, fermer_application, appliquer_mise_a_jour et
        # restaurer_derniere_sauvegarde exigent confirmer=True côté module
        # — le modèle ne le fournit jamais lui-même, c'est justement
        # l'humain qui vient de le faire ici.
        if en_attente["nom"] in (
            "supprimer_fichier", "fermer_application",
            "appliquer_mise_a_jour", "restaurer_derniere_sauvegarde"
        ):
            arguments_confirmes["confirmer"] = True

        try:
            resultat = run_tool(
                en_attente["nom"],
                arguments_confirmes
            )

            log_event(
                "securite",
                f"Action confirmée exécutée: {en_attente['nom']}"
            )

            return f"C'est fait. {resultat}"

        except Exception as e:

            log_error(
                "securite",
                f"Action confirmée échouée: {e}",
                exc_info=False
            )

            return f"L'action a échoué : {str(e)[:150]}"

    if texte in MOTS_CONFIRMATION_NON:

        del _CONFIRMATION_EN_ATTENTE[USER_ID]

        log_event(
            "securite",
            f"Action annulée: {en_attente['nom']}"
        )

        return "D'accord, annulé."

    # Réponse ambiguë : on garde la confirmation en attente et on
    # redemande, plutôt que d'exécuter ou d'abandonner par erreur.
    return (
        f"Je n'ai pas compris ta réponse. Confirmes-tu que je dois "
        f"{_decrire_action(en_attente['nom'], en_attente['arguments'])} ? "
        f"(réponds 'oui' ou 'non')"
    )


# ============================================================
# EXTRACTION AUTOMATIQUE DE FAITS (mémoire "à la Claude")
# ============================================================
#
# Plutôt que d'attendre un "souviens-toi" explicite, on extrait en
# arrière-plan (sans jamais ralentir la réponse visible) les faits
# durables que l'utilisateur partage naturellement — nom, préférences,
# projets en cours, habitudes. Mêmes principes que la mémoire de
# Claude : on ne retient QUE ce qui est explicitement dit (jamais une
# inférence), on exclut le contenu sensible, et un échec d'extraction
# ne doit jamais impacter la conversation elle-même (best-effort).

PROMPT_EXTRACTION_FAITS = """Tu analyses UN SEUL message d'un utilisateur pour repérer un fait DURABLE à mémoriser sur le long terme (comme un profil utilisateur), pas une question ponctuelle ni une demande d'action.

Réponds UNIQUEMENT avec du JSON, rien d'autre, pas de ```:
- Si un fait durable est clairement énoncé : {{"cle": "nom_court_snake_case", "valeur": "le fait en une phrase"}}
- Sinon (question, salutation, demande d'action, rien de durable) : {{"cle": null, "valeur": null}}

Règles strictes :
- Ne retiens QUE ce que l'utilisateur a dit explicitement, jamais une supposition.
- Exclus toujours : santé, finances précises, mots de passe, identifiants, contenu sensible.
- Ignore les questions et demandes d'action (ex: "ouvre X", "quelle heure est-il", "exécute Y").
- Exemples de faits valables : prénom, métier, préférence alimentaire, projet en cours, animal de compagnie, ville, passe-temps.

Message de l'utilisateur : "{message}"
"""


def _extraire_faits_async(message):
    """Lance l'extraction en arrière-plan, sans jamais bloquer la réponse."""

    threading.Thread(
        target=_extraire_faits,
        args=(message,),
        daemon=True
    ).start()


def _extraire_faits(message):

    texte = message.strip()

    # Messages trop courts (salutations, "oui"/"non", etc.) : pas la
    # peine de solliciter le modèle, il n'y a jamais de fait dedans.
    if len(texte) < 8:
        return

    try:
        reponse = _client_ollama.chat(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT_EXTRACTION_FAITS.format(
                        message=texte.replace('"', "'")
                    )
                }
            ],
            options={"temperature": 0}
        )

        contenu = reponse["message"]["content"].strip()

        # Le modèle ajoute parfois des ```json ... ``` malgré la consigne.
        contenu = contenu.strip("`")
        if contenu.lower().startswith("json"):
            contenu = contenu[4:].strip()

        import json as _json
        data = _json.loads(contenu)

        cle = data.get("cle")
        valeur = data.get("valeur")

        if not cle or not valeur:
            return

        cle = str(cle).strip().lower().replace(" ", "_")[:100]
        valeur = str(valeur).strip()[:500]

        if not cle or not valeur:
            return

        remember_memory_db(USER_ID, cle, valeur)
        _indexer_memoire_async(USER_ID, cle, valeur)

        log_event(
            "memoire_auto",
            f"Fait extrait automatiquement: {cle} = {valeur[:60]}"
        )

    except Exception as e:
        # Best-effort : un échec d'extraction ne doit jamais remonter
        # à l'utilisateur ni impacter sa conversation.
        log_warning(
            "memoire_auto",
            f"Extraction échouée: {e}"
        )


# ============================================================
# OUTILS MÉMOIRE / NGAMBAY
# ============================================================

# Un petit modèle applique parfois un réflexe de refus générique
# ("je ne peux pas voir mon propre code", "je ne peux pas agir sur ton
# PC"...) même quand un vrai outil le lui permet. Ce rappel est ajouté
# au message système existant, uniquement pour les tours où des outils
# sont proposés, afin de contrer ce réflexe sans changer le ton de
# JIBI pour les conversations normales.
PROMPT_SYSTEME_OUTILS = (
    "Tu disposes de vrais outils exécutables : navigateur, gestion de "
    "fichiers, lecture de ton propre code source, contrôle du PC, "
    "terminal, vision. Quand une action outil est proposée et pertinente "
    "pour la demande, appelle l'outil correspondant plutôt que de "
    "répondre uniquement par du texte. Tu as bien accès en LECTURE à "
    "ton propre code source via les outils lire_code_source et "
    "lister_code_source : ne dis jamais que tu ne peux pas voir ton "
    "code, utilise l'outil approprié."
)


def _reponse_avec_tools(

    message,
    messages

):

    messages = list(
        messages
    )

    if messages and messages[0].get("role") == "system":

        messages[0] = {
            "role": "system",
            "content": (
                messages[0]["content"]
                + "\n\n"
                + PROMPT_SYSTEME_OUTILS
            )
        }

    else:

        messages.insert(
            0,
            {"role": "system", "content": PROMPT_SYSTEME_OUTILS}
        )


    for _ in range(2):

        response = _client_ollama.chat(

            model=MODEL,

            messages=messages,

            tools=outils_pour_message(message),

            keep_alive=OLLAMA_KEEP_ALIVE,

            options=_ollama_options()

        )


        message_response = (
            response["message"]
        )


        tool_calls = (
            message_response
            .get("tool_calls")
        )


        if not tool_calls:

            return (
                message_response
                .get("content", "")
                .strip()
            )


        messages.append(
            message_response
        )


        for tool_call in tool_calls:

            fonction = (
                tool_call["function"]
            )


            nom = fonction["name"]


            arguments = (
                fonction
                .get("arguments", {})
            )


            if isinstance(
                arguments,
                str
            ):

                try:

                    import ast

                    arguments = (
                        ast.literal_eval(
                            arguments
                        )
                    )

                except Exception:

                    arguments = {}


            log_event(
                "agent",
                f"Outil utilisé: {nom}"
            )


            if nom in OUTILS_SENSIBLES:

                return _demander_confirmation(
                    nom,
                    arguments
                )


            resultat = run_tool(
                nom,
                arguments
            )


            messages.append({

                "role": "tool",

                "content": str(
                    resultat
                )

            })


    return (
        "Désolé, je n'ai pas réussi "
        "à terminer."
    )


# ============================================================
# TRAITEMENT PRINCIPAL
# ============================================================

def _traiter_message(

    message,
    on_chunk=None

):

    log_event(
        "agent",
        f"Message reçu: {message[:50]}..."
    )


    enregistrer_message(

        USER_ID,

        "user",

        message

    )


    # --------------------------------------------------------
    # RÉPONSE À UNE CONFIRMATION EN ATTENTE
    # --------------------------------------------------------
    # Priorité absolue : si une action sensible attend confirmation,
    # ce message est traité comme la réponse à CETTE question, pas
    # comme une nouvelle demande.

    reponse_confirmation = _traiter_confirmation(
        message
    )


    if reponse_confirmation:

        enregistrer_message(

            USER_ID,

            "assistant",

            reponse_confirmation

        )


        if on_chunk:

            for mot in (
                reponse_confirmation
                .split(" ")
            ):

                on_chunk(
                    mot + " "
                )

                time.sleep(
                    0.02
                )


        return reponse_confirmation


    # --------------------------------------------------------
    # MÉMORISATION DU PRÉNOM
    # --------------------------------------------------------

    prenom = extraire_prenom(
        message
    )


    if prenom:

        try:

            remember_memory_db(

                USER_ID,

                "prenom",

                prenom

            )


            _indexer_memoire_async(

                USER_ID,

                "prenom",

                prenom

            )


            reponse_finale = (

                f"Enchanté {prenom} ! "
                f"Je retiendrai que tu "
                f"t'appelles {prenom}."
            )


            enregistrer_message(

                USER_ID,

                "assistant",

                reponse_finale

            )


            log_event(

                "memoire",

                f"Prénom mémorisé: {prenom}"

            )


            if on_chunk:

                for mot in (
                    reponse_finale
                    .split(" ")
                ):

                    on_chunk(
                        mot + " "
                    )

                    time.sleep(
                        0.02
                    )


            return reponse_finale


        except Exception as e:

            log_warning(

                "memoire",

                f"Impossible de mémoriser "
                f"le prénom: {e}"

            )


    # --------------------------------------------------------
    # MÉMOIRE SIMPLE
    # --------------------------------------------------------

    reponse_memoire = (
        memoire_directe(
            message
        )
    )


    if reponse_memoire:

        enregistrer_message(

            USER_ID,

            "assistant",

            reponse_memoire

        )


        log_event(

            "memoire",

            "Demande mémoire traitée "
            "directement depuis MySQL"

        )


        if on_chunk:

            for mot in (
                reponse_memoire
                .split(" ")
            ):

                on_chunk(
                    mot + " "
                )

                time.sleep(
                    0.02
                )


        return reponse_memoire


    # --------------------------------------------------------
    # QUESTION PRÉNOM
    # --------------------------------------------------------

    if demander_prenom(
        message
    ):

        try:

            prenom = recall_db(

                USER_ID,

                "prenom"

            )


            if (

                prenom

                and

                not str(
                    prenom
                ).startswith(
                    "No information"
                )

            ):

                reponse_finale = (
                    f"Tu t'appelles {prenom}."
                )

            else:

                reponse_finale = (
                    "Je ne connais pas "
                    "encore ton prénom."
                )


            enregistrer_message(

                USER_ID,

                "assistant",

                reponse_finale

            )


            log_event(

                "memoire",

                "Prénom récupéré "
                "directement depuis MySQL"

            )


            if on_chunk:

                for mot in (
                    reponse_finale
                    .split(" ")
                ):

                    on_chunk(
                        mot + " "
                    )

                    time.sleep(
                        0.02
                    )


            return reponse_finale


        except Exception as e:

            log_warning(

                "memoire",

                f"Lecture du prénom impossible: {e}"

            )


    # --------------------------------------------------------
    # CONSTRUCTION DU CONTEXTE
    # --------------------------------------------------------

    messages = _historique_messages(
        message
    )


    deja_stream = False


    try:

        # ----------------------------------------------------
        # DOCUMENTS
        # ----------------------------------------------------

        if besoin_connaissances(
            message
        ):

            deja_stream = (
                on_chunk is not None
            )


            reponse_finale = (
                _reponse_avec_connaissances(

                    message,

                    messages,

                    on_chunk=on_chunk

                )
            )


        # ----------------------------------------------------
        # ACTIONS / OUTILS (navigateur, fichiers, PC, terminal,
        # vision, mémoire, ngambay)
        # ----------------------------------------------------
        # Vérifié AVANT la recherche web : une demande d'action
        # explicite ("ouvre", "clique", "exécute"...) doit toujours
        # atteindre les vrais outils, même si le message contient
        # aussi un mot du type "cherche".

        elif besoin_outils(
            message
        ):

            url_directe = url_directe_pour_message(
                message
            )

            if url_directe:

                # Raccourci fiable : on ne laisse pas le petit modèle
                # deviner l'URL, on l'appelle directement.
                resultat_navigation = run_tool(
                    "ouvrir_url",
                    {"url": url_directe}
                )

                log_event(
                    "agent",
                    f"Outil utilisé (raccourci direct): ouvrir_url -> {url_directe}"
                )

                reponse_finale = str(
                    resultat_navigation
                )

            else:

                reponse_finale = (
                    _reponse_avec_tools(

                        message,

                        messages

                    )
                )


        # ----------------------------------------------------
        # INTERNET
        # ----------------------------------------------------

        elif besoin_recherche_web(
            message
        ):

            deja_stream = (
                on_chunk is not None
            )


            reponse_finale = (
                _reponse_avec_recherche(

                    message,

                    messages,

                    on_chunk=on_chunk

                )
            )


        # ----------------------------------------------------
        # QUESTION NORMALE
        # ----------------------------------------------------

        else:

            deja_stream = (
                on_chunk is not None
            )


            reponse_finale = (
                _reponse_ollama_directe(

                    messages,

                    on_chunk=on_chunk

                )
            )


        if not reponse_finale:

            reponse_finale = (
                "Je n'ai pas réussi "
                "à générer une réponse."
            )


        log_event(

            "ollama",

            f"Réponse complète "
            f"({len(reponse_finale)} chars)"

        )


    except ConnectionError:

        log_warning(
            "ollama",
            "Ollama non disponible"
        )


        reponse_finale = (

            "Je suis déconnecté. "
            "Assure-toi que Ollama est lancé "
            "(`ollama serve` dans un terminal)."

        )


    except Exception as e:

        log_error(

            "ollama",

            f"Exception: "
            f"{type(e).__name__}: "
            f"{str(e)[:100]}",

            exc_info=False

        )


        if "timeout" in str(e).lower():

            reponse_finale = (

                "Ollama a pris trop de temps. "
                "Vérifie que le modèle "
                f"{MODEL} est bien chargé."

            )


        elif "llama" in str(e).lower():

            reponse_finale = (

                f"Le modèle {MODEL} "
                "n'est pas chargé. "

                f"Essaie: "
                f"`ollama pull {MODEL}`"

            )


        else:

            reponse_finale = (

                f"Erreur Ollama: "
                f"{str(e)[:100]}"

            )


    # --------------------------------------------------------
    # SAUVEGARDE
    # --------------------------------------------------------

    enregistrer_message(

        USER_ID,

        "assistant",

        reponse_finale

    )


    # --------------------------------------------------------
    # STREAMING POUR LES CHEMINS NON STREAMÉS
    # --------------------------------------------------------

    if (

        on_chunk

        and

        not deja_stream

    ):

        for mot in (
            reponse_finale
            .split(" ")
        ):

            on_chunk(
                mot + " "
            )

            time.sleep(
                0.02
            )


    return reponse_finale


# ============================================================
# API POUR GUI
# ============================================================

def ask_agent_stream(
    message,
    on_chunk
):

    return _traiter_message(

        message,

        on_chunk=on_chunk

    )


# ============================================================
# API CLASSIQUE
# ============================================================

def ask_agent(
    message
):

    return _traiter_message(

        message,

        on_chunk=None

    )


# ============================================================
# TEST TERMINAL
# ============================================================

if __name__ == "__main__":

    print(
        "================================"
    )

    print(
        "          JIBI RAPIDE"
    )

    print(
        "================================"
    )

    print(
        f"Modèle : {MODEL}"
    )

    print(
        "Tape 'quit' pour quitter."
    )


    while True:

        texte = input(
            "\nVous : "
        ).strip()


        if texte.lower() == "quit":

            break


        if not texte:

            continue


        try:

            debut = datetime.now()


            reponse = ask_agent(
                texte
            )


            fin = datetime.now()


            duree = (
                fin - debut
            ).total_seconds()


            print(
                f"\nJIBI : {reponse}"
            )


            print(
                f"\n⏱️ Temps : "
                f"{duree:.2f}s"
            )


        except Exception as e:

            print(
                "\nErreur :",
                e
            )