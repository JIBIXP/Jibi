"""
TOOL ROUTING JIBI — v5

Sélection intelligente des outils.

Objectifs :

1. ne pas envoyer tous les outils au LLM ;
2. réduire le contexte ;
3. identifier les outils pertinents ;
4. détecter l'auto-amélioration ;
5. détecter les demandes documentaires ;
6. rester compatible avec le registre actuel.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


# ============================================================
# NORMALISATION
# ============================================================

def normaliser(
    texte: str,
) -> str:

    texte = (
        texte or ""
    ).lower()

    texte = (
        texte
        .replace("’", "'")
        .replace("œ", "oe")
    )

    texte = re.sub(
        r"\s+",
        " ",
        texte,
    )

    return texte.strip()


# ============================================================
# MOTS OUTILS
# ============================================================

MOTS_OUTILS = {

    # mémoire

    "souviens-toi",
    "souviens toi",
    "rappelle-toi",
    "rappelle toi",
    "mémorise",
    "memorise",
    "n'oublie pas",
    "n oublie pas",
    "ma mémoire",
    "ma memoire",
    "mon prénom",
    "mon prenom",
    "mon nom",

    # navigateur

    "ouvre le site",
    "ouvre la page",
    "va sur",
    "vas sur",
    "navigue vers",
    "clique sur",

    # fichiers

    "crée un fichier",
    "cree un fichier",
    "créer un fichier",
    "creer un fichier",
    "lis le fichier",
    "lire le fichier",
    "liste les fichiers",
    "supprime le fichier",
    "renomme le fichier",

    # documents

    "crée un document",
    "cree un document",
    "créer un document",
    "creer un document",
    "crée un rapport",
    "cree un rapport",
    "créer un rapport",
    "creer un rapport",
    "fais un rapport",
    "faire un rapport",
    "document word",
    "document pdf",
    "rapport word",
    "rapport pdf",
    "cv",
    "lettre",

    # système

    "ouvre l'application",
    "ouvre l application",
    "lance l'application",
    "lance l application",
    "ferme l'application",
    "ouvre vscode",
    "ouvre le terminal",

    # terminal

    "exécute la commande",
    "execute la commande",
    "lance la commande",
    "dans le terminal",

    # vision

    "capture l'écran",
    "capture l ecran",
    "capture d'écran",
    "capture d ecran",
    "analyse cette image",
    "analyse l'image",
    "regarde mon écran",
    "regarde mon ecran",

    # auto amélioration

    "ton code",
    "ta source",
    "ton fichier",
    "tes fichiers",
    "code source",
    "lis ton code",
    "regarde ton code",
    "montre ton code",
    "inspecte ton code",
    "analyse ton code",
    "analyse tes logs",
    "santé jibi",
    "sante jibi",
    "score de santé",
    "score de sante",
    "tableau de bord",
    "tes erreurs",
    "détecte les erreurs",
    "detecte les erreurs",
    "répare ton code",
    "repare ton code",
    "corrige ton code",
    "améliore-toi",
    "ameliore-toi",
    "améliore toi",
    "ameliore toi",
    "propose une amélioration",
    "propose une amelioration",

    # updater

    "mise à jour",
    "mise a jour",
    "mettre à jour",
    "mettre a jour",
    "update",
    "rollback",
    "restaurer",
}


# ============================================================
# ACTIONS
# ============================================================

MOTS_ACTION_SYSTEME = {

    "ouvre",
    "ouvrir",
    "ouvres",
    "ouvrez",

    "ferme",
    "fermer",
    "fermes",
    "fermez",

    "lance",
    "lancer",
    "lances",
    "lancez",

    "clique",
    "cliquer",
    "cliques",
    "cliquez",

    "capture",
    "capturer",

    "analyse",
    "analyser",

    "supprime",
    "supprimer",

    "exécute",
    "exécuter",
    "execute",
    "executer",

    "navigue",
    "naviguer",

    "propose",
    "proposer",

    "améliore",
    "ameliorer",

    "corrige",
    "corriger",

    "répare",
    "repare",

    "crée",
    "cree",

    "génère",
    "genere",
}


# ============================================================
# CATÉGORIES
# ============================================================

CATEGORIES_OUTILS = [

    (
        (
            "ouvre le site",
            "ouvre la page",
            "va sur",
            "vas sur",
            "navigue vers",
            "sur google",
            "sur youtube",
            "sur internet",
            "clique sur",
        ),
        [
            "ouvrir_url",
            "obtenir_texte_page",
            "cliquer",
            "remplir_champ",
            "fermer_navigateur",
        ],
    ),

    (
        (
            "lis le fichier",
            "lire le fichier",
            "liste les fichiers",
            "crée un fichier",
            "cree un fichier",
            "supprime le fichier",
            "renomme le fichier",
        ),
        [
            "creer_fichier",
            "lire_fichier",
            "lister_fichiers",
            "supprimer_fichier",
            "renommer_fichier",
        ],
    ),

    (
        (
            "crée un document",
            "cree un document",
            "crée un rapport",
            "cree un rapport",
            "fais un rapport",
            "document word",
            "document pdf",
            "rapport word",
            "rapport pdf",
            "cv",
            "lettre",
        ),
        [
            "creer_document_word",
            "creer_document_pdf",
        ],
    ),

    (
        (
            "ton code",
            "ta source",
            "ton fichier",
            "tes fichiers",
            "code source",
            "analyse ton code",
            "analyse tes logs",
            "santé jibi",
            "sante jibi",
            "tableau de bord",
            "tes erreurs",
            "répare ton code",
            "repare ton code",
            "corrige ton code",
            "améliore-toi",
            "ameliore-toi",
            "propose une amélioration",
            "propose une amelioration",
        ),
        [
            "lire_code_source",
            "lister_code_source",
            "analyser_sante_jibi",
            "tableau_bord_amelioration",
            "preparer_amelioration",
        ],
    ),

    (
        (
            "ouvre l'application",
            "lance l'application",
            "ferme l'application",
            "ouvre vscode",
            "ouvre le terminal",
        ),
        [
            "ouvrir_application",
            "fermer_application",
        ],
    ),

    (
        (
            "exécute la commande",
            "execute la commande",
            "lance la commande",
            "dans le terminal",
        ),
        [
            "executer_commande",
        ],
    ),

    (
        (
            "capture l'écran",
            "capture l ecran",
            "analyse cette image",
            "analyse l'image",
            "regarde mon écran",
            "regarde mon ecran",
        ),
        [
            "analyser_image",
            "capturer_ecran",
            "capturer_et_analyser",
        ],
    ),

    (
        (
            "souviens-toi",
            "souviens toi",
            "rappelle-toi",
            "rappelle toi",
            "mémorise",
            "memorise",
            "ma mémoire",
            "ma memoire",
            "mon prénom",
            "mon prenom",
            "mon nom",
        ),
        [
            "remember",
            "recall",
        ],
    ),

    (
        (
            "mise à jour",
            "mise a jour",
            "mettre à jour",
            "mettre a jour",
            "update",
            "rollback",
            "restaurer",
        ),
        [
            "verifier_mise_a_jour",
            "appliquer_mise_a_jour",
            "restaurer_derniere_sauvegarde",
            "lister_sauvegardes",
            "obtenir_etat_global_jibi",
        ],
    ),
]


# ============================================================
# BESOIN OUTILS
# ============================================================

def besoin_outils(
    message: str,
) -> bool:

    texte = normaliser(
        message
    )

    if not texte:
        return False

    return (
        any(
            mot in texte
            for mot in MOTS_OUTILS
        )
        or any(
            mot in texte
            for mot in MOTS_ACTION_SYSTEME
        )
    )


# ============================================================
# AUTO AMÉLIORATION
# ============================================================

def besoin_auto_amelioration(
    message: str,
) -> bool:

    texte = normaliser(
        message
    )

    mots = (
        "ton code",
        "ta source",
        "analyse ton code",
        "analyse tes logs",
        "tes erreurs",
        "répare ton code",
        "repare ton code",
        "corrige ton code",
        "améliore-toi",
        "ameliore-toi",
        "propose une amélioration",
        "propose une amelioration",
        "santé jibi",
        "sante jibi",
        "tableau de bord",
        "score de santé",
        "score de sante",
    )

    return any(
        mot in texte
        for mot in mots
    )


# ============================================================
# DOCUMENTS
# ============================================================

def besoin_documents(
    message: str,
) -> bool:

    texte = normaliser(
        message
    )

    mots = (
        "crée un document",
        "cree un document",
        "crée un rapport",
        "cree un rapport",
        "fais un rapport",
        "document word",
        "document pdf",
        "rapport word",
        "rapport pdf",
        "cv",
        "lettre",
    )

    return any(
        mot in texte
        for mot in mots
    )


# ============================================================
# SELECTION
# ============================================================

def outils_pour_message(
    message: str,
    tools: Any,
) -> List[Any]:

    texte = normaliser(
        message
    )

    if not tools:
        return []

    noms_retenus = set()

    for mots, noms in CATEGORIES_OUTILS:

        if any(
            mot in texte
            for mot in mots
        ):

            noms_retenus.update(
                noms
            )

    # Aucun signal :
    # laisser le LLM décider.

    if not noms_retenus:

        return list(tools)

    resultat = []

    for outil in tools:

        try:

            nom = (
                outil
                .get("function", {})
                .get("name")
            )

        except AttributeError:

            continue

        if nom in noms_retenus:

            resultat.append(
                outil
            )

    # Ne jamais bloquer JIBI
    # si le registre ne contient pas
    # exactement les noms attendus.

    if not resultat:

        return list(tools)

    return resultat


# ============================================================
# STATISTIQUES
# ============================================================

def statistiques_routage(
    message: str,
    tools: Iterable[Any],
) -> Dict[str, Any]:

    tools = list(
        tools or []
    )

    texte = normaliser(
        message
    )

    mots_trouves = [
        mot
        for mot in MOTS_OUTILS
        if mot in texte
    ]

    actions_trouvees = [
        mot
        for mot in MOTS_ACTION_SYSTEME
        if mot in texte
    ]

    categories = []

    for mots, noms in CATEGORIES_OUTILS:

        matches = [
            mot
            for mot in mots
            if mot in texte
        ]

        if matches:

            categories.append(
                {
                    "outils": noms,
                    "mots_cles_matches":
                        matches,
                }
            )

    selection = outils_pour_message(
        message,
        tools,
    )

    total = len(tools)

    selection_count = len(
        selection
    )

    reduction = (
        round(
            (
                1
                - selection_count / total
            )
            * 100,
            1,
        )
        if total
        else 0
    )

    return {
        "message_length":
            len(message or ""),

        "mots_declencheurs_trouves":
            mots_trouves,

        "actions_trouvees":
            actions_trouvees,

        "nb_categories_matchees":
            len(categories),

        "categories_matchees":
            categories,

        "nb_outils_total":
            total,

        "nb_outils_selectionnes":
            selection_count,

        "reduction_pourcent":
            reduction,

        "besoin_outils":
            besoin_outils(message),

        "besoin_auto_amelioration":
            besoin_auto_amelioration(message),

        "besoin_documents":
            besoin_documents(message),
    }


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    "normaliser",
    "besoin_outils",
    "outils_pour_message",
    "besoin_auto_amelioration",
    "besoin_documents",
    "statistiques_routage",
    "MOTS_OUTILS",
    "MOTS_ACTION_SYSTEME",
    "CATEGORIES_OUTILS",
]


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == "__main__":

    outils = [
        {
            "function": {
                "name": "ouvrir_url"
            }
        },
        {
            "function": {
                "name": "creer_document_word"
            }
        },
        {
            "function": {
                "name": "lire_code_source"
            }
        },
        {
            "function": {
                "name": "analyser_sante_jibi"
            }
        },
        {
            "function": {
                "name": "executer_commande"
            }
        },
    ]

    exemples = [
        "ouvre google",
        "crée un rapport Word",
        "analyse ton code",
        "répare ton code",
        "capture mon écran",
        "souviens-toi de mon prénom",
        "exécute la commande",
    ]

    print("=" * 70)
    print("JIBI TOOL ROUTING v5")
    print("=" * 70)

    for message in exemples:

        stats = statistiques_routage(
            message,
            outils,
        )

        print()
        print(
            f"Message : {message}"
        )

        print(
            "Outils :",
            stats[
                "nb_outils_selectionnes"
            ],
            "/",
            stats[
                "nb_outils_total"
            ],
        )

        print(
            "Auto-amélioration :",
            stats[
                "besoin_auto_amelioration"
            ],
        )

        print(
            "Documents :",
            stats[
                "besoin_documents"
            ],
        )