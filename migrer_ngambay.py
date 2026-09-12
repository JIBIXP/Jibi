"""
Migration : ajoute les nouvelles colonnes à la table ngambay existante,
sans dépendre du client en ligne de commande mysql (utilise la même
librairie mysql-connector-python que le reste de JIBI).

Utilisation :
    python migrer_ngambay.py

À lancer une seule fois. Si une colonne existe déjà, le script
l'ignore et passe à la suivante (pas besoin de savoir lesquelles
manquent).
"""

import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv(override=True)

# --- DEBUG TEMPORAIRE : à retirer une fois le problème résolu ---
_pwd = os.getenv("MYSQL_PASSWORD", "")
print(f"DEBUG -> host={os.getenv('MYSQL_HOST')!r} user={os.getenv('MYSQL_USER')!r} "
      f"password={_pwd[:2]}***{_pwd[-2:] if len(_pwd) > 2 else ''} (longueur={len(_pwd)}) "
      f"db={os.getenv('MYSQL_DATABASE')!r}")
# --- FIN DEBUG ---

connexion = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST", "localhost"),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", ""),
    database=os.getenv("MYSQL_DATABASE", "ma_base")
)

curseur = connexion.cursor()

colonnes_a_ajouter = [
    ("traduction_en", "TEXT"),
    ("categorie", "VARCHAR(50)"),
    ("source", "VARCHAR(100) DEFAULT 'utilisateur'"),
    ("valide", "BOOLEAN DEFAULT FALSE"),
    ("date_ajout", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
]

for nom_colonne, definition in colonnes_a_ajouter:
    try:
        curseur.execute(
            f"ALTER TABLE ngambay ADD COLUMN {nom_colonne} {definition}"
        )
        connexion.commit()
        print(f"✅ Colonne ajoutée : {nom_colonne}")
    except mysql.connector.Error as e:
        if e.errno == 1060:  # Duplicate column name
            print(f"↷ Déjà présente, ignorée : {nom_colonne}")
        else:
            print(f"❌ Erreur sur {nom_colonne} : {e}")

curseur.close()
connexion.close()

print("\nMigration terminée.")