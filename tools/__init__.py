"""
Modules outils de JIBI (v3).

Enregistre automatiquement les outils disponibles dans tool_registry.TOOLS_REGISTRY.
Chaque sous-module est optionnel : s'il manque ou plante à l'import, JIBI continue
sans ses outils et journalise l'erreur. Rien ici ne casse le démarrage.

Sous-modules :
  browser, files, pc_control, terminal, vision, documents   (de base)
  web_search                                                 (recherche internet)
  self_improvement_tools, updater_tools                      (optionnels)
  plugins/*.py                                               (outils créés par JIBI)
"""

import importlib

from .tool_registry import TOOLS_REGISTRY, register_tool

# ============================================================
# LOGGING (fallback si logging_jibi indisponible)
# ============================================================

try:
    from logging_jibi import log_event, log_warning
except Exception:  # pragma: no cover
    def log_event(cat, msg): print(f"[{cat}] {msg}")
    def log_warning(cat, msg): print(f"[{cat}] ⚠️ {msg}")


# ============================================================
# IMPORT SÉCURISÉ DES SOUS-MODULES
# ============================================================

MODULES = {}          # nom -> module importé
ERREURS_IMPORT = {}   # nom -> message d'erreur


def _importer(nom: str):
    """Importe tools.<nom> ; renvoie le module ou None (jamais d'exception)."""
    try:
        mod = importlib.import_module(f".{nom}", __name__)
        MODULES[nom] = mod
        return mod
    except Exception as e:
        ERREURS_IMPORT[nom] = f"{type(e).__name__}: {e}"
        log_warning("tools", f"Module '{nom}' indisponible → {ERREURS_IMPORT[nom]}")
        return None


browser = _importer("browser")
files = _importer("files")
pc_control = _importer("pc_control")
terminal = _importer("terminal")
vision = _importer("vision")
documents = _importer("documents")
web_search = _importer("web_search")
self_improvement_tools = _importer("self_improvement_tools")
updater_tools = _importer("updater_tools")

SELF_IMPROVEMENT_OK = self_improvement_tools is not None
UPDATER_TOOLS_OK = updater_tools is not None
WEB_SEARCH_OK = web_search is not None


def _reg(mod, nom_outil: str, nom_fonction: str, description: str, schema=None):
    """Enregistre un outil seulement si le module ET la fonction existent."""
    if mod is None:
        return
    fn = getattr(mod, nom_fonction, None)
    if fn is None:
        log_warning("tools", f"Fonction '{nom_fonction}' absente de {mod.__name__} → outil '{nom_outil}' ignoré")
        return
    if schema is None:
        register_tool(nom_outil, fn, description)
    else:
        register_tool(nom_outil, fn, description, schema)


def _schema(props: dict, required=None):
    return {"type": "object", "properties": props, "required": required or []}


S = {"type": "string"}
I = {"type": "integer"}
B = {"type": "boolean"}


# ============================================================
# NAVIGATEUR
# ============================================================

_reg(browser, "ouvrir_url", "ouvrir_url", "Ouvre une URL dans un navigateur.",
     _schema({"url": {"type": "string", "description": "URL http(s)"}}, ["url"]))
_reg(browser, "obtenir_texte_page", "obtenir_texte_page", "Renvoie le texte visible de la page.",
     _schema({"max_caracteres": I}))
_reg(browser, "cliquer", "cliquer", "Clique sur un élément CSS.", _schema({"selecteur": S}, ["selecteur"]))
_reg(browser, "remplir_champ", "remplir_champ", "Remplit un champ formulaire.",
     _schema({"selecteur": S, "texte": S}, ["selecteur", "texte"]))
_reg(browser, "fermer_navigateur", "fermer_navigateur", "Ferme le navigateur.")
_reg(browser, "obtenir_liens", "obtenir_liens", "Liste les liens de la page courante.")
_reg(browser, "capturer_ecran_page", "capturer_ecran_page", "Capture la page courante en PNG.",
     _schema({"nom_fichier": S}))


# ============================================================
# FICHIERS (tools/files.py)
# ============================================================

_reg(files, "creer_fichier", "creer_fichier", "Crée un fichier texte.",
     _schema({"chemin": S, "contenu": S}, ["chemin"]))
_reg(files, "lire_fichier", "lire_fichier", "Lit un fichier.", _schema({"chemin": S}, ["chemin"]))
_reg(files, "lister_fichiers", "lister_fichiers", "Liste les fichiers d'un dossier.", _schema({"sous_dossier": S}))
_reg(files, "supprimer_fichier", "supprimer_fichier", "Supprime un fichier du workspace (confirmation requise).",
     _schema({"chemin": S, "confirmer": B}, ["chemin"]))
_reg(files, "lire_code_source", "lire_code_source", "Lit un .py en lecture seule.", _schema({"chemin": S}, ["chemin"]))
_reg(files, "proposer_amelioration", "proposer_amelioration",
     "Écrit une proposition d'amélioration jamais appliquée auto.",
     _schema({"fichier_concerne": S, "description": S, "code_propose": S},
             ["fichier_concerne", "description", "code_propose"]))


# ============================================================
# CONTRÔLE PC (tools/pc_control.py)
# ============================================================

# --- Applications ---
_reg(pc_control, "ouvrir_application", "ouvrir_application",
     "Ouvre une application (navigateur, vscode, terminal...).", _schema({"nom": S}, ["nom"]))
_reg(pc_control, "fermer_application", "fermer_application",
     "Ferme une application (confirmer=True requis).", _schema({"nom": S, "confirmer": B}, ["nom", "confirmer"]))
_reg(pc_control, "application_est_lancee", "application_est_lancee",
     "Vérifie si une application tourne.", _schema({"nom": S}, ["nom"]))
_reg(pc_control, "obtenir_processus", "obtenir_processus",
     "Liste les processus actifs.", _schema({"recherche": S, "limite": I}))
_reg(pc_control, "informations_systeme", "informations_systeme", "Infos générales PC.", _schema({}))

# --- Fichiers & dossiers (système) ---
_reg(pc_control, "ouvrir_fichier", "ouvrir_fichier", "Ouvre un fichier avec l'appli par défaut.",
     _schema({"chemin": S}, ["chemin"]))
_reg(pc_control, "ouvrir_dossier", "ouvrir_dossier", "Ouvre un dossier dans l'explorateur.",
     _schema({"chemin": S}, ["chemin"]))
_reg(pc_control, "creer_dossier", "creer_dossier", "Crée un dossier (parents auto).", _schema({"chemin": S}, ["chemin"]))
_reg(pc_control, "rechercher_fichiers", "rechercher_fichiers", "Recherche fichiers par pattern (*.pdf).",
     _schema({"nom_pattern": S, "dossier_recherche": S, "limite": I}, ["nom_pattern"]))
_reg(pc_control, "renommer_fichier", "renommer_fichier", "Renomme un fichier/dossier.",
     _schema({"ancien_chemin": S, "nouveau_nom": S}, ["ancien_chemin", "nouveau_nom"]))
_reg(pc_control, "deplacer_fichier", "deplacer_fichier", "Déplace vers un dossier.",
     _schema({"source": S, "destination": S}, ["source", "destination"]))
_reg(pc_control, "copier_fichier", "copier_fichier", "Copie vers un dossier.",
     _schema({"source": S, "destination": S}, ["source", "destination"]))
# ⚠️ renommé : évite d'écraser files.supprimer_fichier (même nom avant)
_reg(pc_control, "supprimer_fichier_definitif", "supprimer_fichier",
     "Supprime définitivement un fichier système (confirmer=True).",
     _schema({"chemin": S, "confirmer": B}, ["chemin", "confirmer"]))

# --- Surveillance ---
_reg(pc_control, "obtenir_espace_disque", "obtenir_espace_disque", "Espace disque total/libre/utilisé.",
     _schema({"chemin": S}))
_reg(pc_control, "obtener_espace_disque", "obtenir_espace_disque", "(alias, ancienne orthographe)",
     _schema({"chemin": S}))
_reg(pc_control, "obtenir_infos_systeme_detaillees", "obtenir_infos_systeme_detaillees",
     "Détails CPU/RAM/disque/température.", _schema({}))
_reg(pc_control, "lister_applications_ouvertes", "lister_applications_ouvertes",
     "Liste applications ouvertes + mémoire.", _schema({"limite": I}))
_reg(pc_control, "surveiller_ressources", "surveiller_ressources",
     "Surveille CPU/RAM pendant N secondes.", _schema({"duree_secondes": I}))


# ============================================================
# TERMINAL
# ============================================================

_reg(terminal, "executer_commande", "executer_commande", "Exécute une commande shell whitelistée.",
     _schema({"commande": S, "confirmer": B}, ["commande"]))


# ============================================================
# VISION
# ============================================================

_reg(vision, "analyser_image", "analyser_image", "Décrit une image via modèle local.",
     _schema({"chemin": S, "question": S}, ["chemin"]))
_reg(vision, "capturer_ecran", "capturer_ecran", "Capture écran et sauvegarde.")
_reg(vision, "capturer_et_analyser", "capturer_et_analyser", "Capture puis analyse l'écran.")


# ============================================================
# DOCUMENTS
# ============================================================

_doc_schema = _schema({"chemin": S, "titre": S, "contenu": S}, ["chemin", "titre", "contenu"])
_reg(documents, "creer_document_word", "creer_document_word", "Crée un document Word (.docx).", _doc_schema)
_reg(documents, "creer_document_pdf", "creer_document_pdf", "Crée un document PDF.", _doc_schema)


# ============================================================
# RECHERCHE WEB (tools/web_search.py) — déclare son propre dict OUTILS
# ============================================================

if WEB_SEARCH_OK:
    for _nom, _spec in getattr(web_search, "OUTILS", {}).items():
        try:
            register_tool(_nom, _spec["fonction"], _spec.get("description", ""),
                          _spec.get("parametres", _schema({})))
        except Exception as _e:
            log_warning("tools", f"web_search.{_nom} non enregistré : {_e}")


# ============================================================
# AUTO-AMÉLIORATION (optionnel)
# ============================================================

if SELF_IMPROVEMENT_OK:
    _reg(self_improvement_tools, "analyser_sante_jibi", "analyser_sante_jibi",
         "Analyse santé JIBI : logs, erreurs, score 0-100.", _schema({"limite_logs": I, "depuis_heures": I}))
    _reg(self_improvement_tools, "tableau_bord_amelioration", "tableau_bord_amelioration",
         "Tableau de bord auto-amélioration.", _schema({}))
    _reg(self_improvement_tools, "preparer_amelioration", "preparer_amelioration",
         "Prépare amélioration (JAMAIS appliquée auto).",
         _schema({"fichier": S, "probleme": S, "solution": S, "justification": S, "priorite": S},
                 ["fichier", "probleme", "solution", "justification"]))


# ============================================================
# UPDATER (optionnel)
# ============================================================

if UPDATER_TOOLS_OK:
    _reg(updater_tools, "verifier_mise_a_jour", "verifier_mise_a_jour_tool",
         "Vérifie si une mise à jour GitHub est dispo.", _schema({}))
    _reg(updater_tools, "appliquer_mise_a_jour", "appliquer_mise_a_jour_tool",
         "Applique la dernière mise à jour (confirmation requise).", _schema({"confirmer": B}))
    _reg(updater_tools, "restaurer_derniere_sauvegarde", "restaurer_derniere_sauvegarde_tool",
         "Restaure depuis dernière sauvegarde (confirmer=True).", _schema({"confirmer": B}))
    _reg(updater_tools, "lister_sauvegardes", "lister_sauvegardes_tool", "Liste toutes les sauvegardes.")
    _reg(updater_tools, "obtenir_etat_global_jibi", "obtenir_etat_global_jibi_tool",
         "État global : version, modifs locaux, updates.")


# ============================================================
# PLUGINS CRÉÉS PAR JIBI (tools/plugins/*.py)
# ============================================================

PLUGINS_OK = False
PLUGINS_CHARGES = []
try:
    plugin_loader = importlib.import_module("tools.plugin_loader")
    _res = plugin_loader.charger_plugins()
    PLUGINS_OK = True
    PLUGINS_CHARGES = _res.get("charges", [])
    if PLUGINS_CHARGES:
        log_event("tools", f"Plugins : {', '.join(PLUGINS_CHARGES)}")
except Exception as _e:
    log_warning("tools", f"plugin_loader indisponible : {_e}")


# ============================================================
# EXPORT & RÉSUMÉ
# ============================================================

__all__ = [n for n in ("browser", "files", "pc_control", "terminal", "vision", "documents",
                       "web_search", "self_improvement_tools", "updater_tools") if n in MODULES]
__all__ += ["TOOLS_REGISTRY", "register_tool", "MODULES", "ERREURS_IMPORT", "etat_outils"]


def etat_outils() -> dict:
    """Résumé utile pour Status / diagnostic."""
    return {
        "nb_outils": len(TOOLS_REGISTRY),
        "modules_ok": sorted(MODULES),
        "modules_ko": dict(ERREURS_IMPORT),
        "plugins": PLUGINS_OK,
        "plugins_charges": PLUGINS_CHARGES,
    }


log_event(
    "tools",
    f"Outils chargés : {len(TOOLS_REGISTRY)} | modules OK : {len(MODULES)} | KO : {len(ERREURS_IMPORT)} "
    f"(self_imp: {'✓' if SELF_IMPROVEMENT_OK else '✗'}, updater: {'✓' if UPDATER_TOOLS_OK else '✗'}, "
    f"web: {'✓' if WEB_SEARCH_OK else '✗'}, plugins: {'✓' if PLUGINS_OK else '✗'})"
)