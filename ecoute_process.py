import sys
import json
import io
import wave
import requests

from voix import (
    FREQUENCE,
    ecouter_jusqua_silence,
    transcrire_audio
)


# ============================================================
# SERVEUR DE MODÈLES LOCAL
# ============================================================

URL_SERVEUR_MODELES = "http://127.0.0.1:8765"


# ============================================================
# COMMUNICATION AVEC LE GUI
# ============================================================

def envoyer(message):
    """
    Envoie un message JSON au GUI.
    """

    try:

        print(
            json.dumps(
                message,
                ensure_ascii=False
            ),
            flush=True
        )

    except Exception as e:

        print(
            json.dumps(
                {
                    "type": "erreur",
                    "message": str(e)
                },
                ensure_ascii=False
            ),
            flush=True
        )


# ============================================================
# AUDIO -> WAV
# ============================================================

def audio_en_wav(audio_np):
    """
    Convertit le tableau audio int16 en WAV
    directement en mémoire.
    """

    buffer = io.BytesIO()

    with wave.open(
        buffer,
        "wb"
    ) as wav:

        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(FREQUENCE)

        wav.writeframes(
            audio_np.tobytes()
        )

    buffer.seek(0)

    return buffer


# ============================================================
# TRANSCRIPTION
# ============================================================

def transcrire(audio_np):
    """
    Essaie d'abord le serveur local.

    Si le serveur n'est pas disponible,
    utilise Parakeet directement dans ce processus.
    """

    if audio_np is None:
        return "", "fr"

    wav_buffer = audio_en_wav(
        audio_np
    )

    try:

        reponse = requests.post(
            f"{URL_SERVEUR_MODELES}/transcrire",
            files={
                "fichier": (
                    "audio.wav",
                    wav_buffer,
                    "audio/wav"
                )
            },
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

        langue = data.get(
            "langue",
            "fr"
        )

        return texte, langue

    except requests.exceptions.ConnectionError:

        print(
            "⚠️ Serveur modèles indisponible."
            " Parakeet local utilisé.",
            flush=True
        )

        return transcrire_audio(
            audio_np
        )

    except requests.exceptions.Timeout:

        print(
            "⚠️ Timeout serveur."
            " Parakeet local utilisé.",
            flush=True
        )

        return transcrire_audio(
            audio_np
        )

    except Exception as e:

        print(
            f"⚠️ Erreur serveur : {e}. "
            "Parakeet local utilisé.",
            flush=True
        )

        return transcrire_audio(
            audio_np
        )


# ============================================================
# ÉCOUTE NORMALE
# ============================================================

def ecouter_normal():

    envoyer(
        {
            "type": "ecoute",
            "etat": "active"
        }
    )

    audio = ecouter_jusqua_silence(
        silence_max_ms=900,
        sensibilite=2,
        duree_max_s=12
    )

    if audio is None:

        envoyer(
            {
                "type": "transcription",
                "texte": "",
                "langue": "fr"
            }
        )

        envoyer(
            {
                "type": "ecoute",
                "etat": "terminee"
            }
        )

        return

    texte, langue = transcrire(
        audio
    )

    envoyer(
        {
            "type": "transcription",
            "texte": texte,
            "langue": langue
        }
    )

    envoyer(
        {
            "type": "ecoute",
            "etat": "terminee"
        }
    )


# ============================================================
# MODE VEILLE
# ============================================================

def ecouter_veille():

    envoyer(
        {
            "type": "ecoute",
            "etat": "veille"
        }
    )

    audio = ecouter_jusqua_silence(
        silence_max_ms=700,
        sensibilite=2,
        duree_max_s=6
    )

    if audio is None:

        envoyer(
            {
                "type": "veille",
                "texte": "",
                "langue": "fr"
            }
        )

        return

    texte, langue = transcrire(
        audio
    )

    envoyer(
        {
            "type": "veille",
            "texte": texte,
            "langue": langue
        }
    )


# ============================================================
# NIVEAU MICRO
# ============================================================

def ecouter_niveau():

    envoyer(
        {
            "type": "ecoute",
            "etat": "active"
        }
    )

    def on_level(niveau):

        envoyer(
            {
                "type": "niveau",
                "valeur": niveau
            }
        )

    audio = ecouter_jusqua_silence(
        silence_max_ms=900,
        sensibilite=2,
        duree_max_s=12,
        on_level=on_level
    )

    if audio is None:

        envoyer(
            {
                "type": "transcription",
                "texte": "",
                "langue": "fr"
            }
        )

        envoyer(
            {
                "type": "ecoute",
                "etat": "terminee"
            }
        )

        return

    texte, langue = transcrire(
        audio
    )

    envoyer(
        {
            "type": "transcription",
            "texte": texte,
            "langue": langue
        }
    )

    envoyer(
        {
            "type": "ecoute",
            "etat": "terminee"
        }
    )


# ============================================================
# BOUCLE PRINCIPALE
# ============================================================

def main():

    if len(sys.argv) < 2:

        envoyer(
            {
                "type": "erreur",
                "message": (
                    "Mode d'écoute manquant."
                )
            }
        )

        return

    mode = sys.argv[1].lower()

    if mode == "veille":

        ecouter_veille()

    elif mode == "niveau":

        ecouter_niveau()

    else:

        ecouter_normal()


# ============================================================
# LANCEMENT
# ============================================================

if __name__ == "__main__":
    main()