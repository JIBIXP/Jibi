"""
Module de gestion des documents de JIBI.

Permet :
- d'analyser des documents ;
- de générer des documents Word ;
- de générer des documents PDF ;
- de détecter le type de document.
"""

from .analyzer import DocumentAnalyzer
from .generator import DocumentGenerator
from .parser import DocumentParser


__all__ = [
    "DocumentAnalyzer",
    "DocumentGenerator",
    "DocumentParser",
]