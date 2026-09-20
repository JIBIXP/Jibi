"""
AUTONOMIE — moteur d'indépendance de JIBI.

JIBI fonctionne selon 3 niveaux d'autonomie :

  * "assiste"  (défaut) : JIBI propose, l'humain dispose. Toute modification
    de code passe par une proposition + "J'AUTORISE <id>". Les zones
    sensibles (core/, self_improvement/) sont intouchables.
  * "semi_auto" : JIBI analyse en continu, prépare les correctifs tout seul
    (diagnostics périodiques automatiques), mais l'humain garde le dernier
    mot pour appliquer.
  * "autonome" : JIBI s'auto-diagnostique, s'auto-corrige et s'améliore seul :
    - les correctifs à FAIBLE RISQUE (petit diff, tests OK, sécurité OK)
      sont appliqués automatiquement, y compris dans core/ ;
    - les changements importants restent proposés à l'humain ;
    - chaque action est écrite au journal (workspace/autonomie/journal.jsonl)
      et reste réversible (backup systématique + rollback).

Sécurité : même en mode "autonome", sont TOUJOURS interdits :
  .env*, .git/, workspace/, chemins absolus, fichiers non-Python,
  code dangereux détecté (eval/exec/os.system...), tests en échec.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from core.config import JIBI_PROJET_DIR as _CFG_DEPOT, WORKSPACE_DIR as _CFG_WS
    DEPOT_DIR = _CFG_DEPOT
    AUTONOMIE_DIR = _CFG_WS / "autonomie"
except Exception:
    DEPOT_DIR = Path(__file__).resolve().parent.parent
    AUTONOMIE_DIR = DEPOT_DIR / "workspace" / "autonomie"

CONFIG_PATH = AUTONOMIE_DIR / "config.json"
JOURNAL_PATH = AUTONOMIE_DIR / "journal.jsonl"

NIVEAU_ASSISTE = "assiste"
NIVEAU_SEMI_AUTO = "semi_auto"
NIVEAU_AUTONOME = "autonome"
NIVEAUX = (NIVEAU_ASSISTE, NIVEAU_SEMI_AUTO, NIVEAU_AUTONOME)

SEUIL_SANTE_ACTION = 95        # en dessous → le cycle cherche des correctifs
MAX_IDEES_PAR_CYCLE = 2        # borne le coût LLM de chaque cycle
MAX_LIGNES_FAIBLE_RISQUE = 40  # diff au-delà → validation humaine obligatoire
TAILLE_MAX_JOURNAL = 500       # entrées conservées

FICHIERS_SURVEILLES = [  # lus par le cerveau pendant le cycle autonome
    "tools/files.py",
    "tools/terminal.py",
    "tools/web_search.py",
    "tools/documents.py",
    "tools/memoire.py",
    "core/tool_routing.py",
    "gui_kit/theme.py",
]

_lock = threading.Lock()
_niveau_cache: Optional[str] = None
_callbacks: List[Callable[[dict], None]] = []
_boucle_thread: Optional[threading.Thread] = None
_boucle_stop: Optional[threading.Event] = None


def _log(msg: str) -> None:
    try:
        from logging_jibi import log_event
        log_event("autonomie", msg)
    except Exception:
        print(f"[autonomie] {msg}")


# ============================================================
# Niveau d'autonomie (persisté)
# ============================================================

def get_niveau() -> str:
    global _niveau_cache
    with _lock:
        if _niveau_cache in NIVEAUX:
            return _niveau_cache
    niveau = (os.getenv("JIBI_AUTONOMIE", "") or "").strip().lower()
    if niveau not in NIVEAUX:
        try:
            if CONFIG_PATH.exists():
                niveau = (json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("niveau") or "").lower()
        except Exception:
            niveau = ""
    if niveau not in NIVEAUX:
        niveau = NIVEAU_ASSISTE
    with _lock:
        _niveau_cache = niveau
    return niveau


def set_niveau(niveau: str) -> dict:
    global _niveau_cache
    niveau = (niveau or "").strip().lower()
    if niveau not in NIVEAUX:
        return {"ok": False, "message": f"Niveau inconnu : {niveau} (attendu : {', '.join(NIVEAUX)})"}
    try:
        AUTONOMIE_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"niveau": niveau, "date": datetime.now().isoformat()},
                                           ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "message": f"Impossible de persister le niveau : {e}"}
    with _lock:
        _niveau_cache = None
    os.environ["JIBI_AUTONOMIE"] = niveau
    _log(f"Niveau d'autonomie → {niveau}")
    journaliser("niveau", {"niveau": niveau})
    return {"ok": True, "niveau": niveau}


def est_autonome() -> bool:
    return get_niveau() == NIVEAU_AUTONOME


def est_semi_auto_ou_plus() -> bool:
    return get_niveau() in (NIVEAU_SEMI_AUTO, NIVEAU_AUTONOME)


# ============================================================
# Journal des actions autonomes
# ============================================================

def journaliser(action: str, details: Any = None) -> dict:
    entree = {"date": datetime.now().isoformat(), "niveau": get_niveau(),
              "action": action, "details": details or {}}
    try:
        AUTONOMIE_DIR.mkdir(parents=True, exist_ok=True)
        with JOURNAL_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entree, ensure_ascii=False) + "\n")
        _tronquer_journal()
    except Exception as e:
        _log(f"Journalisation impossible : {e}")
    for cb in list(_callbacks):
        try:
            cb(entree)
        except Exception:
            pass
    return entree


def _tronquer_journal() -> None:
    try:
        lignes = JOURNAL_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    if len(lignes) > TAILLE_MAX_JOURNAL:
        JOURNAL_PATH.write_text("\n".join(lignes[-TAILLE_MAX_JOURNAL:]) + "\n", encoding="utf-8")


def lire_journal(limite: int = 50) -> List[dict]:
    if not JOURNAL_PATH.exists():
        return []
    try:
        lignes = JOURNAL_PATH.read_text(encoding="utf-8").splitlines()[-limite:]
        out = []
        for ligne in lignes:
            try:
                out.append(json.loads(ligne))
            except Exception:
                continue
        return list(reversed(out))
    except Exception:
        return []


def abonner(callback: Callable[[dict], None]) -> None:
    """La GUI s'abonne ici pour être notifiée des actions autonomes."""
    if callable(callback) and callback not in _callbacks:
        _callbacks.append(callback)


# ============================================================
# Évaluation du risque d'une proposition
# ============================================================

def _taille_diff(proposition: dict) -> int:
    n = 0
    for ligne in (proposition.get("diff") or "").splitlines():
        if ligne.startswith("+") and not ligne.startswith("+++"):
            n += 1
        elif ligne.startswith("-") and not ligne.startswith("---"):
            n += 1
    return n


def evaluer_risque(proposition: dict) -> dict:
    """Dit si une proposition peut être auto-appliquée en mode autonome."""
    from core import evolution  # import local : évite tout cycle d'import
    fichier = proposition.get("fichier", "")
    bloque, raison = evolution.protege(fichier)
    if bloque:
        return {"faible_risque": False, "raison": f"Zone protégée : {raison}"}
    tests = proposition.get("tests") or {}
    if not tests.get("ok"):
        return {"faible_risque": False, "raison": "Tests labo en échec"}
    details = " ".join(tests.get("details", []) or [])
    if "🚫" in details:
        return {"faible_risque": False, "raison": "Sécurité bloquante"}
    taille = _taille_diff(proposition)
    if taille == 0:
        return {"faible_risque": False, "raison": "Aucun changement réel"}
    if taille > MAX_LIGNES_FAIBLE_RISQUE:
        return {"faible_risque": False,
                "raison": f"Diff trop gros ({taille} lignes > {MAX_LIGNES_FAIBLE_RISQUE})"}
    zone_sensible = fichier.startswith(("core/", "self_improvement/"))
    if zone_sensible and "🟡" in details:
        return {"faible_risque": False, "raison": "Zone sensible + avertissement sécurité"}
    return {"faible_risque": True, "raison": f"Petit diff ({taille} lignes), tests OK", "taille_diff": taille}


# ============================================================
# Cycle autonome : observer → réfléchir → agir
# ============================================================

def cycle_autonome() -> dict:
    """Un cycle complet d'autonomie. Retourne un résumé JSON-sérialisable."""
    t0 = time.perf_counter()
    niveau = get_niveau()
    resume: Dict[str, Any] = {
        "date": datetime.now().isoformat(), "niveau": niveau,
        "score_sante": None, "propositions_creees": [],
        "propositions_appliquees": [], "erreurs": [],
    }
    journaliser("cycle_debut", {"niveau": niveau})

    # --- 1. OBSERVER : santé + erreurs récurrentes ---
    try:
        from self_improvement.gestionnaire import analyser_jibi
        analyse = analyser_jibi(depuis_heures=24)
    except Exception as e:
        resume["erreurs"].append(f"Analyse santé impossible : {e}")
        journaliser("cycle_erreur", {"etape": "analyse", "erreur": str(e)[:200]})
        return resume
    score = analyse.get("score_sante", 100)
    resume["score_sante"] = score
    patterns = analyse.get("patterns_recurrents", []) or []
    journaliser("sante", {"score": score,
                          "patterns": [p.get("message", "")[:100] for p in patterns[:3]]})

    # --- 2. RÉFLÉCHIR : le cerveau propose des correctifs ---
    idees: List[dict] = []
    if niveau in (NIVEAU_SEMI_AUTO, NIVEAU_AUTONOME) and (score < SEUIL_SANTE_ACTION or patterns):
        idees = _generer_idees(analyse)
        for idee in idees[:MAX_IDEES_PAR_CYCLE]:
            pid = _preparer_correctif(idee)
            if pid:
                resume["propositions_creees"].append(pid)
    elif niveau == NIVEAU_ASSISTE:
        journaliser("cycle_info", {"message": "Mode assisté : pas de génération auto (diagnostic manuel via 'diagnostic')."})

    # --- 3. AGIR : auto-application des correctifs sûrs (mode autonome) ---
    if niveau == NIVEAU_AUTONOME:
        resume["propositions_appliquees"] = _auto_appliquer()
    else:
        try:
            from core import evolution
            nb = len(evolution.lister("en_attente"))
            if nb:
                journaliser("cycle_info", {"message": f"{nb} proposition(s) attendent ta validation."})
        except Exception:
            pass

    resume["duree_s"] = round(time.perf_counter() - t0, 2)
    journaliser("cycle_fin", {"score": score, "creees": resume["propositions_creees"],
                              "appliquees": resume["propositions_appliquees"],
                              "duree_s": resume["duree_s"]})
    return resume


def _cerveau_disponible() -> bool:
    try:
        from core import cerveau
        return bool(cerveau.disponible())
    except Exception:
        return False


def _generer_idees(analyse: dict) -> List[dict]:
    try:
        from core import cerveau
        from core import evolution
        if not _cerveau_disponible():
            journaliser("cycle_info", {"message": "LLM indisponible : pas de génération d'idées."})
            return []
        fichiers = {}
        for f in FICHIERS_SURVEILLES:
            p = DEPOT_DIR / f
            if p.exists():
                try:
                    fichiers[f] = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
        idees = cerveau.diagnostiquer(analyse, fichiers) or []
        journaliser("idees", {"nombre": len(idees),
                              "titres": [i.get("titre", "?")[:80] for i in idees[:5]]})
        return [i for i in idees if isinstance(i, dict) and i.get("fichier")]
    except Exception as e:
        journaliser("cycle_erreur", {"etape": "idees", "erreur": str(e)[:200]})
        return []


def _preparer_correctif(idee: dict) -> Optional[str]:
    try:
        from core import cerveau, evolution
        f_cible = idee.get("fichier", "").replace("\\", "/")
        bloque, raison = evolution.protege(f_cible)
        if bloque:
            journaliser("correctif_ignore", {"fichier": f_cible, "raison": raison})
            return None
        cible = DEPOT_DIR / f_cible
        if not cible.exists():
            return None
        contenu = cible.read_text(encoding="utf-8", errors="replace")
        nouveau = cerveau.reecrire_fichier(f_cible, contenu, idee.get("description", ""))
        res = evolution.proposer(f_cible, f"Auto-Fix: {idee.get('titre', '')}",
                                 nouveau, origine="cycle_autonome")
        if res.get("proposition"):
            pid = res["proposition"]["id"]
            journaliser("correctif_pret", {"id": pid, "fichier": f_cible,
                                           "tests_ok": bool(res.get("ok"))})
            return pid
        journaliser("correctif_echec", {"fichier": f_cible, "message": res.get("message", "")[:150]})
        return None
    except Exception as e:
        journaliser("cycle_erreur", {"etape": "correctif", "erreur": str(e)[:200]})
        return None


def _auto_appliquer() -> List[str]:
    from core import evolution
    appliquees: List[str] = []
    try:
        en_attente = evolution.lister("en_attente")
    except Exception:
        return appliquees
    for p in en_attente:
        pid = p.get("id")
        if not pid:
            continue
        verdict = evaluer_risque(p)
        if not verdict["faible_risque"]:
            journaliser("auto_skip", {"id": pid, "fichier": p.get("fichier"),
                                      "raison": verdict["raison"]})
            continue
        try:
            r = evolution.appliquer(pid, confirmation="INTERNE:AUTONOME", interne=True)
        except TypeError:
            r = {"succes": False, "erreur": "appliquer() sans support interne"}
        except Exception as e:
            r = {"succes": False, "erreur": str(e)[:200]}
        if r.get("succes"):
            appliquees.append(pid)
            journaliser("auto_applique", {"id": pid, "fichier": r.get("fichier"),
                                          "backup": r.get("backup")})
            _log(f"🤖 AUTO-APPLIQUÉ {pid} → {r.get('fichier')}")
        else:
            journaliser("auto_echec", {"id": pid, "erreur": r.get("erreur", "")[:200]})
    return appliquees


# ============================================================
# Boucle de fond
# ============================================================

def boucle_active() -> bool:
    return bool(_boucle_thread and _boucle_thread.is_alive())


def demarrer_boucle(intervalle_s: int = 1800) -> dict:
    """Lance le cycle autonome périodique dans un thread démon."""
    global _boucle_thread, _boucle_stop
    if boucle_active():
        return {"ok": True, "message": "Boucle déjà active."}
    try:
        intervalle_s = int(os.getenv("JIBI_AUTONOMIE_INTERVALLE", intervalle_s))
    except (TypeError, ValueError):
        pass
    intervalle_s = max(120, int(intervalle_s))
    _boucle_stop = threading.Event()

    def _run():
        _log(f"Boucle autonomie démarrée (toutes les {intervalle_s}s)")
        # Premier cycle rapide (30 s après le démarrage), puis périodique.
        if _boucle_stop.wait(30):
            return
        while not _boucle_stop.is_set():
            try:
                if est_semi_auto_ou_plus():
                    cycle_autonome()
            except Exception as e:
                journaliser("cycle_erreur", {"etape": "boucle", "erreur": str(e)[:200]})
            _boucle_stop.wait(intervalle_s)

    _boucle_thread = threading.Thread(target=_run, daemon=True, name="JibiAutonomie")
    _boucle_thread.start()
    return {"ok": True, "intervalle_s": intervalle_s}


def arreter_boucle() -> dict:
    global _boucle_thread, _boucle_stop
    if _boucle_stop:
        _boucle_stop.set()
    _boucle_thread = None
    return {"ok": True}


def statut() -> dict:
    """État complet pour la GUI / le CLI."""
    try:
        from core import evolution
        en_attente = len(evolution.lister("en_attente"))
        echouees = len(evolution.lister("tests_echoues"))
    except Exception:
        en_attente, echouees = 0, 0
    return {
        "niveau": get_niveau(),
        "boucle_active": boucle_active(),
        "propositions_en_attente": en_attente,
        "propositions_tests_echoues": echouees,
        "journal_dernier": (lire_journal(1) or [None])[0],
    }