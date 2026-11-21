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
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.model_router import profil_vers_tache
from core.telemetry import TelemetryStore, envoyer_alerte_ntfy, envoyer_alerte_webhook, masquer_secrets

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


def _verifier_acces_detail(request: Request, verifier_quota: bool = True) -> Dict[str, Any]:
    expected = os.environ.get("RIOT_PROXY_TOKEN", "").strip()
    id_url = os.environ.get("RIOT_IDENTITY_DATABASE_URL", "").strip()
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""

    identite: Dict[str, Any]
    if id_url:
        if expected and token and hmac.compare_digest(token, expected):
            identite = {
                "user_id": "creator-master",
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
                "user_id": str(row["user_id"]),
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
        uid_local = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]
        identite = {
            "user_id": uid_local,
            "user_ref": uid_local[:12],
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
    if verifier_quota and used_24h >= identite["daily_quota"]:
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


_RR_LOCK = threading.Lock()
_RR_COUNTER = 0


def _extraire_cles_env(var_name: str, rotate: bool = False) -> List[str]:
    """Recupere un pool de cles API depuis VAR, VARS et VAR_1..VAR_5 (separees par virgules/espaces)."""
    global _RR_COUNTER
    brutes: List[str] = []
    for k in (var_name, f"{var_name}S", *[f"{var_name}_{i}" for i in range(1, 6)]):
        val = os.environ.get(k, "").strip()
        if val:
            for morceau in val.replace(";", ",").replace("\n", ",").split(","):
                c = morceau.strip().strip("\"'")
                if c and c not in brutes:
                    brutes.append(c)
    if len(brutes) > 1 and rotate:
        with _RR_LOCK:
             idx = _RR_COUNTER % len(brutes)
             _RR_COUNTER += 1
        brutes = brutes[idx:] + brutes[:idx]
    return brutes


def _compacter_payload_entree(body: Dict[str, Any]) -> Dict[str, Any]:
    """Allege les schemas d'outils et les anciens messages volumineux pour maximiser le budget TPM."""
    out = dict(body)
    tools = out.get("tools")
    if isinstance(tools, list) and tools:
        tools_compacts = []
        for t in tools:
            if not isinstance(t, dict) or not isinstance(t.get("function"), dict):
                tools_compacts.append(t)
                continue
            fn = dict(t["function"])
            desc = " ".join(str(fn.get("description") or "").split())
            if len(desc) > 150:
                fn["description"] = desc[:149].rstrip() + "…"
            params = fn.get("parameters")
            if isinstance(params, dict) and isinstance(params.get("properties"), dict):
                p_copy = dict(params)
                props_out = {}
                for pk, pv in params["properties"].items():
                    if isinstance(pv, dict) and "description" in pv:
                        pv_c = dict(pv)
                        pdesc = " ".join(str(pv_c.get("description") or "").split())
                        if len(pdesc) > 90:
                            pv_c["description"] = pdesc[:89].rstrip() + "…"
                        props_out[pk] = pv_c
                    else:
                        props_out[pk] = pv
                p_copy["properties"] = props_out
                fn["parameters"] = p_copy
            t_copy = dict(t)
            t_copy["function"] = fn
            tools_compacts.append(t_copy)
        out["tools"] = tools_compacts

    msgs = out.get("messages")
    if isinstance(msgs, list) and len(msgs) > 5:
        msgs_compacts = []
        seuil_recent = len(msgs) - 4
        for i, m in enumerate(msgs):
            if not isinstance(m, dict) or i >= seuil_recent or m.get("role") == "system":
                msgs_compacts.append(m)
                continue
            c = m.get("content")
            if isinstance(c, str) and len(c) > 1400:
                m_c = dict(m)
                m_c["content"] = c[:950] + "\n... [historique compacté]\n" + c[-300:]
                msgs_compacts.append(m_c)
            else:
                msgs_compacts.append(m)
        out["messages"] = msgs_compacts
    return out


def _routes_pour_profil(
    model_req: str,
    tache: Optional[str] = None,
    has_tools: bool = False,
    long_context: bool = False,
    rotate_keys: bool = False,
) -> List[Dict[str, str]]:
    """Definit la cascade de fournisseurs/modeles/cles cote serveur selon le profil opaque et la tache.

    Inclut :
      - Pool multi-cles par fournisseur (GROQ_API_KEY="cle1,cle2", GROQ_API_KEY_2, etc.)
      - Rotation multi-modeles intra-Groq (gpt-oss-120b 8k TPM -> llama-3.3-70b-versatile 12k TPM -> gpt-oss-20b)
        pour tripler le quota TPM disponible sur chaque cle Groq avant de basculer.
    """
    m = (tache or profil_vers_tache(model_req or "riot-auto")).lower()
    mistral_models = (
        [
            os.environ.get("RIOT_UPSTREAM_CODE_MODEL", "codestral-latest"),
            os.environ.get("RIOT_UPSTREAM_FAST_MISTRAL_MODEL", "mistral-small-latest"),
        ]
        if m == "code"
        else [
            os.environ.get("RIOT_UPSTREAM_FAST_MISTRAL_MODEL", "mistral-small-latest"),
            os.environ.get("RIOT_UPSTREAM_CODE_MODEL", "codestral-latest"),
        ]
    )
    groq_fast = os.environ.get("RIOT_UPSTREAM_FAST_MODEL", "openai/gpt-oss-20b")
    groq_smart = os.environ.get("RIOT_UPSTREAM_SMART_MODEL", "openai/gpt-oss-120b")
    groq_alt = os.environ.get("RIOT_UPSTREAM_GROQ_ALT_MODEL", "llama-3.3-70b-versatile")
    groq_models = (
        [groq_fast, groq_alt, groq_smart]
        if m == "fast"
        else [groq_smart, groq_alt, groq_fast]
    )

    def _expand(provider: str, url: str, env_var: str, models: List[str]) -> List[Dict[str, str]]:
        cles = _extraire_cles_env(env_var, rotate=rotate_keys)
        if not cles or not url:
            return []
        seen_m: List[str] = []
        for mod in models:
            if mod and mod not in seen_m:
                seen_m.append(mod)
        # On alterne d'abord les cles sur le modele principal, puis sur les modeles secondaires (compteurs TPM distincts)
        items: List[Dict[str, str]] = []
        for mod in seen_m:
            for cle in cles:
                items.append({"provider": provider, "url": url, "key": cle, "model": mod})
        return items

    mistral = _expand("Mistral", "https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY", mistral_models)
    groq = _expand("Groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", groq_models)
    openrouter = _expand(
        "OpenRouter",
        "https://openrouter.ai/api/v1/chat/completions",
        "OPENROUTER_API_KEY",
        [os.environ.get("RIOT_UPSTREAM_DEEP_MODEL", "openrouter/free")],
    )
    gemini = _expand(
        "Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "GEMINI_API_KEY",
        [os.environ.get("RIOT_UPSTREAM_GEMINI_MODEL", "gemini-flash-lite-latest")],
    )
    cerebras = _expand(
        "Cerebras",
        "https://api.cerebras.ai/v1/chat/completions",
        "CEREBRAS_API_KEY",
        [os.environ.get("RIOT_UPSTREAM_CEREBRAS_MODEL", "gpt-oss-120b")],
    )
    nvidia = _expand(
        "NVIDIA",
        "https://integrate.api.nvidia.com/v1/chat/completions",
        "NVIDIA_API_KEY",
        [os.environ.get("RIOT_UPSTREAM_NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")],
    )
    deepseek = _expand(
        "DeepSeek",
        "https://api.deepseek.com/chat/completions",
        "DEEPSEEK_API_KEY",
        [
            os.environ.get(
                "RIOT_UPSTREAM_DEEPSEEK_MODEL",
                "deepseek-reasoner" if (m == "deep" and not has_tools) else "deepseek-chat",
            )
        ],
    )
    together = _expand(
        "Together",
        "https://api.together.xyz/v1/chat/completions",
        "TOGETHER_API_KEY",
        [os.environ.get("RIOT_UPSTREAM_TOGETHER_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")],
    )
    fireworks = _expand(
        "Fireworks",
        "https://api.fireworks.ai/inference/v1/chat/completions",
        "FIREWORKS_API_KEY",
        [os.environ.get("RIOT_UPSTREAM_FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p3-70b-instruct")],
    )
    custom_base = (os.environ.get("CUSTOM_BASE_URL", "") or os.environ.get("FREELLMAPI_BASE_URL", "")).strip().rstrip("/")
    custom_url = ""
    if custom_base:
        custom_url = custom_base if custom_base.endswith("/chat/completions") else (
            f"{custom_base}/chat/completions" if custom_base.endswith("/v1") else f"{custom_base}/v1/chat/completions"
        )
    custom_key = (os.environ.get("CUSTOM_API_KEY", "") or os.environ.get("FREELLMAPI_KEY", "")).strip()
    custom = (
        [{"provider": "Custom", "url": custom_url, "key": custom_key, "model": os.environ.get("RIOT_UPSTREAM_CUSTOM_MODEL", "auto")}]
        if (custom_key and custom_url)
        else []
    )

    if long_context and m != "fast":
        # Contexte volumineux (> ~6.5k tokens) : privilegier Gemini (1M ctx) / DeepSeek / Cerebras / Mistral (40k TPM)
        # avant Groq (8k-12k TPM par modele) et garder OpenRouter en dernier secours
        groupes = [gemini, deepseek, cerebras, nvidia, together, fireworks, mistral, groq, openrouter, custom]
    elif m == "fast":
        groupes = [groq, cerebras, gemini, mistral, fireworks, together, deepseek, nvidia, openrouter, custom]
    elif m == "code":
        groupes = [mistral, deepseek, cerebras, groq, fireworks, together, nvidia, gemini, openrouter, custom]
    elif m == "deep":
        groupes = [deepseek, groq, gemini, cerebras, nvidia, together, mistral, fireworks, openrouter, custom]
    else:  # agent / general avec tool-calling fiable
        groupes = [groq, cerebras, gemini, deepseek, nvidia, mistral, together, fireworks, openrouter, custom]
    return [c for grp in groupes for c in grp]


@app.get("/health")
def health():
    toutes = _routes_pour_profil("riot-auto")
    actifs = len({c["provider"] for c in toutes})
    return {
        "ok": True,
        "service": "RIOT Engine Gateway",
        "routes_actives": actifs,
        "candidats_failover": len(toutes),
        "telemetry_backend": _STORE.backend_name,
        "memory_backend": _get_memory_store().backend_name,
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
        return {"ok": True, "version": "0.3.6", "release": None}
    return {"ok": True, "version": rel["version"], "release": rel}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    client_hash = _verifier_acces(request)
    raw_body: Dict[str, Any] = await request.json()
    body = _compacter_payload_entree(raw_body)
    profil = str(body.get("model", "riot-auto"))
    prompt_user = _extraire_dernier_prompt(body)
    tache_hint = (request.headers.get("x-riot-task", "") or "").strip().lower()
    tache_effective = profil_vers_tache(
        profil,
        messages=body.get("messages"),
        tools=body.get("tools"),
        prompt_hint=tache_hint,
    )
    try:
        payload_chars = len(json.dumps(body.get("messages") or [], ensure_ascii=False)) + len(
            json.dumps(body.get("tools") or [], ensure_ascii=False)
        )
    except Exception:
        payload_chars = len(prompt_user)
    long_context = payload_chars > 22000
    profil_log = f"{profil}:{tache_effective}" if profil.lower() == "riot-auto" else profil
    candidats = _routes_pour_profil(
        profil,
        tache=tache_effective,
        has_tools=bool(body.get("tools")),
        long_context=long_context,
        rotate_keys=True,
    )
    if not candidats:
        _STORE.enregistrer(
            source="proxy", client_id=client_hash, profil=profil_log,
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
            r = requests.post(c["url"], headers=headers, json=payload, timeout=20)
            try:
                from core.key_quota import capturer_reponse
                capturer_reponse(c["provider"], c["key"], c["model"], r.status_code, dict(r.headers))
            except Exception:
                pass
            if r.status_code in (413, 429, 503) or r.status_code >= 500:
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
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            tin = usage.get("prompt_tokens", 0) or 0
            tout = usage.get("completion_tokens", 0) or 0
            _STORE.enregistrer(
                source="proxy",
                client_id=client_hash,
                profil=profil_log,
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
                    f"Client : {client_hash}\nProfil : {profil_log} → {c['provider']} / {c['model']}\nTokens : {tin} in + {tout} out",
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
        profil=profil_log,
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


# ---------------------------------------------------------------------------
# MEMOIRE HYBRIDE CLOUD MULTI-POSTES (Neon PostgreSQL / SQLite WAL)
# ---------------------------------------------------------------------------

def _norm_ts_iso(raw: Any) -> str:
    """Normalise un horodatage ISO-8601 en UTC pour eviter toute erreur de parsing Postgres."""
    s = str(raw or "").strip()
    if s:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def _sanitiser_meta(meta: Any) -> Dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in list(meta.items())[:20]:
        ks = str(k)[:64]
        if isinstance(v, str):
            out[ks] = masquer_secrets(v, max_len=3000)
        elif isinstance(v, (int, float, bool)) or v is None:
            out[ks] = v
        else:
            out[ks] = masquer_secrets(str(v), max_len=500)
    return out


class MemoryCloudStore:
    """Stockage isole par utilisateur pour synchroniser entites et recettes entre appareils."""

    def __init__(self, db_path: Optional[Path] = None, pg_url: Optional[str] = None):
        self.pg_url = (
            pg_url
            if pg_url is not None
            else (
                os.environ.get("RIOT_MEMORY_DATABASE_URL", "").strip()
                or os.environ.get("RIOT_TELEMETRY_DATABASE_URL", "").strip()
                or os.environ.get("RIOT_PORTAL_DATABASE_URL", "").strip()
            )
        ).strip()
        env_db = os.environ.get("RIOT_PROXY_MEMORY_DB", "").strip()
        self.db_path = Path(db_path) if db_path is not None else (
            Path(env_db) if env_db else (Path.home() / ".riot" / "proxy_memory.db")
        )
        self._lock = threading.Lock()
        self._pg_ready = False
        self.backend_name = "neon-postgres" if self.pg_url else "sqlite"
        self._init_db()

    def _connect_sqlite(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=8.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_pg(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.pg_url, autocommit=True, row_factory=dict_row, connect_timeout=8)

    def _init_db(self) -> None:
        if self.pg_url:
            try:
                with self._connect_pg() as conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS user_memories (
                            id BIGSERIAL PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            kind TEXT NOT NULL,
                            mem_key TEXT NOT NULL,
                            content TEXT NOT NULL DEFAULT '',
                            metadata_json TEXT NOT NULL DEFAULT '{}',
                            deleted BOOLEAN NOT NULL DEFAULT FALSE,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE(user_id, kind, mem_key)
                        )
                        """
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_user_memories_uid_ts "
                        "ON user_memories (user_id, updated_at DESC)"
                    )
                self._pg_ready = True
                return
            except Exception as e:
                self.backend_name = f"sqlite-fallback ({type(e).__name__})"

        with self._lock:
            conn = self._connect_sqlite()
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        mem_key TEXT NOT NULL,
                        content TEXT NOT NULL DEFAULT '',
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        deleted INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        UNIQUE(user_id, kind, mem_key)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_memories_uid_ts "
                    "ON user_memories (user_id, updated_at DESC)"
                )
                conn.commit()
            finally:
                conn.close()

    def _row_to_item(self, row: Any) -> Dict[str, Any]:
        meta_raw = row["metadata_json"] or "{}"
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else dict(meta_raw)
        except Exception:
            meta = {}
        upd = row["updated_at"]
        upd_str = upd.astimezone(timezone.utc).isoformat() if hasattr(upd, "astimezone") else str(upd)
        return {
            "kind": row["kind"],
            "mem_key": row["mem_key"],
            "content": row["content"] or "",
            "metadata": meta,
            "deleted": bool(row["deleted"]),
            "updated_at": upd_str,
        }

    def lister(self, user_id: str, since: str = "", inclure_supprimes: bool = False) -> List[Dict[str, Any]]:
        since_norm = _norm_ts_iso(since) if since.strip() else ""
        if self._pg_ready:
            with self._connect_pg() as conn:
                if since_norm:
                    rows = conn.execute(
                        "SELECT kind, mem_key, content, metadata_json, deleted, updated_at "
                        "FROM user_memories WHERE user_id = %s AND updated_at >= %s::timestamptz "
                        "ORDER BY updated_at ASC LIMIT 2000",
                        (user_id, since_norm),
                    ).fetchall()
                elif inclure_supprimes:
                    rows = conn.execute(
                        "SELECT kind, mem_key, content, metadata_json, deleted, updated_at "
                        "FROM user_memories WHERE user_id = %s ORDER BY updated_at ASC LIMIT 2000",
                        (user_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT kind, mem_key, content, metadata_json, deleted, updated_at "
                        "FROM user_memories WHERE user_id = %s AND deleted = FALSE "
                        "ORDER BY updated_at ASC LIMIT 2000",
                        (user_id,),
                    ).fetchall()
                return [self._row_to_item(r) for r in rows]

        with self._lock:
            conn = self._connect_sqlite()
            try:
                if since_norm:
                    rows = conn.execute(
                        "SELECT kind, mem_key, content, metadata_json, deleted, updated_at "
                        "FROM user_memories WHERE user_id = ? AND updated_at >= ? "
                        "ORDER BY updated_at ASC LIMIT 2000",
                        (user_id, since_norm),
                    ).fetchall()
                elif inclure_supprimes:
                    rows = conn.execute(
                        "SELECT kind, mem_key, content, metadata_json, deleted, updated_at "
                        "FROM user_memories WHERE user_id = ? ORDER BY updated_at ASC LIMIT 2000",
                        (user_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT kind, mem_key, content, metadata_json, deleted, updated_at "
                        "FROM user_memories WHERE user_id = ? AND deleted = 0 "
                        "ORDER BY updated_at ASC LIMIT 2000",
                        (user_id,),
                    ).fetchall()
                return [self._row_to_item(r) for r in rows]
            finally:
                conn.close()

    def sync(self, user_id: str, items: List[Dict[str, Any]], since: str = "") -> Dict[str, Any]:
        nettoyes = []
        for raw in (items or [])[:1000]:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "").strip()[:64]
            mem_key = masquer_secrets(str(raw.get("mem_key") or "").strip(), max_len=200)
            if not kind or not mem_key:
                continue
            deleted = bool(raw.get("deleted", False))
            content = "" if deleted else masquer_secrets(str(raw.get("content") or ""), max_len=4000)
            meta_json = "{}" if deleted else json.dumps(_sanitiser_meta(raw.get("metadata")), ensure_ascii=False)
            ts = _norm_ts_iso(raw.get("updated_at"))
            nettoyes.append((kind, mem_key, content, meta_json, deleted, ts))

        if self._pg_ready:
            with self._connect_pg() as conn:
                for kind, mem_key, content, meta_json, deleted, ts in nettoyes:
                    conn.execute(
                        """
                        INSERT INTO user_memories (user_id, kind, mem_key, content, metadata_json, deleted, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s::timestamptz)
                        ON CONFLICT (user_id, kind, mem_key) DO UPDATE SET
                            content = EXCLUDED.content,
                            metadata_json = EXCLUDED.metadata_json,
                            deleted = EXCLUDED.deleted,
                            updated_at = EXCLUDED.updated_at
                        WHERE EXCLUDED.updated_at >= user_memories.updated_at
                        """,
                        (user_id, kind, mem_key, content, meta_json, deleted, ts),
                    )
        else:
            with self._lock:
                conn = self._connect_sqlite()
                try:
                    for kind, mem_key, content, meta_json, deleted, ts in nettoyes:
                        conn.execute(
                            """
                            INSERT INTO user_memories (user_id, kind, mem_key, content, metadata_json, deleted, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT (user_id, kind, mem_key) DO UPDATE SET
                                content = excluded.content,
                                metadata_json = excluded.metadata_json,
                                deleted = excluded.deleted,
                                updated_at = excluded.updated_at
                            WHERE excluded.updated_at >= user_memories.updated_at
                            """,
                            (user_id, kind, mem_key, content, meta_json, 1 if deleted else 0, ts),
                        )
                    conn.commit()
                finally:
                    conn.close()

        retour = self.lister(user_id, since=since, inclure_supprimes=bool(since.strip()))
        return {
            "ok": True,
            "recus": len(nettoyes),
            "items": retour,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "backend": self.backend_name,
        }

    def supprimer(self, user_id: str, kind: str = "", mem_key: str = "") -> int:
        ts = datetime.now(timezone.utc).isoformat()
        if self._pg_ready:
            with self._connect_pg() as conn:
                if kind and mem_key:
                    cur = conn.execute(
                        "UPDATE user_memories SET deleted = TRUE, content = '', metadata_json = '{}', updated_at = %s::timestamptz "
                        "WHERE user_id = %s AND kind = %s AND mem_key = %s",
                        (ts, user_id, kind, mem_key),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE user_memories SET deleted = TRUE, content = '', metadata_json = '{}', updated_at = %s::timestamptz "
                        "WHERE user_id = %s",
                        (ts, user_id),
                    )
                return int(cur.rowcount or 0)

        with self._lock:
            conn = self._connect_sqlite()
            try:
                if kind and mem_key:
                    cur = conn.execute(
                        "UPDATE user_memories SET deleted = 1, content = '', metadata_json = '{}', updated_at = ? "
                        "WHERE user_id = ? AND kind = ? AND mem_key = ?",
                        (ts, user_id, kind, mem_key),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE user_memories SET deleted = 1, content = '', metadata_json = '{}', updated_at = ? "
                        "WHERE user_id = ?",
                        (ts, user_id),
                    )
                conn.commit()
                return int(cur.rowcount or 0)
            finally:
                conn.close()


_MEMORY_STORE: Optional[MemoryCloudStore] = None


def _get_memory_store() -> MemoryCloudStore:
    global _MEMORY_STORE
    if _MEMORY_STORE is None:
        _MEMORY_STORE = MemoryCloudStore()
    return _MEMORY_STORE


@app.get("/v1/memory")
def memory_list(request: Request, since: str = ""):
    identite = _verifier_acces_detail(request, verifier_quota=False)
    items = _get_memory_store().lister(identite["user_id"], since=since, inclure_supprimes=bool(since.strip()))
    return {
        "ok": True,
        "items": items,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "backend": _get_memory_store().backend_name,
    }


@app.post("/v1/memory/sync")
async def memory_sync(request: Request):
    identite = _verifier_acces_detail(request, verifier_quota=False)
    body = await request.json() or {}
    items = body.get("items") if isinstance(body.get("items"), list) else []
    since = str(body.get("since") or "").strip()
    return _get_memory_store().sync(identite["user_id"], items, since=since)


@app.delete("/v1/memory")
def memory_delete(request: Request, kind: str = "", mem_key: str = ""):
    identite = _verifier_acces_detail(request, verifier_quota=False)
    nb = _get_memory_store().supprimer(identite["user_id"], kind=kind.strip(), mem_key=mem_key.strip())
    return {"ok": True, "supprimes": nb}


# ---------------------------------------------------------------------------
# RECHERCHE INTERNET SOURCÉE POUR CLIENTS RIOT (Anti-hallucination)
# ---------------------------------------------------------------------------

def _executer_recherche_web_cloud(requete: str, max_resultats: int = 5, plan: str = "free") -> Dict[str, Any]:
    """Cascade web serveur : Perplexity -> Tavily -> Brave -> DuckDuckGo -> Wikipedia."""
    q = (requete or "").strip()
    max_res = max(1, min(int(max_resultats or 5), 10))

    # 1. Perplexity Sonar (reponses sourcees avec citations)
    pplx_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    allow_free_pplx = os.environ.get("RIOT_PERPLEXITY_ALLOW_FREE", "1").strip() != "0"
    if pplx_key and (allow_free_pplx or plan != "free"):
        try:
            r = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"},
                json={
                    "model": os.environ.get("RIOT_PERPLEXITY_MODEL", "sonar"),
                    "messages": [
                        {"role": "system", "content": "Réponds en français de façon concise, factuelle et vérifiable avec tes sources."},
                        {"role": "user", "content": q},
                    ],
                    "return_citations": True,
                },
                timeout=18,
            )
            if r.status_code == 200:
                data = r.json()
                answer = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                cits = data.get("citations") or []
                results = [{"title": f"Source {i + 1}", "url": str(u), "snippet": ""} for i, u in enumerate(cits[:max_res])]
                if answer or results:
                    return {"ok": True, "source": "riot-web-sonar", "answer": answer, "results": results}
        except Exception:
            pass

    # 2. Tavily Search
    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if tavily_key:
        try:
            r = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": q, "include_answer": True, "max_results": max_res},
                timeout=12,
            )
            if r.status_code == 200:
                data = r.json()
                results = [
                    {
                        "title": str(it.get("title") or "Sans titre"),
                        "url": str(it.get("url") or ""),
                        "snippet": str(it.get("content") or "")[:450],
                    }
                    for it in (data.get("results") or [])[:max_res]
                ]
                return {"ok": True, "source": "riot-web-tavily", "answer": str(data.get("answer") or "").strip(), "results": results}
        except Exception:
            pass

    # 2b. Firecrawl Search API
    fc_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if fc_key:
        try:
            r = requests.post(
                "https://api.firecrawl.dev/v1/search",
                headers={"Authorization": f"Bearer {fc_key}", "Content-Type": "application/json"},
                json={"query": q, "limit": max_res},
                timeout=14,
            )
            if r.status_code == 200:
                items_fc = (r.json().get("data") or [])[:max_res]
                results = [
                    {
                        "title": str(it.get("title") or "Sans titre"),
                        "url": str(it.get("url") or ""),
                        "snippet": str(it.get("description") or it.get("markdown") or "")[:450],
                    }
                    for it in items_fc
                ]
                if results:
                    return {"ok": True, "source": "riot-web-firecrawl", "answer": "", "results": results}
        except Exception:
            pass

    # 3. Brave Search API
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if brave_key:
        try:
            r = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json", "X-Subscription-Token": brave_key},
                params={"q": q, "count": max_res},
                timeout=10,
            )
            if r.status_code == 200:
                web_res = ((r.json().get("web") or {}).get("results") or [])[:max_res]
                results = [
                    {
                        "title": str(it.get("title") or "Sans titre"),
                        "url": str(it.get("url") or ""),
                        "snippet": str(it.get("description") or "")[:450],
                    }
                    for it in web_res
                ]
                if results:
                    return {"ok": True, "source": "riot-web-brave", "answer": "", "results": results}
        except Exception:
            pass

    # 4. DuckDuckGo (ddgs)
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            bruts = list(ddgs.text(q, region="wt-wt", max_results=max_res))
        results = [
            {
                "title": str(it.get("title") or "Résultat").strip(),
                "url": str(it.get("href") or it.get("url") or "").strip(),
                "snippet": str(it.get("body") or it.get("snippet") or "").strip()[:500],
            }
            for it in bruts
        ]
        if results:
            return {"ok": True, "source": "riot-web-ddg", "answer": "", "results": results}
    except Exception:
        pass

    # 5. Wikipedia REST OpenSearch
    for lang in ("fr", "en"):
        try:
            r = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "opensearch", "search": q, "limit": min(max_res, 4), "format": "json"},
                headers={"User-Agent": "RIOT-Engine/1.0"},
                timeout=6,
            )
            if r.status_code == 200:
                arr = r.json()
                if isinstance(arr, list) and len(arr) >= 4 and arr[1]:
                    results = [
                        {"title": str(t), "url": str(u), "snippet": str(d)[:400]}
                        for t, d, u in zip(arr[1], arr[2], arr[3])
                    ]
                    return {"ok": True, "source": f"riot-web-wiki-{lang}", "answer": "", "results": results}
        except Exception:
            continue

    return {"ok": False, "source": "none", "answer": "", "results": [], "erreur": "Aucun résultat web disponible."}


@app.post("/v1/web/search")
async def web_search(request: Request):
    identite = _verifier_acces_detail(request)
    body = await request.json() or {}
    query = str(body.get("query") or body.get("requete") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Paramètre 'query' requis.")
    max_res = int(body.get("max_results") or 5)
    return _executer_recherche_web_cloud(query, max_resultats=max_res, plan=str(identite.get("plan") or "free"))


@app.post("/v1/web/scrape")
async def web_scrape(request: Request):
    _verifier_acces_detail(request)
    body = await request.json() or {}
    url = str(body.get("url") or "").strip()
    max_words = max(100, min(int(body.get("max_words") or 1200), 4000))
    from tools.web import _extraire_meta_page, _nettoyer_html_texte, _valider_url_publique
    ok, val = _valider_url_publique(url)
    if not ok:
        raise HTTPException(status_code=400, detail=val)

    fc_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if fc_key:
        try:
            rf = requests.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {fc_key}", "Content-Type": "application/json"},
                json={"url": val, "formats": ["markdown"], "onlyMainContent": True},
                timeout=16,
            )
            if rf.status_code == 200:
                payload = rf.json().get("data") or {}
                md = str(payload.get("markdown") or "").strip()
                meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                if md:
                    mots = md.split()
                    extrait = " ".join(mots[:max_words]) + (" ... [tronqué]" if len(mots) > max_words else "")
                    return {
                        "ok": True,
                        "url": str(meta.get("sourceURL") or val),
                        "titre": str(meta.get("title") or val),
                        "description": str(meta.get("description") or ""),
                        "texte": extrait,
                        "nb_mots": min(len(mots), max_words),
                        "source": "riot-scrape-firecrawl",
                    }
        except Exception:
            pass

    try:
        rep = requests.get(val, headers={"User-Agent": "RIOT-Engine/1.0"}, timeout=8, allow_redirects=True)
        rep.raise_for_status()
        ok_fin, url_fin = _valider_url_publique(rep.url or val)
        if not ok_fin:
            raise HTTPException(status_code=400, detail=url_fin)
        titre, desc = _extraire_meta_page(rep.text or "")
        texte = _nettoyer_html_texte(rep.text or "")
        mots = texte.split()
        extrait = " ".join(mots[:max_words]) + (" ... [tronqué]" if len(mots) > max_words else "")
        return {
            "ok": True,
            "url": url_fin,
            "titre": titre,
            "description": desc,
            "texte": extrait,
            "nb_mots": min(len(mots), max_words),
            "source": "riot-scrape-http",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Impossible de lire {val} : {e}")
