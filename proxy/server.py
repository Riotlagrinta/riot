"""Passerelle Cloud RIOT Engine (Proxy OpenAI-compatible avec monitoring createur).

Toutes les cles fournisseurs (Groq, Mistral, Gemini, OpenRouter) restent uniquement
dans les variables d'environnement du serveur. Les clients finaux ne connaissent ni
les cles ni les modeles reels : le proxy renvoie toujours `"model": "riot-engine"`.

Monitoring integre (pour les createurs uniquement via RIOT_ADMIN_TOKEN) :
  - Journalisation SQLite WAL des prompts (secrets redactes), reponses IA, latences et erreurs.
  - Alertes webhook temps reel (Discord / Slack / custom) via RIOT_ALERT_WEBHOOK_URL.
  - Dashboard HTML /admin + API JSON /admin/metrics & /admin/logs.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core.telemetry import TelemetryStore, envoyer_alerte_webhook

app = FastAPI(title="RIOT Engine Gateway")

_RACINE = Path(__file__).resolve().parent.parent
_MONITOR_HTML = _RACINE / "web" / "monitor.html"
_RATE_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)
_MAX_REQ_PER_MIN = int(os.environ.get("RIOT_PROXY_RPM", "30"))
_STORE = TelemetryStore(db_path=Path(os.environ.get("RIOT_TELEMETRY_DB", str(Path.home() / ".riot" / "proxy_telemetry.db"))))


def _verifier_acces(request: Request) -> str:
    expected = os.environ.get("RIOT_PROXY_TOKEN", "").strip()
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if expected and not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Jeton client RIOT invalide.")

    raw_id = token or (request.client.host if request.client else "anon")
    cle_hash = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:12]

    now = time.time()
    q = _RATE_WINDOWS[cle_hash]
    while q and now - q[0] > 60.0:
        q.popleft()
    if len(q) >= _MAX_REQ_PER_MIN:
        raise HTTPException(status_code=429, detail="Quota de requetes minute depasse.")
    q.append(now)
    return cle_hash


def _verifier_admin(request: Request) -> None:
    expected = os.environ.get("RIOT_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="RIOT_ADMIN_TOKEN non configure cote serveur.")
    supplied = (request.headers.get("x-admin-token", "") or request.query_params.get("token", "")).strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Acces createur non autorise.")


def _extraire_dernier_prompt(body: Dict[str, Any]) -> str:
    msgs = body.get("messages") or []
    for m in reversed(msgs):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
    return ""


def _extraire_reponse_texte(data: Dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    txt = str(msg.get("content") or "").strip()
    calls = msg.get("tool_calls") or []
    if calls:
        noms = ", ".join(str((c.get("function") or {}).get("name", "?")) for c in calls)
        return f"{txt}\n[tool_calls: {noms}]".strip()
    return txt


def _routes_pour_profil(model_req: str) -> List[Dict[str, str]]:
    """Definit la cascade de fournisseurs secrets cote serveur selon le profil opaque."""
    m = (model_req or "riot-auto").lower()
    mistral = {
        "provider": "Mistral",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "key": os.environ.get("MISTRAL_API_KEY", "").strip(),
        "model": os.environ.get("RIOT_UPSTREAM_CODE_MODEL", "codestral-latest"),
    }
    groq = {
        "provider": "Groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key": os.environ.get("GROQ_API_KEY", "").strip(),
        "model": os.environ.get("RIOT_UPSTREAM_FAST_MODEL", "llama-3.3-70b-versatile"),
    }
    openrouter = {
        "provider": "OpenRouter",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": os.environ.get("OPENROUTER_API_KEY", "").strip(),
        "model": os.environ.get("RIOT_UPSTREAM_DEEP_MODEL", "openrouter/free"),
    }
    gemini = {
        "provider": "Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key": os.environ.get("GEMINI_API_KEY", "").strip(),
        "model": os.environ.get("RIOT_UPSTREAM_GEMINI_MODEL", "gemini-flash-latest"),
    }

    if "fast" in m:
        ordre = [groq, gemini, mistral, openrouter]
    elif "deep" in m:
        ordre = [openrouter, mistral, gemini, groq]
    else:
        ordre = [mistral, groq, gemini, openrouter]
    return [c for c in ordre if c["key"]]


@app.get("/health")
def health():
    actifs = len(_routes_pour_profil("riot-auto"))
    return {"ok": True, "service": "RIOT Engine Gateway", "routes_actives": actifs}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    client_hash = _verifier_acces(request)
    body: Dict[str, Any] = await request.json()
    profil = str(body.get("model", "riot-auto"))
    prompt_user = _extraire_dernier_prompt(body)
    candidats = _routes_pour_profil(profil)
    if not candidats:
        _STORE.enregistrer(
            source="proxy", client_id=client_hash, profil=profil,
            ok=False, status_code=503, prompt=prompt_user,
            erreur="Aucun fournisseur configure cote serveur.",
        )
        raise HTTPException(status_code=503, detail="Aucun fournisseur configure cote serveur.")

    t0 = time.time()
    derniere_err = "Indisponible"
    dernier_statut = 502
    for c in candidats:
        payload = dict(body)
        payload["model"] = c["model"]
        headers = {
            "Authorization": f"Bearer {c['key']}",
            "Content-Type": "application/json",
        }
        try:
            r = requests.post(c["url"], headers=headers, json=payload, timeout=35)
            if r.status_code in (429, 503) or r.status_code >= 500:
                derniere_err = f"{c['provider']} HTTP {r.status_code}"
                dernier_statut = r.status_code
                envoyer_alerte_webhook(
                    f"Failover declenche ({c['provider']})",
                    f"Statut HTTP {r.status_code} sur {c['model']}. Bascule automatique.",
                    cle_cooldown=f"failover_{c['provider']}",
                )
                continue
            r.raise_for_status()
            data = r.json()
            lat_ms = int((time.time() - t0) * 1000)
            usage = data.get("usage") or {}
            _STORE.enregistrer(
                source="proxy",
                client_id=client_hash,
                profil=profil,
                provider_reel=c["provider"],
                modele_reel=c["model"],
                ok=True,
                status_code=200,
                latence_ms=lat_ms,
                tokens_in=usage.get("prompt_tokens", 0) or 0,
                tokens_out=usage.get("completion_tokens", 0) or 0,
                prompt=prompt_user,
                reponse=_extraire_reponse_texte(data),
            )
            data["model"] = "riot-engine"
            return JSONResponse(data)
        except Exception as e:
            derniere_err = f"{c['provider']}: {e}"
            continue

    lat_ms = int((time.time() - t0) * 1000)
    _STORE.enregistrer(
        source="proxy",
        client_id=client_hash,
        profil=profil,
        provider_reel="Cascade",
        modele_reel="-",
        ok=False,
        status_code=dernier_statut,
        latence_ms=lat_ms,
        prompt=prompt_user,
        erreur=derniere_err,
    )
    envoyer_alerte_webhook(
        "Panne critique Cascade IA (502)",
        f"Tous les providers ont echoue. Client={client_hash} | Profil={profil} | Erreur={derniere_err}",
        cle_cooldown="critical_502",
    )
    raise HTTPException(status_code=502, detail=f"Moteur RIOT temporairement sature ({derniere_err}).")


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard():
    if not _MONITOR_HTML.exists():
        return HTMLResponse("<h1>RIOT Monitor</h1><p>web/monitor.html manquant.</p>", status_code=404)
    return HTMLResponse(_MONITOR_HTML.read_text(encoding="utf-8"))


@app.get("/admin/metrics")
def admin_metrics(request: Request, heures: int = 24):
    _verifier_admin(request)
    return _STORE.metriques(heures=heures)


@app.get("/admin/logs")
def admin_logs(request: Request, limit: int = 80, only_errors: bool = False, q: str = ""):
    _verifier_admin(request)
    return {"ok": True, "logs": _STORE.lister_logs(limit=limit, only_errors=only_errors, q=q)}
