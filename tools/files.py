"""
Gestion des fichiers — limitée à un dossier de travail dédié.

Sécurité :
- toute opération est confinée à JIBI_FILES_DIR (par défaut
  ./jibi_files) : impossible de sortir de ce dossier, même avec
  '../../etc/passwd' ou un chemin absolu ailleurs ;
- la suppression exige une confirmation explicite (confirmer=True).
"""

import os

from dotenv import load_dotenv
from datetime import datetime, timezone
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

DOSSIER_TRAVAIL = os.path.abspath(
    os.getenv("JIBI_FILES_DIR", "./jibi_files")
)

os.makedirs(DOSSIER_TRAVAIL, exist_ok=True)


def _resoudre_chemin(chemin):
    """
    Résout `chemin` par rapport au dossier de travail et vérifie qu'il
    n'en sort pas (protection contre '../' et les chemins absolus).
    """

    chemin_complet = os.path.abspath(
        os.path.join(DOSSIER_TRAVAIL, chemin)
    )

    if os.path.commonpath(
        [chemin_complet, DOSSIER_TRAVAIL]
    ) != DOSSIER_TRAVAIL:

        raise PermissionError(
            f"Chemin refusé : '{chemin}' sort du dossier de travail "
            f"autorisé ({DOSSIER_TRAVAIL})."
        )

    return chemin_complet


def creer_fichier(chemin, contenu=""):

    chemin_complet = _resoudre_chemin(chemin)

    try:
        os.makedirs(
            os.path.dirname(chemin_complet),
            exist_ok=True
        )

        with open(chemin_complet, "w", encoding="utf-8") as f:
            f.write(contenu)

        log_event("files", f"Fichier créé: {chemin}")

        return f"Fichier '{chemin}' créé ({len(contenu)} caractères)."

    except Exception as e:
        log_error("files", f"creer_fichier échoué: {e}", exc_info=False)
        raise


def lire_fichier(chemin, max_caracteres=5000):

    chemin_complet = _resoudre_chemin(chemin)

    if not os.path.isfile(chemin_complet):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    with open(chemin_complet, "r", encoding="utf-8", errors="replace") as f:
        contenu = f.read(max_caracteres)

    log_event("files", f"Fichier lu: {chemin}")

    return contenu


def lister_fichiers(sous_dossier=""):

    chemin_complet = _resoudre_chemin(sous_dossier)

    if not os.path.isdir(chemin_complet):
        raise NotADirectoryError(f"Dossier introuvable : {sous_dossier}")

    return sorted(os.listdir(chemin_complet))


def supprimer_fichier(chemin, confirmer=False):

    if not confirmer:
        raise PermissionError(
            "Suppression refusée sans confirmation explicite "
            "(confirmer=True)."
        )

    chemin_complet = _resoudre_chemin(chemin)

    if not os.path.isfile(chemin_complet):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    os.remove(chemin_complet)

    log_event("files", f"Fichier supprimé: {chemin}")

    return f"Fichier '{chemin}' supprimé."


# ============================================================
# LECTURE SEULE DU CODE SOURCE DE JIBI
# ============================================================
#
# Objectif : permettre à JIBI de lire (jamais d'écrire) son propre
# code pour proposer des améliorations, SANS jamais pouvoir modifier
# les vrais fichiers ni accéder à autre chose que du code Python.
#
# Sécurité :
# - extension .py UNIQUEMENT : exclut automatiquement .env (aucune
#   extension) et empêche donc toute fuite de mot de passe MySQL ou
#   de clé API, y compris à voix haute via la synthèse vocale ;
# - confiné à PROJET_DIR, avec la même protection anti '../' que
#   pour le dossier de travail ;
# - AUCUNE fonction d'écriture dans cet espace : voir
#   proposer_amelioration() plus bas pour la seule façon dont JIBI
#   peut "proposer" un changement — toujours dans un fichier séparé.

PROJET_DIR = os.path.abspath(
    os.getenv("JIBI_PROJET_DIR", ".")
)

EXTENSIONS_CODE_AUTORISEES = {".py"}

DOSSIERS_EXCLUS = {
    "__pycache__", ".git", ".vscode", "logs",
    os.path.basename(DOSSIER_TRAVAIL)  # jamais son propre espace d'écriture
}


def _resoudre_chemin_code(chemin):

    chemin_complet = os.path.abspath(
        os.path.join(PROJET_DIR, chemin)
    )

    if os.path.commonpath(
        [chemin_complet, PROJET_DIR]
    ) != PROJET_DIR:

        raise PermissionError(
            f"Chemin refusé : '{chemin}' sort du dossier du projet."
        )

    extension = os.path.splitext(chemin_complet)[1].lower()

    if extension not in EXTENSIONS_CODE_AUTORISEES:
        raise PermissionError(
            f"Lecture refusée : seuls les fichiers .py sont "
            f"accessibles (demandé : '{extension or '(sans extension)'}')."
        )

    return chemin_complet


def lire_code_source(chemin, max_caracteres=8000):
    """Lit un fichier .py du projet, en LECTURE SEULE."""

    chemin_complet = _resoudre_chemin_code(chemin)

    if not os.path.isfile(chemin_complet):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    with open(chemin_complet, "r", encoding="utf-8", errors="replace") as f:
        contenu = f.read(max_caracteres)

    log_event("files", f"Code source lu (lecture seule): {chemin}")

    return contenu


def lister_code_source():
    """Liste tous les fichiers .py du projet (hors dossiers exclus)."""

    resultats = []

    for racine, dossiers, fichiers in os.walk(PROJET_DIR):

        dossiers[:] = [
            d for d in dossiers
            if d not in DOSSIERS_EXCLUS and not d.startswith(".")
        ]

        for nom in fichiers:
            if nom.endswith(".py"):
                chemin_relatif = os.path.relpath(
                    os.path.join(racine, nom),
                    PROJET_DIR
                )
                resultats.append(chemin_relatif.replace("\\", "/"))

    return sorted(resultats)


def proposer_amelioration(fichier_concerne, description, code_propose):
    """
    Écrit une PROPOSITION de changement dans le dossier de travail
    confiné — jamais dans le vrai fichier. C'est à l'humain de relire
    et d'appliquer manuellement s'il est d'accord.
    """

    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    nom_base = os.path.basename(fichier_concerne).replace(".py", "")

    chemin_proposition = f"propositions/{horodatage}_{nom_base}.md"

    contenu = (
        f"# Proposition pour {fichier_concerne}\n\n"
        f"Date (UTC) : {horodatage}\n\n"
        f"## Description\n\n{description}\n\n"
        f"## Code proposé\n\n```python\n{code_propose}\n```\n\n"
        f"---\n*Cette proposition n'a PAS été appliquée. "
        f"Relire puis appliquer manuellement si pertinent.*\n"
    )

    return creer_fichier(chemin_proposition, contenu)