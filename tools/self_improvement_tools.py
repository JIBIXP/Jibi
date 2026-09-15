"""
Outils d'auto-amélioration pour JIBI.
Wrappers autour du module self_improvement pour l'utilisation via function-calling.
"""

from self_improvement.gestionnaire import (
    analyser_jibi,
    tableau_de_bord,
    preparer_amelioration as preparer_amelioration_core
)


def analyser_sante_jibi(limite_logs=1000, depuis_heures=24):
    """
    Analyse la santé de JIBI.
    
    Args:
        limite_logs: Nombre de lignes de logs à analyser
        depuis_heures: Analyser les logs des N dernières heures
        
    Returns:
        dict: Résultat de l'analyse
    """
    try:
        resultats = analyser_jibi(
            limite_logs=limite_logs,
            depuis_heures=depuis_heures
        )
        
        return {
            "succes": True,
            "score_sante": resultats['score_sante'],
            "etat": resultats['etat'],
            "erreurs": len(resultats['erreurs']),
            "warnings": len(resultats['warnings']),
            "patterns_recurrents": len(resultats['patterns_recurrents']),
            "logs_analyses": resultats['logs_analyses'],
            "recommandations": resultats['recommandations']
        }
        
    except Exception as e:
        return {
            "succes": False,
            "erreur": str(e)
        }


def tableau_bord_amelioration():
    """
    Affiche le tableau de bord d'auto-amélioration.
    
    Returns:
        dict: Statistiques complètes
    """
    try:
        resultats = tableau_de_bord()
        
        return {
            "succes": True,
            "propositions": resultats['propositions'],
            "sessions": resultats['sessions'],
            "backups": resultats['backups'],
            "sante": resultats.get('sante'),
            "recommandations": resultats['recommandations']
        }
        
    except Exception as e:
        return {
            "succes": False,
            "erreur": str(e)
        }


def preparer_amelioration(
    fichier,
    probleme,
    solution,
    justification,
    priorite="moyenne"
):
    """
    Prépare une amélioration avec génération de code.
    
    IMPORTANT : Cette fonction NE modifie JAMAIS le code directement.
    Elle prépare seulement une proposition pour validation humaine.
    
    Args:
        fichier: Fichier à améliorer
        probleme: Description du problème
        solution: Description de la solution
        justification: Justification de l'amélioration
        priorite: Priorité (haute/moyenne/basse)
        
    Returns:
        dict: Résultat de la préparation
    """
    try:
        resultats = preparer_amelioration_core(
            fichier=fichier,
            probleme=probleme,
            solution=solution,
            justification=justification,
            priorite=priorite
        )
        
        return {
            "succes": True,
            "proposition_id": resultats['proposition']['id'],
            "pret_pour_application": resultats['pret_pour_application'],
            "raisons_blocage": resultats.get('raisons_blocage', []),
            "validation": resultats.get('validation', {}),
            "tests": resultats.get('tests', {}),
            "message": (
                "Amélioration prête pour validation humaine"
                if resultats['pret_pour_application']
                else "Amélioration non applicable automatiquement"
            )
        }
        
    except Exception as e:
        return {
            "succes": False,
            "erreur": str(e)
        }