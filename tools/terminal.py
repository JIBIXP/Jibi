"""
Terminal — exécution contrôlée de commandes.

Sécurité :
- shell=False systématiquement : la commande est découpée en liste
  d'arguments et passée directement au processus, SANS jamais passer
  par un interpréteur shell. Ça élimine par construction l'injection
  via ';', '&&', '|', '>', etc. — ces caractères sont traités comme du
  texte littéral, pas comme des opérateurs ;
- seul l'exécutable en tête de commande doit figurer dans la liste
  blanche COMMANDES_AUTORISEES (configurable via .env) ;
- timeout systématique pour éviter qu'une commande bloque JIBI
  indéfiniment ;
- une commande absente de la liste blanche est refusée, jamais exécutée
  "juste pour voir".
"""

import os
import shlex
import subprocess

from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

_DEFAUT = "dir,ls,pwd,echo,git,python,pip,node,npm,ollama,type,cat,whoami,date"

COMMANDES_AUTORISEES = {
    c.strip().lower()
    for c in os.getenv("JIBI_COMMANDES_AUTORISEES", _DEFAUT).split(",")
    if c.strip()
}

TIMEOUT_COMMANDE = int(os.getenv("JIBI_TIMEOUT_COMMANDE", "15"))


def executer_commande(commande):
    """
    Exécute `commande` (chaîne, ex: "git status") si son exécutable est
    autorisé, et renvoie stdout/stderr/code de retour.

    Refuse toute commande dont l'exécutable n'est pas dans
    COMMANDES_AUTORISEES — pas d'exception possible, même sur demande
    explicite de l'utilisateur final, car c'est le modèle qui choisit
    la commande à exécuter ici, pas un humain qui tape directement dans
    un vrai terminal.
    """

    try:
        parties = shlex.split(commande, posix=(os.name != "nt"))
    except ValueError as e:
        return {"erreur": f"Commande mal formée : {e}"}

    if not parties:
        return {"erreur": "Commande vide."}

    executable = parties[0].lower()

    if executable not in COMMANDES_AUTORISEES:
        log_warning(
            "terminal",
            f"Commande refusée (hors liste blanche): {executable}"
        )

        return {
            "erreur": (
                f"Commande '{executable}' non autorisée. "
                f"Autorisées : {', '.join(sorted(COMMANDES_AUTORISEES))}"
            )
        }

    try:
        resultat = subprocess.run(
            parties,
            shell=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_COMMANDE
        )

        log_event(
            "terminal",
            f"Commande exécutée: {executable} "
            f"(code {resultat.returncode})"
        )

        return {
            "stdout": resultat.stdout[:3000],
            "stderr": resultat.stderr[:1000],
            "code_retour": resultat.returncode
        }

    except subprocess.TimeoutExpired:
        log_warning("terminal", f"Timeout sur commande: {executable}")
        return {"erreur": f"Timeout après {TIMEOUT_COMMANDE}s."}

    except FileNotFoundError:
        return {"erreur": f"Exécutable introuvable : {executable}"}

    except Exception as e:
        log_error("terminal", f"executer_commande échoué: {e}", exc_info=False)
        return {"erreur": str(e)[:200]}