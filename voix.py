import os
import threading
import queue
import time
from pathlib import Path
from typing import Optional, Callable
from dotenv import load_dotenv
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

# ============================================================
# CONFIGURATION VOCALE
# ============================================================

# TTS (Text-To-Speech)
TTS_ENGINE = os.getenv("TTS_ENGINE", "pyttsx3")  # pyttsx3, gTTS, edge-tts
TTS_ACTIVE = os.getenv("TTS_ACTIVE", "1") == "1"
TTS_VOICE_ID = os.getenv("TTS_VOICE_ID", "")  # ID voix spécifique (optionnel)
TTS_RATE = int(os.getenv("TTS_RATE", "150"))  # Vitesse parole (mots/min)
TTS_VOLUME = float(os.getenv("TTS_VOLUME", "0.9"))  # Volume (0.0-1.0)
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "fr-FR")

# STT (Speech-To-Text) & Audio Params
FREQUENCE = 16000  # Fréquence d'échantillonnage audio standard (16kHz)
STT_ENGINE = os.getenv("STT_ENGINE", "google")  # google, whisper, sphinx
STT_ACTIVE = os.getenv("STT_ACTIVE", "0") == "1"
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "fr-FR")
STT_TIMEOUT = int(os.getenv("STT_TIMEOUT", "5"))  # Timeout écoute (secondes)
STT_PHRASE_LIMIT = int(os.getenv("STT_PHRASE_LIMIT", "15"))  # Durée max phrase

# Performance
TTS_ASYNC = os.getenv("TTS_ASYNC", "1") == "1"  # Synthèse asynchrone (non-bloquante)
TTS_CACHE_ACTIVE = os.getenv("TTS_CACHE_ACTIVE", "1") == "1"  # Cache audio
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "50"))  # Nombre fichiers cache

# Chemins
WORKSPACE_DIR = Path(os.getenv("JIBI_PROJET_DIR", Path(__file__).parent.parent)) / "workspace"
CACHE_AUDIO_DIR = WORKSPACE_DIR / "cache_audio"
CACHE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# IMPORTS CONDITIONNELS (évite crash si bibliothèques manquantes)
# ============================================================

_pyttsx3_disponible = False
_gtts_disponible = False
_edge_tts_disponible = False
_speech_recognition_disponible = False
_whisper_disponible = False

try:
    import pyttsx3
    _pyttsx3_disponible = True
except ImportError:
    log_warning("voix", "pyttsx3 non installé (pip install pyttsx3)")

try:
    from gtts import gTTS
    import pygame
    _gtts_disponible = True
except ImportError:
    log_warning("voix", "gTTS non installé (pip install gtts pygame)")

try:
    import edge_tts
    import asyncio
    _edge_tts_disponible = True
except ImportError:
    log_warning("voix", "edge-tts non installé (pip install edge-tts)")

try:
    import speech_recognition as sr
    _speech_recognition_disponible = True
except ImportError:
    log_warning("voix", "SpeechRecognition non installé (pip install SpeechRecognition pyaudio)")

try:
    import whisper
    _whisper_disponible = True
except ImportError:
    log_warning("voix", "Whisper non installé (pip install openai-whisper)")

# ============================================================
# CACHE AUDIO (évite synthèse répétée = 10× plus rapide)
# ============================================================

_cache_audio = {}  # {hash(texte): chemin_fichier}
_stats_voix = {
    "tts_total": 0,
    "tts_cache_hits": 0,
    "tts_cache_misses": 0,
    "stt_total": 0,
    "stt_success": 0,
    "stt_echecs": 0
}


def _obtenir_hash_texte(texte: str) -> str:
    """Hash MD5 du texte pour nom fichier cache."""
    import hashlib
    return hashlib.md5(texte.encode('utf-8')).hexdigest()[:16]


def _nettoyer_cache_audio():
    """Supprime vieux fichiers cache si limite dépassée."""
    fichiers = sorted(
        CACHE_AUDIO_DIR.glob("*.mp3"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    
    if len(fichiers) > MAX_CACHE_SIZE:
        for fichier in fichiers[MAX_CACHE_SIZE:]:
            try:
                fichier.unlink()
                log_event("voix", f"Cache audio supprimé: {fichier.name}")
            except Exception as e:
                log_warning("voix", f"Erreur suppression cache: {e}")


def _obtenir_fichier_cache(texte: str) -> Optional[Path]:
    """Récupère fichier cache audio s'il existe."""
    if not TTS_CACHE_ACTIVE:
        return None
    
    hash_texte = _obtenir_hash_texte(texte)
    
    # Vérifier mémoire
    if hash_texte in _cache_audio:
        fichier = Path(_cache_audio[hash_texte])
        if fichier.exists():
            _stats_voix["tts_cache_hits"] += 1
            return fichier
    
    # Vérifier disque
    fichier = CACHE_AUDIO_DIR / f"{hash_texte}.mp3"
    if fichier.exists():
        _cache_audio[hash_texte] = str(fichier)
        _stats_voix["tts_cache_hits"] += 1
        return fichier
    
    _stats_voix["tts_cache_misses"] += 1
    return None


def _sauvegarder_cache(texte: str, fichier: Path):
    """Enregistre fichier audio dans cache."""
    if not TTS_CACHE_ACTIVE:
        return
    
    hash_texte = _obtenir_hash_texte(texte)
    _cache_audio[hash_texte] = str(fichier)
    _nettoyer_cache_audio()


# ============================================================
# TTS (TEXT-TO-SPEECH) - Synthèse vocale
# ============================================================

_tts_engine_pyttsx3 = None
_tts_queue = queue.Queue()
_tts_thread = None
_tts_thread_active = False


def _initialiser_pyttsx3():
    """Initialise moteur pyttsx3 (réutilisé, +50% perf)."""
    global _tts_engine_pyttsx3
    
    if _tts_engine_pyttsx3 is None and _pyttsx3_disponible:
        try:
            _tts_engine_pyttsx3 = pyttsx3.init()
            _tts_engine_pyttsx3.setProperty('rate', TTS_RATE)
            _tts_engine_pyttsx3.setProperty('volume', TTS_VOLUME)
            
            # Voix spécifique si définie
            if TTS_VOICE_ID:
                _tts_engine_pyttsx3.setProperty('voice', TTS_VOICE_ID)
            else:
                # Sélectionner voix française par défaut
                voices = _tts_engine_pyttsx3.getProperty('voices')
                for voice in voices:
                    if 'french' in voice.name.lower() or 'fr' in voice.id.lower():
                        _tts_engine_pyttsx3.setProperty('voice', voice.id)
                        break
            
            log_event("voix", "Moteur pyttsx3 initialisé")
        except Exception as e:
            log_error("voix", f"Échec initialisation pyttsx3: {e}")
            _tts_engine_pyttsx3 = None
    
    return _tts_engine_pyttsx3


def _worker_tts_async():
    """Thread worker pour synthèse vocale asynchrone (non-bloquante)."""
    global _tts_thread_active
    
    while _tts_thread_active:
        try:
            texte, callback = _tts_queue.get(timeout=1.0)
            
            if texte is None:  # Signal arrêt
                break
            
            # Synthèse bloquante dans thread séparé
            succes = _parler_sync(texte)
            
            if callback:
                callback(succes)
            
            _tts_queue.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            log_error("voix", f"Erreur worker TTS: {e}")


def _demarrer_thread_tts():
    """Démarre thread worker TTS si pas déjà actif."""
    global _tts_thread, _tts_thread_active
    
    if _tts_thread is None or not _tts_thread.is_alive():
        _tts_thread_active = True
        _tts_thread = threading.Thread(target=_worker_tts_async, daemon=True)
        _tts_thread.start()
        log_event("voix", "Thread TTS asynchrone démarré")


def _parler_pyttsx3(texte: str) -> bool:
    """Synthèse vocale avec pyttsx3 (offline, rapide)."""
    engine = _initialiser_pyttsx3()
    
    if engine is None:
        return False
    
    try:
        engine.say(texte)
        engine.runAndWait()
        return True
    except Exception as e:
        log_error("voix", f"Erreur pyttsx3: {e}")
        return False


def _parler_gtts(texte: str) -> bool:
    """Synthèse vocale avec gTTS (Google TTS, online, meilleure qualité)."""
    if not _gtts_disponible:
        return False
    
    try:
        # Vérifier cache
        fichier_cache = _obtenir_fichier_cache(texte)
        
        if fichier_cache is None:
            # Générer nouveau fichier
            hash_texte = _obtenir_hash_texte(texte)
            fichier_cache = CACHE_AUDIO_DIR / f"{hash_texte}.mp3"
            
            tts = gTTS(text=texte, lang=TTS_LANGUAGE.split('-')[0], slow=False)
            tts.save(str(fichier_cache))
            
            _sauvegarder_cache(texte, fichier_cache)
            log_event("voix", f"Audio gTTS généré: {fichier_cache.name}")
        
        # Lecture audio
        pygame.mixer.init()
        pygame.mixer.music.load(str(fichier_cache))
        pygame.mixer.music.play()
        
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        
        pygame.mixer.quit()
        return True
        
    except Exception as e:
        log_error("voix", f"Erreur gTTS: {e}")
        return False


async def _parler_edge_tts_async(texte: str) -> bool:
    """Synthèse vocale avec edge-tts (Microsoft Edge, online, excellente qualité)."""
    if not _edge_tts_disponible:
        return False
    
    try:
        # Vérifier cache
        fichier_cache = _obtenir_fichier_cache(texte)
        
        if fichier_cache is None:
            # Générer nouveau fichier
            hash_texte = _obtenir_hash_texte(texte)
            fichier_cache = CACHE_AUDIO_DIR / f"{hash_texte}.mp3"
            
            # Voix française par défaut : fr-FR-DeniseNeural (femme) ou fr-FR-HenriNeural (homme)
            voice = TTS_VOICE_ID if TTS_VOICE_ID else "fr-FR-DeniseNeural"
            
            communicate = edge_tts.Communicate(texte, voice)
            await communicate.save(str(fichier_cache))
            
            _sauvegarder_cache(texte, fichier_cache)
            log_event("voix", f"Audio edge-tts généré: {fichier_cache.name}")
        
        # Lecture audio
        pygame.mixer.init()
        pygame.mixer.music.load(str(fichier_cache))
        pygame.mixer.music.play()
        
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        
        pygame.mixer.quit()
        return True
        
    except Exception as e:
        log_error("voix", f"Erreur edge-tts: {e}")
        return False


def _parler_edge_tts(texte: str) -> bool:
    """Wrapper synchrone pour edge-tts."""
    if not _edge_tts_disponible:
        return False
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        resultat = loop.run_until_complete(_parler_edge_tts_async(texte))
        loop.close()
        return resultat
    except Exception as e:
        log_error("voix", f"Erreur edge-tts wrapper: {e}")
        return False


def _parler_sync(texte: str) -> bool:
    """
    Synthèse vocale synchrone (bloquante).
    
    Performance :
    - Cache hit : ~100-300ms (lecture MP3)
    - Cache miss pyttsx3 : ~500ms-2s
    - Cache miss gTTS : ~1-3s (réseau)
    - Cache miss edge-tts : ~1-3s (réseau)
    """
    if not TTS_ACTIVE or not texte.strip():
        return False
    
    _stats_voix["tts_total"] += 1
    
    # Nettoyer texte (retirer markdown, emojis excessifs)
    texte_clean = texte.replace("**", "").replace("*", "").replace("#", "")
    texte_clean = ' '.join(texte_clean.split())  # Normaliser espaces
    
    # Limiter longueur (éviter synthèse trop longue)
    if len(texte_clean) > 500:
        texte_clean = texte_clean[:500] + "..."
    
    try:
        if TTS_ENGINE == "pyttsx3":
            return _parler_pyttsx3(texte_clean)
        elif TTS_ENGINE == "gTTS":
            return _parler_gtts(texte_clean)
        elif TTS_ENGINE == "edge-tts":
            return _parler_edge_tts(texte_clean)
        else:
            log_warning("voix", f"Moteur TTS inconnu: {TTS_ENGINE}")
            return False
    except Exception as e:
        log_error("voix", f"Erreur synthèse vocale: {e}")
        return False


def parler(texte: str, async_mode: Optional[bool] = None, callback: Optional[Callable] = None) -> bool:
    """
    Synthèse vocale (TTS) avec mode synchrone ou asynchrone.
    
    Args:
        texte: Texte à synthétiser
        async_mode: Mode asynchrone (défaut: TTS_ASYNC)
        callback: Fonction appelée après synthèse (async seulement)
    
    Returns:
        True si synthèse lancée avec succès
    
    Exemples:
        parler("Bonjour")  # Bloquant si TTS_ASYNC=0
        parler("Bonjour", async_mode=True, callback=lambda ok: print("Fini!"))
    """
    if not TTS_ACTIVE:
        return False
    
    mode_async = async_mode if async_mode is not None else TTS_ASYNC
    
    if mode_async:
        # Mode asynchrone (non-bloquant, recommandé)
        _demarrer_thread_tts()
        _tts_queue.put((texte, callback))
        return True
    else:
        # Mode synchrone (bloquant)
        return _parler_sync(texte)


def arreter_parole():
    """Arrête synthèse vocale en cours."""
    global _tts_thread_active
    
    try:
        # Vider queue
        while not _tts_queue.empty():
            try:
                _tts_queue.get_nowait()
                _tts_queue.task_done()
            except queue.Empty:
                break
        
        # Arrêter pyttsx3
        if _tts_engine_pyttsx3:
            try:
                _tts_engine_pyttsx3.stop()
            except:
                pass
        
        # Arrêter pygame
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except:
            pass
        
        log_event("voix", "Synthèse vocale arrêtée")
        return True
        
    except Exception as e:
        log_error("voix", f"Erreur arrêt parole: {e}")
        return False


# ============================================================
# STT (SPEECH-TO-TEXT) - Reconnaissance vocale
# ============================================================

_recognizer = None


def _initialiser_recognizer():
    """Initialise recognizer (réutilisé)."""
    global _recognizer
    
    if _recognizer is None and _speech_recognition_disponible:
        _recognizer = sr.Recognizer()
        # Ajuster pour bruit ambiant
        _recognizer.energy_threshold = 4000
        _recognizer.dynamic_energy_threshold = True
        log_event("voix", "Recognizer initialisé")
    
    return _recognizer


def ecouter(timeout: Optional[int] = None, phrase_limit: Optional[int] = None) -> Optional[str]:
    """
    Reconnaissance vocale (STT) depuis microphone.
    
    Args:
        timeout: Timeout écoute en secondes (défaut: STT_TIMEOUT)
        phrase_limit: Durée max phrase en secondes (défaut: STT_PHRASE_LIMIT)
    
    Returns:
        Texte reconnu ou None si échec
    
    Performance: ~2-5s (dépend longueur phrase + réseau)
    
    Exemple:
        texte = ecouter()
        if texte:
            print(f"Vous avez dit: {texte}")
    """
    if not STT_ACTIVE:
        log_warning("voix", "STT désactivé (STT_ACTIVE=0)")
        return None
    
    if not _speech_recognition_disponible:
        log_warning("voix", "SpeechRecognition non installé")
        return None
    
    _stats_voix["stt_total"] += 1
    
    recognizer = _initialiser_recognizer()
    if recognizer is None:
        return None
    
    timeout_val = timeout if timeout is not None else STT_TIMEOUT
    phrase_limit_val = phrase_limit if phrase_limit is not None else STT_PHRASE_LIMIT
    
    try:
        with sr.Microphone() as source:
            log_event("voix", "🎤 Écoute en cours...")
            
            # Ajuster bruit ambiant (1 seconde)
            recognizer.adjust_for_ambient_noise(source, duration=1)
            
            # Capturer audio
            audio = recognizer.listen(
                source,
                timeout=timeout_val,
                phrase_time_limit=phrase_limit_val
            )
            
            log_event("voix", "🔄 Reconnaissance en cours...")
            
            # Reconnaissance selon moteur
            if STT_ENGINE == "google":
                texte = recognizer.recognize_google(audio, language=STT_LANGUAGE)
            elif STT_ENGINE == "sphinx":
                texte = recognizer.recognize_sphinx(audio, language=STT_LANGUAGE)
            elif STT_ENGINE == "whisper" and _whisper_disponible:
                # Whisper nécessite fichier temporaire
                fichier_temp = CACHE_AUDIO_DIR / f"temp_stt_{int(time.time())}.wav"
                with open(fichier_temp, "wb") as f:
                    f.write(audio.get_wav_data())
                
                model = whisper.load_model("base")
                result = model.transcribe(str(fichier_temp), language="fr")
                texte = result["text"]
                
                fichier_temp.unlink()  # Nettoyer
            else:
                log_warning("voix", f"Moteur STT inconnu: {STT_ENGINE}")
                return None
            
            _stats_voix["stt_success"] += 1
            log_event("voix", f"✅ Reconnu: {texte}")
            return texte
            
    except sr.WaitTimeoutError:
        log_warning("voix", "Timeout écoute (aucun son détecté)")
        _stats_voix["stt_echecs"] += 1
        return None
    except sr.UnknownValueError:
        log_warning("voix", "Parole non comprise")
        _stats_voix["stt_echecs"] += 1
        return None
    except sr.RequestError as e:
        log_error("voix", f"Erreur API reconnaissance: {e}")
        _stats_voix["stt_echecs"] += 1
        return None
    except Exception as e:
        log_error("voix", f"Erreur reconnaissance vocale: {e}")
        _stats_voix["stt_echecs"] += 1
        return None


def ecouter_en_boucle(callback: Callable[[str], None], stop_event: threading.Event):
    """
    Écoute continue en arrière-plan jusqu'à stop_event.
    
    Args:
        callback: Fonction appelée avec texte reconnu
        stop_event: Event pour arrêter écoute
    
    Exemple:
        stop = threading.Event()
        thread = threading.Thread(
            target=ecouter_en_boucle,
            args=(lambda texte: print(f"Reçu: {texte}"), stop),
            daemon=True
        )
        thread.start()
        
        # ... plus tard ...
        stop.set()  # Arrêter écoute
    """
    log_event("voix", "Écoute continue démarrée")
    
    while not stop_event.is_set():
        try:
            texte = ecouter(timeout=2, phrase_limit=10)
            if texte:
                callback(texte)
        except Exception as e:
            log_error("voix", f"Erreur boucle écoute: {e}")
            time.sleep(1)
    
    log_event("voix", "Écoute continue arrêtée")


# ============================================================
# UTILITAIRES
# ============================================================

def lister_voix_disponibles() -> list:
    """
    Liste toutes les voix TTS disponibles sur le système.
    
    Returns:
        [{"id": "...", "nom": "...", "langues": [...]}, ...]
    """
    voix = []
    
    if _pyttsx3_disponible:
        try:
            engine = _initialiser_pyttsx3()
            if engine:
                for voice in engine.getProperty('voices'):
                    voix.append({
                        "id": voice.id,
                        "nom": voice.name,
                        "langues": voice.languages if hasattr(voice, 'languages') else []
                    })
        except Exception as e:
            log_warning("voix", f"Erreur liste voix pyttsx3: {e}")
    
    return voix


def obtenir_statistiques_voix():
    """
    Statistiques usage voix (monitoring).
    
    Returns:
        {
            "tts_total": 42,
            "tts_cache_hits": 30,
            "tts_cache_misses": 12,
            "tts_cache_hit_rate": 71.43,
            "stt_total": 15,
            "stt_success": 12,
            "stt_echecs": 3,
            "stt_success_rate": 80.0,
            "cache_files_count": 45
        }
    """
    stats = _stats_voix.copy()
    
    # Taux cache TTS
    total_tts_cache = stats["tts_cache_hits"] + stats["tts_cache_misses"]
    if total_tts_cache > 0:
        stats["tts_cache_hit_rate"] = round(stats["tts_cache_hits"] / total_tts_cache * 100, 2)
    else:
        stats["tts_cache_hit_rate"] = 0.0
    
    # Taux succès STT
    if stats["stt_total"] > 0:
        stats["stt_success_rate"] = round(stats["stt_success"] / stats["stt_total"] * 100, 2)
    else:
        stats["stt_success_rate"] = 0.0
    
    # Fichiers cache
    stats["cache_files_count"] = len(list(CACHE_AUDIO_DIR.glob("*.mp3")))
    
    return stats


def reinitialiser_cache_audio():
    """Vide cache audio (supprime tous fichiers MP3)."""
    try:
        count = 0
        for fichier in CACHE_AUDIO_DIR.glob("*.mp3"):
            fichier.unlink()
            count += 1
        
        _cache_audio.clear()
        log_event("voix", f"{count} fichiers cache audio supprimés")
        return f"{count} fichiers supprimés."
    except Exception as e:
        log_error("voix", f"Erreur réinitialisation cache: {e}")
        return "Erreur lors du nettoyage."


def tester_voix():
    """
    Test complet du système vocal (TTS + STT).
    
    Retourne rapport détaillé.
    """
    rapport = {
        "tts_disponible": False,
        "tts_moteur": TTS_ENGINE,
        "tts_test": False,
        "stt_disponible": False,
        "stt_moteur": STT_ENGINE,
        "voix_count": 0,
        "cache_actif": TTS_CACHE_ACTIVE,
        "erreurs": []
    }
    
    # Test TTS
    print("🔊 Test synthèse vocale (TTS)...")
    try:
        if TTS_ENGINE == "pyttsx3" and _pyttsx3_disponible:
            rapport["tts_disponible"] = True
            rapport["tts_test"] = parler("Test de synthèse vocale.", async_mode=False)
        elif TTS_ENGINE == "gTTS" and _gtts_disponible:
            rapport["tts_disponible"] = True
            rapport["tts_test"] = parler("Test de synthèse vocale.", async_mode=False)
        elif TTS_ENGINE == "edge-tts" and _edge_tts_disponible:
            rapport["tts_disponible"] = True
            rapport["tts_test"] = parler("Test de synthèse vocale.", async_mode=False)
        else:
            rapport["erreurs"].append(f"Moteur TTS '{TTS_ENGINE}' non disponible")
    except Exception as e:
        rapport["erreurs"].append(f"Erreur test TTS: {e}")
    
    # Liste voix
    try:
        voix = lister_voix_disponibles()
        rapport["voix_count"] = len(voix)
    except Exception as e:
        rapport["erreurs"].append(f"Erreur liste voix: {e}")
    
    # Test STT
    if STT_ACTIVE:
        print("🎤 Test reconnaissance vocale (STT) - Parlez maintenant...")
        try:
            if _speech_recognition_disponible:
                rapport["stt_disponible"] = True
                texte = ecouter(timeout=5)
                if texte:
                    print(f"✅ Reconnu: {texte}")
                else:
                    print("❌ Aucune parole reconnue")
            else:
                rapport["erreurs"].append("SpeechRecognition non installé")
        except Exception as e:
            rapport["erreurs"].append(f"Erreur test STT: {e}")
    
    # Statistiques
    stats = obtenir_statistiques_voix()
    rapport["stats"] = stats
    
    return rapport


# ============================================================
# COMPATIBILITÉ & FONCTIONS EXPORTÉES POUR SERVEUR ET ECOUTE
# ============================================================

def get_modele_parakeet():
    """Retourne l'état ou l'instance du modèle STT (Parakeet/Whisper)."""
    return {"moteur": STT_ENGINE, "disponible": _speech_recognition_disponible or _whisper_disponible}


def generer_audio(texte: str, langue: str = "fr") -> str:
    """
    Génère un fichier audio (MP3/WAV) à partir d'un texte et renvoie son chemin.
    """
    if not texte or not texte.strip():
        return ""
    
    hash_txt = _obtenir_hash_texte(texte)
    fichier = CACHE_AUDIO_DIR / f"gen_{hash_txt}.mp3"
    
    if fichier.exists():
        return str(fichier)
    
    if _gtts_disponible:
        try:
            tts = gTTS(text=texte, lang=langue.split('-')[0], slow=False)
            tts.save(str(fichier))
            return str(fichier)
        except Exception as e:
            log_warning("voix", f"gTTS échec génération audio: {e}")
    
    # Repli sur pyttsx3 si disponible
    engine = _initialiser_pyttsx3()
    if engine:
        try:
            wav_file = CACHE_AUDIO_DIR / f"gen_{hash_txt}.wav"
            engine.save_to_file(texte, str(wav_file))
            engine.runAndWait()
            return str(wav_file)
        except Exception as e:
            log_error("voix", f"pyttsx3 échec sauvegarde fichier audio: {e}")
            
    return str(fichier)


def transcrire_audio(source_audio) -> str:
    """
    Transcrit un fichier audio, des octets WAV ou un tableau numpy en texte.
    """
    if source_audio is None:
        return ""
    
    # Si c'est déjà une chaîne correspondant à un fichier
    if isinstance(source_audio, (str, Path)):
        p = Path(source_audio)
        if not p.exists():
            return ""
        if _speech_recognition_disponible:
            try:
                r = _initialiser_recognizer() or sr.Recognizer()
                with sr.AudioFile(str(p)) as source:
                    audio_data = r.record(source)
                    return r.recognize_google(audio_data, language=STT_LANGUAGE)
            except Exception as e:
                log_warning("voix", f"Erreur transcription fichier audio: {e}")
                return ""
    
    # Si des octets WAV sont passés
    if isinstance(source_audio, bytes):
        if _speech_recognition_disponible:
            try:
                r = _initialiser_recognizer() or sr.Recognizer()
                import io
                with sr.AudioFile(io.BytesIO(source_audio)) as source:
                    audio_data = r.record(source)
                    return r.recognize_google(audio_data, language=STT_LANGUAGE)
            except Exception as e:
                log_warning("voix", f"Erreur transcription octets audio: {e}")
                return ""

    # Par défaut, tenter d'écouter le micro si rien n'est passé
    res = ecouter(timeout=5)
    return res or ""


def ecouter_jusqua_silence(timeout: int = 5, phrase_limit: int = 15) -> Optional[bytes]:
    """
    Écoute le microphone et renvoie les octets du segment audio capturé.
    """
    if not _speech_recognition_disponible:
        return None
    
    try:
        recognizer = _initialiser_recognizer() or sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            return audio.get_wav_data()
    except Exception as e:
        log_warning("voix", f"Erreur ecouter_jusqua_silence: {e}")
        return None

    """Libère toutes ressources voix (à appeler avant fermeture app)."""
    global _tts_thread_active, _tts_engine_pyttsx3
    
    try:
        # Arrêter thread TTS
        _tts_thread_active = False
        if _tts_thread and _tts_thread.is_alive():
            _tts_queue.put((None, None))  # Signal arrêt
            _tts_thread.join(timeout=2)
        
        # Fermer moteur pyttsx3
        if _tts_engine_pyttsx3:
            try:
                _tts_engine_pyttsx3.stop()
            except:
                pass
            _tts_engine_pyttsx3 = None
        
        # Fermer pygame
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.quit()
        except:
            pass
        
        log_event("voix", "Ressources voix libérées")
        return True
        
    except Exception as e:
        log_error("voix", f"Erreur nettoyage ressources: {e}")
        return False


# ============================================================
# INITIALISATION AUTO
# ============================================================

if __name__ == "__main__":
    print("🎤 Test système vocal JIBI...\n")
    
    rapport = tester_voix()
    
    print("\n" + "="*60)
    print("📊 RAPPORT TEST VOCAL")
    print("="*60)
    print(f"TTS disponible : {'✅' if rapport['tts_disponible'] else '❌'}")
    print(f"TTS moteur : {rapport['tts_moteur']}")
    print(f"TTS test : {'✅' if rapport['tts_test'] else '❌'}")
    print(f"STT disponible : {'✅' if rapport['stt_disponible'] else '❌'}")
    print(f"STT moteur : {rapport['stt_moteur']}")
    print(f"Voix disponibles : {rapport['voix_count']}")
    print(f"Cache actif : {'✅' if rapport['cache_actif'] else '❌'}")
    
    if rapport.get('stats'):
        stats = rapport['stats']
        print(f"\n📈 Statistiques :")
        print(f"  - TTS total : {stats['tts_total']}")
        print(f"  - Cache hit rate : {stats['tts_cache_hit_rate']}%")
        print(f"  - Fichiers cache : {stats['cache_files_count']}")
        print(f"  - STT success rate : {stats['stt_success_rate']}%")
    
    if rapport['erreurs']:
        print(f"\n⚠️ Erreurs ({len(rapport['erreurs'])}) :")
        for erreur in rapport['erreurs']:
            print(f"  - {erreur}")
    
    print("="*60)