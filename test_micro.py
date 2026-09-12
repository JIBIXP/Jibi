import sounddevice as sd
from scipy.io.wavfile import write

FREQUENCE = 16000
DUREE = 5

print("🎤 Parle pendant 5 secondes...")

audio = sd.rec(
    int(DUREE * FREQUENCE),
    samplerate=FREQUENCE,
    channels=1,
    dtype="int16"
)

sd.wait()

write("test_micro.wav", FREQUENCE, audio)

print("✅ Enregistrement terminé !")
print("📁 Fichier créé : test_micro.wav")