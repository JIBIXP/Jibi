"""
Registre central des outils de JIBI.

Chaque outil enregistré porte maintenant, en plus de sa fonction et sa
description, un schéma `parameters` (format JSON Schema attendu par le
function-calling d'Ollama). tools_ollama_format() génère directement la
liste à passer à `tools=` dans un appel Ollama, pour que agent.py n'ait
pas à dupliquer ces définitions à la main.
"""

TOOLS_REGISTRY = {}


def register_tool(name, function, description="", parameters=None):
    TOOLS_REGISTRY[name] = {
        "function": function,
        "description": description,
        "parameters": parameters or {
            "type": "object",
            "properties": {},
            "required": []
        },
    }


def get_tool(name):
    outil = TOOLS_REGISTRY.get(name)
    return outil["function"] if outil else None


def list_tools():
    return {
        nom: data["description"]
        for nom, data in TOOLS_REGISTRY.items()
    }


def tools_ollama_format():
    """Renvoie la liste des outils enregistrés au format function-calling Ollama."""

    return [
        {
            "type": "function",
            "function": {
                "name": nom,
                "description": data["description"],
                "parameters": data["parameters"],
            }
        }
        for nom, data in TOOLS_REGISTRY.items()
    ]