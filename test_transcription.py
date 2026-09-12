from scipy.io.wavfile import read
from voix import transcrire_audio

print("🔊 Lecture de test_micro.wav...")

frequence, audio = read("test_micro.wav")

print(f"📊 Fréquence : {frequence} Hz")
print(f"📊 Durée : {len(audio) / frequence:.2f} secondes")

texte = transcrire_audio(audio)

print()
print("📝 TRANSCRIPTION :")
print(texte)