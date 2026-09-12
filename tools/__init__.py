"""
Modules outils de JIBI.

L'import de ce package enregistre automatiquement les outils
disponibles dans tool_registry.TOOLS_REGISTRY, avec leur schéma de
paramètres, pour que l'agent puisse les exposer au function-calling
d'Ollama sans dupliquer les définitions à la main (voir
tool_registry.tools_ollama_format()).
"""

from . import browser
from . import files
from . import pc_control
from . import terminal
from . import vision

from .tool_registry import register_tool


register_tool(
    "ouvrir_url",
    browser.ouvrir_url,
    "Ouvre une URL (http/https uniquement) dans un navigateur contrôlé.",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL http(s) à ouvrir."}
        },
        "required": ["url"]
    }
)

register_tool(
    "obtenir_texte_page",
    browser.obtenir_texte_page,
    "Renvoie le texte visible de la page actuellement ouverte.",
    {
        "type": "object",
        "properties": {
            "max_caracteres": {
                "type": "integer",
                "description": "Longueur max du texte renvoyé (défaut 3000)."
            }
        },
        "required": []
    }
)

register_tool(
    "cliquer",
    browser.cliquer,
    "Clique sur un élément de la page via un sélecteur CSS.",
    {
        "type": "object",
        "properties": {
            "selecteur": {"type": "string", "description": "Sélecteur CSS de l'élément."}
        },
        "required": ["selecteur"]
    }
)

register_tool(
    "remplir_champ",
    browser.remplir_champ,
    "Remplit un champ de formulaire via un sélecteur CSS.",
    {
        "type": "object",
        "properties": {
            "selecteur": {"type": "string", "description": "Sélecteur CSS du champ."},
            "texte": {"type": "string", "description": "Texte à saisir."}
        },
        "required": ["selecteur", "texte"]
    }
)

register_tool(
    "fermer_navigateur",
    browser.fermer_navigateur,
    "Ferme le navigateur contrôlé."
)


register_tool(
    "creer_fichier",
    files.creer_fichier,
    "Crée un fichier texte dans le dossier de travail de JIBI.",
    {
        "type": "object",
        "properties": {
            "chemin": {"type": "string", "description": "Chemin relatif du fichier à créer."},
            "contenu": {"type": "string", "description": "Contenu texte du fichier."}
        },
        "required": ["chemin"]
    }
)

register_tool(
    "lire_fichier",
    files.lire_fichier,
    "Lit le contenu d'un fichier du dossier de travail de JIBI.",
    {
        "type": "object",
        "properties": {
            "chemin": {"type": "string", "description": "Chemin relatif du fichier à lire."}
        },
        "required": ["chemin"]
    }
)

register_tool(
    "lister_fichiers",
    files.lister_fichiers,
    "Liste les fichiers d'un sous-dossier du dossier de travail de JIBI.",
    {
        "type": "object",
        "properties": {
            "sous_dossier": {"type": "string", "description": "Sous-dossier à lister (vide = racine)."}
        },
        "required": []
    }
)

register_tool(
    "supprimer_fichier",
    files.supprimer_fichier,
    "Supprime un fichier du dossier de travail de JIBI (confirmation utilisateur requise).",
    {
        "type": "object",
        "properties": {
            "chemin": {"type": "string", "description": "Chemin relatif du fichier à supprimer."}
        },
        "required": ["chemin"]
    }
)

register_tool(
    "lire_code_source",
    files.lire_code_source,
    "Lit un fichier .py du code de JIBI, en LECTURE SEULE (jamais .env ni autre).",
    {
        "type": "object",
        "properties": {
            "chemin": {"type": "string", "description": "Chemin relatif du fichier .py à lire, ex: 'agent.py' ou 'tools/browser.py'."}
        },
        "required": ["chemin"]
    }
)

register_tool(
    "lister_code_source",
    files.lister_code_source,
    "Liste tous les fichiers .py du projet JIBI."
)

register_tool(
    "proposer_amelioration",
    files.proposer_amelioration,
    "Écrit une proposition d'amélioration de code dans un fichier séparé (jamais appliquée automatiquement — à relire et appliquer manuellement).",
    {
        "type": "object",
        "properties": {
            "fichier_concerne": {"type": "string", "description": "Nom du fichier visé par la proposition, ex: 'agent.py'."},
            "description": {"type": "string", "description": "Explication de l'amélioration proposée et pourquoi."},
            "code_propose": {"type": "string", "description": "Extrait de code proposé."}
        },
        "required": ["fichier_concerne", "description", "code_propose"]
    }
)


register_tool(
    "ouvrir_application",
    pc_control.ouvrir_application,
    "Ouvre une application connue (navigateur, explorateur_fichiers, terminal, vscode).",
    {
        "type": "object",
        "properties": {
            "nom": {"type": "string", "description": "Nom de l'application (parmi la liste connue)."}
        },
        "required": ["nom"]
    }
)

register_tool(
    "fermer_application",
    pc_control.fermer_application,
    "Ferme une application par son nom (confirmation utilisateur requise).",
    {
        "type": "object",
        "properties": {
            "nom": {"type": "string", "description": "Nom (ou partie du nom) du processus à fermer."}
        },
        "required": ["nom"]
    }
)


register_tool(
    "executer_commande",
    terminal.executer_commande,
    "Exécute une commande shell parmi une liste blanche autorisée (confirmation utilisateur requise).",
    {
        "type": "object",
        "properties": {
            "commande": {"type": "string", "description": "Commande complète à exécuter, ex: 'git status'."}
        },
        "required": ["commande"]
    }
)


register_tool(
    "analyser_image",
    vision.analyser_image,
    "Décrit ou répond à une question sur une image via un modèle vision local.",
    {
        "type": "object",
        "properties": {
            "chemin": {"type": "string", "description": "Chemin de l'image à analyser."},
            "question": {"type": "string", "description": "Question précise sur l'image (optionnel)."}
        },
        "required": ["chemin"]
    }
)

register_tool(
    "capturer_ecran",
    vision.capturer_ecran,
    "Capture l'écran et enregistre l'image sur disque."
)

register_tool(
    "capturer_et_analyser",
    vision.capturer_et_analyser,
    "Capture l'écran puis l'analyse immédiatement via le modèle vision.",
    {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Question précise sur ce qui est affiché à l'écran (optionnel)."}
        },
        "required": []
    }
)