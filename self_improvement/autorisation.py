"""
JIBI — Autorisation humaine des modifications
==============================================

Responsabilité :
    - enregistrer les décisions humaines ;
    - vérifier une autorisation ;
    - lier une autorisation à une proposition immuable ;
    - conserver une trace d'audit ;
    - empêcher la réutilisation d'une autorisation sur une proposition modifiée.

Important :
    Ce module NE modifie jamais directement les fichiers de production.

Flux attendu :
    proposition
        ↓
    analyse risque
        ↓
    autorisation humaine
        ↓
    vérification intégrité
        ↓
    orchestrateur
        ↓
    backup / application / tests / rollback
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Imports JIBI
# ---------------------------------------------------------------------------

try:
    from core.config import WORKSPACE_DIR
except Exception:
    WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"

try:
    from .propositions import (
        charger_proposition,
        verifier_integrite_proposition,
    )
except Exception:
    from self_improvement.propositions import (
        charger_proposition,
        verifier_integrite_proposition,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKSPACE_DIR = Path(WORKSPACE_DIR).resolve()

DECISIONS_DIR = WORKSPACE_DIR / "jibi_lab" / "decisions_humaines"

DECISIONS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

JOURNAL_DECISIONS = DECISIONS_DIR / "decisions.jsonl"

ANCIEN_JOURNAL = DECISIONS_DIR / "decisions.json"


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ACTION_AUTORISER = "autoriser"
ACTION_REJETER = "rejeter"

STATUT_EN_ATTENTE = "en_attente"
STATUT_AUTORISE = "autorise"
STATUT_REJETE = "rejete"
STATUT_APPLIQUE = "applique"
STATUT_INVALIDE = "invalide"


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    """Retourne un timestamp UTC ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def _normaliser_id(proposition_id: str) -> str:
    """Nettoie et valide un identifiant de proposition."""
    valeur = str(proposition_id or "").strip()

    if not valeur:
        raise ValueError("Identifiant de proposition vide.")

    if not re.fullmatch(r"[A-Za-z0-9_-]{4,128}", valeur):
        raise ValueError(
            f"Identifiant de proposition invalide : {proposition_id!r}"
        )

    return valeur


def _chemin_decision(proposition_id: str) -> Path:
    """Retourne le fichier d'audit dédié à une proposition."""
    pid = _normaliser_id(proposition_id)

    chemin = (DECISIONS_DIR / f"{pid}.json").resolve()

    try:
        chemin.relative_to(DECISIONS_DIR)
    except ValueError:
        raise ValueError("Chemin de décision hors du dossier autorisé.")

    return chemin


def _ecrire_json_atomique(
    chemin: Path,
    donnees: dict[str, Any],
) -> None:
    """
    Écrit un JSON de manière atomique.

    On écrit d'abord dans un fichier temporaire puis on remplace
    l'ancien fichier.
    """
    chemin = chemin.resolve()

    try:
        chemin.relative_to(DECISIONS_DIR)
    except ValueError:
        raise ValueError(
            "Écriture hors du dossier de décisions interdite."
        )

    chemin.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, nom_temp = tempfile.mkstemp(
        prefix=f".{chemin.stem}.",
        suffix=".tmp",
        dir=str(chemin.parent),
        text=True,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as fichier:
            json.dump(
                donnees,
                fichier,
                ensure_ascii=False,
                indent=2,
            )

            fichier.flush()
            os.fsync(fichier.fileno())

        os.replace(
            nom_temp,
            chemin,
        )

    finally:
        try:
            Path(nom_temp).unlink(
                missing_ok=True
            )
        except Exception:
            pass


def _lire_json(
    chemin: Path,
) -> dict[str, Any] | None:
    """Lit un fichier JSON de décision."""
    if not chemin.exists():
        return None

    try:
        with chemin.open(
            "r",
            encoding="utf-8",
        ) as fichier:
            contenu = json.load(fichier)

        if not isinstance(contenu, dict):
            return None

        return contenu

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Extraction de l'identité immuable d'une proposition
# ---------------------------------------------------------------------------

def _identite_proposition(
    proposition_id: str,
) -> dict[str, Any] | None:
    """
    Récupère les éléments qui doivent être liés à l'autorisation.

    Une autorisation ne porte donc pas seulement sur l'ID :
        - ID ;
        - fichier ;
        - SHA source ;
        - SHA nouveau ;
        - niveau de risque ;
        - diff.
    """
    pid = _normaliser_id(
        proposition_id
    )

    proposition = charger_proposition(
        pid
    )

    if not proposition:
        return None

    return {
        "proposition_id": pid,
        "fichier": str(
            proposition.get(
                "fichier",
                "",
            )
        ),
        "source_sha256": str(
            proposition.get(
                "source_sha256",
                "",
            )
        ),
        "nouveau_sha256": str(
            proposition.get(
                "nouveau_sha256",
                "",
            )
        ),
        "niveau_risque": str(
            proposition.get(
                "niveau_risque",
                "",
            )
            or proposition.get(
                "risque",
                "",
            )
        ),
        "diff": str(
            proposition.get(
                "diff",
                "",
            )
        ),
    }


# ---------------------------------------------------------------------------
# Vérification d'intégrité
# ---------------------------------------------------------------------------

def verifier_integrite_autorisation(
    decision: dict[str, Any],
) -> dict[str, Any]:
    """
    Vérifie que l'autorisation correspond toujours à la proposition
    actuellement enregistrée.

    Une autorisation devient invalide si :
        - la proposition n'existe plus ;
        - son fichier change ;
        - le SHA source change ;
        - le SHA de la solution change ;
        - l'intégrité de la proposition échoue.
    """
    if not isinstance(
        decision,
        dict,
    ):
        return {
            "ok": False,
            "valide": False,
            "message": "Décision invalide.",
        }

    pid = decision.get(
        "proposition_id"
    )

    if not pid:
        return {
            "ok": False,
            "valide": False,
            "message": "Identifiant de proposition absent.",
        }

    try:
        pid = _normaliser_id(pid)

    except ValueError as exc:
        return {
            "ok": False,
            "valide": False,
            "message": str(exc),
        }

    proposition = charger_proposition(
        pid
    )

    if not proposition:
        return {
            "ok": False,
            "valide": False,
            "message": f"Proposition introuvable : {pid}",
        }

    # ------------------------------------------------------------------
    # CORRECTION IMPORTANTE :
    # verifier_integrite_proposition() attend le dictionnaire complet
    # de proposition, pas son identifiant.
    # ------------------------------------------------------------------
    try:
        integrite = verifier_integrite_proposition(
            proposition
        )

    except Exception as exc:
        return {
            "ok": False,
            "valide": False,
            "message": f"Erreur de vérification : {exc}",
        }

    if isinstance(
        integrite,
        dict,
    ):
        integrite_ok = bool(
            integrite.get(
                "ok",
                False,
            )
            and integrite.get(
                "valide",
                integrite.get(
                    "ok",
                    False,
                ),
            )
        )

    else:
        integrite_ok = bool(
            integrite
        )

    if not integrite_ok:
        return {
            "ok": False,
            "valide": False,
            "message": (
                "L'intégrité de la proposition est invalide."
            ),
            "details": integrite,
        }

    identite_actuelle = _identite_proposition(
        pid
    )

    if identite_actuelle is None:
        return {
            "ok": False,
            "valide": False,
            "message": (
                "Impossible de reconstruire "
                "l'identité de la proposition."
            ),
        }

    erreurs: list[str] = []

    champs = (
        "fichier",
        "source_sha256",
        "nouveau_sha256",
        "niveau_risque",
    )

    for champ in champs:
        valeur_decision = str(
            decision.get(
                champ,
                "",
            )
        )

        valeur_actuelle = str(
            identite_actuelle.get(
                champ,
                "",
            )
        )

        if not valeur_decision:
            erreurs.append(
                "Champ de sécurité absent "
                f"dans l'autorisation : {champ}"
            )
            continue

        if valeur_decision != valeur_actuelle:
            erreurs.append(
                f"Le champ {champ} "
                "ne correspond plus à la proposition."
            )

    # Vérification supplémentaire du diff.
    diff_actuel = str(
        identite_actuelle.get(
            "diff",
            "",
        )
    )

    diff_decision_sha = str(
        decision.get(
            "diff_sha256",
            "",
        )
    )

    if not diff_decision_sha:
        erreurs.append(
            "Empreinte du diff absente dans l'autorisation."
        )

    elif _sha256(diff_actuel) != diff_decision_sha:
        erreurs.append(
            "Le diff de la proposition a changé."
        )

    if decision.get("approuve") is True:
        confirmation = str(
            decision.get("confirmation", "")
        ).strip()

        if decision.get("confirmation_explicite") is not True:
            erreurs.append(
                "La preuve de confirmation humaine est absente."
            )

        match_confirmation = re.fullmatch(
            r"J(?:['’])AUTORISE\s+"
            r"([A-Za-z0-9][A-Za-z0-9_-]{3,127})",
            confirmation,
            flags=re.IGNORECASE,
        )

        if not match_confirmation:
            erreurs.append(
                "La confirmation humaine enregistrée est invalide."
            )
        elif match_confirmation.group(1).lower() != pid.lower():
            erreurs.append(
                "La confirmation humaine ne correspond pas "
                "à la proposition."
            )

        confirmation_sha = str(
            decision.get("confirmation_sha256", "")
        )

        if not confirmation_sha:
            erreurs.append(
                "Empreinte de la confirmation absente."
            )
        elif _sha256(confirmation) != confirmation_sha:
            erreurs.append(
                "La confirmation humaine a été modifiée."
            )

    if erreurs:
        return {
            "ok": False,
            "valide": False,
            "message": "Autorisation non valide.",
            "erreurs": erreurs,
            "identite_decision": {
                champ: decision.get(champ)
                for champ in champs
            },
            "identite_actuelle": identite_actuelle,
        }

    return {
        "ok": True,
        "valide": True,
        "message": (
            "Autorisation liée à une proposition intègre."
        ),
        "identite": identite_actuelle,
    }


# ---------------------------------------------------------------------------
# Enregistrement d'une décision
# ---------------------------------------------------------------------------

def _sha256(
    texte: str,
) -> str:
    """SHA-256 d'un texte UTF-8."""
    import hashlib

    return hashlib.sha256(
        str(texte).encode("utf-8")
    ).hexdigest()


def _creer_decision(
    proposition_id: str,
    approuve: bool,
    commentaire: str = "",
    utilisateur: str = "humain",
    action: str | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """
    Crée une décision humaine liée à l'état exact de la proposition.
    """
    pid = _normaliser_id(
        proposition_id
    )

    proposition = charger_proposition(pid)
    if not proposition:
        raise ValueError(
            "Impossible d'autoriser une proposition "
            f"inexistante : {pid}"
        )

    verification_proposition = verifier_integrite_proposition(
        proposition
    )
    if isinstance(verification_proposition, dict):
        verification_ok = bool(
            verification_proposition.get(
                "ok",
                False,
            )
            and verification_proposition.get(
                "valide",
                verification_proposition.get("ok", False),
            )
        )
    else:
        verification_ok = bool(verification_proposition)

    if not verification_ok:
        raise ValueError(
            "Impossible d'enregistrer une décision : "
            "l'intégrité de la proposition est invalide. "
            f"Détails : {verification_proposition}"
        )

    identite = _identite_proposition(pid)

    if identite is None:
        raise ValueError(
            "Impossible de reconstruire l'identité de la proposition : "
            f"{pid}"
        )

    if action is None:
        action = (
            ACTION_AUTORISER
            if approuve
            else ACTION_REJETER
        )

    decision = {
        "version": 2,
        "proposition_id": pid,
        "action": action,
        "approuve": bool(approuve),
        "statut": (
            STATUT_AUTORISE
            if approuve
            else STATUT_REJETE
        ),
        "commentaire": str(
            commentaire or ""
        ).strip(),
        "utilisateur": str(
            utilisateur or "humain"
        ),
        "confirmation_explicite": bool(
            approuve and str(confirmation or "").strip()
        ),
        "confirmation": (
            str(confirmation or "").strip()
            if approuve
            else ""
        ),
        "confirmation_sha256": (
            _sha256(str(confirmation or "").strip())
            if approuve and str(confirmation or "").strip()
            else ""
        ),
        "date": _timestamp(),

        "fichier": identite[
            "fichier"
        ],

        "source_sha256": identite[
            "source_sha256"
        ],

        "nouveau_sha256": identite[
            "nouveau_sha256"
        ],

        "niveau_risque": identite[
            "niveau_risque"
        ],

        "diff_sha256": _sha256(
            identite["diff"]
        ),

        "appliquee_le": None,
        "invalidee_le": None,
        "invalidation_raison": None,
    }

    chemin = _chemin_decision(
        pid
    )

    _ecrire_json_atomique(
        chemin,
        decision,
    )

    return decision


# ---------------------------------------------------------------------------
# API publique — autorisation
# ---------------------------------------------------------------------------

def valider_proposition(
    proposition_id: str,
    commentaire: str = "",
    utilisateur: str = "humain",
    confirmation: str = "",
) -> dict[str, Any]:
    """
    Autorise une proposition.

    Cette fonction n'applique PAS la modification.
    """
    try:
        confirmation_normalisee = str(
            confirmation or ""
        ).strip()

        match = re.fullmatch(
            r"J(?:['’])AUTORISE\s+"
            r"([A-Za-z0-9][A-Za-z0-9_-]{3,127})",
            confirmation_normalisee,
            flags=re.IGNORECASE,
        )

        if not match:
            return {
                "ok": False,
                "valide": False,
                "message": (
                    "Autorisation refusée : confirmation humaine "
                    "explicite obligatoire sous la forme "
                    "« J'AUTORISE <id> »."
                ),
            }

        pid_demande = _normaliser_id(proposition_id)
        pid_confirme = match.group(1)

        if pid_confirme.lower() != pid_demande.lower():
            return {
                "ok": False,
                "valide": False,
                "message": (
                    "Autorisation refusée : l'identifiant confirmé "
                    "ne correspond pas à la proposition demandée."
                ),
            }

        decision = _creer_decision(
            proposition_id=pid_demande,
            approuve=True,
            commentaire=commentaire,
            utilisateur=utilisateur,
            action=ACTION_AUTORISER,
            confirmation=confirmation_normalisee,
        )

        return {
            "ok": True,
            "valide": True,
            "decision": decision,
            "message": (
                f"Proposition {proposition_id} autorisée."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "valide": False,
            "message": str(exc),
        }


def autoriser_proposition(
    proposition_id: str,
    commentaire: str = "",
    utilisateur: str = "humain",
    confirmation: str = "",
) -> dict[str, Any]:
    """Alias explicite de valider_proposition."""
    return valider_proposition(
        proposition_id,
        commentaire,
        utilisateur,
        confirmation,
    )


def rejeter_proposition(
    proposition_id: str,
    commentaire: str = "",
    utilisateur: str = "humain",
) -> dict[str, Any]:
    """Enregistre un rejet humain."""
    try:
        decision = _creer_decision(
            proposition_id=proposition_id,
            approuve=False,
            commentaire=commentaire,
            utilisateur=utilisateur,
            action=ACTION_REJETER,
        )

        return {
            "ok": True,
            "valide": True,
            "decision": decision,
            "message": (
                f"Proposition {proposition_id} rejetée."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "valide": False,
            "message": str(exc),
        }


# ---------------------------------------------------------------------------
# Vérification d'une autorisation
# ---------------------------------------------------------------------------

def autorisation_valide(
    proposition_id: str,
    action: str = ACTION_AUTORISER,
) -> bool:
    """
    Retourne True uniquement si :
        1. une décision existe ;
        2. elle autorise l'action demandée ;
        3. elle n'est pas rejetée ;
        4. son identité correspond toujours à la proposition ;
        5. l'intégrité de la proposition est valide.
    """
    try:
        pid = _normaliser_id(
            proposition_id
        )

    except ValueError:
        return False

    decision = _lire_json(
        _chemin_decision(pid)
    )

    if not decision:
        return False

    if decision.get(
        "approuve"
    ) is not True:
        return False

    if decision.get(
        "action"
    ) != action:
        return False

    if decision.get(
        "statut"
    ) not in (
        STATUT_AUTORISE,
        STATUT_APPLIQUE,
    ):
        return False

    verification = verifier_integrite_autorisation(
        decision
    )

    if not verification.get(
        "valide",
        False,
    ):
        return False

    return True


def verifier_autorisation(
    proposition_id: str,
) -> dict[str, Any]:
    """
    Version détaillée de autorisation_valide().
    """
    try:
        pid = _normaliser_id(
            proposition_id
        )

    except ValueError as exc:
        return {
            "ok": False,
            "valide": False,
            "message": str(exc),
        }

    decision = _lire_json(
        _chemin_decision(pid)
    )

    if not decision:
        return {
            "ok": False,
            "valide": False,
            "autorisee": False,
            "message": (
                f"Aucune décision enregistrée pour {pid}."
            ),
        }

    if decision.get(
        "approuve"
    ) is not True:
        return {
            "ok": True,
            "valide": True,
            "autorisee": False,
            "decision": decision,
            "message": "La proposition n'est pas autorisée.",
        }

    integrite = verifier_integrite_autorisation(
        decision
    )

    if not integrite.get(
        "valide",
        False,
    ):
        return {
            "ok": False,
            "valide": False,
            "autorisee": False,
            "decision": decision,
            "integrite": integrite,
            "message": (
                "Autorisation trouvée mais devenue invalide."
            ),
        }

    return {
        "ok": True,
        "valide": True,
        "autorisee": True,
        "decision": decision,
        "integrite": integrite,
        "message": "Autorisation valide.",
    }


# ---------------------------------------------------------------------------
# Cycle de vie
# ---------------------------------------------------------------------------

def marquer_appliquee(
    proposition_id: str,
) -> dict[str, Any]:
    """
    Marque une autorisation comme appliquée.

    Cette fonction ne modifie aucun fichier.
    """
    try:
        pid = _normaliser_id(
            proposition_id
        )

        chemin = _chemin_decision(
            pid
        )

        decision = _lire_json(
            chemin
        )

        if not decision:
            return {
                "ok": False,
                "message": (
                    f"Aucune décision pour {pid}."
                ),
            }

        verification = verifier_integrite_autorisation(
            decision
        )

        if not verification.get(
            "valide",
            False,
        ):
            return {
                "ok": False,
                "message": (
                    "Impossible de marquer la proposition "
                    "comme appliquée : autorisation invalide."
                ),
                "details": verification,
            }

        decision["statut"] = STATUT_APPLIQUE
        decision["appliquee_le"] = _timestamp()

        _ecrire_json_atomique(
            chemin,
            decision,
        )

        return {
            "ok": True,
            "message": (
                f"Proposition {pid} marquée comme appliquée."
            ),
            "decision": decision,
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": str(exc),
        }


# ---------------------------------------------------------------------------
# Examen
# ---------------------------------------------------------------------------

def examiner_proposition(
    proposition_id: str,
) -> dict[str, Any]:
    """
    Retourne l'état complet d'une proposition et de son autorisation.
    """
    try:
        pid = _normaliser_id(
            proposition_id
        )

    except ValueError as exc:
        return {
            "ok": False,
            "message": str(exc),
        }

    proposition = charger_proposition(
        pid
    )

    if not proposition:
        return {
            "ok": False,
            "message": (
                f"Proposition introuvable : {pid}"
            ),
        }

    decision = _lire_json(
        _chemin_decision(pid)
    )

    resultat = {
        "ok": True,
        "proposition_id": pid,
        "proposition": proposition,
        "decision": decision,
        "autorisation": None,
        "integrite": None,
    }

    if decision:
        integrite = verifier_integrite_autorisation(
            decision
        )

        resultat["integrite"] = integrite

        resultat["autorisation"] = bool(
            decision.get(
                "approuve"
            ) is True
            and integrite.get(
                "valide",
                False,
            )
        )

    return resultat


# ---------------------------------------------------------------------------
# Recherche des propositions en attente
# ---------------------------------------------------------------------------

def lister_propositions_en_attente() -> list[dict[str, Any]]:
    """
    Liste les propositions qui n'ont pas encore reçu de décision valide.
    """
    try:
        from .propositions import lister_propositions

    except Exception:
        from self_improvement.propositions import lister_propositions

    resultat: list[dict[str, Any]] = []

    try:
        propositions = lister_propositions()

    except Exception:
        propositions = []

    for proposition in propositions:
        if not isinstance(
            proposition,
            dict,
        ):
            continue

        pid = proposition.get(
            "id"
        ) or proposition.get(
            "proposition_id"
        )

        if not pid:
            continue

        decision = _lire_json(
            _chemin_decision(
                str(pid)
            )
        )

        if decision is None:
            resultat.append(
                proposition
            )
            continue

        if decision.get(
            "approuve"
        ) is True:
            verification = verifier_integrite_autorisation(
                decision
            )

            if not verification.get(
                "valide",
                False,
            ):
                resultat.append(
                    proposition
                )

    return resultat


# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------

def obtenir_statistiques() -> dict[str, Any]:
    """Retourne des statistiques sur les décisions humaines."""
    stats = {
        "total": 0,
        "autorisees": 0,
        "rejetees": 0,
        "appliquees": 0,
        "invalides": 0,
        "en_attente": 0,
    }

    try:
        for chemin in DECISIONS_DIR.glob(
            "*.json"
        ):
            if chemin.name == ANCIEN_JOURNAL.name:
                continue

            decision = _lire_json(
                chemin
            )

            if not decision:
                continue

            stats["total"] += 1

            statut = decision.get(
                "statut"
            )

            if statut == STATUT_AUTORISE:
                stats["autorisees"] += 1

            elif statut == STATUT_REJETE:
                stats["rejetees"] += 1

            elif statut == STATUT_APPLIQUE:
                stats["appliquees"] += 1

            verification = verifier_integrite_autorisation(
                decision
            )

            if not verification.get(
                "valide",
                False,
            ):
                stats["invalides"] += 1

        stats["en_attente"] = len(
            lister_propositions_en_attente()
        )

    except Exception:
        pass

    return stats


# ---------------------------------------------------------------------------
# Formatage
# ---------------------------------------------------------------------------

def formater_decision(
    decision: dict[str, Any] | None,
) -> str:
    """Formate une décision pour l'interface JIBI."""
    if not decision:
        return "Aucune décision."

    pid = decision.get(
        "proposition_id",
        "?",
    )

    statut = decision.get(
        "statut",
        "?",
    )

    utilisateur = decision.get(
        "utilisateur",
        "?",
    )

    date = decision.get(
        "date",
        "?",
    )

    commentaire = decision.get(
        "commentaire",
        "",
    )

    fichier = decision.get(
        "fichier",
        "?",
    )

    risque = decision.get(
        "niveau_risque",
        "?",
    )

    lignes = [
        f"Proposition : {pid}",
        f"Statut      : {statut}",
        f"Fichier     : {fichier}",
        f"Risque      : {risque}",
        f"Utilisateur : {utilisateur}",
        f"Date        : {date}",
    ]

    if commentaire:
        lignes.append(
            f"Commentaire : {commentaire}"
        )

    verification = verifier_integrite_autorisation(
        decision
    )

    lignes.append(
        "Intégrité   : "
        + (
            "OK"
            if verification.get(
                "valide",
                False,
            )
            else "INVALIDE"
        )
    )

    return "\n".join(
        lignes
    )


# ---------------------------------------------------------------------------
# Parsing des commandes humaines
# ---------------------------------------------------------------------------

def parser_commande_autorisation(
    texte: str,
) -> dict[str, Any] | None:
    """
    Analyse uniquement les commandes humaines explicites :

        J'AUTORISE <id>
        JE REJETE <id>
    """
    texte = str(
        texte or ""
    ).strip()

    if not texte:
        return None

    # Autorisation : volontairement stricte.
    match = re.fullmatch(
        r"J(?:['’])AUTORISE\s+"
        r"([A-Za-z0-9][A-Za-z0-9_-]{3,127})",
        texte,
        flags=re.IGNORECASE,
    )

    if match:
        return {
            "action": ACTION_AUTORISER,
            "proposition_id": match.group(1),
            "commentaire": "",
        }

    # Rejet : syntaxe stricte également.
    match = re.fullmatch(
        r"JE\s+REJETE?\s+"
        r"([A-Za-z0-9][A-Za-z0-9_-]{3,127})",
        texte,
        flags=re.IGNORECASE,
    )

    if match:
        return {
            "action": ACTION_REJETER,
            "proposition_id": match.group(1),
            "commentaire": "",
        }

    return None

def traiter_commande(
    texte: str,
    utilisateur: str = "humain",
) -> dict[str, Any]:
    """
    Traite directement une commande d'autorisation humaine.

    Cette fonction n'applique jamais la modification.
    """
    commande = parser_commande_autorisation(
        texte
    )

    if not commande:
        return {
            "ok": False,
            "traitee": False,
            "message": (
                "Commande d'autorisation non reconnue."
            ),
        }

    pid = commande[
        "proposition_id"
    ]

    action = commande[
        "action"
    ]

    commentaire = commande[
        "commentaire"
    ]

    if action == ACTION_AUTORISER:
        resultat = valider_proposition(
            pid,
            commentaire=commentaire,
            utilisateur=utilisateur,
            confirmation=str(texte or "").strip(),
        )

    else:
        resultat = rejeter_proposition(
            pid,
            commentaire=commentaire,
            utilisateur=utilisateur,
        )

    resultat["traitee"] = True

    return resultat


# ---------------------------------------------------------------------------
# Audit — lecture
# ---------------------------------------------------------------------------

def lister_decisions() -> list[dict[str, Any]]:
    """
    Retourne toutes les décisions enregistrées.
    """
    decisions: list[dict[str, Any]] = []

    if not DECISIONS_DIR.exists():
        return decisions

    for chemin in sorted(
        DECISIONS_DIR.glob("*.json")
    ):
        decision = _lire_json(
            chemin
        )

        if decision:
            decisions.append(
                decision
            )

    return decisions


# ---------------------------------------------------------------------------
# Audit — invalidation
# ---------------------------------------------------------------------------

def invalider_decision(
    proposition_id: str,
    raison: str = "",
) -> dict[str, Any]:
    """
    Invalide explicitement une décision.

    On ne supprime PAS la trace d'audit.
    """
    try:
        pid = _normaliser_id(
            proposition_id
        )

        chemin = _chemin_decision(
            pid
        )

        decision = _lire_json(
            chemin
        )

        if not decision:
            return {
                "ok": False,
                "message": (
                    f"Aucune décision pour {pid}."
                ),
            }

        decision["statut"] = STATUT_INVALIDE

        decision["invalidee_le"] = _timestamp()

        decision["invalidation_raison"] = (
            str(raison or "").strip()
            or "Invalidation manuelle."
        )

        _ecrire_json_atomique(
            chemin,
            decision,
        )

        return {
            "ok": True,
            "message": (
                f"Décision {pid} invalidée."
            ),
            "decision": decision,
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": str(exc),
        }


# ---------------------------------------------------------------------------
# Compatibilité historique
# ---------------------------------------------------------------------------

def supprimer_decision(
    proposition_id: str,
) -> dict[str, Any]:
    """
    Ancienne API conservée pour compatibilité.

    On ne supprime plus physiquement une décision d'audit.
    """
    return invalider_decision(
        proposition_id,
        raison=(
            "Ancienne demande de suppression "
            "convertie en invalidation."
        ),
    )


# ---------------------------------------------------------------------------
# Export public
# ---------------------------------------------------------------------------

__all__ = [
    "valider_proposition",
    "autoriser_proposition",
    "rejeter_proposition",
    "autorisation_valide",
    "verifier_autorisation",
    "verifier_integrite_autorisation",
    "marquer_appliquee",
    "examiner_proposition",
    "lister_propositions_en_attente",
    "obtenir_statistiques",
    "formater_decision",
    "parser_commande_autorisation",
    "traiter_commande",
    "lister_decisions",
    "invalider_decision",
    "supprimer_decision",
]