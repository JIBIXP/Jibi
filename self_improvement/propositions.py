"""
Gestion des propositions — PATCHÉ v2
- Branché sur core/config.py (WORKSPACE_DIR)
- Persistance atomique + validation statuts
"""

from pathlib import Path
from datetime import datetime
import json
import uuid

try:
    from core.config import WORKSPACE_DIR
    PROJECT_ROOT = WORKSPACE_DIR.parent
    PROPOSITIONS_DIR = WORKSPACE_DIR / "jibi_lab" / "propositions"
except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    PROPOSITIONS_DIR = PROJECT_ROOT / "workspace" / "jibi_lab" / "propositions"

PRIORITES = {"critique": 1, "haute": 2, "moyenne": 3, "basse": 4}
STATUTS_VALIDES = {"proposition", "en_cours", "testee", "validee", "rejetee", "appliquee"}

def creer_proposition(fichier, probleme, solution, justification="", priorite="moyenne", categorie="general"):
    if priorite not in PRIORITES:
        priorite = "moyenne"
    if not fichier or not str(fichier).strip():
        raise ValueError("Fichier manquant pour la proposition")
    proposition = {
        "id": uuid.uuid4().hex[:12],
        "fichier": str(fichier),
        "probleme": str(probleme),
        "solution": str(solution),
        "justification": str(justification),
        "priorite": priorite,
        "categorie": str(categorie),
        "date_creation": datetime.now().isoformat(),
        "date_modification": datetime.now().isoformat(),
        "statut": "proposition",
        "historique": [{"date": datetime.now().isoformat(), "action": "creation", "detail": "Proposition créée."}],
    }
    return proposition

def sauvegarder_proposition(proposition):
    PROPOSITIONS_DIR.mkdir(parents=True, exist_ok=True)
    fichier = PROPOSITIONS_DIR / f"{proposition['id']}.json"
    try:
        tmp = fichier.with_suffix(".tmp")
        tmp.write_text(json.dumps(proposition, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(fichier)
        return str(fichier)
    except Exception as e:
        return f"Erreur de sauvegarde : {e}"

def charger_proposition(proposition_id):
    fichier = PROPOSITIONS_DIR / f"{proposition_id}.json"
    if not fichier.exists():
        return None
    try:
        return json.loads(fichier.read_text(encoding="utf-8"))
    except Exception:
        return None

def lister_propositions(statut=None, priorite=None):
    if not PROPOSITIONS_DIR.exists():
        return []
    propositions = []
    for fichier in PROPOSITIONS_DIR.glob("*.json"):
        try:
            prop = json.loads(fichier.read_text(encoding="utf-8"))
            if statut and prop.get("statut") != statut:
                continue
            if priorite and prop.get("priorite") != priorite:
                continue
            propositions.append(prop)
        except Exception:
            continue
    propositions.sort(key=lambda p: (PRIORITES.get(p.get("priorite", "moyenne"), 3), p.get("date_creation", "")))
    return propositions

def _ajouter_historique(proposition, action, detail=""):
    if "historique" not in proposition:
        proposition["historique"] = []
    proposition["historique"].append({"date": datetime.now().isoformat(), "action": action, "detail": detail})
    proposition["date_modification"] = datetime.now().isoformat()

def _changer_statut(proposition, nouveau_statut, detail=""):
    if nouveau_statut not in STATUTS_VALIDES:
        raise ValueError(f"Statut invalide : {nouveau_statut}")
    proposition["statut"] = nouveau_statut
    _ajouter_historique(proposition, nouveau_statut, detail)
    return proposition

def marquer_en_cours(proposition):
    return _changer_statut(proposition, "en_cours")

def marquer_testee(proposition, resultat_test=""):
    return _changer_statut(proposition, "testee", resultat_test)

def marquer_validee(proposition, commentaire=""):
    if isinstance(proposition, str):
        # surcharge : si on passe un ID, charger d'abord
        p = charger_proposition(proposition)
        if not p:
            raise ValueError(f"Proposition {proposition} introuvable")
        proposition = p
        result = _changer_statut(proposition, "validee", commentaire)
        sauvegarder_proposition(result)
        return result
    return _changer_statut(proposition, "validee", commentaire)

def marquer_rejetee(proposition, raison=""):
    if isinstance(proposition, str):
        p = charger_proposition(proposition)
        if not p:
            raise ValueError(f"Proposition {proposition} introuvable")
        proposition = p
        proposition["raison_rejet"] = raison
        result = _changer_statut(proposition, "rejetee", raison)
        sauvegarder_proposition(result)
        return result
    proposition["raison_rejet"] = raison
    return _changer_statut(proposition, "rejetee", raison)

def marquer_appliquee(proposition):
    if isinstance(proposition, str):
        p = charger_proposition(proposition)
        if not p:
            raise ValueError(f"Proposition {proposition} introuvable")
        proposition = p
        result = _changer_statut(proposition, "appliquee")
        sauvegarder_proposition(result)
        return result
    return _changer_statut(proposition, "appliquee")

def formater_proposition(proposition):
    priorite_emoji = {"critique": "🔴", "haute": "🟠", "moyenne": "🟡", "basse": "🟢"}
    emoji = priorite_emoji.get(proposition.get("priorite", "moyenne"), "🟡")
    lignes = [
        f"PROPOSITION {proposition.get('id', '?')} {emoji} [{proposition.get('priorite', '?').upper()}]",
        "=" * 50,
        f"Fichier : {proposition.get('fichier', '?')}",
        f"Catégorie : {proposition.get('categorie', '?')}",
        f"Statut : {proposition.get('statut', '?')}",
        f"Date : {proposition.get('date_creation', '?')}",
        "", "Problème :", f"  {proposition.get('probleme', '?')}", "",
        "Solution :", f"  {proposition.get('solution', '?')}",
    ]
    if proposition.get("justification"):
        lignes.extend(["", "Justification :", f"  {proposition['justification']}"])
    if proposition.get("historique"):
        lignes.extend(["", "Historique :"])
        for entree in proposition["historique"][-5:]:
            lignes.append(f"  [{entree['date'][:16]}] {entree['action']} : {entree['detail']}")
    return "\n".join(lignes)

def obtenir_statistiques():
    toutes = lister_propositions()
    if not toutes:
        return {"total": 0, "proposition": 0, "en_cours": 0, "testee": 0, "validee": 0, "rejetee": 0, "appliquee": 0}
    stats = {"total": len(toutes)}
    for prop in toutes:
        statut = prop.get("statut", "inconnu")
        stats[statut] = stats.get(statut, 0) + 1
    return stats
