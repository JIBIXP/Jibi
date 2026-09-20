"""
Serveur local de modèles pour JIBI.

But : charger Parakeet et Kokoro UNE SEULE FOIS, au démarrage de ce
serveur, et les garder en mémoire pendant que tu redémarres gui.py
autant de fois que tu veux en développement — sans repayer le
chargement des modèles (plusieurs secondes à chaque fois) à chaque
relance de l'interface.


Lancement (dans un terminal séparé, à laisser ouvert) :

    python serveur_modeles.py

Le serveur écoute sur http://127.0.0.1:8765

gui.py / ecoute_process.py essaient d'abord de le contacter ; s'il
n'est pas lancé, ils retombent automatiquement sur le chargement
local des modèles (comportement d'avant, juste plus lent au
démarrage). Le serveur est donc optionnel, pas obligatoire.

AMÉLIORATIONS v2 :
- Statistiques détaillées (requêtes, temps moyens, cache)
- Monitoring santé modèles (mémoire GPU/CPU, uptime)
- Gestion erreurs robuste (timeouts, validation, limites)
- Logging intégré avec logging_jibi
- Endpoints admin (stats, reload, shutdown)
- Support batch pour synthèse multiple
"""

import io
import os
import sys
import wave
import time
import asyncio
import psutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List

# Reconfiguration encodage UTF-8 pour Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Import voix (avec gestion erreur si modules manquants)
try:
    from voix import (
        FREQUENCE,
        generer_audio,
        get_modele_parakeet,
        transcrire_audio,
    )
    VOIX_DISPONIBLE = True
except Exception as e:
    print(f"[VOIX WARNING] Module voix partiellement indisponible : {e}")
    VOIX_DISPONIBLE = False
    FREQUENCE = 16000

# Logging JIBI (optionnel, repli sur print si absent)
try:
    from logging_jibi import log_event, log_warning, log_error
    LOGGING_DISPONIBLE = True
except ImportError:
    LOGGING_DISPONIBLE = False
    def log_event(cat, msg): print(f"[{cat}] {msg}")
    def log_warning(cat, msg): print(f"[{cat}] [WARNING] {msg}")
    def log_error(cat, msg, **kw): print(f"[{cat}] [ERROR] {msg}")


# ============================================================
# CONFIGURATION SERVEUR
# ============================================================

SERVEUR_HOST = os.getenv("SERVEUR_MODELES_HOST", "127.0.0.1")
SERVEUR_PORT = int(os.getenv("SERVEUR_MODELES_PORT", "8765"))

# Limites sécurité
MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_TEXTE_LENGTH = 5000  # Caractères
TIMEOUT_TRANSCRIPTION = 60  # Secondes
TIMEOUT_SYNTHESE = 30  # Secondes

# Cache
CACHE_SYNTHESE_ACTIVE = os.getenv("CACHE_SYNTHESE_ACTIVE", "1") == "1"
MAX_CACHE_SYNTHESE = 100

# Clé admin : CORRIGÉ — plus de valeur par défaut codée en dur.
# Avant : os.getenv("ADMIN_KEY", "jibi_admin_2024") était répété sur 5
# endpoints (dont un qui arrête le process et un qui vide le cache). Si
# ADMIN_KEY n'était pas défini dans l'environnement, n'importe qui
# connaissant ce défaut public (visible dans le code source) avait un accès
# admin complet. Désormais, si ADMIN_KEY n'est pas configuré, les endpoints
# admin sont simplement désactivés (403) au lieu de retomber sur un secret
# faible et connu.
ADMIN_KEY = os.getenv("ADMIN_KEY")

# ============================================================
# STATISTIQUES GLOBALES
# ============================================================

_stats_serveur = {
    "demarrage": datetime.now(),
    "uptime_secondes": 0,
    
    # Requêtes
    "requetes_total": 0,
    "requetes_transcription": 0,
    "requetes_synthese": 0,
    "requetes_health": 0,
    "requetes_erreurs": 0,
    
    # Performance transcription
    "transcription_temps_total": 0.0,
    "transcription_temps_moyen": 0.0,
    "transcription_audio_secondes_total": 0.0,
    "transcription_ratio_realtime": 0.0,  # Temps traitement / durée audio
    
    # Performance synthèse
    "synthese_temps_total": 0.0,
    "synthese_temps_moyen": 0.0,
    "synthese_caracteres_total": 0,
    "synthese_cache_hits": 0,
    "synthese_cache_misses": 0,
    
    # Modèles
    "parakeet_charge": False,
    "parakeet_temps_chargement": 0.0,
    "kokoro_charge": False,
    "kokoro_temps_chargement": 0.0,
}

_cache_synthese = {}  # {hash(texte+langue): chemin_fichier}

# ============================================================
# APPLICATION FASTAPI
# ============================================================

app = FastAPI(
    title="JIBI - Serveur modèles",
    description="Serveur de modèles STT/TTS pour JIBI (Parakeet + Kokoro)",
    version="2.0"
)

# CORS (si gui.py web nécessite cross-origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# UTILITAIRES
# ============================================================

def _obtenir_hash_texte(texte: str, langue: str) -> str:
    """Hash pour cache synthèse."""
    import hashlib
    cle = f"{texte}_{langue}"
    return hashlib.md5(cle.encode('utf-8')).hexdigest()[:16]


def _nettoyer_cache_synthese():
    """Supprime vieux fichiers cache si limite dépassée."""
    if len(_cache_synthese) > MAX_CACHE_SYNTHESE:
        # CORRIGÉ : l'ancien code triait les entrées par hash
        # (`key=lambda x: x[0]`), donc dans un ordre essentiellement
        # alphabétique/aléatoire — ce qui contredisait le commentaire
        # "garder les 80% plus récents". Les dicts Python (3.7+) préservent
        # l'ordre d'insertion : il suffit de NE PAS trier pour que les
        # entrées les plus anciennes soient bien en tête de liste et donc
        # supprimées en premier.
        items = list(_cache_synthese.items())
        nb_a_supprimer = len(items) - int(MAX_CACHE_SYNTHESE * 0.8)
        
        for hash_key, _ in items[:nb_a_supprimer]:
            _cache_synthese.pop(hash_key, None)
        
        log_event("serveur_modeles", f"Cache synthèse nettoyé ({nb_a_supprimer} entrées)")


def _verifier_admin_key(admin_key: str):
    """
    Vérifie la clé admin. CORRIGÉ : centralise la vérification (avant
    dupliquée 5 fois) et refuse par défaut si ADMIN_KEY n'est pas configuré,
    plutôt que d'accepter un secret par défaut codé en dur.
    """
    if not ADMIN_KEY or admin_key != ADMIN_KEY:
        raise HTTPException(
            status_code=403,
            detail="Clé admin invalide ou ADMIN_KEY non configurée sur le serveur.",
        )


def _obtenir_info_memoire():
    """Renvoie usage mémoire CPU/GPU."""
    info = {
        "cpu_memoire_mb": 0,
        "cpu_memoire_percent": 0.0,
        "gpu_disponible": False,
        "gpu_memoire_mb": 0,
        "gpu_utilisation_percent": 0.0
    }
    
    # Mémoire CPU (processus serveur)
    try:
        process = psutil.Process()
        mem_info = process.memory_info()
        info["cpu_memoire_mb"] = round(mem_info.rss / 1024 / 1024, 2)
        info["cpu_memoire_percent"] = round(process.memory_percent(), 2)
    except Exception as e:
        log_warning("serveur_modeles", f"Erreur info mémoire CPU: {e}")
    
    # Mémoire GPU (si CUDA disponible)
    try:
        import torch
        if torch.cuda.is_available():
            info["gpu_disponible"] = True
            info["gpu_memoire_mb"] = round(
                torch.cuda.memory_allocated() / 1024 / 1024, 2
            )
            # CORRIGÉ : diviser par max_memory_allocated() (le pic déjà
            # atteint par CE processus) ne donne pas un "% d'utilisation du
            # GPU" — ce ratio finit presque toujours proche de 100% dès que
            # le pic est atteint une fois, et ne renseigne pas sur la
            # pression mémoire réelle du device. On utilise la mémoire
            # totale du GPU comme dénominateur pour un vrai pourcentage
            # d'occupation.
            device = torch.cuda.current_device()
            total_memoire = torch.cuda.get_device_properties(device).total_memory
            info["gpu_utilisation_percent"] = round(
                torch.cuda.memory_allocated() / total_memoire * 100, 2
            ) if total_memoire > 0 else 0.0
    except Exception:
        pass
    
    return info


# ============================================================
# ÉVÉNEMENTS LIFECYCLE
# ============================================================

@app.on_event("startup")
def charger_modeles():
    """Charge modèles au démarrage (une seule fois)."""
    log_event("serveur_modeles", "▶ Démarrage serveur modèles JIBI...")
    
    if not VOIX_DISPONIBLE:
        log_error("serveur_modeles", "Module voix non disponible, serveur en mode dégradé")
        return
    
    # Parakeet (STT)
    log_event("serveur_modeles", "Chargement Parakeet (STT)...")
    try:
        debut = time.perf_counter()
        get_modele_parakeet()
        temps_charge = time.perf_counter() - debut
        
        _stats_serveur["parakeet_charge"] = True
        _stats_serveur["parakeet_temps_chargement"] = round(temps_charge, 2)
        
        log_event("serveur_modeles", f"✓ Parakeet chargé en {temps_charge:.2f}s")
    except Exception as e:
        log_error("serveur_modeles", f"❌ Parakeet échoué: {e}", exc_info=True)
    
    # Kokoro (TTS) - Précharge voix française
    log_event("serveur_modeles", "Chargement Kokoro (TTS)...")
    try:
        from voix import _obtenir_pipeline_kokoro
        
        debut = time.perf_counter()
        _obtenir_pipeline_kokoro("f")  # Français
        temps_charge = time.perf_counter() - debut
        
        _stats_serveur["kokoro_charge"] = True
        _stats_serveur["kokoro_temps_chargement"] = round(temps_charge, 2)
        
        log_event("serveur_modeles", f"✓ Kokoro français chargé en {temps_charge:.2f}s")
    except Exception as e:
        log_warning(
            "serveur_modeles",
            f"⚠️ Kokoro français non préchargé ({type(e).__name__}), se chargera à la demande"
        )
    
    # Récapitulatif
    temps_total = (
        _stats_serveur["parakeet_temps_chargement"] +
        _stats_serveur["kokoro_temps_chargement"]
    )
    
    log_event(
        "serveur_modeles",
        f"✓ Serveur prêt en {temps_total:.2f}s sur http://{SERVEUR_HOST}:{SERVEUR_PORT}"
    )


@app.on_event("shutdown")
def arreter_serveur():
    """Nettoyage avant arrêt."""
    log_event("serveur_modeles", "▶ Arrêt serveur modèles...")
    
    # Statistiques finales
    uptime = datetime.now() - _stats_serveur["demarrage"]
    log_event("serveur_modeles", f"Uptime : {uptime}")
    log_event("serveur_modeles", f"Requêtes total : {_stats_serveur['requetes_total']}")
    log_event("serveur_modeles", f"Erreurs : {_stats_serveur['requetes_erreurs']}")


# ============================================================
# ENDPOINTS HEALTH & STATS
# ============================================================

@app.get("/health")
def health_check():
    """Endpoint de vérification que le serveur est prêt."""
    _stats_serveur["requetes_health"] += 1
    _stats_serveur["requetes_total"] += 1
    
    # Calculer uptime
    uptime = datetime.now() - _stats_serveur["demarrage"]
    _stats_serveur["uptime_secondes"] = int(uptime.total_seconds())
    
    return {
        "status": "ok",
        "message": "Serveur modèles actif et prêt",
        "uptime_secondes": _stats_serveur["uptime_secondes"],
        "uptime_humain": str(uptime).split('.')[0],
        "modeles": {
            "parakeet": _stats_serveur["parakeet_charge"],
            "kokoro": _stats_serveur["kokoro_charge"]
        },
        "voix_disponible": VOIX_DISPONIBLE
    }


@app.get("/stats")
def obtenir_statistiques():
    """Statistiques détaillées du serveur."""
    _stats_serveur["requetes_total"] += 1
    
    # Uptime
    uptime = datetime.now() - _stats_serveur["demarrage"]
    _stats_serveur["uptime_secondes"] = int(uptime.total_seconds())
    
    # Calculs temps moyens
    if _stats_serveur["requetes_transcription"] > 0:
        _stats_serveur["transcription_temps_moyen"] = round(
            _stats_serveur["transcription_temps_total"] / _stats_serveur["requetes_transcription"],
            3
        )
    
    if _stats_serveur["requetes_synthese"] > 0:
        _stats_serveur["synthese_temps_moyen"] = round(
            _stats_serveur["synthese_temps_total"] / _stats_serveur["requetes_synthese"],
            3
        )
    
    # Ratio cache synthèse
    total_cache = _stats_serveur["synthese_cache_hits"] + _stats_serveur["synthese_cache_misses"]
    cache_hit_rate = (
        round(_stats_serveur["synthese_cache_hits"] / total_cache * 100, 2)
        if total_cache > 0 else 0.0
    )
    
    # Ratio real-time transcription
    if _stats_serveur["transcription_audio_secondes_total"] > 0:
        _stats_serveur["transcription_ratio_realtime"] = round(
            _stats_serveur["transcription_temps_total"] /
            _stats_serveur["transcription_audio_secondes_total"],
            2
        )
    
    stats = _stats_serveur.copy()
    stats["uptime_humain"] = str(uptime).split('.')[0]
    stats["cache_synthese_hit_rate"] = cache_hit_rate
    stats["cache_synthese_size"] = len(_cache_synthese)
    stats["memoire"] = _obtenir_info_memoire()
    
    return stats


# CORRIGÉ : cet endpoint MUTE l'état du serveur (reset des stats) mais était
# déclaré en GET. Une requête GET n'est censée avoir aucun effet de bord
# (elle peut être re-jouée, préchargée par un navigateur/proxy, ou loggée
# en clair avec la clé admin dans l'URL). Tous les autres endpoints admin
# mutants utilisent POST/DELETE — on aligne celui-ci sur POST.
@app.post("/stats/reset")
def reinitialiser_statistiques(
    admin_key: str = Query(..., description="Clé admin pour reset stats")
):
    """Réinitialise statistiques (admin seulement)."""
    _verifier_admin_key(admin_key)
    
    # Garder infos modèles, reset le reste
    parakeet_charge = _stats_serveur["parakeet_charge"]
    parakeet_temps = _stats_serveur["parakeet_temps_chargement"]
    kokoro_charge = _stats_serveur["kokoro_charge"]
    kokoro_temps = _stats_serveur["kokoro_temps_chargement"]
    
    _stats_serveur.clear()
    _stats_serveur.update({
        "demarrage": datetime.now(),
        "uptime_secondes": 0,
        "requetes_total": 0,
        "requetes_transcription": 0,
        "requetes_synthese": 0,
        "requetes_health": 0,
        "requetes_erreurs": 0,
        "transcription_temps_total": 0.0,
        "transcription_temps_moyen": 0.0,
        "transcription_audio_secondes_total": 0.0,
        "transcription_ratio_realtime": 0.0,
        "synthese_temps_total": 0.0,
        "synthese_temps_moyen": 0.0,
        "synthese_caracteres_total": 0,
        "synthese_cache_hits": 0,
        "synthese_cache_misses": 0,
        "parakeet_charge": parakeet_charge,
        "parakeet_temps_chargement": parakeet_temps,
        "kokoro_charge": kokoro_charge,
        "kokoro_temps_chargement": kokoro_temps,
    })
    
    log_event("serveur_modeles", "Statistiques réinitialisées")
    return {"status": "ok", "message": "Statistiques réinitialisées"}


# ============================================================
# ENDPOINTS STT (TRANSCRIPTION)
# ============================================================

@app.post("/transcrire")
async def route_transcrire(
    fichier: UploadFile = File(...),
    langue_cible: Optional[str] = Form(None)
):
    """
    Transcrit un fichier audio WAV en texte.
    
    Args:
        fichier: Fichier audio WAV (max 50MB)
        langue_cible: Langue cible (optionnel, auto-détection sinon)
    
    Returns:
        {
            "texte": "...",
            "langue": "fr",
            "duree_audio": 3.5,
            "temps_traitement": 1.2,
            "ratio_realtime": 0.34
        }
    """
    _stats_serveur["requetes_total"] += 1
    _stats_serveur["requetes_transcription"] += 1
    
    if not VOIX_DISPONIBLE:
        _stats_serveur["requetes_erreurs"] += 1
        raise HTTPException(status_code=503, detail="Module voix non disponible")
    
    if not _stats_serveur["parakeet_charge"]:
        _stats_serveur["requetes_erreurs"] += 1
        raise HTTPException(status_code=503, detail="Modèle Parakeet non chargé")
    
    try:
        debut = time.perf_counter()
        
        # Lire fichier
        donnees = await fichier.read()
        
        if not donnees:
            _stats_serveur["requetes_erreurs"] += 1
            raise HTTPException(status_code=400, detail="Fichier audio vide")
        
        if len(donnees) > MAX_AUDIO_SIZE:
            _stats_serveur["requetes_erreurs"] += 1
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux (max {MAX_AUDIO_SIZE / 1024 / 1024}MB)"
            )
        
        # Parser WAV
        with wave.open(io.BytesIO(donnees), "rb") as f:
            trames = f.readframes(f.getnframes())
            channels = f.getnchannels()
            sample_width = f.getsampwidth()
            framerate = f.getframerate()
        
        # Convertir en numpy
        audio_np = np.frombuffer(trames, dtype=np.int16).copy()
        
        if audio_np.size == 0:
            _stats_serveur["requetes_erreurs"] += 1
            raise HTTPException(status_code=400, detail="Audio WAV vide")
        
        # Stéréo → Mono si nécessaire
        if channels == 2:
            audio_np = audio_np.reshape(-1, 2).mean(axis=1).astype(np.int16)
        
        duree_audio = audio_np.size / framerate
        
        log_event(
            "serveur_modeles",
            f"🎤 /transcrire : {duree_audio:.2f}s reçues "
            f"({len(donnees) / 1024:.1f}KB, {framerate}Hz)"
        )
        
        # Transcription avec timeout — CORRIGÉ (double bug) :
        # 1) L'ancienne version utilisait signal.alarm(), explicitement
        #    non-fonctionnel sous Windows (le commentaire promettait un
        #    repli via threading.Timer qui n'a jamais été écrit) : le
        #    timeout était donc purement inexistant sous Windows.
        # 2) transcrire_audio() était appelée de façon bloquante DANS une
        #    route "async def", ce qui gèle out l'event loop asyncio (donc
        #    TOUT le serveur, y compris /health) pendant toute la durée de
        #    chaque transcription. On délègue l'appel bloquant à un
        #    threadpool via run_in_executor et on utilise asyncio.wait_for
        #    pour le timeout, ce qui fonctionne identiquement sur toutes
        #    les plateformes sans bloquer le reste du serveur.
        loop = asyncio.get_event_loop()
        try:
            texte, langue = await asyncio.wait_for(
                loop.run_in_executor(None, transcrire_audio, audio_np),
                timeout=TIMEOUT_TRANSCRIPTION,
            )
        except asyncio.TimeoutError:
            _stats_serveur["requetes_erreurs"] += 1
            raise HTTPException(
                status_code=504,
                detail=f"Transcription timeout ({TIMEOUT_TRANSCRIPTION}s)"
            )
        
        # Statistiques
        temps_traitement = time.perf_counter() - debut
        ratio_realtime = temps_traitement / duree_audio if duree_audio > 0 else 0
        
        _stats_serveur["transcription_temps_total"] += temps_traitement
        _stats_serveur["transcription_audio_secondes_total"] += duree_audio
        
        log_event(
            "serveur_modeles",
            f"✓ Transcription en {temps_traitement:.2f}s "
            f"(ratio {ratio_realtime:.2f}×) : {texte!r}"
        )
        
        return {
            "texte": texte,
            "langue": langue,
            "duree_audio": round(duree_audio, 2),
            "temps_traitement": round(temps_traitement, 2),
            "ratio_realtime": round(ratio_realtime, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        _stats_serveur["requetes_erreurs"] += 1
        log_error("serveur_modeles", f"Erreur transcription: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur transcription: {str(e)[:100]}"
        )


# ============================================================
# ENDPOINTS TTS (SYNTHÈSE)
# ============================================================

@app.post("/synthetiser")
def route_synthetiser(
    texte: str = Form(...),
    langue: str = Form("fr")
):
    """
    Génère l'audio d'un texte (Kokoro TTS).
    
    Args:
        texte: Texte à synthétiser (max 5000 caractères)
        langue: Code langue (fr, en, etc.)
    
    Returns:
        Fichier audio WAV/MP3
    
    Headers:
        X-Cache-Hit: "true" si servi depuis cache
        X-Generation-Time: Temps génération (si cache miss)
    """
    _stats_serveur["requetes_total"] += 1
    _stats_serveur["requetes_synthese"] += 1
    
    if not VOIX_DISPONIBLE:
        _stats_serveur["requetes_erreurs"] += 1
        raise HTTPException(status_code=503, detail="Module voix non disponible")
    
    if not _stats_serveur["kokoro_charge"]:
        log_warning("serveur_modeles", "Kokoro non préchargé, chargement à la demande...")
    
    # Validation
    if not texte.strip():
        _stats_serveur["requetes_erreurs"] += 1
        raise HTTPException(status_code=400, detail="Texte vide")
    
    if len(texte) > MAX_TEXTE_LENGTH:
        _stats_serveur["requetes_erreurs"] += 1
        raise HTTPException(
            status_code=413,
            detail=f"Texte trop long (max {MAX_TEXTE_LENGTH} caractères)"
        )
    
    try:
        cache_hit = False
        temps_generation = 0.0
        
        # Vérifier cache
        if CACHE_SYNTHESE_ACTIVE:
            hash_key = _obtenir_hash_texte(texte, langue)
            chemin_cache = _cache_synthese.get(hash_key)
            
            if chemin_cache and Path(chemin_cache).exists():
                cache_hit = True
                chemin = chemin_cache
                _stats_serveur["synthese_cache_hits"] += 1
                
                log_event(
                    "serveur_modeles",
                    f"🔊 /synthetiser (CACHE HIT) : {len(texte)} car, langue={langue}"
                )
            else:
                _stats_serveur["synthese_cache_misses"] += 1
        
        # Générer si pas en cache
        if not cache_hit:
            debut = time.perf_counter()
            
            log_event(
                "serveur_modeles",
                f"🔊 /synthetiser : {len(texte)} car, langue={langue}"
            )
            
            chemin = generer_audio(texte, langue)
            
            temps_generation = time.perf_counter() - debut
            _stats_serveur["synthese_temps_total"] += temps_generation
            _stats_serveur["synthese_caracteres_total"] += len(texte)
            
            if not chemin:
                _stats_serveur["requetes_erreurs"] += 1
                raise HTTPException(
                    status_code=500,
                    detail="Synthèse audio échouée (Kokoro)"
                )
            
            # Sauvegarder en cache
            if CACHE_SYNTHESE_ACTIVE:
                hash_key = _obtenir_hash_texte(texte, langue)
                _cache_synthese[hash_key] = chemin
                _nettoyer_cache_synthese()
            
            log_event(
                "serveur_modeles",
                f"✓ Synthèse en {temps_generation:.2f}s"
            )
        
        # Réponse
        media_type = "audio/wav" if chemin.endswith(".wav") else "audio/mpeg"
        
        headers = {
            "X-Cache-Hit": "true" if cache_hit else "false",
        }
        
        if not cache_hit:
            headers["X-Generation-Time"] = f"{temps_generation:.2f}"
        
        return FileResponse(
            chemin,
            media_type=media_type,
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        _stats_serveur["requetes_erreurs"] += 1
        log_error("serveur_modeles", f"Erreur synthèse: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur synthèse: {str(e)[:100]}"
        )


@app.post("/synthetiser/batch")
def route_synthetiser_batch(
    textes: List[str] = Form(...),
    langue: str = Form("fr")
):
    """
    Synthèse batch (plusieurs textes d'un coup).
    
    Returns:
        {
            "fichiers": ["chemin1.wav", "chemin2.wav", ...],
            "temps_total": 5.2,
            "cache_hits": 2
        }
    """
    _stats_serveur["requetes_total"] += 1
    
    if not VOIX_DISPONIBLE:
        _stats_serveur["requetes_erreurs"] += 1
        raise HTTPException(status_code=503, detail="Module voix non disponible")
    
    if len(textes) > 20:
        _stats_serveur["requetes_erreurs"] += 1
        raise HTTPException(status_code=413, detail="Max 20 textes par batch")
    
    try:
        debut = time.perf_counter()
        fichiers = []
        cache_hits = 0
        
        for texte in textes:
            if not texte.strip():
                continue
            
            # Vérifier cache
            cache_hit = False
            if CACHE_SYNTHESE_ACTIVE:
                hash_key = _obtenir_hash_texte(texte, langue)
                chemin_cache = _cache_synthese.get(hash_key)
                
                if chemin_cache and Path(chemin_cache).exists():
                    fichiers.append(chemin_cache)
                    cache_hit = True
                    cache_hits += 1
            
            # Générer si pas en cache
            if not cache_hit:
                chemin = generer_audio(texte, langue)
                if chemin:
                    fichiers.append(chemin)
                    
                    if CACHE_SYNTHESE_ACTIVE:
                        hash_key = _obtenir_hash_texte(texte, langue)
                        _cache_synthese[hash_key] = chemin
        
        temps_total = time.perf_counter() - debut
        
        log_event(
            "serveur_modeles",
            f"✓ Batch {len(textes)} synthèses en {temps_total:.2f}s "
            f"({cache_hits} cache hits)"
        )
        
        return {
            "fichiers": fichiers,
            "temps_total": round(temps_total, 2),
            "cache_hits": cache_hits
        }
        
    except Exception as e:
        _stats_serveur["requetes_erreurs"] += 1
        log_error("serveur_modeles", f"Erreur batch synthèse: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur batch: {str(e)[:100]}")


# ============================================================
# ENDPOINTS ADMIN
# ============================================================

@app.post("/admin/reload")
def recharger_modeles(
    admin_key: str = Query(..., description="Clé admin")
):
    """Recharge les modèles (si crash ou mise à jour)."""
    _verifier_admin_key(admin_key)
    
    log_event("serveur_modeles", "▶ Rechargement modèles...")
    
    try:
        charger_modeles()
        return {"status": "ok", "message": "Modèles rechargés"}
    except Exception as e:
        log_error("serveur_modeles", f"Erreur rechargement: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.post("/admin/shutdown")
def arreter_serveur_admin(
    admin_key: str = Query(..., description="Clé admin")
):
    """Arrête le serveur proprement."""
    _verifier_admin_key(admin_key)
    
    log_event("serveur_modeles", "▶ Arrêt serveur demandé (admin)")
    
    # Arrêt propre après réponse
    import threading
    def shutdown():
        time.sleep(1)
        os._exit(0)
    
    threading.Thread(target=shutdown, daemon=True).start()
    
    return {"status": "ok", "message": "Serveur en arrêt..."}


@app.get("/admin/cache")
def obtenir_cache_info(
    admin_key: str = Query(..., description="Clé admin")
):
    """Informations détaillées sur cache synthèse."""
    _verifier_admin_key(admin_key)
    
    cache_entries = []
    taille_totale = 0
    
    for hash_key, chemin in _cache_synthese.items():
        fichier = Path(chemin)
        if fichier.exists():
            taille = fichier.stat().st_size
            taille_totale += taille
            
            cache_entries.append({
                "hash": hash_key,
                "fichier": fichier.name,
                "taille_kb": round(taille / 1024, 2),
                "modifie": datetime.fromtimestamp(fichier.stat().st_mtime).isoformat()
            })
    
    return {
        "count": len(cache_entries),
        "taille_totale_mb": round(taille_totale / 1024 / 1024, 2),
        "max_size": MAX_CACHE_SYNTHESE,
        "entries": sorted(cache_entries, key=lambda x: x["modifie"], reverse=True)
    }


@app.delete("/admin/cache")
def vider_cache(
    admin_key: str = Query(..., description="Clé admin")
):
    """Vide cache synthèse."""
    _verifier_admin_key(admin_key)
    
    count = len(_cache_synthese)
    _cache_synthese.clear()
    
    log_event("serveur_modeles", f"Cache synthèse vidé ({count} entrées)")
    
    return {"status": "ok", "message": f"{count} entrées supprimées"}


# ============================================================
# LANCEMENT SERVEUR
# ============================================================

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════════╗
║        JIBI - Serveur Modèles STT/TTS v2.0               ║
╚══════════════════════════════════════════════════════════╝

📡 Adresse : http://{SERVEUR_HOST}:{SERVEUR_PORT}
🔧 Endpoints :
   - GET  /health          : Santé serveur
   - GET  /stats           : Statistiques détaillées
   - POST /transcrire      : STT (audio → texte)
   - POST /synthetiser     : TTS (texte → audio)
   - POST /synthetiser/batch : TTS batch

🔐 Admin (ADMIN_KEY requis) :
   - POST /admin/reload    : Recharger modèles
   - POST /admin/shutdown  : Arrêter serveur
   - GET  /admin/cache     : Info cache
   - DELETE /admin/cache   : Vider cache
   {'⚠️  ADMIN_KEY non défini : tous les endpoints admin sont désactivés (403).' if not ADMIN_KEY else ''}

⚙️ Configuration :
   - Cache synthèse : {'✅' if CACHE_SYNTHESE_ACTIVE else '❌'}
   - Max cache : {MAX_CACHE_SYNTHESE} entrées
   - Max audio : {MAX_AUDIO_SIZE / 1024 / 1024}MB
   - Max texte : {MAX_TEXTE_LENGTH} caractères

Appuyez sur Ctrl+C pour arrêter.
""")
    
    uvicorn.run(
        app,
        host=SERVEUR_HOST,
        port=SERVEUR_PORT,
        log_level="info"
    )