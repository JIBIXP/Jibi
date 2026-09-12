"""
Sauvegardes et retour arrière (rollback) du code de JIBI.

Principe :
- avant TOUTE mise à jour, updater.py doit appeler creer_sauvegarde()
  ici pour capturer un état restaurable ;
- la sauvegarde est un simple dossier horodaté, copié dans
  workspace/sauvegardes/ — donc indépendant d'un éventuel
  'git reset --hard' qui suivrait, même en cas de dépôt git corrompu ;
- restaurer_derniere_sauvegarde() est une action SENSIBLE, exactement
  comme supprimer_fichier ou fermer_application dans tools/ : elle
  exige confirmer=True, le modèle ne peut jamais l'appeler seul.
"""

import os
import shutil
from datetime import datetime, timezone

from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

DEPOT_DIR = os.path.abspath(os.getenv("JIBI_PROJET_DIR", "."))

DOSSIER_SAUVEGARDES = os.path.abspath(
    os.getenv(
        "JIBI_SAUVEGARDES_DIR",
        os.path.join(DEPOT_DIR, "workspace", "sauvegardes")
    )
)

os.makedirs(DOSSIER_SAUVEGARDES, exist_ok=True)

# Dossiers à ne jamais copier dans une sauvegarde : inutiles, lourds,
# ou eux-mêmes des sauvegardes (éviter la récursion infinie).
EXCLUS = {
    ".git", "__pycache__", ".vscode", "logs",
    "workspace",  # jibi_files/sauvegardes utilisateur : jamais écrasés par un rollback de code
    "venv", ".venv", "node_modules",
}

NOMBRE_MAX_SAUVEGARDES = int(os.getenv("JIBI_MAX_SAUVEGARDES", "5"))


def _ignorer(dossier, contenu):
    return [nom for nom in contenu if nom in EXCLUS]


def creer_sauvegarde(etiquette=""):
    """
    Copie l'état actuel du code (hors dossiers exclus) dans un nouveau
    sous-dossier horodaté. Purge ensuite les plus anciennes sauvegardes
    au-delà de NOMBRE_MAX_SAUVEGARDES.
    """

    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    nom_dossier = f"{horodatage}_{etiquette}".rstrip("_")

    chemin_sauvegarde = os.path.join(
        DOSSIER_SAUVEGARDES, nom_dossier
    )

    shutil.copytree(DEPOT_DIR, chemin_sauvegarde, ignore=_ignorer)

    log_event("updater", f"Sauvegarde créée : {nom_dossier}")

    _purger_anciennes_sauvegardes()

    return chemin_sauvegarde


def lister_sauvegardes():
    """Liste des sauvegardes existantes, de la plus récente à la plus ancienne."""

    if not os.path.isdir(DOSSIER_SAUVEGARDES):
        return []

    return sorted(os.listdir(DOSSIER_SAUVEGARDES), reverse=True)


def _purger_anciennes_sauvegardes():

    sauvegardes = lister_sauvegardes()

    for ancienne in sauvegardes[NOMBRE_MAX_SAUVEGARDES:]:

        chemin = os.path.join(DOSSIER_SAUVEGARDES, ancienne)

        try:
            shutil.rmtree(chemin)
            log_event("updater", f"Ancienne sauvegarde supprimée : {ancienne}")

        except Exception as e:
            log_warning("updater", f"Purge de '{ancienne}' échouée : {e}")


def restaurer_derniere_sauvegarde(confirmer=False):
    """
    Restaure la sauvegarde la plus récente par-dessus le code actuel.

    Action SENSIBLE : refuse sans confirmer=True, exactement comme
    supprimer_fichier/fermer_application dans tools/. C'est à agent.py
    de demander confirmation à l'utilisateur avant d'appeler ceci avec
    confirmer=True.
    """

    if not confirmer:
        raise PermissionError(
            "Restauration refusée sans confirmation explicite "
            "(confirmer=True) — cette action écrase le code actuel."
        )

    sauvegardes = lister_sauvegardes()

    if not sauvegardes:
        raise FileNotFoundError(
            "Aucune sauvegarde disponible pour un rollback."
        )

    plus_recente = sauvegardes[0]

    chemin_source = os.path.join(DOSSIER_SAUVEGARDES, plus_recente)

    for element in os.listdir(chemin_source):

        source = os.path.join(chemin_source, element)
        destination = os.path.join(DEPOT_DIR, element)

        if os.path.isdir(source):

            if os.path.isdir(destination):
                shutil.rmtree(destination)

            shutil.copytree(source, destination)

        else:
            shutil.copy2(source, destination)

    log_event(
        "updater",
        f"Rollback effectué depuis la sauvegarde : {plus_recente}"
    )

    return f"Code restauré depuis la sauvegarde '{plus_recente}'."
