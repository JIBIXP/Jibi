"""
Routage des outils de JIBI.

Détermine quels outils doivent être proposés à Ollama
en fonction de la demande utilisateur.

Objectif :
- réduire le nombre d'outils proposés au petit modèle ;
- rendre la sélection plus fiable ;
- garantir que les outils documentaires sont proposés
  lorsqu'une demande de document est détectée ;
- intégrer l'auto-amélioration dans le routage.
"""


# ============================================================
# MOTS DÉCLENCHEURS DES OUTILS
# ============================================================

MOTS_OUTILS = {
    # --------------------------------------------------------
    # Mémoire
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # Navigateur
    # --------------------------------------------------------
    "ouvre le site",
    "ouvre la page",
    "va sur",
    "vas sur",
    "navigue vers",
    "clique sur",
    "remplis le champ",

    # --------------------------------------------------------
    # Fichiers
    # --------------------------------------------------------
    "crée un fichier",
    "cree un fichier",
    "créer un fichier",
    "creer un fichier",
    "lis le fichier",
    "lire le fichier",
    "liste les fichiers",
    "supprime le fichier",

    # --------------------------------------------------------
    # DOCUMENTS
    # --------------------------------------------------------
    "crée un document",
    "cree un document",
    "créer un document",
    "creer un document",

    "crée-moi un document",
    "cree-moi un document",
    "créer-moi un document",
    "creer-moi un document",

    "crée un rapport",
    "cree un rapport",
    "créer un rapport",
    "creer un rapport",

    "crée-moi un rapport",
    "cree-moi un rapport",
    "créer-moi un rapport",
    "creer-moi un rapport",

    "fais un rapport",
    "fait un rapport",
    "faire un rapport",

    "génère un document",
    "genere un document",
    "générer un document",
    "generer un document",

    "génère un rapport",
    "genere un rapport",
    "générer un rapport",
    "generer un rapport",

    "document word",
    "document pdf",
    "fichier word",
    "fichier pdf",

    "word",
    "pdf",

    "rapport word",
    "rapport pdf",

    "crée un cv",
    "cree un cv",
    "créer un cv",
    "creer un cv",

    "crée une lettre",
    "cree une lettre",
    "créer une lettre",
    "creer une lettre",

    "crée une présentation",
    "cree une presentation",

    # --------------------------------------------------------
    # PC
    # --------------------------------------------------------
    "ouvre l'application",
    "ouvre l application",
    "lance l'application",
    "lance l application",
    "ferme l'application",
    "ferme l application",

    # --------------------------------------------------------
    # Terminal
    # --------------------------------------------------------
    "exécute la commande",
    "execute la commande",
    "lance la commande",
    "dans le terminal",

    # --------------------------------------------------------
    # Vision
    # --------------------------------------------------------
    "capture l'écran",
    "capture l ecran",
    "capture d'écran",
    "capture d ecran",
    "analyse cette image",
    "analyse l'image",
    "que vois-tu à l'écran",
    "que vois tu a l'ecran",

    # --------------------------------------------------------
    # AUTO-AMÉLIORATION
    # --------------------------------------------------------
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
    "propose une amélioration",
    "propose une amelioration",
    "améliore-toi",
    "ameliore-toi",
    "améliore toi",
    "ameliore toi",
    "santé jibi",
    "sante jibi",
    "tableau de bord",
    "score de santé",
    "score de sante",
    "tes erreurs",
    "détecte les erreurs",
    "detecte les erreurs",
}


# ============================================================
# VERBES D'ACTION
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
    "captures",
    "capturez",

    "analyse",
    "analyser",
    "analyses",
    "analysez",

    "supprime",
    "supprimer",
    "supprimes",
    "supprimez",

    "exécute",
    "exécuter",
    "exécutes",
    "exécutez",

    "execute",
    "executer",
    "executes",
    "executez",

    "va sur",
    "vas sur",
    "aller sur",

    "navigue",
    "naviguer",
    "navigues",

    "propose",
    "proposer",

    "améliore",
    "ameliore",
    "améliorer",
    "ameliorer",

    "détecte",
    "detecte",
    "détecter",
    "detecter",

    # Documents
    "crée",
    "cree",
    "créer",
    "creer",
    "génère",
    "genere",
    "générer",
    "generer",
}


# ============================================================
# CATÉGORIES D'OUTILS
# ============================================================

CATEGORIES_OUTILS = [

    # --------------------------------------------------------
    # NAVIGATEUR
    # --------------------------------------------------------
    (
        (
            "va sur",
            "vas sur",
            "rentre sur",
            "ouvre le site",
            "ouvre la page",
            "navigue vers",
            "sur google",
            "sur youtube",
            "sur internet",
            "ouvre google",
            "ouvre youtube",
            "clique sur",
            "remplis le champ",
            "ferme le navigateur",
        ),
        [
            "ouvrir_url",
            "obtenir_texte_page",
            "cliquer",
            "remplir_champ",
            "fermer_navigateur",
        ],
    ),

    # --------------------------------------------------------
    # FICHIERS
    # --------------------------------------------------------
    (
        (
            "lis le fichier",
            "lire le fichier",
            "liste les fichiers",
            "crée un fichier",
            "cree un fichier",
            "créer un fichier",
            "creer un fichier",
            "supprime le fichier",
        ),
        [
            "creer_fichier",
            "lire_fichier",
            "lister_fichiers",
            "supprimer_fichier",
        ],
    ),

    # --------------------------------------------------------
    # DOCUMENTS
    # --------------------------------------------------------
    (
        (
            "crée un document",
            "cree un document",
            "créer un document",
            "creer un document",

            "crée-moi un document",
            "cree-moi un document",

            "crée un rapport",
            "cree un rapport",
            "créer un rapport",
            "creer un rapport",

            "crée-moi un rapport",
            "cree-moi un rapport",

            "fais un rapport",
            "faire un rapport",

            "génère un document",
            "genere un document",
            "générer un document",
            "generer un document",

            "génère un rapport",
            "genere un rapport",

            "document word",
            "document pdf",
            "fichier word",
            "fichier pdf",

            "rapport word",
            "rapport pdf",

            "crée un cv",
            "cree un cv",

            "crée une lettre",
            "cree une lettre",
        ),
        [
            "creer_document_word",
            "creer_document_pdf",
        ],
    ),

    # --------------------------------------------------------
    # CODE SOURCE + AUTO-AMÉLIORATION
    # --------------------------------------------------------
    (
        (
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
            "propose une amélioration",
            "propose une amelioration",
            "améliore-toi",
            "ameliore-toi",
            "améliore toi",
            "ameliore toi",
            "santé jibi",
            "sante jibi",
            "score de santé",
            "score de sante",
            "tableau de bord",
            "tes erreurs",
            "détecte les erreurs",
            "detecte les erreurs",
            "patterns récurrents",
            "patterns recurrents",
        ),
        [
            "lire_code_source",
            "lister_code_source",
            "proposer_amelioration",
            # Outils auto-amélioration (si disponibles via tools/)
            "analyser_sante_jibi",
            "tableau_bord_amelioration",
            "preparer_amelioration",
        ],
    ),

    # --------------------------------------------------------
    # APPLICATIONS
    # --------------------------------------------------------
    (
        (
            "ouvre l'application",
            "ouvre l application",
            "lance l'application",
            "lance l application",
            "ferme l'application",
            "ferme l application",
            "ouvre vscode",
            "ouvre vs code",
            "ouvre le terminal",
            "ouvre l'explorateur",
        ),
        [
            "ouvrir_application",
            "fermer_application",
        ],
    ),

    # --------------------------------------------------------
    # TERMINAL
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # VISION
    # --------------------------------------------------------
    (
        (
            "capture l'écran",
            "capture l ecran",
            "capture d'écran",
            "capture d ecran",
            "analyse cette image",
            "analyse l'image",
            "que vois-tu à l'écran",
            "que vois tu a l'ecran",
            "regarde mon écran",
            "regarde mon ecran",
        ),
        [
            "analyser_image",
            "capturer_ecran",
            "capturer_et_analyser",
        ],
    ),

    # --------------------------------------------------------
    # MÉMOIRE
    # --------------------------------------------------------
    (
        (
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
        ),
        [
            "remember",
            "recall",
        ],
    ),

    # --------------------------------------------------------
    # UPDATER (si disponible)
    # --------------------------------------------------------
    (
        (
            "mise à jour",
            "mise a jour",
            "mettre à jour",
            "mettre a jour",
            "update",
            "vérifier les mises à jour",
            "verifier les mises a jour",
            "dernière version",
            "derniere version",
            "restaurer",
            "rollback",
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
# DÉTECTION BESOIN OUTILS
# ============================================================

def besoin_outils(message):
    """
    Détermine si le message nécessite un outil.
    
    Args:
        message: Message utilisateur
        
    Returns:
        bool: True si des outils sont nécessaires
    """

    texte = " ".join(
        message.lower().strip().split()
    )

    return (
        any(
            mot in texte
            for mot in MOTS_OUTILS
        )
        or
        any(
            mot in texte
            for mot in MOTS_ACTION_SYSTEME
        )
    )


# ============================================================
# SÉLECTION DES OUTILS PERTINENTS
# ============================================================

def outils_pour_message(message, tools):
    """
    Retourne uniquement les outils pertinents
    pour la demande utilisateur.

    Si aucune catégorie précise n'est trouvée,
    tous les outils restent disponibles.
    
    Args:
        message: Message utilisateur
        tools: Liste complète des outils disponibles
        
    Returns:
        list: Outils filtrés ou tous les outils si aucun filtre
    """

    texte = " ".join(
        message.lower().strip().split()
    )

    noms_retenus = set()

    for mots_cles, noms_outils in CATEGORIES_OUTILS:

        if any(
            mot in texte
            for mot in mots_cles
        ):
            noms_retenus.update(
                noms_outils
            )

    # Si aucune catégorie n'est détectée, retourner tous les outils
    if not noms_retenus:
        return tools

    # Filtrer les outils en fonction des noms retenus
    outils_filtres = [
        outil
        for outil in tools
        if outil["function"]["name"] in noms_retenus
    ]

    # Si le filtrage a éliminé tous les outils (ex: nom d'outil incorrect),
    # retourner tous les outils pour éviter un blocage
    if not outils_filtres:
        return tools

    return outils_filtres


# ============================================================
# DÉTECTION SPÉCIFIQUE AUTO-AMÉLIORATION
# ============================================================

def besoin_auto_amelioration(message):
    """
    Détecte si le message concerne l'auto-amélioration.
    
    Args:
        message: Message utilisateur
        
    Returns:
        bool: True si auto-amélioration détectée
    """
    
    MOTS_AUTO_AMELIORATION = {
        "ton code",
        "analyse ton code",
        "analyse tes logs",
        "santé jibi",
        "sante jibi",
        "score de santé",
        "score de sante",
        "tableau de bord",
        "améliore-toi",
        "ameliore-toi",
        "améliore toi",
        "ameliore toi",
        "propose une amélioration",
        "propose une amelioration",
        "tes erreurs",
        "détecte les erreurs",
        "detecte les erreurs",
        "patterns récurrents",
        "patterns recurrents",
    }
    
    texte = " ".join(
        message.lower().strip().split()
    )
    
    return any(
        mot in texte
        for mot in MOTS_AUTO_AMELIORATION
    )


# ============================================================
# DÉTECTION SPÉCIFIQUE DOCUMENTS
# ============================================================

def besoin_documents(message):
    """
    Détecte si le message concerne la création de documents.
    
    Args:
        message: Message utilisateur
        
    Returns:
        bool: True si création de document détectée
    """
    
    MOTS_DOCUMENTS = {
        "crée un document",
        "cree un document",
        "crée un rapport",
        "cree un rapport",
        "fais un rapport",
        "génère un document",
        "genere un document",
        "document word",
        "document pdf",
        "fichier word",
        "fichier pdf",
        "rapport word",
        "rapport pdf",
        "crée un cv",
        "cree un cv",
        "crée une lettre",
        "cree une lettre",
    }
    
    texte = " ".join(
        message.lower().strip().split()
    )
    
    return any(
        mot in texte
        for mot in MOTS_DOCUMENTS
    )


# ============================================================
# STATISTIQUES DE ROUTAGE
# ============================================================

def statistiques_routage(message, tools):
    """
    Retourne des statistiques sur le routage des outils.
    Utile pour le debugging et l'optimisation.
    
    Args:
        message: Message utilisateur
        tools: Liste complète des outils
        
    Returns:
        dict: Statistiques de routage
    """
    
    texte = " ".join(
        message.lower().strip().split()
    )
    
    # Compter les mots déclencheurs trouvés
    mots_trouves = [
        mot for mot in MOTS_OUTILS
        if mot in texte
    ]
    
    actions_trouvees = [
        mot for mot in MOTS_ACTION_SYSTEME
        if mot in texte
    ]
    
    # Catégories matchées
    categories_matchees = []
    for mots_cles, noms_outils in CATEGORIES_OUTILS:
        if any(mot in texte for mot in mots_cles):
            categories_matchees.append({
                'outils': noms_outils,
                'mots_cles_matches': [
                    mot for mot in mots_cles if mot in texte
                ]
            })
    
    # Outils sélectionnés
    outils_selectionnes = outils_pour_message(message, tools)
    
    return {
        'message_length': len(message),
        'mots_declencheurs_trouves': mots_trouves,
        'actions_trouvees': actions_trouvees,
        'nb_categories_matchees': len(categories_matchees),
        'categories_matchees': categories_matchees,
        'nb_outils_total': len(tools),
        'nb_outils_selectionnes': len(outils_selectionnes),
        'reduction_pourcent': round(
            (1 - len(outils_selectionnes) / len(tools)) * 100, 1
        ) if tools else 0,
        'besoin_auto_amelioration': besoin_auto_amelioration(message),
        'besoin_documents': besoin_documents(message),
    }


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    'besoin_outils',
    'outils_pour_message',
    'besoin_auto_amelioration',
    'besoin_documents',
    'statistiques_routage',
    'MOTS_OUTILS',
    'MOTS_ACTION_SYSTEME',
    'CATEGORIES_OUTILS',
]


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    print("="*60)
    print("ROUTAGE DES OUTILS JIBI")
    print("="*60)
    
    # Exemples de messages
    exemples = [
        "ouvre google",
        "crée un rapport word sur Python",
        "analyse ton code",
        "capture l'écran",
        "souviens-toi de mon prénom",
        "tableau de bord amélioration",
        "exécute la commande ls",
    ]
    
    # Simulation d'outils
    tools_simules = [
        {"function": {"name": "ouvrir_url"}},
        {"function": {"name": "creer_document_word"}},
        {"function": {"name": "lire_code_source"}},
        {"function": {"name": "capturer_ecran"}},
        {"function": {"name": "remember"}},
        {"function": {"name": "analyser_sante_jibi"}},
        {"function": {"name": "executer_commande"}},
    ]
    
    print("\n📊 Tests de routage :\n")
    
    for message in exemples:
        stats = statistiques_routage(message, tools_simules)
        print(f"Message : '{message}'")
        print(f"  Outils sélectionnés : {stats['nb_outils_selectionnes']}/{stats['nb_outils_total']}")
        print(f"  Réduction : {stats['reduction_pourcent']}%")
        print(f"  Auto-amélioration : {'✓' if stats['besoin_auto_amelioration'] else '✗'}")
        print(f"  Documents : {'✓' if stats['besoin_documents'] else '✗'}")
        print()
    
    print("✅ Module tool_routing chargé avec succès\n")