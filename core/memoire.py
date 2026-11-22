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
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOG = logging.getLogger("riot.memoire")
RACINE = Path(__file__).resolve().parent.parent
_DEFAULT_USER_DB_PATH = Path.home() / ".riot" / "riot_memory.db"


def _determiner_db_path() -> Path:
    """Résout l'emplacement persistant de la base mémoire utilisateur (~/.riot/riot_memory.db)."""
    env_db = os.environ.get("RIOT_MEMORY_DB", "").strip()
    if env_db:
        return Path(env_db)
    return _DEFAULT_USER_DB_PATH


DB_PATH = _determiner_db_path()
FICHIER_JSON = DB_PATH.parent / "memory.json"
LEGACY_DB_PATH = RACINE / "riot_memory.db"
LEGACY_JSON = RACINE / "memory.json"
ANCIEN_JSON = RACINE / "memoire.json"

_VERROU = threading.RLock()
_CONNEXION: Optional[sqlite3.Connection] = None
_CONNEXION_PATH: Optional[str] = None
_SYNC_LOCK = threading.Lock()
_DERNIERE_SYNC_THREAD: float = 0.0
_DERNIERE_AUTO_EXTRACTION: float = 0.0
_AUTO_EXTRACT_COOLDOWN_SEC: float = 45.0


def _maintenant_iso() -> str:
    """Horodatage ISO-8601 UTC pour comparaisons Last-Write-Wins multi-postes."""
    return datetime.now(timezone.utc).isoformat()


def _masquer_texte(texte: str, max_len: int = 4000) -> str:
    """Masque automatiquement clés API, tokens et secrets avant toute persistance ou synchro."""
    val = str(texte or "").strip()
    if not val:
        return ""
    try:
        from core.telemetry import masquer_secrets
        return masquer_secrets(val, max_len=max_len)
    except Exception:
        return val[:max_len]


def _migrer_base_racine_si_besoin(cible: Path) -> None:
    """Migre l'ancienne base située dans le dossier du code vers ~/.riot/riot_memory.db sans perte."""
    try:
        if cible.resolve() == LEGACY_DB_PATH.resolve():
            return
        if not LEGACY_DB_PATH.exists() or LEGACY_DB_PATH.stat().st_size == 0:
            return
        if cible.exists() and cible.stat().st_size > 0:
            return
        cible.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(str(LEGACY_DB_PATH), timeout=10.0)
        dst = sqlite3.connect(str(cible), timeout=10.0)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        LOG.info("Mémoire locale migrée vers %s", cible)
    except Exception as e:
        LOG.warning("Migration mémoire vers %s ignorée : %s", cible, e)


def reinitialiser_connexion(db_path: Optional[Path] = None) -> None:
    """Ferme proprement la connexion courante (utile après changement de DB_PATH ou en test)."""
    global _CONNEXION, _CONNEXION_PATH, DB_PATH, FICHIER_JSON
    with _VERROU:
        if _CONNEXION is not None:
            try:
                _CONNEXION.close()
            except Exception:
                pass
            _CONNEXION = None
            _CONNEXION_PATH = None
        if db_path is not None:
            DB_PATH = Path(db_path)
            FICHIER_JSON = DB_PATH.parent / "memory.json"


def get_connexion() -> sqlite3.Connection:
    """Retourne une connexion SQLite partagée (mode WAL, thread-safe avec _VERROU)."""
    global _CONNEXION, _CONNEXION_PATH, FICHIER_JSON
    cible = Path(DB_PATH)
    cible_str = str(cible)
    with _VERROU:
        if _CONNEXION is not None and _CONNEXION_PATH != cible_str:
            try:
                _CONNEXION.close()
            except Exception:
                pass
            _CONNEXION = None
            _CONNEXION_PATH = None

        if _CONNEXION is None:
            cible.parent.mkdir(parents=True, exist_ok=True)
            FICHIER_JSON = cible.parent / "memory.json"
            if cible_str == str(_DEFAULT_USER_DB_PATH):
                _migrer_base_racine_si_besoin(cible)
            _CONNEXION = sqlite3.connect(
                cible_str,
                check_same_thread=False,
                timeout=15.0,
            )
            _CONNEXION.row_factory = sqlite3.Row
            _CONNEXION_PATH = cible_str
            # Activation du mode WAL pour lectures/écritures concurrentes ultra-rapides
            _CONNEXION.execute("PRAGMA journal_mode = WAL;")
            _CONNEXION.execute("PRAGMA synchronous = NORMAL;")
            _initialiser_base(_CONNEXION)
            _migrer_anciens_fichiers(_CONNEXION)
            _auto_importer_playbook_si_nouveau(_CONNEXION)
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

        # 5. Tombstones & métadonnées de synchro cloud
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memoire_tombstones (
                kind TEXT NOT NULL,
                mem_key TEXT NOT NULL,
                deleted_at TEXT NOT NULL,
                PRIMARY KEY(kind, mem_key)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memoire_meta (
                cle TEXT PRIMARY KEY,
                valeur TEXT NOT NULL
            );
        """)

        # Migration douce recettes_code : colonnes gouvernance + trigger UPDATE FTS5
        cols = {r[1] for r in conn.execute("PRAGMA table_info(recettes_code);").fetchall()}
        if "mis_a_jour_a" not in cols:
            conn.execute("ALTER TABLE recettes_code ADD COLUMN mis_a_jour_a TEXT DEFAULT '';")
            conn.execute("UPDATE recettes_code SET mis_a_jour_a = cree_a WHERE mis_a_jour_a = '';")
        migrations_recettes = {
            "scope": "TEXT DEFAULT 'global'",
            "interdits": "TEXT DEFAULT ''",
            "verification": "TEXT DEFAULT ''",
            "confiance": "REAL DEFAULT 0.65",
            "utilisations": "INTEGER DEFAULT 0",
            "echecs": "INTEGER DEFAULT 0",
            "source": "TEXT DEFAULT 'dev'",
            "statut": "TEXT DEFAULT 'active'",
        }
        for col, ddl in migrations_recettes.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE recettes_code ADD COLUMN {col} {ddl};")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recettes_statut_scope ON recettes_code(statut, scope, confiance DESC);")
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_recettes_au AFTER UPDATE ON recettes_code BEGIN
                DELETE FROM recettes_fts WHERE id = old.id;
                INSERT INTO recettes_fts(id, titre, langage, probleme, cause, solution, tags)
                VALUES (new.id, new.titre, new.langage, new.probleme, new.cause, new.solution, new.tags);
            END;
        """)


_STOPWORDS_FTS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "en", "au",
    "aux", "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "nos",
    "vos", "comment", "pourquoi", "avec", "pour", "sur", "dans", "est", "que",
    "qui", "quoi", "pas", "plus", "the", "and", "for", "with", "how", "from",
    "this", "that", "probleme", "problème", "erreur", "bug",
}


def _nettoyer_requete_fts(texte: str) -> str:
    """Nettoie une chaîne pour FTS5 et génère une requête OR pondérée par BM25."""
    mots = [m for m in re.findall(r"\w+", texte, re.UNICODE) if len(m) >= 2]
    if not mots:
        mots = re.findall(r"\w+", texte, re.UNICODE)
    if not mots:
        return ""
    significatifs = [m for m in mots if m.lower() not in _STOPWORDS_FTS]
    cibles = (significatifs or mots)[:10]
    # OR permet à BM25 de classer les meilleurs recouvrements en premier sans exiger 100% des mots
    return " OR ".join(f'"{m}"*' for m in cibles)


def _migrer_anciens_fichiers(conn: sqlite3.Connection):
    """Importe les données de memory.json ou memoire.json si la base SQLite est vide."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM memoire_entites;")
    if cur.fetchone()[0] > 0:
        return  # Déjà des données dans SQLite

    donnees = {}
    for candidat in (FICHIER_JSON, LEGACY_JSON):
        if candidat.exists():
            try:
                donnees = json.loads(candidat.read_text(encoding="utf-8"))
                break
            except Exception:
                pass
    if not donnees and ANCIEN_JSON.exists():
        try:
            anc = json.loads(ANCIEN_JSON.read_text(encoding="utf-8"))
            donnees = {"facts": anc.get("faits", [])}
        except Exception:
            pass

    if not donnees:
        return

    maintenant = _maintenant_iso()
    with conn:
        for cat in ("preferences", "people", "projects"):
            for cle, val in donnees.get(cat, {}).items():
                conn.execute("""
                    INSERT OR REPLACE INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
                    VALUES (?, ?, ?, ?, ?);
                """, (cat, str(cle), _masquer_texte(str(val)), maintenant, maintenant))

        for idx, fait in enumerate(donnees.get("facts", [])):
            conn.execute("""
                INSERT OR REPLACE INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
                VALUES (?, ?, ?, ?, ?);
            """, ("facts", f"fait_{idx+1}", _masquer_texte(str(fait)), maintenant, maintenant))


# ------------------------------------------------------------------ API Entités

def memoriser_entite(
    categorie: str,
    cle: str,
    contenu: str,
    *,
    mis_a_jour_a: Optional[str] = None,
    sync_auto: bool = True,
) -> None:
    """Enregistre ou met à jour une entité dans la mémoire SQLite (avec masquage secrets)."""
    conn = get_connexion()
    maintenant = mis_a_jour_a or _maintenant_iso()
    cat_norm = str(categorie).lower().strip()
    cle_norm = _masquer_texte(str(cle).strip(), max_len=200)
    val_norm = _masquer_texte(str(contenu).strip(), max_len=4000)

    if not cle_norm:
        cle_norm = val_norm[:40]
    if not val_norm:
        return

    with _VERROU, conn:
        conn.execute("""
            INSERT INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(categorie, cle) DO UPDATE SET
                contenu = excluded.contenu,
                mis_a_jour_a = excluded.mis_a_jour_a;
        """, (cat_norm, cle_norm, val_norm, maintenant, maintenant))
        conn.execute(
            "DELETE FROM memoire_tombstones WHERE kind = ? AND mem_key = ?;",
            (f"entity:{cat_norm}", cle_norm),
        )
    if sync_auto:
        pousser_synchro_asynchrone()


def supprimer_entite(categorie: str, cle: str, *, sync_auto: bool = True) -> bool:
    """Supprime une entité précise de la mémoire et trace le tombstone pour le Cloud."""
    conn = get_connexion()
    cat_norm = str(categorie).lower().strip()
    cle_norm = str(cle).strip()
    maintenant = _maintenant_iso()
    with _VERROU, conn:
        cur = conn.execute(
            "DELETE FROM memoire_entites WHERE categorie = ? AND cle = ?;",
            (cat_norm, cle_norm),
        )
        supprime = cur.rowcount > 0
        if supprime:
            conn.execute("""
                INSERT INTO memoire_tombstones(kind, mem_key, deleted_at)
                VALUES (?, ?, ?)
                ON CONFLICT(kind, mem_key) DO UPDATE SET deleted_at = excluded.deleted_at;
            """, (f"entity:{cat_norm}", cle_norm, maintenant))
    if supprime and sync_auto:
        pousser_synchro_asynchrone()
    return supprime


def oublier_par_motif(motif: str, *, sync_auto: bool = True) -> int:
    """Oublie toutes les entités contenant le motif dans la clé ou le contenu."""
    conn = get_connexion()
    motif_like = f"%{motif.strip()}%"
    maintenant = _maintenant_iso()
    with _VERROU, conn:
        cibles = conn.execute("""
            SELECT categorie, cle FROM memoire_entites
            WHERE cle LIKE ? OR contenu LIKE ?;
        """, (motif_like, motif_like)).fetchall()
        cur = conn.execute("""
            DELETE FROM memoire_entites
            WHERE cle LIKE ? OR contenu LIKE ?;
        """, (motif_like, motif_like))
        for r in cibles:
            conn.execute("""
                INSERT INTO memoire_tombstones(kind, mem_key, deleted_at)
                VALUES (?, ?, ?)
                ON CONFLICT(kind, mem_key) DO UPDATE SET deleted_at = excluded.deleted_at;
            """, (f"entity:{r['categorie']}", r["cle"], maintenant))
        nb = cur.rowcount
    if nb > 0 and sync_auto:
        pousser_synchro_asynchrone()
    return nb


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

def _cle_recette(titre: str, langage: str = "") -> str:
    """Clé canonique déterministe pour dédupliquer et synchroniser une recette de code."""
    t = re.sub(r"\s+", " ", (titre or "").strip().lower())
    l = (langage or "").strip().lower()
    return f"{l}::{t}"[:180]


def ajouter_recette_code(
    titre: str,
    probleme: str,
    solution: str,
    cause: str = "",
    langage: str = "",
    tags: str = "",
    *,
    mis_a_jour_a: Optional[str] = None,
    sync_auto: bool = True,
) -> int:
    """Enregistre ou met à jour une fiche de résolution de bug ou recette de dev."""
    conn = get_connexion()
    maintenant = mis_a_jour_a or _maintenant_iso()
    titre_c = _masquer_texte(titre, max_len=300)
    lang_c = (langage or "").strip().lower()[:60]
    prob_c = _masquer_texte(probleme, max_len=2000)
    cause_c = _masquer_texte(cause, max_len=1500)
    sol_c = _masquer_texte(solution, max_len=3000)
    tags_c = _masquer_texte(tags, max_len=300)
    if not titre_c or not prob_c or not sol_c:
        return 0

    with _VERROU, conn:
        existante = conn.execute(
            "SELECT id FROM recettes_code WHERE lower(trim(titre)) = ? AND lower(trim(langage)) = ? LIMIT 1;",
            (titre_c.lower(), lang_c),
        ).fetchone()
        if existante:
            rid = int(existante["id"])
            conn.execute("""
                UPDATE recettes_code
                SET probleme = ?, cause = ?, solution = ?, tags = ?, mis_a_jour_a = ?
                WHERE id = ?;
            """, (prob_c, cause_c, sol_c, tags_c, maintenant, rid))
        else:
            cur = conn.execute("""
                INSERT INTO recettes_code(titre, langage, probleme, cause, solution, tags, cree_a, mis_a_jour_a)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (titre_c, lang_c, prob_c, cause_c, sol_c, tags_c, maintenant, maintenant))
            rid = int(cur.lastrowid or 0)
        conn.execute(
            "DELETE FROM memoire_tombstones WHERE kind = 'recipe' AND mem_key = ?;",
            (_cle_recette(titre_c, lang_c),),
        )
    if sync_auto:
        pousser_synchro_asynchrone()
    return rid


def rechercher_recettes_code(requete: str, limite: int = 5) -> List[Dict[str, Any]]:
    """Cherche dans le carnet de recettes par FTS5 ou mots-clés."""
    conn = get_connexion()
    q_fts = _nettoyer_requete_fts(requete)
    resultats = []

    with _VERROU:
        if q_fts:
            try:
                cur = conn.execute("""
                    SELECT r.id, r.titre, r.langage, r.probleme, r.cause, r.solution, r.tags, r.cree_a,
                           COALESCE(r.scope, 'global') AS scope,
                           COALESCE(r.interdits, '') AS interdits,
                           COALESCE(r.verification, '') AS verification,
                           COALESCE(r.confiance, 0.65) AS confiance,
                           COALESCE(r.statut, 'active') AS statut
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
                SELECT id, titre, langage, probleme, cause, solution, tags, cree_a,
                       COALESCE(scope, 'global') AS scope,
                       COALESCE(interdits, '') AS interdits,
                       COALESCE(verification, '') AS verification,
                       COALESCE(confiance, 0.65) AS confiance,
                       COALESCE(statut, 'active') AS statut
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


def recup_recettes_pertinentes(
    contexte: str,
    limite: int = 4,
    *,
    scope_stack: Optional[str] = None,
    scope_projet: Optional[str] = None,
) -> str:
    """Recherche des recettes/lecons actives pertinentes (filtrees par scope et confiance)."""
    if not contexte or len(contexte.strip()) < 3:
        return ""
    recettes = rechercher_recettes_code(contexte, limite=max(8, limite * 2))
    if not recettes:
        return ""

    stack_cible = f"stack:{scope_stack.strip().lower()}" if scope_stack else ""
    proj_cible = f"project:{scope_projet.strip().lower()}" if scope_projet else ""

    filtrees: List[Dict[str, Any]] = []
    for r in recettes:
        statut = str(r.get("statut") or "active").lower()
        if statut == "archived":
            continue
        sc = str(r.get("scope") or "global").strip().lower()
        if sc.startswith("project:") and proj_cible and sc != proj_cible:
            continue
        if sc.startswith("project:") and not proj_cible:
            continue
        conf = float(r.get("confiance") if r.get("confiance") is not None else 0.65)
        if conf < 0.30:
            continue
        bonus = 0.25 if (sc == proj_cible and proj_cible) or (sc == stack_cible and stack_cible) else 0.0
        copie = dict(r)
        copie["_score"] = conf + bonus
        filtrees.append(copie)

    if not filtrees:
        return ""
    filtrees.sort(key=lambda x: x["_score"], reverse=True)
    filtrees = filtrees[:limite]

    blocs = ["\n[Playbook RIOT & Leçons Éprouvées Pertinentes] :"]
    for r in filtrees:
        conf_pct = int(round(float(r.get("confiance") if r.get("confiance") is not None else 0.65) * 100))
        ligne = (
            f"• [#{r['id']} · {r.get('scope') or 'global'} · {conf_pct}%] "
            f"{r['titre']} ({r.get('langage') or 'dev'})\n"
            f"  Cause: {r.get('cause') or 'N/A'}\n"
            f"  À FAIRE: {r['solution']}"
        )
        if r.get("interdits"):
            ligne += f"\n  À ÉVITER: {r['interdits']}"
        if r.get("verification"):
            ligne += f"\n  Vérification: {r['verification']}"
        blocs.append(ligne)
    return "\n".join(blocs) + "\n"


def _anonymiser_texte_lecon(texte: str, max_len: int = 2000) -> str:
    s = _masquer_texte(texte, max_len=max_len)
    s = re.sub(r"[A-Za-z]:\\Users\\[^\\\s\"']+", "<HOME>", s, flags=re.IGNORECASE)
    s = re.sub(r"[A-Za-z]:\\PROJETS\\[^\\\s\"']+", "<PROJET>", s, flags=re.IGNORECASE)
    s = re.sub(r"/(?:home|Users)/[^/\s\"']+", "<HOME>", s)
    return s


def enregistrer_lecon_mentor(
    titre: str,
    probleme: str,
    solution: str,
    *,
    cause: str = "",
    langage: str = "",
    tags: str = "",
    scope: str = "global",
    interdits: str = "",
    verification: str = "",
    source: str = "antigravity_mentor",
    confiance: float = 0.68,
    sync_auto: bool = True,
) -> int:
    """Enregistre ou consolide une lecon apprise avec gouvernance (scope, anti-pattern, confiance)."""
    titre_c = _anonymiser_texte_lecon(titre, max_len=260)
    prob_c = _anonymiser_texte_lecon(probleme, max_len=1500)
    sol_c = _anonymiser_texte_lecon(solution, max_len=2000)
    cause_c = _anonymiser_texte_lecon(cause, max_len=1000)
    inter_c = _anonymiser_texte_lecon(interdits, max_len=1000)
    verif_c = _anonymiser_texte_lecon(verification, max_len=500)
    lang_c = (langage or "").strip().lower()[:60]
    tags_c = _anonymiser_texte_lecon(tags, max_len=300)
    sc_c = (scope or "global").strip().lower()[:80] or "global"
    conf_c = max(0.0, min(1.0, float(confiance)))
    if not titre_c or not prob_c or not sol_c:
        return 0

    conn = get_connexion()
    maintenant = _maintenant_iso()
    with _VERROU, conn:
        existante = conn.execute(
            "SELECT id, confiance FROM recettes_code WHERE lower(trim(titre)) = ? AND lower(trim(langage)) = ? LIMIT 1;",
            (titre_c.lower(), lang_c),
        ).fetchone()
        if existante:
            rid = int(existante["id"])
            nouvelle_conf = min(1.0, max(float(existante["confiance"] or 0.65), conf_c) + 0.05)
            conn.execute("""
                UPDATE recettes_code
                SET probleme = ?, cause = ?, solution = ?, tags = ?, scope = ?,
                    interdits = ?, verification = ?, confiance = ?, source = ?,
                    statut = 'active', mis_a_jour_a = ?
                WHERE id = ?;
            """, (prob_c, cause_c, sol_c, tags_c, sc_c, inter_c, verif_c, nouvelle_conf, source, maintenant, rid))
        else:
            cur = conn.execute("""
                INSERT INTO recettes_code(
                    titre, langage, probleme, cause, solution, tags,
                    scope, interdits, verification, confiance, utilisations, echecs, source, statut,
                    cree_a, mis_a_jour_a
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 'active', ?, ?);
            """, (titre_c, lang_c, prob_c, cause_c, sol_c, tags_c, sc_c, inter_c, verif_c, conf_c, source, maintenant, maintenant))
            rid = int(cur.lastrowid or 0)
    if sync_auto:
        pousser_synchro_asynchrone()
    return rid


def evaluer_lecon(rid: int, succes: bool) -> Dict[str, Any]:
    """Met a jour le score de confiance d'une lecon et l'auto-archive si elle echoue repetitivement."""
    conn = get_connexion()
    maintenant = _maintenant_iso()
    with _VERROU, conn:
        row = conn.execute("SELECT id, confiance, utilisations, echecs, statut FROM recettes_code WHERE id = ?;", (rid,)).fetchone()
        if not row:
            return {"ok": False}
        conf = float(row["confiance"] if row["confiance"] is not None else 0.65)
        uses = int(row["utilisations"] or 0)
        fails = int(row["echecs"] or 0)
        if succes:
            uses += 1
            conf = min(1.0, round(conf + 0.12, 3))
        else:
            fails += 1
            conf = max(0.0, round(conf - 0.25, 3))
        statut = "archived" if (conf < 0.30 or fails >= 3) else "active"
        conn.execute("""
            UPDATE recettes_code
            SET confiance = ?, utilisations = ?, echecs = ?, statut = ?, mis_a_jour_a = ?
            WHERE id = ?;
        """, (conf, uses, fails, statut, maintenant, rid))
    return {"ok": True, "id": rid, "confiance": conf, "utilisations": uses, "echecs": fails, "statut": statut}


def lister_lecons_gouvernees(
    statut: str = "",
    scope: str = "",
    requete: str = "",
    limite: int = 80,
) -> List[Dict[str, Any]]:
    """Retourne les lecons avec metadonnees de gouvernance pour inspection/gestion."""
    conn = get_connexion()
    clauses = ["1=1"]
    params: List[Any] = []
    if statut.strip():
        clauses.append("lower(COALESCE(statut, 'active')) = ?")
        params.append(statut.strip().lower())
    if scope.strip():
        clauses.append("lower(COALESCE(scope, 'global')) LIKE ?")
        params.append(f"{scope.strip().lower()}%")
    if requete.strip():
        motif = f"%{requete.strip()}%"
        clauses.append("(titre LIKE ? OR probleme LIKE ? OR solution LIKE ? OR interdits LIKE ? OR tags LIKE ?)")
        params.extend([motif, motif, motif, motif, motif])
    params.append(int(limite))
    sql = f"""
        SELECT id, titre, langage, probleme, cause, solution, tags,
               COALESCE(scope, 'global') AS scope,
               COALESCE(interdits, '') AS interdits,
               COALESCE(verification, '') AS verification,
               COALESCE(confiance, 0.65) AS confiance,
               COALESCE(utilisations, 0) AS utilisations,
               COALESCE(echecs, 0) AS echecs,
               COALESCE(source, 'dev') AS source,
               COALESCE(statut, 'active') AS statut,
               cree_a, COALESCE(mis_a_jour_a, cree_a) AS mis_a_jour_a
        FROM recettes_code
        WHERE {' AND '.join(clauses)}
        ORDER BY CASE WHEN COALESCE(statut, 'active') = 'active' THEN 0 ELSE 1 END,
                 COALESCE(confiance, 0.65) DESC, id DESC
        LIMIT ?;
    """
    with _VERROU:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def changer_statut_lecon(rid: int, action: str) -> bool:
    """Action sur une lecon : 'active', 'archived', 'promote_global', 'boost'."""
    conn = get_connexion()
    act = (action or "").strip().lower()
    maintenant = _maintenant_iso()
    with _VERROU, conn:
        if act == "active":
            cur = conn.execute("UPDATE recettes_code SET statut = 'active', mis_a_jour_a = ? WHERE id = ?;", (maintenant, rid))
        elif act == "archived":
            cur = conn.execute("UPDATE recettes_code SET statut = 'archived', mis_a_jour_a = ? WHERE id = ?;", (maintenant, rid))
        elif act == "promote_global":
            cur = conn.execute("UPDATE recettes_code SET scope = 'global', statut = 'active', confiance = MAX(COALESCE(confiance, 0.65), 0.85), mis_a_jour_a = ? WHERE id = ?;", (maintenant, rid))
        elif act == "boost":
            cur = conn.execute("UPDATE recettes_code SET confiance = MIN(1.0, COALESCE(confiance, 0.65) + 0.15), statut = 'active', mis_a_jour_a = ? WHERE id = ?;", (maintenant, rid))
        else:
            return False
        return cur.rowcount > 0


def supprimer_lecon(rid: int) -> bool:
    """Supprime definitivement une lecon de la base locale."""
    conn = get_connexion()
    with _VERROU, conn:
        row = conn.execute("SELECT titre, langage FROM recettes_code WHERE id = ?;", (rid,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM recettes_code WHERE id = ?;", (rid,))
        conn.execute(
            "INSERT OR REPLACE INTO memoire_tombstones(kind, mem_key, deleted_at) VALUES ('recipe', ?, ?);",
            (_cle_recette(row["titre"], row["langage"]), _maintenant_iso()),
        )
        return True


def purger_lecons_obsoletes(min_confiance: float = 0.30) -> int:
    """Archive toutes les lecons dont la confiance est passee sous le seuil."""
    conn = get_connexion()
    with _VERROU, conn:
        cur = conn.execute(
            "UPDATE recettes_code SET statut = 'archived', mis_a_jour_a = ? WHERE COALESCE(statut, 'active') = 'active' AND (COALESCE(confiance, 0.65) < ? OR COALESCE(echecs, 0) >= 3);",
            (_maintenant_iso(), float(min_confiance)),
        )
        return cur.rowcount or 0


def statistiques_gouvernance_memoire() -> Dict[str, Any]:
    conn = get_connexion()
    with _VERROU:
        row = conn.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN COALESCE(statut, 'active') = 'active' THEN 1 ELSE 0 END) AS actives,
                   SUM(CASE WHEN COALESCE(statut, 'active') = 'archived' THEN 1 ELSE 0 END) AS archivees,
                   SUM(CASE WHEN COALESCE(source, 'dev') = 'antigravity_mentor' THEN 1 ELSE 0 END) AS mentor_count,
                   ROUND(AVG(CASE WHEN COALESCE(statut, 'active') = 'active' THEN COALESCE(confiance, 0.65) END), 3) AS conf_moy
            FROM recettes_code;
        """).fetchone()
        return {
            "total": int(row["total"] or 0),
            "actives": int(row["actives"] or 0),
            "archivees": int(row["archivees"] or 0),
            "mentor_count": int(row["mentor_count"] or 0),
            "confiance_moyenne": float(row["conf_moy"] or 0.0),
        }


def exporter_playbook_public(
    chemin_sortie: Optional[Path] = None,
    min_confiance: float = 0.70,
) -> Dict[str, Any]:
    """Exporte uniquement les lecons globales/stack eprouvees et anonymisees pour distribution publique."""
    lecons = lister_lecons_gouvernees(statut="active", limite=500)
    exportables = []
    for l in lecons:
        sc = str(l.get("scope") or "global").lower()
        if sc.startswith("project:"):
            continue
        if float(l.get("confiance") or 0.0) < min_confiance:
            continue
        exportables.append({
            "titre": _anonymiser_texte_lecon(l["titre"], 260),
            "langage": l.get("langage") or "dev",
            "scope": sc,
            "probleme": _anonymiser_texte_lecon(l["probleme"], 1500),
            "cause": _anonymiser_texte_lecon(l.get("cause") or "", 1000),
            "solution": _anonymiser_texte_lecon(l["solution"], 2000),
            "interdits": _anonymiser_texte_lecon(l.get("interdits") or "", 1000),
            "verification": _anonymiser_texte_lecon(l.get("verification") or "", 500),
            "tags": l.get("tags") or "",
            "confiance": round(float(l.get("confiance") or 0.7), 3),
        })
    cible = Path(chemin_sortie) if chemin_sortie else (RACINE / "data" / "riot_playbook_public.json")
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(
        json.dumps({"version": 1, "lecons": exportables}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "fichier": str(cible), "exportees": len(exportables)}


def importer_playbook_public(chemin_source: Optional[Path] = None) -> int:
    """Importe un playbook public JSON dans la base locale sans ecraser les lecons plus fiables."""
    cible = Path(chemin_source) if chemin_source else (RACINE / "data" / "riot_playbook_public.json")
    if not cible.exists():
        return 0
    try:
        brut = json.loads(cible.read_text(encoding="utf-8"))
        liste = brut.get("lecons") if isinstance(brut, dict) else []
        if not isinstance(liste, list):
            return 0
        ajoutes = 0
        for item in liste:
            if not isinstance(item, dict) or not item.get("titre") or not item.get("solution"):
                continue
            rid = enregistrer_lecon_mentor(
                titre=str(item["titre"]),
                probleme=str(item.get("probleme") or item["titre"]),
                solution=str(item["solution"]),
                cause=str(item.get("cause") or ""),
                langage=str(item.get("langage") or "dev"),
                tags=str(item.get("tags") or ""),
                scope=str(item.get("scope") or "global"),
                interdits=str(item.get("interdits") or ""),
                verification=str(item.get("verification") or ""),
                source="curated",
                confiance=float(item.get("confiance") or 0.78),
                sync_auto=False,
            )
            if rid:
                ajoutes += 1
        return ajoutes
    except Exception:
        return 0


def _auto_importer_playbook_si_nouveau(conn: sqlite3.Connection) -> None:
    """Importe automatiquement data/riot_playbook_public.json si nouveau ou mis a jour."""
    cible = RACINE / "data" / "riot_playbook_public.json"
    if not cible.exists() or not cible.is_file():
        return
    try:
        import hashlib
        contenu = cible.read_bytes()
        empreinte = hashlib.sha256(contenu).hexdigest()[:24]
        row = conn.execute("SELECT valeur FROM memoire_meta WHERE cle = 'playbook_public_hash';").fetchone()
        if row and str(row["valeur"]) == empreinte:
            return
        importer_playbook_public(cible)
        with _VERROU, conn:
            conn.execute(
                "INSERT OR REPLACE INTO memoire_meta(cle, valeur) VALUES ('playbook_public_hash', ?);",
                (empreinte,),
            )
    except Exception:
        pass


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


# ---------------------------------------------------------------------------
# SYNCHRONISATION CLOUD HYBRIDE (SQLite <-> RIOT Gateway / Neon Postgres)
# ---------------------------------------------------------------------------

def _config_cloud() -> Tuple[str, str]:
    """Retourne (base_url, token) si la synchro cloud est configurée et active."""
    if os.environ.get("RIOT_MEMORY_SYNC", "1").strip() == "0":
        return "", ""
    try:
        from core.config import reglage
        url = (
            os.environ.get("RIOT_GATEWAY_URL", "")
            or str(reglage("gateway.url", "") or "")
            or "https://riot-engine-proxy.onrender.com/v1"
        ).strip().rstrip("/")
        tok = (os.environ.get("RIOT_GATEWAY_TOKEN", "") or str(reglage("gateway.token", "") or "")).strip()
    except Exception:
        url = os.environ.get("RIOT_GATEWAY_URL", "").strip().rstrip("/")
        tok = os.environ.get("RIOT_GATEWAY_TOKEN", "").strip()
    if not tok:
        return "", ""
    base = url[:-3] if url.endswith("/v1") else url
    return base.rstrip("/"), tok


def _get_meta(cle: str, defaut: str = "") -> str:
    conn = get_connexion()
    with _VERROU:
        row = conn.execute("SELECT valeur FROM memoire_meta WHERE cle = ?;", (cle,)).fetchone()
        return str(row["valeur"]) if row else defaut


def _set_meta(cle: str, valeur: str) -> None:
    conn = get_connexion()
    with _VERROU, conn:
        conn.execute(
            "INSERT INTO memoire_meta(cle, valeur) VALUES (?, ?) "
            "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur;",
            (cle, str(valeur)),
        )


def collecter_items_locaux() -> List[Dict[str, Any]]:
    """Exporte entités, recettes et tombstones locaux au format de synchro unifié."""
    conn = get_connexion()
    items: List[Dict[str, Any]] = []
    with _VERROU:
        for row in conn.execute(
            "SELECT categorie, cle, contenu, mis_a_jour_a FROM memoire_entites ORDER BY id ASC;"
        ).fetchall():
            items.append({
                "kind": f"entity:{row['categorie']}",
                "mem_key": row["cle"],
                "content": _masquer_texte(row["contenu"]),
                "metadata": {"categorie": row["categorie"]},
                "deleted": False,
                "updated_at": row["mis_a_jour_a"] or _maintenant_iso(),
            })

        for row in conn.execute(
            "SELECT titre, langage, probleme, cause, solution, tags, cree_a, mis_a_jour_a "
            "FROM recettes_code ORDER BY id ASC;"
        ).fetchall():
            meta = {
                "titre": _masquer_texte(row["titre"], 300),
                "langage": row["langage"] or "",
                "probleme": _masquer_texte(row["probleme"], 2000),
                "cause": _masquer_texte(row["cause"] or "", 1500),
                "solution": _masquer_texte(row["solution"], 3000),
                "tags": _masquer_texte(row["tags"] or "", 300),
            }
            items.append({
                "kind": "recipe",
                "mem_key": _cle_recette(row["titre"], row["langage"] or ""),
                "content": f"{meta['titre']} : {meta['solution']}",
                "metadata": meta,
                "deleted": False,
                "updated_at": row["mis_a_jour_a"] or row["cree_a"] or _maintenant_iso(),
            })

        for row in conn.execute(
            "SELECT kind, mem_key, deleted_at FROM memoire_tombstones;"
        ).fetchall():
            items.append({
                "kind": row["kind"],
                "mem_key": row["mem_key"],
                "content": "",
                "metadata": {},
                "deleted": True,
                "updated_at": row["deleted_at"],
            })
    return items


def appliquer_items_cloud(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """Fusionne les items reçus du Cloud en local selon Last-Write-Wins."""
    if not items:
        return {"appliques": 0, "supprimes": 0}
    conn = get_connexion()
    appliques = 0
    supprimes = 0
    with _VERROU, conn:
        for it in items:
            if not isinstance(it, dict):
                continue
            kind = str(it.get("kind") or "").strip()
            mem_key = str(it.get("mem_key") or "").strip()
            if not kind or not mem_key:
                continue
            deleted = bool(it.get("deleted", False))
            ts = str(it.get("updated_at") or _maintenant_iso())

            if kind.startswith("entity:"):
                cat = kind.split(":", 1)[1].strip().lower()
                if deleted:
                    cur = conn.execute(
                        "DELETE FROM memoire_entites WHERE categorie = ? AND cle = ? AND mis_a_jour_a <= ?;",
                        (cat, mem_key, ts),
                    )
                    if cur.rowcount > 0:
                        supprimes += 1
                    conn.execute("""
                        INSERT INTO memoire_tombstones(kind, mem_key, deleted_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(kind, mem_key) DO UPDATE SET
                            deleted_at = CASE
                                WHEN excluded.deleted_at > memoire_tombstones.deleted_at
                                THEN excluded.deleted_at ELSE memoire_tombstones.deleted_at
                            END;
                    """, (kind, mem_key, ts))
                else:
                    ex = conn.execute(
                        "SELECT mis_a_jour_a FROM memoire_entites WHERE categorie = ? AND cle = ?;",
                        (cat, mem_key),
                    ).fetchone()
                    if ex and (ex["mis_a_jour_a"] or "") > ts:
                        continue
                    tomb = conn.execute(
                        "SELECT deleted_at FROM memoire_tombstones WHERE kind = ? AND mem_key = ?;",
                        (kind, mem_key),
                    ).fetchone()
                    if tomb and (tomb["deleted_at"] or "") > ts:
                        continue
                    contenu = _masquer_texte(str(it.get("content") or ""))
                    if not contenu:
                        continue
                    conn.execute("""
                        INSERT INTO memoire_entites(categorie, cle, contenu, cree_a, mis_a_jour_a)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(categorie, cle) DO UPDATE SET
                            contenu = excluded.contenu,
                            mis_a_jour_a = excluded.mis_a_jour_a;
                    """, (cat, mem_key, contenu, ts, ts))
                    conn.execute(
                        "DELETE FROM memoire_tombstones WHERE kind = ? AND mem_key = ?;",
                        (kind, mem_key),
                    )
                    appliques += 1

            elif kind == "recipe":
                meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
                titre = _masquer_texte(str(meta.get("titre") or mem_key.split("::", 1)[-1]), 300)
                lang = str(meta.get("langage") or (mem_key.split("::", 1)[0] if "::" in mem_key else "")).strip().lower()
                if deleted:
                    cur = conn.execute(
                        "DELETE FROM recettes_code WHERE lower(trim(titre)) = ? AND lower(trim(langage)) = ?;",
                        (titre.lower(), lang),
                    )
                    if cur.rowcount > 0:
                        supprimes += 1
                    conn.execute("""
                        INSERT INTO memoire_tombstones(kind, mem_key, deleted_at)
                        VALUES ('recipe', ?, ?)
                        ON CONFLICT(kind, mem_key) DO UPDATE SET deleted_at = excluded.deleted_at;
                    """, (mem_key, ts))
                else:
                    prob = _masquer_texte(str(meta.get("probleme") or it.get("content") or ""), 2000)
                    sol = _masquer_texte(str(meta.get("solution") or it.get("content") or ""), 3000)
                    cause = _masquer_texte(str(meta.get("cause") or ""), 1500)
                    tags = _masquer_texte(str(meta.get("tags") or ""), 300)
                    if not titre or not sol:
                        continue
                    ex = conn.execute(
                        "SELECT id, mis_a_jour_a FROM recettes_code WHERE lower(trim(titre)) = ? AND lower(trim(langage)) = ? LIMIT 1;",
                        (titre.lower(), lang),
                    ).fetchone()
                    if ex:
                        if (ex["mis_a_jour_a"] or "") > ts:
                            continue
                        conn.execute("""
                            UPDATE recettes_code
                            SET probleme = ?, cause = ?, solution = ?, tags = ?, mis_a_jour_a = ?
                            WHERE id = ?;
                        """, (prob, cause, sol, tags, ts, int(ex["id"])))
                    else:
                        conn.execute("""
                            INSERT INTO recettes_code(titre, langage, probleme, cause, solution, tags, cree_a, mis_a_jour_a)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                        """, (titre, lang, prob, cause, sol, tags, ts, ts))
                    conn.execute("DELETE FROM memoire_tombstones WHERE kind = 'recipe' AND mem_key = ?;", (mem_key,))
                    appliques += 1

    return {"appliques": appliques, "supprimes": supprimes}


def synchroniser_cloud(timeout: float = 8.0) -> Dict[str, Any]:
    """Synchronise la mémoire SQLite locale avec la passerelle Cloud RIOT / Neon."""
    base_url, tok = _config_cloud()
    if not base_url or not tok:
        return {"ok": False, "raison": "non_connecte"}

    with _SYNC_LOCK:
        try:
            import requests
            since = _get_meta("cloud_last_sync", "")
            locaux = collecter_items_locaux()
            r = requests.post(
                f"{base_url}/v1/memory/sync",
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                json={"items": locaux, "since": since},
                timeout=timeout,
            )
            if r.status_code != 200:
                return {"ok": False, "status_code": r.status_code, "erreur": r.text[:200]}
            data = r.json()
            res_merge = appliquer_items_cloud(data.get("items") or [])
            server_time = str(data.get("server_time") or _maintenant_iso())
            _set_meta("cloud_last_sync", server_time)
            return {
                "ok": True,
                "envoyes": len(locaux),
                "recus": len(data.get("items") or []),
                "appliques": res_merge["appliques"],
                "supprimes": res_merge["supprimes"],
                "server_time": server_time,
            }
        except Exception as e:
            LOG.debug("Synchro mémoire cloud ignorée : %s", e)
            return {"ok": False, "erreur": str(e)}


def pousser_synchro_asynchrone(min_interval_sec: float = 2.0) -> None:
    """Lance une synchro Cloud non bloquante en tâche de fond (anti-rafale)."""
    global _DERNIERE_SYNC_THREAD
    base_url, tok = _config_cloud()
    if not base_url or not tok:
        return
    now = time.time()
    if now - _DERNIERE_SYNC_THREAD < min_interval_sec:
        return
    _DERNIERE_SYNC_THREAD = now
    threading.Thread(target=synchroniser_cloud, daemon=True, name="riot-memory-sync").start()


def lancer_synchro_arriere_plan() -> None:
    """Déclenche une synchro initiale non bloquante (au démarrage CLI/IDE/login)."""
    pousser_synchro_asynchrone(min_interval_sec=0.0)


def etat_synchro_cloud() -> Dict[str, Any]:
    """Retourne l'état courant de la mémoire locale et de sa configuration Cloud."""
    base_url, tok = _config_cloud()
    conn = get_connexion()
    with _VERROU:
        nb_ent = conn.execute("SELECT COUNT(*) FROM memoire_entites;").fetchone()[0]
        nb_rec = conn.execute("SELECT COUNT(*) FROM recettes_code;").fetchone()[0]
    return {
        "db_path": str(DB_PATH),
        "cloud_actif": bool(base_url and tok),
        "gateway": base_url or None,
        "derniere_synchro": _get_meta("cloud_last_sync", "") or None,
        "nb_entites": int(nb_ent),
        "nb_recettes": int(nb_rec),
    }


# ---------------------------------------------------------------------------
# AUTO-EXTRACTION SILENCIEUSE TYPE HERMES AGENT (POST-ÉCHANGE)
# ---------------------------------------------------------------------------

_RE_SIGNAL_MEMOIRE = re.compile(
    r"(?i)\b("
    r"je\s+pr[eé]f[eè]re|toujours|jamais|retiens|m[eé]morise|rappelle-toi|"
    r"mon\s+projet|mon\s+pc|notre\s+stack|nous\s+utilisons|j'utilise|je\s+travaille|"
    r"r[eè]gle|convention|dor[eé]navant|[aà]\s+l'avenir|ne\s+fais\s+plus|"
    r"corrig[eé]|r[eé]solu|traceback|exception|erreur\s+http|pytest|bug\s+fix[eé]|"
    r"correctif|patch\s+appliqu[eé]"
    r")\b"
)


def _echange_merite_memoire(
    user_msg: str,
    assistant_msg: str,
    surface: str = "cli",
    forcer: bool = False,
) -> bool:
    """Filtre heuristique strict pour éviter d'appeler un LLM sur des échanges triviaux."""
    if os.environ.get("RIOT_AUTO_MEMORY", "1").strip() == "0":
        return False
    try:
        from core.config import reglage
        if reglage("memoire.auto_extract", True) is False:
            return False
    except Exception:
        pass

    u = (user_msg or "").strip()
    a = (assistant_msg or "").strip()
    if len(u) < 20 or len(a) < 40:
        return False
    if u.startswith("/"):
        return False

    # Anti-empoisonnement : ne jamais mémoriser un tour où l'assistant a échoué ou refusé d'agir
    a_low = a.lower()
    if any(
        m in a_low
        for m in (
            "[erreur]",
            "je ne peux pas directement",
            "je ne peux pas piloter",
            "je ne peux pas accéder",
            "impossible de",
            "impossible d'",
            "i cannot",
            "i can't",
        )
    ):
        return False

    explicite = bool(re.search(r"(?i)\b(retiens|m[eé]morise|je\s+pr[eé]f[eè]re|dor[eé]navant|r[eè]gle)\b", u))
    if not forcer and not explicite and not _RE_SIGNAL_MEMOIRE.search(f"{u}\n{a[:900]}"):
        return False

    if not forcer and not explicite:
        if time.time() - _DERNIERE_AUTO_EXTRACTION < _AUTO_EXTRACT_COOLDOWN_SEC:
            return False
    return True


def _parser_json_memoire(texte: str) -> Dict[str, Any]:
    """Extrait proprement un JSON {entities: [...], recipes: [...]} d'une sortie LLM."""
    brut = (texte or "").strip()
    if not brut:
        return {"entities": [], "recipes": []}
    m_bloc = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", brut, re.DOTALL)
    if m_bloc:
        brut = m_bloc.group(1)
    else:
        debut, fin = brut.find("{"), brut.rfind("}")
        if debut != -1 and fin > debut:
            brut = brut[debut:fin + 1]
    try:
        data = json.loads(brut)
        if isinstance(data, dict):
            return {
                "entities": data.get("entities") if isinstance(data.get("entities"), list) else [],
                "recipes": data.get("recipes") if isinstance(data.get("recipes"), list) else [],
            }
    except Exception:
        pass
    return {"entities": [], "recipes": []}


def extraire_et_memoriser_depuis_echange(
    user_msg: str,
    assistant_msg: str,
    surface: str = "cli",
    forcer: bool = False,
    provider: Any = None,
) -> Dict[str, int]:
    """Analyse un échange terminé et enregistre silencieusement faits/règles/recettes durables."""
    global _DERNIERE_AUTO_EXTRACTION
    if not _echange_merite_memoire(user_msg, assistant_msg, surface=surface, forcer=forcer):
        return {"entities": 0, "recipes": 0}

    _DERNIERE_AUTO_EXTRACTION = time.time()
    try:
        if provider is None:
            from core.llm import llm
            provider = llm()
        if not provider or not provider.disponible():
            return {"entities": 0, "recipes": 0}
    except Exception:
        return {"entities": 0, "recipes": 0}

    u_clean = _masquer_texte(user_msg, max_len=1200)
    a_clean = _masquer_texte(assistant_msg, max_len=1800)

    sys_prompt = (
        "Tu es un extracteur silencieux de mémoire long terme. "
        "Extrais UNIQUEMENT les informations durables utiles pour les futures sessions "
        "(préférences utilisateur EXPLICITEMENT exprimées par l'utilisateur, projets actifs, personnes/proches, "
        "règles de dev strictes, ou recettes de résolution de bugs réellement résolus). "
        "N'invente rien. N'enregistre JAMAIS une préférence négative ou restriction déduite d'un refus "
        "ou d'une incapacité de l'assistant. N'inclus JAMAIS de clés API, tokens, mots de passe ou détails éphémères. "
        "Réponds STRICTEMENT en JSON valide sans texte autour :\n"
        '{"entities": [{"categorie": "preferences|projects|people|facts|regles_dev", "cle": "etiquette_courte", "contenu": "..."}], '
        '"recipes": [{"titre": "...", "langage": "python|ts|sql|...", "probleme": "...", "cause": "...", "solution": "...", "tags": "tag1,tag2"}]}'
    )
    user_prompt = f"[Surface: {surface}]\nUtilisateur: {u_clean}\nAssistant: {a_clean}"

    try:
        rep = provider.repondre(sys_prompt, [{"role": "user", "content": user_prompt}], [])
        texte_rep = " ".join(
            getattr(b, "text", "") for b in getattr(rep, "content", [])
            if getattr(b, "type", None) == "text"
        ).strip()
    except Exception as e:
        LOG.debug("Auto-extraction mémoire ignorée : %s", e)
        return {"entities": 0, "recipes": 0}

    extrait = _parser_json_memoire(texte_rep)
    cats_valides = {"preferences", "projects", "people", "facts", "regles_dev"}
    nb_ent = 0
    nb_rec = 0

    for ent in extrait["entities"][:5]:
        if not isinstance(ent, dict):
            continue
        cat = str(ent.get("categorie") or "facts").strip().lower()
        if cat not in cats_valides:
            cat = "facts"
        cle = str(ent.get("cle") or "").strip()
        contenu = str(ent.get("contenu") or "").strip()
        if len(contenu) >= 6:
            memoriser_entite(cat, cle, contenu, sync_auto=False)
            nb_ent += 1

    for rec in extrait["recipes"][:2]:
        if not isinstance(rec, dict):
            continue
        titre = str(rec.get("titre") or "").strip()
        prob = str(rec.get("probleme") or "").strip()
        sol = str(rec.get("solution") or "").strip()
        if titre and prob and sol:
            ajouter_recette_code(
                titre=titre,
                probleme=prob,
                solution=sol,
                cause=str(rec.get("cause") or "").strip(),
                langage=str(rec.get("langage") or "").strip(),
                tags=str(rec.get("tags") or "").strip(),
                sync_auto=False,
            )
            nb_rec += 1

    if nb_ent or nb_rec:
        pousser_synchro_asynchrone()
    return {"entities": nb_ent, "recipes": nb_rec}


def lancer_auto_memoire_asynchrone(user_msg: str, assistant_msg: str, surface: str = "cli") -> None:
    """Déclenche l'auto-extraction de mémoire en tâche de fond sans ralentir la réponse."""
    if not _echange_merite_memoire(user_msg, assistant_msg, surface=surface, forcer=False):
        return
    threading.Thread(
        target=extraire_et_memoriser_depuis_echange,
        args=(user_msg, assistant_msg),
        kwargs={"surface": surface, "forcer": True},
        daemon=True,
        name="riot-auto-memory",
    ).start()
