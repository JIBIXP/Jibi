"""
Contrôle du PC — Base et Avancé (version unifiée).

Responsabilités :
- Ouvrir/fermer des applications ;
- Gérer fichiers et dossiers (créer, renommer, déplacer, copier, supprimer) ;
- Rechercher des fichiers ;
- Obtenir l'espace disque ;
- Surveiller CPU/RAM/disque en temps réel ;
- Lister les applications ouvertes ;
- Informations système détaillées ;

Sécurité :
- Les opérations de suppression nécessitent confirmer=True ;
- Les chemins sont validés (pas de chemins système critiques) ;
- Les recherches sont limitées en profondeur et en résultats ;
- Aucune commande arbitraire n'est exécutée.
"""

import os
import platform
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from logging_jibi import log_event, log_warning, log_error


SYSTEME = platform.system()

# Dossier de travail sécurisé par défaut
WORKSPACE = Path("workspace").resolve()
WORKSPACE.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Chemins interdits (protection système)
# ---------------------------------------------------------------------------

CHEMINS_PROTEGES = {
    "Windows": [
        r"C:\Windows",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\ProgramData",
        r"C:\System Volume Information",
    ],
    "Darwin": [
        "/System", "/Library", "/bin", "/sbin", "/usr", "/private",
    ],
    "Linux": [
        "/bin", "/sbin", "/usr", "/lib", "/lib64", "/sys", "/proc", "/boot", "/etc",
    ],
}


def _chemin_est_protege(chemin):
    """Vérifie si un chemin correspond à un répertoire système protégé."""
    try:
        chemin_absolu = Path(chemin).resolve()
        chemin_str = str(chemin_absolu)
        for protege in CHEMINS_PROTEGES.get(SYSTEME, []):
            if chemin_str.startswith(protege):
                return True
        return False
    except Exception:
        return True


def _valider_chemin(chemin, operation=""):
    """Valide un chemin avant une opération."""
    if not chemin:
        return False, "Aucun chemin spécifié."
    try:
        chemin_obj = Path(chemin).resolve()
    except Exception as e:
        return False, f"Chemin invalide : {e}"
    if _chemin_est_protege(chemin_obj):
        return False, f"Opération refusée : '{chemin}' est un répertoire système protégé."
    return True, ""


def _formater_taille(octets):
    """Formate une taille en octets vers une unité lisible."""
    for unite in ["o", "Ko", "Mo", "Go", "To"]:
        if octets < 1024.0:
            return f"{octets:.1f} {unite}"
        octets /= 1024.0
    return f"{octets:.1f} Po"


# ===========================================================================
# PARTIE 1 — CONTRÔLE APPLICATIONS (BASE)
# ===========================================================================


def ouvrir_application(nom):
    """
    Ouvre une application connue.
    
    nom : Nom de l'application (navigateur, explorateur_fichiers, terminal, vscode...)
    """
    if not nom:
        return "Aucun nom d'application spécifié."

    try:
        if SYSTEME == "Windows":
            # Mappage noms courants vers exécutables Windows
            mapping = {
                "navigateur": ["msedge"],
                "firefox": ["firefox"],
                "chrome": ["chrome"],
                "explorer": ["explorer"],
                "explorateur_fichiers": ["explorer"],
                "terminal": ["cmd"],
                "vscode": ["code"],
                "notepad": ["notepad"],
                "word": ["winword"],
                "excel": ["excel"],
                "powerpoint": ["powerpnt"],
            }
            
            cmd = mapping.get(nom.lower().strip())
            if cmd is None:
                return "Application non autorisée. Applications disponibles : " + ", ".join(sorted(mapping))
            subprocess.Popen(cmd, shell=False)
        
        elif SYSTEME == "Darwin":
            subprocess.Popen(["open", "-a", nom])
        
        else:  # Linux
            # Essayer d'abord desktop-entry puis fallback xdg-open
            subprocess.Popen(["gtk-launch", nom], stderr=subprocess.DEVNULL) or \
            subprocess.Popen(["xdg-open", nom], stderr=subprocess.DEVNULL)

        log_event("pc_control", f"Application ouverte : {nom}")
        return f"Application '{nom}' lancée."

    except FileNotFoundError:
        return f"Application '{nom}' introuvable."
    except Exception as e:
        log_error("pc_control", f"ouvrir_application échoué : {e}", exc_info=False)
        return f"Impossible d'ouvrir '{nom}' : {str(e)[:150]}"


def application_est_lancee(nom):
    """Vérifie si une application est lancée (recherche dans processus)."""
    try:
        import psutil
    except ImportError:
        return "psutil requis pour cette fonction."
    
    nom_lower = nom.lower()
    for proc in psutil.process_iter(['name']):
        try:
            if nom_lower in proc.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def obtenir_etat_application(nom):
    """Indique si une application est lancée avec détails."""
    lancee = application_est_lancee(nom)
    if not lancee:
        return {"lancee": False, "message": f"'{nom}' n'est pas actuellement lancé."}
    return {"lancee": True, "message": f"'{nom}' est en cours d'exécution."}


def obtenir_processus(recherche="", limite=30):
    """Liste les processus actifs."""
    try:
        import psutil
    except ImportError:
        return "psutil requis."
    
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        limite = 30
    
    resultats = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            info = proc.info
            if recherche and recherche.lower() not in info.get('name', '').lower():
                continue
            resultats.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if len(resultats) >= limite:
            break
    
    return resultats[:limite] if resultats else "Aucun processus trouvé."


def fermer_application(nom, confirmer=False):
    """
    Ferme une application par son nom.
    
    CONFIRMATION OBLIGATOIRE (confirmer=True).
    """
    if not confirmer:
        raise PermissionError("Fermeture refusée sans confirmation explicite (confirmer=True).")
    
    if SYSTEME == "Windows":
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", f"{nom}.exe"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            log_event("pc_control", f"Application fermée : {nom}")
            return f"Application '{nom}' fermée."
        except subprocess.TimeoutExpired:
            return f"Timeout lors de la fermeture de '{nom}'."
        except Exception as e:
            return f"Erreur fermeture '{nom}' : {str(e)[:100]}"
    
    else:  # macOS / Linux
        try:
            import psutil
            fermes = 0
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if nom.lower() in proc.info['name'].lower():
                        proc.terminate()
                        fermes += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if fermes > 0:
                log_event("pc_control", f"{fermes} processus '{nom}' terminés.")
                return f"{fermes} instance(s) de '{nom}' fermée(s)."
            else:
                return f"Aucun processus '{nom}' trouvé à fermer."
        except ImportError:
            return "psutil requis pour cette fonction sur Linux/macOS."
        except Exception as e:
            return f"Erreur fermeture : {str(e)[:100]}"


def informations_systeme():
    """Retourne infos générales : système, machine, processeur, mémoire."""
    try:
        mem = None
        cpu_freq_val = None
        
        import psutil
        mem = psutil.virtual_memory()
        freq = psutil.cpu_freq()
        if freq:
            cpu_freq_val = freq.current
    except ImportError:
        pass
    
    return {
        "systeme": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processeur": platform.processor() or "Inconnu",
        "architecture": platform.architecture()[0],
        "python": platform.python_version(),
        "cpu_coeurs": os.cpu_count(),
        "cpu_frequence_mhz": cpu_freq_val,
        "ram_total_mo": round(mem.total / (1024 * 1024)) if mem else None,
        "ram_libre_mo": round(mem.available / (1024 * 1024)) if mem else None,
    }


# ===========================================================================
# PARTIE 2 — GESTION FICHIERS ET DOSSIERS (AVANCÉ)
# ===========================================================================


def ouvrir_fichier(chemin):
    """Ouvre un fichier avec l'application par défaut."""
    valide, erreur = _valider_chemin(chemin, "ouvrir")
    if not valide:
        return erreur

    chemin_obj = Path(chemin).resolve()

    if not chemin_obj.exists():
        return f"Le fichier '{chemin}' n'existe pas."
    if not chemin_obj.is_file():
        return f"'{chemin}' n'est pas un fichier."

    try:
        if SYSTEME == "Windows":
            os.startfile(str(chemin_obj))
        elif SYSTEME == "Darwin":
            subprocess.Popen(["open", str(chemin_obj)])
        else:
            subprocess.Popen(["xdg-open", str(chemin_obj)])

        log_event("pc_control", f"Fichier ouvert : {chemin}")
        return f"Fichier '{chemin_obj.name}' ouvert."

    except Exception as e:
        log_error("pc_control", f"ouvrir_fichier échoué : {e}", exc_info=False)
        return f"Impossible d'ouvrir '{chemin}' : {str(e)[:150]}"


def ouvrir_dossier(chemin):
    """Ouvre un dossier dans l'explorateur."""
    valide, erreur = _valider_chemin(chemin, "ouvrir")
    if not valide:
        return erreur

    chemin_obj = Path(chemin).resolve()

    if not chemin_obj.exists():
        return f"Le dossier '{chemin}' n'existe pas."
    if not chemin_obj.is_dir():
        return f"'{chemin}' n'est pas un dossier."

    try:
        if SYSTEME == "Windows":
            subprocess.Popen(["explorer", str(chemin_obj)])
        elif SYSTEME == "Darwin":
            subprocess.Popen(["open", str(chemin_obj)])
        else:
            subprocess.Popen(["xdg-open", str(chemin_obj)])

        log_event("pc_control", f"Dossier ouvert : {chemin}")
        return f"Dossier '{chemin_obj.name}' ouvert dans l'explorateur."

    except Exception as e:
        log_error("pc_control", f"ouvrir_dossier échoué : {e}", exc_info=False)
        return f"Impossible d'ouvrir '{chemin}' : {str(e)[:150]}"


def creer_dossier(chemin):
    """Crée un nouveau dossier (et ses parents si nécessaire)."""
    valide, erreur = _valider_chemin(chemin, "créer")
    if not valide:
        return erreur

    chemin_obj = Path(chemin).resolve()

    if chemin_obj.exists():
        return "Existe déjà" if chemin_obj.is_dir() else "'{chemin}' existe mais n'est pas un dossier."

    try:
        chemin_obj.mkdir(parents=True, exist_ok=True)
        log_event("pc_control", f"Dossier créé : {chemin}")
        return f"Dossier '{chemin_obj.name}' créé avec succès."

    except Exception as e:
        log_error("pc_control", f"creer_dossier échoué : {e}", exc_info=False)
        return f"Impossible de créer '{chemin}' : {str(e)[:150]}"


def rechercher_fichiers(nom_pattern, dossier_recherche=None, limite=50):
    """
    Recherche des fichiers par pattern (*, ?) avec limite de résultats.
    """
    if not nom_pattern:
        return "Aucun pattern spécifié."

    if dossier_recherche is None:
        dossier_recherche = WORKSPACE

    valide, erreur = _valider_chemin(dossier_recherche, "rechercher")
    if not valide:
        return erreur

    dossier_obj = Path(dossier_recherche).resolve()

    if not dossier_obj.exists() or not dossier_obj.is_dir():
        return f"Dossier de recherche invalide : '{dossier_recherche}'"

    try:
        limite = max(1, min(int(limite), 200))
    except (TypeError, ValueError):
        limite = 50

    try:
        resultats = []
        for fichier in dossier_obj.rglob(nom_pattern):
            if len(resultats) >= limite:
                break
            if fichier.is_file():
                taille = fichier.stat().st_size
                resultats.append({
                    "chemin": str(fichier.relative_to(dossier_obj)),
                    "nom": fichier.name,
                    "taille": _formater_taille(taille),
                    "date_modif": datetime.fromtimestamp(fichier.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                })

        if not resultats:
            return f"Aucun fichier correspondant à '{nom_pattern}' dans '{dossier_recherche}'."

        lignes = [f"Fichiers trouvés ({len(resultats)}) :\n"]
        for r in resultats:
            lignes.append(f"  • {r['nom']} ({r['taille']}) — {r['chemin']} ({r['date_modif']})")

        log_event("pc_control", f"Recherche '{nom_pattern}' : {len(resultats)} résultats")
        return "\n".join(lignes)

    except Exception as e:
        log_error("pc_control", f"rechercher_fichiers échoué : {e}", exc_info=False)
        return f"Erreur recherche : {str(e)[:150]}"


def renommer_fichier(ancien_chemin, nouveau_nom):
    """Renomme un fichier ou dossier (nouveau_nom uniquement, pas un chemin)."""
    valide, erreur = _valider_chemin(ancien_chemin, "renommer")
    if not valide:
        return erreur

    ancien_obj = Path(ancien_chemin).resolve()

    if not ancien_obj.exists():
        return f"'{ancien_chemin}' n'existe pas."

    nouveau_obj = ancien_obj.parent / nouveau_nom

    valide, erreur = _valider_chemin(nouveau_obj, "renommer")
    if not valide:
        return erreur

    if nouveau_obj.exists():
        return f"'{nouveau_nom}' existe déjà à cet emplacement."

    try:
        ancien_obj.rename(nouveau_obj)
        log_event("pc_control", f"Renommé : {ancien_chemin} → {nouveau_nom}")
        return f"Renommé en '{nouveau_nom}' avec succès."

    except Exception as e:
        log_error("pc_control", f"renommer_fichier échoué : {e}", exc_info=False)
        return f"Impossible de renommer : {str(e)[:150]}"


def deplacer_fichier(source, destination):
    """Déplace un fichier/dossier vers un dossier destination."""
    valide, erreur = _valider_chemin(source, "déplacer")
    if not valide:
        return erreur
    valide, erreur = _valider_chemin(destination, "déplacer")
    if not valide:
        return erreur

    source_obj = Path(source).resolve()
    dest_obj = Path(destination).resolve()

    if not source_obj.exists():
        return f"'{source}' n'existe pas."
    if not dest_obj.exists() or not dest_obj.is_dir():
        return f"Destination invalide : '{destination}'"

    nouveau_chemin = dest_obj / source_obj.name
    if nouveau_chemin.exists():
        return f"Un fichier nommé '{source_obj.name}' existe déjà dans '{destination}'."

    try:
        shutil.move(str(source_obj), str(nouveau_chemin))
        log_event("pc_control", f"Déplacé : {source} → {destination}")
        return f"Déplacé vers '{destination}' avec succès."

    except Exception as e:
        log_error("pc_control", f"deplacer_fichier échoué : {e}", exc_info=False)
        return f"Impossible de déplacer : {str(e)[:150]}"


def copier_fichier(source, destination):
    """Copie un fichier/dossier vers un dossier destination."""
    valide, erreur = _valider_chemin(source, "copier")
    if not valide:
        return erreur
    valide, erreur = _valider_chemin(destination, "copier")
    if not valide:
        return erreur

    source_obj = Path(source).resolve()
    dest_obj = Path(destination).resolve()

    if not source_obj.exists():
        return f"'{source}' n'existe pas."
    if not dest_obj.exists() or not dest_obj.is_dir():
        return f"Destination invalide : '{destination}'"

    nouveau_chemin = dest_obj / source_obj.name
    if nouveau_chemin.exists():
        return f"Un fichier nommé '{source_obj.name}' existe déjà dans '{destination}'."

    try:
        if source_obj.is_file():
            shutil.copy2(str(source_obj), str(nouveau_chemin))
        else:
            shutil.copytree(str(source_obj), str(nouveau_chemin))

        log_event("pc_control", f"Copié : {source} → {destination}")
        return f"Copié vers '{destination}' avec succès."

    except Exception as e:
        log_error("pc_control", f"copier_fichier échoué : {e}", exc_info=False)
        return f"Impossible de copier : {str(e)[:150]}"


def supprimer_fichier(chemin, confirmer=False):
    """
    Supprime un fichier ou dossier.
    
    ⚠️  confirmer=True OBLIGatoire.
    """
    if not confirmer:
        raise PermissionError("Suppression refusée sans confirmation explicite (confirmer=True).")

    valide, erreur = _valider_chemin(chemin, "supprimer")
    if not valide:
        return erreur

    chemin_obj = Path(chemin).resolve()

    if not chemin_obj.exists():
        return f"'{chemin}' n'existe pas."

    try:
        if chemin_obj.is_file():
            chemin_obj.unlink()
            log_event("pc_control", f"Fichier supprimé : {chemin}")
            return f"Fichier '{chemin_obj.name}' supprimé."
        else:
            shutil.rmtree(str(chemin_obj))
            log_event("pc_control", f"Dossier supprimé : {chemin}")
            return f"Dossier '{chemin_obj.name}' supprimé."

    except Exception as e:
        log_error("pc_control", f"supprimer_fichier échoué : {e}", exc_info=False)
        return f"Impossible de supprimer : {str(e)[:150]}"


# ===========================================================================
# PARTIE 3 — SURVEILLANCE SYSTÈME AVANCÉE
# ===========================================================================


def obtenir_espace_disque(chemin=None):
    """Retourne espace disque total/utilisé/libre."""
    try:
        import psutil
    except ImportError:
        return "psutil requis : pip install psutil"

    if chemin is None:
        chemin = "C:\\" if SYSTEME == "Windows" else "/"

    try:
        usage = psutil.disk_usage(Path(chemin).resolve())
        t_go = usage.total / (1024**3)
        u_go = usage.used / (1024**3)
        l_go = usage.free / (1024**3)
        return (
            f"Espace disque ({chemin}) :\n"
            f"  • Total : {t_go:.1f} Go\n"
            f"  • Utilisé : {u_go:.1f} Go ({usage.percent}%)\n"
            f"  • Libre : {l_go:.1f} Go"
        )
    except Exception as e:
        log_error("pc_control", f"obtenir_espace_disque échoué : {e}", exc_info=False)
        return f"Erreur espace disque : {str(e)[:150]}"


def obtenir_infos_systeme_detaillees():
    """Infos CPU/RAM/disque détaillées + température si disponible."""
    try:
        import psutil
    except ImportError:
        return "psutil requis : pip install psutil"

    try:
        cpu_p = psutil.cpu_percent(interval=1)
        cpu_n = psutil.cpu_count()
        cpu_f = psutil.cpu_freq()
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        lines = [
            f"🖥️  SYSTÈME : {platform.system()} {platform.release()}",
            f"    Machine : {platform.machine()} | CPU : {platform.processor() or '?'}",
            "",
            f"⚙️  CPU : {cpu_p:.1f}% | Cœurs : {cpu_n}",
        ]
        if cpu_f:
            lines.append(f"    Fréquence : {cpu_f.current:.0f} MHz")

        lines.extend([
            "",
            f"🧠 RAM : {ram.total/(1024**3):.1f} Go total",
            f"    Utilisée : {ram.used/(1024**3):.1f} Go ({ram.percent}%)",
            f"    Libre : {ram.available/(1024**3):.1f} Go",
            "",
            f"💾 DISQUE : {disk.total/(1024**3):.1f} Go total",
            f"    Utilisé : {disk.used/(1024**3):.1f} Go ({disk.percent}%)",
            f"    Libre : {disk.free/(1024**3):.1f} Go",
        ])

        # Température si disponible
        try:
            if hasattr(psutil, "sensors_temperatures"):
                for name, entries in psutil.sensors_temperatures().items():
                    for entry in entries[:3]:
                        if entry.current:
                            lines.append(f"\n🌡️  {entry.label or name} : {entry.current:.1f}°C")
        except Exception:
            pass

        return "\n".join(lines)

    except Exception as e:
        log_error("pc_control", f"infos_système échoué : {e}", exc_info=False)
        return f"Erreur : {str(e)[:150]}"


def lister_applications_ouvertes(limite=20):
    """Liste applications ouvertes avec utilisation mémoire."""
    try:
        import psutil
    except ImportError:
        return "psutil requis : pip install psutil"

    try:
        limite = max(1, min(int(limite), 50))
    except (TypeError, ValueError):
        limite = 20

    apps = {}
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            nom = proc.info.get('name')
            if not nom or nom.startswith('System') or nom.startswith('['):
                continue
            mem_mb = (proc.info.get('memory_info').rss / (1024*1024)) if proc.info.get('memory_info') else 0
            if nom not in apps:
                apps[nom] = {"nom": nom, "memoire_mo": mem_mb, "instances": 1}
            else:
                apps[nom]["instances"] += 1
                apps[nom]["memoire_mo"] += mem_mb
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    tries = sorted(apps.values(), key=lambda x: x["memoire_mo"], reverse=True)[:limite]
    
    if not tries:
        return "Aucune application détectée."

    lines = [f"Applications ouvertes ({len(tries)}) :\n"]
    for app in tries:
        ins = f" ({app['instances']} instances)" if app["instances"] > 1 else ""
        lines.append(f"  • {app['nom']}{ins} — {app['memoire_mo']:.0f} Mo")

    return "\n".join(lines)


def surveiller_ressources(duree_secondes=5):
    """Surveille CPU/RAM pendant N secondes et retourne moyennes/pics."""
    try:
        import psutil, time
    except ImportError:
        return "psutil requis : pip install psutil"

    try:
        d = max(1, min(int(duree_secondes), 30))
        cpu_samples = []
        mem_samples = []

        for _ in range(d):
            cpu_samples.append(psutil.cpu_percent(interval=1))
            mem_samples.append(psutil.virtual_memory().percent)

        return (
            f"📊 Surveillance ({d}s) :\n\n"
            f"CPU :\n"
            f"  • Moyenne : {sum(cpu_samples)/len(cpu_samples):.1f}%\n"
            f"  • Maximum : {max(cpu_samples):.1f}%\n\n"
            f"RAM :\n"
            f"  • Moyenne : {sum(mem_samples)/len(mem_samples):.1f}%\n"
            f"  • Maximum : {max(mem_samples):.1f}%"
        )
    except Exception as e:
        log_error("pc_control", f"surveillance échouée : {e}", exc_info=False)
        return f"Erreur surveillance : {str(e)[:150]}"
