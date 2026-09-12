"""
ingest.py
=========

Script en ligne de commande pour remplir la base de connaissances de JIBI
sans avoir à écrire du code à chaque fois.

Usage :
    python ingest.py mes_cours/                    # ingère un dossier entier
    python ingest.py mes_cours/ --categorie cours   # avec une catégorie
    python ingest.py --stats                        # voir ce qui est déjà dedans
"""

import argparse
import connaissances


def main():
    parser = argparse.ArgumentParser(description="Ingestion de documents dans la base de connaissances JIBI")
    parser.add_argument("dossier", nargs="?", help="Dossier à ingérer (.txt, .md, .pdf, sous-dossiers inclus)")
    parser.add_argument("--categorie", default="general", help="Étiquette libre, ex: cours, notes, projet")
    parser.add_argument("--non-recursif", action="store_true", help="Ne pas descendre dans les sous-dossiers")
    parser.add_argument("--stats", action="store_true", help="Afficher ce qui est déjà dans la base, sans rien ingérer")
    args = parser.parse_args()

    if args.stats or not args.dossier:
        stats = connaissances.statistiques()
        print(f"\n{stats['morceaux']} morceau(x) en base, depuis {len(stats['sources'])} fichier(s) :")
        for source in stats["sources"]:
            print(f"  - {source}")
        if not args.dossier:
            print("\n(passe un dossier en argument pour ingérer de nouveaux fichiers)")
        return

    print(f"Ingestion de '{args.dossier}' (catégorie: {args.categorie})...\n")
    total = connaissances.ingerer_dossier(
        args.dossier,
        categorie=args.categorie,
        recursif=not args.non_recursif,
    )
    print(f"\nTerminé : {total} nouveau(x) morceau(x) ajouté(s).")


if __name__ == "__main__":
    main()