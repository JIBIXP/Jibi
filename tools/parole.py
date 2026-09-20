"""
Outil voix de JIBI (synthèse vocale).

Branche le module voix.py (jusqu'ici orphelin : importé par personne dans
l'application) comme un outil appelable depuis le chat.
"""
import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*a, **kw):
        return False

load_dotenv(override=True)


def _voix():
    try:
        import voix as _v
        return _v
    except Exception as e:
        raise RuntimeError(f"Module voix indisponible : {e}")


def dire(texte, async_mode=True):
    """Lit un texte à voix haute (TTS)."""
    texte = (texte or "").strip()
    if not texte:
        return "❌ Rien à dire (texte vide)."
    if os.getenv("TTS_ACTIVE", "1") != "1":
        return "🔇 Voix désactivée (TTS_ACTIVE=0 dans .env)."
    v = _voix()
    ok = v.parler(texte[:1000], async_mode=bool(async_mode))
    return "🔊 Lecture vocale lancée." if ok else "❌ Échec de la synthèse vocale."


def arreter_voix():
    """Stoppe la lecture vocale en cours."""
    v = _voix()
    try:
        v.arreter_parole()
        return "🔇 Voix stoppée."
    except Exception as e:
        return f"❌ {e}"