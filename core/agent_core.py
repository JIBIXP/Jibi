"""
AGENT CORE v3.5 — FULL (diagnostic corrigé + evolution.proposer + router fichier)
"""
from __future__ import annotations
import re
import json
import time
import uuid
import threading
import inspect
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEPOT_DIR = Path(__file__).resolve().parent.parent
try:
    from core.config import JIBI_PROJET_DIR as _CFG_DEPOT
    DEPOT_DIR = _CFG_DEPOT
except Exception:
    pass

from core import evolution
try:
    from core import cerveau
except Exception:
    cerveau = None

try:
    from self_improvement.gestionnaire import analyser_jibi, preparer_amelioration, autoriser_et_appliquer
    from self_improvement.autorisation import rejeter_proposition, lister_propositions_en_attente
    SI_OK = True
except ImportError:
    SI_OK = False
    def analyser_jibi(**kw): return {"score_sante": 100, "niveau_sante": "?", "patterns_recurrents": [], "nombre_erreurs": 0}
    def preparer_amelioration(**kw): return {"ok": False, "message": "gestionnaire indisponible"}
    def autoriser_et_appliquer(**kw): return {"succes": False, "erreur": "gestionnaire indisponible"}
    def rejeter_proposition(**kw): return {"ok": False, "message": "indisponible"}
    def lister_propositions_en_attente(): return []

try:
    import tools
    from tools.tool_registry import get_tool, list_tools
    try:
        from tools.tool_registry import TOOLS_REGISTRY
    except Exception:
        TOOLS_REGISTRY = {}
    TOOLS_OK = True
except Exception:
    TOOLS_OK = False
    TOOLS_REGISTRY = {}
    def get_tool(n): return None
    def list_tools(): return {}

_TOOLS_CACHE: Dict[str, Any] = {"data": None, "t": 0.0}
_TOOLS_CACHE_TTL = 3.0  # secondes — list_tools() est appelé ~4x/message, inutile de rescanner à chaque fois

def _list_tools_cached() -> dict:
    now = time.time()
    if _TOOLS_CACHE["data"] is not None and (now - _TOOLS_CACHE["t"]) < _TOOLS_CACHE_TTL:
        return _TOOLS_CACHE["data"]
    try:
        data = list_tools() or {}
    except Exception:
        data = {}
    _TOOLS_CACHE["data"] = data
    _TOOLS_CACHE["t"] = now
    return data

RE_AUTORISE = re.compile(r"^j(?:['’])?autorise\s+(\S+)", re.I)
RE_REJET = re.compile(r"^(?:je\s+)?rejet(?:t?e|er)\s+(\S+)", re.I)
RE_CONFIRME = re.compile(r"^(?:confirme|oui)\s+(\S+)\s*$", re.I)
RE_FICHIER = re.compile(r"[\w./\\-]+\.py")
RE_CREATION = re.compile(r"^(?:cr[ée]e|ajoute)\s+(?:un\s+|une\s+)?(?:outil|fonctionnalit[ée]|plugin|fonction)\s+([A-Za-z_]\w*)\s*:\s*(.+)$", re.I | re.S)
RE_LANCE = re.compile(r"^(?:lance|ex[ée]cute|execute)\s+([a-zA-Z_]\w*)\s*(.*)$", re.I | re.S)
RE_LIS_URL = re.compile(r"^(?:lis|lire)\s+(https?://\S+)\s*$", re.I)
RE_OUVRE = re.compile(r"^(?:ouvre|va\s+sur|va\s+à)\s+(.+)$", re.I)
RE_SALUTATION = re.compile(r"^(bonjour|bonsoir|salut|coucou|hello|hey|yo|[cç]a\s*va\??|comment\s*(vas[- ]tu|ça\s*va|tu\s*vas)\??)\s*[!.?]*$", re.I)
RE_JSON_ARGS = re.compile(r"(\{.*\})", re.S)
RE_KV = re.compile(r"""(\w+)\s*=\s*(".*?"|'.*?'|\S+)""")

MODIFIABLES_DIAG = ["gui.py", "tools/browser.py", "tools/files.py", "tools/pc_control.py", "tools/terminal.py", "tools/vision.py", "tools/documents.py", "tools/web_search.py"]
SITES_CONNUS = {"google": "https://www.google.com", "youtube": "https://www.youtube.com", "gmail": "https://mail.google.com", "wikipedia": "https://www.wikipedia.org", "github": "https://github.com", "chatgpt": "https://chat.openai.com", "twitter": "https://x.com", "x": "https://x.com", "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com"}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

# ==========================================
# FIX 1 : classification_locale reçoit "améliore"
# ==========================================
def classification_locale(msg: str) -> str:
    low = (msg or "").strip().lower()
    if not low:
        return "DISCUSSION"
    if RE_SALUTATION.match(low):
        return "SALUTATION"
    if re.match(r"^(cherche|recherche|trouve)\b", low):
        return "RECHERCHE"
    if re.search(r"\.(py|txt|md|json|csv)\b", low) or "fichier" in low:
        # FIX : ajoute "améliore|ameliore|change|corrige|optimise|design"
        if re.search(r"^(crée|cree|ouvre|lis|lire|modifie|édite|supprime|renomme|liste|écris|ecris|améliore|ameliore|change|corrige|optimise|design)", low):
            return "FICHIER"
    if re.search(r"(code|fonction|classe|python|javascript|bug|corrige|implémente)", low):
        return "CODE"
    first = low.split()[0] if low.split() else ""
    try:
        tools_list = _list_tools_cached() or {}
        if first in tools_list:
            return "OUTIL"
    except Exception:
        pass
    if re.match(r"^(diagnostic|diagnostique|status|statut|état|etat|score|santé|sante)\b", low):
        return "DIAGNOSTIC"
    if re.match(r"^(executer|exécuter|commande|shell|terminal)\b", low):
        return "COMMANDE"
    if "?" in msg or low.startswith(("que ", "qui ", "ou ", "où ", "comment ", "pourquoi ", "quand ")):
        return "QUESTION"
    if len(low.split()) <= 6:
        return "DISCUSSION"
    return "TACHE_COMPLEXE"

@dataclass
class ReponseAgent:
    texte: str
    confidence: float = 0.8
    action_requise: Optional[Dict[str, Any]] = None
    amelioration_proposee: bool = False
    requiere_autorisation: bool = False
    proposition_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    date_creation: str = field(default_factory=lambda: datetime.now().isoformat())
    def to_dict(self):
        return self.__dict__.copy()

class AgentCore:
    def __init__(self, config=None):
        self._historique: List[Dict] = []
        self._nombre_actions_total = 0
        self._nombre_actions_succes = 0
        self._nombre_erreurs = 0
        self._nombre_ameliorations_proposees = 0
        self._nombre_ameliorations_appliquees = 0
        self._derniere_analyse_sante = {"score": 100, "date": None}
        self._actions_en_attente: Dict[str, Dict[str, Any]] = {}
        self._llm_cache = {"ok": False, "t": 0.0}
        self._lock = threading.Lock()
        self._last_timings: Dict[str, float] = {}

    def _llm_disponible(self) -> bool:
        if cerveau is None:
            return False
        now = time.time()
        with self._lock:
            if now - self._llm_cache["t"] < 5.0:
                return bool(self._llm_cache["ok"])
        try:
            ok = bool(cerveau.disponible(force=True))
        except Exception:
            ok = False
        with self._lock:
            self._llm_cache = {"ok": ok, "t": now}
        return ok

    def _doit_appeler_llm(self, msg: str) -> bool:
        msg = msg or ""
        low = msg.lower().strip()
        if not msg:
            return False
        if (RE_AUTORISE.match(msg) or RE_REJET.match(msg) or RE_CONFIRME.match(msg)):
            return False
        if low.strip(" .!?") in {"liste", "list", "propositions", "en attente", "status", "statut", "santé", "sante", "état", "etat", "score"}:
            return False
        if (RE_LANCE.match(msg) or RE_LIS_URL.match(msg) or RE_OUVRE.match(msg)):
            return False
        if RE_SALUTATION.match(low):
            return False
        parties = msg.split(None, 1)
        first = parties[0] if parties else ""
        if first and first in (_list_tools_cached() or {}):
            return False
        if len(msg) < 12:
            return False
        return True

    def _est_discussion_simple(self, msg: str) -> bool:
        low = _norm(msg).lower()
        if not low:
            return False
        mots_action = ("modifie", "modifier", "change", "changer", "corrige", "corriger", "améliore", "ameliore", "optimise", "crée", "cree", "ajoute", "supprime", "efface", "cherche", "recherche", "trouve", "ouvre", "lance", "exécute", "execute", "diagnostique", "diagnostic", "répare", "repare", "installe", "désinstalle", "desinstalle", "lis ", "lire ", "écris", "ecris", "fais un fichier", "crée un fichier", "cree un fichier")
        if any(k in low for k in mots_action):
            return False
        if RE_FICHIER.search(msg):
            return False
        parties = msg.split(None, 1)
        first = parties[0] if parties else ""
        if first and first in (_list_tools_cached() or {}):
            return False
        if len(low) <= 80:
            return True
        return False

    def _parse_args(self, txt: str) -> dict:
        txt = (txt or "").strip()
        if not txt:
            return {}
        m = RE_JSON_ARGS.search(txt)
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        out = {}
        for k, v in RE_KV.findall(txt):
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            elif v.lower() in ("true", "false"):
                v = v.lower() == "true"
            else:
                try:
                    v = int(v)
                except Exception:
                    try:
                        v = float(v)
                    except Exception:
                        pass
            out[k] = v
        return out

    def _tool_spec(self, nom: str) -> dict:
        try:
            return (TOOLS_REGISTRY or {}).get(nom) or {}
        except Exception:
            return {}

    def _valider_schema(self, schema: dict | None, args: dict) -> Tuple[bool, str, dict]:
        if not schema or schema.get("type") != "object":
            return True, "schema: (aucun)", args
        props = schema.get("properties", {}) or {}
        required = set(schema.get("required", []) or [])
        missing = [k for k in required if k not in args]
        if missing:
            return False, "Paramètres manquants: " + ", ".join(missing), args
        casted = dict(args)
        for k, spec in props.items():
            if k not in casted:
                continue
            t = (spec or {}).get("type")
            v = casted[k]
            try:
                if t == "integer" and not isinstance(v, int):
                    casted[k] = int(v)
                elif t == "number" and not isinstance(v, (int, float)):
                    casted[k] = float(v)
                elif t == "boolean" and not isinstance(v, bool):
                    casted[k] = str(v).lower() in ("1", "true", "yes", "oui")
                elif t == "string" and not isinstance(v, str):
                    casted[k] = str(v)
            except Exception:
                return False, f"Type invalide pour {k} (attendu {t})", args
        return True, "schema: OK", casted

    def _est_sensible(self, nom: str, args: dict, schema: dict | None) -> bool:
        if (schema and schema.get("properties") and "confirmer" in schema["properties"]):
            return not bool((args or {}).get("confirmer"))
        n = (nom or "").lower()
        segments = set(n.split("_"))
        if "rm" in segments:
            return True
        racines_specifiques = ("supprim", "delete", "remove", "wipe", "format", "kill", "update", "mise_a_jour", "restaurer")
        if any(x in n for x in racines_specifiques):
            return True
        return False

    def url_directe_pour_message(self, msg: str) -> Optional[str]:
        m = RE_OUVRE.match(msg.strip())
        if not m:
            return None
        cible = _norm(m.group(1)).lower()
        cible = re.sub(r"^(le|la|les|un|une)\s+", "", cible).strip()
        if cible.startswith(("http://", "https://")):
            return cible
        if cible.startswith("www."):
            return "https://" + cible
        return SITES_CONNUS.get(cible)

    def traiter_message(self, message: str, context=None, on_chunk=None, cancel_event=None) -> ReponseAgent:
        t_router0 = time.perf_counter()
        msg = _norm(message)
        low = msg.lower()
        self._log("reçu", msg)
        cat = classification_locale(msg)
        t_router = time.perf_counter() - t_router0
        try:
            mc = RE_CONFIRME.match(msg)
            if mc:
                aid = mc.group(1)
                with self._lock:
                    pending = self._actions_en_attente.pop(aid, None)
                if not pending:
                    return ReponseAgent("Action à confirmer introuvable/expirée.", 0.6, metadata={"categorie": cat, "timings": {"ROUTER": round(t_router,4)}})
                args = dict(pending.get("args") or {})
                args["confirmer"] = True
                return self._executer(pending["outil"], args)

            if RE_AUTORISE.match(msg):
                return self._autoriser(RE_AUTORISE.match(msg).group(1))
            if RE_REJET.match(msg):
                return self._rejeter(RE_REJET.match(msg).group(1))
            if low.strip(" .!?") in {"liste", "list", "propositions", "en attente"}:
                return self._liste()
            if cat == "SALUTATION":
                return ReponseAgent("Salut ! Je suis JIBI, ton assistant local. Dis-moi ce que tu veux faire, ou tape « aide » pour voir les commandes.", 0.9, metadata={"categorie": cat, "timings": {"ROUTER": round(t_router,4)}})
            if cat == "RECHERCHE":
                requete = re.sub(r"^(cherche|recherche|trouve)\s*(moi\s*)?", "", msg, flags=re.I).strip()
                if not requete:
                    requete = msg
                rep = self._rechercher(requete)
                rep.metadata.update({"categorie": cat, "timings": {"ROUTER": round(t_router,4)}})
                return rep
            if cat == "DIAGNOSTIC":
                if cancel_event and cancel_event.is_set():
                    return ReponseAgent("⏹️ Annulé.", 0.9, metadata={"categorie": cat})
                rep = self._diagnostic(creer_propositions=True)
                rep.metadata.update({"categorie": cat})
                return rep

            # ==========================================
            # FIX 2 : ROUTER LOCAL FICHIER AVANT LLM
            # ==========================================
            if any(k in low for k in ("améliore", "ameliore", "modifie", "change", "corrige", "optimise", "design")):
                fichiers = self._trouver_fichiers(msg)
                if not fichiers and ("design" in low or "interface" in low or "couleur" in low):
                    fichiers = ["gui.py"]
                if fichiers:
                    return self._modifier_fichier(fichiers[0], msg.split(":",1)[-1].strip())

            ml = RE_LIS_URL.match(msg)
            if ml:
                url = ml.group(1)
                if get_tool("lire_page"):
                    return self._executer("lire_page", {"url": url, "max_caracteres": 4000})
                return ReponseAgent("⚠️ Outil lire_page indisponible.", 0.5)
            url = self.url_directe_pour_message(msg)
            if url and get_tool("ouvrir_url"):
                return self._executer("ouvrir_url", {"url": url})
            if RE_CREATION.match(msg):
                m = RE_CREATION.match(msg)
                return self._creer_outil(m.group(1), m.group(2))
            ml = RE_LANCE.match(msg)
            if ml:
                nom_outil = ml.group(1)
                if nom_outil in (_list_tools_cached() or {}):
                    args = self._parse_args(ml.group(2) or "")
                    return self._executer(nom_outil, args)
            parties = msg.split(None, 1)
            first = parties[0] if parties else ""
            if first and first in (_list_tools_cached() or {}):
                rest = msg[len(first):].strip()
                return self._executer(first, self._parse_args(rest))
            if (("voir" in low and "code" in low) or ("lire" in low and "code" in low)):
                if get_tool("lire_code_source"):
                    rep = None
                    for f in ("core/agent_core.py", "gui.py", "tools/__init__.py"):
                        rep = self._executer("lire_code_source", {"chemin": f})
                        if "❌" not in rep.texte:
                            return rep
                    if rep:
                        return rep
                return ReponseAgent("⚠️ Outil lire_code_source indisponible.", 0.5)

            if self._doit_appeler_llm(msg):
                if cerveau and self._est_discussion_simple(msg):
                    try:
                        if on_chunk or cancel_event:
                            texte = cerveau.completer(msg, profil="CONVERSATION", stream=bool(on_chunk), on_chunk=on_chunk, cancel_event=cancel_event)
                        else:
                            texte = cerveau.completer(msg, profil="CONVERSATION")
                        return ReponseAgent(texte, 0.85, metadata={"categorie": cat, "profil": "CONVERSATION", "timings": {"ROUTER": round(t_router,4)}})
                    except Exception:
                        pass
                llm_ok = self._llm_disponible()
                if llm_ok:
                    try:
                        return self._router_llm(msg, on_chunk=on_chunk, cancel_event=cancel_event, categorie=cat, t_router=t_router)
                    except Exception:
                        return self._router_regles(msg, low)
            return self._router_regles(msg, low)
        except Exception as e:
            self._nombre_erreurs += 1
            return ReponseAgent(f"❌ Erreur interne : {e}", 0.2, metadata={"categorie": cat, "timings": {"ROUTER": round(t_router,4)}})

    def _router_llm(self, msg: str, on_chunk=None, cancel_event=None, categorie="TACHE_COMPLEXE", t_router=0) -> ReponseAgent:
        if self._est_discussion_simple(msg):
            texte = cerveau.completer(msg, profil="CONVERSATION", stream=bool(on_chunk), on_chunk=on_chunk, cancel_event=cancel_event)
            return ReponseAgent(texte, 0.85, metadata={"categorie": categorie, "profil": "CONVERSATION"})
        if categorie == "FICHIER":
            fichiers = self._trouver_fichiers(msg)
            if fichiers:
                return self._modifier_fichier(fichiers[0], msg.split(":",1)[-1].strip() or msg)
        if categorie == "CODE" and cerveau:
            try:
                if len(msg) < 500:
                    texte = cerveau.completer(msg, profil="CODE", stream=bool(on_chunk), on_chunk=on_chunk, cancel_event=cancel_event)
                    return ReponseAgent(texte, 0.85, metadata={"categorie": categorie, "profil": "CODE"})
            except Exception:
                pass
        plan = cerveau.planifier(msg, contexte="Outils disponibles : " + ", ".join(list(_list_tools_cached())[:60]))
        it = plan.get("intention", "discussion")
        desc = (plan.get("description") or msg)
        if (it == "modifier_fichier" and plan.get("fichier")):
            return self._modifier_fichier(plan["fichier"], desc)
        if (it == "creer_outil" and plan.get("nom_outil")):
            return self._creer_outil(plan["nom_outil"], desc)
        if it == "diagnostic":
            return self._diagnostic(creer_propositions=True)
        if it == "rechercher_web":
            return self._rechercher(plan.get("requete") or msg)
        if (it == "executer_outil" and plan.get("nom_outil")):
            return self._executer(plan["nom_outil"], plan.get("arguments") or {})
        if it == "etat":
            return self._etat()
        if it == "liste":
            return self._liste()
        reponse = plan.get("reponse")
        if reponse:
            return ReponseAgent(reponse, 0.85, metadata={"categorie": categorie})
        texte = cerveau.completer(msg, profil="QUESTION" if categorie=="QUESTION" else "CONVERSATION", stream=bool(on_chunk), on_chunk=on_chunk, cancel_event=cancel_event)
        return ReponseAgent(texte, 0.85, metadata={"categorie": categorie})

    def _router_regles(self, msg: str, low: str) -> ReponseAgent:
        if RE_SALUTATION.match(low):
            return ReponseAgent("Salut ! Je suis JIBI, ton assistant local. Dis-moi ce que tu veux faire, ou tape « aide » pour voir les commandes.", 0.9)
        if (any(low.startswith(k) for k in ("cherche", "trouve", "recherche")) or "sur internet" in low or "sur le net" in low):
            requete = re.sub(r"^(cherche|trouve|recherche)\s*(moi\s*)?", "", msg, flags=re.I)
            return self._rechercher(requete)
        if ("diagnosti" in low or ("devrais" in low and ("améliorer" in low or "ameliorer" in low))):
            return self._diagnostic(creer_propositions=True)
        if any(k in low for k in ("améliore", "ameliore", "modifie", "change", "corrige", "optimise", "design")):
            fichiers = self._trouver_fichiers(msg)
            if not fichiers and ("design" in low or "interface" in low or "couleur" in low):
                fichiers = ["gui.py"]
            if not fichiers:
                return ReponseAgent("🔍 Précise le fichier : ex. 'Améliore gui.py : fond plus sombre'", 0.6)
            return self._modifier_fichier(fichiers[0], msg.split(":",1)[-1].strip())
        if low.strip(" .!?") in {"status", "statut", "santé", "sante", "état", "etat", "score"}:
            return self._etat()
        if low.strip(" .!?") in {"aide", "help", "commandes", "commande", "?"}:
            return self._aide(low)
        if (self._llm_disponible() and cerveau):
            try:
                return ReponseAgent(cerveau.completer(msg, profil="CONVERSATION"), 0.8)
            except Exception:
                pass
        return self._aide(low)

    def _modifier_fichier(self, fichier: str, demande: str) -> ReponseAgent:
        fichier = fichier.replace("\\", "/")
        bloque, raison = evolution.protege(fichier)
        if bloque:
            return ReponseAgent(f"🚫 {raison}\nCe fichier ne se modifie qu'à la main (frein de sécurité).", 0.9)
        cible = DEPOT_DIR / fichier
        if not cible.exists():
            return ReponseAgent(f"❌ {fichier} n'existe pas. Pour créer : 'Crée un outil nom : description'", 0.6)
        if (self._llm_disponible() and cerveau):
            contenu = cible.read_text(encoding="utf-8", errors="replace")
            nouveau = cerveau.reecrire_fichier(fichier, contenu, demande)
            res = evolution.proposer(fichier, demande, nouveau, origine="cerveau")
            if not res.get("proposition"):
                return ReponseAgent(f"⚠️ {res.get('message')}", 0.5)
            p = res["proposition"]
            self._nombre_ameliorations_proposees += 1
            etat = "✅ tests labo OK" if res["ok"] else "❌ tests labo échoués (autorisation impossible)"
            return ReponseAgent("🧪 Proposition prête (fichier réel intact)\n\n"
                              f"  • ID : {p['id']}\n"
                              f"  • Fichier : {fichier}\n"
                              f"  • {etat}\n"
                              f"  {res['message']}\n\n"
                              f"🔍 Diff Viewer → ID {p['id']}\n"
                              f"🔐 J'AUTORISE {p['id']}   |   🚫 Rejette {p['id']}", 0.9,
                              amelioration_proposee=True, requiere_autorisation=True, proposition_id=p["id"])
        r = preparer_amelioration(fichier=fichier, probleme=demande, solution=demande[:300], justification="Demande utilisateur", priorite="moyenne")
        pid = (r.get("proposition") or {}).get("id")
        return ReponseAgent(f"🔧 (mode sans LLM) Proposition {pid or '—'} pour {fichier}.\n"
                          "⚠️ Configure JIBI_LLM_URL/MODEL pour activer le cerveau.\n"
                          + (f"J'AUTORISE {pid}" if pid else f"⚠️ {r.get('message')}"), 0.7, proposition_id=pid)

    def _creer_outil(self, nom: str, description: str) -> ReponseAgent:
        nom = re.sub(r"[^a-z0-9_]", "_", nom.lower()).strip("_")
        fichier = f"tools/plugins/{nom}.py"
        if (DEPOT_DIR / fichier).exists():
            return ReponseAgent(f"⚠️ {fichier} existe déjà → 'Améliore {fichier} : {description}'", 0.8)
        llm_ok = (self._llm_disponible() and cerveau)
        if llm_ok:
            code = cerveau.creer_outil(nom, description)
            origine = "cerveau"
        else:
            code = self._squelette(nom, description)
            origine = "squelette"
        res = evolution.proposer(fichier, f"Nouvel outil : {description}", code, origine=origine)
        if not res.get("proposition"):
            return ReponseAgent(f"⚠️ {res.get('message')}", 0.5)
        p = res["proposition"]
        self._nombre_ameliorations_proposees += 1
        return ReponseAgent(f"🆕 Nouvel outil préparé : {fichier}\n"
                          f"  • ID : {p['id']}\n"
                          f"  {res['message']}\n\n"
                          f"🔍 Relis le code (Diff Viewer) puis : J'AUTORISE {p['id']}", 0.9,
                          amelioration_proposee=True, requiere_autorisation=True, proposition_id=p["id"])

    def _diagnostic(self, creer_propositions=False) -> ReponseAgent:
        analyse = (analyser_jibi(depuis_heures=48) if SI_OK else {})
        lignes = [f"🩺 DIAGNOSTIC JIBI — score {analyse.get('score_sante', '?')}/100"]
        for pat in analyse.get("patterns_recurrents", [])[:5]:
            lignes.append(f"  🔁 {pat.get('message', '?')[:80]} (×{pat.get('frequence', '?')})")
        if not (self._llm_disponible() and cerveau):
            lignes.append("\n⚠️ Sans LLM je ne peux pas analyser mon code.")
            return ReponseAgent("\n".join(lignes), 0.7)
        fichiers = {f: (DEPOT_DIR / f).read_text(encoding="utf-8", errors="replace")
                    for f in MODIFIABLES_DIAG if (DEPOT_DIR / f).exists()}
        idees = cerveau.diagnostiquer(analyse, fichiers)
        if not idees:
            lignes.append("\nAucune amélioration identifiée.")
            return ReponseAgent("\n".join(lignes), 0.8)
        lignes.append(f"\n💡 {len(idees)} amélioration(s) identifiée(s) :")
        propositions_ids = []
        if creer_propositions:
            # Chaque idée = 1 appel LLM séquentiel (reecrire_fichier) ; sur un petit modèle local
            # ça coûte cher. On ne génère les correctifs que pour les idées prioritaires.
            ordre_prio = {"haute": 0, "moyenne": 1, "basse": 2}
            idees_triees = sorted(idees, key=lambda d: ordre_prio.get((d.get("priorite") or "moyenne").lower(), 1))
            MAX_CORRECTIFS = 3
            idees_retenues = idees_triees[:MAX_CORRECTIFS]
            if len(idees) > len(idees_retenues):
                lignes.append(f"  (génération limitée aux {len(idees_retenues)} idées les plus prioritaires sur {len(idees)} — dis « génère la N » pour une idée précise)")
            lignes.append("\n🛠️ Génération des correctifs...")
            for i, idee in enumerate(idees_retenues, 1):
                f_cible = idee.get("fichier")
                if not f_cible or f_cible not in fichiers:
                    lignes.append(f"  {i}. ⚠️ Fichier cible introuvable : {f_cible}")
                    continue
                desc = idee.get("description", "")
                try:
                    nouveau = cerveau.reecrire_fichier(f_cible, fichiers[f_cible], desc)
                    res = evolution.proposer(f_cible, f"Auto-Fix: {idee.get('titre','')}", nouveau, origine="auto_diagnostic")
                    if res.get("proposition"):
                        pid = res["proposition"]["id"]
                        propositions_ids.append(pid)
                        etat = "✅ Tests OK" if res["ok"] else "⚠️ Tests échoués"
                        lignes.append(f"  {i}. [{pid}] {f_cible} — {etat}")
                    else:
                        lignes.append(f"  {i}. ❌ Échec création : {res.get('message')}")
                except Exception as e:
                    lignes.append(f"  {i}. ❌ Erreur : {str(e)[:60]}")
            if propositions_ids:
                lignes.append("\n👉 Allez dans 'Évolutions' pour voir les diffs et AUTORISER les IDs ci-dessus.")
                return ReponseAgent("\n".join(lignes), 0.95, proposition_id=propositions_ids[0])
        lignes.append("\nDemande: « génère la 1 » si tu veux que je prépare UNE proposition.")
        return ReponseAgent("\n".join(lignes), 0.9)

    def _rechercher(self, requete: str) -> ReponseAgent:
        try:
            from tools.web_search import rechercher, formater_resultats
        except Exception:
            return ReponseAgent("⚠️ tools/web_search.py manquant.", 0.4)
        typ = ("videos" if any(k in (requete or "").lower() for k in ("vidéo", "video", "youtube")) else "web")
        r = rechercher(requete, 8, typ)
        if not r.get("ok"):
            return ReponseAgent(f"❌ Recherche impossible : {r.get('erreur')}", 0.4)
        txt = formater_resultats(r)
        return ReponseAgent(txt + "\n\nDis « lis <url> » pour lire une page.", 0.9)

    def _executer(self, nom: str, args: dict) -> ReponseAgent:
        fn = get_tool(nom)
        if not fn:
            return ReponseAgent(f"Outil '{nom}' inconnu.", 0.5)
        spec = self._tool_spec(nom) or {}
        schema = spec.get("parametres")
        ok, msg, args2 = self._valider_schema(schema, args or {})
        if not ok:
            return ReponseAgent(f"❌ {nom} : {msg}\nSchéma: {json.dumps(schema, ensure_ascii=False)}", 0.6)
        if self._est_sensible(nom, args2, schema):
            action_id = uuid.uuid4().hex[:10]
            with self._lock:
                self._actions_en_attente[action_id] = {"outil": nom, "args": args2}
            return ReponseAgent("⚠️ Action sensible.\nRésumé: " + nom + "(" + str(args2) + ")\nConfirme: CONFIRME " + action_id, 0.85, action_requise={"type": "confirmation", "id": action_id, "outil": nom, "args": args2})
        try:
            r = (fn(**args2) if args2 else fn())
            self._nombre_actions_succes += 1
            return ReponseAgent(f"🔧 {nom} → {str(r)[:1500]}", 0.9)
        except Exception as e:
            self._nombre_erreurs += 1
            return ReponseAgent(f"❌ {nom} : {e}", 0.5)

    def _autoriser(self, pid: str) -> ReponseAgent:
        conf = f"J'AUTORISE {pid}"
        if evolution.charger(pid):
            r = evolution.appliquer(pid, conf)
        else:
            r = autoriser_et_appliquer(proposition_id=pid, confirmation=conf, commentaire="via chat")
        if r.get("succes"):
            self._nombre_ameliorations_appliquees += 1
            note = ("\n\n🎨 gui.py modifié : relance JIBI pour voir le nouveau design." if r.get("fichier") == "gui.py" else "")
            return ReponseAgent("✅ APPLIQUÉ\n" + f"  • {r.get('fichier')}\n" + f"  • backup : {r.get('backup')}" + note, 0.99, proposition_id=pid)
        self._nombre_erreurs += 1
        return ReponseAgent(f"❌ {r.get('erreur') or r.get('message')}", 0.5, proposition_id=pid)

    def _rejeter(self, pid: str) -> ReponseAgent:
        if evolution.charger(pid):
            r = evolution.rejeter(pid, "via chat")
        else:
            r = rejeter_proposition(prop_id=pid, commentaire="via chat")
        return ReponseAgent(f"🚫 {pid} rejetée." if r.get("ok") else f"❌ {r.get('message')}", 0.9)

    def _liste(self) -> ReponseAgent:
        props = (evolution.lister("en_attente") + evolution.lister("tests_echoues") + list(lister_propositions_en_attente() or []))
        if not props:
            return ReponseAgent("📋 Aucune proposition en attente.", 0.9)
        out = [f"📋 {len(props)} proposition(s) :"]
        for p in props[:15]:
            out.append(f"  • [{p.get('id')}] " + f"{p.get('fichier')} — " + f"{p.get('statut')} — " + f"{p.get('probleme', '')[:60]}")
        out.append("\nJ'AUTORISE <id>   |   Rejette <id>")
        return ReponseAgent("\n".join(out), 0.95)

    def _etat(self) -> ReponseAgent:
        a = (analyser_jibi(depuis_heures=24) if SI_OK else {})
        s = a.get("score_sante", 100)
        self._derniere_analyse_sante = {"score": s, "date": datetime.now().isoformat()}
        llm = self._llm_disponible()
        model = (getattr(cerveau, "MODEL", "?") if (llm and cerveau) else "OFF")
        return ReponseAgent(f"Santé {s}/100 " + f"({a.get('niveau_sante', '?')})" +
                            f"\n  • Erreurs 24h : " + f"{a.get('nombre_erreurs', 0)}   " +
                            f"• Cerveau LLM : " + f"{('✅ ' + model) if llm else '❌ OFF'}" +
                            f"\n  • Outils : " + f"{len(_list_tools_cached() or {})}", 0.95)

    def _aide(self, low: str) -> ReponseAgent:
        return ReponseAgent("Commandes :\n" +
                           "  • Status / Liste / J'AUTORISE <id> / Rejette <id>\n" +
                           "  • Va sur google | ouvre github | lis https://...\n" +
                           "  • Lance <outil> {json} (ou key=value)\n" +
                           "  • Cherche <requête>\n", 0.8)

    def _trouver_fichiers(self, txt: str) -> List[str]:
        matches = RE_FICHIER.findall(txt or "")
        if not matches:
            return []
        out: List[str] = []
        for raw in matches:
            c = (raw.replace("\\", "/").strip().lstrip("./"))
            if "/" in c:
                if (DEPOT_DIR / c).is_file() and c not in out:
                    out.append(c)
                continue
            for cand in (c, f"tools/{c}", f"tools/plugins/{c}"):
                if (DEPOT_DIR / cand).is_file() and cand not in out:
                    out.append(cand)
                    break
        if len(out) > 1:
            out = sorted(out, key=lambda p: (p.count("/"), len(p)), reverse=True)
            out = [out[0]]
        return out

    @staticmethod
    def _squelette(nom, description):
        return (f'"""{description}"""\n\n' +
                f"def {nom}(**kwargs) -> dict:\n" +
                f'    """{description}"""\n' +
                f'    return {{"ok": True, "outil": "{nom}", "parametres": kwargs, "message": "à compléter"}}\n\n\n' +
                f'OUTILS = {{"{nom}": {{"fonction": {nom}, "description": "{description[:100]}", "parametres": {{"type": "object", "properties": {{}}, "required": []}}}}}}\n')

    def _log(self, t, d=""):
        with self._lock:
            self._historique.append({"type": t, "detail": d[:200], "timestamp": datetime.now().isoformat()})
            self._nombre_actions_total += 1


if __name__ == "__main__":
    print("AGENT CORE v3.5 — FULL")
    ac = AgentCore()
    print("AgentCore OK — traitement message test :", ac.traiter_message("bonjour").texte[:60])