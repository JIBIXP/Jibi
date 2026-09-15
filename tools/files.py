"""
Gestion des fichiers — limitée à un dossier de travail dédié.

Sécurité :
- toute opération est confinée à JIBI_FILES_DIR (par défaut
  ./jibi_files) : impossible de sortir de ce dossier, même avec
  '../../etc/passwd' ou un chemin absolu ailleurs ;
- la suppression exige une confirmation explicite (confirmer=True) ;
- lecture du code source limitée aux fichiers .py uniquement (pas de .env) ;
- aucune modification directe du code source possible ;
- propositions d'amélioration toujours dans un fichier séparé.

Architecture :
- JIBI_FILES_DIR : espace de travail confiné pour fichiers utilisateur
- JIBI_PROJET_DIR : racine du projet (lecture seule code source)
- WORKSPACE_DIR : espace auto-amélioration (isolé)
"""

import os
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)


# ============================================================
# CONFIGURATION
# ============================================================

# Dossier de travail pour fichiers utilisateur
DOSSIER_TRAVAIL = os.path.abspath(
    os.getenv("JIBI_FILES_DIR", "./jibi_files")
)

# Répertoire racine du projet JIBI
PROJET_DIR = os.path.abspath(
    os.getenv("JIBI_PROJET_DIR", ".")
)

# Workspace pour auto-amélioration
WORKSPACE_DIR = Path(PROJET_DIR) / "workspace"

# Extensions autorisées pour lecture code source
EXTENSIONS_CODE_AUTORISEES = {".py"}

# Dossiers exclus de l'exploration du code source
DOSSIERS_EXCLUS = {
    "__pycache__",
    ".git",
    ".vscode",
    "logs",
    "venv",
    "env",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    os.path.basename(DOSSIER_TRAVAIL),  # Jamais son propre espace d'écriture
}

# Fichiers sensibles (jamais lus ni modifiés)
FICHIERS_INTERDITS = {
    ".env",
    ".env.local",
    ".env.production",
    "secrets.json",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}

# Taille maximale de lecture par défaut (évite saturation mémoire)
MAX_TAILLE_LECTURE = 10 * 1024 * 1024  # 10 MB


# ============================================================
# INITIALISATION
# ============================================================

os.makedirs(DOSSIER_TRAVAIL, exist_ok=True)
os.makedirs(WORKSPACE_DIR / "propositions", exist_ok=True)


# ============================================================
# VALIDATION DES CHEMINS
# ============================================================

def _resoudre_chemin(chemin):
    """
    Résout `chemin` par rapport au dossier de travail et vérifie qu'il
    n'en sort pas (protection contre '../' et les chemins absolus).
    
    Args:
        chemin: Chemin relatif à résoudre
        
    Returns:
        str: Chemin absolu sécurisé
        
    Raises:
        PermissionError: Si le chemin tente de sortir du dossier autorisé
    """
    chemin_complet = os.path.abspath(
        os.path.join(DOSSIER_TRAVAIL, chemin)
    )

    if os.path.commonpath(
        [chemin_complet, DOSSIER_TRAVAIL]
    ) != DOSSIER_TRAVAIL:

        raise PermissionError(
            f"Chemin refusé : '{chemin}' sort du dossier de travail "
            f"autorisé ({DOSSIER_TRAVAIL})."
        )

    return chemin_complet


def _resoudre_chemin_code(chemin):
    """
    Résout un chemin de code source avec validations strictes.
    
    Args:
        chemin: Chemin relatif du fichier .py
        
    Returns:
        str: Chemin absolu sécurisé
        
    Raises:
        PermissionError: Si le chemin est interdit
        ValueError: Si l'extension n'est pas .py
    """
    chemin_complet = os.path.abspath(
        os.path.join(PROJET_DIR, chemin)
    )

    # Vérifier qu'on reste dans PROJET_DIR
    if os.path.commonpath(
        [chemin_complet, PROJET_DIR]
    ) != PROJET_DIR:

        raise PermissionError(
            f"Chemin refusé : '{chemin}' sort du dossier du projet."
        )

    # Vérifier l'extension
    extension = os.path.splitext(chemin_complet)[1].lower()

    if extension not in EXTENSIONS_CODE_AUTORISEES:
        raise PermissionError(
            f"Lecture refusée : seuls les fichiers .py sont "
            f"accessibles (demandé : '{extension or '(sans extension)'}')."
        )

    # Vérifier que ce n'est pas un fichier interdit
    nom_fichier = os.path.basename(chemin_complet)
    
    if nom_fichier in FICHIERS_INTERDITS or nom_fichier.startswith('.env'):
        raise PermissionError(
            f"Lecture refusée : '{nom_fichier}' est un fichier sensible."
        )

    return chemin_complet


def _valider_taille_fichier(chemin_complet, max_taille=MAX_TAILLE_LECTURE):
    """
    Vérifie que la taille du fichier est acceptable.
    
    Args:
        chemin_complet: Chemin absolu du fichier
        max_taille: Taille maximale en octets
        
    Raises:
        ValueError: Si le fichier est trop volumineux
    """
    if os.path.isfile(chemin_complet):
        taille = os.path.getsize(chemin_complet)
        
        if taille > max_taille:
            raise ValueError(
                f"Fichier trop volumineux : {taille / 1024 / 1024:.1f} MB "
                f"(max : {max_taille / 1024 / 1024:.1f} MB)"
            )


# ============================================================
# OPÉRATIONS FICHIERS (dossier de travail)
# ============================================================

def creer_fichier(chemin, contenu=""):
    """
    Crée un fichier dans le dossier de travail.
    
    Args:
        chemin: Chemin relatif du fichier à créer
        contenu: Contenu du fichier (défaut vide)
        
    Returns:
        str: Message de confirmation
        
    Raises:
        PermissionError: Si le chemin est invalide
        OSError: Si la création échoue
    """
    chemin_complet = _resoudre_chemin(chemin)

    try:
        # Créer les dossiers parents si nécessaire
        os.makedirs(
            os.path.dirname(chemin_complet),
            exist_ok=True
        )

        with open(chemin_complet, "w", encoding="utf-8") as f:
            f.write(contenu)

        log_event("files", f"Fichier créé : {chemin}")

        return f"✓ Fichier '{chemin}' créé ({len(contenu)} caractères)"

    except Exception as e:
        log_error("files", f"creer_fichier échoué : {e}", exc_info=False)
        raise


def lire_fichier(chemin, max_caracteres=5000):
    """
    Lit un fichier du dossier de travail.
    
    Args:
        chemin: Chemin relatif du fichier à lire
        max_caracteres: Nombre maximum de caractères à lire
        
    Returns:
        str: Contenu du fichier (tronqué si nécessaire)
        
    Raises:
        FileNotFoundError: Si le fichier n'existe pas
        PermissionError: Si le chemin est invalide
    """
    chemin_complet = _resoudre_chemin(chemin)

    if not os.path.isfile(chemin_complet):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    _valider_taille_fichier(chemin_complet)

    try:
        with open(chemin_complet, "r", encoding="utf-8", errors="replace") as f:
            contenu = f.read(max_caracteres)

        log_event("files", f"Fichier lu : {chemin}")

        if os.path.getsize(chemin_complet) > max_caracteres:
            contenu += f"\n\n... (tronqué à {max_caracteres} caractères)"

        return contenu

    except Exception as e:
        log_error("files", f"lire_fichier échoué : {e}", exc_info=False)
        raise


def lister_fichiers(sous_dossier=""):
    """
    Liste les fichiers d'un sous-dossier du dossier de travail.
    
    Args:
        sous_dossier: Sous-dossier à lister (vide = racine)
        
    Returns:
        list: Liste des noms de fichiers/dossiers
        
    Raises:
        NotADirectoryError: Si le chemin n'est pas un dossier
    """
    chemin_complet = _resoudre_chemin(sous_dossier)

    if not os.path.isdir(chemin_complet):
        raise NotADirectoryError(f"Dossier introuvable : {sous_dossier}")

    try:
        elements = []
        
        for element in sorted(os.listdir(chemin_complet)):
            chemin_element = os.path.join(chemin_complet, element)
            
            if os.path.isdir(chemin_element):
                elements.append(f"📁 {element}/")
            else:
                taille = os.path.getsize(chemin_element)
                elements.append(f"📄 {element} ({taille} octets)")
        
        return elements

    except Exception as e:
        log_error("files", f"lister_fichiers échoué : {e}", exc_info=False)
        raise


def supprimer_fichier(chemin, confirmer=False):
    """
    Supprime un fichier du dossier de travail (confirmation requise).
    
    Args:
        chemin: Chemin relatif du fichier à supprimer
        confirmer: Doit être True pour confirmer la suppression
        
    Returns:
        str: Message de confirmation
        
    Raises:
        PermissionError: Si confirmer=False
        FileNotFoundError: Si le fichier n'existe pas
    """
    if not confirmer:
        raise PermissionError(
            "Suppression refusée sans confirmation explicite "
            "(confirmer=True)."
        )

    chemin_complet = _resoudre_chemin(chemin)

    if not os.path.isfile(chemin_complet):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    try:
        os.remove(chemin_complet)

        log_event("files", f"Fichier supprimé : {chemin}")

        return f"✓ Fichier '{chemin}' supprimé"

    except Exception as e:
        log_error("files", f"supprimer_fichier échoué : {e}", exc_info=False)
        raise


def obtenir_infos_fichier(chemin):
    """
    Obtient les informations d'un fichier.
    
    Args:
        chemin: Chemin relatif du fichier
        
    Returns:
        dict: Informations sur le fichier
    """
    chemin_complet = _resoudre_chemin(chemin)

    if not os.path.isfile(chemin_complet):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    try:
        stats = os.stat(chemin_complet)
        
        return {
            "nom": os.path.basename(chemin),
            "taille": stats.st_size,
            "taille_lisible": f"{stats.st_size / 1024:.1f} KB",
            "date_creation": datetime.fromtimestamp(stats.st_ctime).isoformat(),
            "date_modification": datetime.fromtimestamp(stats.st_mtime).isoformat(),
            "extension": os.path.splitext(chemin)[1],
        }

    except Exception as e:
        log_error("files", f"obtenir_infos_fichier échoué : {e}", exc_info=False)
        raise


# ============================================================
# LECTURE SEULE DU CODE SOURCE DE JIBI
# ============================================================

def lire_code_source(chemin, max_caracteres=8000):
    """
    Lit un fichier .py du projet, en LECTURE SEULE.
    
    SÉCURITÉ :
    - Extension .py UNIQUEMENT (exclut .env automatiquement)
    - Confiné à PROJET_DIR
    - Aucune écriture possible
    
    Args:
        chemin: Chemin relatif du fichier .py (ex: 'agent.py')
        max_caracteres: Nombre max de caractères à lire
        
    Returns:
        str: Contenu du fichier (tronqué si nécessaire)
        
    Raises:
        PermissionError: Si le fichier n'est pas autorisé
        FileNotFoundError: Si le fichier n'existe pas
    """
    chemin_complet = _resoudre_chemin_code(chemin)

    if not os.path.isfile(chemin_complet):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    _valider_taille_fichier(chemin_complet)

    try:
        with open(chemin_complet, "r", encoding="utf-8", errors="replace") as f:
            contenu = f.read(max_caracteres)

        log_event("files", f"Code source lu (lecture seule) : {chemin}")

        if os.path.getsize(chemin_complet) > max_caracteres:
            nb_lignes = contenu.count('\n')
            contenu += f"\n\n... (tronqué à {max_caracteres} caractères, ~{nb_lignes} lignes)"

        return contenu

    except Exception as e:
        log_error("files", f"lire_code_source échoué : {e}", exc_info=False)
        raise


def lister_code_source():
    """
    Liste tous les fichiers .py du projet (hors dossiers exclus).
    
    Returns:
        list: Liste des chemins relatifs des fichiers .py
    """
    resultats = []

    try:
        for racine, dossiers, fichiers in os.walk(PROJET_DIR):

            # Filtrer les dossiers exclus
            dossiers[:] = [
                d for d in dossiers
                if d not in DOSSIERS_EXCLUS and not d.startswith(".")
            ]

            for nom in fichiers:
                if nom.endswith(".py") and nom not in FICHIERS_INTERDITS:
                    chemin_relatif = os.path.relpath(
                        os.path.join(racine, nom),
                        PROJET_DIR
                    )
                    # Normaliser les séparateurs (Windows → Unix)
                    resultats.append(chemin_relatif.replace("\\", "/"))

        log_event("files", f"Code source listé : {len(resultats)} fichiers .py")

        return sorted(resultats)

    except Exception as e:
        log_error("files", f"lister_code_source échoué : {e}", exc_info=False)
        raise


def analyser_structure_code():
    """
    Analyse la structure du code source de JIBI.
    
    Returns:
        dict: Structure du projet par catégories
    """
    try:
        fichiers = lister_code_source()
        
        structure = {
            "core": [],
            "tools": [],
            "modules": [],
            "self_improvement": [],
            "updater": [],
            "racine": [],
            "autres": []
        }
        
        for fichier in fichiers:
            if fichier.startswith("core/"):
                structure["core"].append(fichier)
            elif fichier.startswith("tools/"):
                structure["tools"].append(fichier)
            elif fichier.startswith("modules/"):
                structure["modules"].append(fichier)
            elif fichier.startswith("self_improvement/"):
                structure["self_improvement"].append(fichier)
            elif fichier.startswith("updater/"):
                structure["updater"].append(fichier)
            elif "/" not in fichier:
                structure["racine"].append(fichier)
            else:
                structure["autres"].append(fichier)
        
        return structure

    except Exception as e:
        log_error("files", f"analyser_structure_code échoué : {e}", exc_info=False)
        raise


# ============================================================
# PROPOSITIONS D'AMÉLIORATION
# ============================================================

def proposer_amelioration(fichier_concerne, description, code_propose):
    """
    Écrit une PROPOSITION de changement dans le dossier de travail
    confiné — jamais dans le vrai fichier. C'est à l'humain de relire
    et d'appliquer manuellement s'il est d'accord.
    
    IMPORTANT :
    - Cette fonction NE modifie JAMAIS le code source directement
    - La proposition est écrite dans workspace/propositions/
    - Toujours nécessite validation humaine
    
    Args:
        fichier_concerne: Nom du fichier visé (ex: 'agent.py')
        description: Explication de l'amélioration proposée
        code_propose: Extrait de code proposé
        
    Returns:
        str: Message de confirmation avec chemin de la proposition
    """
    try:
        horodatage = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        nom_base = os.path.basename(fichier_concerne).replace(".py", "")

        # Utiliser workspace au lieu de jibi_files pour les propositions
        propositions_dir = WORKSPACE_DIR / "propositions"
        propositions_dir.mkdir(parents=True, exist_ok=True)
        
        nom_fichier = f"{horodatage}_{nom_base}.md"
        chemin_complet = propositions_dir / nom_fichier

        contenu = (
            f"# Proposition d'amélioration pour {fichier_concerne}\n\n"
            f"**Date (UTC)** : {horodatage}\n\n"
            f"---\n\n"
            f"## 📋 Description\n\n{description}\n\n"
            f"## 💡 Code proposé\n\n```python\n{code_propose}\n```\n\n"
            f"---\n\n"
            f"⚠️ **IMPORTANT** : Cette proposition n'a PAS été appliquée automatiquement.\n\n"
            f"Pour appliquer cette amélioration :\n\n"
            f"1. Relis attentivement le code proposé\n"
            f"2. Vérifie qu'il est pertinent et sûr\n"
            f"3. Applique manuellement les changements dans `{fichier_concerne}`\n"
            f"4. Teste que JIBI fonctionne correctement\n\n"
            f"---\n\n"
            f"*Proposition générée automatiquement par le système d'auto-amélioration de JIBI.*\n"
        )

        with open(chemin_complet, "w", encoding="utf-8") as f:
            f.write(contenu)

        log_event(
            "files",
            f"Proposition créée : {nom_fichier} pour {fichier_concerne}"
        )

        return (
            f"✓ Proposition créée : {chemin_complet}\n\n"
            f"⚠️ Cette proposition n'a PAS été appliquée automatiquement.\n"
            f"Relis le fichier puis applique manuellement si pertinent."
        )

    except Exception as e:
        log_error("files", f"proposer_amelioration échoué : {e}", exc_info=False)
        raise


def lister_propositions():
    """
    Liste toutes les propositions d'amélioration existantes.
    
    Returns:
        list: Liste des propositions avec métadonnées
    """
    try:
        propositions_dir = WORKSPACE_DIR / "propositions"
        
        if not propositions_dir.exists():
            return []
        
        propositions = []
        
        for fichier in sorted(propositions_dir.glob("*.md"), reverse=True):
            stats = fichier.stat()
            
            propositions.append({
                "nom": fichier.name,
                "chemin": str(fichier),
                "date": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                "taille": stats.st_size
            })
        
        return propositions

    except Exception as e:
        log_error("files", f"lister_propositions échoué : {e}", exc_info=False)
        raise


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    'creer_fichier',
    'lire_fichier',
    'lister_fichiers',
    'supprimer_fichier',
    'obtenir_infos_fichier',
    'lire_code_source',
    'lister_code_source',
    'analyser_structure_code',
    'proposer_amelioration',
    'lister_propositions',
]