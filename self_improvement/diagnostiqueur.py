# -*- coding: utf-8 -*-
"""
JIBI - Diagnostiqueur v3
========================

Transforme les observations en diagnostics structurés.

Rôle :
    observation
        ↓
    extraction des preuves
        ↓
    classification
        ↓
    normalisation cible
        ↓
    recherche fonction AST
        ↓
    récence / répétition
        ↓
    confiance
        ↓
    diagnostic

IMPORTANT :
    - Ne modifie jamais le code.
    - Ne génère aucun patch.
    - Ne lance aucune correction.
    - Ne décide jamais d'une application.
    - Ne considère pas automatiquement les anciennes erreurs comme actuelles.

Le diagnostiqueur fournit des faits et des hypothèses à l'orchestrateur.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .observateur import RapportObservation


# ============================================================================
# CONFIGURATION
# ============================================================================

try:
    from core.config import PROJECT_ROOT
except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]


PROJECT_ROOT = Path(PROJECT_ROOT).resolve()


# ============================================================================
# MODELES
# ============================================================================

@dataclass
class HypotheseDiagnostic:
    categorie: str
    cause: str
    cible: Optional[str]
    fonction: Optional[str]

    preuves: list[str] = field(default_factory=list)

    confiance: float = 0.0
    gravite: str = "INCONNUE"

    occurrences: int = 1

    # CONFIRME / PROBABLE / RECURRENT / HISTORIQUE / INCERTAIN
    statut: str = "INCERTAIN"

    recente: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RapportDiagnostic:
    ok: bool
    niveau: str

    hypotheses: list[HypotheseDiagnostic]

    fichiers_candidats: list[str]

    erreurs_analysees: int
    warnings_analyses: int

    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "niveau": self.niveau,
            "hypotheses": [
                h.to_dict()
                for h in self.hypotheses
            ],
            "fichiers_candidats": self.fichiers_candidats,
            "erreurs_analysees": self.erreurs_analysees,
            "warnings_analyses": self.warnings_analyses,
            "message": self.message,
        }


# ============================================================================
# CLASSIFICATION
# ============================================================================

ERROR_CLASSES = {
    "ModuleNotFoundError": "DEPENDANCE",
    "ImportError": "DEPENDANCE",

    "NameError": "REFERENCE",
    "AttributeError": "REFERENCE",

    "TypeError": "TYPE",
    "ValueError": "VALEUR",
    "KeyError": "DONNEE",
    "JSONDecodeError": "DONNEE",

    "FileNotFoundError": "FICHIER",
    "PermissionError": "PERMISSION",

    "SyntaxError": "SYNTAXE",
    "IndentationError": "SYNTAXE",

    "TimeoutError": "PERFORMANCE",
    "Timeout": "PERFORMANCE",
    "ReadTimeout": "PERFORMANCE",

    "ConnectionError": "CONNEXION",
    "ConnectionRefusedError": "CONNEXION",
    "HTTPError": "CONNEXION",

    "OSError": "SYSTEME",
    "RuntimeError": "EXECUTION",
}


CATEGORY_KEYWORDS = {
    "PERFORMANCE": (
        "timeout",
        "timed out",
        "trop long",
        "délai",
        "latence",
    ),

    "CONNEXION": (
        "connection refused",
        "connexion refusée",
        "connection error",
        "httpconnectionpool",
        "connexion impossible",
    ),

    "DEPENDANCE": (
        "module not found",
        "no module named",
        "importerror",
        "dépendance",
    ),

    "FICHIER": (
        "file not found",
        "fichier introuvable",
        "no such file",
    ),

    "PERMISSION": (
        "permission denied",
        "access denied",
        "accès refusé",
    ),

    "DONNEE": (
        "json",
        "invalid json",
        "decode",
        "clé absente",
    ),
}


# ============================================================================
# EXTRACTION CLASSE ERREUR
# ============================================================================

def _extraire_classe_erreur(
    message: str,
) -> Optional[str]:
    """Détecte la classe d'exception la plus précise."""

    classes = sorted(
        ERROR_CLASSES,
        key=len,
        reverse=True,
    )

    for nom in classes:
        if re.search(
            rf"\b{re.escape(nom)}\b",
            message,
            re.IGNORECASE,
        ):
            return nom

    return None


# ============================================================================
# EXTRACTION FICHIER
# ============================================================================

def _extraire_fichier(
    message: str,
) -> Optional[str]:
    """Extrait un chemin Python depuis un message."""

    patterns = [
        # Traceback Python.
        r'File\s+"([^"]+\.py)"',

        # Windows absolu.
        r'([A-Za-z]:[\\/][^"\r\n]+?\.py)',

        # Chemin Linux absolu.
        r'(/[^\s"\']+?\.py)',

        # Chemins JIBI relatifs.
        (
            r'((?:core|self_improvement|tools|updater|gui|tests)'
            r'[\\/][^"\s:]+?\.py)'
        ),

        # Fichier simple.
        r'\b([A-Za-z0-9_.-]+\.py)\b',
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            message,
            re.IGNORECASE,
        )

        if match:
            return match.group(1)

    return None


# ============================================================================
# NORMALISATION CHEMIN
# ============================================================================

def _normaliser_cible(
    fichier: Optional[str],
) -> Optional[str]:
    """
    Convertit une cible vers un chemin relatif au projet.

    Exemples :
        C:\\...\\Agent_IA\\core\\cerveau.py
            -> core/cerveau.py

        core\\cerveau.py
            -> core/cerveau.py

        /agent_core.py
            -> agent_core.py
    """

    if not fichier:
        return None

    try:
        brut = str(fichier).strip().strip('"').strip("'")

        if not brut:
            return None

        # Normalisation des séparateurs.
        brut = brut.replace("\\", "/")

        # Nettoyage des préfixes.
        while brut.startswith("./"):
            brut = brut[2:]

        # Chemin absolu Windows/Linux.
        try:
            candidat = Path(brut)

            if candidat.is_absolute():
                try:
                    relatif = candidat.resolve().relative_to(
                        PROJECT_ROOT
                    )

                    return relatif.as_posix()
                except Exception:
                    pass
        except Exception:
            pass

        # Si le chemin contient la racine du projet sous forme texte.
        root_text = str(PROJECT_ROOT).replace("\\", "/").rstrip("/")

        if brut.lower().startswith(
            root_text.lower() + "/"
        ):
            brut = brut[len(root_text) + 1:]

        # Éviter les faux absolus Linux issus des logs.
        brut = brut.lstrip("/")

        # Nettoyage.
        brut = re.sub(
            r"/+",
            "/",
            brut,
        )

        # Protection contre les remontées de répertoire.
        parties = []

        for partie in brut.split("/"):
            if partie in {"", "."}:
                continue

            if partie == "..":
                if parties:
                    parties.pop()
                continue

            parties.append(partie)

        resultat = "/".join(parties)

        return resultat or None

    except Exception:
        return None


# ============================================================================
# EXTRACTION LIGNE
# ============================================================================

def _extraire_ligne(
    message: str,
) -> Optional[int]:
    """Extrait une ligne depuis plusieurs formats."""

    patterns = [
        r"\bline\s+(\d+)\b",
        r"\bligne\s+(\d+)\b",
        r"\.py[\"']?\s*[:,]\s*(\d+)",
        r",\s*line\s+(\d+)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            message,
            re.IGNORECASE,
        )

        if match:
            try:
                ligne = int(match.group(1))

                if ligne > 0:
                    return ligne

            except (TypeError, ValueError):
                pass

    return None


# ============================================================================
# EXTRACTION FONCTION
# ============================================================================

def _extraire_fonction_traceback(
    message: str,
) -> Optional[str]:
    """Cherche une fonction directement dans un traceback."""

    matches = re.findall(
        r"\bin\s+([A-Za-z_][A-Za-z0-9_]*)",
        message,
    )

    if not matches:
        return None

    exclusions = {
        "line",
        "module",
        "file",
        "the",
        "function",
    }

    for nom in reversed(matches):
        if nom.lower() not in exclusions:
            return nom

    return None


# ============================================================================
# RESOLUTION FICHIER
# ============================================================================

def _chemin_projet(
    fichier: Optional[str],
) -> Optional[Path]:

    if not fichier:
        return None

    try:
        cible = _normaliser_cible(fichier)

        if not cible:
            return None

        chemin = (
            PROJECT_ROOT / cible
        ).resolve()

        try:
            chemin.relative_to(PROJECT_ROOT)
        except ValueError:
            return None

        return chemin

    except Exception:
        return None


# ============================================================================
# RECHERCHE FONCTION AST
# ============================================================================

def _chercher_fonction(
    fichier: str,
    ligne: Optional[int],
) -> Optional[str]:
    """Détermine la fonction contenant une ligne donnée."""

    if ligne is None:
        return None

    try:
        path = _chemin_projet(fichier)

        if path is None or not path.is_file():
            return None

        contenu = path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        arbre = ast.parse(
            contenu,
            filename=str(path),
        )

        candidats: list[
            tuple[int, int, int, str]
        ] = []

        for node in ast.walk(arbre):

            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            debut = getattr(
                node,
                "lineno",
                None,
            )

            fin = getattr(
                node,
                "end_lineno",
                debut,
            )

            if debut is None:
                continue

            if fin is None:
                fin = debut

            if debut <= ligne <= fin:

                profondeur = 0

                parent = node

                while hasattr(parent, "_parent"):
                    profondeur += 1
                    parent = parent._parent

                candidats.append(
                    (
                        debut,
                        fin,
                        profondeur,
                        node.name,
                    )
                )

        if not candidats:
            return None

        # Fonction la plus spécifique :
        # début le plus tardif, puis fin la plus courte.
        candidats.sort(
            key=lambda item: (
                item[0],
                -(item[1] - item[0]),
                item[2],
            ),
            reverse=True,
        )

        return candidats[0][3]

    except Exception:
        return None


# ============================================================================
# PARSING AST AVEC PARENTS
# ============================================================================

def _ajouter_parents(
    arbre: ast.AST,
) -> None:
    """Ajoute temporairement les références parent aux nœuds AST."""

    for parent in ast.walk(arbre):
        for enfant in ast.iter_child_nodes(parent):
            try:
                setattr(
                    enfant,
                    "_parent",
                    parent,
                )
            except Exception:
                pass


# ============================================================================
# GRAVITE
# ============================================================================

def _gravite(
    categorie: str,
) -> str:

    if categorie == "SYNTAXE":
        return "CRITIQUE"

    if categorie in {
        "DEPENDANCE",
        "PERMISSION",
        "CONNEXION",
        "SYSTEME",
    }:
        return "HAUTE"

    if categorie in {
        "REFERENCE",
        "FICHIER",
        "EXECUTION",
        "TYPE",
        "PERFORMANCE",
    }:
        return "MOYENNE"

    return "BASSE"


# ============================================================================
# CAUSE
# ============================================================================

def _decrire_cause(
    classe: Optional[str],
    categorie: str,
    message: str,
) -> str:

    if classe:

        if classe == "ReadTimeout":
            return (
                "Délai de réponse dépassé lors d'une "
                "communication avec un service."
            )

        if classe == "Timeout":
            return (
                "Délai d'exécution ou de réponse dépassé."
            )

        if classe == "ConnectionError":
            return (
                "Connexion impossible vers un service "
                "externe ou local."
            )

        if classe == "ConnectionRefusedError":
            return (
                "Connexion refusée : le service cible "
                "semble indisponible."
            )

        if classe == "ModuleNotFoundError":
            return (
                "Dépendance ou module Python introuvable."
            )

        if classe == "ImportError":
            return (
                "Import Python impossible."
            )

        if classe == "PermissionError":
            return (
                "Accès refusé à une ressource."
            )

        if classe == "TypeError":
            return (
                "Type ou argument incompatible avec "
                "l'appel effectué."
            )

        if classe == "AttributeError":
            return (
                "Attribut ou méthode demandé absent de l'objet."
            )

        if classe == "NameError":
            return (
                "Nom ou variable utilisé mais non défini."
            )

        if classe in {
            "SyntaxError",
            "IndentationError",
        }:
            return (
                "Erreur de syntaxe ou d'indentation Python."
            )

        if classe == "FileNotFoundError":
            return (
                "Fichier ou ressource introuvable."
            )

        if classe == "JSONDecodeError":
            return (
                "Données JSON invalides ou impossibles à décoder."
            )

        return f"Erreur {classe}."

    texte = message.lower()

    for categorie_cible, mots in CATEGORY_KEYWORDS.items():

        if any(
            mot in texte
            for mot in mots
        ):
            descriptions = {
                "PERFORMANCE": (
                    "Délai de réponse ou d'exécution dépassé."
                ),
                "CONNEXION": (
                    "Problème de communication avec un service."
                ),
                "DEPENDANCE": (
                    "Dépendance ou module Python potentiellement absent."
                ),
                "FICHIER": (
                    "Ressource ou fichier potentiellement introuvable."
                ),
                "PERMISSION": (
                    "Accès refusé à une ressource."
                ),
                "DONNEE": (
                    "Données potentiellement invalides."
                ),
            }

            return descriptions.get(
                categorie_cible,
                "Problème détecté.",
            )

    return "Erreur non classifiée."


# ============================================================================
# CLASSIFICATION TEXTUELLE
# ============================================================================

def _classifier_message(
    message: str,
) -> str:

    classe = _extraire_classe_erreur(message)

    if classe:
        return ERROR_CLASSES.get(
            classe,
            "INCONNUE",
        )

    texte = message.lower()

    for categorie, mots in CATEGORY_KEYWORDS.items():
        if any(
            mot in texte
            for mot in mots
        ):
            return categorie

    return "INCONNUE"


# ============================================================================
# RECENCE
# ============================================================================

def _extraire_date(
    message: str,
) -> Optional[datetime]:
    """
    Cherche une date dans les logs.

    Formats supportés :
        2026-09-17 03:10:15
        2026-09-17T03:10:15
    """

    patterns = [
        r"\b"
        r"(20\d{2}-\d{2}-\d{2}"
        r"[ T]"
        r"\d{2}:\d{2}:\d{2}"
        r"(?:[.,]\d+)?)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            message,
        )

        if not match:
            continue

        valeur = match.group(1)

        try:
            valeur = valeur.replace(",", ".")

            date = datetime.fromisoformat(
                valeur
            )

            if date.tzinfo is None:
                date = date.replace(
                    tzinfo=timezone.utc
                )

            return date

        except ValueError:
            continue

    return None


def _est_recente(
    message: str,
    heures: int = 24,
) -> bool:

    date = _extraire_date(message)

    if date is None:
        return False

    maintenant = datetime.now(
        timezone.utc
    )

    age = maintenant - date

    return age.total_seconds() >= 0 and age.total_seconds() <= (
        heures * 3600
    )


# ============================================================================
# CONFIANCE
# ============================================================================

def _calculer_confiance(
    classe: Optional[str],
    fichier: Optional[str],
    ligne: Optional[int],
    fonction: Optional[str],
    recente: bool,
    occurrences: int = 1,
) -> float:

    score = 0.25

    if classe:
        score += 0.20

    if fichier:
        score += 0.15

    if ligne is not None:
        score += 0.10

    if fonction:
        score += 0.10

    if recente:
        score += 0.05

    # La répétition renforce modérément la confiance.
    if occurrences > 1:
        score += min(
            0.10,
            0.02 * (occurrences - 1),
        )

    return round(
        min(score, 0.95),
        3,
    )


# ============================================================================
# STATUT
# ============================================================================

def _determiner_statut(
    confiance: float,
    recente: bool,
    occurrences: int,
) -> str:

    if not recente:
        return "HISTORIQUE"

    if occurrences >= 3 and confiance >= 0.70:
        return "RECURRENT"

    if confiance >= 0.80:
        return "CONFIRME"

    if confiance >= 0.60:
        return "PROBABLE"

    return "INCERTAIN"


# ============================================================================
# ANALYSE D'UNE ERREUR
# ============================================================================

def analyser_erreur(
    erreur: str,
    occurrences: int = 1,
) -> HypotheseDiagnostic:

    classe = _extraire_classe_erreur(
        erreur
    )

    categorie = (
        ERROR_CLASSES.get(
            classe,
            "INCONNUE",
        )
        if classe
        else _classifier_message(erreur)
    )

    fichier_brut = _extraire_fichier(
        erreur
    )

    fichier = _normaliser_cible(
        fichier_brut
    )

    ligne = _extraire_ligne(
        erreur
    )

    fonction = _extraire_fonction_traceback(
        erreur
    )

    if fonction is None and fichier and ligne:
        fonction = _chercher_fonction(
            fichier,
            ligne,
        )

    recente = _est_recente(
        erreur
    )

    confiance = _calculer_confiance(
        classe=classe,
        fichier=fichier,
        ligne=ligne,
        fonction=fonction,
        recente=recente,
        occurrences=occurrences,
    )

    statut = _determiner_statut(
        confiance=confiance,
        recente=recente,
        occurrences=occurrences,
    )

    preuves = [
        erreur
    ]

    if classe:
        preuves.append(
            f"Classe détectée : {classe}"
        )

    if fichier:
        preuves.append(
            f"Fichier détecté : {fichier}"
        )

    if ligne is not None:
        preuves.append(
            f"Ligne détectée : {ligne}"
        )

    if fonction:
        preuves.append(
            f"Fonction détectée : {fonction}"
        )

    if recente:
        preuves.append(
            "Événement considéré comme récent."
        )
    else:
        preuves.append(
            "Événement non confirmé comme récent."
        )

    if occurrences > 1:
        preuves.append(
            f"Occurrences : {occurrences}"
        )

    return HypotheseDiagnostic(
        categorie=categorie,
        cause=_decrire_cause(
            classe,
            categorie,
            erreur,
        ),
        cible=fichier,
        fonction=fonction,
        preuves=preuves,
        confiance=confiance,
        gravite=_gravite(
            categorie
        ),
        occurrences=occurrences,
        statut=statut,
        recente=recente,
    )


# ============================================================================
# CLE DE REGROUPEMENT
# ============================================================================

def _normaliser_cause(
    cause: str,
) -> str:

    texte = cause.lower()

    # Supprimer les détails variables.
    texte = re.sub(
        r"\d+",
        "#",
        texte,
    )

    texte = re.sub(
        r"\s+",
        " ",
        texte,
    ).strip()

    return texte


def _cle_regroupement(
    hypothese: HypotheseDiagnostic,
) -> tuple[str, str, str, str]:

    return (
        hypothese.categorie,
        _normaliser_cause(
            hypothese.cause
        ),
        hypothese.cible or "",
        hypothese.fonction or "",
    )


# ============================================================================
# REGROUPEMENT
# ============================================================================

def _regrouper_hypotheses(
    hypotheses: list[HypotheseDiagnostic],
) -> list[HypotheseDiagnostic]:

    groupes: dict[
        tuple[str, str, str, str],
        HypotheseDiagnostic,
    ] = {}

    occurrences: dict[
        tuple[str, str, str, str],
        int,
    ] = defaultdict(int)

    recentes: dict[
        tuple[str, str, str, str],
        bool,
    ] = defaultdict(bool)

    for hypothese in hypotheses:

        cle = _cle_regroupement(
            hypothese
        )

        occurrences[cle] += 1

        if hypothese.recente:
            recentes[cle] = True

        if cle not in groupes:

            groupes[cle] = hypothese

            continue

        existante = groupes[cle]

        # Fusion des preuves.
        for preuve in hypothese.preuves:

            if preuve not in existante.preuves:
                existante.preuves.append(
                    preuve
                )

        # Meilleure localisation.
        if (
            existante.cible is None
            and hypothese.cible is not None
        ):
            existante.cible = hypothese.cible

        if (
            existante.fonction is None
            and hypothese.fonction is not None
        ):
            existante.fonction = hypothese.fonction

        # Gravité maximale.
        ordre = {
            "CRITIQUE": 0,
            "HAUTE": 1,
            "MOYENNE": 2,
            "BASSE": 3,
            "INCONNUE": 4,
        }

        if ordre.get(
            hypothese.gravite,
            99,
        ) < ordre.get(
            existante.gravite,
            99,
        ):
            existante.gravite = hypothese.gravite

    resultat = []

    for cle, hypothese in groupes.items():

        nombre = occurrences[cle]

        hypothese.occurrences = nombre

        hypothese.recente = recentes[cle]

        # Recalcul avec le nombre réel d'occurrences.
        classe = None

        # On ne reconstruit pas artificiellement la classe.
        # On renforce seulement légèrement la confiance.
        hypothese.confiance = min(
            0.95,
            round(
                hypothese.confiance
                + min(
                    0.10,
                    max(0, nombre - 1) * 0.02,
                ),
                3,
            ),
        )

        hypothese.statut = _determiner_statut(
            confiance=hypothese.confiance,
            recente=hypothese.recente,
            occurrences=nombre,
        )

        if nombre > 1:
            hypothese.preuves.append(
                f"Occurrences regroupées : {nombre}"
            )

        resultat.append(
            hypothese
        )

    ordre_gravite = {
        "CRITIQUE": 0,
        "HAUTE": 1,
        "MOYENNE": 2,
        "BASSE": 3,
        "INCONNUE": 4,
    }

    # Les événements récents passent avant les historiques.
    resultat.sort(
        key=lambda h: (
            0 if h.recente else 1,
            ordre_gravite.get(
                h.gravite,
                99,
            ),
            -h.confiance,
            -h.occurrences,
        )
    )

    return resultat


# ============================================================================
# ANALYSE DES WARNINGS
# ============================================================================

def _analyser_warnings(
    warnings: list[str],
) -> list[HypotheseDiagnostic]:

    hypotheses = []

    for warning in warnings:

        categorie = _classifier_message(
            warning
        )

        if categorie == "INCONNUE":
            continue

        hypotheses.append(
            HypotheseDiagnostic(
                categorie=categorie,
                cause=_decrire_cause(
                    None,
                    categorie,
                    warning,
                ),
                cible=_normaliser_cible(
                    _extraire_fichier(warning)
                ),
                fonction=None,
                preuves=[
                    warning,
                    "Source : warning",
                ],
                confiance=0.35,
                gravite="BASSE",
                occurrences=1,
                statut="INCERTAIN",
                recente=_est_recente(
                    warning
                ),
            )
        )

    return hypotheses


# ============================================================================
# NIVEAU GLOBAL
# ============================================================================

def _niveau_global(
    hypotheses: list[HypotheseDiagnostic],
) -> str:

    if not hypotheses:
        return "AUCUN_PROBLEME"

    recentes = [
        h
        for h in hypotheses
        if h.recente
    ]

    # Ne jamais déclarer CRITIQUE uniquement
    # sur la base d'une erreur historique.
    critiques_recentes = [
        h
        for h in recentes
        if h.gravite == "CRITIQUE"
    ]

    if critiques_recentes:
        return "CRITIQUE"

    if any(
        h.statut == "CONFIRME"
        for h in recentes
    ):
        return "CONFIRME"

    if any(
        h.statut == "RECURRENT"
        for h in recentes
    ):
        return "RECURRENT"

    if any(
        h.statut == "PROBABLE"
        for h in recentes
    ):
        return "PROBABLE"

    if recentes:
        return "INCERTAIN"

    return "HISTORIQUE"


# ============================================================================
# DIAGNOSTIC PRINCIPAL
# ============================================================================

def diagnostiquer(
    observation: RapportObservation,
) -> RapportDiagnostic:

    hypotheses_brutes: list[
        HypotheseDiagnostic
    ] = []

    fichiers: list[str] = []

    # ------------------------------------------------------------------------
    # Fichiers déjà identifiés par l'observateur.
    # ------------------------------------------------------------------------

    for fichier in observation.fichiers_concernes:

        cible = _normaliser_cible(
            fichier
        )

        if cible and cible not in fichiers:
            fichiers.append(cible)

    # ------------------------------------------------------------------------
    # Erreurs.
    # ------------------------------------------------------------------------

    for erreur in observation.erreurs:

        hypothese = analyser_erreur(
            erreur
        )

        if (
            hypothese.cible
            and hypothese.cible not in fichiers
        ):
            fichiers.append(
                hypothese.cible
            )

        hypotheses_brutes.append(
            hypothese
        )

    # ------------------------------------------------------------------------
    # Warnings exploitables.
    # ------------------------------------------------------------------------

    hypotheses_brutes.extend(
        _analyser_warnings(
            observation.warnings
        )
    )

    # ------------------------------------------------------------------------
    # Regroupement.
    # ------------------------------------------------------------------------

    hypotheses = _regrouper_hypotheses(
        hypotheses_brutes
    )

    # ------------------------------------------------------------------------
    # Niveau global.
    # ------------------------------------------------------------------------

    niveau = _niveau_global(
        hypotheses
    )

    if not hypotheses:

        message = (
            "Aucun problème exploitable détecté."
        )

    elif niveau == "HISTORIQUE":

        message = (
            f"{len(observation.erreurs)} erreur(s) et "
            f"{len(observation.warnings)} warning(s) analysés. "
            "Les problèmes détectés ne sont pas confirmés comme récents."
        )

    else:

        message = (
            f"{len(observation.erreurs)} erreur(s) et "
            f"{len(observation.warnings)} warning(s) analysés, "
            f"{len(hypotheses)} problème(s) regroupé(s). "
            f"Niveau actuel : {niveau}."
        )

    return RapportDiagnostic(
        ok=True,
        niveau=niveau,
        hypotheses=hypotheses,
        fichiers_candidats=fichiers,
        erreurs_analysees=len(
            observation.erreurs
        ),
        warnings_analyses=len(
            observation.warnings
        ),
        message=message,
    )


# ============================================================================
# API JIBI
# ============================================================================

def diagnostiquer_jibi() -> RapportDiagnostic:
    """Observe puis diagnostique JIBI."""

    from .observateur import observer

    return diagnostiquer(
        observer()
    )


# ============================================================================
# RESUME
# ============================================================================

def resume_diagnostic(
    rapport: RapportDiagnostic,
) -> str:

    lignes = [
        "=== DIAGNOSTIC JIBI ===",
        f"Niveau : {rapport.niveau}",
        f"Message : {rapport.message}",
        f"Erreurs analysées : {rapport.erreurs_analysees}",
        f"Warnings analysés : {rapport.warnings_analyses}",
        f"Problèmes regroupés : {len(rapport.hypotheses)}",
        "",
    ]

    for index, hypothese in enumerate(
        rapport.hypotheses,
        start=1,
    ):

        lignes.extend(
            [
                (
                    f"[{index}] "
                    f"{hypothese.categorie}"
                ),
                f"Cause : {hypothese.cause}",
                (
                    "Cible : "
                    f"{hypothese.cible or 'inconnue'}"
                ),
                (
                    "Fonction : "
                    f"{hypothese.fonction or 'inconnue'}"
                ),
                (
                    "Confiance : "
                    f"{hypothese.confiance:.0%}"
                ),
                (
                    "Gravité : "
                    f"{hypothese.gravite}"
                ),
                (
                    "Statut : "
                    f"{hypothese.statut}"
                ),
                (
                    "Récent : "
                    f"{'oui' if hypothese.recente else 'non'}"
                ),
                (
                    "Occurrences : "
                    f"{hypothese.occurrences}"
                ),
                (
                    "Preuves : "
                    f"{len(hypothese.preuves)}"
                ),
                "",
            ]
        )

    return "\n".join(lignes)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "HypotheseDiagnostic",
    "RapportDiagnostic",
    "analyser_erreur",
    "diagnostiquer",
    "diagnostiquer_jibi",
    "resume_diagnostic",
]