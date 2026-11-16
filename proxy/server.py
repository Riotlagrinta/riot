"""Passerelle Cloud RIOT Engine (Proxy OpenAI-compatible a deployer cote serveur).

Toutes les cles fournisseurs (Groq, Mistral, Gemini, OpenRouter) restent uniquement
dans les variables d'environnement du serveur. Les clients finaux ne connaissent ni
les cles ni les modeles reels : le proxy renvoie toujours `"model": "riot-engine"`.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="RIOT Engine Gateway")

_RATE_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)
_MAX_REQ_PER_MIN = int(os.environ.get("RIOT_PROXY_RPM", "30"))


def _verifier_acces(request: Request) -> str:
    expected = os.environ.get("RIOT_PROXY_TOKEN", "").strip()
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if expected and token != expected:
        raise HTTPException(status_code=401, detail="Jeton client RIOT invalide.")

    cle_client = token or (request.client.host if request.client else "anon")
    now = time.time()
    q = _RATE_WINDOWS[cle_client]
    while q and now - q[0] > 60.0:
        q.popleft()
    if len(q) >= _MAX_REQ_PER_MIN:
        raise HTTPException(status_code=429, detail="Quota de requetes minute depasse.")
    q.append(now)
    return cle_client


def _routes_pour_profil(model_req: str) -> List[Dict[str, str]]:
    """Definit la cascade de fournisseurs secrets cote serveur selon le profil opaque."""
    m = (model_req or "riot-auto").lower()
    mistral = {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "key": os.environ.get("MISTRAL_API_KEY", "").strip(),
        "model": os.environ.get("RIOT_UPSTREAM_CODE_MODEL", "codestral-latest"),
    }
    groq = {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key": os.environ.get("GROQ_API_KEY", "").strip(),
        "model": os.environ.get("RIOT_UPSTREAM_FAST_MODEL", "llama-3.3-70b-versatile"),
    }
    openrouter = {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": os.environ.get("OPENROUTER_API_KEY", "").strip(),
        "model": os.environ.get("RIOT_UPSTREAM_DEEP_MODEL", "openrouter/free"),
    }
    gemini = {
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
    _verifier_acces(request)
    body: Dict[str, Any] = await request.json()
    candidats = _routes_pour_profil(str(body.get("model", "riot-auto")))
    if not candidats:
        raise HTTPException(status_code=503, detail="Aucun fournisseur configure cote serveur.")

    derniere_err = "Indisponible"
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
                derniere_err = f"HTTP {r.status_code}"
                continue
            r.raise_for_status()
            data = r.json()
            # Masquage strict du modele et du fournisseur reel
            data["model"] = "riot-engine"
            return JSONResponse(data)
        except Exception as e:
            derniere_err = str(e)
            continue

    raise HTTPException(status_code=502, detail=f"Moteur RIOT temporairement sature ({derniere_err}).")
