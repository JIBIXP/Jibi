"""
CERVEAU JIBI — v12.4
====================

Responsabilité :
    Communiquer avec le LLM et produire des résultats structurés.

Le cerveau :
    - ne modifie jamais les fichiers de production ;
    - ne crée jamais de fichier ;
    - ne décide jamais d'appliquer un patch ;
    - ne gère jamais les autorisations ;
    - ne gère jamais les backups ;
    - ne gère jamais les rollbacks.

Chaîne :
    observateur
        ↓
    diagnostiqueur / analyseur
        ↓
    cerveau
        ↓
    generateur_patch
        ↓
    propositions
        ↓
    laboratoire
        ↓
    validateur
        ↓
    risk_engine
        ↓
    orchestrateur

v12.4 :
    - LLM = enrichissement OPTIONNEL (pas obligatoire)
    - Fallback déterministe TOUJOURS calculé
    - Résultat garanti même si LLM échoue/timeout
    - regroupement déterministe des problèmes (detecteur.py)
    - sélection équilibrée des groupes (diversité des types)
    - contexte compact (5 groupes max)
    - prompt simplifié pour ANALYSE_PROBLEMES
    - timeout adapté (90s pour ANALYSE_PROBLEMES)
    - profils ANALYSE_CODE / ANALYSE_PROJET / ANALYSE_PROBLEMES
    - JSON robuste
    - aucune écriture de production
"""

from __future__ import annotations

import ast
import json
import re
import threading
import time

from typing import Any, Callable, Dict, List, Optional, Tuple

from core import config as _cfg


# ============================================================
# IMPORTS OPTIMISATION
# ============================================================

try:
    from self_improvement.detecteur import (
        regrouper_problemes,
    )
except Exception:
    regrouper_problemes = None


# ============================================================
# CONFIGURATION
# ============================================================

API = str(
    getattr(
        _cfg,
        "LLM_API",
        "ollama",
    )
).lower()

URL = str(
    getattr(
        _cfg,
        "OLLAMA_HOST",
        "http://localhost:11434",
    )
).rstrip("/")

MODEL = str(
    getattr(
        _cfg,
        "MODEL",
        "llama3.2:3b",
    )
)

MODEL_CODE = str(
    getattr(
        _cfg,
        "MODEL_CODE",
        MODEL,
    )
)

KEY = str(
    getattr(
        _cfg,
        "LLM_KEY",
        "",
    )
)

TIMEOUT = int(
    getattr(
        _cfg,
        "TIMEOUT_OLLAMA",
        120,
    )
)

TIMEOUT_CODE = int(
    getattr(
        _cfg,
        "TIMEOUT_CODE",
        300,
    )
)

OLLAMA_KEEP_ALIVE = str(
    getattr(
        _cfg,
        "OLLAMA_KEEP_ALIVE",
        "30m",
    )
)

OLLAMA_NUM_CTX = int(
    getattr(
        _cfg,
        "OLLAMA_NUM_CTX",
        4096,
    )
)

OLLAMA_NUM_THREADS = int(
    getattr(
        _cfg,
        "OLLAMA_NUM_THREADS",
        4,
    )
)


# ============================================================
# PROFILS
# ============================================================

PROFILS = {
    "CONVERSATION": {
        "num_predict": int(
            _cfg.OLLAMA_PREDICT_CHAT
        ),
        "temperature": float(
            _cfg.OLLAMA_TEMPERATURE_CHAT
        ),
    },

    "QUESTION": {
        "num_predict": int(
            _cfg.OLLAMA_PREDICT_QUESTION
        ),
        "temperature": float(
            _cfg.OLLAMA_TEMPERATURE_QUESTION
        ),
    },

    "CODE": {
        "num_predict": int(
            _cfg.OLLAMA_PREDICT_CODE
        ),
        "temperature": float(
            _cfg.OLLAMA_TEMPERATURE_CODE
        ),
    },

    "ANALYSE_CODE": {
        "num_predict": 320,
        "temperature": 0.1,
    },

    "ANALYSE_PROJET": {
        "num_predict": 384,
        "temperature": 0.1,
    },

    "ANALYSE_PROBLEMES": {
        "num_predict": 160,
        "temperature": 0.0,
    },

    "TACHE_COMPLEXE": {
        "num_predict": int(
            _cfg.OLLAMA_PREDICT_COMPLEXE
        ),
        "temperature": float(
            _cfg.OLLAMA_TEMPERATURE_COMPLEXE
        ),
    },

    "RECHERCHE": {
        "num_predict": int(
            _cfg.OLLAMA_PREDICT_RECHERCHE
        ),
        "temperature": float(
            _cfg.OLLAMA_TEMPERATURE_RECHERCHE
        ),
    },
}


# ============================================================
# PROMPTS DE BASE
# ============================================================

try:
    from core.prompts import PROMPT_SYSTEME

    SYSTEME_JIBI = PROMPT_SYSTEME.strip()

except Exception:
    SYSTEME_JIBI = (
        "Tu es JIBI, un assistant IA local écrit en Python. "
        "Réponds en français, clairement et concrètement."
    )


def _system_for(
    profil: str,
) -> str:
    """
    Retourne le prompt système adapté au profil.
    """

    try:
        from core.prompts import (
            PROMPT_BASE,
            PROMPT_CONVERSATION,
            PROMPT_CODE,
            PROMPT_RECHERCHE,
            PROMPT_ACTION,
        )

        mapping = {
            "CONVERSATION": PROMPT_CONVERSATION,
            "QUESTION": PROMPT_CONVERSATION,
            "CODE": PROMPT_CODE,
            "ANALYSE_CODE": PROMPT_CODE,
            "ANALYSE_PROJET": PROMPT_CODE,
            "ANALYSE_PROBLEMES": PROMPT_CODE,
            "RECHERCHE": PROMPT_RECHERCHE,
            "TACHE_COMPLEXE": PROMPT_ACTION,
        }

        return mapping.get(
            profil,
            PROMPT_BASE,
        )

    except Exception:
        return SYSTEME_JIBI


def _system_analyse_code() -> str:
    """
    Prompt strict pour analyse d'un fichier.
    """

    return """
Tu es le moteur d'analyse technique de JIBI.

Tu travailles uniquement à partir de données produites
par un analyseur statique Python.

RÈGLES :
- ne rien inventer ;
- ne pas supposer un problème absent des données ;
- ne pas utiliser de connaissances externes ;
- utiliser les vrais noms ;
- utiliser les vraies lignes ;
- toute amélioration doit avoir une preuve ;
- pas de conseils génériques sans preuve ;
- maximum 3 améliorations ;
- si rien n'est justifié, retourner [].

Catégories :
refactoring
architecture
complexite
import
qualite
securite
performance
tests

Réponds uniquement avec un objet JSON valide.
""".strip()


def _system_analyse_projet() -> str:
    """
    Prompt strict pour analyse du projet.
    """

    return """
Tu es l'architecte technique de JIBI.

Tu travailles uniquement à partir de la cartographie réelle
d'un projet Python.

RÈGLES :
- ne jamais inventer un fichier ;
- ne jamais inventer une dépendance ;
- utiliser uniquement les données fournies ;
- identifier les problèmes réellement visibles ;
- distinguer faits et recommandations ;
- maximum 3 améliorations ;
- ne pas remplir artificiellement la liste.

Réponds uniquement avec un objet JSON valide.
""".strip()


def _system_analyse_problemes() -> str:
    """
    Prompt minimal pour la synthèse des problèmes détectés.
    """

    return """
Tu es le moteur de synthèse technique de JIBI.

Utilise uniquement les problèmes fournis.

RÈGLES :
- ne rien inventer ;
- ne pas transformer une heuristique en certitude ;
- regrouper les symptômes d'une même cause ;
- identifier les causes racines ;
- chaque amélioration doit avoir une preuve ;
- maximum 3 améliorations ;
- améliorations distinctes.

Réponds uniquement en JSON valide.
""".strip()


# ============================================================
# REQUESTS
# ============================================================

try:
    import requests
except ImportError:
    requests = None


# ============================================================
# CACHE DISPONIBILITÉ
# ============================================================

_cache_dispo: Optional[bool] = None
_cache_t: float = 0.0
_cache_lock = threading.Lock()


def _headers() -> Dict[str, str]:
    """
    Construit les headers HTTP.
    """

    headers = {
        "Content-Type": "application/json"
    }

    if KEY:
        headers["Authorization"] = (
            f"Bearer {KEY}"
        )

    return headers


def _invalidate_disponibilite() -> None:
    global _cache_dispo
    global _cache_t

    with _cache_lock:
        _cache_dispo = None
        _cache_t = 0.0


# ============================================================
# DISPONIBILITÉ DU LLM
# ============================================================

def disponible(
    force: bool = False,
) -> bool:
    """
    Vérifie rapidement que le serveur LLM répond.
    """

    global _cache_dispo
    global _cache_t

    maintenant = time.time()

    with _cache_lock:
        if (
            _cache_dispo is not None
            and not force
            and maintenant - _cache_t < 10
        ):
            return bool(
                _cache_dispo
            )

    if requests is None:
        with _cache_lock:
            _cache_dispo = False
            _cache_t = maintenant

        return False

    try:

        if API == "ollama":

            response = requests.get(
                f"{URL}/api/tags",
                headers=_headers(),
                timeout=3,
            )

        else:

            response = requests.get(
                f"{URL}/models",
                headers=_headers(),
                timeout=3,
            )

        ok = response.status_code == 200

    except Exception:

        ok = False

    with _cache_lock:
        _cache_dispo = ok
        _cache_t = time.time()

    return ok


# ============================================================
# MESSAGES
# ============================================================

def _construire_messages(
    user: Any,
    system: Optional[str] = None,
    profil: str = "CONVERSATION",
) -> List[Dict[str, str]]:
    """
    Construit les messages envoyés au LLM.
    """

    if not isinstance(
        user,
        str,
    ):
        user = str(
            user
        )

    if system is None:
        system = _system_for(
            profil
        )

    return [
        {
            "role": "system",
            "content": system,
        },
        {
            "role": "user",
            "content": user,
        },
    ]


# ============================================================
# COMMUNICATION LLM
# ============================================================

def completer(
    user: Any,
    system: Optional[str] = None,
    profil: str = "CONVERSATION",
    stream: bool = False,
    on_chunk: Optional[Callable[[str], None]] = None,
    cancel_event: Any = None,
    json_mode: bool = False,
    temperature: Optional[float] = None,
) -> str:
    """
    Appelle le LLM.

    Aucun fichier de production n'est modifié.
    """

    if requests is None:
        raise RuntimeError(
            "Le module requests est requis."
        )

    if profil not in PROFILS:
        profil = "CONVERSATION"

    model_to_use = (
        MODEL_CODE
        if profil in {
            "CODE",
            "ANALYSE_CODE",
            "ANALYSE_PROJET",
            "ANALYSE_PROBLEMES",
            "TACHE_COMPLEXE",
        }
        else MODEL
    )

    cfg = PROFILS[
        profil
    ]

    if temperature is None:
        temperature = cfg[
            "temperature"
        ]

    try:

        temperature = float(
            temperature
        )

    except (
        TypeError,
        ValueError,
    ):

        temperature = 0.1

    temperature = max(
        0.0,
        min(
            2.0,
            temperature,
        ),
    )

    messages = _construire_messages(
        user=user,
        system=system,
        profil=profil,
    )

    # --------------------------------------------------------
    # TIMEOUT
    # --------------------------------------------------------

    if profil == "ANALYSE_PROBLEMES":

        timeout = min(
            TIMEOUT_CODE,
            90,  # Timeout adapté au contexte optimisé
        )

    elif profil in {
        "CODE",
        "ANALYSE_CODE",
        "ANALYSE_PROJET",
        "TACHE_COMPLEXE",
    }:

        timeout = TIMEOUT_CODE

    else:

        timeout = TIMEOUT

    # --------------------------------------------------------
    # OLLAMA
    # --------------------------------------------------------

    if API == "ollama":

        num_ctx = OLLAMA_NUM_CTX

        if profil in {
            "ANALYSE_CODE",
            "ANALYSE_PROJET",
        }:

            num_ctx = min(
                OLLAMA_NUM_CTX,
                2048,
            )

        elif profil == "ANALYSE_PROBLEMES":

            num_ctx = min(
                OLLAMA_NUM_CTX,
                1024,
            )

        options = {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": cfg[
                "num_predict"
            ],
            "num_thread": OLLAMA_NUM_THREADS,
        }

        body = {
            "model": model_to_use,
            "messages": messages,
            "stream": stream,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": options,
        }

        if json_mode:
            body["format"] = "json"

        try:

            if not stream:

                response = requests.post(
                    f"{URL}/api/chat",
                    json=body,
                    headers=_headers(),
                    timeout=timeout,
                )

                response.raise_for_status()

                data = response.json()

                if not isinstance(
                    data,
                    dict,
                ):

                    raise RuntimeError(
                        f"Réponse Ollama invalide : {data!r}"
                    )

                message = data.get(
                    "message",
                    {},
                )

                if not isinstance(
                    message,
                    dict,
                ):

                    raise RuntimeError(
                        "Message Ollama invalide."
                    )

                content = message.get(
                    "content",
                    "",
                )

                if not isinstance(
                    content,
                    str,
                ):

                    raise RuntimeError(
                        "Contenu Ollama non textuel."
                    )

                return content

            morceaux: List[str] = []

            with requests.post(
                f"{URL}/api/chat",
                json=body,
                headers=_headers(),
                stream=True,
                timeout=timeout,
            ) as response:

                response.raise_for_status()

                for line in response.iter_lines(
                    decode_unicode=True,
                ):

                    if (
                        cancel_event is not None
                        and cancel_event.is_set()
                    ):
                        break

                    if not line:
                        continue

                    try:

                        data = json.loads(
                            line
                        )

                    except (
                        json.JSONDecodeError,
                        TypeError,
                    ):

                        continue

                    message = data.get(
                        "message",
                        {},
                    )

                    if not isinstance(
                        message,
                        dict,
                    ):

                        message = {}

                    chunk = message.get(
                        "content",
                        "",
                    )

                    if chunk:

                        morceaux.append(
                            chunk
                        )

                        if on_chunk:

                            try:
                                on_chunk(
                                    chunk
                                )
                            except Exception:
                                pass

                    if data.get(
                        "done"
                    ):

                        break

            return "".join(
                morceaux
            )

        except requests.Timeout as exc:

            _invalidate_disponibilite()

            raise RuntimeError(
                f"Timeout LLM après {timeout}s."
            ) from exc

        except requests.ConnectionError as exc:

            _invalidate_disponibilite()

            raise RuntimeError(
                f"Impossible de joindre le serveur LLM : {URL}"
            ) from exc

        except requests.RequestException as exc:

            _invalidate_disponibilite()

            raise RuntimeError(
                f"Erreur HTTP LLM : {exc}"
            ) from exc

    # --------------------------------------------------------
    # OPENAI COMPATIBLE
    # --------------------------------------------------------

    body = {
        "model": model_to_use,
        "messages": messages,
        "temperature": temperature,
        "stream": stream,
    }

    if json_mode:

        body[
            "response_format"
        ] = {
            "type": "json_object"
        }

    try:

        response = requests.post(
            f"{URL}/chat/completions",
            json=body,
            headers=_headers(),
            timeout=timeout,
        )

        response.raise_for_status()

        data = response.json()

    except requests.Timeout as exc:

        _invalidate_disponibilite()

        raise RuntimeError(
            f"Timeout LLM après {timeout}s."
        ) from exc

    except requests.ConnectionError as exc:

        _invalidate_disponibilite()

        raise RuntimeError(
            f"Impossible de joindre le serveur LLM : {URL}"
        ) from exc

    except requests.RequestException as exc:

        _invalidate_disponibilite()

        raise RuntimeError(
            f"Erreur HTTP LLM : {exc}"
        ) from exc

    if not isinstance(
        data,
        dict,
    ):

        raise RuntimeError(
            f"Réponse API invalide : {data!r}"
        )

    choices = data.get(
        "choices",
        [],
    )

    if not isinstance(
        choices,
        list,
    ) or not choices:

        raise RuntimeError(
            f"Réponse API sans choix : {data!r}"
        )

    message = choices[
        0
    ]

    if not isinstance(
        message,
        dict,
    ):

        raise RuntimeError(
            f"Réponse API invalide : {data!r}"
        )

    message_data = message.get(
        "message",
        {},
    )

    if not isinstance(
        message_data,
        dict,
    ):

        raise RuntimeError(
            f"Réponse API invalide : {data!r}"
        )

    content = message_data.get(
        "content",
        "",
    )

    if not isinstance(
        content,
        str,
    ):

        raise RuntimeError(
            f"Contenu API invalide : {data!r}"
        )

    return content


# ============================================================
# EXTRACTION JSON
# ============================================================

def _extraire_json_objet(
    texte: Any,
) -> Optional[Dict[str, Any]]:
    """
    Extrait un objet JSON même lorsque le modèle
    ajoute accidentellement du texte.
    """

    if not texte:
        return None

    texte = str(
        texte
    ).strip()

    # --------------------------------------------------------
    # JSON DIRECT
    # --------------------------------------------------------

    try:

        data = json.loads(
            texte
        )

        if isinstance(
            data,
            dict,
        ):
            return data

    except (
        json.JSONDecodeError,
        TypeError,
    ):

        pass

    # --------------------------------------------------------
    # BLOC MARKDOWN
    # --------------------------------------------------------

    match = re.search(
        r"```(?:json)?\s*(.*?)```",
        texte,
        re.DOTALL | re.IGNORECASE,
    )

    if match:

        bloc = match.group(
            1
        ).strip()

        try:

            data = json.loads(
                bloc
            )

            if isinstance(
                data,
                dict,
            ):
                return data

        except (
            json.JSONDecodeError,
            TypeError,
        ):

            pass

    # --------------------------------------------------------
    # RECHERCHE OBJET
    # --------------------------------------------------------

    debut = texte.find(
        "{"
    )

    if debut < 0:
        return None

    profondeur = 0
    dans_chaine = False
    echappe = False

    for index in range(
        debut,
        len(texte),
    ):

        caractere = texte[
            index
        ]

        if dans_chaine:

            if echappe:

                echappe = False

            elif caractere == "\\":

                echappe = True

            elif caractere == '"':

                dans_chaine = False

            continue

        if caractere == '"':

            dans_chaine = True

        elif caractere == "{":

            profondeur += 1

        elif caractere == "}":

            profondeur -= 1

            if profondeur == 0:

                candidat = texte[
                    debut:index + 1
                ]

                try:

                    data = json.loads(
                        candidat
                    )

                    if isinstance(
                        data,
                        dict,
                    ):
                        return data

                except (
                    json.JSONDecodeError,
                    TypeError,
                ):

                    return None

    return None


def completer_json(
    user: Any,
    system: Optional[str] = None,
    profil: str = "TACHE_COMPLEXE",
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Complétion JSON sans masquer l'échec du modèle.
    """

    try:

        texte = completer(
            user=user,
            system=system,
            profil=profil,
            json_mode=True,
            temperature=temperature,
        )

    except Exception as exc:

        return {
            "_json_error": True,
            "_raw": "",
            "_exception": str(
                exc
            ),
        }

    resultat = _extraire_json_objet(
        texte
    )

    if resultat is not None:
        return resultat

    return {
        "_json_error": True,
        "_raw": str(
            texte or ""
        ),
    }


# ============================================================
# PLANIFICATION (routage LLM pour messages ambigus)
# ============================================================

_INTENTIONS_PLAN = (
    "DISCUSSION",
    "QUESTION",
    "DIAGNOSTIC",
    "ANALYSE_CODE",
    "ETAT",
    "LISTE",
    "RECHERCHE",
    "OUVRIR_URL",
    "MODIFIER_FICHIER",
    "CREER_OUTIL",
    "EXECUTER_OUTIL",
    "TACHE_COMPLEXE",
)

_SYSTEM_PLANIFIER = """Tu es le routeur de JIBI.
Analyse le message de l'utilisateur et retourne UNIQUEMENT un JSON,
sans aucun texte ni markdown autour.

Le JSON doit contenir au minimum la clé "intention", dont la valeur
doit être EXACTEMENT une de ces valeurs (en majuscules) :
DISCUSSION, QUESTION, DIAGNOSTIC, ANALYSE_CODE, ETAT, LISTE,
RECHERCHE, OUVRIR_URL, MODIFIER_FICHIER, CREER_OUTIL, EXECUTER_OUTIL,
TACHE_COMPLEXE.

Ajoute les paramètres pertinents selon l'intention, si identifiables :
- "fichier" pour ANALYSE_CODE / MODIFIER_FICHIER
- "requete" pour RECHERCHE
- "nom_outil" et "arguments" pour CREER_OUTIL / EXECUTER_OUTIL

Si aucune intention claire ne se dégage, utilise "QUESTION".

Exemple de réponse :
{"intention": "ANALYSE_CODE", "fichier": "core/agent_core.py"}
"""


def planifier(
    message: Any,
) -> Dict[str, Any]:
    """
    Demande au LLM de produire un plan structuré (intention + paramètres)
    pour un message que la classification locale n'a pas su router.

    Ce plan est ensuite normalisé par router.extraire_plan() /
    router.normaliser_intention(), qui attendent une intention en
    MAJUSCULES parmi celles listées dans router.INTENTIONS.

    En cas d'échec du LLM ou de JSON invalide, retourne un plan de repli
    sûr plutôt que de laisser l'appelant planter sur un AttributeError
    ou un KeyError.
    """

    texte = str(message or "").strip()

    if not texte:
        return {"intention": "DISCUSSION"}

    resultat = completer_json(
        user=texte,
        system=_SYSTEM_PLANIFIER,
        profil="TACHE_COMPLEXE",
    )

    if not isinstance(resultat, dict) or resultat.get("_json_error"):
        # Repli sûr : pas de plan exploitable, on route vers une
        # question conversationnelle plutôt que de casser l'appelant.
        return {
            "intention": "QUESTION",
            "_plan_error": True,
            "_details": resultat if isinstance(resultat, dict) else str(resultat),
        }

    intention = str(resultat.get("intention", "")).strip().upper()

    if intention not in _INTENTIONS_PLAN:
        intention = "QUESTION"

    resultat["intention"] = intention

    return resultat


# ============================================================
# EXTRACTION CODE
# ============================================================

def extraire_code(
    texte: Any,
) -> str:

    if not isinstance(
        texte,
        str,
    ) or not texte.strip():

        raise ValueError(
            "Réponse vide du modèle."
        )

    texte = texte.strip()

    match = re.search(
        r"```(?:python|py)?\s*(.*?)```",
        texte,
        re.DOTALL | re.IGNORECASE,
    )

    code = (
        match.group(
            1
        ).strip()
        if match
        else texte
    )

    if not code:

        raise ValueError(
            "Code Python vide."
        )

    return code + "\n"


# ============================================================
# VALIDATION CODE
# ============================================================

def valider_code(
    code: Any,
    contexte: str = "",
) -> Tuple[str, bool, str]:

    if not isinstance(
        code,
        str,
    ):

        return (
            "",
            False,
            "Code non textuel",
        )

    if not code.strip():

        return (
            code,
            False,
            "Code vide",
        )

    try:

        arbre = ast.parse(
            code
        )

    except SyntaxError as exc:

        return (
            code,
            False,
            (
                f"Erreur syntaxe : "
                f"{exc.msg} "
                f"(ligne {exc.lineno})"
            ),
        )

    appels_interdits = {
        "eval",
        "exec",
        "__import__",
    }

    modules_interdits = {
        "subprocess",
        "ctypes",
    }

    for node in ast.walk(
        arbre
    ):

        if isinstance(
            node,
            ast.Call,
        ):

            nom = ""

            if isinstance(
                node.func,
                ast.Name,
            ):

                nom = node.func.id

            elif isinstance(
                node.func,
                ast.Attribute,
            ):

                nom = node.func.attr

            if nom in appels_interdits:

                return (
                    code,
                    False,
                    f"Appel interdit : {nom}()",
                )

            if (
                isinstance(
                    node.func,
                    ast.Attribute,
                )
                and node.func.attr
                in {
                    "system",
                    "popen",
                }
            ):

                return (
                    code,
                    False,
                    (
                        "Appel système interdit : "
                        f"{node.func.attr}()"
                    ),
                )

        elif isinstance(
            node,
            ast.Import,
        ):

            for alias in node.names:

                racine = alias.name.split(
                    ".",
                    1,
                )[0]

                if racine in modules_interdits:

                    return (
                        code,
                        False,
                        f"Import interdit : {racine}",
                    )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):

            module = node.module or ""

            racine = module.split(
                ".",
                1,
            )[0]

            if racine in modules_interdits:

                return (
                    code,
                    False,
                    f"Import interdit : {racine}",
                )

    return (
        code,
        True,
        "Validation AST légère OK",
    )


# ============================================================
# SECTIONS PYTHON
# ============================================================

def detecter_sections_python(
    code: str,
) -> Dict[str, Tuple[int, int]]:

    sections: Dict[
        str,
        Tuple[int, int],
    ] = {}

    if not code:
        return sections

    try:

        tree = ast.parse(
            code
        )

    except SyntaxError:

        return sections

    for node in ast.walk(
        tree
    ):

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):

            sections[
                node.name
            ] = (
                node.lineno - 1,
                node.end_lineno
                or node.lineno,
            )

    return sections


# ============================================================
# PATCH CIBLE
# ============================================================

def appliquer_patch_cible(
    contenu_original: str,
    section: str,
    nouveau_code: str,
) -> str:

    sections = detecter_sections_python(
        contenu_original
    )

    if section not in sections:

        raise ValueError(
            f"Section inconnue : {section}"
        )

    start, end = sections[
        section
    ]

    lignes = contenu_original.splitlines()
    nouveau = nouveau_code.splitlines()

    resultat = (
        lignes[:start]
        + nouveau
        + lignes[end:]
    )

    return (
        "\n".join(
            resultat
        )
        + "\n"
    )


# ============================================================
# CRÉATION OUTIL
# ============================================================

def creer_outil(
    nom: str,
    description: str,
) -> str:

    if not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*",
        nom,
    ):

        raise ValueError(
            f"Nom d'outil invalide : {nom}"
        )

    prompt = f"""
Crée un outil Python pour JIBI.

Nom :
{nom}

Description :
{description}

Contraintes :
- Python 3.10+ ;
- robuste ;
- pas de eval ;
- pas de exec ;
- pas de __import__ ;
- pas de os.system ;
- pas de os.popen ;
- pas de subprocess ;
- ne lit aucun secret ;
- ne modifie automatiquement aucun fichier ;
- retourne uniquement le code Python.
"""

    brut = completer(
        prompt,
        profil="CODE",
        temperature=0.2,
    )

    code = extraire_code(
        brut
    )

    code, ok, raison = valider_code(
        code,
        f"outil:{nom}",
    )

    if not ok:

        raise ValueError(
            raison
        )

    return code


# ============================================================
# OBJET → DICT
# ============================================================

def _objet_vers_dict(
    objet: Any,
) -> Dict[str, Any]:

    if objet is None:
        return {}

    if isinstance(
        objet,
        dict,
    ):

        return objet

    to_dict = getattr(
        objet,
        "to_dict",
        None,
    )

    if callable(
        to_dict
    ):

        try:

            resultat = to_dict()

            if isinstance(
                resultat,
                dict,
            ):
                return resultat

        except Exception:

            pass

    data = getattr(
        objet,
        "__dict__",
        None,
    )

    if isinstance(
        data,
        dict,
    ):

        return dict(
            data
        )

    return {
        "valeur": str(
            objet
        )
    }


# ============================================================
# COMPACTION ANALYSE CODE
# ============================================================

def _compacter_analyse_code(
    analyse: Any,
) -> Dict[str, Any]:
    """
    Transforme l'analyse AST complète en petit contexte
    exploitable par le modèle.
    """

    data = _objet_vers_dict(
        analyse
    )

    fonctions = data.get(
        "fonctions",
        [],
    )

    classes = data.get(
        "classes",
        [],
    )

    imports = data.get(
        "imports",
        [],
    )

    erreurs = data.get(
        "erreurs",
        [],
    )

    fonctions_compactes = []

    if isinstance(
        fonctions,
        list,
    ):

        for fonction in fonctions:

            info = _objet_vers_dict(
                fonction
            )

            nom = str(
                info.get(
                    "nom",
                    "",
                )
            )

            debut = info.get(
                "ligne",
                info.get(
                    "lineno",
                    None,
                ),
            )

            fin = info.get(
                "ligne_fin",
                info.get(
                    "end_lineno",
                    None,
                ),
            )

            try:

                longueur = (
                    int(fin)
                    - int(debut)
                    + 1
                    if debut is not None
                    and fin is not None
                    else None
                )

            except (
                TypeError,
                ValueError,
            ):

                longueur = None

            fonctions_compactes.append(
                {
                    "nom": nom,
                    "ligne": debut,
                    "ligne_fin": fin,
                    "longueur": longueur,
                }
            )

    fonctions_compactes.sort(
        key=lambda x: (
            x["longueur"]
            if isinstance(
                x.get("longueur"),
                int,
            )
            else 0
        ),
        reverse=True,
    )

    classes_compactes = []

    if isinstance(
        classes,
        list,
    ):

        for classe in classes:

            info = _objet_vers_dict(
                classe
            )

            nom = str(
                info.get(
                    "nom",
                    "",
                )
            )

            debut = info.get(
                "ligne",
                info.get(
                    "lineno",
                    None,
                ),
            )

            fin = info.get(
                "ligne_fin",
                info.get(
                    "end_lineno",
                    None,
                ),
            )

            try:

                longueur = (
                    int(fin)
                    - int(debut)
                    + 1
                    if debut is not None
                    and fin is not None
                    else None
                )

            except (
                TypeError,
                ValueError,
            ):

                longueur = None

            methodes = info.get(
                "methodes",
                [],
            )

            if not isinstance(
                methodes,
                list,
            ):

                methodes = []

            classes_compactes.append(
                {
                    "nom": nom,
                    "ligne": debut,
                    "ligne_fin": fin,
                    "longueur": longueur,
                    "nb_methodes": len(
                        methodes
                    ),
                }
            )

    classes_compactes.sort(
        key=lambda x: (
            x["longueur"]
            if isinstance(
                x.get("longueur"),
                int,
            )
            else 0
        ),
        reverse=True,
    )

    if not isinstance(
        imports,
        list,
    ):

        imports = []

    if not isinstance(
        erreurs,
        list,
    ):

        erreurs = []

    try:

        lignes = int(
            data.get(
                "lignes",
                0,
            )
            or 0
        )

    except (
        TypeError,
        ValueError,
    ):

        lignes = 0

    return {
        "fichier": data.get(
            "fichier"
        ),
        "existe": bool(
            data.get(
                "existe",
                True,
            )
        ),
        "syntaxe_valide": bool(
            data.get(
                "syntaxe_valide",
                True,
            )
        ),
        "lignes": lignes,
        "nb_fonctions": len(
            fonctions_compactes
        ),
        "nb_classes": len(
            classes_compactes
        ),
        "nb_imports": len(
            imports
        ),
        "erreurs": [
            str(x)
            for x in erreurs[:10]
        ],
        "fonctions_longues": (
            fonctions_compactes[:15]
        ),
        "classes_grandes": (
            classes_compactes[:10]
        ),
        "imports": [
            str(x)
            for x in imports[:50]
        ],
    }


# ============================================================
# FALLBACK ANALYSE CODE
# ============================================================

def _fallback_analyse_code(
    donnees: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Résultat déterministe utilisé lorsque le LLM
    ne fournit pas un JSON exploitable.
    """

    ameliorations = []

    fonctions = donnees.get(
        "fonctions_longues",
        [],
    )

    classes = donnees.get(
        "classes_grandes",
        [],
    )

    erreurs = donnees.get(
        "erreurs",
        [],
    )

    for fonction in fonctions:

        longueur = fonction.get(
            "longueur"
        )

        if not isinstance(
            longueur,
            int,
        ):
            continue

        if longueur >= 100:

            ameliorations.append(
                {
                    "type": "refactoring",
                    "titre": (
                        "Fonction volumineuse : "
                        f"{fonction.get('nom', '?')}"
                    ),
                    "description": (
                        "Cette fonction couvre un volume "
                        "important de lignes et peut être "
                        "décomposée en responsabilités plus "
                        "petites."
                    ),
                    "element": str(
                        fonction.get(
                            "nom",
                            "",
                        )
                    ),
                    "ligne": fonction.get(
                        "ligne"
                    ),
                    "preuve": (
                        f"{longueur} lignes."
                    ),
                    "impact": "fort",
                    "risque": "faible",
                    "confiance": 0.95,
                }
            )

    for classe in classes:

        longueur = classe.get(
            "longueur"
        )

        if not isinstance(
            longueur,
            int,
        ):
            continue

        if longueur >= 300:

            ameliorations.append(
                {
                    "type": "architecture",
                    "titre": (
                        "Classe volumineuse : "
                        f"{classe.get('nom', '?')}"
                    ),
                    "description": (
                        "Cette classe concentre un volume "
                        "important de code et peut nécessiter "
                        "une séparation des responsabilités."
                    ),
                    "element": str(
                        classe.get(
                            "nom",
                            "",
                        )
                    ),
                    "ligne": classe.get(
                        "ligne"
                    ),
                    "preuve": (
                        f"{longueur} lignes et "
                        f"{classe.get('nb_methodes', 0)} méthodes."
                    ),
                    "impact": "fort",
                    "risque": "moyen",
                    "confiance": 0.95,
                }
            )

    if erreurs:

        ameliorations.append(
            {
                "type": "qualite",
                "titre": "Erreur détectée",
                "description": (
                    "L'analyseur statique a détecté "
                    "une erreur à examiner."
                ),
                "element": "",
                "ligne": None,
                "preuve": "; ".join(
                    erreurs[:3]
                ),
                "impact": "fort",
                "risque": "faible",
                "confiance": 1.0,
            }
        )

    ameliorations = ameliorations[:3]

    points = [
        f"Fichier : {donnees.get('fichier')}",
        f"Lignes : {donnees.get('lignes')}",
        f"Fonctions : {donnees.get('nb_fonctions')}",
        f"Classes : {donnees.get('nb_classes')}",
        f"Imports : {donnees.get('nb_imports')}",
    ]

    if donnees.get(
        "erreurs"
    ):

        points.append(
            f"Erreurs détectées : "
            f"{len(donnees['erreurs'])}"
        )

    return {
        "resume": (
            "Analyse déterministe construite à partir "
            "des données de l'analyseur statique."
        ),
        "points_importants": points,
        "ameliorations": ameliorations,
    }


# ============================================================
# ANALYSE CODE
# ============================================================

def analyser_code_resultat(
    analyse: Any,
    probleme: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyse un fichier à partir du résultat de l'analyseur_code.
    """

    donnees = _compacter_analyse_code(
        analyse
    )

    objectif = (
        str(
            probleme
        ).strip()
        if probleme
        else "Analyse structurelle générale."
    )

    prompt = f"""
FICHIER :
{donnees["fichier"]}

EXISTE :
{donnees["existe"]}

SYNTAXE VALIDE :
{donnees["syntaxe_valide"]}

NOMBRE DE LIGNES :
{donnees["lignes"]}

NOMBRE DE FONCTIONS :
{donnees["nb_fonctions"]}

NOMBRE DE CLASSES :
{donnees["nb_classes"]}

NOMBRE D'IMPORTS :
{donnees["nb_imports"]}

ERREURS :
{json.dumps(
    donnees["erreurs"],
    ensure_ascii=False,
)}

FONCTIONS LES PLUS LONGUES :
{json.dumps(
    donnees["fonctions_longues"],
    ensure_ascii=False,
)}

CLASSES LES PLUS GRANDES :
{json.dumps(
    donnees["classes_grandes"],
    ensure_ascii=False,
)}

IMPORTS :
{json.dumps(
    donnees["imports"],
    ensure_ascii=False,
)}

OBJECTIF :
{objectif}

Chaque amélioration doit être directement justifiée
par une donnée ci-dessus.

Retourne au maximum 3 améliorations.

Format :

{{
  "resume": "...",
  "points_importants": [],
  "ameliorations": [
    {{
      "type": "...",
      "titre": "...",
      "description": "...",
      "element": "...",
      "ligne": null,
      "preuve": "...",
      "impact": "faible|moyen|fort",
      "risque": "faible|moyen|fort",
      "confiance": 0.0
    }}
  ]
}}
"""

    resultat = completer_json(
        prompt,
        system=_system_analyse_code(),
        profil="ANALYSE_CODE",
        temperature=0.1,
    )

    if resultat.get(
        "_json_error"
    ):

        return _fallback_analyse_code(
            donnees
        )

    resume = str(
        resultat.get(
            "resume",
            "",
        )
    ).strip()

    points = resultat.get(
        "points_importants",
        [],
    )

    if not isinstance(
        points,
        list,
    ):

        points = []

    points = [
        str(x).strip()
        for x in points[:10]
        if str(x).strip()
    ]

    ameliorations = resultat.get(
        "ameliorations",
        [],
    )

    if not isinstance(
        ameliorations,
        list,
    ):

        ameliorations = []

    propres = []

    for item in ameliorations[:3]:

        if not isinstance(
            item,
            dict,
        ):

            continue

        titre = str(
            item.get(
                "titre",
                "",
            )
        ).strip()

        description = str(
            item.get(
                "description",
                "",
            )
        ).strip()

        preuve = str(
            item.get(
                "preuve",
                "",
            )
        ).strip()

        if not titre or not description:
            continue

        try:

            confiance = float(
                item.get(
                    "confiance",
                    0.0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            confiance = 0.0

        propres.append(
            {
                "type": str(
                    item.get(
                        "type",
                        "qualite",
                    )
                ),
                "titre": titre,
                "description": description,
                "element": str(
                    item.get(
                        "element",
                        "",
                    )
                ),
                "ligne": item.get(
                    "ligne"
                ),
                "preuve": preuve,
                "impact": str(
                    item.get(
                        "impact",
                        "moyen",
                    )
                ),
                "risque": str(
                    item.get(
                        "risque",
                        "faible",
                    )
                ),
                "confiance": max(
                    0.0,
                    min(
                        1.0,
                        confiance,
                    ),
                ),
            }
        )

    if not resume and not propres:

        return _fallback_analyse_code(
            donnees
        )

    return {
        "resume": resume,
        "points_importants": points,
        "ameliorations": propres,
    }


# ============================================================
# ANALYSE PROJET
# ============================================================

def _normaliser_analyse_projet(
    analyse: Any,
) -> Dict[str, Any]:

    data = _objet_vers_dict(
        analyse
    )

    modules = data.get(
        "modules",
        [],
    )

    if not isinstance(
        modules,
        list,
    ):

        modules = []

    internes = data.get(
        "dependances_internes",
        {},
    )

    externes = data.get(
        "dependances_externes",
        {},
    )

    erreurs = data.get(
        "erreurs",
        [],
    )

    if not isinstance(
        erreurs,
        list,
    ):

        erreurs = []

    return {
        "racine": data.get(
            "racine",
            data.get(
                "projet",
                None,
            ),
        ),
        "nb_fichiers": data.get(
            "nb_fichiers",
            0,
        ),
        "nb_fonctions": data.get(
            "nb_fonctions",
            0,
        ),
        "nb_classes": data.get(
            "nb_classes",
            0,
        ),
        "nb_imports": data.get(
            "nb_imports",
            0,
        ),
        "modules": [
            str(x)
            for x in modules[:80]
        ],
        "dependances_internes": (
            internes
            if isinstance(
                internes,
                dict,
            )
            else {}
        ),
        "dependances_externes": (
            externes
            if isinstance(
                externes,
                dict,
            )
            else {}
        ),
        "erreurs": [
            str(x)
            for x in erreurs[:20]
        ],
    }


def analyser_projet_resultat(
    analyse_projet: Any,
    problemes: Optional[Any] = None,
) -> Dict[str, Any]:

    donnees = _normaliser_analyse_projet(
        analyse_projet
    )

    problemes_data = (
        problemes
        if problemes is not None
        else []
    )

    prompt = f"""
CARTOGRAPHIE RÉELLE DU PROJET :

{json.dumps(
    donnees,
    ensure_ascii=False,
    indent=2,
    default=str,
)}

PROBLÈMES DÉJÀ DÉTECTÉS :

{json.dumps(
    problemes_data,
    ensure_ascii=False,
    indent=2,
    default=str,
)}

Retourne uniquement :

{{
  "resume": "...",
  "architecture": "...",
  "problemes_prioritaires": [],
  "ameliorations": []
}}
"""

    resultat = completer_json(
        prompt,
        system=_system_analyse_projet(),
        profil="ANALYSE_PROJET",
        temperature=0.1,
    )

    if resultat.get(
        "_json_error"
    ):

        return {
            "resume": (
                "Analyse projet : "
                f"{donnees.get('nb_fichiers', 0)} fichiers, "
                f"{donnees.get('nb_fonctions', 0)} fonctions, "
                f"{donnees.get('nb_classes', 0)} classes."
            ),
            "architecture": "Analyse en attente.",
            "problemes_prioritaires": [],
            "ameliorations": [],
        }

    resume = str(
        resultat.get(
            "resume",
            "",
        )
    ).strip()

    architecture = str(
        resultat.get(
            "architecture",
            "",
        )
    ).strip()

    prioritaires = resultat.get(
        "problemes_prioritaires",
        [],
    )

    if not isinstance(
        prioritaires,
        list,
    ):

        prioritaires = []

    prioritaires = [
        str(x).strip()
        for x in prioritaires[:10]
        if str(x).strip()
    ]

    ameliorations = resultat.get(
        "ameliorations",
        [],
    )

    if not isinstance(
        ameliorations,
        list,
    ):

        ameliorations = []

    propres = []

    for item in ameliorations[:3]:

        if not isinstance(
            item,
            dict,
        ):

            continue

        titre = str(
            item.get(
                "titre",
                "",
            )
        ).strip()

        description = str(
            item.get(
                "description",
                "",
            )
        ).strip()

        if not titre or not description:
            continue

        try:

            confiance = float(
                item.get(
                    "confiance",
                    0.0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            confiance = 0.0

        propres.append(
            {
                "type": str(
                    item.get(
                        "type",
                        "architecture",
                    )
                ),
                "titre": titre,
                "description": description,
                "preuve": str(
                    item.get(
                        "preuve",
                        "",
                    )
                ),
                "impact": str(
                    item.get(
                        "impact",
                        "moyen",
                    )
                ),
                "risque": str(
                    item.get(
                        "risque",
                        "faible",
                    )
                ),
                "confiance": max(
                    0.0,
                    min(
                        1.0,
                        confiance,
                    ),
                ),
            }
        )

    return {
        "resume": resume,
        "architecture": architecture,
        "problemes_prioritaires": prioritaires,
        "ameliorations": propres,
    }


# ============================================================
# ANALYSE PROBLÈMES RESULTAT
# ============================================================

def analyser_problemes_resultat(
    problemes,
    objectif: str = "",
    utiliser_llm: bool = True,
) -> Dict[str, Any]:
    """
    Analyse des problèmes regroupés pour identifier
    les améliorations prioritaires.
    
    Version optimisée v12.4 :
    - Fallback déterministe TOUJOURS calculé
    - LLM = enrichissement optionnel
    - Résultat garanti même si LLM échoue
    
    Args:
        problemes: Liste de problèmes détectés
        objectif: Objectif de l'amélioration
        utiliser_llm: Si True, tente l'enrichissement LLM
        
    Returns:
        Dict avec résultat (fallback ou enrichi par LLM)
    """

    # --------------------------------------------------------
    # NORMALISATION
    # --------------------------------------------------------

    if not isinstance(problemes, list):
        problemes = []

    if not problemes:
        return {
            "problemes_racines": [],
            "ameliorations": [],
            "resume": "Aucun problème détecté.",
            "_fallback": True,
            "_llm_utilise": False,
        }

    # --------------------------------------------------------
    # REGROUPEMENT DÉTERMINISTE
    # --------------------------------------------------------

    if regrouper_problemes is not None:
        groupes = regrouper_problemes(
            problemes,
            max_groupes=5,
        )
    else:
        groupes = problemes[:5]

    # --------------------------------------------------------
    # FALLBACK DÉTERMINISTE (TOUJOURS CALCULÉ)
    # --------------------------------------------------------

    resultat_fallback = _fallback_analyse_problemes(groupes)
    
    # Ajouter l'indicateur LLM
    resultat_fallback["_llm_utilise"] = False

    # --------------------------------------------------------
    # ENRICHISSEMENT LLM (OPTIONNEL)
    # --------------------------------------------------------

    if not utiliser_llm:
        return resultat_fallback

    # Construction contexte minimal
    donnees = []

    for groupe in groupes:
        if isinstance(groupe, dict):
            donnees.append({
                "type": groupe.get("type"),
                "gravite": groupe.get("gravite"),
                "titre": str(groupe.get("titre", ""))[:160],
                "description": str(groupe.get("description", ""))[:160],
                "ids": groupe.get("ids", [])[:20],
                "fichiers": groupe.get("fichiers", [])[:10],
                "preuve": str(groupe.get("preuve", ""))[:200],
                "nombre": groupe.get("nombre", 0),
                "confiance": groupe.get("confiance", 0.0),
                "niveau_confiance": groupe.get("niveau_confiance", "HEURISTIQUE"),
            })

    prompt = f"""Objectif :
{objectif[:200]}

Causes détectées :
{json.dumps(donnees, ensure_ascii=False, indent=2)}

À partir uniquement de ces causes :

1. résume les causes principales ;
2. propose au maximum 3 améliorations ;
3. chaque amélioration doit utiliser une preuve présente dans les données.

JSON uniquement :

{{
  "resume": "...",
  "problemes_racines": [],
  "ameliorations": []
}}"""

    # Tentative LLM
    try:
        resultat_llm = completer_json(
            prompt,
            system=_system_analyse_problemes(),
            profil="ANALYSE_PROBLEMES",
            temperature=0.0,
        )

        # Vérifier si le LLM a échoué
        if resultat_llm.get("_json_error"):
            return resultat_fallback

        # Valider le résultat LLM
        resume = str(resultat_llm.get("resume", "")).strip()
        
        # Si le résumé contient "déterministe", c'est que le LLM a renvoyé le fallback
        if not resume or "déterministe" in resume.lower():
            return resultat_fallback

        # Extraire et valider les données
        problemes_racines = resultat_llm.get("problemes_racines", [])
        if not isinstance(problemes_racines, list):
            problemes_racines = []

        problemes_racines = [
            str(x).strip()
            for x in problemes_racines[:5]
            if str(x).strip()
        ]

        ameliorations = resultat_llm.get("ameliorations", [])
        if not isinstance(ameliorations, list):
            ameliorations = []

        propres = []

        for item in ameliorations[:3]:
            if not isinstance(item, dict):
                continue

            titre = str(item.get("titre", "")).strip()
            description = str(item.get("description", "")).strip()

            if not titre or not description:
                continue

            preuve = str(item.get("preuve", "")).strip()

            try:
                confiance = float(item.get("confiance", 0.0))
            except (TypeError, ValueError):
                confiance = 0.0

            propres.append({
                "type": str(item.get("type", "qualite")),
                "titre": titre[:160],
                "description": description[:300],
                "preuve": preuve[:200],
                "ids": item.get("ids", [])[:20],
                "fichiers": item.get("fichiers", [])[:10],
                "impact": str(item.get("impact", "moyen")),
                "risque": str(item.get("risque", "faible")),
                "confiance": max(0.0, min(1.0, confiance)),
            })

        # Si aucune amélioration valide, utiliser le fallback
        if not propres:
            return resultat_fallback

        # LLM a réussi
        return {
            "resume": resume,
            "problemes_racines": problemes_racines,
            "ameliorations": propres,
            "_fallback": False,
            "_llm_utilise": True,
        }

    except Exception as exc:
        # Toute erreur → retourner fallback
        return resultat_fallback


# ============================================================
# FALLBACK ANALYSE PROBLEMES
# ============================================================

def _fallback_analyse_problemes(
    groupes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Résultat déterministe lorsque le LLM échoue.
    
    Utilise uniquement les groupes fournis.
    """

    if not groupes:
        return {
            "resume": "Aucun problème détecté.",
            "problemes_racines": [],
            "ameliorations": [],
            "_fallback": True,
        }

    # Tri par gravité et nombre
    gravites_ordre = {
        "critique": 0,
        "important": 1,
        "qualite": 2,
        "refactoring": 3,
    }

    groupes_tries = sorted(
        groupes,
        key=lambda x: (
            gravites_ordre.get(
                str(
                    x.get(
                        "gravite",
                        "",
                    )
                ).lower(),
                9,
            ),
            -x.get(
                "nombre",
                0,
            ),
        ),
    )

    problemes_racines = []
    ameliorations = []

    for groupe in groupes_tries[:5]:

        type_pb = str(
            groupe.get(
                "type",
                "inconnu",
            )
        )

        nombre = groupe.get(
            "nombre",
            0,
        )

        gravite = str(
            groupe.get(
                "gravite",
                "qualite",
            )
        )

        problemes_racines.append(
            f"{nombre} problème(s) de type '{type_pb}' "
            f"(gravité: {gravite})"
        )

    for groupe in groupes_tries[:3]:

        titre = str(
            groupe.get(
                "titre",
                groupe.get(
                    "type",
                    "Problème détecté",
                ),
            )
        )[:160]

        description = str(
            groupe.get(
                "description",
                "",
            )
        )[:300]

        preuve = str(
            groupe.get(
                "preuve",
                "",
            )
        )[:200]

        ameliorations.append(
            {
                "type": str(
                    groupe.get(
                        "type",
                        "qualite",
                    )
                ),
                "titre": titre,
                "description": (
                    description
                    or f"Corriger les problèmes de type {groupe.get('type')}"
                ),
                "preuve": preuve,
                "ids": groupe.get(
                    "ids",
                    [],
                )[:20],
                "fichiers": groupe.get(
                    "fichiers",
                    [],
                )[:10],
                "impact": "moyen",
                "risque": "faible",
                "confiance": float(
                    groupe.get(
                        "confiance",
                        0.8,
                    )
                ),
            }
        )

    return {
        "resume": (
            f"Analyse déterministe : {len(groupes)} groupe(s) "
            f"de problèmes détecté(s)."
        ),
        "problemes_racines": problemes_racines,
        "ameliorations": ameliorations,
        "_fallback": True,
    }


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    "disponible",
    "completer",
    "completer_json",
    "planifier",
    "extraire_code",
    "valider_code",
    "creer_outil",
    "analyser_code_resultat",
    "analyser_projet_resultat",
    "analyser_problemes_resultat",
    "detecter_sections_python",
    "appliquer_patch_cible",
]