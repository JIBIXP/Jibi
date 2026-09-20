"""
Module de gestion des documents de JIBI.

Permet :
- d'analyser des documents ;
- de générer des documents Word ;
- de générer des documents PDF ;
- de détecter le type de document.

CORRIGÉ v2 : imports paresseux — les dépendances lourdes et optionnelles
(PyPDF2, python-docx, fpdf, PIL, pytesseract) ne sont chargées qu'à la
première utilisation réelle, jamais au simple `import`. Avant, un seul
package manquant faisait échouer toute la chaîne d'outils de JIBI.
"""

__all__ = [
    "DocumentAnalyzer",
    "DocumentGenerator",
    "DocumentParser",
]


def __getattr__(name):
    if name == "DocumentAnalyzer":
        from .analyzer import DocumentAnalyzer
        return DocumentAnalyzer
    if name == "DocumentGenerator":
        from .generator import DocumentGenerator
        return DocumentGenerator
    if name == "DocumentParser":
        from .parser import DocumentParser
        return DocumentParser
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")