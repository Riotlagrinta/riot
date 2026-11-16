"""Suivi en temps reel des quotas, requetes restantes et etat des cles API RIOT.

Ne stocke ni n'affiche jamais les cles completes (uniquement un masque `sk-...xxxx`).
Combine :
  1. Capture passive des headers HTTP `x-ratelimit-*` apres chaque appel LLM reel.
  2. Sondage leger (`/auth/key` OpenRouter, `/models` Gemini, ping `max_tokens=1` Groq/Mistral)
     a la demande via `/keys` ou `/admin/keys`.
  3. Consommation locale/proxy depuis `core/budget.py` et `core/telemetry.py`.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import requests

_LOCK = threading.Lock()
_CACHE_FICHIER = Path.home() / ".riot" / "key_quotas.json"


def masquer_cle(cle: str) -> str:
    c = (cle or "").strip()
    if len(c) <= 10:
        return "***"
    return f"{c[:6]}...{c[-4:]}"


def _charger_cache() -> Dict[str, Any]:
    try:
        if _CACHE_FICHIER.exists():
            return json.loads(_CACHE_FICHIER.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def _sauver_cache(data: Dict[str, Any]) -> None:
    try:
        _CACHE_FICHIER.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FICHIER.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _extraire_ratelimit(provider: str, headers: Dict[str, str], body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    info: Dict[str, Any] = {
        "req_limit": None,
        "req_remaining": None,
        "req_reset": h.get("x-ratelimit-reset-requests", "") or h.get("retry-after", ""),
        "tok_limit": None,
        "tok_remaining": None,
        "tok_reset": h.get("x-ratelimit-reset-tokens", ""),
        "window": "jour/min",
    }

    p = provider.lower()
    if "groq" in p:
        info["req_limit"] = h.get("x-ratelimit-limit-requests")
        info["req_remaining"] = h.get("x-ratelimit-remaining-requests")
        info["tok_limit"] = h.get("x-ratelimit-limit-tokens")
        info["tok_remaining"] = h.get("x-ratelimit-remaining-tokens")
        info["window"] = "RPD / TPM"
    elif "mistral" in p:
        info["req_limit"] = h.get("x-ratelimit-limit-req-minute")
        info["req_remaining"] = h.get("x-ratelimit-remaining-req-minute")
        info["tok_limit"] = h.get("x-ratelimit-limit-tokens-minute")
        info["tok_remaining"] = h.get("x-ratelimit-remaining-tokens-minute")
        info["window"] = "RPM / TPM"
    elif "openrouter" in p and body and isinstance(body.get("data"), dict):
        d = body["data"]
        fr = d.get("free_model_daily_requests") or {}
        if fr:
            info["req_limit"] = fr.get("limit")
            info["req_remaining"] = fr.get("remaining")
            info["window"] = "RPD (gratuit)"
        elif d.get("limit") is not None:
            info["req_limit"] = d.get("limit")
            info["req_remaining"] = d.get("limit_remaining")
            info["window"] = "Crédits ($)"
    else:
        for rk in ("x-ratelimit-limit-requests", "anthropic-ratelimit-requests-limit"):
            if rk in h:
                info["req_limit"] = h[rk]
        for rk in ("x-ratelimit-remaining-requests", "anthropic-ratelimit-requests-remaining"):
            if rk in h:
                info["req_remaining"] = h[rk]
        for tk in ("x-ratelimit-limit-tokens", "anthropic-ratelimit-tokens-limit"):
            if tk in h:
                info["tok_limit"] = h[tk]
        for tk in ("x-ratelimit-remaining-tokens", "anthropic-ratelimit-tokens-remaining"):
            if tk in h:
                info["tok_remaining"] = h[tk]
    return info


def capturer_reponse(provider: str, cle: str, modele: str, status_code: int, headers: Dict[str, str], body: Optional[Dict[str, Any]] = None) -> None:
    """Enregistre les derniers headers de quota retournes par un provider."""
    mask = masquer_cle(cle)
    id_entree = f"{provider}:{mask}"
    rl = _extraire_ratelimit(provider, headers, body=body)
    entree = {
        "provider": provider,
        "cle_masquee": mask,
        "modele": modele,
        "status_code": int(status_code),
        "etat": "OK" if status_code == 200 else ("Saturée (429)" if status_code == 429 else f"Erreur ({status_code})"),
        "rl": rl,
        "updated_at": time.time(),
        "updated_iso": datetime.now(tz=timezone.utc).strftime("%H:%M:%S UTC"),
    }
    with _LOCK:
        cache = _charger_cache()
        prev = cache.get(id_entree, {})
        # Conserver les derniers compteurs si la reponse courante n'avait pas de headers RL
        if not rl.get("req_limit") and not rl.get("tok_limit") and prev.get("rl"):
            entree["rl"] = prev["rl"]
        cache[id_entree] = entree
        _sauver_cache(cache)


def _cles_par_provider() -> List[Dict[str, Any]]:
    from core.config import reglage
    from core.llm import _recuperer_liste_cles

    specs = [
        ("Groq", "groq", "GROQ_API_KEY", reglage("groq.modele", "openai/gpt-oss-120b")),
        ("Mistral", "mistral", "MISTRAL_API_KEY", reglage("mistral.modele", "codestral-latest")),
        ("OpenRouter", "openrouter", "OPENROUTER_API_KEY", reglage("openrouter.modele", "openrouter/free")),
        ("Gemini", "gemini", "GEMINI_API_KEY", reglage("gemini.modele", "gemini-flash-latest")),
        ("Anthropic", "anthropic", "ANTHROPIC_API_KEY", reglage("anthropic.modele", "claude-haiku-4-5")),
    ]
    res: List[Dict[str, Any]] = []
    for nom, sec, env_k, modele in specs:
        cles = _recuperer_liste_cles(reglage(f"{sec}.cles", []) or reglage(f"{sec}.cle", ""), env_k)
        for c in cles:
            res.append({"provider": nom, "section": sec, "cle": c, "modele": str(modele)})
    return res


def _sonder_cle(item: Dict[str, Any]) -> Dict[str, Any]:
    prov = item["provider"]
    cle = item["cle"]
    modele = item["modele"]
    mask = masquer_cle(cle)

    try:
        if prov == "OpenRouter":
            r = requests.get("https://openrouter.ai/api/v1/auth/key", headers={"Authorization": f"Bearer {cle}"}, timeout=8)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            capturer_reponse(prov, cle, modele, r.status_code, dict(r.headers), body=body)
            d = body.get("data") or {}
            fr = d.get("free_model_daily_requests") or {}
            return {
                "provider": prov,
                "cle_masquee": mask,
                "modele": modele,
                "status_code": r.status_code,
                "etat": "OK" if r.ok else f"Erreur ({r.status_code})",
                "req_remaining": fr.get("remaining") if fr else d.get("limit_remaining"),
                "req_limit": fr.get("limit") if fr else d.get("limit"),
                "tok_remaining": None,
                "tok_limit": None,
                "reset": "Quotidien" if fr else (d.get("limit_reset") or "-"),
                "note": f"Tier {'gratuit' if d.get('is_free_tier') else 'payant'} · Usage jour: {d.get('usage_daily', 0)}",
            }

        if prov == "Gemini":
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": cle}, timeout=8)
            capturer_reponse(prov, cle, modele, r.status_code, dict(r.headers))
            return {
                "provider": prov,
                "cle_masquee": mask,
                "modele": modele,
                "status_code": r.status_code,
                "etat": "OK" if r.ok else ("Saturée (429)" if r.status_code == 429 else f"Erreur ({r.status_code})"),
                "req_remaining": None,
                "req_limit": None,
                "tok_remaining": None,
                "tok_limit": None,
                "reset": "-",
                "note": "Clé active (Google ne publie pas le solde chiffré en header)",
            }

        if prov in ("Groq", "Mistral"):
            url = (
                "https://api.groq.com/openai/v1/chat/completions"
                if prov == "Groq"
                else "https://api.mistral.ai/v1/chat/completions"
            )
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {cle}", "Content-Type": "application/json"},
                json={"model": modele, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1},
                timeout=10,
            )
            capturer_reponse(prov, cle, modele, r.status_code, dict(r.headers))
            rl = _extraire_ratelimit(prov, dict(r.headers))
            return {
                "provider": prov,
                "cle_masquee": mask,
                "modele": modele,
                "status_code": r.status_code,
                "etat": "OK" if r.ok else ("Saturée (429)" if r.status_code == 429 else f"Erreur ({r.status_code})"),
                "req_remaining": rl.get("req_remaining"),
                "req_limit": rl.get("req_limit"),
                "tok_remaining": rl.get("tok_remaining"),
                "tok_limit": rl.get("tok_limit"),
                "reset": rl.get("req_reset") or rl.get("tok_reset") or rl.get("window") or "-",
                "note": rl.get("window", ""),
            }

        if prov == "Anthropic":
            r = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": cle, "anthropic-version": "2023-06-01"},
                timeout=8,
            )
            capturer_reponse(prov, cle, modele, r.status_code, dict(r.headers))
            rl = _extraire_ratelimit(prov, dict(r.headers))
            return {
                "provider": prov,
                "cle_masquee": mask,
                "modele": modele,
                "status_code": r.status_code,
                "etat": "OK" if r.ok else f"Erreur ({r.status_code})",
                "req_remaining": rl.get("req_remaining"),
                "req_limit": rl.get("req_limit"),
                "tok_remaining": rl.get("tok_remaining"),
                "tok_limit": rl.get("tok_limit"),
                "reset": "-",
                "note": "Clé Anthropic vérifiée",
            }
    except Exception as e:
        return {
            "provider": prov,
            "cle_masquee": mask,
            "modele": modele,
            "status_code": 0,
            "etat": "Injoignable",
            "req_remaining": None,
            "req_limit": None,
            "tok_remaining": None,
            "tok_limit": None,
            "reset": "-",
            "note": str(e)[:80],
        }
    return {}


def inspecter_cles(sonder: bool = True) -> Dict[str, Any]:
    """Retourne l'etat live de toutes les cles API + consommation locale du jour."""
    from core import budget

    items = _cles_par_provider()
    cache = _charger_cache()
    lignes: List[Dict[str, Any]] = []

    for it in items:
        if sonder:
            row = _sonder_cle(it)
        else:
            mask = masquer_cle(it["cle"])
            c = cache.get(f"{it['provider']}:{mask}", {})
            rl = c.get("rl") or {}
            row = {
                "provider": it["provider"],
                "cle_masquee": mask,
                "modele": c.get("modele") or it["modele"],
                "status_code": c.get("status_code") or "-",
                "etat": c.get("etat") or "Non sondée",
                "req_remaining": rl.get("req_remaining"),
                "req_limit": rl.get("req_limit"),
                "tok_remaining": rl.get("tok_remaining"),
                "tok_limit": rl.get("tok_limit"),
                "reset": rl.get("req_reset") or rl.get("tok_reset") or rl.get("window") or "-",
                "note": c.get("updated_iso") or "Lance /keys pour sonder",
            }
        lignes.append(row)

    conso = budget.resume()
    return {
        "ok": True,
        "cles": lignes,
        "budget_jour": conso.get("jour", {}),
        "budget_mois": conso.get("mois", {}),
    }
