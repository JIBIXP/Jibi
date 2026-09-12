"""
Contrôle du PC — ouverture/fermeture d'applications.

Sécurité :
- ouvrir_application n'accepte QUE des noms présents dans
  APPLICATIONS_AUTORISEES (mapping nom → commande réelle), jamais un
  chemin arbitraire fourni tel quel : ça évite qu'un message ambigu
  ("ouvre ceci : /chemin/vers/script_malveillant") ne lance n'importe
  quoi ;
- fermer_application exige une confirmation explicite (confirmer=True),
  car terminer un processus peut faire perdre du travail non sauvegardé ;
- fermer_application utilise psutil et ne cible que les processus dont
  le nom correspond, jamais un PID fourni en clair par le modèle.
"""

import os
import platform
import subprocess

from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

SYSTEME = platform.system()  # "Windows", "Darwin", "Linux"

# Mapping nom convivial -> commande réelle. À compléter dans le code
# (pas via message utilisateur) pour garder le contrôle sur ce qui peut
# être lancé.
APPLICATIONS_AUTORISEES = {
    "navigateur": {
        "Windows": ["cmd", "/c", "start", "chrome"],
        "Darwin": ["open", "-a", "Google Chrome"],
        "Linux": ["xdg-open", "https://"],
    },
    "explorateur_fichiers": {
        "Windows": ["explorer"],
        "Darwin": ["open", "."],
        "Linux": ["xdg-open", "."],
    },
    "terminal": {
        "Windows": ["cmd"],
        "Darwin": ["open", "-a", "Terminal"],
        "Linux": ["x-terminal-emulator"],
    },
    "vscode": {
        "Windows": ["code"],
        "Darwin": ["code"],
        "Linux": ["code"],
    },
}


def ouvrir_application(nom):

    nom = nom.strip().lower()

    config = APPLICATIONS_AUTORISEES.get(nom)

    if not config:
        return (
            f"Application '{nom}' non reconnue. "
            f"Autorisées : {', '.join(APPLICATIONS_AUTORISEES)}"
        )

    commande = config.get(SYSTEME)

    if not commande:
        return f"Application '{nom}' non supportée sur {SYSTEME}."

    try:
        subprocess.Popen(commande, shell=False)

        log_event("pc_control", f"Application ouverte: {nom}")

        return f"'{nom}' lancé."

    except Exception as e:
        log_error("pc_control", f"ouvrir_application échoué: {e}", exc_info=False)
        return f"Impossible de lancer '{nom}' : {str(e)[:150]}"


def fermer_application(nom, confirmer=False):

    if not confirmer:
        raise PermissionError(
            "Fermeture refusée sans confirmation explicite "
            "(confirmer=True) — du travail non sauvegardé pourrait "
            "être perdu."
        )

    try:
        import psutil
    except ImportError:
        raise ImportError(
            "Le paquet 'psutil' est requis pour fermer une application : "
            "pip install psutil"
        )

    nom = nom.strip().lower()
    fermes = 0

    for proc in psutil.process_iter(["pid", "name"]):

        try:
            if nom in (proc.info["name"] or "").lower():
                proc.terminate()
                fermes += 1

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    log_event("pc_control", f"Fermeture '{nom}': {fermes} processus")

    if fermes == 0:
        return f"Aucun processus correspondant à '{nom}' trouvé."

    return f"{fermes} processus '{nom}' fermé(s)."