from __future__ import annotations

"""
JIBI - Orchestrateur d'évolution v3
===================================

Orchestrateur central de l'auto-réparation de JIBI.

Flux :

    observation
        ↓
    diagnostic
        ↓
    génération
        ↓
    proposition
        ↓
    laboratoire
        ↓
    validation
        ↓
    analyse risque
        ↓
    autorisation
        ↓
    backup
        ↓
    application
        ↓
    validation post-application
        ↓
    rollback éventuel
        ↓
    état / mémoire

IMPORTANT :
    - L'orchestrateur coordonne.
    - Le cerveau génère.
    - Le diagnostiqueur analyse.
    - Le laboratoire teste.
    - Le validateur vérifie.
    - Le moteur de risque décide du niveau de risque.
    - L'autorisation contrôle l'accord.
    - versions gère les backups/restaurations.
    - L'orchestrateur ne laisse jamais le LLM écrire directement en production.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import ast
import textwrap
import hashlib
import json
import re
import shutil
import tempfile


# ============================================================================
# IMPORTS
# ============================================================================

try:
    from core import config
except Exception:
    config = None


from self_improvement import (
    analyseur,
    analyseur_code,
    autorisation,
    detecteur,
    laboratoire,
    propositions,
    risk_engine,
    validateur,
    versions,
)

try:
    from self_improvement import generateur_patch
except Exception:
    generateur_patch = None

try:
    from self_improvement import testeur
except Exception:
    testeur = None

try:
    from self_improvement import observateur
except Exception:
    observateur = None

try:
    from self_improvement import diagnostiqueur
except Exception:
    diagnostiqueur = None

try:
    from core import cerveau
except Exception:
    cerveau = None

try:
    from self_improvement import politiques
except Exception:
    politiques = None


# ============================================================================
# RESULTAT
# ============================================================================

@dataclass
class ResultatOrchestration:
    ok: bool
    etape: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "etape": self.etape,
            "message": self.message,
            "details": self.details,
        }


# ============================================================================
# ORCHESTRATEUR
# ============================================================================

class OrchestrateurEvolution:
    """
    Orchestrateur central de l'auto-réparation de JIBI.
    """

    def __init__(
        self,
        depot: Optional[str | Path] = None,
    ):
        if depot is None:

            if config is not None:
                depot = getattr(
                    config,
                    "PROJECT_ROOT",
                    None,
                )

            if not depot:
                depot = Path.cwd()

        self.depot = Path(
            depot
        ).resolve()

    # ========================================================================
    # CHEMINS
    # ========================================================================

    def _relatif(
        self,
        chemin: str | Path,
    ) -> str:

        try:
            path = Path(
                chemin
            ).resolve()

            return path.relative_to(
                self.depot
            ).as_posix()

        except ValueError:
            return str(chemin)

    def _chemin(
        self,
        fichier: str | Path,
    ) -> Path:
        """
        Résout un fichier dans le projet.

        Toute tentative de sortie du projet est refusée.
        """

        chemin = Path(
            fichier
        )

        if not chemin.is_absolute():
            chemin = self.depot / chemin

        chemin = chemin.resolve()

        try:
            chemin.relative_to(
                self.depot
            )
        except ValueError:
            raise ValueError(
                "Chemin hors du projet."
            )

        return chemin

    # ========================================================================
    # SECURITE
    # ========================================================================

    def _est_protege(
        self,
        chemin: Path,
    ) -> bool:
        """
        Détermine si un fichier ne doit jamais être modifié.
        """

        try:
            chemin = chemin.resolve()

            chemin.relative_to(
                self.depot
            )

        except ValueError:
            return True

        # --------------------------------------------------------------------
        # Politique centralisée si disponible.
        # --------------------------------------------------------------------

        if politiques is not None:

            try:

                fonction = getattr(
                    politiques,
                    "politique_fichier",
                    None,
                )

                if callable(fonction):

                    resultat = fonction(
                        self._relatif(chemin)
                    )

                    if isinstance(
                        resultat,
                        dict,
                    ):
                        if not resultat.get(
                            "autorise",
                            resultat.get(
                                "ok",
                                True,
                            ),
                        ):
                            return True

                    elif isinstance(
                        resultat,
                        tuple,
                    ):
                        if resultat and not bool(
                            resultat[0]
                        ):
                            return True

                    elif resultat is False:
                        return True

            except Exception:
                return True

        # --------------------------------------------------------------------
        # Protections de secours.
        # --------------------------------------------------------------------

        parties = {
            p.lower()
            for p in chemin.parts
        }

        dossiers_proteges = {
            ".git",
            ".hg",
            ".svn",
            ".venv",
            "venv",
            "env",
            "__pycache__",
            "node_modules",
        }

        if parties.intersection(
            dossiers_proteges
        ):
            return True

        fichiers_proteges = {
            ".env",
            ".env.local",
            ".env.production",
            "requirements.txt",
            "pyproject.toml",
            "poetry.lock",
            "uv.lock",
            "package.json",
            "package-lock.json",
        }

        if chemin.name.lower() in fichiers_proteges:
            return True

        # L'auto-réparation actuelle cible uniquement Python.
        if chemin.suffix.lower() != ".py":
            return True

        # --------------------------------------------------------------------
        # Compatibilité avec config.py.
        # --------------------------------------------------------------------

        if config is not None:

            try:

                fonction = getattr(
                    config,
                    "valider_securite_fichier",
                    None,
                )

                if callable(fonction):

                    resultat = fonction(
                        str(chemin)
                    )

                    if isinstance(
                        resultat,
                        tuple,
                    ):
                        return not bool(
                            resultat[0]
                        )

                    return not bool(
                        resultat
                    )

            except Exception:
                return True

        return False

    # ========================================================================
    # HASH
    # ========================================================================

    def _sha256(
        self,
        contenu: str,
    ) -> str:

        return hashlib.sha256(
            contenu.encode("utf-8")
        ).hexdigest()

    # ========================================================================
    # LECTURE
    # ========================================================================

    def _lire(
        self,
        chemin: Path,
    ) -> str:

        return chemin.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

    # ========================================================================
    # PHASE 1 - ANALYSER ET PROPOSER
    # ========================================================================

    def analyser_et_proposer(
        self,
        objectif: str = "Améliorer la qualité du code",
        utiliser_llm: bool = True,
    ) -> ResultatOrchestration:
        """
        Analyse complète du projet et produit des pistes d'amélioration.

        Aucun fichier de production n'est modifié.
        """

        try:
            if analyseur_code is None:
                return ResultatOrchestration(
                    False,
                    "analyse",
                    "Analyseur de code indisponible.",
                )

            if detecteur is None:
                return ResultatOrchestration(
                    False,
                    "analyse",
                    "Détecteur de problèmes indisponible.",
                )

            # ---------------------------------------------------------------
            # 1. Analyse structurelle du projet
            # ---------------------------------------------------------------

            analyse = analyseur_code.analyser_projet(
                self.depot
            )

            # ---------------------------------------------------------------
            # 2. Détection des problèmes
            # ---------------------------------------------------------------

            problemes = detecteur.detecter_problemes(
                analyse
            )

            if not isinstance(
                problemes,
                list,
            ):
                problemes = list(
                    problemes or []
                )

            # ---------------------------------------------------------------
            # 3. Regroupement déterministe
            # ---------------------------------------------------------------

            groupes = detecteur.regrouper_problemes(
                problemes,
                max_groupes=5,
            )

            if not isinstance(
                groupes,
                list,
            ):
                groupes = list(
                    groupes or []
                )

            # ---------------------------------------------------------------
            # 4. Analyse LLM optionnelle
            # ---------------------------------------------------------------

            resultat_llm = None
            llm_utilise = False

            if utiliser_llm and cerveau is not None:

                fonction = getattr(
                    cerveau,
                    "analyser_problemes_resultat",
                    None,
                )

                if callable(fonction):

                    try:
                        resultat_llm = fonction(
                            problemes,
                            objectif=objectif,
                        )
                        llm_utilise = True

                    except Exception as exc:
                        resultat_llm = {
                            "_fallback": True,
                            "_llm_utilise": False,
                            "_erreur": str(exc),
                        }

            # ---------------------------------------------------------------
            # 5. Fallback local
            # ---------------------------------------------------------------

            if resultat_llm is None:
                resultat_llm = self._fallback_groupes(
                    groupes,
                    objectif,
                )

            return ResultatOrchestration(
                True,
                "analyse",
                "Analyse du projet terminée.",
                {
                    "objectif": objectif,
                    "analyse": analyse,
                    "problemes": problemes,
                    "groupes": groupes,
                    "resultat": resultat_llm,
                    "llm": llm_utilise,
                    "modification_production": False,
                },
            )

        except Exception as exc:

            return ResultatOrchestration(
                False,
                "analyse",
                f"Échec de l'analyse : {exc}",
            )

    def _fallback_groupes(
        self,
        groupes,
        objectif: str,
    ) -> dict:
        """
        Résultat déterministe quand le LLM n'est pas utilisé
        ou échoue.
        """

        resultat = {
            "_fallback": True,
            "_llm_utilise": False,
            "objectif": objectif,
            "resume": "",
            "problemes_racines": [],
            "ameliorations": [],
        }

        if not groupes:
            resultat["resume"] = (
                "Aucun groupe de problèmes détecté."
            )
            return resultat

        descriptions = []

        for groupe in groupes[:5]:

            if not isinstance(
                groupe,
                dict,
            ):
                continue

            type_probleme = str(
                groupe.get(
                    "type",
                    "inconnu",
                )
            )

            gravite = str(
                groupe.get(
                    "gravite",
                    "inconnue",
                )
            )

            nombre = int(
                groupe.get(
                    "nombre",
                    0,
                )
                or 0
            )

            fichiers = groupe.get(
                "fichiers",
                [],
            )

            if not isinstance(
                fichiers,
                list,
            ):
                fichiers = []

            descriptions.append(
                f"{type_probleme} "
                f"({gravite}, {nombre} problème(s))"
            )

            resultat[
                "problemes_racines"
            ].append(
                {
                    "type": type_probleme,
                    "gravite": gravite,
                    "nombre": nombre,
                    "fichiers": fichiers[:10],
                    "ids": groupe.get(
                        "ids",
                        [],
                    )[:10],
                }
            )

            if len(
                resultat["ameliorations"]
            ) < 3:

                resultat[
                    "ameliorations"
                ].append(
                    {
                        "type": type_probleme,
                        "fichiers": fichiers[:5],
                        "action": (
                            "Analyser puis proposer "
                            "une correction minimale."
                        ),
                    }
                )

        resultat["resume"] = (
            "Groupes détectés : "
            + ", ".join(descriptions)
        )

        return resultat

    # ========================================================================
    # PHASE 2 - GENERATION DES PATCHES
    # ========================================================================

    def _collecter_unites_code(
        self,
        contenu: str,
        max_unites: int | None = 8,
        max_lignes: int = 220,
    ) -> list[dict[str, Any]]:
        """
        Extrait de petites unités Python réellement remplaçables.

        Le LLM ne reçoit jamais le fichier complet : il reçoit uniquement
        les unités candidates nécessaires pour choisir une cible précise.
        """
        try:
            arbre = ast.parse(contenu)
        except SyntaxError as exc:
            raise RuntimeError(
                f"Impossible de cibler le code : syntaxe actuelle invalide ({exc.msg})."
            ) from exc

        lignes = contenu.splitlines()
        unites: list[dict[str, Any]] = []

        def visiter_noeud(node: ast.AST, parent: str = "") -> None:
            if not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                return

            nom = getattr(node, "name", "")
            qualifie = f"{parent}.{nom}" if parent else nom

            debut = min(
                [
                    getattr(node, "lineno", 1),
                    *[
                        getattr(decorateur, "lineno", getattr(node, "lineno", 1))
                        for decorateur in getattr(node, "decorator_list", [])
                    ],
                ]
            ) - 1
            fin = getattr(node, "end_lineno", None)

            if fin is None:
                return

            nombre_lignes = fin - debut

            if 3 <= nombre_lignes <= max_lignes:
                code = "\n".join(lignes[debut:fin]) + "\n"
                unites.append(
                    {
                        "id": qualifie,
                        "nom": nom,
                        "type": (
                            "classe"
                            if isinstance(node, ast.ClassDef)
                            else "fonction"
                        ),
                        "ligne_debut": debut + 1,
                        "ligne_fin": fin,
                        "nombre_lignes": nombre_lignes,
                        "code": code,
                    }
                )

            # On descend dans les classes pour permettre le ciblage d'une
            # méthode sans envoyer la classe entière au modèle.
            if isinstance(node, ast.ClassDef):
                for enfant in node.body:
                    visiter_noeud(enfant, qualifie)

        for noeud in arbre.body:
            visiter_noeud(noeud)

        # On privilégie les unités courtes : elles sont plus sûres à réécrire
        # avec un budget de sortie limité.
        unites.sort(
            key=lambda item: (
                item["nombre_lignes"],
                item["ligne_debut"],
                item["id"],
            )
        )

        return unites[:max_unites] if max_unites is not None else unites

    def _normaliser_cible_demandee(
        self,
        contexte: dict[str, Any],
    ) -> Optional[str]:
        """Récupère un symbole explicite depuis le contexte de génération."""
        if not isinstance(contexte, dict):
            return None

        cles = (
            "cible",
            "symbole",
            "fonction",
            "classe",
            "nom_fonction",
            "nom_classe",
        )

        for cle in cles:
            valeur = contexte.get(cle)
            if isinstance(valeur, str) and valeur.strip():
                return valeur.strip()

        groupe = contexte.get("groupe")
        if isinstance(groupe, dict):
            for cle in cles:
                valeur = groupe.get(cle)
                if isinstance(valeur, str) and valeur.strip():
                    return valeur.strip()

        return None

    def _remplacer_unite_code(
        self,
        contenu: str,
        unite: dict[str, Any],
        remplacement: str,
    ) -> str:
        """
        Remplace exactement une fonction/méthode/classe ciblée.
        Aucun autre bloc du fichier n'est modifié ici.
        """
        if not isinstance(remplacement, str):
            raise ValueError("Le remplacement généré n'est pas textuel.")

        remplacement = remplacement.strip()

        extraction = getattr(cerveau, "extraire_code", None)
        if callable(extraction):
            remplacement = extraction(remplacement).strip()

        if not remplacement:
            raise ValueError("Le remplacement généré est vide.")

        try:
            arbre_remplacement = ast.parse(remplacement)
        except SyntaxError as exc:
            raise ValueError(
                f"Remplacement syntaxiquement invalide : {exc.msg}."
            ) from exc

        noeuds = [
            noeud
            for noeud in arbre_remplacement.body
            if isinstance(
                noeud,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            )
        ]

        if len(noeuds) != 1:
            raise ValueError(
                "Le remplacement doit contenir exactement une fonction, méthode ou classe."
            )

        noeud = noeuds[0]
        type_attendu = "classe" if isinstance(noeud, ast.ClassDef) else "fonction"
        if type_attendu != unite.get("type"):
            raise ValueError(
                "Le type de l'unité générée ne correspond pas à la cible."
            )

        if getattr(noeud, "name", "") != unite.get("nom"):
            raise ValueError(
                "Le nom de l'unité générée ne correspond pas à la cible."
            )

        source_lignes = contenu.splitlines()
        debut = int(unite["ligne_debut"]) - 1
        fin = int(unite["ligne_fin"])

        if debut < 0 or fin > len(source_lignes) or debut >= fin:
            raise ValueError("Bornes de remplacement invalides.")

        ancienne_premiere_ligne = source_lignes[debut]
        indentation = ancienne_premiere_ligne[:
            len(ancienne_premiere_ligne)
            - len(ancienne_premiere_ligne.lstrip())
        ]

        remplacement = textwrap.dedent(
            remplacement
        ).strip("\n")

        nouvelles_lignes = remplacement.splitlines()
        remplacement_indente = "\n".join(
            (
                indentation + ligne
                if ligne.strip()
                else ""
            )
            for ligne in nouvelles_lignes
        )

        source_lignes[debut:fin] = remplacement_indente.splitlines()
        return "\n".join(source_lignes) + "\n"

    def _generer_nouveau_code(
        self,
        fichier: str,
        objectif: str,
        contexte: dict | None = None,
    ) -> str:
        """
        Génère une modification ciblée au lieu de réécrire tout le fichier.

        Le LLM reçoit uniquement :
        - le chemin du fichier ;
        - l'objectif ;
        - un contexte limité ;
        - une petite liste de fonctions/classes candidates.

        Il renvoie une cible + un remplacement. Le remplacement est ensuite
        fusionné localement dans le fichier original. Le fichier réel n'est
        jamais écrit par cette méthode.
        """
        if cerveau is None:
            raise RuntimeError("Module cerveau indisponible.")

        chemin = self._chemin(fichier)

        if not chemin.exists():
            raise FileNotFoundError(
                f"Fichier introuvable : {chemin}"
            )

        contenu_actuel = self._lire(chemin)
        contexte = contexte or {}

        cible_demandee = self._normaliser_cible_demandee(contexte)
        # Collecte complète avant filtrage : une cible nommée ne doit jamais
        # disparaître parce qu'elle n'est pas parmi les fonctions les plus
        # courtes du fichier.
        unites = self._collecter_unites_code(
            contenu_actuel,
            max_unites=None,
        )

        if cible_demandee:
            exactes = [
                unite
                for unite in unites
                if unite["id"] == cible_demandee
                or unite["nom"] == cible_demandee
            ]
            if exactes:
                unites = exactes[:1]

        # Sans symbole explicite, un petit ensemble réduit le bruit et évite
        # de dépasser le contexte du modèle. Les propositions automatiques
        # restent donc limitées à des modifications courtes et contrôlables.
        if not cible_demandee:
            mots_objectif = {
                mot.lower()
                for mot in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", objectif)
                if len(mot) > 2
            }
            unites.sort(
                key=lambda unite: (
                    0 if unite["nom"].lower() in mots_objectif else 1,
                    unite["nombre_lignes"],
                    unite["ligne_debut"],
                )
            )
            unites = unites[:4]

        if not unites:
            raise RuntimeError(
                "Aucune petite unité Python ciblable (fonction/méthode/classe) n'a été trouvée."
            )

        contexte_limite = {
            cle: valeur
            for cle, valeur in contexte.items()
            if cle not in {"contenu", "ancien", "nouveau"}
        }

        candidats = []
        for unite in unites:
            candidats.append(
                {
                    "id": unite["id"],
                    "type": unite["type"],
                    "lignes": f"{unite['ligne_debut']}-{unite['ligne_fin']}",
                    "code": unite["code"],
                }
            )

        prompt = f"""
Tu es le générateur de patch ciblé de JIBI.

Fichier : {self._relatif(chemin)}
Objectif : {objectif}
Contexte : {json.dumps(contexte_limite, ensure_ascii=False, default=str)}

Tu dois modifier UNE SEULE unité parmi les candidates ci-dessous.
La valeur de « cible » DOIT être exactement l’identifiant « id » d’une candidate.
Tu dois conserver le comportement existant sauf pour l’amélioration demandée.
Ne modifie aucun import global et ne touche à aucune autre fonction.
N'ajoute jamais eval, exec, __import__, os.system ni subprocess.

CANDIDATES :
{json.dumps(candidats, ensure_ascii=False, indent=2)}

Réponds UNIQUEMENT avec un objet JSON valide, sans Markdown et sans texte avant/après :
{{
  "cible": "id exact de la candidate",
  "remplacement": "une seule définition Python complète"
}}

Règles :
- « cible » = valeur exacte de « id ».
- « remplacement » = une seule fonction, méthode ou classe complète.
- Ne mets pas de « ... ».
- Ne renvoie aucun commentaire hors JSON.
"""

        system_patch = (
            "Tu es un moteur de patch Python. "
            "Tu réponds exclusivement avec un objet JSON valide. "
            "Le champ cible doit être une valeur exacte du champ id fourni. "
            "Le champ remplacement doit contenir une seule définition Python complète. "
            "Aucun texte, Markdown ou explication hors du JSON. "
        )

        fonction_json = getattr(
            cerveau,
            "completer_json",
            None,
        )

        if callable(fonction_json):
            resultat = fonction_json(
                prompt,
                system=system_patch,
                profil="PATCH",
                temperature=0.0,
            )
        else:
            fonction = getattr(
                cerveau,
                "completer",
                None,
            )
            if not callable(fonction):
                raise RuntimeError(
                    "Fonction cerveau.completer indisponible."
                )

            brut = fonction(
                    prompt,
                    system=system_patch,
                    profil="PATCH",
                temperature=0.0,
                json_mode=True,
            )

            parseur = getattr(
                cerveau,
                "_extraire_json_objet",
                None,
            )

            resultat = (
                parseur(brut)
                if callable(parseur)
                else None
            )

        def extraire_champs_patch(obj: Any) -> tuple[str, Optional[str]]:
            if not isinstance(obj, dict):
                return "", None

            # Certains modèles encapsulent le résultat dans « patch ».
            imbrique = obj.get("patch")
            if isinstance(imbrique, dict):
                obj = imbrique

            cible_locale = ""
            for cle in (
                "cible",
                "target",
                "id",
                "nom",
                "fonction",
                "classe",
            ):
                valeur = obj.get(cle)
                if isinstance(valeur, str) and valeur.strip():
                    cible_locale = valeur.strip()
                    break

            remplacement_local: Optional[str] = None
            for cle in (
                "remplacement",
                "replacement",
                "code",
                "nouveau",
                "contenu",
            ):
                valeur = obj.get(cle)
                if isinstance(valeur, str) and valeur.strip():
                    remplacement_local = valeur
                    break

            return cible_locale, remplacement_local

        cible, remplacement = extraire_champs_patch(resultat)

        # Deuxième tentative uniquement si le premier JSON est incomplet.
        # Cela évite de relancer le LLM dans les cas normaux.
        if not cible or not isinstance(remplacement, str):
            fonction = getattr(
                cerveau,
                "completer",
                None,
            )

            if callable(fonction):
                prompt_retry = f"""
Retourne UNIQUEMENT ce JSON, avec les deux champs obligatoires :

{{
  "cible": "{unites[0]['id']}",
  "remplacement": "..."
}}

Fichier : {self._relatif(chemin)}
Objectif : {objectif}

Choisis exactement UNE candidate ci-dessous et remplace-la par son code Python complet.
La valeur de cible doit être exactement l'un des ids fournis.

{json.dumps(candidats, ensure_ascii=False, indent=2)}
"""
                brut_retry = fonction(
                    prompt_retry,
                    system=system_patch,
                    profil="CODE",
                    temperature=0.0,
                    json_mode=True,
                )
                parseur = getattr(
                    cerveau,
                    "_extraire_json_objet",
                    None,
                )
                resultat_retry = (
                    parseur(brut_retry)
                    if callable(parseur)
                    else None
                )
                cible, remplacement = extraire_champs_patch(
                    resultat_retry
                )

        if not cible or not isinstance(remplacement, str):
            cles = (
                sorted(resultat.keys())
                if isinstance(resultat, dict)
                else []
            )
            raise RuntimeError(
                "Réponse LLM incomplète : cible/remplacement manquant "
                f"(clés reçues : {cles})."
            )

        correspondances = [
            unite
            for unite in unites
            if unite["id"] == cible
            or unite["nom"] == cible
        ]

        if len(correspondances) != 1:
            raise RuntimeError(
                f"Cible LLM ambiguë ou inconnue : {cible!r}."
            )

        unite = correspondances[0]
        nouveau = self._remplacer_unite_code(
            contenu_actuel,
            unite,
            remplacement,
        )

        if nouveau == contenu_actuel:
            raise RuntimeError(
                "Le patch ciblé ne produit aucun changement."
            )

        # Contrôle final : le fichier complet doit rester syntaxiquement valide.
        try:
            ast.parse(nouveau)
        except SyntaxError as exc:
            raise RuntimeError(
                f"Le fichier complet devient syntaxiquement invalide : {exc.msg}."
            ) from exc

        return nouveau

    def generer_patch_amelioration(
        self,
        fichier: str,
        objectif: str,
        contexte: dict | None = None,
    ) -> ResultatOrchestration:
        """
        Génère un patch et crée une proposition.
        Aucun changement de production.
        """

        try:
            chemin = self._chemin(
                fichier
            )

            if self._est_protege(
                chemin
            ):
                return ResultatOrchestration(
                    False,
                    "generation",
                    "Fichier protégé.",
                    {
                        "fichier": str(chemin),
                    },
                )

            if not chemin.exists():
                return ResultatOrchestration(
                    False,
                    "generation",
                    "Fichier introuvable.",
                    {
                        "fichier": str(chemin),
                    },
                )

            ancien = self._lire(
                chemin
            )

            nouveau = self._generer_nouveau_code(
                fichier,
                objectif,
                contexte,
            )

            if ancien == nouveau:
                return ResultatOrchestration(
                    False,
                    "generation",
                    "Aucune modification proposée.",
                    {
                        "fichier": fichier,
                    },
                )

            # ---------------------------------------------------------------
            # Génération du diff / patch
            # ---------------------------------------------------------------

            diff = ""

            if generateur_patch is not None:

                fonction = getattr(
                    generateur_patch,
                    "patch_depuis_contenu",
                    None,
                )

                if callable(fonction):
                    try:
                        patch_obj = fonction(
                            ancien,
                            nouveau,
                            fichier,
                        )
                    except TypeError:
                        try:
                            patch_obj = fonction(
                                fichier,
                                ancien,
                                nouveau,
                            )
                        except TypeError:
                            patch_obj = None

                    if patch_obj is not None:
                        if isinstance(
                            patch_obj,
                            str,
                        ):
                            diff = patch_obj
                        else:
                            diff = str(
                                getattr(
                                    patch_obj,
                                    "diff",
                                    "",
                                )
                            )

            if not diff:
                import difflib

                diff = "".join(
                    difflib.unified_diff(
                        ancien.splitlines(True),
                        nouveau.splitlines(True),
                        f"a/{fichier}",
                        f"b/{fichier}",
                    )
                )

            # ---------------------------------------------------------------
            # Validation immédiate du nouveau code
            # ---------------------------------------------------------------

            validation = self._valider_contenu(
                nouveau,
                chemin,
            )

            if not validation.get(
                "ok",
                False,
            ):
                return ResultatOrchestration(
                    False,
                    "validation",
                    "Code généré invalide.",
                    {
                        "fichier": fichier,
                        "validation": validation,
                    },
                )

            # ---------------------------------------------------------------
            # Création proposition
            # ---------------------------------------------------------------

            proposition = propositions.creer_proposition(
                fichier=self._relatif(chemin),
                solution=nouveau,
                probleme=objectif,
                origine="cerveau",
                priorite="moyenne",
                raison=objectif,
                source="orchestrateur",
            )

            if isinstance(proposition, dict):
                proposition["categorie"] = "modification"
                proposition["type_probleme"] = "patch"
                proposition["details"] = {
                    "objectif": objectif,
                    "contexte": contexte or {},
                }

            if not isinstance(
                proposition,
                dict,
            ):
                proposition = {
                    "id": str(proposition),
                    "fichier": self._relatif(chemin),
                }

            proposition["ancien"] = ancien
            proposition["nouveau"] = nouveau
            proposition["diff"] = diff
            proposition["objectif"] = objectif
            proposition["validation"] = validation

            sauvegarder = getattr(
                propositions,
                "sauvegarder_proposition",
                None,
            )

            if callable(sauvegarder):
                sauvegarder(
                    proposition
                )

            proposition_id = proposition.get(
                "id"
            )

            return ResultatOrchestration(
                True,
                "proposition",
                "✅ Patch généré et proposition enregistrée.",
                {
                    "proposition_id": proposition_id,
                    "fichier": self._relatif(chemin),
                    "objectif": objectif,
                    "diff": diff,
                    "validation": validation,
                },
            )

        except Exception as exc:

            return ResultatOrchestration(
                False,
                "generation",
                f"Échec génération patch : {exc}",
            )

    def _extraire_cible_objectif(
        self,
        objectif: str,
    ) -> dict[str, str] | None:
        """
        Extrait une cible explicite depuis un objectif utilisateur.

        Exemple reconnu :
            "Améliorer uniquement la lisibilité de normaliser_message
            dans core/router.py sans changer son comportement"

        Retourne un dictionnaire ``fichier`` / ``cible`` uniquement lorsque
        les deux éléments sont suffisamment explicites.
        Aucun appel LLM n'est effectué ici.
        """
        if not isinstance(objectif, str):
            return None

        texte = objectif.strip()
        if not texte:
            return None

        # Recherche d'un chemin Python explicite, relatif au projet.
        match_fichier = re.search(
            r"(?<![\w.-])([A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_.-]+)*\.py)\b",
            texte,
        )
        if not match_fichier:
            return None

        fichier = match_fichier.group(1).replace("\\", "/")

        # Recherche d'un symbole Python explicitement nommé.
        patterns = (
            r"\b(?:fonction|méthode|classe)\s+[`'\"]?([A-Za-z_]\w*)",
            r"\b(?:de|pour|sur)\s+[`'\"]?([A-Za-z_]\w*)\s+(?:dans|du|de)\b",
        )

        cible = None
        for pattern in patterns:
            match_cible = re.search(pattern, texte, re.IGNORECASE)
            if match_cible:
                cible = match_cible.group(1)
                break

        # Cas fréquent : "de normaliser_message dans core/router.py".
        if cible is None:
            avant_fichier = texte[:match_fichier.start()]
            candidats = re.findall(
                r"\b([A-Za-z_]\w*)\b",
                avant_fichier,
            )
            mots_generiques = {
                "améliorer", "ameliorer", "uniquement", "lisibilité",
                "lisibilite", "comportement", "fonctionnalité",
                "fonctionnalite", "sans", "changer", "modifier",
                "dans", "la", "le", "de", "du", "pour",
                "sur", "classe", "fonction", "méthode", "methode",
            }
            candidats = [
                mot
                for mot in candidats
                if mot.lower() not in mots_generiques
            ]
            if candidats:
                # Le dernier identifiant avant le chemin est généralement la cible.
                cible = candidats[-1]

        if not cible:
            return None

        try:
            chemin = self._chemin(fichier)
        except (ValueError, TypeError):
            return None

        if not chemin.exists() or chemin.suffix.lower() != ".py":
            return None

        return {
            "fichier": self._relatif(chemin),
            "cible": cible,
        }

    def generer_patches_pour_analyse(
        self,
        analyse: dict,
    ) -> ResultatOrchestration:
        """
        Génère des propositions à partir des groupes produits par la Phase 1.

        Si l'objectif utilisateur contient une cible explicite (symbole +
        fichier), cette cible devient prioritaire sur les groupes globaux
        détectés dans tout le projet. Cela évite, par exemple, de modifier
        ``self_improvement/orchestrateur.py`` simplement parce qu'il contient
        le premier groupe de complexité alors que l'utilisateur demande
        ``normaliser_message`` dans ``core/router.py``.
        """

        if not isinstance(analyse, dict):
            return ResultatOrchestration(
                False,
                "generation",
                "Analyse invalide.",
            )

        objectif = str(
            analyse.get(
                "objectif",
                "Améliorer la qualité du code",
            )
        ).strip()

        groupes = analyse.get("groupes", [])
        if not isinstance(groupes, list):
            groupes = []

        propositions_creees: list[str] = []
        erreurs: list[dict[str, Any]] = []

        # ------------------------------------------------------------------
        # Priorité absolue à une cible explicitement demandée.
        # ------------------------------------------------------------------
        cible_explicite = self._extraire_cible_objectif(objectif)

        if cible_explicite:
            fichiers_cibles = [cible_explicite["fichier"]]
            contexte_cible = {
                "cible": cible_explicite["cible"],
                "fichier_cible": cible_explicite["fichier"],
                "source": "objectif_utilisateur",
                "problemes": [],
            }

            for fichier in fichiers_cibles:
                resultat = self.generer_patch_amelioration(
                    fichier=fichier,
                    objectif=objectif,
                    contexte=contexte_cible,
                )

                if resultat.ok:
                    pid = resultat.details.get("proposition_id")
                    if pid:
                        propositions_creees.append(pid)
                else:
                    erreurs.append({
                        "fichier": fichier,
                        "cible": cible_explicite["cible"],
                        "message": resultat.message,
                    })

            return ResultatOrchestration(
                bool(propositions_creees),
                "generation",
                (
                    "✅ Patch ciblé généré."
                    if propositions_creees
                    else "Aucun patch ciblé généré."
                ),
                {
                    "propositions": propositions_creees,
                    "erreurs": erreurs,
                    "nombre": len(propositions_creees),
                    "cible_explicite": cible_explicite,
                    "mode": "cible_explicite",
                },
            )

        # ------------------------------------------------------------------
        # Comportement historique : objectifs généraux -> groupes globaux.
        # ------------------------------------------------------------------
        for groupe in groupes[:5]:
            if not isinstance(groupe, dict):
                continue

            fichiers = groupe.get("fichiers", [])
            if not isinstance(fichiers, list):
                fichiers = []

            probleme = groupe.get("type", "amélioration")
            contexte = {
                "groupe": groupe,
                "problemes": groupe.get("ids", []),
            }

            # Un patch par fichier, avec une limite pour éviter de lancer
            # des dizaines de requêtes LLM.
            for fichier in fichiers[:3]:
                if not isinstance(fichier, str):
                    continue

                resultat = self.generer_patch_amelioration(
                    fichier=fichier,
                    objectif=f"{objectif} — problème : {probleme}",
                    contexte=contexte,
                )

                if resultat.ok:
                    pid = resultat.details.get("proposition_id")
                    if pid:
                        propositions_creees.append(pid)
                else:
                    erreurs.append({
                        "fichier": fichier,
                        "message": resultat.message,
                    })

        return ResultatOrchestration(
            bool(propositions_creees),
            "generation",
            (
                "✅ Patches générés."
                if propositions_creees
                else "Aucun patch généré."
            ),
            {
                "propositions": propositions_creees,
                "erreurs": erreurs,
                "nombre": len(propositions_creees),
                "mode": "groupes_globaux",
            },
        )

    # ========================================================================
    # PHASE 3 - LABORATOIRE + VALIDATION
    # ========================================================================

    def _tests_comportement_router(self) -> list[dict]:
        """Jeu de tests comportementaux minimal et sans effet de bord pour router.py.

        Les entrées sont volontairement simples : elles servent à vérifier que le patch
        n'altère pas les réponses existantes pour les chemins normaux.
        """

        return [
            {"nom": "analyse_code", "args": ("analyse mon code Python",), "kwargs": {}},
            {"nom": "discussion", "args": ("bonjour",), "kwargs": {}},
            {"nom": "question", "args": ("question générale",), "kwargs": {}},
            {"nom": "action_dict", "args": ({"action": "ANALYSE_CODE"},), "kwargs": {}},
        ]

    def _charger_module_isole(self, chemin: Path, nom: str):
        """Charge un module Python par chemin, sans modifier sys.modules durablement."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(nom, chemin)
        if spec is None or spec.loader is None:
            raise ImportError(f"Impossible de charger le module : {chemin}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _tester_comportement_router(
        self,
        chemin_production: Path,
        chemin_labo: Path,
    ) -> dict:
        """Compare le comportement de router_message() production/laboratoire."""
        try:
            prod = self._charger_module_isole(
                chemin_production,
                "_jibi_router_production_test",
            )
            lab = self._charger_module_isole(
                chemin_labo,
                "_jibi_router_labo_test",
            )

            fonction_prod = getattr(prod, "router_message", None)
            fonction_lab = getattr(lab, "router_message", None)

            if not callable(fonction_prod) or not callable(fonction_lab):
                return {
                    "ok": True,
                    "applicable": False,
                    "message": "Aucun contrat comportemental router_message applicable.",
                    "tests": [],
                }

            tests = self._tests_comportement_router()
            resultats = []
            divergences = []

            for test in tests:
                try:
                    prod_val = fonction_prod(*test["args"], **test["kwargs"])
                    prod_err = None
                except Exception as exc:
                    prod_val = None
                    prod_err = f"{type(exc).__name__}: {exc}"

                try:
                    lab_val = fonction_lab(*test["args"], **test["kwargs"])
                    lab_err = None
                except Exception as exc:
                    lab_val = None
                    lab_err = f"{type(exc).__name__}: {exc}"

                prod_repr = repr(prod_val) if prod_err is None else f"__EXCEPTION__:{prod_err}"
                lab_repr = repr(lab_val) if lab_err is None else f"__EXCEPTION__:{lab_err}"
                identique = prod_repr == lab_repr

                ligne = {
                    "nom": test["nom"],
                    "production": prod_repr,
                    "laboratoire": lab_repr,
                    "identique": identique,
                }
                resultats.append(ligne)

                if not identique:
                    divergences.append(ligne)

            return {
                "ok": not divergences,
                "applicable": True,
                "message": (
                    "Comportement compatible avec la production."
                    if not divergences
                    else "Divergence comportementale détectée."
                ),
                "tests": resultats,
                "divergences": divergences,
            }

        except Exception as exc:
            return {
                "ok": False,
                "applicable": True,
                "message": f"Erreur pendant le test comportemental : {exc}",
                "tests": [],
            }

    def _tester_comportement(
        self,
        chemin_production: Path,
        chemin_labo: Path,
    ) -> dict:
        """Exécute les contrats comportementaux connus, sinon retourne non applicable."""
        if chemin_production.name.lower() == "router.py":
            return self._tester_comportement_router(
                chemin_production,
                chemin_labo,
            )

        return {
            "ok": True,
            "applicable": False,
            "message": "Aucun contrat comportemental spécifique pour ce fichier.",
            "tests": [],
        }

    def tester_patch_en_laboratoire(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:
        """
        Teste réellement la proposition dans une session laboratoire.
        """

        proposition = self._charger_proposition(
            proposition_id
        )

        if not proposition:
            return ResultatOrchestration(
                False,
                "laboratoire",
                "Proposition introuvable.",
            )

        fichier = proposition.get(
            "fichier"
        )

        nouveau = proposition.get(
            "nouveau"
        )

        if not fichier or not isinstance(
            nouveau,
            str,
        ):
            return ResultatOrchestration(
                False,
                "laboratoire",
                "Proposition invalide.",
            )

        try:
            chemin = self._chemin(
                fichier
            )

            session = laboratoire.creer_session()

            session_path = Path(
                session.get("chemin", session)
                if isinstance(
                    session,
                    dict,
                )
                else session
            ).resolve()

            # ---------------------------------------------------------------
            # Copier le fichier original dans le labo
            # ---------------------------------------------------------------

            copie = laboratoire.copier_fichier_dans_laboratoire(
                chemin,
                session_path,
            )

            copie = Path(
                copie
            ).resolve()

            # ---------------------------------------------------------------
            # Écrire le nouveau contenu UNIQUEMENT dans le labo
            # ---------------------------------------------------------------

            copie.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            copie.write_text(
                nouveau,
                encoding="utf-8",
            )

            # ---------------------------------------------------------------
            # Testeur réel
            # ---------------------------------------------------------------

            rapport = None

            if testeur is not None:

                fonction = getattr(
                    testeur,
                    "tester_fichier",
                    None,
                )

                if callable(fonction):
                    rapport = fonction(
                        copie
                    )

            if rapport is None:
                rapport = self._valider_contenu(
                    nouveau,
                    copie,
                )

            ok = bool(
                rapport.get(
                    "valide",
                    rapport.get(
                        "ok",
                        False,
                    ),
                )
            )

            # ---------------------------------------------------------------
            # Test comportemental
            # ---------------------------------------------------------------

            comportement = self._tester_comportement(
                chemin,
                copie,
            )

            if comportement.get("applicable", False):
                ok = ok and bool(comportement.get("ok", False))

            # ---------------------------------------------------------------
            # Persistance du résultat laboratoire
            # ---------------------------------------------------------------

            proposition_modifiee = dict(proposition)
            proposition_modifiee["tests"] = rapport
            proposition_modifiee["comportement"] = comportement
            proposition_modifiee["laboratoire"] = {
                "ok": bool(ok),
                "session": str(session_path),
                "fichier_labo": str(copie),
                "rapport": rapport,
                "comportement": comportement,
                "date": datetime.now().isoformat(),
            }

            sauvegarder = getattr(
                propositions,
                "sauvegarder_proposition",
                None,
            )

            if callable(sauvegarder):
                try:
                    resultat_sauvegarde = sauvegarder(
                        proposition_modifiee
                    )
                    if isinstance(resultat_sauvegarde, dict):
                        proposition_modifiee = resultat_sauvegarde
                except Exception:
                    pass

            if ok:
                marquer = getattr(
                    propositions,
                    "marquer_testee",
                    None,
                )
                if callable(marquer):
                    try:
                        resultat_marque = marquer(
                            dict(proposition_modifiee),
                            rapport,
                        )
                        if isinstance(resultat_marque, dict):
                            proposition_modifiee = resultat_marque
                            if callable(sauvegarder):
                                try:
                                    sauvegarder(proposition_modifiee)
                                except Exception:
                                    pass
                    except Exception:
                        pass

            return ResultatOrchestration(
                ok,
                "laboratoire",
                (
                    "✅ Test laboratoire réussi."
                    if ok
                    else "❌ Test laboratoire échoué."
                ),
                {
                    "proposition_id": proposition_id,
                    "session": str(session_path),
                    "fichier_labo": str(copie),
                    "rapport": rapport,
                    "comportement": comportement,
                    "laboratoire_ok": bool(ok),
                },
            )

        except Exception as exc:

            return ResultatOrchestration(
                False,
                "laboratoire",
                f"Erreur laboratoire : {exc}",
            )

    def valider_patch(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:
        """
        Alias logique vers la validation existante.
        """

        return self.valider(
            proposition_id
        )

    def tester_et_valider_patch(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        labo = self.tester_patch_en_laboratoire(
            proposition_id
        )

        if not labo.ok:
            return labo

        validation = self.valider_patch(
            proposition_id
        )

        if not validation.ok:
            return validation

        return ResultatOrchestration(
            True,
            "validation",
            "✅ Patch testé et validé.",
            {
                "proposition_id": proposition_id,
                "laboratoire": labo.details,
                "validation": validation.details,
            },
        )

    def nettoyer_laboratoire(
        self,
        session: str | None = None,
    ) -> ResultatOrchestration:

        try:

            if session:

                resultat = laboratoire.supprimer_session(
                    session
                )

                return ResultatOrchestration(
                    bool(resultat),
                    "nettoyage",
                    (
                        "Session laboratoire supprimée."
                        if resultat
                        else "Session introuvable."
                    ),
                    {
                        "session": session,
                    },
                )

            fonction = getattr(
                laboratoire,
                "nettoyer_vieilles_sessions",
                None,
            )

            if callable(
                fonction
            ):
                nombre = fonction()

                return ResultatOrchestration(
                    True,
                    "nettoyage",
                    "Nettoyage du laboratoire effectué.",
                    {
                        "sessions_supprimees": nombre,
                    },
                )

            return ResultatOrchestration(
                False,
                "nettoyage",
                "Fonction de nettoyage indisponible.",
            )

        except Exception as exc:

            return ResultatOrchestration(
                False,
                "nettoyage",
                f"Erreur nettoyage : {exc}",
            )

    # ========================================================================
    # PHASE 4 - RISQUE + AUTORISATION
    # ========================================================================

    def evaluer_risque_patch(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        return self.evaluer_risque(
            proposition_id
        )

    def _calculer_score_risque(
        self,
        proposition: dict[str, Any],
    ) -> float:
        """
        Transforme l'évaluation du moteur de risque
        en score numérique 0-100.
        Plus le score est élevé, plus le risque est important.
        """

        risque = self._evaluer_risque(
            proposition
        )

        niveau = str(
            risque.get(
                "niveau",
                "inconnu",
            )
        ).lower()

        score = {
            "faible": 20.0,
            "moyen": 45.0,
            "élevé": 75.0,
            "critique": 95.0,
        }.get(
            niveau,
            60.0,
        )

        if risque.get(
            "touches_imports",
            False,
        ):
            score += 10.0

        if risque.get(
            "touches_dependances",
            False,
        ):
            score += 15.0

        lignes = int(
            risque.get(
                "lignes_diff",
                0,
            )
            or 0
        )

        limite_diff = 50

        if politiques is not None:
            try:
                limite_diff = int(
                    getattr(
                        politiques,
                        "LIMITE_DIFF_AUTO",
                        50,
                    )
                )
            except Exception:
                limite_diff = 50

        if lignes > limite_diff:
            score += 10.0

        return max(
            0.0,
            min(
                100.0,
                score,
            ),
        )

    def demander_autorisation(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        return self.autoriser(
            proposition_id
        )

    def evaluer_et_autoriser(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        risque = self.evaluer_risque_patch(
            proposition_id
        )

        if not risque.ok:
            return risque

        donnees = risque.details.get(
            "risque",
            {},
        )

        proposition = self._charger_proposition(
            proposition_id
        )

        if not proposition:
            return ResultatOrchestration(
                False,
                "autorisation",
                "Proposition introuvable.",
            )

        score = self._calculer_score_risque(
            proposition
        )

        return ResultatOrchestration(
            True,
            "autorisation",
            "Évaluation terminée.",
            {
                "proposition_id": proposition_id,
                "risque": donnees,
                "score_risque": score,
                "autorisation_requise": (
                    score >= 50.0
                    or not donnees.get(
                        "auto_applicable",
                        False,
                    )
                ),
            },
        )

    # ========================================================================
    # PHASE 5 - APPLICATION + ROLLBACK
    # ========================================================================

    def appliquer_patch_securise(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        return self.appliquer(
            proposition_id
        )

    def _rollback_immediat(
        self,
        chemin: Path,
        backup: Path,
    ) -> bool:

        try:

            resultat = self._restaurer_backup(
                backup
            )

            if isinstance(
                resultat,
                dict,
            ):
                return bool(
                    resultat.get(
                        "ok",
                        False,
                    )
                )

            return bool(
                resultat
            )

        except Exception:
            return False

    def rollback_patch(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        return self.restaurer(
            proposition_id
        )

    # ========================================================================
    # PHASE 6 - AMELIORATION COMPLETE
    # ========================================================================

    def executer_amelioration_complete(
        self,
        objectif: str = "Améliorer la qualité du code",
        utiliser_llm: bool = True,
        auto_appliquer: bool | None = None,
    ) -> ResultatOrchestration:
        """
        Exécute le cycle complet :

        analyse
        → génération
        → laboratoire
        → validation
        → risque
        → autorisation
        → application éventuelle
        """

        # Sans choix explicite de l'appelant, le niveau global pilote le
        # comportement. Le niveau 5 n'autorise que les correctifs déclarés
        # auto-applicables par le moteur de risque.
        if auto_appliquer is None:
            auto_appliquer = bool(
                config is not None
                and getattr(config, "AUTO_REPAIR_LEVEL", 0) >= 5
            )

        # ---------------------------------------------------------------
        # PHASE 1
        # ---------------------------------------------------------------

        analyse = self.analyser_et_proposer(
            objectif=objectif,
            utiliser_llm=utiliser_llm,
        )

        if not analyse.ok:
            return analyse

        # ---------------------------------------------------------------
        # Sauvegarde analyse
        # ---------------------------------------------------------------

        self.sauvegarder_analyse(
            analyse.details
        )

        # ---------------------------------------------------------------
        # PHASE 2
        # ---------------------------------------------------------------

        generation = self.generer_patches_pour_analyse(
            analyse.details
        )

        if not generation.ok:
            return ResultatOrchestration(
                False,
                "generation",
                generation.message,
                {
                    "analyse": analyse.details,
                    "generation": generation.details,
                },
            )

        ids = generation.details.get(
            "propositions",
            [],
        )

        resultats = []

        # ---------------------------------------------------------------
        # PHASES 3 → 5
        # ---------------------------------------------------------------

        for proposition_id in ids:

            test_validation = (
                self.tester_et_valider_patch(
                    proposition_id
                )
            )

            if not test_validation.ok:

                resultats.append(
                    {
                        "proposition_id": proposition_id,
                        "ok": False,
                        "etape": test_validation.etape,
                        "message": test_validation.message,
                    }
                )
                continue

            risque = self.evaluer_et_autoriser(
                proposition_id
            )

            if not risque.ok:

                resultats.append(
                    {
                        "proposition_id": proposition_id,
                        "ok": False,
                        "etape": risque.etape,
                        "message": risque.message,
                    }
                )
                continue

            autorisation_requise = bool(
                risque.details.get(
                    "autorisation_requise",
                    True,
                )
            )

            # -----------------------------------------------------------
            # Application automatique
            # -----------------------------------------------------------

            if auto_appliquer and not autorisation_requise:

                application = (
                    self.appliquer_auto(
                        proposition_id
                    )
                )

                resultats.append(
                    {
                        "proposition_id": proposition_id,
                        "ok": application.ok,
                        "etape": application.etape,
                        "message": application.message,
                        "details": application.details,
                    }
                )

            else:

                resultats.append(
                    {
                        "proposition_id": proposition_id,
                        "ok": True,
                        "etape": "autorisation",
                        "message": (
                            "Patch validé ; "
                            "autorisation requise avant application."
                        ),
                        "risque": risque.details,
                    }
                )

        # ---------------------------------------------------------------
        # Résultat global
        # ---------------------------------------------------------------

        nombre_ok = sum(
            1
            for r in resultats
            if r.get("ok")
        )

        cycle_ok = bool(
            resultats
        ) and nombre_ok > 0

        return ResultatOrchestration(
            cycle_ok,
            "complete",
            (
                "✅ Au moins un patch a été exécuté avec succès."
                if cycle_ok
                else "❌ Aucun patch n'a été exécuté avec succès."
            ),
            {
                "objectif": objectif,
                "analyse": analyse.details,
                "generation": generation.details,
                "propositions": resultats,
                "nombre_propositions": len(ids),
                "nombre_succes": nombre_ok,
                "auto_appliquer": auto_appliquer,
            },
        )

    # ========================================================================
    # UTILITAIRE - SAUVEGARDE ANALYSE
    # ========================================================================

    def sauvegarder_analyse(
        self,
        analyse: dict,
    ) -> Path:

        dossier = (
            self.depot
            / "workspace"
            / "analyses"
        )

        dossier.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        fichier = (
            dossier
            / f"analyse_{timestamp}.json"
        )

        fichier.write_text(
            json.dumps(
                analyse,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        return fichier

    # ========================================================================
    # OBSERVATION
    # ========================================================================

    def observer(
        self,
    ) -> ResultatOrchestration:

        try:

            if observateur is not None:

                fonction = getattr(
                    observateur,
                    "observer",
                    None,
                )

                if callable(fonction):

                    resultat = fonction()

                    return ResultatOrchestration(
                        True,
                        "observation",
                        "Observation effectuée.",
                        {
                            "observation": resultat,
                        },
                    )

            fonction = getattr(
                analyseur,
                "analyser_logs",
                None,
            )

            if callable(fonction):

                resultat = fonction()

                return ResultatOrchestration(
                    True,
                    "observation",
                    "Analyse des logs effectuée.",
                    {
                        "observation": resultat,
                    },
                )

            return ResultatOrchestration(
                False,
                "observation",
                "Aucun observateur disponible.",
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "observation",
                f"Échec de l'observation : {e}",
            )

    # ========================================================================
    # DIAGNOSTIC
    # ========================================================================

    def diagnostiquer(
        self,
    ) -> ResultatOrchestration:

        try:

            observation_resultat = (
                self.observer()
            )

            if not observation_resultat.ok:
                return observation_resultat

            observation = (
                observation_resultat
                .details
                .get("observation")
            )

            if observation is None:

                return ResultatOrchestration(
                    False,
                    "diagnostic",
                    "Observation absente.",
                )

            if diagnostiqueur is not None:

                fonction = getattr(
                    diagnostiqueur,
                    "diagnostiquer",
                    None,
                )

                if callable(fonction):

                    diagnostic = fonction(
                        observation
                    )

                    return ResultatOrchestration(
                        True,
                        "diagnostic",
                        "Diagnostic effectué.",
                        {
                            "observation": observation,
                            "diagnostic": diagnostic,
                        },
                    )

            return ResultatOrchestration(
                False,
                "diagnostic",
                "Diagnostiqueur indisponible.",
                {
                    "observation": observation,
                },
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "diagnostic",
                f"Échec du diagnostic : {e}",
            )

    # ========================================================================
    # GENERATION
    # ========================================================================

    def preparer_reparation(
        self,
        fichier: str,
        demande: str,
    ) -> ResultatOrchestration:

        try:

            chemin = self._chemin(
                fichier
            )

            if not chemin.exists():

                return ResultatOrchestration(
                    False,
                    "generation",
                    "Fichier introuvable.",
                    {
                        "fichier": str(chemin),
                    },
                )

            if not chemin.is_file():

                return ResultatOrchestration(
                    False,
                    "generation",
                    "Le chemin n'est pas un fichier.",
                    {
                        "fichier": str(chemin),
                    },
                )

            if self._est_protege(
                chemin
            ):

                return ResultatOrchestration(
                    False,
                    "securite",
                    "Fichier protégé.",
                    {
                        "fichier": str(chemin),
                    },
                )

            contenu_actuel = self._lire(
                chemin
            )

            if not contenu_actuel.strip():

                return ResultatOrchestration(
                    False,
                    "generation",
                    "Fichier vide.",
                    {
                        "fichier": str(chemin),
                    },
                )

            if cerveau is None:

                return ResultatOrchestration(
                    False,
                    "generation",
                    "Module cerveau indisponible.",
                )

            fonction = getattr(
                cerveau,
                "reecrire_fichier_cible",
                None,
            )

            if not callable(fonction):

                return ResultatOrchestration(
                    False,
                    "generation",
                    "Fonction de génération indisponible.",
                )

            nouveau_contenu = fonction(
                str(chemin),
                contenu_actuel,
                demande,
            )

            if not isinstance(
                nouveau_contenu,
                str,
            ):

                return ResultatOrchestration(
                    False,
                    "generation",
                    "Le cerveau n'a pas produit de texte.",
                )

            if not nouveau_contenu.strip():

                return ResultatOrchestration(
                    False,
                    "generation",
                    "Le cerveau a produit un contenu vide.",
                )

            if (
                nouveau_contenu
                == contenu_actuel
            ):

                return ResultatOrchestration(
                    False,
                    "generation",
                    "Aucune modification proposée.",
                )

            # ---------------------------------------------------------------
            # VALIDATION SYNTAXIQUE IMMÉDIATE
            # ---------------------------------------------------------------

            validation = self._valider_contenu(
                nouveau_contenu,
                chemin,
            )

            if not validation["ok"]:

                return ResultatOrchestration(
                    False,
                    "validation",
                    "Le code généré est invalide.",
                    {
                        "fichier": str(chemin),
                        "rapport": validation,
                    },
                )

            # ---------------------------------------------------------------
            # CREATION PROPOSITION
            # ---------------------------------------------------------------

            fichier_relatif = self._relatif(
                chemin
            )

            proposition = (
                propositions.creer_proposition(
                    fichier=fichier_relatif,
                    solution=nouveau_contenu,
                    probleme=demande,
                    origine="jibi",
                    priorite="moyenne",
                    raison=demande,
                    source=contenu_actuel,
                )
            )

            if not proposition:

                return ResultatOrchestration(
                    False,
                    "proposition",
                    "Impossible de créer la proposition.",
                )

            proposition_id = (
                proposition.get("id")
                if isinstance(
                    proposition,
                    dict,
                )
                else str(proposition)
            )

            risque = self._evaluer_risque(
                proposition
            )

            return ResultatOrchestration(
                True,
                "proposition",
                "✅ Proposition générée et enregistrée.",
                {
                    "proposition_id": proposition_id,
                    "fichier": str(chemin),
                    "demande": demande,
                    "risque": risque,
                    "validation": validation,
                },
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "generation",
                f"Erreur pendant la préparation : {e}",
            )

    # ========================================================================
    # PROPOSITIONS
    # ========================================================================

    def preparer_lot_reparation(
        self,
        fichiers: list[str],
        demande: str,
    ) -> ResultatOrchestration:
        """Prépare une proposition indépendante pour chaque fichier d'un lot."""
        cibles = list(dict.fromkeys(str(fichier).strip() for fichier in fichiers))
        cibles = [fichier for fichier in cibles if fichier]
        if not cibles:
            return ResultatOrchestration(False, "lot", "Aucun fichier cible.")

        propositions_lot: list[str] = []
        for fichier in cibles:
            resultat = self.preparer_reparation(fichier, demande)
            if not resultat.ok:
                return ResultatOrchestration(
                    False, "lot", resultat.message,
                    {"fichier": fichier, "propositions": propositions_lot},
                )
            proposition_id = resultat.details.get("proposition_id")
            if not proposition_id:
                return ResultatOrchestration(False, "lot", "Proposition sans identifiant.")
            propositions_lot.append(str(proposition_id))

        return ResultatOrchestration(
            True, "lot", "Propositions du lot préparées.",
            {"fichiers": cibles, "proposition_ids": propositions_lot},
        )

    def _charger_proposition(
        self,
        proposition_id: str,
    ) -> Optional[dict[str, Any]]:

        try:

            resultat = (
                propositions.charger_proposition(
                    proposition_id
                )
            )

            if isinstance(
                resultat,
                dict,
            ):
                return resultat

        except Exception:
            pass

        return None

    def lister_propositions(
        self,
    ) -> list[dict[str, Any]]:

        resultat: list[
            dict[str, Any]
        ] = []

        try:

            fonction = getattr(
                propositions,
                "lister_propositions",
                None,
            )

            if callable(fonction):

                donnees = fonction()

                if isinstance(
                    donnees,
                    list,
                ):
                    return donnees

        except Exception:
            pass

        # ---------------------------------------------------------------
        # Fallback direct sur le répertoire.
        # ---------------------------------------------------------------

        try:

            dossier = getattr(
                propositions,
                "PROPOSITIONS_DIR",
                self.depot
                / "workspace"
                / "propositions",
            )

            dossier = Path(
                dossier
            )

            if not dossier.exists():
                return []

            for fichier in sorted(
                dossier.glob("*.json"),
                reverse=True,
            ):

                try:

                    data = json.loads(
                        fichier.read_text(
                            encoding="utf-8"
                        )
                    )

                    if isinstance(
                        data,
                        dict,
                    ):
                        resultat.append(
                            data
                        )

                except Exception:
                    continue

        except Exception:
            pass

        return resultat

    def rejeter(
        self,
        proposition_id: str,
        utilisateur: str = "utilisateur",
    ) -> ResultatOrchestration:

        proposition = (
            self._charger_proposition(
                proposition_id
            )
        )

        if not proposition:

            return ResultatOrchestration(
                False,
                "rejet",
                "Proposition introuvable.",
            )

        try:

            fonction = getattr(
                autorisation,
                "rejeter_proposition",
                None,
            )

            if callable(fonction):

                try:
                    resultat = fonction(
                        proposition_id,
                        utilisateur,
                    )
                except TypeError:
                    resultat = fonction(
                        proposition_id
                    )

                return ResultatOrchestration(
                    True,
                    "rejet",
                    "Proposition rejetée.",
                    {
                        "proposition_id": proposition_id,
                        "utilisateur": utilisateur,
                        "resultat": resultat,
                    },
                )

            # -----------------------------------------------------------
            # Fallback : marquage local si disponible.
            # -----------------------------------------------------------

            fonction = getattr(
                propositions,
                "marquer_rejetee",
                None,
            )

            if callable(fonction):

                resultat = fonction(
                    proposition_id,
                    {
                        "utilisateur": utilisateur,
                        "raison": "Rejet utilisateur",
                    },
                )

                return ResultatOrchestration(
                    True,
                    "rejet",
                    "Proposition rejetée.",
                    {
                        "proposition_id": proposition_id,
                        "resultat": resultat,
                    },
                )

            return ResultatOrchestration(
                False,
                "rejet",
                "Fonction de rejet indisponible.",
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "rejet",
                f"Erreur lors du rejet : {e}",
            )

    # ========================================================================
    # RISQUE
    # ========================================================================

    def _evaluer_risque(
        self,
        proposition: dict[str, Any],
    ) -> dict[str, Any]:

        try:

            fonction = getattr(
                risk_engine,
                "evaluer_proposition",
                None,
            )

            if callable(fonction):

                resultat = fonction(
                    proposition
                )

                if isinstance(
                    resultat,
                    dict,
                ):
                    return resultat

        except Exception:
            pass

        return {
            "niveau": "inconnu",
            "auto_applicable": False,
        }

    def evaluer_risque(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        proposition = (
            self._charger_proposition(
                proposition_id
            )
        )

        if not proposition:

            return ResultatOrchestration(
                False,
                "risque",
                "Proposition introuvable.",
            )

        risque = self._evaluer_risque(
            proposition
        )

        return ResultatOrchestration(
            True,
            "risque",
            "Évaluation du risque terminée.",
            {
                "proposition_id": proposition_id,
                "risque": risque,
            },
        )

    # ========================================================================
    # VALIDATION
    # ========================================================================

    def _valider_contenu(
        self,
        contenu: str,
        chemin: Path,
    ) -> dict[str, Any]:

        try:

            fonction = getattr(
                validateur,
                "valider_syntaxe",
                None,
            )

            if not callable(fonction):

                return {
                    "ok": False,
                    "message": (
                        "Validateur syntaxique indisponible."
                    ),
                }

            resultat = fonction(
                contenu,
                str(chemin),
            )

            if isinstance(
                resultat,
                dict,
            ):

                return resultat

            return {
                "ok": bool(resultat),
                "message": (
                    "Validation terminée."
                ),
            }

        except Exception as e:

            return {
                "ok": False,
                "message": str(e),
            }

    def valider(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        proposition = (
            self._charger_proposition(
                proposition_id
            )
        )

        if not proposition:

            return ResultatOrchestration(
                False,
                "validation",
                "Proposition introuvable.",
            )

        fichier = proposition.get(
            "fichier"
        )

        nouveau = proposition.get(
            "nouveau"
        )

        if (
            not fichier
            or not isinstance(
                nouveau,
                str,
            )
        ):

            return ResultatOrchestration(
                False,
                "validation",
                "Proposition invalide.",
            )

        try:

            chemin = self._chemin(
                fichier
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "securite",
                f"Chemin invalide : {e}",
            )

        if self._est_protege(
            chemin
        ):

            return ResultatOrchestration(
                False,
                "securite",
                "Fichier protégé.",
                {
                    "fichier": str(chemin),
                },
            )

        if not chemin.exists():

            return ResultatOrchestration(
                False,
                "validation",
                "Fichier introuvable.",
                {
                    "fichier": str(chemin),
                },
            )

        rapport = self._valider_contenu(
            nouveau,
            chemin,
        )

        if not rapport.get(
            "ok",
            False,
        ):

            return ResultatOrchestration(
                False,
                "validation",
                "Validation échouée.",
                {
                    "proposition_id": proposition_id,
                    "rapport": rapport,
                },
            )

        return ResultatOrchestration(
            True,
            "validation",
            "Validation réussie.",
            {
                "proposition_id": proposition_id,
                "rapport": rapport,
            },
        )

    # ========================================================================
    # LABORATOIRE
    # ========================================================================

    def tester_en_labo(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        proposition = (
            self._charger_proposition(
                proposition_id
            )
        )

        if not proposition:

            return ResultatOrchestration(
                False,
                "laboratoire",
                "Proposition introuvable.",
            )

        fichier = proposition.get(
            "fichier"
        )

        nouveau = proposition.get(
            "nouveau"
        )

        if (
            not fichier
            or not isinstance(
                nouveau,
                str,
            )
        ):

            return ResultatOrchestration(
                False,
                "laboratoire",
                "Proposition invalide.",
            )

        try:

            chemin = self._chemin(
                fichier
            )

            if not chemin.exists():

                return ResultatOrchestration(
                    False,
                    "laboratoire",
                    "Fichier source introuvable.",
                    {
                        "fichier": str(chemin),
                    },
                )

            # ---------------------------------------------------------------
            # Création session isolée.
            # ---------------------------------------------------------------

            session = None

            fonction_session = getattr(
                laboratoire,
                "creer_session",
                None,
            )

            if callable(
                fonction_session
            ):

                try:

                    session = fonction_session(
                        self.depot
                    )

                except TypeError:

                    session = fonction_session()

            if isinstance(
                session,
                dict,
            ):

                session_dir = (
                    session.get("chemin")
                    or session.get("directory")
                    or session.get("path")
                )

            else:

                session_dir = session

            # ---------------------------------------------------------------
            # Laboratoire réel.
            # ---------------------------------------------------------------

            if session_dir:

                session_dir = Path(
                    session_dir
                ).resolve()

                cible = (
                    session_dir
                    / self._relatif(
                        chemin
                    )
                )

                cible.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                cible.write_text(
                    nouveau,
                    encoding="utf-8",
                )

                rapport = self._valider_contenu(
                    nouveau,
                    cible,
                )

                if not rapport.get(
                    "ok",
                    False,
                ):

                    return ResultatOrchestration(
                        False,
                        "laboratoire",
                        "Validation laboratoire échouée.",
                        {
                            "proposition_id": proposition_id,
                            "session": str(session_dir),
                            "rapport": rapport,
                        },
                    )

                return ResultatOrchestration(
                    True,
                    "laboratoire",
                    "Test laboratoire réussi.",
                    {
                        "proposition_id": proposition_id,
                        "session": str(session_dir),
                        "rapport": rapport,
                    },
                )

            # ---------------------------------------------------------------
            # Fallback validation mémoire.
            # ---------------------------------------------------------------

            rapport = self._valider_contenu(
                nouveau,
                chemin,
            )

            return ResultatOrchestration(
                bool(
                    rapport.get(
                        "ok",
                        False,
                    )
                ),
                "laboratoire",
                "Validation laboratoire terminée.",
                {
                    "proposition_id": proposition_id,
                    "rapport": rapport,
                },
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "laboratoire",
                f"Erreur laboratoire : {e}",
            )

    # ========================================================================
    # AUTORISATION
    # ========================================================================

    def autoriser(
        self,
        proposition_id: str,
        confirmation: Optional[str] = None,
        utilisateur: str = "utilisateur",
    ) -> ResultatOrchestration:

        proposition = (
            self._charger_proposition(
                proposition_id
            )
        )

        if not proposition:

            return ResultatOrchestration(
                False,
                "autorisation",
                "Proposition introuvable.",
            )

        try:

            fonction = getattr(
                autorisation,
                "valider_proposition",
                None,
            )

            if not callable(
                fonction
            ):

                return ResultatOrchestration(
                    False,
                    "autorisation",
                    "Fonction d'autorisation indisponible.",
                )

            confirmation = (
                confirmation
                or f"J'AUTORISE {proposition_id}"
            )

            resultat = fonction(
                proposition_id,
                confirmation,
                f"Autorisation accordée par {utilisateur}",
            )

            if isinstance(
                resultat,
                dict,
            ):

                ok = resultat.get(
                    "ok",
                    True,
                )

            else:

                ok = bool(
                    resultat
                )

            if not ok:

                return ResultatOrchestration(
                    False,
                    "autorisation",
                    "Autorisation refusée.",
                    {
                        "resultat": resultat,
                    },
                )

            return ResultatOrchestration(
                True,
                "autorisation",
                "Autorisation enregistrée.",
                {
                    "proposition_id": proposition_id,
                    "utilisateur": utilisateur,
                    "resultat": resultat,
                },
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "autorisation",
                f"Erreur d'autorisation : {e}",
            )

    # ========================================================================
    # INTEGRITE SOURCE
    # ========================================================================

    def _verifier_source(
        self,
        chemin: Path,
        proposition: dict[str, Any],
    ) -> tuple[
        bool,
        str,
        str,
    ]:

        attendu = proposition.get(
            "source_sha256"
        )

        actuel = (
            propositions.sha256_fichier(
                chemin
            )
        )

        if (
            attendu
            and actuel != attendu
        ):

            return (
                False,
                attendu,
                actuel,
            )

        return (
            True,
            attendu or actuel,
            actuel,
        )

    # ========================================================================
    # BACKUP
    # ========================================================================

    def _backup(
        self,
        chemin: Path,
        proposition_id: Optional[str] = None,
    ) -> Any:

        try:

            fonction = getattr(
                versions,
                "creer_backup",
                None,
            )

            if not callable(
                fonction
            ):
                return None

            try:

                return fonction(
                    chemin,
                    proposition_id=proposition_id,
                )

            except TypeError:

                try:
                    return fonction(
                        chemin
                    )
                except TypeError:
                    return fonction(
                        str(chemin)
                    )

        except Exception:
            return None

    # ========================================================================
    # APPLICATION TRANSACTIONNELLE
    # ========================================================================

    def _appliquer_contenu(
        self,
        chemin: Path,
        contenu: str,
    ) -> dict[str, Any]:

        temporaire: Optional[
            Path
        ] = None

        try:

            chemin.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".py",
                dir=str(
                    chemin.parent
                ),
                delete=False,
            ) as fichier_tmp:

                temporaire = Path(
                    fichier_tmp.name
                )

                fichier_tmp.write(
                    contenu
                )

                fichier_tmp.flush()

            # ---------------------------------------------------------------
            # Validation AVANT remplacement.
            # ---------------------------------------------------------------

            rapport = self._valider_contenu(
                contenu,
                chemin,
            )

            if not rapport.get(
                "ok",
                False,
            ):

                return {
                    "ok": False,
                    "message": "Contenu invalide.",
                    "rapport": rapport,
                }

            # ---------------------------------------------------------------
            # Conservation des métadonnées.
            # ---------------------------------------------------------------

            if chemin.exists():

                try:

                    shutil.copystat(
                        chemin,
                        temporaire,
                    )

                except Exception:
                    pass

            # ---------------------------------------------------------------
            # Remplacement atomique.
            # ---------------------------------------------------------------

            temporaire.replace(
                chemin
            )

            return {
                "ok": True,
                "message": (
                    "Modification appliquée."
                ),
                "sha256": self._sha256(
                    contenu
                ),
            }

        except Exception as e:

            return {
                "ok": False,
                "message": str(e),
            }

        finally:

            if temporaire is not None:

                try:

                    if temporaire.exists():
                        temporaire.unlink()

                except Exception:
                    pass

    # ========================================================================
    # AUTORISATION PERSISTEE
    # ========================================================================

    def _autorisation_deja_validee(
        self,
        proposition_id: str,
    ) -> bool:
        """Vérifie l'autorisation persistée pour la proposition."""

        try:
            examiner = getattr(
                autorisation,
                "examiner_proposition",
                None,
            )

            if not callable(examiner):
                return False

            examen = examiner(proposition_id)

            if not isinstance(examen, dict):
                return False

            autorisation_data = examen.get("autorisation")

            # API actuelle : autorisation = True / False
            if isinstance(autorisation_data, bool):
                return autorisation_data

            # API compatible ancienne : autorisation = {"validee": True}
            if isinstance(autorisation_data, dict):
                return autorisation_data.get("validee", False) is True

            # Autre éventuelle forme de compatibilité.
            return examen.get("validee", False) is True

        except Exception:
            return False

    # ========================================================================
    # APPLICATION
    # ========================================================================

    def appliquer(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        proposition = (
            self._charger_proposition(
                proposition_id
            )
        )

        if not proposition:

            return ResultatOrchestration(
                False,
                "application",
                "Proposition introuvable.",
            )

        fichier = proposition.get(
            "fichier"
        )

        nouveau = proposition.get(
            "nouveau"
        )

        if (
            not fichier
            or not isinstance(
                nouveau,
                str,
            )
        ):

            return ResultatOrchestration(
                False,
                "application",
                "Proposition invalide.",
            )

        # --------------------------------------------------------------------
        # Résolution sécurisée.
        # --------------------------------------------------------------------

        try:

            chemin = self._chemin(
                fichier
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "securite",
                f"Chemin invalide : {e}",
            )

        if self._est_protege(
            chemin
        ):

            return ResultatOrchestration(
                False,
                "securite",
                "Fichier protégé.",
                {
                    "fichier": str(chemin),
                },
            )

        if not chemin.exists():

            return ResultatOrchestration(
                False,
                "application",
                "Fichier introuvable.",
                {
                    "fichier": str(chemin),
                },
            )

        # --------------------------------------------------------------------
        # Intégrité source.
        # --------------------------------------------------------------------

        (
            source_ok,
            source_attendu,
            source_actuel,
        ) = self._verifier_source(
            chemin,
            proposition,
        )

        if not source_ok:

            return ResultatOrchestration(
                False,
                "integrite",
                (
                    "❌ Le fichier source a changé "
                    "depuis la proposition."
                ),
                {
                    "source_attendu": source_attendu,
                    "source_actuel": source_actuel,
                },
            )

        # --------------------------------------------------------------------
        # Résultat laboratoire obligatoire.
        # Aucun patch ne peut être appliqué tant qu'un test laboratoire
        # récent et réussi n'est pas persisté sur la proposition.
        # --------------------------------------------------------------------

        laboratoire_resultat = proposition.get(
            "laboratoire"
        )

        if not isinstance(laboratoire_resultat, dict) or laboratoire_resultat.get("ok") is not True:
            return ResultatOrchestration(
                False,
                "laboratoire",
                "Test laboratoire réussi requis avant application.",
                {
                    "proposition_id": proposition_id,
                    "laboratoire": laboratoire_resultat,
                },
            )

        # --------------------------------------------------------------------
        # Autorisation persistée.
        # --------------------------------------------------------------------

        if not self._autorisation_deja_validee(
            proposition_id
        ):
            return ResultatOrchestration(
                False,
                "autorisation",
                (
                    "Autorisation requise "
                    "avant application."
                ),
                {
                    "proposition_id":
                        proposition_id,
                },
            )

        # --------------------------------------------------------------------
        # Validation finale.
        # --------------------------------------------------------------------

        validation = self.valider(
            proposition_id
        )

        if not validation.ok:
            return validation

        # --------------------------------------------------------------------
        # Backup obligatoire.
        # --------------------------------------------------------------------

        backup = self._backup(
            chemin,
            proposition_id,
        )

        if backup is None:

            return ResultatOrchestration(
                False,
                "backup",
                (
                    "Backup impossible. "
                    "Application annulée."
                ),
                {
                    "proposition_id":
                        proposition_id,
                    "fichier": str(chemin),
                },
            )

        # --------------------------------------------------------------------
        # Application.
        # --------------------------------------------------------------------

        resultat = self._appliquer_contenu(
            chemin,
            nouveau,
        )

        if not resultat.get(
            "ok",
            False,
        ):

            return ResultatOrchestration(
                False,
                "application",
                "❌ Échec de l'application.",
                {
                    "proposition_id":
                        proposition_id,
                    "resultat": resultat,
                    "backup": backup,
                },
            )

        # --------------------------------------------------------------------
        # Validation post-application.
        # --------------------------------------------------------------------

        try:

            contenu_applique = self._lire(
                chemin
            )

            post = self._valider_contenu(
                contenu_applique,
                chemin,
            )

            if not post.get(
                "ok",
                False,
            ):

                # -----------------------------------------------------------
                # Rollback immédiat.
                # -----------------------------------------------------------

                rollback = self._restaurer_backup(
                    backup
                )

                return ResultatOrchestration(
                    False,
                    "rollback",
                    (
                        "❌ Validation post-application "
                        "échouée. Rollback effectué."
                    ),
                    {
                        "proposition_id":
                            proposition_id,
                        "rapport": post,
                        "backup": backup,
                        "rollback": rollback,
                    },
                )

        except Exception as e:

            rollback = self._restaurer_backup(
                backup
            )

            return ResultatOrchestration(
                False,
                "rollback",
                (
                    "Erreur post-application. "
                    "Rollback effectué."
                ),
                {
                    "proposition_id":
                        proposition_id,
                    "erreur": str(e),
                    "backup": backup,
                    "rollback": rollback,
                },
            )

        # --------------------------------------------------------------------
        # Marquage.
        # --------------------------------------------------------------------

        statut_resultat = None
        statut_ok = False

        try:

            fonction = getattr(
                propositions,
                "marquer_appliquee",
                None,
            )

            if callable(
                fonction
            ):

                statut_resultat = fonction(
                    proposition_id
                )

                statut_ok = bool(
                    statut_resultat
                )

        except Exception as e:

            statut_resultat = str(e)

        return ResultatOrchestration(
            True,
            "application",
            "✅ Modification appliquée.",
            {
                "proposition_id":
                    proposition_id,
                "fichier": str(chemin),
                "backup": backup,
                "sha256": self._sha256(
                    nouveau
                ),
                "statut_proposition": (
                    "appliquee"
                    if statut_ok
                    else "application_ok_statut_non_marque"
                ),
                "marquage": statut_resultat,
            },
        )

    # ========================================================================
    # APPLICATION TRANSACTIONNELLE D'UN LOT
    # ========================================================================

    def appliquer_lot(
        self,
        proposition_ids: list[str],
    ) -> ResultatOrchestration:
        """Applique un ensemble de propositions avec rollback global.

        Chaque proposition passe le laboratoire, la validation et le risque
        avant la première écriture. Si l'une des applications échoue, les
        fichiers déjà modifiés sont restaurés depuis leurs backups.
        """
        ids = list(dict.fromkeys(str(pid).strip() for pid in proposition_ids))
        ids = [pid for pid in ids if pid]
        if not ids:
            return ResultatOrchestration(False, "lot", "Aucune proposition fournie.")

        preflight: list[str] = []
        for proposition_id in ids:
            labo = self.tester_en_labo(proposition_id)
            if not labo.ok:
                return ResultatOrchestration(False, "lot", labo.message, {"proposition_id": proposition_id})
            validation = self.valider(proposition_id)
            if not validation.ok:
                return ResultatOrchestration(False, "lot", validation.message, {"proposition_id": proposition_id})
            risque = self.evaluer_risque(proposition_id)
            donnees_risque = risque.details.get("risque", {}) if risque.ok else {}
            if not risque.ok or not donnees_risque.get("auto_applicable", False):
                return ResultatOrchestration(
                    False, "lot", "Une proposition du lot n'est pas auto-applicable.",
                    {"proposition_id": proposition_id, "risque": donnees_risque},
                )
            preflight.append(proposition_id)

        applications: list[dict[str, Any]] = []
        for proposition_id in preflight:
            resultat = self.appliquer_auto(proposition_id)
            if resultat.ok:
                applications.append(resultat.details)
                continue

            restaurations = []
            for details in reversed(applications):
                backup = details.get("backup") if isinstance(details, dict) else None
                restaurations.append(self._restaurer_backup(backup))
            return ResultatOrchestration(
                False,
                "rollback_lot",
                "Échec d'un patch : le lot a été restauré.",
                {
                    "proposition_id": proposition_id,
                    "erreur": resultat.message,
                    "restaurations": restaurations,
                    "appliquees_avant_echec": applications,
                },
            )

        return ResultatOrchestration(
            True,
            "lot",
            "Lot appliqué avec succès.",
            {"propositions": preflight, "applications": applications},
        )

    # ========================================================================
    # RESTAURATION BACKUP
    # ========================================================================

    def _restaurer_backup(
        self,
        backup: Any,
    ) -> Any:

        if not backup:
            return False

        try:

            fonction = getattr(
                versions,
                "restaurer_backup",
                None,
            )

            if not callable(
                fonction
            ):
                return False

            # ----------------------------------------------------------------
            # Le système de versions peut retourner :
            # - chemin
            # - dict
            # ----------------------------------------------------------------

            cible = backup

            if isinstance(
                backup,
                dict,
            ):

                cible = (
                    backup.get("backup")
                    or backup.get("chemin")
                    or backup.get("path")
                )

            if not cible:
                return False

            return fonction(
                cible
            )

        except Exception as e:

            return {
                "ok": False,
                "message": str(e),
            }

    # ========================================================================
    # RESTAURATION PUBLIQUE
    # ========================================================================

    def restaurer(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        proposition = (
            self._charger_proposition(
                proposition_id
            )
        )

        if not proposition:

            return ResultatOrchestration(
                False,
                "rollback",
                "Proposition introuvable.",
            )

        try:

            fichier = proposition.get(
                "fichier"
            )

            if not fichier:

                return ResultatOrchestration(
                    False,
                    "rollback",
                    "Fichier de proposition inconnu.",
                )

            chemin = self._chemin(
                fichier
            )

            fonction_liste = getattr(
                versions,
                "lister_backups",
                None,
            )

            fonction_restore = getattr(
                versions,
                "restaurer_backup",
                None,
            )

            if not callable(
                fonction_liste
            ):

                return ResultatOrchestration(
                    False,
                    "rollback",
                    "Gestionnaire de backups indisponible.",
                )

            if not callable(
                fonction_restore
            ):

                return ResultatOrchestration(
                    False,
                    "rollback",
                    "Fonction de restauration indisponible.",
                )

            backups = fonction_liste(
                chemin
            )

            if not backups:

                return ResultatOrchestration(
                    False,
                    "rollback",
                    "Aucun backup disponible.",
                )

            dernier = backups[-1]

            resultat = fonction_restore(
                dernier
            )

            return ResultatOrchestration(
                True,
                "rollback",
                "Backup restauré.",
                {
                    "backup": dernier,
                    "resultat": resultat,
                },
            )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "rollback",
                f"Erreur rollback : {e}",
            )

    # ========================================================================
    # AUTORISATION AUTOMATIQUE CONTROLEE
    # ========================================================================

    def _enregistrer_autorisation_auto(
        self,
        proposition_id: str,
    ) -> dict[str, Any]:
        """
        Enregistre une décision automatique uniquement après validation
        du moteur de risque et du niveau AUTO_REPAIR.

        Préfère une API publique `autoriser_automatiquement` si elle
        existe. Compatibilité de secours : utilise l'écriture persistée
        de `autorisation.py` sans simuler une confirmation humaine.
        """

        commentaire = (
            "Autorisation automatique contrôlée par JIBI "
            "après validation du risque."
        )

        fonction = getattr(
            autorisation,
            "autoriser_automatiquement",
            None,
        )

        if callable(fonction):
            try:
                resultat = fonction(
                    proposition_id,
                    commentaire=commentaire,
                )
            except TypeError:
                resultat = fonction(
                    proposition_id
                )

            if isinstance(resultat, dict):
                return resultat

            return {
                "ok": bool(resultat),
                "resultat": resultat,
            }

        # Compatibilité avec la version actuelle de autorisation.py.
        ecrire = getattr(
            autorisation,
            "_ecrire_decision",
            None,
        )

        if not callable(ecrire):
            return {
                "ok": False,
                "message": (
                    "Autorisation automatique indisponible : "
                    "ajouter autoriser_automatiquement() à autorisation.py."
                ),
            }

        ok = bool(
            ecrire(
                proposition_id,
                True,
                commentaire,
            )
        )

        if not ok:
            return {
                "ok": False,
                "message": "Impossible d'enregistrer l'autorisation automatique.",
            }

        try:
            marquer = getattr(
                propositions,
                "marquer_validee",
                None,
            )

            if callable(marquer):
                marquer(
                    proposition_id,
                    commentaire=commentaire,
                )
        except Exception:
            pass

        return {
            "ok": True,
            "message": "Autorisation automatique enregistrée.",
            "source": "jibi-auto",
        }

    # ========================================================================
    # APPLICATION AUTOMATIQUE
    # ========================================================================

    def appliquer_auto(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        proposition = (
            self._charger_proposition(
                proposition_id
            )
        )

        if not proposition:

            return ResultatOrchestration(
                False,
                "auto",
                "Proposition introuvable.",
            )

        risque = self._evaluer_risque(
            proposition
        )

        auto_applicable = bool(
            risque.get(
                "auto_applicable",
                False,
            )
        )

        niveau_auto = 0

        if config is not None:

            try:

                niveau_auto = int(
                    getattr(
                        config,
                        "AUTO_REPAIR_LEVEL",
                        0,
                    )
                )

            except Exception:

                niveau_auto = 0

        if not auto_applicable:

            return ResultatOrchestration(
                False,
                "risque",
                (
                    "Application automatique refusée "
                    "par la politique de risque."
                ),
                {
                    "risque": risque,
                    "niveau_auto": niveau_auto,
                },
            )

        if niveau_auto < 5:

            return ResultatOrchestration(
                False,
                "risque",
                (
                    "Niveau d'auto-réparation "
                    "insuffisant."
                ),
                {
                    "risque": risque,
                    "niveau_auto": niveau_auto,
                },
            )

        # --------------------------------------------------------------------
        # Autorisation interne contrôlée.
        # --------------------------------------------------------------------

        try:
            resultat = self._enregistrer_autorisation_auto(
                proposition_id
            )

            if not resultat.get(
                "ok",
                False,
            ):
                return ResultatOrchestration(
                    False,
                    "autorisation",
                    "Autorisation automatique refusée.",
                    {
                        "resultat": resultat,
                    },
                )

        except Exception as e:

            return ResultatOrchestration(
                False,
                "autorisation",
                (
                    "Autorisation automatique "
                    f"impossible : {e}"
                ),
            )

        return self.appliquer(
            proposition_id
        )

    # ========================================================================
    # WORKFLOW COMPLET
    # ========================================================================

    def workflow(
        self,
        proposition_id: str,
    ) -> ResultatOrchestration:

        # --------------------------------------------------------------------
        # 1. Laboratoire
        # --------------------------------------------------------------------

        labo = self.tester_en_labo(
            proposition_id
        )

        if not labo.ok:
            return labo

        # --------------------------------------------------------------------
        # 2. Validation
        # --------------------------------------------------------------------

        validation = self.valider(
            proposition_id
        )

        if not validation.ok:
            return validation

        # --------------------------------------------------------------------
        # 3. Risque
        # --------------------------------------------------------------------

        risque = self.evaluer_risque(
            proposition_id
        )

        if not risque.ok:
            return risque

        donnees_risque = (
            risque.details.get(
                "risque",
                {},
            )
        )

        niveau_auto = 0

        if config is not None:

            try:

                niveau_auto = int(
                    getattr(
                        config,
                        "AUTO_REPAIR_LEVEL",
                        0,
                    )
                )

            except Exception:
                niveau_auto = 0

        auto_applicable = bool(
            donnees_risque.get(
                "auto_applicable",
                False,
            )
        )

        # --------------------------------------------------------------------
        # 4. Application automatique contrôlée.
        # --------------------------------------------------------------------

        if (
            auto_applicable
            and niveau_auto >= 5
        ):

            return self.appliquer_auto(
                proposition_id
            )

        # --------------------------------------------------------------------
        # 5. Autorisation humaine nécessaire.
        # --------------------------------------------------------------------

        return ResultatOrchestration(
            True,
            "risque",
            (
                "✅ Proposition validée jusqu'à "
                "l'évaluation du risque. "
                "Autorisation requise avant application."
            ),
            {
                "proposition_id":
                    proposition_id,
                "risque":
                    donnees_risque,
                "auto_applicable":
                    auto_applicable,
                "niveau_auto":
                    niveau_auto,
                "autorisation_requise":
                    True,
            },
        )

    # ========================================================================
    # ETAT
    # ========================================================================

    def etat(
        self,
    ) -> dict[str, Any]:

        total = 0
        proposition_count = 0
        en_cours = 0
        testee = 0
        validee = 0
        rejetee = 0
        appliquee = 0

        for data in self.lister_propositions():

            if not isinstance(
                data,
                dict,
            ):
                continue

            statut = data.get(
                "statut",
                "proposition",
            )

            total += 1

            if statut == "proposition":
                proposition_count += 1

            elif statut == "en_cours":
                en_cours += 1

            elif statut == "testee":
                testee += 1

            elif statut == "validee":
                validee += 1

            elif statut == "rejetee":
                rejetee += 1

            elif statut == "appliquee":
                appliquee += 1

        sessions = 0

        try:

            fonction = getattr(
                laboratoire,
                "compter_sessions",
                None,
            )

            if callable(
                fonction
            ):
                sessions = int(
                    fonction()
                )

        except Exception:
            sessions = 0

        return {
            "propositions": {
                "total": total,
                "proposition": proposition_count,
                "en_cours": en_cours,
                "testee": testee,
                "validee": validee,
                "rejetee": rejetee,
                "appliquee": appliquee,
            },
            "sessions_labo": sessions,
            "depot": str(
                self.depot
            ),
        }

    # ========================================================================
    # TABLEAU DE BORD
    # ========================================================================

    def tableau_de_bord(
        self,
    ) -> dict[str, Any]:

        return self.etat()


# ============================================================================
# FACTORY
# ============================================================================

def creer_orchestrateur(
    depot: Optional[str | Path] = None,
) -> OrchestrateurEvolution:

    return OrchestrateurEvolution(
        depot=depot
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "ResultatOrchestration",
    "OrchestrateurEvolution",
    "creer_orchestrateur",
]
