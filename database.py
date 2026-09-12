import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv
from datetime import datetime, timezone
from logging_jibi import log_event, log_warning, log_error

load_dotenv(override=True)

# ============================================================
# POOL DE CONNEXIONS (évite create/close répété = 50% plus rapide)
# ============================================================

_connection_pool = None

def _initialiser_pool():
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = pooling.MySQLConnectionPool(
            pool_name="jibi_pool",
            pool_size=5,  # Reuse 5 connections
            pool_reset_session=True,
            host=os.getenv("MYSQL_HOST", "localhost"),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "ma_base")
        )

def connecter():
    _initialiser_pool()
    return _connection_pool.get_connection()


def creer_tables():
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute("""
            CREATE TABLE IF NOT EXISTS memoire (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100),
                cle VARCHAR(100),
                valeur TEXT,
                UNIQUE KEY user_cle (user_id, cle)
            )
        """)

        # Colonne embedding pour la mémoire sémantique (recherche par sens,
        # pas seulement par clé exacte). ADD COLUMN échoue si elle existe
        # déjà : on l'ignore silencieusement dans ce cas précis.
        try:
            curseur.execute("ALTER TABLE memoire ADD COLUMN embedding LONGTEXT NULL")
            connexion.commit()
        except Exception:
            pass

        curseur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100),
                role VARCHAR(20),
                message TEXT,
                horodatage DATETIME
            )
        """)

        # Index composite : historique_conversation filtre par user_id ET
        # trie par horodatage à chaque message. Sans index, MySQL relit
        # toute la table (scan complet) et ça ralentit au fur et à mesure
        # que l'historique grossit. CREATE INDEX n'a pas de IF NOT EXISTS
        # portable ici : on ignore juste l'erreur "index déjà existant".
        try:
            curseur.execute(
                "CREATE INDEX idx_conversations_user_horodatage "
                "ON conversations (user_id, horodatage)"
            )
            connexion.commit()
        except mysql.connector.Error as e:
            if e.errno != 1061:  # 1061 = Duplicate key name (déjà créé)
                raise

        curseur.execute("""
            CREATE TABLE IF NOT EXISTS ngambay (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phrase_ngambay TEXT,
                traduction_fr TEXT,
                traduction_en TEXT,
                categorie VARCHAR(50),
                source VARCHAR(100) DEFAULT 'utilisateur',
                valide BOOLEAN DEFAULT FALSE,
                date_ajout DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index FULLTEXT : rechercher_ngambay fait un LIKE '%texte%' des
        # deux côtés, qui ne peut jamais utiliser d'index classique (le %
        # au début empêche ça) et scanne toute la table à chaque recherche.
        # Avec FULLTEXT + MATCH...AGAINST, la recherche reste rapide même
        # quand le vocabulaire grossit. rechercher_ngambay garde un repli
        # sur LIKE si jamais le moteur de stockage ne supporte pas FULLTEXT.
        try:
            curseur.execute(
                "CREATE FULLTEXT INDEX idx_ngambay_fulltext "
                "ON ngambay (phrase_ngambay, traduction_fr)"
            )
            connexion.commit()
        except mysql.connector.Error as e:
            if e.errno != 1061:
                log_warning("database", f"Index FULLTEXT ngambay non créé: {e}")

        connexion.commit()
    except Exception as e:
        print(f"Erreur création tables: {e}")
        log_error("database", f"Création tables échouée: {e}", exc_info=False)
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()
    
    log_event("database", "Tables initialisées")


def remember_memory_db(user_id, key, value):
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute("""
            INSERT INTO memoire (user_id, cle, valeur)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE valeur = %s
        """, (user_id, key, value, value))

        connexion.commit()
    except Exception as e:
        print(f"Erreur remember_memory_db: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()

    return f"Memory saved: {key}."


def recall_db(user_id, key):
    connexion = connecter()
    resultat = None
    try:
        curseur = connexion.cursor()

        curseur.execute(
            """
            SELECT valeur
            FROM memoire
            WHERE user_id = %s AND cle = %s
            """,
            (user_id, key)
        )

        resultat = curseur.fetchone()
    except Exception as e:
        print(f"Erreur recall_db: {e}")
    finally:
        curseur.close()
        connexion.close()

    if resultat is None:
        return "No information saved for this key."

    return resultat[0]


def sauvegarder_embedding(user_id, cle, embedding_json):
    """Attache un embedding (JSON, sous forme de texte) à un souvenir existant."""
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            "UPDATE memoire SET embedding = %s WHERE user_id = %s AND cle = %s",
            (embedding_json, user_id, cle)
        )

        connexion.commit()
    except Exception as e:
        print(f"Erreur sauvegarder_embedding: {e}")
        log_warning("database", f"sauvegarder_embedding échoué: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()


def obtenir_memoires_avec_embeddings(user_id):
    """Renvoie tous les souvenirs d'un utilisateur qui ont un embedding calculé."""
    connexion = connecter()
    resultats = []
    try:
        curseur = connexion.cursor()

        curseur.execute(
            """
            SELECT cle, valeur, embedding
            FROM memoire
            WHERE user_id = %s AND embedding IS NOT NULL
            """,
            (user_id,)
        )

        resultats = curseur.fetchall()
    except Exception as e:
        print(f"Erreur obtenir_memoires_avec_embeddings: {e}")
    finally:
        curseur.close()
        connexion.close()

    return resultats


def enregistrer_message(user_id, role, message):
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            """
            INSERT INTO conversations
            (user_id, role, message, horodatage)
            VALUES (%s, %s, %s, %s)
            """,
            (
                user_id,
                role,
                message,
                datetime.now(timezone.utc)
            )
        )

        connexion.commit()
    except Exception as e:
        print(f"Erreur enregistrer_message: {e}")
        log_error("database", f"Enregistrer message échoué: {e}", exc_info=False)
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()


def historique_conversation(user_id, limite=20, minutes_max=None):
    """
    Renvoie les derniers échanges d'un utilisateur.

    `minutes_max` (optionnel) limite en plus aux messages des N dernières
    minutes : sert à repartir sur un contexte propre après une pause,
    SANS jamais supprimer l'historique complet de la base (qui reste
    disponible en entier pour consultation ou analyse ultérieure — voir
    aussi historique_complet()).
    """
    connexion = connecter()
    resultats = []
    try:
        curseur = connexion.cursor()

        if minutes_max is not None:
            curseur.execute(
                """
                SELECT role, message
                FROM conversations
                WHERE user_id = %s
                  AND horodatage >= UTC_TIMESTAMP() - INTERVAL %s MINUTE
                ORDER BY horodatage DESC
                LIMIT %s
                """,
                (user_id, minutes_max, limite)
            )
        else:
            curseur.execute(
                """
                SELECT role, message
                FROM conversations
                WHERE user_id = %s
                ORDER BY horodatage DESC
                LIMIT %s
                """,
                (user_id, limite)
            )

        resultats = curseur.fetchall()
    except Exception as e:
        print(f"Erreur historique_conversation: {e}")
    finally:
        curseur.close()
        connexion.close()

    return list(reversed(resultats))


def historique_complet(user_id, limite=500):
    """
    Renvoie l'historique complet (ou jusqu'à `limite`), sans filtre de
    fraîcheur — pour consultation, export ou analyse, PAS pour être
    réinjecté tel quel dans le contexte d'Ollama (utiliser
    historique_conversation avec minutes_max pour ça).
    """
    return historique_conversation(user_id, limite=limite, minutes_max=None)


def ajouter_ngambay(phrase_ngambay, traduction_fr, traduction_en=None, categorie=None):
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            """
            INSERT INTO ngambay
            (phrase_ngambay, traduction_fr, traduction_en, categorie, source, valide)
            VALUES (%s, %s, %s, %s, 'utilisateur', FALSE)
            """,
            (phrase_ngambay, traduction_fr, traduction_en, categorie)
        )

        connexion.commit()
    except Exception as e:
        print(f"Erreur ajouter_ngambay: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()

    return "Phrase Ngambay enregistrée (à vérifier)."


def valider_ngambay(id_phrase):
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            "UPDATE ngambay SET valide = TRUE WHERE id = %s",
            (id_phrase,)
        )

        connexion.commit()
    except Exception as e:
        print(f"Erreur valider_ngambay: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()

    return f"Phrase {id_phrase} validée."


def corriger_ngambay(id_phrase, nouvelle_traduction_fr):
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            "UPDATE ngambay SET traduction_fr = %s, valide = FALSE WHERE id = %s",
            (nouvelle_traduction_fr, id_phrase)
        )

        connexion.commit()
    except Exception as e:
        print(f"Erreur corriger_ngambay: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()

    return f"Traduction {id_phrase} corrigée, à revalider."


def rechercher_ngambay(texte, limite=10):
    connexion = connecter()
    resultats = []
    try:
        curseur = connexion.cursor()

        # Recherche FULLTEXT en priorité (rapide, utilise l'index créé
        # dans creer_tables). Si l'index n'existe pas encore (ancienne
        # base pas encore migrée) ou si la requête échoue pour une autre
        # raison, on retombe sur l'ancien LIKE '%...%' pour ne jamais
        # casser la fonctionnalité.
        # Le mode BOOLEAN de MySQL donne un sens spécial à +, -, *, etc.
        # On les retire pour éviter une erreur de syntaxe sur une requête
        # utilisateur qui en contiendrait.
        import re as _re
        texte_nettoye = _re.sub(r'[+\-<>()~*"@]', ' ', texte).strip()

        try:
            if texte_nettoye:
                curseur.execute(
                    """
                    SELECT phrase_ngambay, traduction_fr
                    FROM ngambay
                    WHERE MATCH(phrase_ngambay, traduction_fr) AGAINST (%s IN BOOLEAN MODE)
                    LIMIT %s
                    """,
                    (f"{texte_nettoye}*", limite)
                )
                resultats = curseur.fetchall()
        except mysql.connector.Error:
            resultats = []

        if not resultats:
            recherche = f"%{texte}%"
            curseur.execute(
                """
                SELECT phrase_ngambay, traduction_fr
                FROM ngambay
                WHERE phrase_ngambay LIKE %s
                   OR traduction_fr LIKE %s
                LIMIT %s
                """,
                (recherche, recherche, limite)
            )
            resultats = curseur.fetchall()
    except Exception as e:
        print(f"Erreur rechercher_ngambay: {e}")
    finally:
        curseur.close()
        connexion.close()

    return resultats


def obtenir_vocabulaire_ngambay(limite=100):
    """
    Renvoie un échantillon du vocabulaire, PAS toute la table.

    Priorité aux entrées validées (plus fiables), puis aux plus récentes.
    Sans cette limite, un vocabulaire qui grossit finirait entièrement
    injecté dans le prompt système à chaque question Ngambay, ce qui
    ralentit le modèle et dilue le contexte utile. Pour une phrase
    précise, préférer rechercher_ngambay() qui cible la recherche.
    """
    connexion = connecter()
    resultats = []
    try:
        curseur = connexion.cursor()

        curseur.execute(
            """
            SELECT phrase_ngambay, traduction_fr
            FROM ngambay
            ORDER BY valide DESC, date_ajout DESC
            LIMIT %s
            """,
            (limite,)
        )

        resultats = curseur.fetchall()
    except Exception as e:
        print(f"Erreur obtenir_vocabulaire_ngambay: {e}")
    finally:
        curseur.close()
        connexion.close()

    return resultats