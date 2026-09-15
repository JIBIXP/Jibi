"""
AUTORISATION HUMAINE — PATCHÉ v2
- Branché sur core/config.py (WORKSPACE_DIR, USER_ID)
- Écriture atomique + logs sécu + timings
"""
import json
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

try:
    from core.config import WORKSPACE_DIR, USER_ID
    PROJET_ROOT = WORKSPACE_DIR.parent
    DECISIONS_DIR = WORKSPACE_DIR / "jibi_lab" / "decisions_humaines"
except Exception:
    PROJET_ROOT = Path(__file__).resolve().parent.parent
    DECISIONS_DIR = PROJET_ROOT / "workspace" / "jibi_lab" / "decisions_humaines"
    USER_ID = "admin"
DECISIONS_DIR.mkdir(parents=True, exist_ok=True)

try:
    from logging_jibi import log_event
except Exception:
    def log_event(*a, **kw): pass

PHRASE_AUTORISATION = "J'AUTORISE"
PHRASE_REJET = "JE REJETE"
REGEX_AUTORISATION = re.compile(r"^J['’]AUTORISE\s+([a-zA-Z0-9_\-]+)(?:\s+(.*))?$", re.IGNORECASE)
REGEX_REJET = re.compile(r"^JE\s+REJETE\s+([a-zA-Z0-9_\-]+)(?:\s+(.*))?$", re.IGNORECASE)

def _chemin_decision(prop_id: str) -> Path:
    return DECISIONS_DIR / f"{prop_id}.json"

def _lire_decision(prop_id: str) -> Optional[Dict]:
    chemin = _chemin_decision(prop_id)
    if not chemin.exists():
        return None
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except Exception:
        return None

def _ecrire_decision(prop_id: str, approuve: bool, commentaire: str = "") -> bool:
    try:
        DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
        data = {"proposition_id": prop_id, "approuve": approuve, "commentaire": commentaire, "date": datetime.now().isoformat(), "utilisateur": USER_ID}
        chemin = _chemin_decision(prop_id)
        tmp = chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(chemin)
        return True
    except Exception:
        return False

def _parser_confirmation(confirmation: str) -> Optional[Dict]:
    if not confirmation or not confirmation.strip():
        return None
    confirmation = confirmation.strip()
    m = REGEX_AUTORISATION.match(confirmation)
    if m:
        return {"prop_id": m.group(1), "commentaire": (m.group(2) or "").strip(), "action": "autoriser"}
    m = REGEX_REJET.match(confirmation)
    if m:
        return {"prop_id": m.group(1), "commentaire": (m.group(2) or "").strip(), "action": "rejet"}
    return None

def autorisation_valide(prop_id: str, confirmation: str) -> bool:
    t0 = time.perf_counter()
    if not prop_id or not confirmation:
        return False
    decision = _lire_decision(prop_id)
    if decision and decision.get("approuve") is False:
        log_event("autorisation", f"Refus {prop_id} déjà rejeté")
        return False
    parsed = _parser_confirmation(confirmation)
    if not parsed:
        return False
    if parsed["prop_id"] != prop_id:
        return False
    if parsed["action"] != "autoriser":
        return False
    log_event("autorisation", f"Autorisation {prop_id} valide en {time.perf_counter()-t0:.4f}s")
    return True

def valider_proposition(prop_id: str, confirmation: str, commentaire: str = "") -> Dict[str, Any]:
    if not autorisation_valide(prop_id, confirmation):
        return {"ok": False, "message": f"Confirmation invalide. Format attendu : {PHRASE_AUTORISATION} {prop_id}", "proposition_id": prop_id}
    try:
        from self_improvement.propositions import charger_proposition
        prop = charger_proposition(prop_id)
        if not prop:
            return {"ok": False, "message": f"Proposition '{prop_id}' introuvable.", "proposition_id": prop_id}
    except Exception:
        pass
    if not _ecrire_decision(prop_id, True, commentaire):
        return {"ok": False, "message": "Impossible d'écrire la décision sur disque.", "proposition_id": prop_id}
    try:
        from self_improvement.propositions import marquer_validee
        # marquer_validee gère str ou dict
        marquer_validee(prop_id, commentaire=commentaire or "Validé via autorisation.py")
    except Exception:
        pass
    return {"ok": True, "message": f"Proposition {prop_id} validée avec succès.", "proposition_id": prop_id, "date": datetime.now().isoformat()}

def rejeter_proposition(prop_id: str, commentaire: str = "") -> Dict[str, Any]:
    if not prop_id:
        return {"ok": False, "message": "ID manquant.", "proposition_id": None}
    if not _ecrire_decision(prop_id, False, commentaire):
        return {"ok": False, "message": "Impossible d'écrire la décision sur disque.", "proposition_id": prop_id}
    try:
        from self_improvement.propositions import marquer_rejetee
        marquer_rejetee(prop_id, raison=commentaire or "Rejeté par l'utilisateur")
    except Exception:
        pass
    return {"ok": True, "message": f"Proposition {prop_id} rejetée.", "proposition_id": prop_id}

def marquer_appliquee(prop_id: str) -> Dict[str, Any]:
    if not prop_id:
        return {"ok": False, "message": "ID manquant."}
    try:
        from self_improvement.propositions import marquer_appliquee as _marquer
        _marquer(prop_id)
        return {"ok": True, "message": f"Proposition {prop_id} marquée appliquée."}
    except Exception as e:
        return {"ok": False, "message": str(e)}

def examiner_proposition(prop_id: str) -> Optional[Dict[str, Any]]:
    try:
        from self_improvement.propositions import charger_proposition
        prop = charger_proposition(prop_id)
    except Exception:
        prop = None
    if not prop:
        return None
    decision = _lire_decision(prop_id)
    return {"id": prop_id, "fichier": prop.get("fichier", "?"), "probleme": prop.get("probleme", ""), "solution": prop.get("solution", ""), "priorite": prop.get("priorite", "moyenne"), "statut": prop.get("statut", "en_attente"), "date_creation": prop.get("date_creation", ""), "autorisation": {"validee": decision.get("approuve") is True if decision else False, "rejetee": decision.get("approuve") is False if decision else False, "commentaire": decision.get("commentaire", "") if decision else "", "date": decision.get("date", "") if decision else ""}}

def lister_propositions_en_attente() -> List[Dict]:
    try:
        from self_improvement.propositions import lister_propositions
        toutes = lister_propositions()
    except Exception:
        return []
    en_attente = []
    for prop in toutes:
        pid = prop.get("id")
        if not pid:
            continue
        decision = _lire_decision(pid)
        if decision and decision.get("approuve") is not None:
            continue
        if prop.get("statut") == "appliquee":
            continue
        en_attente.append(prop)
    return en_attente

def obtenir_statistiques() -> Dict[str, int]:
    try:
        from self_improvement.propositions import lister_propositions
        toutes = lister_propositions()
    except Exception:
        toutes = []
    stats = {"total": len(toutes), "en_attente": 0, "testee": 0, "validee": 0, "rejetee": 0, "appliquee": 0}
    for prop in toutes:
        statut = prop.get("statut", "en_attente")
        if statut in stats:
            stats[statut] += 1
        else:
            stats["en_attente"] += 1
    return stats

def formater_phrase_autorisation(prop_id: str) -> str:
    return f"{PHRASE_AUTORISATION} {prop_id}"

def formater_phrase_rejet(prop_id: str) -> str:
    return f"{PHRASE_REJET} {prop_id}"

def lister_decisions() -> List[Dict]:
    if not DECISIONS_DIR.exists():
        return []
    decisions = []
    for fichier in sorted(DECISIONS_DIR.glob("*.json"), reverse=True):
        try:
            decisions.append(json.loads(fichier.read_text(encoding="utf-8")))
        except Exception:
            continue
    return decisions

def supprimer_decision(prop_id: str) -> bool:
    chemin = _chemin_decision(prop_id)
    if chemin.exists():
        try:
            chemin.unlink()
            return True
        except Exception:
            return False
    return False

__all__ = ["autorisation_valide", "valider_proposition", "rejeter_proposition", "marquer_appliquee", "examiner_proposition", "lister_propositions_en_attente", "obtenir_statistiques", "formater_phrase_autorisation", "formater_phrase_rejet", "lister_decisions", "supprimer_decision", "PHRASE_AUTORISATION", "DECISIONS_DIR"]
