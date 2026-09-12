"""
Package updater de JIBI.

L'import de ce package enregistre automatiquement les outils de mise
à jour dans le MÊME registre que tools/ (tool_registry.TOOLS_REGISTRY),
pour qu'ils soient exposés au function-calling d'Ollama sans dupliquer
les définitions à la main. Voir tools/__init__.py pour le même schéma.
"""

from . import checker
from . import updater
from . import rollback

from tools.tool_registry import register_tool


register_tool(
    "verifier_mise_a_jour",
    checker.verifier_mise_a_jour,
    "Vérifie (lecture seule) si une mise à jour de JIBI est disponible "
    "sur le dépôt git distant.",
)

register_tool(
    "appliquer_mise_a_jour",
    updater.appliquer_mise_a_jour,
    "Applique la dernière mise à jour disponible de JIBI (confirmation "
    "utilisateur requise). Crée automatiquement une sauvegarde avant "
    "toute modification et annule si l'opération échoue.",
    {
        "type": "object",
        "properties": {},
        "required": []
    }
)

register_tool(
    "restaurer_derniere_sauvegarde",
    rollback.restaurer_derniere_sauvegarde,
    "Restaure le code de JIBI à partir de la dernière sauvegarde "
    "connue, annulant la dernière mise à jour (confirmation "
    "utilisateur requise).",
    {
        "type": "object",
        "properties": {},
        "required": []
    }
)
