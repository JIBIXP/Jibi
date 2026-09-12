
import atexit
import os
import re
import shutil
import tempfile
import uuid
import time

import numpy as np
import sounddevice as sd
import torch
import webrtcvad

from logging_jibi import log_event, log_error


# ============================================================
# CONFIGURATION
# ============================================================

FREQUENCE = 16000
DUREE_TRAME_MS = 30

# Pré-roll : récupère les premières syllabes
PRE_ROLL_MS = 240

# Temps de silence avant arrêt
# 900 ms = plus réactif que 1200 ms
POST_ROLL_MS = 300
SILENCE_MAX_MS = 900

TAILLE_TRAME = int(
    FREQUENCE * DUREE_TRAME_MS / 1000
)


# ============================================================
# DOSSIER TEMPORAIRE AUDIO
# ============================================================

_TEMP_AUDIO_DIR = tempfile.mkdtemp(
    prefix="jibi_audio_"
)


def _nettoyer_audio_temp():
    """Nettoie les fichiers audio temporaires à la fermeture."""
    try:
        if os.path.isdir(_TEMP_AUDIO_DIR):
            shutil.rmtree(_TEMP_AUDIO_DIR)
    except Exception as e:
        print(f"Erreur nettoyage audio : {e}")


atexit.register(_nettoyer_audio_temp)


# ============================================================
# PARAKEET
# ============================================================

PARAKEET_MODEL = "nvidia/parakeet-tdt-0.6b-v3"

_modele_parakeet = None


def get_modele_parakeet():
    """
    Charge Parakeet une seule fois.

    Le modèle reste ensuite en mémoire pour éviter
    de le recharger à chaque phrase.
    """

    global _modele_parakeet

    if _modele_parakeet is not None:
        return _modele_parakeet

    print("🧠 Chargement de Parakeet...")

    from transformers import pipeline

    if torch.cuda.is_available():
        device = 0
        dtype = torch.float16

        print("🎮 Parakeet : GPU NVIDIA détecté")

    else:
        device = -1
        dtype = torch.float32

        print("💻 Parakeet : CPU")

    _modele_parakeet = pipeline(
        "automatic-speech-recognition",
        model=PARAKEET_MODEL,
        device=device,
        torch_dtype=dtype
    )

    print("✅ Parakeet prêt.")

    return _modele_parakeet


# ============================================================
# VOLUME MICROPHONE
# ============================================================

def calculer_volume(trame):
    """Calcule un niveau sonore normalisé entre 0 et 1."""

    audio = trame.astype(np.float32)

    volume = np.sqrt(
        np.mean(audio ** 2)
    )

    return float(
        min(volume / 5000.0, 1.0)
    )


# ============================================================
# WARMUP VAD
# ============================================================

def _warmer_vad():
    """
    Initialise WebRTC VAD une première fois
    afin de réduire le délai au premier lancement.
    """

    try:
        vad = webrtcvad.Vad(2)

        silence = np.zeros(
            TAILLE_TRAME,
            dtype=np.int16
        )

        vad.is_speech(
            silence.tobytes(),
            FREQUENCE
        )

    except Exception:
        pass


_warmer_vad()


# ============================================================
# ÉCOUTE
# ============================================================

def ecouter_jusqua_silence(
    silence_max_ms=SILENCE_MAX_MS,
    sensibilite=1,
    duree_max_s=15,
    on_level=None
):
    """
    Écoute le microphone jusqu'à détection d'un silence.

    Optimisations :
    - VAD WebRTC
    - calibration rapide
    - pré-roll
    - détection de parole après quelques trames
    - arrêt plus rapide après la fin de phrase
    """

    vad = webrtcvad.Vad(sensibilite)

    trames_audio = []
    historique = []

    trames_silence = 0
    trames_parole_consecutives = 0

    a_parle = False

    max_trames_silence = max(
        1,
        int(silence_max_ms / DUREE_TRAME_MS)
    )

    pre_roll_frames = max(
        1,
        int(PRE_ROLL_MS / DUREE_TRAME_MS)
    )

    # --------------------------------------------------------
    # Calibration courte
    # --------------------------------------------------------

    calibration_ms = 300

    calibration_frames = max(
        1,
        int(calibration_ms / DUREE_TRAME_MS)
    )

    niveaux_bruit = []

    # --------------------------------------------------------
    # Microphone
    # --------------------------------------------------------

    stream = sd.InputStream(
        samplerate=FREQUENCE,
        channels=1,
        dtype="int16",
        blocksize=TAILLE_TRAME
    )

    try:

        with stream:

            max_trames = int(
                duree_max_s * 1000 / DUREE_TRAME_MS
            )

            for index in range(max_trames):

                trame, _ = stream.read(
                    TAILLE_TRAME
                )

                trame = trame.copy()

                niveau = calculer_volume(trame)

                if on_level:
                    on_level(niveau)

                # ------------------------------------------------
                # Historique pour récupérer le début de la voix
                # ------------------------------------------------

                historique.append(trame)

                if len(historique) > pre_roll_frames:
                    historique.pop(0)

                # ------------------------------------------------
                # Calibration
                # ------------------------------------------------

                if index < calibration_frames:

                    niveaux_bruit.append(niveau)

                    continue

                if niveaux_bruit:

                    bruit_moyen = float(
                        np.mean(niveaux_bruit)
                    )

                else:

                    bruit_moyen = 0.01

                # ------------------------------------------------
                # Seuil adaptatif
                # ------------------------------------------------

                seuil_volume = max(
                    0.02,
                    bruit_moyen * 2.0
                )

                # ------------------------------------------------
                # VAD
                # ------------------------------------------------

                try:

                    est_parole_vad = vad.is_speech(
                        trame.tobytes(),
                        FREQUENCE
                    )

                except Exception:

                    est_parole_vad = False

                est_parole = (
                    est_parole_vad
                    and niveau >= seuil_volume
                )

                # ------------------------------------------------
                # Détection du début
                # ------------------------------------------------

                if est_parole:

                    trames_parole_consecutives += 1

                else:

                    trames_parole_consecutives = 0

                if not a_parle:

                    # 3 trames = 90 ms
                    # évite les petits bruits
                    if trames_parole_consecutives >= 3:

                        trames_audio.extend(
                            historique
                        )

                        historique.clear()

                        a_parle = True
                        trames_silence = 0

                        trames_audio.append(
                            trame
                        )

                    continue

                # ------------------------------------------------
                # Après le début de parole
                # ------------------------------------------------

                if est_parole:

                    trames_silence = 0

                    trames_audio.append(
                        trame
                    )

                else:

                    trames_silence += 1

                    trames_audio.append(
                        trame
                    )

                    # Silence suffisamment long
                    if trames_silence >= max_trames_silence:
                        break

    except KeyboardInterrupt:

        pass

    except Exception as e:

        print(
            f"❌ Erreur microphone : {e}"
        )

    finally:

        try:
            stream.stop()
        except Exception:
            pass

        try:
            stream.close()
        except Exception:
            pass

    # ========================================================
    # Aucune parole
    # ========================================================

    if not trames_audio or not a_parle:
        return None

    audio = np.concatenate(
        trames_audio,
        axis=0
    )

    # ========================================================
    # Vérification signal
    # ========================================================

    audio_float = audio.astype(
        np.float32
    )

    peak = (
        float(np.max(np.abs(audio_float)))
        if audio_float.size
        else 0.0
    )

    if peak < 500:

        return None

    # ========================================================
    # Petite amplification
    # ========================================================

    if peak < 12000:

        facteur = min(
            16000.0 / peak,
            1.8
        )

        audio = np.clip(
            audio_float * facteur,
            -32768,
            32767
        ).astype(np.int16)

    return audio


# ============================================================
# TRANSCRIPTION PARAKEET
# ============================================================

def transcrire_audio(audio_np):
    """
    Transcrit l'audio avec Parakeet.

    Optimisation principale :
    num_beams=1 au lieu de 5.

    Cela réduit fortement le temps de génération
    tout en conservant un résultat adapté à un assistant vocal.
    """

    if audio_np is None:

        return ("", "fr")

    audio_np = np.asarray(
        audio_np
    ).reshape(-1)

    if audio_np.size == 0:

        return ("", "fr")

    duree = (
        audio_np.size / FREQUENCE
    )

    if duree < 0.20:

        print(
            f"⚠️ Audio trop court : {duree:.2f}s"
        )

        return ("", "fr")

    print(
        f"🎤 Audio reçu : {duree:.2f}s"
    )

    # --------------------------------------------------------
    # int16 -> float32
    # --------------------------------------------------------

    audio_float = (
        audio_np.astype(np.float32)
        / 32768.0
    )

    # Retire le DC offset
    audio_float -= np.mean(
        audio_float
    )

    # Protection NaN / Inf
    audio_float = np.nan_to_num(
        audio_float,
        nan=0.0,
        posinf=0.0,
        neginf=0.0
    )

    modele = get_modele_parakeet()

    try:

        resultat = modele(
            {
                "raw": audio_float,
                "sampling_rate": FREQUENCE
            },

            generate_kwargs={

                # ------------------------------------------------
                # IMPORTANT :
                # 1 beam = beaucoup plus rapide
                # ------------------------------------------------
                "num_beams": 1,

                "do_sample": False,

                "temperature": 0.0,

                # Suffisant pour les phrases vocales
                "max_new_tokens": 128
            }
        )

        texte = str(
            resultat.get(
                "text",
                ""
            )
        ).strip()

        # Nettoyage des espaces multiples
        texte = re.sub(
            r"\s+",
            " ",
            texte
        ).strip()

        print(
            f"🧠 Parakeet : {texte!r}"
        )

        return (
            texte,
            "fr"
        )

    except Exception as e:

        print(
            "❌ Erreur Parakeet : "
            f"{type(e).__name__}: {e}"
        )

        log_error(
            "stt",
            f"Parakeet échoué : "
            f"{type(e).__name__}: {str(e)[:100]}",
            exc_info=False
        )

        return (
            "",
            "fr"
        )


# ============================================================
# KOKORO
# ============================================================

_pipelines_kokoro = {}


def _obtenir_pipeline_kokoro(
    lang_code
):
    """
    Charge Kokoro une seule fois par langue.
    """

    if lang_code not in _pipelines_kokoro:

        print(
            f"🔊 Chargement de Kokoro ({lang_code})..."
        )

        from kokoro import KPipeline

        _pipelines_kokoro[
            lang_code
        ] = KPipeline(
            lang_code=lang_code
        )

        print(
            f"✅ Kokoro {lang_code} prêt."
        )

    return _pipelines_kokoro[
        lang_code
    ]


def _choisir_voix_kokoro(
    langue
):

    if langue == "fr":

        return (
            "f",
            "ff_siwis"
        )

    if langue == "en":

        return (
            "a",
            "af_heart"
        )

    return (
        "f",
        "ff_siwis"
    )


def _generer_kokoro(
    texte,
    langue
):

    import soundfile as sf

    lang_code, voix = (
        _choisir_voix_kokoro(
            langue
        )
    )

    pipeline = (
        _obtenir_pipeline_kokoro(
            lang_code
        )
    )

    morceaux = []

    for _, _, audio in pipeline(
        texte,
        voice=voix,
        speed=1.0
    ):

        if audio is not None:

            morceaux.append(
                np.asarray(audio)
            )

    if not morceaux:

        raise RuntimeError(
            "Kokoro n'a produit aucun audio."
        )

    audio_complet = np.concatenate(
        morceaux
    )

    # --------------------------------------------------------
    # Normalisation
    # --------------------------------------------------------

    audio_complet = (
        audio_complet
        .astype(np.float32)
    )

    peak = float(
        np.abs(
            audio_complet
        ).max()
    )

    if peak > 0:

        audio_complet = (
            audio_complet
            / peak
            * 0.95
        )

    # --------------------------------------------------------
    # Fichier
    # --------------------------------------------------------

    fichier_sortie = os.path.join(
        _TEMP_AUDIO_DIR,
        f"reponse_{uuid.uuid4().hex[:8]}.wav"
    )

    sf.write(
        fichier_sortie,
        audio_complet,
        24000,
        subtype="PCM_16"
    )

    return fichier_sortie


# ============================================================
# DÉCOUPAGE PHRASES
# ============================================================

def decouper_en_phrases(
    texte
):
    """
    Découpe le texte en phrases.

    Utilisé notamment par d'anciens composants de JIBI.
    Le nouveau GUI peut maintenant envoyer les phrases
    directement pendant le streaming.
    """

    texte = (
        texte or ""
    ).strip()

    if not texte:

        return []

    morceaux = re.split(
        r"(?<=[.!?。！？])\s+",
        texte
    )

    return [
        morceau.strip()
        for morceau in morceaux
        if morceau.strip()
    ]


# ============================================================
# GÉNÉRATION AUDIO LOCALE
# ============================================================

def generer_audio(
    texte,
    langue="fr"
):
    """
    Génère un fichier audio avec Kokoro.

    Ne joue pas automatiquement le fichier.
    """

    if not texte:

        return None

    try:

        log_event(
            "tts",
            "Kokoro..."
        )

        return _generer_kokoro(
            texte,
            langue
        )

    except Exception as erreur_kokoro:

        print(
            "❌ Synthèse vocale KO "
            f"(Kokoro): {str(erreur_kokoro)[:100]}"
        )

        log_error(
            "tts",
            "Kokoro échoué: "
            f"{type(erreur_kokoro).__name__}: "
            f"{str(erreur_kokoro)[:100]}",
            exc_info=False
        )

        return None


# ============================================================
# PARLER
# ============================================================

def parler(
    texte,
    langue="fr"
):
    """
    Compatibilité avec l'ancien système.
    Génère puis ouvre le fichier avec Windows.
    """

    fichier_sortie = generer_audio(
        texte,
        langue
    )

    if fichier_sortie:

        os.system(
            f'start "" "{fichier_sortie}"'
        )


# ============================================================
# SERVEUR TTS LOCAL
# ============================================================

URL_SERVEUR_MODELES = (
    "http://127.0.0.1:8765"
)


def generer_audio_client(
    texte,
    langue="fr"
):
    """
    Client TTS utilisé par gui.py.

    Priorité :
        1. serveur TTS local
        2. Kokoro directement dans ce processus

    Le format d'appel reste compatible avec
    l'ancien gui.py et le nouveau.
    """

    if not texte:

        return None

    texte = str(
        texte
    ).strip()

    if not texte:

        return None

    try:

        import requests

        reponse = requests.post(
            f"{URL_SERVEUR_MODELES}/synthetiser",

            data={
                "texte": texte,
                "langue": langue
            },

            # Timeout raisonnable
            timeout=30
        )

        reponse.raise_for_status()

        content_type = (
            reponse.headers
            .get(
                "content-type",
                ""
            )
            .lower()
        )

        if "wav" in content_type:

            extension = ".wav"

        elif "mp3" in content_type:

            extension = ".mp3"

        else:

            # Ton serveur actuel renvoie
            # probablement du WAV.
            extension = ".wav"

        fichier_sortie = os.path.join(
            _TEMP_AUDIO_DIR,
            f"reponse_{uuid.uuid4().hex[:8]}"
            f"{extension}"
        )

        # ----------------------------------------------------
        # Écriture directe
        # ----------------------------------------------------

        with open(
            fichier_sortie,
            "wb"
        ) as f:

            f.write(
                reponse.content
            )

        taille = os.path.getsize(
            fichier_sortie
        )

        if taille <= 0:

            raise RuntimeError(
                "Le serveur TTS a renvoyé "
                "un fichier vide."
            )

        log_event(
            "tts",
            f"Audio prêt : "
            f"{os.path.basename(fichier_sortie)} "
            f"({taille} bytes)"
        )

        return fichier_sortie

    except Exception as e:

        log_error(
            "tts",
            f"Erreur serveur audio : "
            f"{type(e).__name__}: {str(e)[:120]}",
            exc_info=False
        )

        print(
            "⚠️ Serveur TTS indisponible, "
            "utilisation de Kokoro local."
        )

        # ----------------------------------------------------
        # FALLBACK KOKORO
        # ----------------------------------------------------

        return generer_audio(
            texte,
            langue
        )
