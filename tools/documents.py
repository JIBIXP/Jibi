"""
Création de documents Word et PDF.

Sécurité :
- réutilise _resoudre_chemin() de files.py ;
- confinement dans JIBI_FILES_DIR ;
- protection contre ../ et chemins absolus ;
- écriture uniquement dans le dossier de travail ;
- aucune logique de sécurité dupliquée.

Le moteur de génération est délégué à modules.document.generator.
"""

import os

from .files import _resoudre_chemin

from modules.document.generator import DocumentGenerator

from logging_jibi import log_event, log_error


def creer_document_word(chemin, titre, contenu):
    """
    Crée un document Word (.docx) dans le dossier de travail.
    """

    if not chemin.lower().endswith(".docx"):
        chemin = chemin + ".docx"

    chemin_complet = _resoudre_chemin(chemin)

    try:
        os.makedirs(
            os.path.dirname(chemin_complet),
            exist_ok=True
        )

        DocumentGenerator.generate_word(
            chemin_complet,
            titre,
            contenu
        )

        log_event(
            "documents",
            f"Document Word créé: {chemin}"
        )

        return (
            f"Document Word '{chemin}' "
            f"créé avec succès."
        )

    except Exception as e:

        log_error(
            "documents",
            f"creer_document_word échoué: {e}",
            exc_info=False
        )

        raise


def creer_document_pdf(chemin, titre, contenu):
    """
    Crée un document PDF dans le dossier de travail.
    """

    if not chemin.lower().endswith(".pdf"):
        chemin = chemin + ".pdf"

    chemin_complet = _resoudre_chemin(chemin)

    try:
        os.makedirs(
            os.path.dirname(chemin_complet),
            exist_ok=True
        )

        DocumentGenerator.generate_pdf(
            chemin_complet,
            titre,
            contenu
        )

        log_event(
            "documents",
            f"Document PDF créé: {chemin}"
        )

        return (
            f"Document PDF '{chemin}' "
            f"créé avec succès."
        )

    except Exception as e:

        log_error(
            "documents",
            f"creer_document_pdf échoué: {e}",
            exc_info=False
        )

        raise