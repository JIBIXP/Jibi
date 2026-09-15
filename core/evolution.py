"""
ÉVOLUTION — labo indépendant pour les changements écrits par le cerveau.
Ne touche pas self_improvement/. Réutilise validation.py en lecture seule.
Cycle : proposer() -> [humain lit le diff] -> appliquer(id, "J'AUTORISE <id>") -> tests -> rollback si échec.
"""
import json, shutil, difflib, uuid, importlib.util, py_compile, sys
from datetime import datetime
from pathlib import Path

DEPOT = Path(__file__).resolve().parent.parent
DIR = DEPOT / "workspace" / "jibi_lab" / "evolutions"
BACKUPS = DEPOT / "workspace" / "backups" / "evolutions"
DOSSIERS_PROTEGES = ("core", "self_improvement", "updater", ".git", "workspace")
FICHIERS_PROTEGES = {"agent.py", ".env", "requirements.txt", "logging_jibi.py", "serveur_modeles.py", "database.py"}


def protege(fichier: str) -> tuple:
    p = Path(fichier.replace("\\", "/"))
    if p.is_absolute():
        return True, "Chemin absolu interdit"
    if p.parts and p.parts[0] in DOSSIERS_PROTEGES:
        return True, f"Dossier protégé : {p.parts[0]}/"
    if p.name in FICHIERS_PROTEGES:
        return True, f"Fichier protégé : {p.name}"
    if p.suffix != ".py":
        return True, "Seuls les .py sont modifiables automatiquement"
    return False, ""


def _log(msg):
    try:
        from logging_jibi import log_event
        log_event("evolution", msg)
    except Exception:
        print(f"[evolution] {msg}")


def _path(pid): return DIR / f"{pid}.json"


def charger(pid: str):
    f = _path(pid)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _sauver(p): DIR.mkdir(parents=True, exist_ok=True); _path(p["id"]).write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def lister(statut=None) -> list:
    if not DIR.exists():
        return []
    out = []
    for f in DIR.glob("*.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            if statut is None or p.get("statut") == statut:
                out.append(p)
        except Exception:
            pass
    return sorted(out, key=lambda p: p.get("date_creation", ""), reverse=True)


def tester_contenu(fichier: str, contenu: str) -> dict:
    """Syntaxe + sécurité + import isolé (pour tools/). Ne touche pas au fichier réel."""
    res = {"ok": True, "details": []}
    try:
        compile(contenu, fichier, "exec")
        res["details"].append("✅ syntaxe")
    except SyntaxError as e:
        return {"ok": False, "details": [f"❌ syntaxe : {e}"]}
    try:
        from self_improvement.validation import analyser_modification
        v = analyser_modification(fichier, contenu)
        res["details"].append(f"{'🚫' if v['niveau']=='bloqué' else '✅'} sécurité : {v['niveau']}")
        res["risques"] = v.get("risques", [])
        if v["niveau"] == "bloqué":
            res["ok"] = False
            return res
    except Exception as e:
        res["details"].append(f"⚠️ validation indisponible : {e}")
    if fichier.startswith("tools/"):
        # FIX (bug de concurrence) : deux propositions évaluées en même temps
        # (ex. deux requêtes agent en vol après un clic sur "Annuler" côté GUI)
        # écrivaient toutes les deux sur le même fichier `_test_import.py`,
        # ce qui pouvait faire échouer/corrompre l'import isolé de l'une
        # des deux. Chaque appel utilise maintenant son propre nom de fichier.
        DIR.mkdir(parents=True, exist_ok=True)
        tmp = DIR / f"_test_import_{uuid.uuid4().hex[:8]}.py"
        tmp.write_text(contenu, encoding="utf-8")
        try:
            spec = importlib.util.spec_from_file_location(f"_ev_{uuid.uuid4().hex[:6]}", tmp)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            res["details"].append("✅ import isolé")
        except Exception as e:
            res["ok"] = False
            res["details"].append(f"❌ import : {e}")
        finally:
            tmp.unlink(missing_ok=True)
    return res


def proposer(fichier: str, demande: str, nouveau_contenu: str, origine="agent", priorite="moyenne") -> dict:
    fichier = fichier.replace("\\", "/")
    bloque, raison = protege(fichier)
    if bloque:
        return {"ok": False, "message": f"🚫 {raison}"}
    cible = DEPOT / fichier
    ancien = cible.read_text(encoding="utf-8", errors="replace") if cible.exists() else ""
    if ancien == nouveau_contenu:
        return {"ok": False, "message": "Aucun changement produit."}
    tests = tester_contenu(fichier, nouveau_contenu)
    diff = "".join(difflib.unified_diff(ancien.splitlines(True), nouveau_contenu.splitlines(True),
                                        f"a/{fichier}", f"b/{fichier}"))
    p = {
        "id": uuid.uuid4().hex[:12], "fichier": fichier, "type": "modification" if ancien else "nouveau_fichier",
        "probleme": demande, "solution": f"Réécriture proposée par {origine}", "priorite": priorite,
        "statut": "en_attente" if tests["ok"] else "tests_echoues",
        "date_creation": datetime.now().isoformat(), "origine": origine,
        "ancien": ancien, "nouveau": nouveau_contenu, "diff": diff, "tests": tests,
    }
    _sauver(p)
    _log(f"Proposition {p['id']} → {fichier} ({p['statut']})")
    return {"ok": tests["ok"], "proposition": p, "message": "\n".join(tests["details"])}


def rejeter(pid: str, commentaire="") -> dict:
    p = charger(pid)
    if not p:
        return {"ok": False, "message": "Introuvable"}
    p.update(statut="rejetee", date_decision=datetime.now().isoformat(), commentaire=commentaire)
    _sauver(p)
    return {"ok": True, "message": f"{pid} rejetée"}


def appliquer(pid: str, confirmation: str) -> dict:
    p = charger(pid)
    if not p:
        return {"succes": False, "erreur": f"Proposition {pid} introuvable"}
    if confirmation.replace("’", "'").strip().upper() != f"J'AUTORISE {pid}".upper():
        return {"succes": False, "erreur": "Phrase d'autorisation invalide"}
    if p["statut"] not in ("en_attente", "tests_echoues"):
        return {"succes": False, "erreur": f"Statut actuel : {p['statut']}"}
    if p["statut"] == "tests_echoues":
        return {"succes": False, "erreur": "Les tests labo ont échoué : " + " | ".join(p["tests"]["details"])}
    bloque, raison = protege(p["fichier"])
    if bloque:
        return {"succes": False, "erreur": raison}

    cible = DEPOT / p["fichier"]
    backup = None
    if cible.exists():
        BACKUPS.mkdir(parents=True, exist_ok=True)
        backup = BACKUPS / f"{datetime.now():%Y%m%d_%H%M%S}_{pid}_{cible.name}.bak"
        shutil.copy2(cible, backup)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(p["nouveau"], encoding="utf-8")

    # tests post-déploiement
    try:
        py_compile.compile(str(cible), doraise=True)
        if p["fichier"].startswith("tools/"):
            mod = p["fichier"][:-3].replace("/", ".")
            if mod in sys.modules:
                importlib.reload(sys.modules[mod])
            else:
                importlib.import_module(mod)
            if p["fichier"].startswith("tools/plugins/"):
                from tools.plugin_loader import charger_plugins
                r = charger_plugins()
                if any(cible.name in e for e in r.get("erreurs", [])):
                    raise RuntimeError("; ".join(r["erreurs"]))
    except Exception as e:
        if backup:
            shutil.copy2(backup, cible)
        else:
            cible.unlink(missing_ok=True)
        p.update(statut="rollback", erreur=str(e), date_decision=datetime.now().isoformat())
        _sauver(p)
        _log(f"ROLLBACK {pid} : {e}")
        return {"succes": False, "erreur": f"Échec post-déploiement → rollback effectué : {e}"}

    p.update(statut="appliquee", backup=str(backup) if backup else None, date_decision=datetime.now().isoformat())
    _sauver(p)
    _log(f"APPLIQUÉ {pid} → {p['fichier']}")
    return {"succes": True, "fichier": p["fichier"], "backup": str(backup) if backup else "(nouveau fichier)"}


def restaurer(pid: str) -> dict:
    p = charger(pid)
    if not p or not p.get("backup"):
        return {"ok": False, "message": "Pas de backup pour cette proposition"}
    shutil.copy2(p["backup"], DEPOT / p["fichier"])
    p["statut"] = "restauree"; _sauver(p)
    return {"ok": True, "message": f"{p['fichier']} restauré depuis {p['backup']}"}