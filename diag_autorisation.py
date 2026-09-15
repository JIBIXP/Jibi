"""Diagnostic étape par étape de l'autorisation."""
import traceback
import sys
sys.path.insert(0, ".")

print("=" * 60)
print("DIAGNOSTIC AUTORISATION")
print("=" * 60)

PROP_ID = "d5d1aebd6ff4"

# AMÉLIORATION : on résout le chemin des propositions de la même façon que
# self_improvement/propositions.py (via PROJECT_ROOT), plutôt qu'avec un
# chemin relatif codé en dur ("workspace/jibi_lab/propositions"). Avant,
# lancer ce script depuis un autre répertoire que la racine du projet
# pouvait faire dire "fichier introuvable" à l'étape 1 alors que
# charger_proposition() (étape 2) le trouvait sans problème (ou l'inverse) —
# ce qui rendait le diagnostic trompeur.
try:
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent
    PROPOSITIONS_DIR = PROJECT_ROOT / "workspace" / "jibi_lab" / "propositions"
except Exception:
    from pathlib import Path
    PROPOSITIONS_DIR = Path("workspace/jibi_lab/propositions")

# Étape 1 : Le fichier JSON existe-t-il ?
print(f"\n[1] Vérification du fichier proposition...")
try:
    chemin = PROPOSITIONS_DIR / f"{PROP_ID}.json"
    if chemin.exists():
        print(f"    ✅ Fichier trouvé : {chemin}")
        contenu = chemin.read_text(encoding="utf-8")
        print(f"    Contenu ({len(contenu)} chars) :")
        print(f"    {contenu[:300]}")
    else:
        print(f"    ❌ Fichier INTROUVABLE : {chemin}")
        print("    → Il faut d'abord créer la proposition.")
        print(f"    → Vérifiez : {PROPOSITIONS_DIR}")
        # Lister ce qui existe
        if PROPOSITIONS_DIR.exists():
            fichiers = list(PROPOSITIONS_DIR.glob("*.json"))
            print(f"    Fichiers présents : {len(fichiers)}")
            for f in fichiers[:5]:
                print(f"      • {f.name}")
        else:
            print("    → Le dossier propositions/ n'existe pas !")
except Exception as e:
    print(f"    ❌ Erreur : {e}")
    traceback.print_exc()

# Étape 2 : charger_proposition
print(f"\n[2] charger_proposition('{PROP_ID}')...")
try:
    from self_improvement.propositions import charger_proposition
    prop = charger_proposition(PROP_ID)
    if prop:
        print(f"    ✅ Proposition chargée :")
        print(f"       id      = {prop.get('id')}")
        print(f"       fichier = {prop.get('fichier')}")
        print(f"       statut  = {prop.get('statut')}")
    else:
        print(f"    ❌ Proposition introuvable (retourne None)")
except Exception as e:
    print(f"    ❌ Erreur : {e}")
    traceback.print_exc()

# Étape 3 : autorisation_valide
print(f"\n[3] autorisation_valide('{PROP_ID}', \"J'AUTORISE {PROP_ID}\")...")
try:
    from self_improvement.autorisation import autorisation_valide
    result = autorisation_valide(PROP_ID, f"J'AUTORISE {PROP_ID}")
    print(f"    Résultat : {result}")
    if not result:
        print("    ❌ L'autorisation est refusée !")
        # AMÉLIORATION : la regex d'autorisation est déclarée avec
        # re.IGNORECASE dans autorisation.py — la casse de "J'AUTORISE"
        # n'a donc PAS d'importance. Seul l'id doit correspondre EXACTEMENT
        # (lui est sensible à la casse) et la phrase doit commencer par
        # J'AUTORISE suivi d'un espace puis de l'id.
        print("    → La casse de \"J'AUTORISE\" n'a pas d'importance (regex insensible à la casse).")
        print(f"    → Vérifiez surtout que l'id est EXACTEMENT : {PROP_ID}")
except Exception as e:
    print(f"    ❌ Erreur : {e}")
    traceback.print_exc()

# Étape 4 : valider_proposition
print(f"\n[4] valider_proposition(prop_id='{PROP_ID}', confirmation=...)...")
try:
    from self_improvement.autorisation import valider_proposition
    result = valider_proposition(
        prop_id=PROP_ID,
        confirmation=f"J'AUTORISE {PROP_ID}",
        commentaire="Test diagnostic"
    )
    print(f"    Résultat : {result}")

    # AMÉLIORATION : on relit la proposition sur disque pour confirmer que
    # le statut a été RÉELLEMENT persisté (et pas seulement que la fonction
    # a répondu "ok": True). C'est exactement le point qui était cassé
    # avant le correctif d'autorisation.py (marquer_validee() recevait
    # l'id en string au lieu de l'objet proposition, l'exception était
    # avalée en silence, et le statut restait bloqué sur "proposition").
    from self_improvement.propositions import charger_proposition
    prop_apres = charger_proposition(PROP_ID)
    statut_apres = prop_apres.get("statut") if prop_apres else None
    if statut_apres == "validee":
        print(f"    ✅ Statut persisté sur disque : '{statut_apres}'")
    else:
        print(f"    ⚠️  Statut sur disque après validation : '{statut_apres}' (attendu : 'validee')")
except Exception as e:
    print(f"    ❌ Erreur : {e}")
    traceback.print_exc()

# Étape 5 : autoriser_et_appliquer (le pipeline complet)
print(f"\n[5] autoriser_et_appliquer(...) [PIPELINE COMPLET]...")
try:
    from self_improvement.gestionnaire import autoriser_et_appliquer
    result = autoriser_et_appliquer(
        proposition_id=PROP_ID,
        confirmation=f"J'AUTORISE {PROP_ID}",
        commentaire="Test diagnostic"
    )
    print(f"    Résultat : {result}")

    # AMÉLIORATION : même vérification de persistance qu'à l'étape 4,
    # mais on s'attend cette fois à "appliquee" si le pipeline a réussi.
    from self_improvement.propositions import charger_proposition
    prop_finale = charger_proposition(PROP_ID)
    statut_final = prop_finale.get("statut") if prop_finale else None
    if result.get("succes") and statut_final == "appliquee":
        print(f"    ✅ Statut persisté sur disque : '{statut_final}'")
    elif result.get("succes"):
        print(f"    ⚠️  Pipeline signalé comme réussi mais statut sur disque = '{statut_final}' (attendu : 'appliquee')")
    else:
        print(f"    ℹ️  Statut sur disque : '{statut_final}' (pipeline non réussi, voir résultat ci-dessus)")
except Exception as e:
    print(f"    ❌ Erreur : {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("DIAGNOSTIC TERMINÉ")
print("=" * 60)