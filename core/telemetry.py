"""Module de telemetrie, audit prompts/reponses et alertes temps reel pour RIOT.

Supporte deux backends transparents :
  1. Neon PostgreSQL (RIOT_TELEMETRY_DATABASE_URL / RIOT_PORTAL_DATABASE_URL) pour la prod Render
  2. SQLite WAL bornee (~/.riot/telemetry.db) en mode local hors ligne

Securite & Confidentialite :
  - Masque automatiquement les cles API, tokens Bearer et secrets .env avant stockage.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SECRET_PATTERNS = [
    (re.compile(r"\b(sk-(?:proj-|ant-|or-[a-z0-9-]+-)?[A-Za-z0-9_-]{16,})\b"), "[SECRET_KEY]"),
    (re.compile(r"\b(AIza[0-9A-Za-z_-]{25,})\b"), "[GOOGLE_KEY]"),
    (re.compile(r"\b(gsk_[A-Za-z0-9]{16,})\b"), "[GROQ_KEY]"),
    (re.compile(r"\b(vcp_[A-Za-z0-9_-]{16,}|vercel_[A-Za-z0-9_-]{16,})\b"), "[VERCEL_TOKEN]"),
    (re.compile(r"\b(mstrl_[A-Za-z0-9_-]{16,}|csk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{16,}|xai-[A-Za-z0-9_-]{16,})\b"), "[PROVIDER_KEY]"),
    (re.compile(r"\b(npm_[A-Za-z0-9]{16,})\b"), "[NPM_TOKEN]"),
    (re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[GH_TOKEN]"),
    (re.compile(r"\b(riot_cli_[A-Za-z0-9]{16,})\b"), "[RIOT_TOKEN]"),
    (re.compile(r"\b(freellmapi-[A-Za-z0-9_-]{16,})\b"), "[FREELLMAPI_KEY]"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._-]{16,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^:\s]+:)[^@\s]+(@)", re.IGNORECASE), r"\1[REDACTED]\2"),
    (re.compile(r"(?im)^([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|DSN)\s*=\s*)(.+)$"), r"\1[REDACTED]"),
]

_ALERT_LOCK = threading.Lock()
_LAST_ALERTS: Dict[str, float] = {}


def masquer_secrets(texte: str, max_len: int = 4000) -> str:
    """Redacte les secrets evidents dans un prompt ou une reponse avant journalisation."""
    if not texte:
        return ""
    out = str(texte)
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    if len(out) > max_len:
        out = out[:max_len] + "\n... [tronque]"
    return out


class TelemetryStore:
    """Stockage Neon Postgres (si configure) ou SQLite WAL pour logs LLM et releases."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_lignes: int = 5000,
        retention_jours: int = 30,
        telemetry_pg_url: Optional[str] = None,
        portal_pg_url: Optional[str] = None,
    ):
        self.telemetry_pg_url = (
            telemetry_pg_url
            if telemetry_pg_url is not None
            else os.environ.get("RIOT_TELEMETRY_DATABASE_URL", "")
        ).strip()
        self.portal_pg_url = (
            portal_pg_url
            if portal_pg_url is not None
            else (
                os.environ.get("RIOT_PORTAL_DATABASE_URL", "").strip()
                or self.telemetry_pg_url
            )
        ).strip()

        env_db = os.environ.get("RIOT_TELEMETRY_DB", "").strip()
        if db_path is not None:
            self.db_path = Path(db_path)
        elif env_db:
            self.db_path = Path(env_db)
        else:
            self.db_path = Path.home() / ".riot" / "telemetry.db"

        self.max_lignes = max_lignes
        self.retention_jours = retention_jours
        self._lock = threading.Lock()
        self._pg_ready = False
        self.backend_name = "neon-postgres" if self.telemetry_pg_url else "sqlite"
        self._init_db()

    # ------------------------------------------------------------------ connexions

    def _connect_sqlite(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_pg(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=8)

    def _init_db(self) -> None:
        if self.telemetry_pg_url:
            try:
                with self._connect_pg(self.telemetry_pg_url) as conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS llm_events (
                            id              BIGSERIAL PRIMARY KEY,
                            ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            source          TEXT NOT NULL DEFAULT 'proxy',
                            user_ref        TEXT NOT NULL DEFAULT '',
                            profil          TEXT NOT NULL DEFAULT 'riot-auto',
                            provider_reel   TEXT NOT NULL DEFAULT '',
                            modele_reel     TEXT NOT NULL DEFAULT '',
                            ok              BOOLEAN NOT NULL DEFAULT TRUE,
                            status_code     INTEGER NOT NULL DEFAULT 200,
                            latence_ms      INTEGER NOT NULL DEFAULT 0,
                            tokens_in       INTEGER NOT NULL DEFAULT 0,
                            tokens_out      INTEGER NOT NULL DEFAULT 0,
                            prompt_extrait  TEXT NOT NULL DEFAULT '',
                            reponse_extrait TEXT NOT NULL DEFAULT '',
                            erreur          TEXT NOT NULL DEFAULT ''
                        )
                        """
                    )
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_events_ts ON llm_events (ts DESC)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_events_user ON llm_events (user_ref, ts DESC)")

                if self.portal_pg_url:
                    with self._connect_pg(self.portal_pg_url) as pconn:
                        pconn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS releases (
                                id           SERIAL PRIMARY KEY,
                                version      TEXT NOT NULL UNIQUE,
                                titre        TEXT NOT NULL,
                                notes        TEXT NOT NULL,
                                commande     TEXT NOT NULL DEFAULT 'npm install -g @riotlagrinta/riot@latest',
                                is_published BOOLEAN NOT NULL DEFAULT TRUE,
                                published_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        pconn.execute(
                            """
                            INSERT INTO releases (version, titre, notes, commande)
                            VALUES (
                                '0.3.1',
                                'RIOT v0.3.1 — IDE Agentique, Mode Opaque & Logo Spirale',
                                E'• RIOT IDE multi-panneaux (CodeMirror, diff coloré Accepter/Rejeter, terminal, Ctrl+P)\\n• 3 thèmes au choix (Obsidian & Ambre, Encre & Émeraude, Tactical Ops)\\n• Moteur opaque RIOT Engine & passerelle Cloud dédiée',
                                'npm install -g @riotlagrinta/riot@latest'
                            )
                            ON CONFLICT (version) DO NOTHING
                            """
                        )
                        pconn.execute(
                            """
                            INSERT INTO releases (version, titre, notes, commande)
                            VALUES (
                                '0.3.3',
                                'RIOT v0.3.3 — Mémoire Hybride Neon, Web Anti-Hallucination & Connecteurs MCP',
                                E'• Mémoire long terme hybride SQLite (~/.riot) + Neon PostgreSQL & auto-extraction silencieuse\\n• Recherche Internet sourcée & lecture web Firecrawl/Perplexity/DDG (/v1/web/search & /v1/web/scrape)\\n• Catalogue de 15 connecteurs MCP prêts en 1 commande (/mcp catalog, /mcp add firecrawl/github/supabase...)',
                                'npm install -g @riotlagrinta/riot@latest'
                            )
                            ON CONFLICT (version) DO NOTHING
                            """
                        )
                        pconn.execute(
                            """
                            INSERT INTO releases (version, titre, notes, commande)
                            VALUES (
                                '0.3.4',
                                'RIOT v0.3.4 — Sélection Adaptative de Modèles, Anti-Boucles & Pilotage PC/Remotion',
                                E'• Sélection adaptative automatique du modèle par requête (fast / agent / code / deep)\\n• Pilotage complet Windows, Remotion & FFmpeg dans Studio/CLI avec garde-fous anti-boucles et fallback navigateur\\n• Protection anti-empoisonnement mémoire & déclenchement strict de grill-me',
                                'npm install -g @riotlagrinta/riot@latest'
                            )
                            ON CONFLICT (version) DO NOTHING
                            """
                        )
                        pconn.execute(
                            """
                            INSERT INTO releases (version, titre, notes, commande)
                            VALUES (
                                '0.3.5',
                                'RIOT v0.3.5 — Protection Tokens Vercel, Anti-Saturation Quotas & Contexte Compact',
                                E'• Masquage strict des tokens Vercel (vcp_/vercel_), provider keys et secrets en télémétrie & mémoire\\n• Routage adaptatif affiné : auto-mémoire sur modèle rapide, contexte long orienté Gemini avant Groq/OpenRouter\\n• Compactage automatique de l\\'historique Studio pour rester sous les limites TPM et éviter les bascules lentes',
                                'npm install -g @riotlagrinta/riot@latest'
                            )
                            ON CONFLICT (version) DO NOTHING
                            """
                        )
                        pconn.execute(
                            """
                            INSERT INTO releases (version, titre, notes, commande)
                            VALUES (
                                '0.3.6',
                                'RIOT v0.3.6 — Pool Multi-Clés, Rotation Intra-Groq 28k TPM & Schémas Compacts',
                                E'• Rotation multi-modèles intra-Groq (gpt-oss-120b -> llama-3.3-70b-versatile 12k TPM -> gpt-oss-20b) + failover HTTP 413\\n• Support pool multi-clés Round-Robin (GROQ_API_KEY="cle1,cle2", MISTRAL_API_KEY, etc.)\\n• Compression automatique (-45%) des schémas d\\'outils et de l\\'historique en CLI, IDE, Studio et Proxy',
                                'npm install -g @riotlagrinta/riot@latest'
                            )
                            ON CONFLICT (version) DO NOTHING
                            """
                        )
                        pconn.execute(
                            """
                            INSERT INTO releases (version, titre, notes, commande)
                            VALUES (
                                '0.3.7',
                                'RIOT v0.3.7 — Agent Codeur Renforcé (Auto-Ancrage, Patch Souple, 10 Tours & max_tokens 4096)',
                                E'• Auto-ancrage du dossier projet actif dans CLI, Studio, terminal et explorer_projet + détection de stack\\n• patcher_code tolérant aux espaces de fin de ligne + indices de lignes proches\\n• Boucle agentique étendue à 10 tours avec synthèse finale garantie et max_tokens porté à 4096',
                                'npm install -g @riotlagrinta/riot@latest'
                            )
                            ON CONFLICT (version) DO NOTHING
                            """
                        )
                        pconn.execute(
                            """
                            INSERT INTO releases (version, titre, notes, commande)
                            VALUES (
                                '0.3.8',
                                'RIOT v0.3.8 — Accès Illimité 24h, Sous-Agents Spécialisés, Continuité & FreeLLMAPI',
                                E'• Accès 24h illimité sans plafond journalier (protection anti-rafale RPM conservée)\\n• Chaque sous-agent piloté par son modèle optimal (Codestral/Sonnet 4.5 en code jusqu\\'à 8 192 tokens, GPT-OSS/Llama 3.3 en agent, Nemotron 838k en contexte XXL)\\n• Journal de Continuité inter-modèles + support natif FreeLLMAPI (127.0.0.1:31415/v1)',
                                'npm install -g @riotlagrinta/riot@latest'
                            )
                            ON CONFLICT (version) DO NOTHING
                            """
                        )
                self._pg_ready = True
                return
            except Exception as e:
                # Bascule de secours SQLite uniquement si Postgres injoignable au boot
                self.backend_name = f"sqlite-fallback ({type(e).__name__})"

        with self._lock:
            conn = self._connect_sqlite()
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts REAL NOT NULL,
                        source TEXT NOT NULL,
                        client_id TEXT DEFAULT '',
                        profil TEXT DEFAULT '',
                        provider_reel TEXT DEFAULT '',
                        modele_reel TEXT DEFAULT '',
                        ok INTEGER NOT NULL,
                        status_code INTEGER DEFAULT 200,
                        latence_ms INTEGER DEFAULT 0,
                        tokens_in INTEGER DEFAULT 0,
                        tokens_out INTEGER DEFAULT 0,
                        prompt_extrait TEXT DEFAULT '',
                        reponse_extrait TEXT DEFAULT '',
                        erreur TEXT DEFAULT ''
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_events_ts ON llm_events(ts DESC);")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS releases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts REAL NOT NULL,
                        version TEXT UNIQUE NOT NULL,
                        titre TEXT NOT NULL,
                        notes TEXT NOT NULL,
                        commande TEXT DEFAULT 'npm install -g @riotlagrinta/riot@latest'
                    )
                    """
                )
                cnt = conn.execute("SELECT COUNT(*) FROM releases").fetchone()[0]
                if cnt == 0:
                    conn.execute(
                        "INSERT INTO releases (ts, version, titre, notes, commande) VALUES (?, ?, ?, ?, ?)",
                        (
                            time.time(),
                            "0.3.8",
                            "RIOT v0.3.8 — Accès Illimité 24h, Sous-Agents Spécialisés, Continuité & FreeLLMAPI",
                            "• Accès 24h illimité sans plafond journalier (protection anti-rafale RPM conservée)\n"
                            "• Chaque sous-agent piloté par son modèle optimal (Codestral/Sonnet 4.5 en code jusqu'à 8 192 tokens, GPT-OSS/Llama 3.3 en agent, Nemotron 838k en contexte XXL)\n"
                            "• Journal de Continuité inter-modèles + support natif FreeLLMAPI (127.0.0.1:31415/v1)",
                            "npm install -g @riotlagrinta/riot@latest",
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------ ecriture

    def enregistrer(
        self,
        *,
        source: str,
        client_id: str = "",
        profil: str = "",
        provider_reel: str = "",
        modele_reel: str = "",
        ok: bool = True,
        status_code: int = 200,
        latence_ms: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        prompt: str = "",
        reponse: str = "",
        erreur: str = "",
    ) -> None:
        log_contenu = os.environ.get("RIOT_LOG_CONTENT", "1").strip() != "0"
        prompt_safe = masquer_secrets(prompt, 4000) if log_contenu else "[journalisation contenu desactivee]"
        rep_safe = masquer_secrets(reponse, 4000) if log_contenu else ""
        err_safe = masquer_secrets(erreur, 1200)

        if self._pg_ready and self.telemetry_pg_url:
            with self._connect_pg(self.telemetry_pg_url) as conn:
                conn.execute(
                    """
                    INSERT INTO llm_events (
                        source, user_ref, profil, provider_reel, modele_reel,
                        ok, status_code, latence_ms, tokens_in, tokens_out,
                        prompt_extrait, reponse_extrait, erreur
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source[:32],
                        str(client_id)[:120],
                        str(profil)[:48],
                        str(provider_reel)[:48],
                        str(modele_reel)[:96],
                        bool(ok),
                        int(status_code),
                        int(latence_ms),
                        int(tokens_in or 0),
                        int(tokens_out or 0),
                        prompt_safe,
                        rep_safe,
                        err_safe,
                    ),
                )
            return

        now = time.time()
        with self._lock:
            conn = self._connect_sqlite()
            try:
                conn.execute(
                    """
                    INSERT INTO llm_events (
                        ts, source, client_id, profil, provider_reel, modele_reel,
                        ok, status_code, latence_ms, tokens_in, tokens_out,
                        prompt_extrait, reponse_extrait, erreur
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now,
                        source[:32],
                        str(client_id)[:120],
                        str(profil)[:48],
                        str(provider_reel)[:48],
                        str(modele_reel)[:96],
                        1 if ok else 0,
                        int(status_code),
                        int(latence_ms),
                        int(tokens_in or 0),
                        int(tokens_out or 0),
                        prompt_safe,
                        rep_safe,
                        err_safe,
                    ),
                )
                seuil_ts = now - (self.retention_jours * 86400)
                conn.execute("DELETE FROM llm_events WHERE ts < ?", (seuil_ts,))
                conn.execute(
                    """
                    DELETE FROM llm_events WHERE id NOT IN (
                        SELECT id FROM llm_events ORDER BY id DESC LIMIT ?
                    )
                    """,
                    (self.max_lignes,),
                )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------ quotas & lecture

    def compter_requetes_utilisateur_24h(self, user_ref: str) -> int:
        if not user_ref:
            return 0
        if self._pg_ready and self.telemetry_pg_url:
            with self._connect_pg(self.telemetry_pg_url) as conn:
                row = conn.execute(
                    "SELECT COUNT(*)::int AS total FROM llm_events WHERE user_ref = %s AND ts >= NOW() - INTERVAL '24 hours'",
                    (user_ref,),
                ).fetchone()
                return int(row["total"]) if row else 0

        depuis = time.time() - 86400
        with self._lock:
            conn = self._connect_sqlite()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM llm_events WHERE client_id = ? AND ts >= ?",
                    (user_ref, depuis),
                ).fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

    def metriques(self, heures: int = 24) -> Dict[str, Any]:
        if self._pg_ready and self.telemetry_pg_url:
            depuis_dt = datetime.now(timezone.utc) - timedelta(hours=max(1, heures))
            with self._connect_pg(self.telemetry_pg_url) as conn:
                rows = conn.execute(
                    "SELECT * FROM llm_events WHERE ts >= %s ORDER BY ts DESC LIMIT 5000",
                    (depuis_dt,),
                ).fetchall()
        else:
            depuis = time.time() - (max(1, heures) * 3600)
            with self._lock:
                conn = self._connect_sqlite()
                try:
                    rows = conn.execute(
                        "SELECT * FROM llm_events WHERE ts >= ? ORDER BY ts DESC",
                        (depuis,),
                    ).fetchall()
                finally:
                    conn.close()

        total = len(rows)
        succes = sum(1 for r in rows if bool(r["ok"]))
        erreurs = total - succes
        latences = sorted(int(r["latence_ms"] or 0) for r in rows if r["latence_ms"] is not None)
        moy_lat = int(sum(latences) / len(latences)) if latences else 0
        p95_lat = latences[int(0.95 * (len(latences) - 1))] if latences else 0
        tin = sum(int(r["tokens_in"] or 0) for r in rows)
        tout = sum(int(r["tokens_out"] or 0) for r in rows)

        par_provider: Dict[str, Dict[str, int]] = {}
        par_source: Dict[str, int] = {}
        err_list: List[Dict[str, Any]] = []
        for r in rows:
            pk = f"{r['provider_reel'] or 'RIOT'} / {r['modele_reel'] or '-'}"
            st = par_provider.setdefault(pk, {"total": 0, "erreurs": 0})
            st["total"] += 1
            if not bool(r["ok"]):
                st["erreurs"] += 1
                if len(err_list) < 12:
                    ts_val = r["ts"]
                    iso_str = (
                        ts_val.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                        if isinstance(ts_val, datetime)
                        else datetime.fromtimestamp(float(ts_val), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    )
                    err_list.append({
                        "id": r["id"],
                        "iso": iso_str,
                        "source": r["source"],
                        "provider": pk,
                        "status_code": r["status_code"],
                        "erreur": r["erreur"],
                    })
            src = r["source"] or "local"
            par_source[src] = par_source.get(src, 0) + 1

        return {
            "ok": True,
            "backend": self.backend_name,
            "fenetre_heures": heures,
            "total": total,
            "succes": succes,
            "erreurs": erreurs,
            "taux_succes_pct": round((succes / total) * 100, 1) if total else 100.0,
            "latence_moy_ms": moy_lat,
            "latence_p95_ms": p95_lat,
            "tokens_in": tin,
            "tokens_out": tout,
            "par_provider": par_provider,
            "par_source": par_source,
            "dernieres_erreurs": err_list,
        }

    def lister_logs(self, limit: int = 80, only_errors: bool = False, q: str = "") -> List[Dict[str, Any]]:
        lim = min(max(1, int(limit)), 500)
        if self._pg_ready and self.telemetry_pg_url:
            clauses = []
            params: List[Any] = []
            if only_errors:
                clauses.append("ok = FALSE")
            if q.strip():
                like = f"%{q.strip()}%"
                clauses.append("(prompt_extrait ILIKE %s OR reponse_extrait ILIKE %s OR erreur ILIKE %s OR modele_reel ILIKE %s OR user_ref ILIKE %s)")
                params.extend([like, like, like, like, like])
            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"SELECT * FROM llm_events {where_sql} ORDER BY id DESC LIMIT %s"
            params.append(lim)
            with self._connect_pg(self.telemetry_pg_url) as conn:
                rows = conn.execute(sql, tuple(params)).fetchall()
        else:
            clauses = []
            params = []
            if only_errors:
                clauses.append("ok = 0")
            if q.strip():
                like = f"%{q.strip()}%"
                clauses.append("(prompt_extrait LIKE ? OR reponse_extrait LIKE ? OR erreur LIKE ? OR modele_reel LIKE ? OR client_id LIKE ?)")
                params.extend([like, like, like, like, like])
            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"SELECT * FROM llm_events {where_sql} ORDER BY id DESC LIMIT ?"
            params.append(lim)
            with self._lock:
                conn = self._connect_sqlite()
                try:
                    rows = conn.execute(sql, params).fetchall()
                finally:
                    conn.close()

        out: List[Dict[str, Any]] = []
        for r in rows:
            ts_val = r["ts"]
            if isinstance(ts_val, datetime):
                ts_num = ts_val.timestamp()
                iso_str = ts_val.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts_num = float(ts_val)
                iso_str = datetime.fromtimestamp(ts_num, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            client_val = r["user_ref"] if isinstance(r, dict) and "user_ref" in r else r["client_id"]
            out.append({
                "id": r["id"],
                "ts": ts_num,
                "iso": iso_str,
                "source": r["source"],
                "client_id": client_val,
                "profil": r["profil"],
                "provider_reel": r["provider_reel"],
                "modele_reel": r["modele_reel"],
                "ok": bool(r["ok"]),
                "status_code": r["status_code"],
                "latence_ms": r["latence_ms"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "prompt": r["prompt_extrait"],
                "reponse": r["reponse_extrait"],
                "erreur": r["erreur"],
            })
        return out

    # ------------------------------------------------------------------ releases

    def publier_release(self, version: str, titre: str, notes: str, commande: str = "") -> Dict[str, Any]:
        ver = (version or "").strip().lstrip("v")
        tit = (titre or "").strip() or f"RIOT v{ver}"
        not_txt = (notes or "").strip()
        cmd = (commande or "").strip() or "npm install -g @riotlagrinta/riot@latest"
        if not ver:
            raise ValueError("Numero de version requis.")

        if self._pg_ready and self.portal_pg_url:
            with self._connect_pg(self.portal_pg_url) as conn:
                conn.execute(
                    """
                    INSERT INTO releases (version, titre, notes, commande, is_published, published_at)
                    VALUES (%s, %s, %s, %s, TRUE, NOW())
                    ON CONFLICT (version) DO UPDATE SET
                        titre = EXCLUDED.titre,
                        notes = EXCLUDED.notes,
                        commande = EXCLUDED.commande,
                        is_published = TRUE,
                        published_at = NOW()
                    """,
                    (ver[:32], tit[:160], not_txt[:8000], cmd[:200]),
                )
            return {"ok": True, "version": ver, "titre": tit, "notes": not_txt, "commande": cmd}

        now = time.time()
        with self._lock:
            conn = self._connect_sqlite()
            try:
                conn.execute(
                    """
                    INSERT INTO releases (ts, version, titre, notes, commande)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(version) DO UPDATE SET
                        ts=excluded.ts, titre=excluded.titre, notes=excluded.notes, commande=excluded.commande
                    """,
                    (now, ver[:32], tit[:160], not_txt[:8000], cmd[:200]),
                )
                conn.commit()
            finally:
                conn.close()
        return {"ok": True, "version": ver, "titre": tit, "notes": not_txt, "commande": cmd}

    def lister_releases(self, limit: int = 20) -> List[Dict[str, Any]]:
        lim = min(max(1, int(limit)), 100)
        if self._pg_ready and self.portal_pg_url:
            with self._connect_pg(self.portal_pg_url) as conn:
                rows = conn.execute(
                    "SELECT id, version, titre, notes, commande, published_at FROM releases WHERE is_published = TRUE ORDER BY published_at DESC, id DESC LIMIT %s",
                    (lim,),
                ).fetchall()
            return [
                {
                    "id": r["id"],
                    "version": r["version"],
                    "titre": r["titre"],
                    "notes": r["notes"],
                    "commande": r["commande"],
                    "date": r["published_at"].astimezone(timezone.utc).strftime("%Y-%m-%d")
                    if isinstance(r["published_at"], datetime)
                    else str(r["published_at"])[:10],
                }
                for r in rows
            ]

        with self._lock:
            conn = self._connect_sqlite()
            try:
                rows = conn.execute(
                    "SELECT * FROM releases ORDER BY ts DESC, id DESC LIMIT ?",
                    (lim,),
                ).fetchall()
            finally:
                conn.close()
        return [
            {
                "id": r["id"],
                "version": r["version"],
                "titre": r["titre"],
                "notes": r["notes"],
                "commande": r["commande"],
                "date": datetime.fromtimestamp(r["ts"], tz=timezone.utc).strftime("%Y-%m-%d"),
            }
            for r in rows
        ]

    def derniere_release(self) -> Optional[Dict[str, Any]]:
        rels = self.lister_releases(limit=1)
        return rels[0] if rels else None

    def statut_public(self, heures: int = 24) -> Dict[str, Any]:
        m = self.metriques(heures=heures)
        taux = float(m.get("taux_succes_pct", 100.0))
        etat = "operational" if taux >= 95.0 else ("degraded" if taux >= 75.0 else "outage")
        return {
            "ok": True,
            "etat": etat,
            "disponibilite_pct": taux,
            "latence_moy_ms": m.get("latence_moy_ms", 0),
            "requetes_24h": m.get("total", 0),
        }


_DEFAULT_STORE: Optional[TelemetryStore] = None


def store_defaut() -> TelemetryStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = TelemetryStore()
    return _DEFAULT_STORE


def _ntfy_ascii_header(texte: str, max_len: int = 120) -> str:
    """Nettoie une chaine pour les entetes HTTP ntfy (ASCII pur sans UnicodeEncodeError)."""
    import unicodedata

    norm = unicodedata.normalize("NFKD", str(texte or ""))
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split())[:max_len] or "RIOT Monitor"


def envoyer_alerte_ntfy(
    titre: str,
    details: str,
    *,
    priority: str = "default",
    tags: str = "bell",
    cle_cooldown: str = "",
    cooldown_sec: int = 0,
    ntfy_url: Optional[str] = None,
    ntfy_token: Optional[str] = None,
    sync: bool = False,
) -> Dict[str, Any]:
    """Envoie une notification temps reel vers un topic ntfy (https://ntfy.sh/<topic>)."""
    url = (ntfy_url or os.environ.get("RIOT_NTFY_URL", "")).strip()
    if not url:
        return {"ok": False, "sent": False, "detail": "RIOT_NTFY_URL non configuree."}

    if cle_cooldown and cooldown_sec > 0:
        now = time.time()
        with _ALERT_LOCK:
            prev = _LAST_ALERTS.get(f"ntfy:{cle_cooldown}", 0.0)
            if now - prev < cooldown_sec:
                return {"ok": True, "sent": False, "detail": "Cooldown actif."}
            _LAST_ALERTS[f"ntfy:{cle_cooldown}"] = now

    prio = priority if priority in ("min", "low", "default", "high", "urgent") else "default"
    body_bytes = masquer_secrets(details or titre, 1800).encode("utf-8")
    headers = {
        "Title": _ntfy_ascii_header(titre),
        "Priority": prio,
        "Tags": _ntfy_ascii_header(tags, 80),
        "Content-Type": "text/plain; charset=utf-8",
        "User-Agent": "RIOT-Monitor/1.0",
    }
    tok = (ntfy_token or os.environ.get("RIOT_NTFY_TOKEN", "")).strip()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    def _dispatch() -> Dict[str, Any]:
        try:
            req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"ok": True, "sent": True, "status": getattr(resp, "status", 200)}
        except Exception as e:
            return {"ok": False, "sent": False, "detail": str(e)}

    if sync:
        return _dispatch()

    threading.Thread(target=_dispatch, daemon=True, name="riot-ntfy-alert").start()
    return {"ok": True, "sent": True, "queued": True}


def envoyer_alerte_webhook(
    titre: str,
    details: str,
    cle_cooldown: str = "generic",
    cooldown_sec: int = 60,
    webhook_url: Optional[str] = None,
    priority: str = "high",
    tags: str = "warning",
) -> None:
    """Envoie une alerte non-bloquante vers Discord/Slack/Webhook custom ET ntfy (avec anti-spam)."""
    envoyer_alerte_ntfy(
        titre,
        details,
        priority=priority,
        tags=tags,
        cle_cooldown=cle_cooldown,
        cooldown_sec=cooldown_sec,
    )

    url = (webhook_url or os.environ.get("RIOT_ALERT_WEBHOOK_URL", "")).strip()
    if not url:
        return
    now = time.time()
    with _ALERT_LOCK:
        prev = _LAST_ALERTS.get(cle_cooldown, 0.0)
        if now - prev < cooldown_sec:
            return
        _LAST_ALERTS[cle_cooldown] = now

    msg = f"**[RIOT MONITOR] {titre}**\n{masquer_secrets(details, 1400)}"

    def _send():
        try:
            body = json.dumps({"content": msg, "text": msg, "title": titre, "details": details}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "RIOT-Monitor/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4):
                pass
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True, name="riot-webhook-alert").start()
