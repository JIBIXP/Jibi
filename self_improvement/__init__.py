"""
Système d'auto-amélioration contrôlée de JIBI — PATCHÉ v2
- Branché config + cache + timings
"""
__version__ = "2.0.0"
__auteur__ = "JIBI"

def diagnostic_global():
    import time
    t0 = time.perf_counter()
    try:
        from self_improvement.analyseur import analyser_logs
        from self_improvement.laboratoire import initialiser_laboratoire, compter_sessions
        from self_improvement.versions import compter_backups
        analyse = analyser_logs()
        nb_erreurs = analyse.get("nombre_erreurs", 0)
        types = analyse.get("types", {})
        nb_sessions = compter_sessions()
        nb_backups = compter_backups()
        lab = initialiser_laboratoire()
        lignes = [
            "🩺 DIAGNOSTIC SELF_IMPROVEMENT",
            "=" * 40,
            f"  Version : {__version__}",
            f"  Erreurs dans les logs : {nb_erreurs}",
        ]
        if types:
            for categorie, nombre in types.items():
                if nombre > 0:
                    lignes.append(f"    • {categorie} : {nombre}")
        lignes.extend([
            f"  Sessions laboratoire : {nb_sessions}",
            f"  Sauvegardes : {nb_backups}",
            f"  Laboratoire : {lab}",
            f"  Durée : {time.perf_counter()-t0:.3f}s",
            "=" * 40,
        ])
        if nb_erreurs == 0:
            lignes.append("✅ Aucun problème détecté.")
        elif nb_erreurs < 10:
            lignes.append("⚠️  Quelques erreurs à examiner.")
        else:
            lignes.append("🔴 Nombreuses erreurs détectées.")
        return "\n".join(lignes)
    except Exception as e:
        return f"❌ Erreur de diagnostic : {e}"