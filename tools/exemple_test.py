def calculer_moyenne(nombres):
    """
    Calcule la moyenne d'une liste de nombres.

    :param nombres: Liste de nombres pour lesquels calculer la moyenne.
    :type nombres: list of float
    :return: La moyenne des nombres.
    :rtype: float
    """
    if not nombres:
        return 0
    return sum(nombres) / len(nombres)

def formater_resultat(valeur):
    """
    Formate une valeur en une chaîne de caractères avec deux décimales.

    :param valeur: La valeur à formater.
    :type valeur: float
    :return: La chaîne de caractères formatée.
    :rtype: str
    """
    return f"Résultat : {valeur:.2f}"
