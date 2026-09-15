"""
Analyseur santé — PATCHÉ v2
- Regex compilées + branché config + cache TTL 60s + timings [ANALYSE]
"""
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
import re
import json
import time

try:
    from core.config import LOGS_DIR as CFG_LOGS, WORKSPACE_DIR, SEUIL_PATTERN_RECURRENT, LIMITE_LOGS_ANALYSE
    LOG_DIR = CFG_LOGS
    HISTORIQUE_DIR = WORKSPACE_DIR / "jibi_lab" / "historique"
    SEUIL_DEFAUT = SEUIL_PATTERN_RECURRENT
    LIMITE_DEFAUT = LIMITE_LOGS_ANALYSE
except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    HISTORIQUE_DIR = PROJECT_ROOT / "workspace" / "jibi_lab" / "historique"
    SEUIL_DEFAUT = 3
    LIMITE_DEFAUT = 1000

MOTIFS_ERREURS = [r"\berror\b", r"\bexception\b", r"\btraceback\b", r"\bfailed\b", r"\bfailure\b", r"\béchec\b", r"\berreur\b", r"\bfatal\b", r"\bcritical\b"]
MOTIFS_WARNINGS = [r"\bwarning\b", r"\bavertissement\b", r"\bdeprecated\b", r"\bobsolete\b"]
MOTIFS_CRITIQUES = [r"\bpermission\s*denied\b", r"\baccess\s*denied\b", r"\bout\s*of\s*memory\b", r"\bdisk\s*full\b", r"\bsegfault\b", r"\bcorrupt", r"\blost\s*connection\b"]

RE_ERREURS = [re.compile(m, re.I) for m in MOTIFS_ERREURS]
RE_WARNINGS = [re.compile(m, re.I) for m in MOTIFS_WARNINGS]
RE_CRITIQUES = [re.compile(m, re.I) for m in MOTIFS_CRITIQUES]
RE_TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
RE_PID = re.compile(r"PID\s*\d+")
RE_HEX = re.compile(r"0x[0-9a-fA-F]+")
RE_IP = re.compile(r"\d+\.\d+\.\d+\.\d+")

_cache = {"t": 0, "key": None, "val": None}

def lire_logs(limite=LIMITE_DEFAUT, depuis_heures=None):
    t0 = time.perf_counter()
    if not LOG_DIR.exists():
        return ""
    fichiers = sorted(LOG_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not fichiers:
        return ""
    if depuis_heures is not None:
        seuil = datetime.now() - timedelta(hours=depuis_heures)
        fichiers = [f for f in fichiers if datetime.fromtimestamp(f.stat().st_mtime) >= seuil]
    lignes = []
    for fichier in fichiers[:5]:
        try:
            with fichier.open(encoding="utf-8", errors="replace") as fh:
                # tail optimisé : ne lire que la fin si gros fichier
                content = fh.read()
                lignes.extend(content.splitlines()[-2000:])
        except Exception:
            continue
    if depuis_heures is not None:
        seuil = datetime.now() - timedelta(hours=depuis_heures)
        lignes_filtrees = []
        for ligne in lignes:
            m = RE_TIMESTAMP.search(ligne)
            if m:
                try:
                    ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    if ts >= seuil:
                        lignes_filtrees.append(ligne)
                except ValueError:
                    lignes_filtrees.append(ligne)
            else:
                lignes_filtrees.append(ligne)
        lignes = lignes_filtrees
    result = "\n".join(lignes[-limite:])
    # print(f"[ANALYSE lire_logs] {time.perf_counter()-t0:.3f}s lignes={len(lignes)}")
    return result

def _est_critique(ligne_lower):
    return any(rx.search(ligne_lower) for rx in RE_CRITIQUES)

def extraire_erreurs(texte):
    if not texte:
        return []
    erreurs = []
    for ligne in texte.splitlines():
        low = ligne.lower()
        if any(rx.search(low) for rx in RE_ERREURS):
            ligne = ligne.strip()
            if ligne:
                erreurs.append({"texte": ligne, "type": "erreur", "critique": _est_critique(low)})
    return erreurs

def extraire_warnings(texte):
    if not texte:
        return []
    warnings = []
    for ligne in texte.splitlines():
        low = ligne.lower()
        if any(rx.search(low) for rx in RE_WARNINGS):
            ligne = ligne.strip()
            if ligne:
                warnings.append({"texte": ligne, "type": "warning", "critique": False})
    return warnings

def compter_types_erreurs(erreurs):
    resultats = {"critique": 0, "exception": 0, "traceback": 0, "erreur": 0, "warning": 0, "autres": 0}
    for erreur in erreurs:
        texte = erreur.get("texte", "").lower()
        type_err = erreur.get("type", "erreur")
        if erreur.get("critique"):
            resultats["critique"] += 1
        elif "exception" in texte:
            resultats["exception"] += 1
        elif "traceback" in texte:
            resultats["traceback"] += 1
        elif type_err == "warning":
            resultats["warning"] += 1
        elif "error" in texte or "erreur" in texte:
            resultats["erreur"] += 1
        else:
            resultats["autres"] += 1
    return resultats

def detecter_patterns_recurrents(erreurs, seuil=SEUIL_DEFAUT):
    if not erreurs:
        return []
    messages = []
    for erreur in erreurs:
        texte = erreur.get("texte", "")
        texte = RE_TIMESTAMP.sub("", texte)
        texte = RE_PID.sub("PID XXX", texte)
        texte = RE_HEX.sub("0xXXX", texte)
        texte = RE_IP.sub("IP", texte)
        texte = texte.strip()
        if texte:
            messages.append(texte)
    compteur = Counter(messages)
    return [{"message": msg, "frequence": nb} for msg, nb in compteur.most_common(20) if nb >= seuil]

def calculer_score_sante(analyse):
    types = analyse.get("types", {})
    nb_critiques = types.get("critique", 0)
    nb_exceptions = types.get("exception", 0)
    nb_warnings = types.get("warning", 0)
    score = 100
    score -= nb_critiques * 25
    score -= nb_exceptions * 10
    score -= types.get("traceback", 0) * 8
    score -= types.get("erreur", 0) * 3
    score -= nb_warnings * 1
    if analyse.get("nombre_erreurs", 0) > 50:
        score -= 15
    elif analyse.get("nombre_erreurs", 0) > 20:
        score -= 5
    return max(0, min(100, score))

def obtenir_niveau_sante(score):
    if score >= 90:
        return "🟢 Excellent"
    elif score >= 70:
        return "🟡 Bon"
    elif score >= 50:
        return "🟠 Moyen"
    elif score >= 25:
        return "🔴 Mauvais"
    else:
        return "💀 Critique"

def analyser_logs(depuis_heures=None, limite=LIMITE_DEFAUT, use_cache=True):
    key = (depuis_heures, limite)
    if use_cache and _cache["key"] == key and time.time() - _cache["t"] < 60:
        return _cache["val"]
    t0 = time.perf_counter()
    logs = lire_logs(limite=limite, depuis_heures=depuis_heures)
    erreurs = extraire_erreurs(logs)
    warnings = extraire_warnings(logs)
    toutes = erreurs + warnings
    types = compter_types_erreurs(toutes)
    patterns = detecter_patterns_recurrents(erreurs)
    analyse = {"date": datetime.now().isoformat(), "logs_lignes": len(logs.splitlines()) if logs else 0, "nombre_erreurs": len(erreurs), "nombre_warnings": len(warnings), "erreurs": [e["texte"] for e in erreurs[:50]], "erreurs_critiques": [e["texte"] for e in erreurs if e.get("critique")][:10], "types": types, "patterns_recurrents": patterns}
    analyse["score_sante"] = calculer_score_sante(analyse)
    analyse["niveau_sante"] = obtenir_niveau_sante(analyse["score_sante"])
    analyse["duree"] = round(time.perf_counter() - t0, 4)
    _cache.update(t=time.time(), key=key, val=analyse)
    return analyse

def obtenir_resume(depuis_heures=None):
    analyse = analyser_logs(depuis_heures=depuis_heures)
    lignes = [f"🩺 Santé JIBI : {analyse['niveau_sante']} ({analyse['score_sante']}/100) [{analyse.get('duree',0)}s]", f"   Erreurs : {analyse['nombre_erreurs']}", f"   Warnings : {analyse['nombre_warnings']}"]
    if analyse["erreurs_critiques"]:
        lignes.append(f"   🔴 Critiques : {len(analyse['erreurs_critiques'])}")
    if analyse["patterns_recurrents"]:
        lignes.append("   Patterns récurrents :")
        for p in analyse["patterns_recurrents"][:5]:
            lignes.append(f"     • [{p['frequence']}x] {p['message'][:80]}")
    return "\n".join(lignes)

def sauvegarder_analyse(analyse=None):
    if analyse is None:
        analyse = analyser_logs()
    HISTORIQUE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fichier = HISTORIQUE_DIR / f"analyse_{timestamp}.json"
    try:
        analyse_copy = {k: v for k, v in analyse.items() if k != "erreurs"}
        analyse_copy["nombre_erreurs_total"] = analyse.get("nombre_erreurs", 0)
        fichier.write_text(json.dumps(analyse_copy, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(fichier)
    except Exception:
        return None
