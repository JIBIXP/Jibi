def calculer_moyenne(nombres):
    if not nombres:
        return 0
    return sum(nombres) / len(nombres)

def formater_resultat(valeur):
    return f"Résultat : {valeur:.2f}"
