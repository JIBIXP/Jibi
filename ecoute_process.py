import io
import json
import os
import sys
import wave

import numpy as np

from voix import (
    FREQUENCE,
    ecouter_jusqua_silence,
    transcrire_audio
)

from logging_jibi import (
    log_event,
    log_warning
)


# ============================================================
# SERVEUR LOCAL
# ============================================================

URL_SERVEUR_MODELES = "http://127.0.0.1:8765"


# ============================================================
# MOT D'ACTIVATION (VEILLE)
# ============================================================

MOT_ACTIVATION = os.getenv("JIBI_MOT_ACTIVATION", "jibi").strip().lower()

# Sécurité anti-boucle infinie en mode veille : nombre max de cycles
# d'écoute sans détection avant d'abandonner (le GUI relance ensuite
# un nouveau processus veille s'il le souhaite toujours).
VEILLE_CYCLES_MAX = int(os.getenv("JIBI_VEILLE_CYCLES_MAX", "10000"))


def _contient_mot_activation(texte):
    return MOT_ACTIVATION in texte.lower()


def _extraire_commande(texte):
    """
    Retire le mot d'activation du texte transcrit et renvoie ce qui
    reste (la commande). Gère aussi les formes "Jibi," / "Dis Jibi".
    """

    import re

    nettoye = re.sub(
        rf"\bdis\s+{re.escape(MOT_ACTIVATION)}\b",
        "",
        texte,
        flags=re.IGNORECASE
    )

    nettoye = re.sub(
        rf"\b{re.escape(MOT_ACTIVATION)}\b",
        "",
        nettoye,
        flags=re.IGNORECASE
    )

    nettoye = nettoye.strip(" ,.!?:;-")

    return " ".join(nettoye.split())


# ============================================================
# AUDIO -> WAV
# ============================================================

def _audio_vers_wav_bytes(
    audio_np,
    frequence
):
    """
    Transforme un tableau audio numpy en WAV
    mono PCM 16 bits.
    """

    audio_np = np.asarray(
        audio_np,
        dtype=np.int16
    ).reshape(-1)

    tampon = io.BytesIO()

    with wave.open(
        tampon,
        "wb"
    ) as f:

        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(frequence)

        f.writeframes(
            audio_np.tobytes()
        )

    return tampon.getvalue()


# ============================================================
# TRANSCRIPTION
# ============================================================

def transcrire(audio_np):
    """
    Essaie d'abord le serveur Parakeet local.

    Si le serveur n'est pas disponible :
    -> utilise directement Parakeet dans ce processus.
    """

    if (
        audio_np is None
        or len(audio_np) == 0
    ):

        return (
            "",
            "fr"
        )

    try:

        import requests

        donnees_wav = (
            _audio_vers_wav_bytes(
                audio_np,
                FREQUENCE
            )
        )

        # ----------------------------------------------------
        # Serveur STT local
        # ----------------------------------------------------

        reponse = requests.post(

            f"{URL_SERVEUR_MODELES}/transcrire",

            files={
                "fichier": (
                    "audio.wav",
                    donnees_wav,
                    "audio/wav"
                )
            },

            # 20 s suffit largement pour une transcription
            # normale. Le fallback sera déclenché plus tôt.
            timeout=20
        )

        reponse.raise_for_status()

        data = reponse.json()

        texte = str(
            data.get(
                "texte",
                ""
            )
        ).strip()

        langue = str(
            data.get(
                "langue",
                "fr"
            )
        )

        log_event(
            "stt",
            f"Serveur : {texte[:80]}"
        )

        return (
            texte,
            langue
        )

    # ========================================================
    # SERVEUR ABSENT
    # ========================================================

    except requests.exceptions.ConnectionError:

        print(
            "⚠️ Serveur STT indisponible → "
            "Parakeet local"
        )

        log_warning(
            "stt",
            "Serveur indisponible, fallback local"
        )

        return transcrire_audio(
            audio_np
        )

    # ========================================================
    # SERVEUR TROP LENT
    # ========================================================

    except requests.exceptions.Timeout:

        print(
            "⚠️ Serveur STT trop lent → "
            "Parakeet local"
        )

        log_warning(
            "stt",
            "Serveur timeout, fallback local"
        )

        return transcrire_audio(
            audio_np
        )

    # ========================================================
    # AUTRE ERREUR
    # ========================================================

    except Exception as e:

        print(
            "⚠️ Erreur serveur STT "
            f"({type(e).__name__}) → "
            "Parakeet local"
        )

        log_warning(
            "stt",
            f"Serveur error ({type(e).__name__})"
        )

        return transcrire_audio(
            audio_np
        )


# ============================================================
# ENVOI JSON VERS GUI
# ============================================================

def envoyer_json(
    donnees
):
    """
    Envoie une ligne JSON au GUI.

    IMPORTANT :
    flush=True permet au GUI de recevoir
    immédiatement les informations.
    """

    print(
        json.dumps(
            donnees,
            ensure_ascii=False
        ),
        flush=True
    )


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

if __name__ == "__main__":

    MODE_VEILLE = "--veille" in sys.argv

    # --------------------------------------------------------
    # Niveau microphone
    # --------------------------------------------------------

    def envoyer_niveau(
        niveau
    ):

        envoyer_json(
            {
                "level": float(
                    niveau
                )
            }
        )

    # ============================================================
    # MODE VEILLE : boucle jusqu'au mot d'activation
    # ============================================================

    if MODE_VEILLE:

        envoyer_json(
            {
                "status": "veille",
                "mot_activation": MOT_ACTIVATION
            }
        )

        log_event(
            "veille",
            f"Démarrage veille (mot: '{MOT_ACTIVATION}')"
        )

        for _ in range(VEILLE_CYCLES_MAX):

            # Écoute courte : on ne veut pas bloquer 12s à chaque
            # cycle juste pour repérer un mot d'activation.
            audio = ecouter_jusqua_silence(
                silence_max_ms=700,
                sensibilite=2,
                duree_max_s=6,
                on_level=envoyer_niveau
            )

            if audio is None:
                continue

            texte, langue = transcrire(audio)
            texte = " ".join(str(texte or "").strip().split())

            if not texte:
                continue

            if not _contient_mot_activation(texte):
                # Pas le mot d'activation : on ignore et on
                # recommence à écouter, sans rien remonter au GUI.
                continue

            commande = _extraire_commande(texte)

            log_event(
                "veille",
                f"Mot d'activation détecté, commande: {commande[:60]!r}"
            )

            envoyer_json(
                {
                    "texte": commande,
                    "langue": langue or "fr",
                    "reveil": True
                }
            )

            break

        else:

            # VEILLE_CYCLES_MAX atteint sans détection : on remonte
            # un résultat vide, le GUI décide s'il relance la veille.
            envoyer_json(
                {
                    "texte": "",
                    "langue": "",
                    "reveil": True
                }
            )

    # ============================================================
    # MODE NORMAL : une seule écoute, comme avant
    # ============================================================

    else:

        # --------------------------------------------------------
        # Indique au GUI que l'écoute commence
        # --------------------------------------------------------

        envoyer_json(
            {
                "status": "ecoute"
            }
        )

        # --------------------------------------------------------
        # Écoute
        # --------------------------------------------------------

        audio = ecouter_jusqua_silence(

            # 900 ms maximum de silence
            # avant de considérer la phrase terminée
            silence_max_ms=900,

            # Sensibilité WebRTC
            sensibilite=2,

            # Sécurité : maximum 12 secondes
            duree_max_s=12,

            # Mise à jour du niveau microphone
            on_level=envoyer_niveau
        )

        # ========================================================
        # RIEN N'A ÉTÉ DÉTECTÉ
        # ========================================================

        if audio is None:

            envoyer_json(
                {
                    "texte": "",
                    "langue": ""
                }
            )

        # ========================================================
        # AUDIO DÉTECTÉ
        # ========================================================

        else:

            duree = (
                len(audio)
                / FREQUENCE
            )

            envoyer_json(
                {
                    "status": "transcription",
                    "duree": round(
                        duree,
                        2
                    )
                }
            )

            # ----------------------------------------------------
            # Transcription
            # ----------------------------------------------------

            texte, langue = transcrire(
                audio
            )

            # ----------------------------------------------------
            # Nettoyage final
            # ----------------------------------------------------

            texte = str(
                texte or ""
            ).strip()

            # Évite les espaces multiples
            texte = " ".join(
                texte.split()
            )

            langue = str(
                langue or "fr"
            ).strip()

            # ----------------------------------------------------
            # Résultat vers GUI
            # ----------------------------------------------------

            envoyer_json(
                {
                    "texte": texte,
                    "langue": langue
                }
            )