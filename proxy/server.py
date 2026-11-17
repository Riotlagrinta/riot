"""Passerelle Cloud RIOT Engine (Proxy OpenAI-compatible + API Releases/Monitoring pour Portail Externe).

Toutes les cles fournisseurs (Groq, Mistral, Gemini, OpenRouter) restent uniquement
dans les variables d'environnement du serveur. Les clients finaux ne connaissent ni
les cles ni les modeles reels : le proxy renvoie toujours `"model": "riot-engine"`.

Endpoints publics :
  - GET  /health           -> sante passerelle
  - GET  /status/public    -> disponibilite + latence agregee (zero prompt/modele expose)
  - GET  /releases         -> notes de versions publiees
  - GET  /releases/latest  -> derniere version officielle (pour core/updater.py)

Endpoints Createur (proteges par RIOT_ADMIN_TOKEN) :
  - GET  /admin/metrics    -> KPIs detailles par provider/modele/erreur
  - GET  /admin/logs       -> prompts (secrets redactes), reponses IA et erreurs
  - POST /admin/releases   -> publier ou mettre a jour une release officielle
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.telemetry import TelemetryStore, envoyer_alerte_ntfy, envoyer_alerte_webhook

app = FastAPI(title="RIOT Engine Gateway")

_ORIGINS_RAW = os.environ.get("RIOT_PORTAL_ORIGIN", "*").strip()
_ORIGINS = [o.strip() for o in _ORIGINS_RAW.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RATE_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)
_MAX_REQ_PER_MIN = int(os.environ.get("RIOT_PROXY_RPM", "30"))
_STORE = TelemetryStore(db_path=Path(os.environ.get("RIOT_TELEMETRY_DB", str(Path.home() / ".riot" / "proxy_telemetry.db"))))


@app.on_event("startup")
def _notifier_demarrage():
    actifs = len(_routes_pour_profil("riot-auto"))
    envoyer_alerte_ntfy(
        "RIOT Proxy demarre",
        f"Service en ligne ({_STORE.backend_name}) · {actifs} routes IA actives.",
        priority="low",
        tags="rocket,green_circle",
        cle_cooldown="proxy_startup",
        cooldown_sec=30,
    )


def _verifier_jeton_neon(raw_token: str) -> Optional[Dict[str, Any]]:
    id_url = os.environ.get("RIOT_IDENTITY_DATABASE_URL", "").strip()
    if not id_url or not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(id_url, autocommit=True, row_factory=dict_row, connect_timeout=8) as conn:
        row = conn.execute(
            """
            SELECT u.id::text AS user_id, u.email, u.display_name, u.plan, u.daily_quota,
                   u.is_active, t.id::text AS token_id
            FROM client_tokens t
            INNER JOIN users u ON u.id = t.user_id
            WHERE t.token_hash = %s
              AND t.revoked_at IS NULL
              AND (t.expires_at IS NULL OR t.expires_at > NOW())
              AND u.is_active = TRUE
            LIMIT 1
            """,
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        try:
            conn.execute("UPDATE client_tokens SET last_used_at = NOW() WHERE id = %s::uuid", (row["token_id"],))
        except Exception:
            pass
        return dict(row)


def _verifier_acces_detail(request: Request) -> Dict[str, Any]:
    expected = os.environ.get("RIOT_PROXY_TOKEN", "").strip()
    id_url = os.environ.get("RIOT_IDENTITY_DATABASE_URL", "").strip()
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""

    identite: Dict[str, Any]
    if id_url:
        if expected and token and hmac.compare_digest(token, expected):
            identite = {
                "user_ref": "creator-master",
                "email": "creator@riot.local",
                "display_name": "Créateur RIOT",
                "plan": "team",
                "daily_quota": 100000,
            }
        else:
            row = _verifier_jeton_neon(token)
            if not row:
                envoyer_alerte_ntfy(
                    "RIOT Securite : acces refuse (401)",
                    "Tentative de requete sans jeton valide sur RIOT Engine.",
                    priority="high",
                    tags="lock,warning",
                    cle_cooldown="auth_401",
                    cooldown_sec=60,
                )
                raise HTTPException(
                    status_code=401,
                    detail="Connexion RIOT requise. Créez un jeton sur https://riot-portal.vercel.app/account puis lancez `riot login`.",
                )
            identite = {
                "user_ref": f"{row['email']} ({row['user_id'][:8]})",
                "email": row["email"],
                "display_name": row["display_name"] or row["email"],
                "plan": row["plan"],
                "daily_quota": int(row["daily_quota"] or 40),
            }
    else:
        if expected and not hmac.compare_digest(token, expected):
            raise HTTPException(status_code=401, detail="Jeton client RIOT invalide.")
        raw_id = token or (request.client.host if request.client else "anon")
        identite = {
            "user_ref": hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:12],
            "email": "local@riot",
            "display_name": "Local",
            "plan": "free",
            "daily_quota": 10000,
        }

    cle_hash = identite["user_ref"]
    now = time.time()
    q = _RATE_WINDOWS[cle_hash]
    while q and now - q[0] > 60.0:
        q.popleft()
    if len(q) >= _MAX_REQ_PER_MIN:
        raise HTTPException(status_code=429, detail="Quota de requêtes par minute dépassé.")
    q.append(now)

    used_24h = _STORE.compter_requetes_utilisateur_24h(cle_hash)
    if used_24h >= identite["daily_quota"]:
        envoyer_alerte_ntfy(
            "RIOT Quota journalier atteint",
            f"Utilisateur : {cle_hash} ({identite['plan']}) · {used_24h}/{identite['daily_quota']} requêtes sur 24h.",
            priority="high",
            tags="hourglass,warning",
            cle_cooldown=f"quota_{cle_hash}",
            cooldown_sec=120,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Quota journalier atteint ({used_24h}/{identite['daily_quota']} requêtes sur le plan {identite['plan']}).",
        )
    identite["used_24h"] = used_24h
    return identite


def _verifier_acces(request: Request) -> str:
    return _verifier_acces_detail(request)["user_ref"]


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
    return {
        "ok": True,
        "service": "RIOT Engine Gateway",
        "routes_actives": actifs,
        "telemetry_backend": _STORE.backend_name,
        "identity_auth": bool(os.environ.get("RIOT_IDENTITY_DATABASE_URL", "").strip()),
    }


@app.get("/auth/verify")
def auth_verify(request: Request):
    identite = _verifier_acces_detail(request)
    envoyer_alerte_ntfy(
        "RIOT Auth : poste connecte",
        f"Utilisateur : {identite['display_name']} ({identite['email']})\nPlan : {identite['plan']} · Quota : {identite['used_24h']}/{identite['daily_quota']} req/24h",
        priority="default",
        tags="key,white_check_mark",
        cle_cooldown=f"verify_{identite['email']}",
        cooldown_sec=30,
    )
    return {
        "ok": True,
        "model": "riot-engine",
        "user": {
            "email": identite["email"],
            "display_name": identite["display_name"],
            "plan": identite["plan"],
            "daily_quota": identite["daily_quota"],
            "used_24h": identite["used_24h"],
        },
    }


@app.get("/status/public")
def public_status(heures: int = 24):
    st = _STORE.statut_public(heures=heures)
    st["routes_actives"] = len(_routes_pour_profil("riot-auto")) > 0
    return st


@app.get("/releases")
def public_releases(limit: int = 20):
    return {"ok": True, "releases": _STORE.lister_releases(limit=limit)}


@app.get("/releases/latest")
def public_latest_release():
    rel = _STORE.derniere_release()
    if not rel:
        return {"ok": True, "version": "0.3.1", "release": None}
    return {"ok": True, "version": rel["version"], "release": rel}


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
            try:
                from core.key_quota import capturer_reponse
                capturer_reponse(c["provider"], c["key"], c["model"], r.status_code, dict(r.headers))
            except Exception:
                pass
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
            tin = usage.get("prompt_tokens", 0) or 0
            tout = usage.get("completion_tokens", 0) or 0
            _STORE.enregistrer(
                source="proxy",
                client_id=client_hash,
                profil=profil,
                provider_reel=c["provider"],
                modele_reel=c["model"],
                ok=True,
                status_code=200,
                latence_ms=lat_ms,
                tokens_in=tin,
                tokens_out=tout,
                prompt=prompt_user,
                reponse=_extraire_reponse_texte(data),
            )
            if os.environ.get("RIOT_NTFY_ALL_REQUESTS", "1").strip() != "0":
                envoyer_alerte_ntfy(
                    f"RIOT IA : {c['provider']} ({lat_ms}ms)",
                    f"Client : {client_hash}\nProfil : {profil} → {c['provider']} / {c['model']}\nTokens : {tin} in + {tout} out",
                    priority="low",
                    tags="zap,robot",
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
        priority="urgent",
        tags="rotating_light,skull",
    )
    raise HTTPException(status_code=502, detail=f"Moteur RIOT temporairement sature ({derniere_err}).")


@app.get("/admin/metrics")
def admin_metrics(request: Request, heures: int = 24):
    _verifier_admin(request)
    return _STORE.metriques(heures=heures)


@app.get("/admin/logs")
def admin_logs(request: Request, limit: int = 80, only_errors: bool = False, q: str = ""):
    _verifier_admin(request)
    return {"ok": True, "logs": _STORE.lister_logs(limit=limit, only_errors=only_errors, q=q)}


@app.get("/admin/keys")
def admin_keys(request: Request, sonder: bool = True):
    _verifier_admin(request)
    from core.key_quota import inspecter_cles
    res = inspecter_cles(sonder=sonder)
    if sonder:
        en_panne = [c for c in res.get("cles", []) if c.get("etat") not in ("OK", "Non sondée")]
        if en_panne:
            detail_err = "\n".join(f"• {c['provider']} ({c['cle_masquee']}) : {c['etat']}" for c in en_panne)
            envoyer_alerte_ntfy(
                "RIOT Cles API : alerte quota/erreur",
                detail_err,
                priority="high",
                tags="key,warning",
                cle_cooldown="keys_probe_warn",
                cooldown_sec=30,
            )
    return res


@app.post("/admin/releases")
async def admin_publish_release(request: Request):
    _verifier_admin(request)
    body = await request.json() or {}
    try:
        res = _STORE.publier_release(
            version=str(body.get("version", "")),
            titre=str(body.get("titre", "")),
            notes=str(body.get("notes", "")),
            commande=str(body.get("commande", "")),
        )
        envoyer_alerte_ntfy(
            f"RIOT Release v{res['version']} publiee",
            f"{res['titre']}\n{res['notes'][:400]}",
            priority="default",
            tags="tada,package",
        )
        return JSONResponse(res)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/admin/ntfy/test")
def admin_ntfy_test(request: Request):
    _verifier_admin(request)
    res = envoyer_alerte_ntfy(
        "RIOT Monitor : test en direct",
        "Notification de test envoyée avec succès depuis la passerelle Render !",
        priority="default",
        tags="white_check_mark,bell",
        sync=True,
    )
    if not res.get("sent"):
        raise HTTPException(status_code=400, detail=res.get("detail") or "Envoi ntfy impossible.")
    return res
