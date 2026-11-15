"""Mémoire long terme de RIOT : Moteur SQLite haute performance avec recherche plein texte (FTS5).

Structure relationnelle + Index FTS5 ultra-rapides :
- Table `memoire_entites` & FTS5 `memoire_fts` : Préférences, Proches, Projets, Faits et Règles de dev.
- Table `recettes_code` & FTS5 `recettes_fts` : Livre de recettes de résolution de bugs et patterns.
- Table `etude_documents` & FTS5 `etude_fts` : Ingestion des cours et documentation technique.

Garantit une rétrocompatibilité intégrale avec l'ancienne interface (charger, sauver, texte_pour_systeme)
et migre automatiquement l'ancien memory.json / memoire.json au premier lancement.
"""
import json
import logging
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOG = logging.getLogger("riot.memoire")
RACINE = Path(__file__).resolve().parent.parent
DB_PATH = RACINE / "riot_memory.db"
FICHIER_JSON = RACINE / "memory.json"
ANCIEN_JSON = RACINE / "memoire.json"

_VERROU = threading.RLock()
_CONNEXION: Optional[sqlite3.Connection] = None


def get_connexion() -> sqlite3.Connection:
    """Retourne une connexion SQLite partagée (mode WAL, thread-safe avec _VERROU)."""
    global _CONNEXION
    if _CONNEXION is None:
        _CONNEXION = sqlite3.connect(
            str(DB_PATH),
            check_same_thread=False,
            timeout=15.0,
        )
        _CONNEXION.row_factory = sqlite3.Row
        # Activation du mode WAL pour lectures/écritures concurrentes ultra-rapides
        _CONNEXION.execute("PRAGMA journal_mode = WAL;")
        _CONNEXION.execute("PRAGMA synchronous = NORMAL;")
        _initialiser_base(_CONNEXION)
        _migrer_anciens_fichiers(_CONNEXION)
    return _CONNEXION


def _initialiser_base(conn: sqlite3.Connection):
    """Crée les tables relationnelles et virtuelles FTS5 avec leurs déclencheurs (triggers)."""
    with conn:
        # 1. Entités mémoire principales (préférences, projets, faits, règles)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memoire_entites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categorie TEXT NOT NULL,
                cle TEXT NOT NULL,
                contenu TEXT NOT NULL,
                cree_a TEXT NOT NULL,
                mis_a_jour_a TEXT NOT NULL,
                UNIQUE(categorie, cle)
            );
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memoire_fts USING fts5(
                id UNINDEXED,
                categorie,
                cle,
                contenu,
                tokenize = 'porter unicode61'
            );
        """)
        # Triggers de synchro memoire_fts
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_memoire_ai AFTER INSERT ON memoire_entites BEGIN
                INSERT INTO memoire_fts(id, categorie, cle, contenu)
                VALUES (new.id, new.categorie, new.cle, new.contenu);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_memoire_ad AFTER DELETE ON memoire_entites BEGIN
                DELETE FROM memoire_fts WHERE id = old.id;
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_memoire_au AFTER UPDATE ON memoire_entites BEGIN
                DELETE FROM memoire_fts WHERE id = old.id;
                INSERT INTO memoire_fts(id, categorie, cle, contenu)
                VALUES (new.id, new.categorie, new.cle, new.contenu);
            END;
        """)

        # 2. Livre de recettes de code & bugs (carnet d'apprentissage dev)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recettes_code (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL,
                langage TEXT DEFAULT '',
                probleme TEXT NOT NULL,
                cause TEXT DEFAULT '',
                solution TEXT NOT NULL,
                tags TEXT DEFAULT '',
                cree_a TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS recettes_fts USING fts5(
                id UNINDEXED,
                titre,
                langage,
                probleme,
                cause,
                solution,
                tags,
                tokenize = 'porter unicode61'
            );
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_recettes_ai AFTER INSERT ON recettes_code BEGIN
                INSERT INTO recettes_fts(id, titre, langage, probleme, cause, solution, tags)
                VALUES (new.id, new.titre, new.langage, new.probleme, new.cause, new.solution, new.tags);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_recettes_ad AFTER DELETE ON recettes_code BEGIN
                DELETE FROM recettes_fts WHERE id = old.id;
            END;
        """)

        # 3. Documents d'étude et cours techniques (RAG local)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS etude_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fichier TEXT NOT NULL,
                titre TEXT DEFAULT '',
                section TEXT DEFAULT '',
                texte TEXT NOT NULL,
                cree_a TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS etude_fts USING fts5(
                id UNINDEXED,
                fichier,
                titre,
                section,
                texte,
                tokenize = 'porter unicode61'
            );
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_etude_ai AFTER INSERT ON etude_documents BEGIN
                INSERT INTO etude_fts(id, fichier, titre, section, texte)
                VALUES (new.id, new.fichier, new.titre, new.section, new.texte);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_etude_ad AFTER DELETE ON etude_documents BEGIN
                DELETE FROM etude_fts WHERE id = old.id;
            END;
        """)

        # 4. Historique persistant des discussions (Sessions & Messages)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                titre TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'swarm',
                projet TEXT,
                cree_a TEXT NOT NULL,
                mis_a_jour_a TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                fichiers TEXT DEFAULT '[]',
                cree_a TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);
        """)


def _nettoyer_requete_fts(texte: str) -> str:
    """Nettoie une chaîne pour éviter les erreurs de syntaxe FTS5 et applique les jokers."""
    mots = re.findall(r"\w+", texte, re.UNICODE)
    if not mots:
        return ""
    # Chaque mot termine par un joker * pour matcher les préfixes
    return " ".join(f'"{m}"*' for m in mots)


def _migrer_anciens_fichiers(conn: sqlite3.Connection):
    """Importe les données de memory.json ou memoire.json si la base SQLite est vide."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM memoire_entites;")
    if cur.fetchone()[0] > 0:
        return  # Déjà des données dans SQLite

    donnees = {}
    if FICHIER_JSON.exists():
        try:
            donnees = json.loads(FICHIER_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    elif ANCIEN_JSON.exists():
        try:
            anc = json.loads(ANCIEN_JSON.read_text(encoding="utf-8"))
            donnees = {"facts": anc.get("faits", [])}
        except Exception:
            pass

    if not donnees:
        return

    maintenant = datetime.now().isoformat()
    with conn:
        for cat in ("preferences", "people", "projects"):
            for cle, val in donnees.get(cat, {}).items():
                conn.execute("""
                    INSERT OR REPLACE INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
                    VALUES (?, ?, ?, ?, ?);
                """, (cat, str(cle), str(val), maintenant, maintenant))

        for idx, fait in enumerate(donnees.get("facts", [])):
            conn.execute("""
                INSERT OR REPLACE INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
                VALUES (?, ?, ?, ?, ?);
            """, ("facts", f"fait_{idx+1}", str(fait), maintenant, maintenant))


# ------------------------------------------------------------------ API Entités

def memoriser_entite(categorie: str, cle: str, contenu: str) -> None:
    """Enregistre ou met à jour une entité dans la mémoire SQLite."""
    conn = get_connexion()
    maintenant = datetime.now().isoformat()
    cat_norm = str(categorie).lower().strip()
    cle_norm = str(cle).strip()
    val_norm = str(contenu).strip()

    if not cle_norm:
        cle_norm = val_norm[:40]

    with _VERROU, conn:
        conn.execute("""
            INSERT INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(categorie, cle) DO UPDATE SET
                contenu = excluded.contenu,
                mis_a_jour_a = excluded.mis_a_jour_a;
        """, (cat_norm, cle_norm, val_norm, maintenant, maintenant))


def supprimer_entite(categorie: str, cle: str) -> bool:
    """Supprime une entité précise de la mémoire."""
    conn = get_connexion()
    with _VERROU, conn:
        cur = conn.execute(
            "DELETE FROM memoire_entites WHERE categorie = ? AND cle = ?;",
            (str(categorie).lower().strip(), str(cle).strip()),
        )
        return cur.rowcount > 0


def oublier_par_motif(motif: str) -> int:
    """Oublie toutes les entités contenant le motif dans la clé ou le contenu."""
    conn = get_connexion()
    motif_like = f"%{motif.strip()}%"
    with _VERROU, conn:
        cur = conn.execute("""
            DELETE FROM memoire_entites
            WHERE cle LIKE ? OR contenu LIKE ?;
        """, (motif_like, motif_like))
        return cur.rowcount


def rechercher_fts(requete: str, categorie: Optional[str] = None, limite: int = 10) -> List[Dict[str, Any]]:
    """Recherche plein texte ultra-rapide avec ranking FTS5 (fallback LIKE)."""
    conn = get_connexion()
    q_fts = _nettoyer_requete_fts(requete)

    resultats = []
    with _VERROU:
        if q_fts:
            try:
                if categorie:
                    cur = conn.execute("""
                        SELECT e.id, e.categorie, e.cle, e.contenu, e.mis_a_jour_a
                        FROM memoire_fts f
                        JOIN memoire_entites e ON f.id = e.id
                        WHERE memoire_fts MATCH ? AND e.categorie = ?
                        ORDER BY bm25(memoire_fts)
                        LIMIT ?;
                    """, (q_fts, str(categorie).lower().strip(), limite))
                else:
                    cur = conn.execute("""
                        SELECT e.id, e.categorie, e.cle, e.contenu, e.mis_a_jour_a
                        FROM memoire_fts f
                        JOIN memoire_entites e ON f.id = e.id
                        WHERE memoire_fts MATCH ?
                        ORDER BY bm25(memoire_fts)
                        LIMIT ?;
                    """, (q_fts, limite))
                resultats = [dict(r) for r in cur.fetchall()]
            except sqlite3.OperationalError:
                resultats = []

        # Fallback LIKE si FTS5 ne donne rien ou syntaxe vide
        if not resultats and requete.strip():
            motif_like = f"%{requete.strip()}%"
            if categorie:
                cur = conn.execute("""
                    SELECT id, categorie, cle, contenu, mis_a_jour_a
                    FROM memoire_entites
                    WHERE (cle LIKE ? OR contenu LIKE ?) AND categorie = ?
                    ORDER BY id DESC LIMIT ?;
                """, (motif_like, motif_like, str(categorie).lower().strip(), limite))
            else:
                cur = conn.execute("""
                    SELECT id, categorie, cle, contenu, mis_a_jour_a
                    FROM memoire_entites
                    WHERE cle LIKE ? OR contenu LIKE ?
                    ORDER BY id DESC LIMIT ?;
                """, (motif_like, motif_like, limite))
            resultats = [dict(r) for r in cur.fetchall()]

    return resultats


# ------------------------------------------------------------------ Recettes de code & Bugs

def ajouter_recette_code(
    titre: str,
    probleme: str,
    solution: str,
    cause: str = "",
    langage: str = "",
    tags: str = "",
) -> int:
    """Enregistre une nouvelle fiche de résolution de bug ou recette de dev."""
    conn = get_connexion()
    maintenant = datetime.now().isoformat()
    with _VERROU, conn:
        cur = conn.execute("""
            INSERT INTO recettes_code(titre, langage, probleme, cause, solution, tags, cree_a)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            titre.strip(),
            langage.strip().lower(),
            probleme.strip(),
            cause.strip(),
            solution.strip(),
            tags.strip(),
            maintenant,
        ))
        return cur.lastrowid or 0


def rechercher_recettes_code(requete: str, limite: int = 5) -> List[Dict[str, Any]]:
    """Cherche dans le carnet de recettes par FTS5 ou mots-clés."""
    conn = get_connexion()
    q_fts = _nettoyer_requete_fts(requete)
    resultats = []

    with _VERROU:
        if q_fts:
            try:
                cur = conn.execute("""
                    SELECT r.id, r.titre, r.langage, r.probleme, r.cause, r.solution, r.tags, r.cree_a
                    FROM recettes_fts f
                    JOIN recettes_code r ON f.id = r.id
                    WHERE recettes_fts MATCH ?
                    ORDER BY bm25(recettes_fts)
                    LIMIT ?;
                """, (q_fts, limite))
                resultats = [dict(row) for row in cur.fetchall()]
            except sqlite3.OperationalError:
                resultats = []

        if not resultats and requete.strip():
            motif = f"%{requete.strip()}%"
            cur = conn.execute("""
                SELECT id, titre, langage, probleme, cause, solution, tags, cree_a
                FROM recettes_code
                WHERE titre LIKE ? OR probleme LIKE ? OR solution LIKE ? OR tags LIKE ?
                ORDER BY id DESC LIMIT ?;
            """, (motif, motif, motif, motif, limite))
            resultats = [dict(row) for row in cur.fetchall()]

    return resultats


def lister_recettes_code(limite: int = 20) -> List[Dict[str, Any]]:
    conn = get_connexion()
    with _VERROU:
        cur = conn.execute("""
            SELECT id, titre, langage, probleme, cause, solution, tags, cree_a
            FROM recettes_code ORDER BY id DESC LIMIT ?;
        """, (limite,))
        return [dict(row) for row in cur.fetchall()]


def lister_regles_dev() -> List[Dict[str, Any]]:
    """Retourne la liste des règles de dev et d'ingénierie apprises."""
    conn = get_connexion()
    with _VERROU:
        cur = conn.execute("""
            SELECT id, cle, contenu, mis_a_jour_a
            FROM memoire_entites
            WHERE categorie = 'regles_dev'
            ORDER BY id ASC;
        """)
        return [dict(row) for row in cur.fetchall()]


def ajouter_regle_dev(cle: str, contenu: str) -> None:
    """Enregistre ou met à jour une règle de dev stricte."""
    memoriser_entite("regles_dev", cle, contenu)


def supprimer_regle_dev(cle: str) -> bool:
    """Supprime une règle de dev par sa clé."""
    return supprimer_entite("regles_dev", cle)


def recup_recettes_pertinentes(contexte: str, limite: int = 3) -> str:
    """Recherche des recettes de code et règles pertinentes pour enrichir le prompt de RIOT."""
    if not contexte or len(contexte.strip()) < 3:
        return ""
    recettes = rechercher_recettes_code(contexte, limite=limite)
    if not recettes:
        return ""
    blocs = ["\n[Recettes de code et solutions éprouvées pertinentes] :"]
    for r in recettes:
        blocs.append(
            f"• Problème: {r['titre']} ({r.get('langage') or 'dev'})\n"
            f"  Cause: {r.get('cause') or 'N/A'}\n"
            f"  Solution recommandée: {r['solution']}"
        )
    return "\n".join(blocs) + "\n"


# ------------------------------------------------------------------ Documents d'étude

def ajouter_document_etude(fichier: str, titre: str, section: str, texte: str) -> int:
    """Enregistre un passage d'un document d'étude pour la recherche documentaire."""
    conn = get_connexion()
    maintenant = datetime.now().isoformat()
    with _VERROU, conn:
        cur = conn.execute("""
            INSERT INTO etude_documents(fichier, titre, section, texte, cree_a)
            VALUES (?, ?, ?, ?, ?);
        """, (fichier.strip(), titre.strip(), section.strip(), texte.strip(), maintenant))
        return cur.lastrowid or 0


def rechercher_etude(requete: str, limite: int = 5) -> List[Dict[str, Any]]:
    """Recherche plein texte dans les documents de cours ingérés."""
    conn = get_connexion()
    q_fts = _nettoyer_requete_fts(requete)
    resultats = []

    with _VERROU:
        if q_fts:
            try:
                cur = conn.execute("""
                    SELECT d.id, d.fichier, d.titre, d.section, d.texte
                    FROM etude_fts f
                    JOIN etude_documents d ON f.id = d.id
                    WHERE etude_fts MATCH ?
                    ORDER BY bm25(etude_fts)
                    LIMIT ?;
                """, (q_fts, limite))
                resultats = [dict(row) for row in cur.fetchall()]
            except sqlite3.OperationalError:
                resultats = []

        if not resultats and requete.strip():
            motif = f"%{requete.strip()}%"
            cur = conn.execute("""
                SELECT id, fichier, titre, section, texte
                FROM etude_documents
                WHERE texte LIKE ? OR titre LIKE ? OR section LIKE ?
                ORDER BY id DESC LIMIT ?;
            """, (motif, motif, motif, limite))
            resultats = [dict(row) for row in cur.fetchall()]

    return resultats


# ------------------------------------------------------------------ Rétrocompatibilité

def charger() -> Dict[str, Any]:
    """Retourne la mémoire sous la forme classique dict pour compatibilité intégrale."""
    conn = get_connexion()
    memoire = {"preferences": {}, "people": {}, "projects": {}, "facts": []}

    with _VERROU:
        cur = conn.execute("SELECT categorie, cle, contenu FROM memoire_entites ORDER BY id ASC;")
        for cat, cle, val in cur.fetchall():
            if cat in ("preferences", "people", "projects"):
                memoire[cat][cle] = val
            elif cat in ("facts", "fait"):
                memoire["facts"].append(val)
            else:
                # Catégories étendues (ex: regle_dev)
                if cat not in memoire:
                    memoire[cat] = {}
                memoire[cat][cle] = val

    return memoire


def sauver(memoire: Dict[str, Any]) -> None:
    """Synchronise un dictionnaire de mémoire dans SQLite et sauvegarde en backup JSON."""
    conn = get_connexion()
    maintenant = datetime.now().isoformat()

    with _VERROU, conn:
        for cat in ("preferences", "people", "projects"):
            for cle, val in memoire.get(cat, {}).items():
                conn.execute("""
                    INSERT INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(categorie, cle) DO UPDATE SET
                        contenu = excluded.contenu,
                        mis_a_jour_a = excluded.mis_a_jour_a;
                """, (cat, str(cle), str(val), maintenant, maintenant))

        for idx, fait in enumerate(memoire.get("facts", [])):
            conn.execute("""
                INSERT INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(categorie, cle) DO UPDATE SET
                    contenu = excluded.contenu,
                    mis_a_jour_a = excluded.mis_a_jour_a;
            """, ("facts", f"fait_{idx+1}", str(fait), maintenant, maintenant))

    # Backup JSON lisible à la main
    try:
        tmp = FICHIER_JSON.with_suffix(".tmp")
        tmp.write_text(json.dumps(memoire, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(FICHIER_JSON)
    except Exception:
        pass


def texte_pour_systeme(memoire: Optional[Dict[str, Any]] = None) -> str:
    """Génère le texte synthétique injecté dans le prompt système."""
    if memoire is None:
        memoire = charger()

    parties = []
    if memoire.get("preferences"):
        parties.append("Préférences : " + " ; ".join(
            f"{k} = {v}" for k, v in memoire["preferences"].items()))
    if memoire.get("people"):
        parties.append("Personnes : " + " ; ".join(
            f"{k} = {v}" for k, v in memoire["people"].items()))
    if memoire.get("projects"):
        parties.append("Projets : " + " ; ".join(
            f"{k} = {v}" for k, v in memoire["projects"].items()))
    if memoire.get("regles_dev"):
        parties.append("Règles d'ingénierie apprises : " + " ; ".join(
            f"{k} = {v}" for k, v in memoire["regles_dev"].items()))
    if memoire.get("facts"):
        parties.append("Faits mémorisés : " + " ; ".join(memoire["facts"]))

    if not parties:
        return ""

    return (
        "\n\nCe que tu sais déjà sur l'utilisateur et son environnement "
        "(sers-t'en sans le réciter spontanément) :\n" + "\n".join(parties)
    )


# ---------------------------------------------------------------------------
# GESTION DES SESSIONS DE CHAT ET DE L'HISTORIQUE PERSISTANT
# ---------------------------------------------------------------------------

def creer_session_chat(session_id: Optional[str] = None, titre: str = "Nouvelle discussion", mode: str = "swarm", projet: Optional[str] = None) -> str:
    """Crée ou initialise une nouvelle session de chat persistante."""
    import uuid
    if not session_id:
        session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    maintenant = datetime.now().isoformat()
    conn = get_connexion()
    with _VERROU, conn:
        conn.execute("""
            INSERT OR REPLACE INTO chat_sessions (id, titre, mode, projet, cree_a, mis_a_jour_a)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (session_id, titre, mode, projet or "", maintenant, maintenant))
    return session_id


def lister_sessions_chat(limit: int = 50) -> List[Dict[str, Any]]:
    """Retourne la liste des sessions de discussion triées de la plus récente à la plus ancienne."""
    conn = get_connexion()
    with _VERROU:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.titre, s.mode, s.projet, s.cree_a, s.mis_a_jour_a,
                   COUNT(m.id) as nb_messages
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON s.id = m.session_id
            GROUP BY s.id
            ORDER BY s.mis_a_jour_a DESC
            LIMIT ?;
        """, (limit,))
        lignes = cur.fetchall()
        return [
            {
                "id": row["id"],
                "titre": row["titre"],
                "mode": row["mode"],
                "projet": row["projet"],
                "cree_a": row["cree_a"],
                "mis_a_jour_a": row["mis_a_jour_a"],
                "nb_messages": row["nb_messages"]
            }
            for row in lignes
        ]


def obtenir_session_chat(session_id: str) -> Optional[Dict[str, Any]]:
    """Récupère une session de chat spécifique avec tous ses messages enregistrés."""
    conn = get_connexion()
    with _VERROU:
        cur = conn.cursor()
        cur.execute("SELECT id, titre, mode, projet, cree_a, mis_a_jour_a FROM chat_sessions WHERE id = ?;", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        session = {
            "id": row["id"],
            "titre": row["titre"],
            "mode": row["mode"],
            "projet": row["projet"],
            "cree_a": row["cree_a"],
            "mis_a_jour_a": row["mis_a_jour_a"],
            "messages": obtenir_messages_chat(session_id)
        }
        return session


def ajouter_message_chat(session_id: str, role: str, content: str, fichiers: Optional[List[Dict[str, Any]]] = None):
    """Ajoute un message (user/assistant) dans l'historique persistant d'une session."""
    if not session_id or not content.strip():
        return
    maintenant = datetime.now().isoformat()
    fichiers_json = json.dumps(fichiers or [], ensure_ascii=False)
    conn = get_connexion()
    with _VERROU, conn:
        # S'assurer que la session existe
        cur = conn.cursor()
        cur.execute("SELECT id, titre FROM chat_sessions WHERE id = ?;", (session_id,))
        row = cur.fetchone()
        if not row:
            # Auto-génération d'un titre basé sur le message si c'est le 1er message
            titre_auto = content.strip().replace("\n", " ")[:36] + ("..." if len(content.strip()) > 36 else "")
            conn.execute("""
                INSERT INTO chat_sessions (id, titre, mode, projet, cree_a, mis_a_jour_a)
                VALUES (?, ?, 'swarm', '', ?, ?);
            """, (session_id, titre_auto, maintenant, maintenant))
        else:
            # Si le titre était par défaut et que c'est un message user, le renommer intelligemment
            if row["titre"] in ("Nouvelle discussion", "Nouveau chat") and role == "user":
                titre_auto = content.strip().replace("\n", " ")[:36] + ("..." if len(content.strip()) > 36 else "")
                conn.execute("UPDATE chat_sessions SET titre = ? WHERE id = ?;", (titre_auto, session_id))

        conn.execute("""
            INSERT INTO chat_messages (session_id, role, content, fichiers, cree_a)
            VALUES (?, ?, ?, ?, ?);
        """, (session_id, role, content.strip(), fichiers_json, maintenant))

        conn.execute("UPDATE chat_sessions SET mis_a_jour_a = ? WHERE id = ?;", (maintenant, session_id))


def renommer_session_chat(session_id: str, titre: str):
    """Renomme le titre d'une session de chat."""
    maintenant = datetime.now().isoformat()
    conn = get_connexion()
    with _VERROU, conn:
        conn.execute("UPDATE chat_sessions SET titre = ?, mis_a_jour_a = ? WHERE id = ?;", (titre.strip(), maintenant, session_id))


def supprimer_session_chat(session_id: str) -> bool:
    """Supprime définitivement une session et tous ses messages."""
    conn = get_connexion()
    with _VERROU, conn:
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?;", (session_id,))
        cur = conn.cursor()
        cur.execute("DELETE FROM chat_sessions WHERE id = ?;", (session_id,))
        return cur.rowcount > 0


def obtenir_messages_chat(session_id: str, limit: int = 60) -> List[Dict[str, Any]]:
    """Retourne la liste chronologique des messages récents pour une session donnée."""
    conn = get_connexion()
    with _VERROU:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, role, content, fichiers, cree_a
            FROM (
                SELECT id, role, content, fichiers, cree_a
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC;
        """, (session_id, limit))
        lignes = cur.fetchall()
        resultats = []
        for row in lignes:
            try:
                fichiers = json.loads(row["fichiers"]) if row["fichiers"] else []
            except Exception:
                fichiers = []
            resultats.append({
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "fichiers": fichiers,
                "cree_a": row["cree_a"]
            })
        return resultats
