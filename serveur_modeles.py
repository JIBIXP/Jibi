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
"""

import io
import wave
import time

import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from voix import (
    FREQUENCE,
    generer_audio,
    get_modele_parakeet,
    transcrire_audio,
)


app = FastAPI(title="JIBI - Serveur modèles")


@app.get("/health")
def health_check():
    """Endpoint de vérification que le serveur est prêt."""
    return {
        "status": "ok",
        "message": "Serveur modèles actif et prêt"
    }


@app.on_event("startup")
def charger_modeles():

    print("▶ Chargement des modèles (Parakeet + Kokoro)...")

    try:
        get_modele_parakeet()
        print("  ✓ Parakeet chargé")
    except Exception as e:
        print(f"  ❌ Parakeet échoué: {e}")

    # Précharge la voix française de Kokoro (la plus utilisée).
    from voix import _obtenir_pipeline_kokoro
    try:
        _obtenir_pipeline_kokoro("f")
        print("  ✓ Kokoro français chargé")
    except Exception as e:
        print(f"  ⚠️ Kokoro français non préchargé ({type(e).__name__}), se chargera à la demande.")

    print("✓ Serveur en écoute sur http://127.0.0.1:8765")


@app.post("/transcrire")
async def route_transcrire(fichier: UploadFile = File(...)):
    """Transcrit un fichier audio WAV."""
    try:
        debut = time.perf_counter()
        donnees = await fichier.read()

        if not donnees:
            raise HTTPException(
                status_code=400,
                detail="Fichier audio vide"
            )

        with wave.open(io.BytesIO(donnees), "rb") as f:
            trames = f.readframes(f.getnframes())

        audio_np = np.frombuffer(
            trames,
            dtype=np.int16
        ).copy()

        if audio_np.size == 0:
            raise HTTPException(
                status_code=400,
                detail="Audio WAV vide"
            )

        duree = audio_np.size / FREQUENCE
        print(f"🎤 /transcrire : {duree:.2f}s reçues")

        texte, langue = transcrire_audio(audio_np)

        temps = time.perf_counter() - debut
        print(
            f"✓ Transcription en {temps:.2f}s : "
            f"{texte!r}"
        )

        return {
            "texte": texte,
            "langue": langue
        }
    except Exception as e:
        print(f"❌ Erreur transcription: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur transcription: {str(e)[:100]}"
        )


@app.post("/synthetiser")
def route_synthetiser(
    texte: str = Form(...),
    langue: str = Form("fr")
):
    """Génère l'audio d'un texte."""
    try:
        chemin = generer_audio(texte, langue)

        if not chemin:
            raise HTTPException(
                status_code=500,
                detail="Synthèse audio échouée (Kokoro)"
            )

        media_type = (
            "audio/wav"
            if chemin.endswith(".wav")
            else "audio/mpeg"
        )

        return FileResponse(chemin, media_type=media_type)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erreur synthèse: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur synthèse: {str(e)[:100]}"
        )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)