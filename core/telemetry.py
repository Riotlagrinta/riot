"""Module de telemetrie, audit prompts/reponses et alertes temps reel pour RIOT.

Concu 100% en bibliotheque standard Python (zéro dependance externe) afin d'etre
utilisable autant cote client local (CLI / IDE / Studio) que sur la passerelle
Cloud `proxy/server.py` (Render / Railway).

Securite & Confidentialite :
  - Masque automatiquement les cles API, tokens Bearer et secrets .env avant stockage.
  - Stockage SQLite WAL borne (purge auto par retention/volume) pour eviter toute saturation disque.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SECRET_PATTERNS = [
    (re.compile(r"\b(sk-(?:proj-)?[A-Za-z0-9_-]{16,})\b"), "[SECRET_KEY]"),
    (re.compile(r"\b(AIza[0-9A-Za-z_-]{25,})\b"), "[GOOGLE_KEY]"),
    (re.compile(r"\b(gsk_[A-Za-z0-9]{16,})\b"), "[GROQ_KEY]"),
    (re.compile(r"\b(npm_[A-Za-z0-9]{16,})\b"), "[NPM_TOKEN]"),
    (re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[GH_TOKEN]"),
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
    """Stockage SQLite WAL bornee pour logs LLM (prompts, reponses, latence, erreurs)."""

    def __init__(self, db_path: Optional[Path] = None, max_lignes: int = 5000, retention_jours: int = 30):
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
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
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
                            "0.3.1",
                            "RIOT v0.3.1 — IDE Agentique, Mode Opaque & Logo Spirale",
                            "• RIOT IDE multi-panneaux (CodeMirror, diff coloré Accepter/Rejeter, terminal, Ctrl+P)\n"
                            "• 3 thèmes au choix (Obsidian & Ambre, Encre & Émeraude, Tactical Ops)\n"
                            "• Moteur opaque RIOT Engine & passerelle Cloud dédiée",
                            "npm install -g @riotlagrinta/riot@latest",
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

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
        now = time.time()

        with self._lock:
            conn = self._connect()
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
                        str(client_id)[:64],
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

    def metriques(self, heures: int = 24) -> Dict[str, Any]:
        depuis = time.time() - (max(1, heures) * 3600)
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM llm_events WHERE ts >= ? ORDER BY ts DESC",
                    (depuis,),
                ).fetchall()
            finally:
                conn.close()

        total = len(rows)
        succes = sum(1 for r in rows if r["ok"] == 1)
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
            if r["ok"] == 0:
                st["erreurs"] += 1
                if len(err_list) < 12:
                    err_list.append({
                        "id": r["id"],
                        "iso": datetime.fromtimestamp(r["ts"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "source": r["source"],
                        "provider": pk,
                        "status_code": r["status_code"],
                        "erreur": r["erreur"],
                    })
            src = r["source"] or "local"
            par_source[src] = par_source.get(src, 0) + 1

        return {
            "ok": True,
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
        clauses = []
        params: List[Any] = []
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
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()

        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "iso": datetime.fromtimestamp(r["ts"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "source": r["source"],
                "client_id": r["client_id"],
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
            }
            for r in rows
        ]

    def publier_release(self, version: str, titre: str, notes: str, commande: str = "") -> Dict[str, Any]:
        ver = (version or "").strip().lstrip("v")
        tit = (titre or "").strip() or f"RIOT v{ver}"
        not_txt = (notes or "").strip()
        cmd = (commande or "").strip() or "npm install -g @riotlagrinta/riot@latest"
        if not ver:
            raise ValueError("Numero de version requis.")
        now = time.time()
        with self._lock:
            conn = self._connect()
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
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM releases ORDER BY ts DESC, id DESC LIMIT ?",
                    (min(max(1, int(limit)), 100),),
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


def envoyer_alerte_webhook(
    titre: str,
    details: str,
    cle_cooldown: str = "generic",
    cooldown_sec: int = 60,
    webhook_url: Optional[str] = None,
) -> None:
    """Envoie une alerte non-bloquante vers Discord/Slack/Webhook custom (avec anti-spam)."""
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
