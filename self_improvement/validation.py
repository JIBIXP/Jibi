"""
Validation de sécurité — PATCHÉ v2
- Branché sur core/config.py (listes sensibles uniques)
- Regex compilées + timings
"""

import re
import time
from pathlib import Path

try:
    from core.config import FICHIERS_SENSIBLES as CFG_FICHIERS, DOSSIERS_SENSIBLES as CFG_DOSSIERS, JIBI_PROJET_DIR
    PROJECT_ROOT = JIBI_PROJET_DIR
    DOSSIERS_SENSIBLES = set(CFG_DOSSIERS) | {"self_improvement", "updater"}
    FICHIERS_SENSIBLES = set(CFG_FICHIERS) | {"database.py", "connaissances.py"}
except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DOSSIERS_SENSIBLES = {"core", "self_improvement", "updater", "modules"}
    FICHIERS_SENSIBLES = {"agent.py", "database.py", "connaissances.py", "memory_manager.py", "logging_jibi.py", "ecoute_process.py", ".env", "requirements.txt", "serveur_modeles.py"}

def est_fichier_sensible(fichier):
    chemin = Path(fichier)
    try:
        relatif = chemin.resolve().relative_to(PROJECT_ROOT.resolve())
    except (ValueError, OSError):
        relatif = chemin
    parties = relatif.parts
    for dossier in DOSSIERS_SENSIBLES:
        if dossier in parties:
            return True
    if len(parties) == 1 and parties[0] in FICHIERS_SENSIBLES:
        return True
    if ".env" in parties:
        return True
    return False

MOTIFS_BLOQUANTS = [
    (r"\beval\s*\(", "eval() — exécution de code arbitraire"),
    (r"\bexec\s*\(", "exec() — exécution de code arbitraire"),
    (r"os\.system\s*\(", "os.system() — exécution de commande shell"),
    (r"subprocess\.\w+\s*\([^)]*shell\s*=\s*True", "subprocess avec shell=True"),
    (r"__import__\s*\(", "__import__() dynamique"),
    (r"shutil\.rmtree\s*\(\s*['\"]/", "rmtree sur chemin absolu système"),
    (r"open\s*\(\s*['\"]/etc/", "Accès à /etc"),
    (r"open\s*\(\s*['\"]/proc/", "Accès à /proc"),
    (r"rm\s+-rf\s+/", "Suppression récursive de racine système"),
    (r"DROP\s+TABLE", "SQL destructif"),
    (r"DELETE\s+FROM\s+.*WHERE\s+1\s*=\s*1", "SQL : suppression totale"),
    (r"chmod\s+777", "chmod 777 — permissions dangereuses"),
    (r"curl\s+.*\|\s*(ba)?sh", "Piping curl vers shell"),
    (r"wget\s+.*\|\s*(ba)?sh", "Piping wget vers shell"),
    (r"base64\s+(-d|--decode)", "Décodage base64 (payload masqué)"),
]
MOTIFS_ATTENTION = [
    (r"os\.remove|os\.unlink|Path.*unlink", "Suppression de fichier"),
    (r"shutil\.move|shutil\.copy", "Déplacement/copie de fichier"),
    (r"subprocess\.(call|run|Popen)", "Exécution de sous-processus"),
    (r"open\s*\([^)]*['\"]w['\"]", "Ouverture fichier en écriture"),
    (r"INSERT\s+INTO|UPDATE\s+\w+|ALTER\s+TABLE", "Modification de base de données"),
    (r"import\s+os\b", "Import os (large surface d'attaque)"),
    (r"import\s+subprocess\b", "Import subprocess"),
    (r"requests\.(post|put|delete)", "Requête HTTP modifiante"),
    (r"pip\s+install|pip3\s+install", "Installation de package"),
    (r"sys\.path\.insert|sys\.path\.append", "Modification du path Python"),
]
RE_BLOQUANTS = [(re.compile(p, re.I), d) for p, d in MOTIFS_BLOQUANTS]
RE_ATTENTION = [(re.compile(p, re.I), d) for p, d in MOTIFS_ATTENTION]

def analyser_modification(fichier, solution):
    t0 = time.perf_counter()
    risques = []
    fichier_sensible = est_fichier_sensible(fichier)
    if fichier_sensible:
        risques.append(f"Fichier sensible : {fichier} (zone protégée, modification refusée)")
        return {"niveau": "bloqué", "action": "Fichier dans une zone protégée. Modification refusée.", "risques": risques, "fichier_sensible": True, "duree": round(time.perf_counter()-t0, 4)}
    texte = (solution or "")
    for rx, description in RE_BLOQUANTS:
        if rx.search(texte):
            risques.append(f"🔴 {description}")
    for rx, description in RE_ATTENTION:
        if rx.search(texte):
            risques.append(f"🟡 {description}")
    a_bloquant = any(r.startswith("🔴") for r in risques)
    a_attention = any(r.startswith("🟡") for r in risques)
    if a_bloquant:
        niveau, action = "bloqué", "Modification refusée : code dangereux détecté dans la solution. Reformule sans patterns critiques."
    elif a_attention:
        niveau, action = "attention", "Modification possible avec prudence : risques identifiés, relecture humaine renforcée requise."
    else:
        niveau, action = "sécurisé", "Aucun risque détecté. Préparation en laboratoire autorisée."
    return {"niveau": niveau, "action": action, "risques": risques, "fichier_sensible": False, "duree": round(time.perf_counter()-t0, 4)}

def formater_validation(validation):
    emoji = {"sécurisé": "✅", "attention": "⚠️", "bloqué": "🚫"}.get(validation.get("niveau", "?"), "❓")
    lignes = [f"{emoji} Validation : {validation.get('niveau', '?').upper()}", f"   Action : {validation.get('action', '?')}"]
    if validation.get("risques"):
        lignes.append("   Risques :")
        for risque in validation["risques"]:
            lignes.append(f"     {risque}")
    return "\n".join(lignes)
