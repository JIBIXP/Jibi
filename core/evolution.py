"""
Façade de compatibilité du moteur d'évolution JIBI.

Le moteur réel se trouve dans :
    self_improvement.evolution

Ce fichier évite de casser les anciens imports :
    from core import evolution
"""

from self_improvement.evolution import *  # noqa: F401,F403