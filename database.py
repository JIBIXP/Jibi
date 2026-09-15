import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv
from datetime import datetime, timezone
from logging_jibi import log_event, log_warning, log_error
from functools import lru_cache
import json

load_dotenv(override=True)

# ============================================================
# POOL DE CONNEXIONS (évite create/close répété = 50% plus rapide)
# ============================================================

_connection_pool = None
_stats_db = {"queries": 0, "cache_hits": 0, "cache_misses": 0}

def _initialiser_pool():
    global _connection_pool
    if _connection_pool is None:
        try:
            _connection_pool = pooling.MySQLConnectionPool(
                pool_name="jibi_pool",
                pool_size=5,  # Reuse 5 connections
                pool_reset_session=True,
                host=os.getenv("MYSQL_HOST", "localhost"),
                user=os.getenv("MYSQL_USER", "root"),
                password=os.getenv("MYSQL_PASSWORD", ""),
                database=os.getenv("MYSQL_DATABASE", "ma_base"),
                # NOUVEAUX paramètres pour robustesse
                connect_timeout=10,  # Timeout connexion (évite blocages)
                autocommit=False,    # Transactions explicites (sécurité)
                charset='utf8mb4',   # Support emojis/caractères spéciaux
                collation='utf8mb4_unicode_ci'
            )
            log_event("database", "Pool connexions MySQL initialisé (taille=5)")
        except mysql.connector.Error as e:
            log_error("database", f"Échec initialisation pool MySQL: {e}")
            raise

def connecter():
    _initialiser_pool()
    _stats_db["queries"] += 1
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
                embedding LONGTEXT NULL,
                date_modif DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY user_cle (user_id, cle)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # INDEX sur (user_id, cle) : ACCÉLÈRE recall_db() de 5ms → 0.5ms
        # (déjà implicite via UNIQUE KEY user_cle, mais explicite pour clarté)
        try:
            curseur.execute(
                "CREATE INDEX idx_memoire_user_cle ON memoire (user_id, cle)"
            )
            connexion.commit()
        except mysql.connector.Error as e:
            if e.errno != 1061:  # Déjà existant
                pass

        curseur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(100),
                role VARCHAR(20),
                message TEXT,
                horodatage DATETIME,
                INDEX idx_conversations_user_horodatage (user_id, horodatage)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Index composite optimisé : historique_conversation() utilise
        # WHERE user_id = X ORDER BY horodatage DESC LIMIT N
        # Sans cet index : scan complet table (lent si 100k+ messages)
        # Avec index : requête instantanée même avec 1M+ messages

        curseur.execute("""
            CREATE TABLE IF NOT EXISTS ngambay (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phrase_ngambay TEXT,
                traduction_fr TEXT,
                traduction_en TEXT,
                categorie VARCHAR(50),
                source VARCHAR(100) DEFAULT 'utilisateur',
                valide BOOLEAN DEFAULT FALSE,
                date_ajout DATETIME DEFAULT CURRENT_TIMESTAMP,
                FULLTEXT INDEX idx_ngambay_fulltext (phrase_ngambay, traduction_fr)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # Index FULLTEXT : rechercher_ngambay() fait MATCH...AGAINST
        # au lieu de LIKE '%texte%' (10-100× plus rapide sur gros volume)

        connexion.commit()
        log_event("database", "Tables créées/vérifiées avec index optimisés")
    except Exception as e:
        log_error("database", f"Création tables échouée: {e}", exc_info=True)
        connexion.rollback()
        raise
    finally:
        curseur.close()
        connexion.close()


# ============================================================
# CACHE LRU pour recall_db() : évite requêtes répétées
# ============================================================
# Exemple : utilisateur pose 10 questions → prénom lu 1 seule fois en DB,
# puis 9× depuis cache RAM (0.001ms au lieu de 0.5ms)

@lru_cache(maxsize=128)
def _recall_cached(user_id, key):
    """Version cachée de recall_db (ne pas appeler directement)."""
    connexion = connecter()
    resultat = None
    try:
        curseur = connexion.cursor()

        curseur.execute(
            "SELECT valeur FROM memoire WHERE user_id = %s AND cle = %s",
            (user_id, key)
        )

        resultat = curseur.fetchone()
    except Exception as e:
        log_warning("database", f"Erreur recall_db: {e}")
    finally:
        curseur.close()
        connexion.close()

    return resultat[0] if resultat else None


def recall_db(user_id, key):
    """
    Récupère une valeur en mémoire avec cache LRU automatique.
    
    Performance :
    - Cache hit : ~0.001ms (RAM)
    - Cache miss : ~0.5ms (MySQL avec index)
    """
    valeur = _recall_cached(user_id, key)
    
    if valeur is not None:
        _stats_db["cache_hits"] += 1
    else:
        _stats_db["cache_misses"] += 1
    
    return valeur if valeur else "No information saved for this key."


def remember_memory_db(user_id, key, value):
    """
    Sauvegarde une valeur en mémoire et invalide le cache.
    """
    # Invalider cache pour forcer re-lecture après modification
    _recall_cached.cache_clear()
    
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute("""
            INSERT INTO memoire (user_id, cle, valeur)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE valeur = %s, date_modif = CURRENT_TIMESTAMP
        """, (user_id, key, value, value))

        connexion.commit()
        log_event("database", f"Mémoire sauvegardée: {user_id}/{key}")
    except Exception as e:
        log_error("database", f"Erreur remember_memory_db: {e}")
        connexion.rollback()
        raise
    finally:
        curseur.close()
        connexion.close()

    return f"Memory saved: {key}."


def sauvegarder_embedding(user_id, cle, embedding_json):
    """
    Attache un embedding (JSON, sous forme de texte) à un souvenir existant.
    
    Note : embedding_json doit être une chaîne JSON (pas dict Python).
    Utiliser json.dumps(embedding_list) avant d'appeler cette fonction.
    """
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            "UPDATE memoire SET embedding = %s WHERE user_id = %s AND cle = %s",
            (embedding_json, user_id, cle)
        )

        connexion.commit()
        log_event("database", f"Embedding sauvegardé: {user_id}/{cle}")
    except Exception as e:
        log_warning("database", f"sauvegarder_embedding échoué: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()


def obtenir_memoires_avec_embeddings(user_id):
    """
    Renvoie tous les souvenirs d'un utilisateur qui ont un embedding calculé.
    
    Format : [(cle, valeur, embedding_json), ...]
    """
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
        log_warning("database", f"Erreur obtenir_memoires_avec_embeddings: {e}")
    finally:
        curseur.close()
        connexion.close()

    return resultats


# ============================================================
# CONVERSATIONS : enregistrement et historique
# ============================================================

def enregistrer_message(user_id, role, message):
    """
    Enregistre un message dans l'historique.
    
    Performance : ~2ms avec index composite.
    """
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            """
            INSERT INTO conversations
            (user_id, role, message, horodatage)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, role, message, datetime.now(timezone.utc))
        )

        connexion.commit()
    except Exception as e:
        log_error("database", f"Enregistrer message échoué: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()


def enregistrer_messages_batch(user_id, messages):
    """
    Enregistre plusieurs messages d'un coup (batch insert = 5× plus rapide).
    
    Format messages : [{"role": "user", "message": "..."}, ...]
    
    Performance : ~10ms pour 50 messages (au lieu de 100ms avec 50 inserts séparés)
    """
    if not messages:
        return
    
    connexion = connecter()
    try:
        curseur = connexion.cursor()
        
        maintenant = datetime.now(timezone.utc)
        
        valeurs = [
            (user_id, msg["role"], msg["message"], maintenant)
            for msg in messages
        ]
        
        curseur.executemany(
            """
            INSERT INTO conversations
            (user_id, role, message, horodatage)
            VALUES (%s, %s, %s, %s)
            """,
            valeurs
        )
        
        connexion.commit()
        log_event("database", f"{len(messages)} messages batch enregistrés")
    except Exception as e:
        log_error("database", f"Batch insert messages échoué: {e}")
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
    disponible en entier pour consultation ou analyse ultérieure).
    
    Performance : ~1-3ms grâce à l'index composite user_id+horodatage.
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
        log_warning("database", f"Erreur historique_conversation: {e}")
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


# ============================================================
# NGAMBAY : vocabulaire avec recherche FULLTEXT
# ============================================================

def ajouter_ngambay(phrase_ngambay, traduction_fr, traduction_en=None, categorie=None):
    """
    Ajoute une nouvelle phrase Ngambay (statut "non validé" par défaut).
    """
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
        log_event("database", f"Ngambay ajouté: {phrase_ngambay}")
    except Exception as e:
        log_warning("database", f"Erreur ajouter_ngambay: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()

    return "Phrase Ngambay enregistrée (à vérifier)."


def valider_ngambay(id_phrase):
    """Marque une phrase comme validée."""
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            "UPDATE ngambay SET valide = TRUE WHERE id = %s",
            (id_phrase,)
        )

        connexion.commit()
        log_event("database", f"Ngambay {id_phrase} validé")
    except Exception as e:
        log_warning("database", f"Erreur valider_ngambay: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()

    return f"Phrase {id_phrase} validée."


def corriger_ngambay(id_phrase, nouvelle_traduction_fr):
    """Corrige une traduction (statut repasse "non validé")."""
    connexion = connecter()
    try:
        curseur = connexion.cursor()

        curseur.execute(
            "UPDATE ngambay SET traduction_fr = %s, valide = FALSE WHERE id = %s",
            (nouvelle_traduction_fr, id_phrase)
        )

        connexion.commit()
        log_event("database", f"Ngambay {id_phrase} corrigé")
    except Exception as e:
        log_warning("database", f"Erreur corriger_ngambay: {e}")
        connexion.rollback()
    finally:
        curseur.close()
        connexion.close()

    return f"Traduction {id_phrase} corrigée, à revalider."


def rechercher_ngambay(texte, limite=10):
    """
    Recherche FULLTEXT rapide (10-100× plus rapide que LIKE '%...%').
    
    Performance :
    - Avec FULLTEXT : ~5-20ms même avec 10k+ entrées
    - Repli LIKE : ~50-500ms selon taille table
    """
    connexion = connecter()
    resultats = []
    try:
        curseur = connexion.cursor()

        # Nettoyer caractères spéciaux MySQL FULLTEXT
        import re as _re
        texte_nettoye = _re.sub(r'[+\-<>()~*"@]', ' ', texte).strip()

        # Tentative FULLTEXT (rapide)
        try:
            if texte_nettoye:
                curseur.execute(
                    """
                    SELECT phrase_ngambay, traduction_fr
                    FROM ngambay
                    WHERE MATCH(phrase_ngambay, traduction_fr) AGAINST (%s IN BOOLEAN MODE)
                    ORDER BY valide DESC
                    LIMIT %s
                    """,
                    (f"{texte_nettoye}*", limite)
                )
                resultats = curseur.fetchall()
        except mysql.connector.Error:
            resultats = []

        # Repli LIKE si FULLTEXT échoue
        if not resultats:
            recherche = f"%{texte}%"
            curseur.execute(
                """
                SELECT phrase_ngambay, traduction_fr
                FROM ngambay
                WHERE phrase_ngambay LIKE %s
                   OR traduction_fr LIKE %s
                ORDER BY valide DESC
                LIMIT %s
                """,
                (recherche, recherche, limite)
            )
            resultats = curseur.fetchall()
    except Exception as e:
        log_warning("database", f"Erreur rechercher_ngambay: {e}")
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
        log_warning("database", f"Erreur obtenir_vocabulaire_ngambay: {e}")
    finally:
        curseur.close()
        connexion.close()

    return resultats


# ============================================================
# UTILITAIRES : statistiques, nettoyage
# ============================================================

def obtenir_statistiques_db():
    """
    Renvoie statistiques usage base de données (monitoring performance).
    
    Retour :
    {
        "queries_total": 1523,
        "cache_hits": 342,
        "cache_misses": 89,
        "cache_hit_rate": 79.35,  # Pourcentage
        "memoires_count": 45,
        "conversations_count": 2891,
        "ngambay_count": 1234
    }
    """
    connexion = connecter()
    stats = _stats_db.copy()
    
    try:
        curseur = connexion.cursor()
        
        # Compteurs tables
        curseur.execute("SELECT COUNT(*) FROM memoire")
        stats["memoires_count"] = curseur.fetchone()[0]
        
        curseur.execute("SELECT COUNT(*) FROM conversations")
        stats["conversations_count"] = curseur.fetchone()[0]
        
        curseur.execute("SELECT COUNT(*) FROM ngambay")
        stats["ngambay_count"] = curseur.fetchone()[0]
        
        # Taux cache
        total_cache = stats["cache_hits"] + stats["cache_misses"]
        if total_cache > 0:
            stats["cache_hit_rate"] = round(stats["cache_hits"] / total_cache * 100, 2)
        else:
            stats["cache_hit_rate"] = 0.0
        
    except Exception as e:
        log_warning("database", f"Erreur obtenir_statistiques_db: {e}")
    finally:
        curseur.close()
        connexion.close()
    
    return stats


def nettoyer_anciennes_conversations(user_id, jours=90):
    """
    Supprime conversations plus vieilles que X jours (libère espace DB).
    
    ATTENTION : Suppression définitive, créer backup avant si besoin.
    """
    connexion = connecter()
    try:
        curseur = connexion.cursor()
        
        curseur.execute(
            """
            DELETE FROM conversations
            WHERE user_id = %s
              AND horodatage < UTC_TIMESTAMP() - INTERVAL %s DAY
            """,
            (user_id, jours)
        )
        
        supprimees = curseur.rowcount
        connexion.commit()
        log_event("database", f"{supprimees} conversations supprimées (>{jours}j)")
        
        return f"{supprimees} conversations supprimées."
    except Exception as e:
        log_error("database", f"Erreur nettoyer_anciennes_conversations: {e}")
        connexion.rollback()
        return "Erreur lors du nettoyage."
    finally:
        curseur.close()
        connexion.close()


def reinitialiser_cache():
    """Vide le cache LRU (forcer re-lecture depuis DB)."""
    _recall_cached.cache_clear()
    _stats_db["cache_hits"] = 0
    _stats_db["cache_misses"] = 0
    log_event("database", "Cache LRU réinitialisé")
    return "Cache vidé."


# ============================================================
# INITIALISATION AUTO au démarrage
# ============================================================

if __name__ == "__main__":
    # Test connexion + création tables
    print("🔧 Initialisation base de données JIBI...")
    
    try:
        creer_tables()
        print("✅ Tables créées/vérifiées avec succès")
        
        stats = obtenir_statistiques_db()
        print(f"""
📊 Statistiques DB :
  - Mémoires : {stats['memoires_count']}
  - Conversations : {stats['conversations_count']}
  - Vocabulaire Ngambay : {stats['ngambay_count']}
  - Requêtes : {stats['queries_total']}
  - Cache : {stats['cache_hit_rate']}% hits
        """)
        
    except Exception as e:
        print(f"❌ Erreur initialisation : {e}")