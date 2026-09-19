"""
JIBI — propositions.py v6

Gestion sécurisée des propositions d'auto-réparation.

Principes :
- aucune modification directe de la production ;
- chaque proposition est liée au SHA-256 exact du contenu source ;
- chaque nouveau contenu possède son propre SHA-256 ;
- le diff est conservé et possède son propre SHA-256 ;
- les changements de statut sont historisés ;
- l'intégrité est vérifiable avant autorisation et application ;
- aucune décision d'autorisation n'est prise ici ;
- aucune modification du fichier de production n'est effectuée ici ;
- compatibilité avec risk_engine.py, validateur.py et autorisation.py.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================================
# CONFIGURATION
# ============================================================================

try:
    from core.config import WORKSPACE_DIR
except Exception:
    WORKSPACE_DIR = (
        Path(__file__).resolve().parent.parent / "workspace"
    )


PROPOSITIONS_DIR = (
    Path(WORKSPACE_DIR)
    / "jibi_lab"
    / "propositions"
)


# ============================================================================
# IMPORTS INTERNES
# ============================================================================

try:
    from .risk_engine import evaluer_proposition
except Exception:
    evaluer_proposition = None


try:
    from .validateur import valider_syntaxe
except Exception:

    def valider_syntaxe(
        contenu: str,
        nom: str = "<string>",
    ) -> Dict[str, Any]:
        """
        Fallback minimal.

        Normalement, validateur.py doit être disponible.
        """
        try:
            compile(contenu, nom, "exec")

            return {
                "ok": True,
                "message": "Syntaxe valide.",
                "syntaxe_ok": True,
                "erreurs": [],
            }

        except SyntaxError as erreur:
            return {
                "ok": False,
                "message": str(erreur),
                "syntaxe_ok": False,
                "erreurs": [
                    {
                        "ligne": erreur.lineno,
                        "colonne": erreur.offset,
                        "message": erreur.msg,
                    }
                ],
            }


# ============================================================================
# OUTILS CRYPTOGRAPHIQUES
# ============================================================================

def sha256_texte(contenu: str) -> str:
    """
    Calcule le SHA-256 du contenu UTF-8.

    Le calcul est déterministe :
    même contenu -> même empreinte.
    """
    if not isinstance(contenu, str):
        raise TypeError(
            "sha256_texte() attend une chaîne de caractères."
        )

    return hashlib.sha256(
        contenu.encode("utf-8")
    ).hexdigest()


def sha256_fichier(
    fichier: str | Path,
) -> str:
    """
    Calcule l'empreinte du contenu textuel d'un fichier.

    On conserve la même convention que lors de la création
    des propositions : lecture UTF-8 avec remplacement des
    caractères invalides.
    """
    path = Path(fichier)

    if not path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Le chemin n'est pas un fichier : {path}"
        )

    contenu = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    return sha256_texte(contenu)


def sha256_diff(diff: str) -> str:
    """
    Calcule l'empreinte du diff.

    Cette empreinte permet de vérifier que le diff présenté
    lors de l'autorisation correspond toujours à la proposition.
    """
    return sha256_texte(diff)


# ============================================================================
# OUTILS INTERNES
# ============================================================================

def _timestamp() -> str:
    """Retourne un timestamp ISO avec fuseau horaire."""
    return datetime.now().astimezone().isoformat()


def _generer_id() -> str:
    """
    Génère un identifiant court et imprévisible.
    """
    return secrets.token_hex(6)


def _chemin_proposition(
    proposition_id: str,
) -> Path:
    """
    Retourne le fichier JSON correspondant à un ID.

    Protection contre les traversées de chemin.
    """
    if not isinstance(proposition_id, str):
        raise TypeError(
            "L'identifiant doit être une chaîne."
        )

    proposition_id = proposition_id.strip()

    if not proposition_id:
        raise ValueError(
            "Identifiant de proposition vide."
        )

    if not all(
        caractere.isalnum()
        or caractere in {"_", "-"}
        for caractere in proposition_id
    ):
        raise ValueError(
            "Identifiant de proposition invalide."
        )

    return PROPOSITIONS_DIR / f"{proposition_id}.json"


def _sauver(
    proposition: Dict[str, Any],
) -> bool:
    """
    Sauvegarde atomiquement une proposition.

    Cette fonction écrit uniquement dans le dépôt des propositions,
    jamais dans le fichier de production.
    """
    try:
        proposition_id = proposition.get("id")

        if not proposition_id:
            return False

        cible = _chemin_proposition(
            proposition_id
        )

        PROPOSITIONS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        contenu = json.dumps(
            proposition,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

        # Nom temporaire unique afin d'éviter les collisions.
        temporaire = PROPOSITIONS_DIR / (
            f".{proposition_id}."
            f"{secrets.token_hex(4)}.tmp"
        )

        try:
            temporaire.write_text(
                contenu,
                encoding="utf-8",
            )

            temporaire.replace(cible)

        finally:
            if temporaire.exists():
                try:
                    temporaire.unlink()
                except OSError:
                    pass

        return True

    except Exception:
        return False


def _charger(
    chemin: Path,
) -> Optional[Dict[str, Any]]:
    """Charge une proposition JSON valide."""
    try:
        if not chemin.exists():
            return None

        if not chemin.is_file():
            return None

        contenu = chemin.read_text(
            encoding="utf-8",
        )

        proposition = json.loads(
            contenu
        )

        if not isinstance(proposition, dict):
            return None

        return proposition

    except Exception:
        return None


# ============================================================================
# VALIDATION
# ============================================================================

def verifier_syntaxe_solution(
    fichier: str,
    contenu: str,
) -> Dict[str, Any]:
    """
    Vérifie la syntaxe du nouveau contenu.
    """
    return valider_syntaxe(
        contenu,
        str(fichier),
    )


def verifier_integrite_proposition(
    proposition: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Vérifie les empreintes internes de la proposition.

    Contrôles :
    - ancien <-> source_sha256
    - nouveau <-> nouveau_sha256
    - diff <-> diff_sha256

    Aucun fichier de production n'est modifié.
    """
    try:
        if not isinstance(proposition, dict):
            return {
                "ok": False,
                "source_sha256": None,
                "nouveau_sha256": None,
                "diff_sha256": None,
                "problemes": [
                    "Proposition invalide."
                ],
            }

        ancien = proposition.get(
            "ancien",
            "",
        )

        nouveau = proposition.get(
            "nouveau",
            "",
        )

        diff = proposition.get(
            "diff",
            "",
        )

        if not isinstance(ancien, str):
            raise TypeError(
                "Le contenu 'ancien' est invalide."
            )

        if not isinstance(nouveau, str):
            raise TypeError(
                "Le contenu 'nouveau' est invalide."
            )

        if not isinstance(diff, str):
            raise TypeError(
                "Le contenu 'diff' est invalide."
            )

        sha_ancien = sha256_texte(
            ancien
        )

        sha_nouveau = sha256_texte(
            nouveau
        )

        sha_diff = sha256_diff(
            diff
        )

        attendu_ancien = proposition.get(
            "source_sha256"
        )

        attendu_nouveau = proposition.get(
            "nouveau_sha256"
        )

        attendu_diff = proposition.get(
            "diff_sha256"
        )

        problemes: list[str] = []

        if attendu_ancien != sha_ancien:
            problemes.append(
                "SHA du contenu source incohérent."
            )

        if attendu_nouveau != sha_nouveau:
            problemes.append(
                "SHA du nouveau contenu incohérent."
            )

        # Compatibilité avec les anciennes propositions :
        # si diff_sha256 n'existe pas, on ne rend pas les anciennes
        # propositions invalides uniquement pour cette raison.
        if attendu_diff is not None:
            if attendu_diff != sha_diff:
                problemes.append(
                    "SHA du diff incohérent."
                )

        return {
            "ok": not problemes,
            "source_sha256": sha_ancien,
            "nouveau_sha256": sha_nouveau,
            "diff_sha256": sha_diff,
            "problemes": problemes,
        }

    except Exception as erreur:
        return {
            "ok": False,
            "source_sha256": None,
            "nouveau_sha256": None,
            "diff_sha256": None,
            "problemes": [
                str(erreur)
            ],
        }


def verifier_source_actuelle(
    proposition: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Vérifie que le fichier de production correspond encore
    au SHA enregistré lors de la création.

    Ce contrôle est effectué juste avant autorisation/application.
    """
    try:
        if not isinstance(proposition, dict):
            return {
                "ok": False,
                "message": "Proposition invalide.",
            }

        fichier = proposition.get(
            "fichier"
        )

        if not fichier:
            return {
                "ok": False,
                "message": (
                    "Fichier absent de la proposition."
                ),
            }

        path = Path(fichier)

        if not path.exists():
            return {
                "ok": False,
                "message": (
                    "Fichier source introuvable."
                ),
            }

        if not path.is_file():
            return {
                "ok": False,
                "message": (
                    "La cible n'est pas un fichier."
                ),
            }

        sha_attendu = proposition.get(
            "source_sha256"
        )

        if not sha_attendu:
            return {
                "ok": False,
                "message": (
                    "SHA source absent de la proposition."
                ),
            }

        sha_actuel = sha256_fichier(
            path
        )

        if sha_actuel != sha_attendu:
            return {
                "ok": False,
                "message": (
                    "Le fichier source a changé "
                    "depuis la création de la proposition."
                ),
                "sha_attendu": sha_attendu,
                "sha_actuel": sha_actuel,
            }

        return {
            "ok": True,
            "message": "Source inchangée.",
            "sha_attendu": sha_attendu,
            "sha_actuel": sha_actuel,
        }

    except Exception as erreur:
        return {
            "ok": False,
            "message": str(erreur),
        }


# ============================================================================
# CRÉATION
# ============================================================================

def creer_proposition(
    fichier: str | Path,
    solution: str,
    probleme: str = "",
    origine: str = "jibi",
    priorite: str = "moyenne",
    raison: str = "",
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crée une proposition d'auto-réparation.

    IMPORTANT :
    cette fonction ne modifie jamais le fichier de production.
    """
    path = Path(fichier)

    if not path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Le chemin n'est pas un fichier : {path}"
        )

    if not isinstance(solution, str):
        raise TypeError(
            "La solution doit être une chaîne."
        )

    # ------------------------------------------------------------------------
    # Lecture source
    # ------------------------------------------------------------------------

    ancien = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    # ------------------------------------------------------------------------
    # Vérification modification réelle
    # ------------------------------------------------------------------------

    if ancien == solution:
        raise ValueError(
            "La proposition ne contient aucune modification."
        )

    # ------------------------------------------------------------------------
    # Validation syntaxique
    # ------------------------------------------------------------------------

    validation = verifier_syntaxe_solution(
        str(path),
        solution,
    )

    if not validation.get("ok", False):
        raise ValueError(
            "Solution syntaxiquement invalide : "
            f"{validation.get('message', '')}"
        )

    # ------------------------------------------------------------------------
    # SHA
    # ------------------------------------------------------------------------

    source_sha256 = sha256_texte(
        ancien
    )

    nouveau_sha256 = sha256_texte(
        solution
    )

    # ------------------------------------------------------------------------
    # DIFF
    # ------------------------------------------------------------------------

    diff = "".join(
        difflib.unified_diff(
            ancien.splitlines(
                keepends=True
            ),
            solution.splitlines(
                keepends=True
            ),
            fromfile=str(path),
            tofile=str(path),
        )
    )

    diff_sha256 = sha256_diff(
        diff
    )

    # ------------------------------------------------------------------------
    # Identifiant
    # ------------------------------------------------------------------------

    proposition_id = _generer_id()

    # ------------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------------

    maintenant = _timestamp()

    proposition: Dict[str, Any] = {
        # Identité
        "id": proposition_id,

        # Cible
        "fichier": str(path),

        # Description
        "probleme": probleme,
        "raison": raison or probleme,
        "origine": origine,
        "source": source or origine,
        "priorite": priorite,

        # État
        "statut": "proposition",
        "date_creation": maintenant,

        # Contenu
        "ancien": ancien,
        "nouveau": solution,

        # Empreintes
        "source_sha256": source_sha256,
        "nouveau_sha256": nouveau_sha256,
        "diff_sha256": diff_sha256,

        # Diff
        "diff": diff,

        # Taille
        "taille_ancien": len(
            ancien.encode("utf-8")
        ),
        "taille_nouveau": len(
            solution.encode("utf-8")
        ),
        "taille_diff": len(
            diff.encode("utf-8")
        ),

        # Validation
        "validation": validation,

        # Tests
        "tests": {},

        # Laboratoire
        "laboratoire": {},

        # Autorisation
        "autorisation": {
            "requise": True,
            "validee": False,
            "source_sha256": source_sha256,
            "nouveau_sha256": nouveau_sha256,
            "diff_sha256": diff_sha256,
        },

        # Backup
        "backup": None,

        # Application
        "application": None,

        # Historique
        "historique": [
            {
                "ancien_statut": None,
                "statut": "proposition",
                "date": maintenant,
                "details": {},
            }
        ],
    }

    # ------------------------------------------------------------------------
    # Évaluation du risque
    # ------------------------------------------------------------------------

    if evaluer_proposition is not None:
        try:
            evaluation = evaluer_proposition(
                proposition
            )

            if hasattr(
                evaluation,
                "to_dict",
            ):
                evaluation = evaluation.to_dict()

            elif hasattr(
                evaluation,
                "__dict__",
            ):
                evaluation = dict(
                    evaluation.__dict__
                )

            if not isinstance(
                evaluation,
                dict,
            ):
                raise TypeError(
                    "Évaluation de risque invalide."
                )

            proposition["risque"] = evaluation

        except Exception as erreur:
            # Principe de sécurité :
            # en cas d'incertitude, risque critique.
            proposition["risque"] = {
                "fichier": str(path),
                "niveau": "critique",
                "lignes_diff": 0,
                "touches_imports": False,
                "touches_dependances": False,
                "auto_applicable": False,
                "raisons": [
                    "évaluation du risque impossible",
                    str(erreur),
                ],
            }

    else:
        proposition["risque"] = {
            "fichier": str(path),
            "niveau": "critique",
            "lignes_diff": 0,
            "touches_imports": False,
            "touches_dependances": False,
            "auto_applicable": False,
            "raisons": [
                "risk_engine indisponible",
            ],
        }

    # ------------------------------------------------------------------------
    # Intégrité
    # ------------------------------------------------------------------------

    integrite = verifier_integrite_proposition(
        proposition
    )

    if not integrite["ok"]:
        raise RuntimeError(
            "Erreur d'intégrité de la proposition : "
            + "; ".join(
                integrite.get(
                    "problemes",
                    []
                )
            )
        )

    # ------------------------------------------------------------------------
    # Sauvegarde
    # ------------------------------------------------------------------------

    if not _sauver(proposition):
        raise OSError(
            "Impossible de sauvegarder la proposition."
        )

    return proposition


# ============================================================================
# PERSISTANCE
# ============================================================================

def sauvegarder_proposition(
    proposition: Dict[str, Any],
) -> bool:
    """
    Sauvegarde une proposition existante.
    """
    return _sauver(
        proposition
    )


def charger_proposition(
    proposition_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Charge une proposition par son identifiant.
    """
    try:
        return _charger(
            _chemin_proposition(
                proposition_id
            )
        )
    except Exception:
        return None


def lister_propositions(
    statut: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Liste les propositions, de la plus récente à la plus ancienne.
    """
    resultats: List[
        Dict[str, Any]
    ] = []

    if not PROPOSITIONS_DIR.exists():
        return resultats

    try:
        fichiers = sorted(
            PROPOSITIONS_DIR.glob(
                "*.json"
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return resultats

    for fichier in fichiers:
        proposition = _charger(
            fichier
        )

        if proposition is None:
            continue

        if (
            statut is not None
            and proposition.get(
                "statut"
            ) != statut
        ):
            continue

        resultats.append(
            proposition
        )

    return resultats


def lister_propositions_syntaxe() -> List[Dict[str, Any]]:
    """
    Retourne les propositions dont la syntaxe initiale est valide.
    """
    return [
        proposition
        for proposition in lister_propositions()
        if proposition.get(
            "validation",
            {},
        ).get(
            "ok",
            False,
        )
    ]


# ============================================================================
# STATUTS
# ============================================================================

def _changer_statut(
    proposition_id: str,
    statut: str,
    details: Optional[
        Dict[str, Any]
    ] = None,
) -> bool:
    """
    Change le statut et ajoute une entrée à l'historique.
    """
    proposition = charger_proposition(
        proposition_id
    )

    if proposition is None:
        return False

    ancien_statut = proposition.get(
        "statut"
    )

    proposition["statut"] = statut

    proposition.setdefault(
        "historique",
        [],
    ).append(
        {
            "ancien_statut": ancien_statut,
            "statut": statut,
            "date": _timestamp(),
            "details": details or {},
        }
    )

    return sauvegarder_proposition(
        proposition
    )


def marquer_en_cours(
    proposition_id: str,
) -> bool:
    return _changer_statut(
        proposition_id,
        "en_cours",
    )


def marquer_testee(
    proposition_id: str,
    tests: Optional[
        Dict[str, Any]
    ] = None,
) -> bool:
    return _changer_statut(
        proposition_id,
        "testee",
        tests,
    )


def marquer_validee(
    proposition_id: str,
    validation: Optional[
        Dict[str, Any]
    ] = None,
) -> bool:
    return _changer_statut(
        proposition_id,
        "validee",
        validation,
    )


def marquer_rejetee(
    proposition_id: str,
    raison: str = "",
) -> bool:
    return _changer_statut(
        proposition_id,
        "rejetee",
        {
            "raison": raison,
        },
    )


def marquer_appliquee(
    proposition_id: str,
    application: Optional[
        Dict[str, Any]
    ] = None,
) -> bool:
    return _changer_statut(
        proposition_id,
        "appliquee",
        application,
    )


# ============================================================================
# AFFICHAGE
# ============================================================================

def formater_proposition(
    proposition: Dict[str, Any],
) -> str:
    """
    Formate une proposition pour affichage humain.
    """
    risque = proposition.get(
        "risque",
        {},
    )

    if isinstance(risque, dict):
        niveau = risque.get(
            "niveau",
            "?",
        )
    else:
        niveau = str(risque)

    return (
        f"[{proposition.get('id', '?')}] "
        f"{proposition.get('fichier', '?')}\n"
        f"Statut : "
        f"{proposition.get('statut', '?')}\n"
        f"Risque : {niveau}\n"
        f"SHA source : "
        f"{proposition.get('source_sha256', '?')}\n"
        f"SHA nouveau : "
        f"{proposition.get('nouveau_sha256', '?')}\n"
        f"SHA diff : "
        f"{proposition.get('diff_sha256', '?')}\n"
        f"Raison : "
        f"{proposition.get('raison', '')}"
    )


# ============================================================================
# STATISTIQUES
# ============================================================================

def obtenir_statistiques() -> Dict[str, int]:
    """
    Retourne les statistiques globales des propositions.
    """
    propositions = lister_propositions()

    statistiques: Dict[str, int] = {
        "total": len(propositions),
        "proposition": 0,
        "en_cours": 0,
        "testee": 0,
        "validee": 0,
        "rejetee": 0,
        "appliquee": 0,
    }

    for proposition in propositions:
        statut = proposition.get(
            "statut",
            "proposition",
        )

        statistiques[statut] = (
            statistiques.get(
                statut,
                0,
            )
            + 1
        )

    return statistiques


def obtenir_statistiques_syntaxe() -> Dict[str, int]:
    """
    Retourne les statistiques de validation syntaxique.
    """
    propositions = lister_propositions()

    valides = sum(
        1
        for proposition in propositions
        if proposition.get(
            "validation",
            {},
        ).get(
            "ok",
            False,
        )
    )

    return {
        "total": len(propositions),
        "syntaxiquement_valides": valides,
        "invalides": (
            len(propositions)
            - valides
        ),
    }


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # SHA
    "sha256_texte",
    "sha256_fichier",
    "sha256_diff",

    # Création
    "creer_proposition",

    # Persistance
    "sauvegarder_proposition",
    "charger_proposition",
    "lister_propositions",
    "lister_propositions_syntaxe",

    # Validation
    "verifier_syntaxe_solution",
    "verifier_integrite_proposition",
    "verifier_source_actuelle",

    # Statuts
    "marquer_en_cours",
    "marquer_testee",
    "marquer_validee",
    "marquer_rejetee",
    "marquer_appliquee",

    # Affichage
    "formater_proposition",

    # Statistiques
    "obtenir_statistiques",
    "obtenir_statistiques_syntaxe",

    # Configuration
    "PROPOSITIONS_DIR",
]