"""
Core JIBI.

Le package core contient :
- agent_core : orchestration de haut niveau
- cerveau : communication avec le LLM
- evolution : façade de compatibilité
- tool_routing : routage des outils
- config : configuration centrale
- prompts : prompts système
"""

__version__ = "5.0.0"

__all__ = [
    "agent_core",
    "cerveau",
    "evolution",
    "tool_routing",
]