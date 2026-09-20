"""
Outils mémoire de JIBI (faits durables + historique court terme).

Backend : memoire_locale.py (SQLite, zéro configuration).
"""
import memoire_locale as _mem


def remember(cle, valeur):
    """Mémorise durablement un fait sur l'utilisateur (ex: cle='prenom', valeur='Ulriche')."""
    r = _mem.remember(str(cle or ""), str(valeur or ""))
    if r.get("ok"):
        return f"✓ Mémorisé : {r['cle']}"
    return f"❌ {r.get('message', 'Échec')}"


def recall(cle):
    """Relit un fait mémorisé."""
    v = _mem.recall(str(cle or ""))
    return v if v is not None else f"(aucun souvenir pour '{cle}')"


def oublier(cle):
    """Oublie un fait mémorisé."""
    r = _mem.oublier(str(cle or ""))
    return f"✓ Oublié : {r['cle']}" if r.get("ok") else f"(rien à oublier pour '{cle}')"


def lister_memoires(limite=20):
    """Liste les faits mémorisés."""
    try:
        limite = max(1, min(int(limite), 100))
    except (TypeError, ValueError):
        limite = 20
    faits = _mem.lister_faits(limite)
    if not faits:
        return "Aucun souvenir pour l'instant."
    return "\n".join(f"• {f['cle']} : {f['valeur'][:150]}" for f in faits)


def historique_conversation(limite=10):
    """Relit les derniers échanges (contexte court terme)."""
    try:
        limite = max(1, min(int(limite), 50))
    except (TypeError, ValueError):
        limite = 10
    tours = _mem.historique(limite)
    if not tours:
        return "Historique vide."
    return "\n".join(f"[{t['role']}] {t['message'][:300]}" for t in tours)