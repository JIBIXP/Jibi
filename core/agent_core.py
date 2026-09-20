"""
AGENT CORE JIBI — v8

Rôle :
    Interface principale entre :
        - utilisateur
        - routeur
        - cerveau / LLM
        - outils
        - orchestrateur d'auto-amélioration

Principe :
    AgentCore route et coordonne.
    Cerveau communique avec le LLM.
    Orchestrateur contrôle les modifications.
    Sécurité contrôle les accès préliminaires.

CORRECTIONS v8 :
    - Routage amélioré pour différencier :
        * Questions conversationnelles → cerveau
        * Demandes d'analyse/explication → cerveau
        * Analyse de code → analyseur_code
        * Diagnostic technique système → orchestrateur
        * Modifications de code → propositions
    - Classification locale réduite aux cas évidents
    - Le LLM traite les cas ambigus

AgentCore ne :
    - écrit jamais directement un fichier de production ;
    - ne crée jamais directement un outil en production ;
    - ne gère pas les backups ;
    - ne gère pas les rollbacks ;
    - ne contourne pas les autorisations ;
    - n'exécute pas un outil avec des arguments non validés.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core import cerveau
from core import config
from core import router
from core import securite


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("jibi.agent_core")


# ============================================================
# IMPORTS OPTIONNELS
# ============================================================

try:
    from self_improvement.orchestrateur import creer_orchestrateur
except Exception:
    creer_orchestrateur = None


try:
    from self_improvement.gestionnaire import (
        analyser_jibi,
        tableau_de_bord,
    )
except Exception:
    analyser_jibi = None
    tableau_de_bord = None


try:
    from self_improvement import analyseur_code
except Exception:
    analyseur_code = None


try:
    from tools import TOOLS_REGISTRY
except Exception:
    logger.warning(
        "Registre d'outils (tools/) indisponible : "
        "AgentCore démarrera sans outils enregistrés."
    )
    TOOLS_REGISTRY = {}


def _outils_depuis_registre() -> Dict[str, Callable[..., Any]]:
    """
    Construit le dict {nom_outil: fonction} attendu par AgentCore
    à partir de tools.TOOLS_REGISTRY (qui stocke des specs enrichies
    {"function", "description", "parameters"}, pas des callables nus).
    """

    outils: Dict[str, Callable[..., Any]] = {}

    for nom, spec in TOOLS_REGISTRY.items():

        fonction = (
            spec.get("function")
            if isinstance(spec, dict)
            else None
        )

        if callable(fonction):
            outils[nom] = fonction
        else:
            logger.warning(
                "Outil '%s' ignoré : pas de fonction "
                "appelable dans le registre.",
                nom,
            )

    return outils


# ============================================================
# RÉPONSE
# ============================================================

@dataclass
class ReponseAgent:
    texte: str
    confidence: float = 1.0
    intention: str = ""
    succes: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# OUTILS
# ============================================================

class AgentCore:

    def __init__(
        self,
        outils: Optional[Dict[str, Callable[..., Any]]] = None,
    ) -> None:

        self.outils: Dict[str, Callable[..., Any]] = (
            outils
            if outils is not None
            else _outils_depuis_registre()
        )

        self._orchestrateur = None

        if creer_orchestrateur is not None:
            try:
                self._orchestrateur = (
                    creer_orchestrateur()
                )

            except Exception as exc:
                logger.warning(
                    "Orchestrateur indisponible : %s",
                    exc,
                )

    # ========================================================
    # LLM
    # ========================================================

    def _llm_disponible(self) -> bool:
        try:
            return bool(
                cerveau.disponible()
            )

        except Exception:
            return False

    # ========================================================
    # TOOL SPEC
    # ========================================================

    def _annotation_type(
        self,
        annotation: Any,
    ) -> str:
        """
        Convertit une annotation Python simple en type JSON.
        """

        if annotation is inspect.Parameter.empty:
            return "string"

        if annotation is int:
            return "integer"

        if annotation is float:
            return "number"

        if annotation is bool:
            return "boolean"

        if annotation in (dict, Dict):
            return "object"

        if annotation in (list, List):
            return "array"

        return "string"

    def _tool_spec(
        self,
        nom: str,
        fonction: Callable[..., Any],
    ) -> Dict[str, Any]:
        """
        Construit une description déclarative d'un outil.

        Cette fonction ne permet aucune exécution.
        """

        try:
            signature = inspect.signature(fonction)

        except Exception as exc:
            logger.warning(
                "Signature outil impossible %s : %s",
                nom,
                exc,
            )

            return {
                "name": nom,
                "description": f"Outil JIBI : {nom}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }

        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param_name, param in signature.parameters.items():

            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            properties[param_name] = {
                "type": self._annotation_type(
                    param.annotation
                )
            }

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        description = (
            getattr(
                fonction,
                "__doc__",
                None,
            )
            or f"Outil JIBI : {nom}"
        )

        return {
            "name": nom,
            "description": str(description).strip(),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    # ========================================================
    # VALIDATION OUTIL
    # ========================================================

    def _valider_arguments_outil(
        self,
        outil: Callable[..., Any],
        arguments: Dict[str, Any],
    ) -> tuple[bool, str]:

        if not isinstance(arguments, dict):
            return False, "Les arguments doivent être un objet."

        try:
            signature = inspect.signature(outil)

        except Exception as exc:
            return False, (
                f"Signature de l'outil inaccessible : {exc}"
            )

        params = signature.parameters

        accepte_kwargs = any(
            param.kind
            == inspect.Parameter.VAR_KEYWORD
            for param in params.values()
        )

        for nom in arguments:

            if nom not in params and not accepte_kwargs:
                return False, (
                    f"Argument inconnu : {nom}"
                )

        try:
            signature.bind(**arguments)

        except TypeError as exc:
            return False, str(exc)

        return True, ""

    # ========================================================
    # SÉCURITÉ
    # ========================================================

    def _est_sensible(
        self,
        message: str,
    ) -> bool:

        return securite.est_texte_sensible(
            message
        )

    # ========================================================
    # OUTILS DISPONIBLES
    # ========================================================

    def _outils_specs(self) -> List[Dict[str, Any]]:
        """
        Décrit les outils disponibles pour le LLM (planifier()).

        Priorité à la spec déclarée dans tools/__init__.py
        (description soignée + schéma JSON, notamment les champs
        "confirmer" marqués required pour les actions destructives) ;
        repli sur l'introspection Python pure (_tool_spec) pour les
        outils fournis hors registre (ex. tests, outils ad hoc).
        """

        specs: List[Dict[str, Any]] = []

        for nom, fonction in self.outils.items():

            if not callable(fonction):
                continue

            try:
                spec_registre = TOOLS_REGISTRY.get(nom)

                if (
                    isinstance(spec_registre, dict)
                    and spec_registre.get("parameters")
                ):
                    specs.append({
                        "name": nom,
                        "description": (
                            spec_registre.get("description")
                            or f"Outil JIBI : {nom}"
                        ),
                        "parameters": spec_registre.get(
                            "parameters",
                            {
                                "type": "object",
                                "properties": {},
                                "required": [],
                            },
                        ),
                    })

                else:
                    specs.append(
                        self._tool_spec(
                            nom,
                            fonction,
                        )
                    )

            except Exception:
                logger.exception(
                    "Impossible de décrire l'outil %s",
                    nom,
                )

        return specs

    # ========================================================
    # CLASSIFICATION STRICTE
    # ========================================================

    def _classification_stricte(
        self,
        message: str,
    ) -> Optional[str]:
        """
        Classification locale réduite aux cas ÉVIDENTS uniquement.
        
        Retourne None si le message est ambigu et doit passer au LLM.
        """
        
        msg_lower = message.lower().strip()
        
        # ============================================================
        # CAS ÉVIDENTS - Autorisation/Rejet
        # ============================================================
        
        if re.match(
            r"^j(?:[''])?autorise\s+[a-z0-9_-]+",
            msg_lower,
        ):
            return "CONFIRMATION"
            
        if re.match(
            r"^(?:je\s+)?rejet(?:te|e)\s+[a-z0-9_-]+",
            msg_lower,
        ):
            return "REJET"
            
        if re.match(
            r"^(?:confirme|oui)\s+[a-z0-9_-]+",
            msg_lower,
        ):
            return "CONFIRMATION"
        
        # ============================================================
        # CAS ÉVIDENTS - Listes/État
        # ============================================================
        
        if msg_lower in {
            "liste",
            "liste propositions",
            "propositions",
            "liste des propositions",
        }:
            return "LISTE"
            
        if msg_lower in {
            "état",
            "etat",
            "statut",
            "status",
        }:
            return "ETAT"
        
        # ============================================================
        # CAS ÉVIDENTS - Diagnostic SYSTÈME (très spécifique)
        # ============================================================
        
        diagnostic_system_patterns = [
            r"^diagnostic\s+(?:système|systeme|complet|technique)",
            r"^fais\s+un\s+diagnostic\s+(?:système|systeme|du\s+système)",
            r"^vérifie\s+(?:la\s+)?santé\s+(?:du\s+)?système",
            r"^analyse\s+(?:la\s+)?santé\s+(?:du\s+)?projet",
        ]
        
        for pattern in diagnostic_system_patterns:
            if re.search(pattern, msg_lower):
                return "DIAGNOSTIC"
        
        # ============================================================
        # CAS ÉVIDENTS - Analyse de code (avec fichier/module explicite)
        # ============================================================
        
        if re.search(
            r"(?:analyse|inspecte|examine)\s+(?:le\s+)?(?:fichier\s+)?[a-z0-9_/.-]+\.py",
            msg_lower,
        ):
            return "ANALYSE_CODE"
        
        # ============================================================
        # CAS ÉVIDENTS - Recherche web
        # ============================================================
        
        if msg_lower.startswith(("recherche ", "cherche sur ", "google ")):
            return "RECHERCHE"
            
        # ============================================================
        # CAS ÉVIDENTS - URLs
        # ============================================================
        
        if re.search(r"https?://", message):
            return "OUVRIR_URL"
        
        # ============================================================
        # CAS ÉVIDENTS - Modification fichier (avec nom explicite)
        # ============================================================
        
        if re.search(
            r"(?:modifie|corrige|répare)\s+(?:le\s+fichier\s+)?[a-z0-9_/.-]+\.py",
            msg_lower,
        ):
            return "MODIFIER_FICHIER"

        # ============================================================
        # CAS ÉVIDENTS - Salutations & Conversation
        # ============================================================
        salutations = (
            "bonjour", "salut", "hello", "hi", "coucou", "yo", "bonsoir", "hey",
            "merci", "merci beaucoup", "au revoir", "bye", "à bientôt", "a bientot",
            "ça va", "ca va", "comment vas-tu", "comment tu vas", "comment ca va",
            "comment ça va", "qui es-tu", "tu es qui", "présente-toi", "presente toi",
        )
        if msg_lower in salutations or any(msg_lower.startswith(s + " ") for s in salutations):
            return "DISCUSSION"

        # ============================================================
        # CAS ÉVIDENTS - Auto-amélioration / Diagnostics
        # ============================================================
        if re.search(r"^(?:auto[- ]?am[ée]lior|am[ée]liore[- ]toi|diagnostic\b|optimise[- ]toi)", msg_lower):
            return "DIAGNOSTIC"

        # ============================================================
        # CAS ÉVIDENTS - Questions & Demandes d'aide
        # ============================================================
        if msg_lower.startswith((
            "comment",
            "pourquoi",
            "qu'est-ce",
            "quest-ce",
            "quel",
            "quelle",
            "quels",
            "quelles",
            "explique",
            "décris",
            "decris",
            "montre",
            "dis-moi",
            "peux-tu",
            "est-ce que",
            "aide-moi",
            "donne-moi",
            "trouve",
            "qui ",
            "quand ",
            "où ",
        )):
            return "QUESTION"

        return None

    # ========================================================
    # MESSAGE PRINCIPAL
    # ========================================================

    def traiter_message(
        self,
        message: str,
        on_chunk: Optional[Callable[[str], None]] = None,
        cancel_event: Any = None,
    ) -> ReponseAgent:

        if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
            return ReponseAgent(
                "Requête annulée.",
                0.0,
                "ANNULATION",
                False,
            )

        if not isinstance(message, str):
            message = str(message)

        message = router.normaliser_message(
            message
        )

        if not message:
            return ReponseAgent(
                "Je n'ai reçu aucun message.",
                1.0,
                "DISCUSSION",
            )

        # ============================================================
        # ÉTAPE 0 : Questions d'identité / accès → vérification réelle
        # ============================================================

        message_lower = message.lower()
        motifs_identite = (
            "qui es tu",
            "tu es une ia",
            "est-ce que tu es une ia",
            "as-tu accès",
            "acces a ton propre code",
            "accès à ton propre code",
            "tu peux lire ton code",
            "peux-tu lire ton code",
            "tu as accès à tes fichiers",
        )

        if any(motif in message_lower for motif in motifs_identite):
            etat = self._verifier_etat_agent()
            if etat["verification_ok"]:
                return ReponseAgent(
                    "Oui, je suis un assistant IA local. "
                    "J’ai vérifié que le projet est accessible et que je peux lire des fichiers du code source.",
                    0.95,
                    "IDENTITE",
                    True,
                    etat,
                )

            return ReponseAgent(
                "Je ne peux pas confirmer mon accès à cet instant, "
                "mais je ne prétends pas avoir un accès que je n’ai pas vérifié.",
                0.6,
                "IDENTITE",
                False,
                etat,
            )

        # ============================================================
        # ÉTAPE 1 : Classification stricte (cas évidents uniquement)
        # ============================================================
        
        intention = self._classification_stricte(
            message
        )

        if intention is not None:

            if intention in ("QUESTION", "DISCUSSION"):
                return self._question(
                    message,
                    on_chunk=on_chunk,
                    cancel_event=cancel_event,
                )

            if intention == "DIAGNOSTIC":
                return self._diagnostic()

            if intention == "ETAT":
                return self._etat()

            if intention == "LISTE":
                return self._liste()

            if intention == "ANALYSE_CODE":
                return self._analyser_code(
                    message
                )

            if intention == "RECHERCHE":
                return self._rechercher(message)

            if intention == "OUVRIR_URL":
                return self._ouvrir_url(message)

            if intention == "CONFIRMATION":
                return self._autoriser(message)

            if intention == "REJET":
                return self._rejeter(message)

            if intention == "MODIFIER_FICHIER":
                return self._modifier_fichier(
                    message
                )

            if intention == "CREER_OUTIL":
                return self._creer_outil(
                    message
                )

            if intention == "EXECUTER_OUTIL":
                return self._executer(
                    message
                )

        # ============================================================
        # ÉTAPE 2 : LLM pour cas ambigus
        # ============================================================

        if not self._llm_disponible():

            return ReponseAgent(
                "Je n'ai pas compris la demande et le LLM est indisponible.",
                0.4,
                "INCONNU",
                False,
            )

        try:
            plan = cerveau.planifier(
                message
            )

        except Exception as exc:

            logger.exception(
                "Erreur planification"
            )

            return ReponseAgent(
                f"Erreur de planification : {exc}",
                0.2,
                "ERREUR",
                False,
            )

        plan = router.extraire_plan(
            plan
        )

        intention = router.normaliser_intention(
            plan.get("intention")
        )

        # ============================================================
        # ÉTAPE 3 : Routage selon plan LLM
        # ============================================================

        if intention == "DIAGNOSTIC":
            return self._diagnostic()

        if intention == "ETAT":
            return self._etat()

        if intention == "LISTE":
            return self._liste()

        if intention == "ANALYSE_CODE":
            return self._analyser_code(
                message,
                plan,
            )

        if intention == "RECHERCHE":
            requete = str(
                plan.get(
                    "requete",
                    message,
                )
            )

            return self._rechercher(
                requete
            )

        if intention == "MODIFIER_FICHIER":
            return self._modifier_fichier(
                message,
                plan,
            )

        if intention == "CREER_OUTIL":
            return self._creer_outil(
                message,
                plan,
            )

        if intention == "EXECUTER_OUTIL":
            return self._executer(
                message,
                plan,
            )

        if intention == "OUVRIR_URL":
            return self._ouvrir_url(message)

        if intention == "TACHE_COMPLEXE":
            return self._tache_complexe(
                message,
                plan,
            )

        # ============================================================
        # PAR DÉFAUT : Question conversationnelle → Cerveau
        # ============================================================

        return self._question(
            message,
            on_chunk=on_chunk,
            cancel_event=cancel_event,
        )

    # ========================================================
    # VÉRIFICATION D'ÉTAT (IDENTITÉ / ACCÈS)
    # ========================================================

    def _verifier_etat_agent(self) -> dict[str, Any]:
        """
        Vérifie l'accès réel à son environnement avant de faire
        une affirmation sur son identité ou ses fichiers.
        """
        projet = getattr(config, "JIBI_PROJET_DIR", None)
        root = Path(str(projet)).resolve() if projet else Path.cwd()

        fichiers_a_tester = [
            root / "core" / "prompts.py",
            root / "core" / "agent_core.py",
            root / "self_improvement" / "gestionnaire.py",
        ]

        lecture_ok: list[dict[str, Any]] = []
        for fichier in fichiers_a_tester:
            try:
                ok = (
                    fichier.exists()
                    and fichier.is_file()
                    and os.access(fichier, os.R_OK)
                )
            except Exception:
                ok = False

            lecture_ok.append({
                "fichier": str(fichier),
                "ok": bool(ok),
            })

        return {
            "identite": "assistant IA locale",
            "projet": str(root),
            "acces_code": any(item["ok"] for item in lecture_ok),
            "lecture_fichiers": lecture_ok,
            "outils_disponibles": bool(self.outils),
            "verification_ok": (
                any(item["ok"] for item in lecture_ok)
                and bool(self.outils)
            ),
        }

    # ========================================================
    # DIAGNOSTIC
    # ========================================================

    def _diagnostic(self) -> ReponseAgent:

        if self._orchestrateur is not None:

            try:
                resultat = (
                    self._orchestrateur.diagnostiquer()
                )

                metadata = getattr(
                    resultat,
                    "__dict__",
                    {},
                ) or {}

                details = metadata.get(
                    "details",
                    {},
                ) or {}

                observation = details.get(
                    "observation"
                )

                diagnostic = details.get(
                    "diagnostic"
                )

                lignes = [
                    "🔍 DIAGNOSTIC JIBI",
                    "",
                    f"État : {getattr(diagnostic, 'niveau', 'INCONNU')}",
                    f"Message : {getattr(diagnostic, 'message', getattr(resultat, 'message', ''))}",
                ]

                if observation is not None:

                    sante = getattr(
                        observation,
                        "sante",
                        None,
                    )

                    if sante is not None:

                        lignes.extend([
                            "",
                            "📊 SANTÉ DU SYSTÈME",
                            f"Score : {getattr(sante, 'score', '?')}/100",
                            f"Niveau : {getattr(sante, 'niveau', '?')}",
                            f"Erreurs : {getattr(sante, 'erreurs', 0)}",
                            f"Avertissements : {getattr(sante, 'warnings', 0)}",
                            f"Patterns récurrents : {getattr(sante, 'patterns_recurrents', 0)}",
                        ])

                hypotheses = getattr(
                    diagnostic,
                    "hypotheses",
                    [],
                ) or []

                fichiers = getattr(
                    diagnostic,
                    "fichiers_candidats",
                    [],
                ) or []

                if hypotheses:

                    lignes.extend([
                        "",
                        "🧠 HYPOTHÈSES",
                    ])

                    lignes.extend(
                        f"• {h}"
                        for h in hypotheses
                    )

                if fichiers:

                    lignes.extend([
                        "",
                        "📁 FICHIERS CONCERNÉS",
                    ])

                    lignes.extend(
                        f"• {f}"
                        for f in fichiers
                    )

                erreurs = getattr(
                    diagnostic,
                    "erreurs_analysees",
                    0,
                )

                warnings = getattr(
                    diagnostic,
                    "warnings_analyses",
                    0,
                )

                lignes.extend([
                    "",
                    "📋 ANALYSE",
                    f"Erreurs analysées : {erreurs}",
                    f"Avertissements analysés : {warnings}",
                ])

                # ------------------------------------------------------
                # Analyse statique complémentaire (detecteur.py)
                #
                # diagnostiquer() ne lit que les logs d'exécution passés ;
                # analyser_et_proposer() fait tourner le vrai détecteur
                # statique (imports morts, complexité, appels dangereux,
                # secrets, incohérences d'architecture...) sur le code
                # source lui-même. Lecture seule, jamais de patch généré
                # ici (modification_production=False côté orchestrateur).
                # ------------------------------------------------------
                groupes_statiques = None

                try:
                    resultat_statique = (
                        self._orchestrateur.analyser_et_proposer(
                            utiliser_llm=False,
                        )
                    )

                    details_statique = getattr(
                        resultat_statique,
                        "details",
                        {},
                    ) or {}

                    groupes_statiques = details_statique.get(
                        "groupes",
                        [],
                    ) or []

                    if getattr(resultat_statique, "ok", False) and groupes_statiques:

                        lignes.extend([
                            "",
                            "🔎 ANALYSE STATIQUE (code source)",
                        ])

                        for groupe in groupes_statiques[:5]:

                            if not isinstance(groupe, dict):
                                continue

                            type_probleme = groupe.get("type", "inconnu")
                            gravite = groupe.get("gravite", "inconnue")
                            nombre = groupe.get("nombre", 0)

                            lignes.append(
                                f"• {type_probleme} "
                                f"({gravite}, {nombre} occurrence(s))"
                            )

                except Exception:
                    logger.exception(
                        "Erreur analyse statique (detecteur) "
                        "lors du diagnostic"
                    )

                if groupes_statiques is not None:
                    metadata = {
                        **metadata,
                        "analyse_statique_groupes": groupes_statiques,
                    }

                return ReponseAgent(
                    "\n".join(lignes),
                    0.95,
                    "DIAGNOSTIC",
                    bool(
                        getattr(
                            resultat,
                            "ok",
                            True,
                        )
                    ),
                    metadata,
                )

            except Exception as exc:

                logger.exception(
                    "Erreur orchestrateur diagnostic"
                )

        if analyser_jibi is not None:

            try:
                analyse = analyser_jibi()

                return ReponseAgent(
                    json.dumps(
                        analyse,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                    0.85,
                    "DIAGNOSTIC",
                    True,
                )

            except Exception as exc:

                return ReponseAgent(
                    f"❌ Analyse impossible : {exc}",
                    0.2,
                    "DIAGNOSTIC",
                    False,
                )

        return ReponseAgent(
            "❌ Le système de diagnostic est indisponible.",
            0.2,
            "DIAGNOSTIC",
            False,
        )

    # ========================================================
    # ÉTAT
    # ========================================================

    def _etat(self) -> ReponseAgent:

        if tableau_de_bord is not None:

            try:
                resultat = tableau_de_bord()

                return ReponseAgent(
                    str(resultat),
                    0.9,
                    "ETAT",
                )

            except Exception as exc:
                logger.debug(
                    "Tableau de bord indisponible : %s",
                    exc,
                )

        if analyser_jibi is not None:

            try:
                analyse = analyser_jibi()

                return ReponseAgent(
                    json.dumps(
                        analyse,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                    0.8,
                    "ETAT",
                )

            except Exception as exc:

                return ReponseAgent(
                    f"❌ État indisponible : {exc}",
                    0.2,
                    "ETAT",
                    False,
                )

        return ReponseAgent(
            "État JIBI indisponible.",
            0.3,
            "ETAT",
            False,
        )

    # ========================================================
    # LISTE
    # ========================================================

    def _liste(self) -> ReponseAgent:

        if self._orchestrateur is None:

            return ReponseAgent(
                "📋 Orchestrateur indisponible.",
                0.3,
                "LISTE",
                False,
            )

        try:
            propositions = (
                self._orchestrateur.lister_propositions()
            )

        except Exception as exc:

            logger.exception(
                "Erreur liste propositions"
            )

            return ReponseAgent(
                f"❌ Impossible de lire les propositions : {exc}",
                0.2,
                "LISTE",
                False,
            )

        if not propositions:

            return ReponseAgent(
                "📋 Aucune proposition disponible.",
                0.8,
                "LISTE",
            )

        lignes = [
            f"📋 {len(propositions)} proposition(s)"
        ]

        for proposition in propositions:

            if isinstance(proposition, dict):

                pid = proposition.get(
                    "id",
                    proposition.get(
                        "proposal_id",
                        "?",
                    ),
                )

                fichier = proposition.get(
                    "fichier",
                    proposition.get(
                        "file",
                        "?",
                    ),
                )

                statut = proposition.get(
                    "statut",
                    proposition.get(
                        "status",
                        "proposition",
                    ),
                )

                lignes.append(
                    f"• [{pid}] "
                    f"{fichier} — "
                    f"{statut}"
                )

            else:
                lignes.append(
                    f"• {proposition}"
                )

        lignes.extend([
            "",
            "J'AUTORISE <id>",
            "Rejette <id>",
        ])

        return ReponseAgent(
            "\n".join(lignes),
            0.95,
            "LISTE",
        )

    # ========================================================
    # ANALYSE CODE
    # ========================================================

    def _analyser_code(
        self,
        message: str,
        plan: Optional[dict] = None,
    ) -> ReponseAgent:
        """
        Analyse un fichier ou module Python sans modification.
        """

        fichier = None

        if isinstance(plan, dict):
            fichier = plan.get("fichier")

        if not fichier:
            match = re.search(
                r"[a-z0-9_/.-]+\.py",
                message.lower(),
            )
            if match:
                fichier = match.group(0)

        if not fichier:
            return ReponseAgent(
                "Quel fichier dois-je analyser ?",
                0.6,
                "ANALYSE_CODE",
            )

        fichier = str(fichier).strip()

        # Vérification sécurité (lecture seule)
        if not securite.valider_securite_fichier(
            fichier,
            modification=False,
        ):
            return ReponseAgent(
                "❌ Fichier refusé par la politique de sécurité.",
                0.1,
                "ANALYSE_CODE",
                False,
                {
                    "fichier": fichier,
                    "securite": False,
                },
            )

        if analyseur_code is None:
            return ReponseAgent(
                "❌ Module d'analyse de code indisponible.",
                0.2,
                "ANALYSE_CODE",
                False,
            )

        try:
            resultat = analyseur_code.analyser_fichier(
                fichier
            )

            # Génération du résumé
            resume = analyseur_code.resume_analyse(
                resultat
            )

            # Ajout de détails si demandé
            details_lignes = []

            if resultat.syntaxe_valide:
                if resultat.classes:
                    details_lignes.append(
                        "\n📦 CLASSES :"
                    )
                    for classe in resultat.classes[:5]:
                        details_lignes.append(
                            f"  • {classe.nom} "
                            f"(ligne {classe.ligne}, "
                            f"{len(classe.methodes)} méthodes)"
                        )
                    if len(resultat.classes) > 5:
                        details_lignes.append(
                            f"  ... et {len(resultat.classes) - 5} autres"
                        )

                if resultat.fonctions:
                    details_lignes.append(
                        "\n🔧 FONCTIONS :"
                    )
                    for fonction in resultat.fonctions[:5]:
                        async_marker = "async " if fonction.async_ else ""
                        args_preview = ", ".join(fonction.arguments[:3])
                        if len(fonction.arguments) > 3:
                            args_preview += "..."
                        details_lignes.append(
                            f"  • {async_marker}{fonction.nom}({args_preview})"
                        )
                    if len(resultat.fonctions) > 5:
                        details_lignes.append(
                            f"  ... et {len(resultat.fonctions) - 5} autres"
                        )

                if resultat.imports:
                    details_lignes.append(
                        f"\n📥 IMPORTS : {len(resultat.imports)} modules"
                    )

            texte_final = resume
            if details_lignes:
                texte_final += "\n" + "\n".join(details_lignes)

            return ReponseAgent(
                texte_final,
                0.95,
                "ANALYSE_CODE",
                resultat.syntaxe_valide,
                {
                    "fichier": fichier,
                    "analyse": resultat.to_dict(),
                },
            )

        except Exception as exc:
            logger.exception(
                "Erreur analyse code"
            )

            return ReponseAgent(
                f"❌ Erreur d'analyse : {exc}",
                0.2,
                "ANALYSE_CODE",
                False,
            )

    # ========================================================
    # QUESTION
    # ========================================================

    def _question(
        self,
        message: str,
        on_chunk: Optional[Callable[[str], None]] = None,
        cancel_event: Any = None,
    ) -> ReponseAgent:

        try:
            texte = cerveau.completer(
                message,
                profil="QUESTION",
                stream=bool(on_chunk),
                on_chunk=on_chunk,
                cancel_event=cancel_event,
            )

            return ReponseAgent(
                texte,
                0.9,
                "QUESTION",
            )

        except Exception as exc:

            logger.exception(
                "Erreur LLM question"
            )

            return ReponseAgent(
                f"❌ Erreur LLM : {exc}",
                0.2,
                "QUESTION",
                False,
            )

    # ========================================================
    # TÂCHE COMPLEXE
    # ========================================================

    def _tache_complexe(
        self,
        message: str,
        plan: Optional[dict] = None,
    ) -> ReponseAgent:

        if isinstance(plan, dict) and plan:

            return ReponseAgent(
                json.dumps(
                    plan,
                    ensure_ascii=False,
                    indent=2,
                ),
                0.75,
                "TACHE_COMPLEXE",
            )

        try:
            nouveau_plan = cerveau.planifier(
                message
            )

            nouveau_plan = router.extraire_plan(
                nouveau_plan
            )

            return ReponseAgent(
                json.dumps(
                    nouveau_plan,
                    ensure_ascii=False,
                    indent=2,
                ),
                0.75,
                "TACHE_COMPLEXE",
            )

        except Exception as exc:

            return ReponseAgent(
                f"❌ Planification impossible : {exc}",
                0.2,
                "TACHE_COMPLEXE",
                False,
            )

    # ========================================================
    # MODIFICATION FICHIER
    # ========================================================

    def _modifier_fichier(
        self,
        message: str,
        plan: Optional[dict] = None,
    ) -> ReponseAgent:

        if self._orchestrateur is None:

            return ReponseAgent(
                "❌ Orchestrateur indisponible.",
                0.2,
                "MODIFIER_FICHIER",
                False,
            )

        fichier = None

        if isinstance(plan, dict):
            fichier = plan.get(
                "fichier"
            )

        if not fichier:

            match = re.search(
                r"(?:fichier|file)\s+[`\"']?([^`\"'\s]+)",
                message,
                re.IGNORECASE,
            )

            if match:
                fichier = match.group(1)

        if not fichier:
            # Raccourcis pour les composants que l'utilisateur désigne
            # habituellement par leur fonctionnalité plutôt que par un chemin.
            # La proposition reste soumise au laboratoire et à autorisation.
            fonctionnalites = {
                "voix": "voix.py",
                "audio": "voix.py",
                "interface": "gui.py",
                "gui": "gui.py",
                "mémoire": "memory_manager.py",
                "memoire": "memory_manager.py",
                "base de données": "database.py",
                "database": "database.py",
                "agent": "core/agent_core.py",
                "outils": "tools/tool_registry.py",
            }
            message_lower = message.lower()
            for nom, chemin in fonctionnalites.items():
                if nom in message_lower:
                    fichier = chemin
                    break

        fichiers_lot = plan.get("fichiers") if isinstance(plan, dict) else None
        if not isinstance(fichiers_lot, list):
            fichiers_lot = re.findall(
                r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_./-]+\.py\b",
                message,
            )
        if isinstance(fichiers_lot, list) and len(fichiers_lot) > 1:
            return self._modifier_lot(message, fichiers_lot)

        if not fichier:
            analyse = self._orchestrateur.analyser_et_proposer(
                objectif=message,
                utiliser_llm=False,
            )
            details = getattr(analyse, "details", {}) or {}
            groupes = details.get("groupes", [])
            resume = "\n".join(
                f"• {g.get('type', 'problème')} ({g.get('gravite', 'inconnue')})"
                for g in groupes[:5] if isinstance(g, dict)
            ) or "Aucun problème statique prioritaire détecté."
            return ReponseAgent(
                "Diagnostic préparé sans modifier le projet. Indique le fichier "
                "à modifier pour générer une proposition contrôlée.\n" + resume,
                0.8,
                "MODIFIER_FICHIER",
                bool(getattr(analyse, "ok", False)),
                {"analyse": details, "ecriture": False},
            )

        fichier = str(fichier).strip()

        if not securite.valider_securite_fichier(
            fichier,
            modification=True,
        ):
            return ReponseAgent(
                "❌ Fichier refusé par la politique de sécurité.",
                0.1,
                "MODIFIER_FICHIER",
                False,
                {
                    "fichier": fichier,
                    "securite": False,
                },
            )

        try:

            resultat = (
                self._orchestrateur.preparer_reparation(
                    fichier=fichier,
                    demande=message,
                )
            )

            # Une demande explicite de l'utilisateur peut terminer son cycle
            # automatiquement lorsque le niveau d'auto-réparation l'autorise.
            # workflow() conserve le laboratoire, la validation, l'analyse de
            # risque, le backup et le rollback de l'orchestrateur.
            details = getattr(resultat, "details", {}) or {}
            proposition_id = details.get("proposition_id")

            if (
                getattr(resultat, "ok", False)
                and proposition_id
                and getattr(config, "AUTO_REPAIR_LEVEL", 0) >= 5
            ):
                resultat = self._orchestrateur.workflow(
                    str(proposition_id)
                )

            return ReponseAgent(
                str(
                    getattr(
                        resultat,
                        "message",
                        resultat,
                    )
                ),
                0.85,
                "MODIFIER_FICHIER",
                bool(
                    getattr(
                        resultat,
                        "ok",
                        True,
                    )
                ),
                getattr(
                    resultat,
                    "__dict__",
                    {},
                ),
            )

        except Exception as exc:

            logger.exception(
                "Préparation modification impossible"
            )

            return ReponseAgent(
                f"❌ Préparation impossible : {exc}",
                0.2,
                "MODIFIER_FICHIER",
                False,
            )

    def _modifier_lot(
        self,
        message: str,
        fichiers: list[Any],
    ) -> ReponseAgent:
        """Prépare puis applique un lot multi-fichiers éligible."""
        cibles = [str(fichier).strip() for fichier in fichiers if str(fichier).strip()]
        if not cibles or not all(
            securite.valider_securite_fichier(fichier, modification=True)
            for fichier in cibles
        ):
            return ReponseAgent(
                "❌ Un fichier du lot est refusé par la politique de sécurité.",
                0.1, "MODIFIER_FICHIER", False,
            )
        try:
            preparation = self._orchestrateur.preparer_lot_reparation(cibles, message)
            if not preparation.ok:
                return ReponseAgent(preparation.message, 0.3, "MODIFIER_FICHIER", False, preparation.details)
            ids = preparation.details.get("proposition_ids", [])
            if getattr(config, "AUTO_REPAIR_LEVEL", 0) >= 5:
                resultat = self._orchestrateur.appliquer_lot(ids)
                return ReponseAgent(resultat.message, 0.85, "MODIFIER_FICHIER", resultat.ok, resultat.details)
            return ReponseAgent(preparation.message, 0.85, "MODIFIER_FICHIER", True, preparation.details)
        except Exception as exc:
            logger.exception("Préparation lot impossible")
            return ReponseAgent(f"❌ Préparation du lot impossible : {exc}", 0.2, "MODIFIER_FICHIER", False)

    # ========================================================
    # CRÉATION OUTIL
    # ========================================================

    def _creer_outil(
        self,
        message: str,
        plan: Optional[dict] = None,
    ) -> ReponseAgent:

        nom = None
        description = message

        if isinstance(plan, dict):

            nom = plan.get(
                "nom_outil"
            )

            description = plan.get(
                "description",
                message,
            )

        if not nom:

            match = re.search(
                r"(?:outil|fonction|tool)\s+"
                r"([a-zA-Z_][a-zA-Z0-9_]*)",
                message,
                re.IGNORECASE,
            )

            if match:
                nom = match.group(1)

        if not nom:

            return ReponseAgent(
                "Quel est le nom de l'outil ?",
                0.6,
                "CREER_OUTIL",
            )

        nom = str(nom).strip()

        if not re.fullmatch(
            r"[a-zA-Z_][a-zA-Z0-9_]{0,63}",
            nom,
        ):
            return ReponseAgent(
                "❌ Nom d'outil invalide.",
                0.1,
                "CREER_OUTIL",
                False,
            )

        if nom in self.outils:

            return ReponseAgent(
                f"❌ L'outil existe déjà : {nom}",
                0.1,
                "CREER_OUTIL",
                False,
            )

        try:

            code = cerveau.creer_outil(
                nom,
                str(
                    description or message
                ),
            )

        except Exception as exc:

            logger.exception(
                "Génération outil impossible"
            )

            return ReponseAgent(
                f"❌ Création impossible : {exc}",
                0.2,
                "CREER_OUTIL",
                False,
            )

        return ReponseAgent(
            "🛠️ Outil généré comme proposition. "
            "Il doit être validé et testé avant toute installation.",
            0.8,
            "CREER_OUTIL",
            True,
            {
                "nom": nom,
                "code": code,
                "production_modifiee": False,
                "installe": False,
                "necessite_validation": True,
            },
        )

    # ========================================================
    # EXÉCUTION OUTIL
    # ========================================================

    def _executer(
        self,
        message: str,
        plan: 