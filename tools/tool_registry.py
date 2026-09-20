"""
Registre central des outils de JIBI.
"""

# ============================================================
# IMPORTS — UN SEUL FICHIER pc_control maintenant
# ============================================================

from tools.pc_control import (
    # --- Contrôle applications (BASE) ---
    ouvrir_application,
    application_est_lancee,
    obtenir_etat_application,
    obtenir_processus,
    fermer_application,
    informations_systeme,

    # --- Gestion fichiers (AVANCÉ) ---
    ouvrir_fichier,
    ouvrir_dossier,
    creer_dossier,
    rechercher_fichiers,
    renommer_fichier,
    deplacer_fichier,
    copier_fichier,
    supprimer_fichier,

    # --- Surveillance (AVANCÉ) ---
    obtenir_espace_disque,
    obtenir_infos_systeme_detaillees,
    lister_applications_ouvertes,
    surveiller_ressources,
)

from tools.documents import (
    creer_document_word,
    creer_document_pdf,
)

# ---------------------------------------------------------------------------
# Registre
# ---------------------------------------------------------------------------

TOOLS_REGISTRY = {}


def register_tool(name, function, description="", parameters=None):
    TOOLS_REGISTRY[name] = {
        "function": function,
        "description": description,
        "parameters": parameters or {"type": "object", "properties": {}, "required": []},
    }


def get_tool(name):
    outil = TOOLS_REGISTRY.get(name)
    return outil["function"] if outil else None


def list_tools():
    return {n: d["description"] for n, d in TOOLS_REGISTRY.items()}


def tools_ollama_format():
    return [
        {"type": "function", "function": {"name": n, "description": d["description"], "parameters": d["parameters"]}}
        for n, d in TOOLS_REGISTRY.items()
    ]


# ===========================================================================
# ENREGISTREMENT DES OUTILS PC (tout ici, plus besoin de if PC_CONTROL_ADVANCED_OK)
# ===========================================================================

# --- Applications ---

register_tool("ouvrir_application", ouvrir_application,
    "Ouvre une application autorisée sur le PC.",
    {"type":"object","properties":{"nom":{"type":"string","description":"Nom de l'application (navigateur, vscode, terminal...)"}},"required":["nom"]})

register_tool("application_est_lancee", application_est_lancee,
    "Vérifie si une application est lancée.",
    {"type":"object","properties":{"nom":{"type":"string"}},"required":["nom"]})

register_tool("obtenir_etat_application", obtenir_etat_application,
    "État d'une application.",
    {"type":"object","properties":{"nom":{"type":"string"}},"required":["nom"]})

register_tool("obtenir_processus", obtenir_processus,
    "Liste les processus actifs.",
    {"type":"object","properties":{"recherche":{"type":"string"},"limite":{"type":"integer"}},"required":[]})

register_tool("fermer_application", fermer_application,
    "Ferme une application (CONFIRMATION REQUISE).",
    {"type":"object","properties":{"nom":{"type":"string"},"confirmer":{"type":"boolean"}},"required":["nom","confirmer"]})

register_tool("informations_systeme", informations_systeme,
    "Infos générales PC.",
    {"type":"object","properties":{},"required":[]})

# --- Fichiers & Dossiers ---

register_tool("ouvrir_fichier", ouvrir_fichier,
    "Ouvre un fichier avec l'appli par défaut.",
    {"type":"object","properties":{"chemin":{"type":"string"}},"required":["chemin"]})

register_tool("ouvrir_dossier", ouvrir_dossier,
    "Ouvre un dossier dans l'explorateur.",
    {"type":"object","properties":{"chemin":{"type":"string"}},"required":["chemin"]})

register_tool("creer_dossier", creer_dossier,
    "Crée un dossier (parents auto-créés).",
    {"type":"object","properties":{"chemin":{"type":"string"}},"required":["chemin"]})

register_tool("rechercher_fichiers", rechercher_fichiers,
    "Recherche fichiers par pattern (*.pdf, rapport_*).",
    {"type":"object","properties":{
        "nom_pattern":{"type":"string"},
        "dossier_recherche":{"type":"string"},
        "limite":{"type":"integer"}
    },"required":["nom_pattern"]})

register_tool("renommer_fichier", renommer_fichier,
    "Renomme un fichier/dossier.",
    {"type":"object","properties":{"ancien_chemin":{"type":"string"},"nouveau_nom":{"type":"string"}},"required":["ancien_chemin","nouveau_nom"]})

register_tool("deplacer_fichier", deplacer_fichier,
    "Déplace vers un dossier.",
    {"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"]})

register_tool("copier_fichier", copier_fichier,
    "Copie vers un dossier.",
    {"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"]})

register_tool("supprimer_fichier", supprimer_fichier,
    "Supprime définitivement (CONFIRMATION REQUISE).",
    {"type":"object","properties":{"chemin":{"type":"string"},"confirmer":{"type":"boolean"}},"required":["chemin","confirmer"]})

# --- Surveillance ---

register_tool("obtenir_espace_disque", obtenir_espace_disque,
    "Espace disque (total, utilisé, libre).",
    {"type":"object","properties":{"chemin":{"type":"string"}},"required":[]})

register_tool("obtenir_infos_systeme_detaillees", obtenir_infos_systeme_detaillees,
    "Détails CPU/RAM/disque/température.",
    {"type":"object","properties":{},"required":[]})

register_tool("lister_applications_ouvertes", lister_applications_ouvertes,
    "Liste applications ouvertes + mémoire.",
    {"type":"object","properties":{"limite":{"type":"integer"}},"required":[]})

register_tool("surveiller_ressources", surveiller_ressources,
    "Surveille CPU/RAM pendant N secondes.",
    {"type":"object","properties":{"duree_secondes":{"type":"integer"}},"required":[]})

# --- Documents ---

register_tool("creer_document_word", creer_document_word,
    "Crée un document Word (.docx).",
    {"type":"object","properties":{"nom_fichier":{"type":"string"},"titre":{"type":"string"},"contenu":{"type":"string"}},"required":["nom_fichier","titre","contenu"]})

register_tool("creer_document_pdf", creer_document_pdf,
    "Crée un document PDF.",
    {"type":"object","properties":{"nom_fichier":{"type":"string"},"titre":{"type":"string"},"contenu":{"type":"string"}},"required":["nom_fichier","titre","contenu"]})


# --- Auto-Amélioration & Recherche ---

try:
    from tools.self_improvement_tools import (
        analyser_sante_jibi,
        tableau_bord_amelioration,
        preparer_amelioration,
    )
    register_tool("analyser_sante_jibi", analyser_sante_jibi,
        "Analyse la santé globale et les logs récents de JIBI pour détecter anomalies.",
        {"type":"object","properties":{"limite_logs":{"type":"integer"}},"required":[]})
    register_tool("tableau_bord_amelioration", tableau_bord_amelioration,
        "Tableau de bord de l'auto-amélioration et propositions d'évolution.",
        {"type":"object","properties":{},"required":[]})
    register_tool("preparer_amelioration", preparer_amelioration,
        "Prépare une proposition d'amélioration de code dans le laboratoire.",
        {"type":"object","properties":{"fichier":{"type":"string"},"probleme":{"type":"string"},"solution":{"type":"string"}},"required":["fichier","probleme","solution"]})
except Exception as _e_si:
    pass

try:
    from tools.web_search import rechercher_web
    register_tool("rechercher_web", rechercher_web,
        "Effectue une recherche d'informations en ligne via le Web.",
        {"type":"object","properties":{"requete":{"type":"string"}},"required":["requete"]})
except Exception as _e_ws:
    pass


def obtenir_catalogue_outils():
    """Renvoie la liste structurée des outils pour affichage GUI."""
    catalogue = []
    for name, data in TOOLS_REGISTRY.items():
        catalogue.append({
            "nom": name,
            "description": data.get("description", ""),
            "actif": True,
        })
    return catalogue


# ===========================================================================
# VÉRIFICATION
# ===========================================================================

def verifier_registre():
    outils_attendus = [
        "ouvrir_application","application_est_lancee","obtenir_etat_application","obtenir_processus",
        "fermer_application","informations_systeme","ouvrir_fichier","ouvrir_dossier","creer_dossier",
        "rechercher_fichiers","renommer_fichier","deplacer_fichier","copier_fichier","supprimer_fichier",
        "obtenir_espace_disque","obtenir_infos_systeme_detaillees","lister_applications_ouvertes",
        "surveiller_ressources","creer_document_word","creer_document_pdf",
    ]
    manquants = [n for n in outils_attendus if n not in TOOLS_REGISTRY]
    return (False, manquants) if manquants else (True, [])

REGISTRE_OK, OUTILS_MANQUANTS = verifier_registre()

