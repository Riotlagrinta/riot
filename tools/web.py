"""Outils d'accès Internet fiables et anti-hallucination (Recherche Web sourcée + Lecture de pages).

Cascade transparente :
  1. Perplexity / Tavily / Brave si configurés localement
  2. Passerelle Cloud RIOT (`/v1/web/search`) si l'utilisateur est connecté via `/login`
  3. DuckDuckGo (`ddgs`) enrichi (titres + URLs + extraits) + fallback Wikipedia REST API
"""
from __future__ import annotations

import html
import ipaddress
import os
import re
import socket
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.registre import outil

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _valider_url_publique(url: str) -> Tuple[bool, str]:
    """Valide une URL HTTP(S) et bloque tout accès SSRF vers localhost ou réseaux privés."""
    u = (url or "").strip()
    if not u:
        return False, "URL vide."
    if not u.startswith(("http://", "https://")):
        u = "https://" + u

    try:
        parsed = urllib.parse.urlparse(u)
    except Exception as e:
        return False, f"URL invalide : {e}"

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False, "Seuls les schémas http:// et https:// sont autorisés."

    host = parsed.hostname.strip().lower()
    if host in ("localhost", "localhost.localdomain") or host.endswith(".local"):
        return False, "Accès aux hôtes locaux bloqué (protection SSRF)."

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return False, f"Hôte introuvable ({host}) : {e}"

    for _, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                return False, f"Adresse réseau non publique refusée ({ip_str})."
        except ValueError:
            return False, "Adresse IP invalide."

    return True, u


def _nettoyer_html_texte(html_brut: str) -> str:
    """Extrait le texte lisible d'une page HTML et neutralise scripts et injections de prompt."""
    t = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html_brut, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    for pat in (
        r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
        r"you\s+are\s+now\s+in\s+developer\s+mode",
        r"system\s*:\s*system_override",
    ):
        t = re.sub(pat, "[CONTENU FILTRÉ]", t, flags=re.IGNORECASE)
    return t


def _extraire_meta_page(html_brut: str) -> Tuple[str, str]:
    m_titre = re.search(r"<title[^>]*>(.*?)</title>", html_brut, re.IGNORECASE | re.DOTALL)
    titre = html.unescape(re.sub(r"\s+", " ", m_titre.group(1)).strip()) if m_titre else "Sans titre"
    m_desc = re.search(
        r'<meta\s+[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
        html_brut,
        re.IGNORECASE,
    )
    desc = html.unescape(m_desc.group(1).strip()) if m_desc else ""
    return titre, desc


def _lire_page_brute(url: str, max_mots: int = 1200, timeout: float = 8.0) -> Dict[str, Any]:
    ok, val = _valider_url_publique(url)
    if not ok:
        return {"ok": False, "url": url, "erreur": val}

    # 1. Firecrawl local (si FIRECRAWL_API_KEY configurée : idéal pour sites JS/SPA/Markdown propre)
    fc_key = (os.environ.get("FIRECRAWL_API_KEY", "") or _reglage_sur("web.firecrawl_key")).strip()
    if fc_key:
        try:
            rf = requests.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {fc_key}", "Content-Type": "application/json"},
                json={"url": val, "formats": ["markdown"], "onlyMainContent": True},
                timeout=max(timeout, 15.0),
            )
            if rf.status_code == 200:
                payload = (rf.json().get("data") or {})
                md = str(payload.get("markdown") or "").strip()
                meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                if md:
                    mots = md.split()
                    extrait = " ".join(mots[:max_mots]) + (" ... [tronqué]" if len(mots) > max_mots else "")
                    return {
                        "ok": True,
                        "url": str(meta.get("sourceURL") or val),
                        "titre": str(meta.get("title") or val),
                        "description": str(meta.get("description") or ""),
                        "texte": extrait,
                        "nb_mots": min(len(mots), max_mots),
                        "source": "firecrawl",
                    }
        except Exception:
            pass

    # 2. Passerelle Cloud (/v1/web/scrape) si connecté par jeton
    gw_tok = (os.environ.get("RIOT_GATEWAY_TOKEN", "") or _reglage_sur("gateway.token")).strip()
    if gw_tok:
        gw_url = (
            os.environ.get("RIOT_GATEWAY_URL", "")
            or _reglage_sur("gateway.url")
            or "https://riot-engine-proxy.onrender.com/v1"
        ).strip().rstrip("/")
        base = gw_url[:-3] if gw_url.endswith("/v1") else gw_url
        try:
            rg = requests.post(
                f"{base}/v1/web/scrape",
                headers={"Authorization": f"Bearer {gw_tok}", "Content-Type": "application/json"},
                json={"url": val, "max_words": max_mots},
                timeout=max(timeout, 15.0),
            )
            if rg.status_code == 200:
                data = rg.json()
                if data.get("ok") and data.get("texte"):
                    return data
        except Exception:
            pass

    # 3. Scraping HTTP direct assaini
    err_direct = ""
    try:
        rep = requests.get(
            val,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            timeout=timeout,
            allow_redirects=True,
        )
        rep.raise_for_status()
        ok_final, url_finale = _valider_url_publique(rep.url or val)
        if not ok_final:
            return {"ok": False, "url": url, "erreur": url_finale}

        ctype = (rep.headers.get("content-type") or "").lower()
        brut = rep.text or ""
        if "html" in ctype or "<html" in brut[:500].lower():
            titre, desc = _extraire_meta_page(brut)
            texte = _nettoyer_html_texte(brut)
        else:
            titre, desc = url_finale, ""
            texte = re.sub(r"\s+", " ", brut).strip()

        mots = texte.split()
        if len(mots) >= 15:
            extrait = " ".join(mots[:max_mots]) + (" ... [tronqué]" if len(mots) > max_mots else "")
            return {
                "ok": True,
                "url": url_finale,
                "titre": titre,
                "description": desc,
                "texte": extrait,
                "nb_mots": min(len(mots), max_mots),
                "source": "http-direct",
            }
    except Exception as e:
        err_direct = str(e)

    # 4. Repli Jina Reader (rendu Markdown gratuit pour pages JS/SPA si direct vide ou bloqué)
    try:
        rj = requests.get(
            f"https://r.jina.ai/{val}",
            headers={"User-Agent": _USER_AGENT, "Accept": "text/plain"},
            timeout=max(timeout, 12.0),
        )
        if rj.status_code == 200 and len(rj.text.strip()) > 60:
            mots = rj.text.strip().split()
            extrait = " ".join(mots[:max_mots]) + (" ... [tronqué]" if len(mots) > max_mots else "")
            return {
                "ok": True,
                "url": val,
                "titre": val,
                "description": "",
                "texte": extrait,
                "nb_mots": min(len(mots), max_mots),
                "source": "jina-reader",
            }
    except Exception:
        pass

    return {"ok": False, "url": val, "erreur": err_direct or "Contenu web vide ou protégé."}


def _reglage_sur(cle: str, defaut: str = "") -> str:
    try:
        from core.config import reglage
        return str(reglage(cle, defaut) or "").strip()
    except Exception:
        return defaut


def recherche_web_structuree(requete: str, max_resultats: int = 5) -> Dict[str, Any]:
    """Exécute la cascade de recherche Internet et renvoie {ok, source, answer, results}."""
    q = (requete or "").strip()
    if not q:
        return {"ok": False, "erreur": "Requête vide.", "results": []}
    max_res = max(1, min(int(max_resultats or 5), 10))

    # 1. Clé Perplexity locale (si configurée en mode créateur ou env)
    pplx_key = (os.environ.get("PERPLEXITY_API_KEY", "") or _reglage_sur("web.perplexity_key")).strip()
    if pplx_key:
        try:
            r = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {pplx_key}", "Content-Type": "application/json"},
                json={
                    "model": os.environ.get("RIOT_PERPLEXITY_MODEL", "sonar"),
                    "messages": [
                        {"role": "system", "content": "Réponds en français de façon claire, factuelle et précise en citant tes sources."},
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
                    return {"ok": True, "source": "perplexity", "answer": answer, "results": results}
        except Exception:
            pass

    # 2. Clé Tavily locale (si configurée)
    tavily_key = (os.environ.get("TAVILY_API_KEY", "") or _reglage_sur("web.tavily_key")).strip()
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
                return {"ok": True, "source": "tavily", "answer": str(data.get("answer") or "").strip(), "results": results}
        except Exception:
            pass

    # 2b. Clé Firecrawl locale (search + contenu markdown)
    fc_key = (os.environ.get("FIRECRAWL_API_KEY", "") or _reglage_sur("web.firecrawl_key")).strip()
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
                    return {"ok": True, "source": "firecrawl", "answer": "", "results": results}
        except Exception:
            pass

    # 3. Passerelle Cloud RIOT (/v1/web/search) si connecté par jeton
    gw_tok = (os.environ.get("RIOT_GATEWAY_TOKEN", "") or _reglage_sur("gateway.token")).strip()
    if gw_tok:
        gw_url = (
            os.environ.get("RIOT_GATEWAY_URL", "")
            or _reglage_sur("gateway.url")
            or "https://riot-engine-proxy.onrender.com/v1"
        ).strip().rstrip("/")
        base = gw_url[:-3] if gw_url.endswith("/v1") else gw_url
        try:
            r = requests.post(
                f"{base}/v1/web/search",
                headers={"Authorization": f"Bearer {gw_tok}", "Content-Type": "application/json"},
                json={"query": q, "max_results": max_res},
                timeout=18,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("ok") and (data.get("answer") or data.get("results")):
                    return {
                        "ok": True,
                        "source": str(data.get("source") or "riot-gateway"),
                        "answer": str(data.get("answer") or "").strip(),
                        "results": list(data.get("results") or [])[:max_res],
                    }
        except Exception:
            pass

    # 4. DuckDuckGo (ddgs) enrichi avec Titre + URL + Snippet complet
    results_ddg: List[Dict[str, str]] = []
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            bruts = list(ddgs.text(q, region="wt-wt", max_results=max_res))
        for item in bruts:
            results_ddg.append({
                "title": str(item.get("title") or "Résultat").strip(),
                "url": str(item.get("href") or item.get("url") or "").strip(),
                "snippet": str(item.get("body") or item.get("snippet") or "").strip()[:500],
            })
        if results_ddg:
            return {"ok": True, "source": "duckduckgo", "answer": "", "results": results_ddg}
    except Exception:
        pass

    # 5. Repli Wikipedia API (fr puis en) pour faits généraux si DDG indisponible
    for lang in ("fr", "en"):
        try:
            r = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "opensearch", "search": q, "limit": min(max_res, 4), "format": "json"},
                headers={"User-Agent": _USER_AGENT},
                timeout=6,
            )
            if r.status_code == 200:
                arr = r.json()
                if isinstance(arr, list) and len(arr) >= 4 and arr[1]:
                    res_wiki = []
                    for titre, desc, url_w in zip(arr[1], arr[2], arr[3]):
                        res_wiki.append({"title": str(titre), "url": str(url_w), "snippet": str(desc)[:400]})
                    return {"ok": True, "source": f"wikipedia-{lang}", "answer": "", "results": res_wiki}
        except Exception:
            continue

    return {"ok": False, "erreur": "Aucun moteur de recherche joignable actuellement.", "results": []}


@outil(
    nom="chercher_web",
    description="Recherche des informations à jour sur Internet avec titres, URLs sources et synthèse. "
                "Indispensable pour éviter d'halluciner sur l'actualité, les versions de librairies/APIs, "
                "les prix ou tout fait incertain. Mets approfondir=True pour lire aussi le contenu des meilleures pages.",
    parametres={
        "type": "object",
        "properties": {
            "requete": {"type": "string", "description": "Mots-clés ou question précise à rechercher sur le web"},
            "max_resultats": {"type": "integer", "description": "Nombre de sources à retourner (défaut: 5)", "default": 5},
            "approfondir": {
                "type": "boolean",
                "description": "Si True, lit automatiquement le texte des 2 premières pages trouvées pour plus de précision.",
                "default": False,
            },
        },
        "required": ["requete"],
    },
    lent=True,
    phrase_attente="Je vérifie sur Internet tout de suite.",
)
def chercher_web(requete: str, max_resultats: int = 5, approfondir: bool = False) -> str:
    """Recherche sur Internet et renvoie des sources vérifiées (avec lecture optionnelle des pages)."""
    res = recherche_web_structuree(requete, max_resultats=max_resultats)
    if not res.get("ok"):
        return f"Recherche impossible : {res.get('erreur', 'aucun résultat')}"

    lignes: List[str] = [f"### Résultats Web ({res.get('source', 'web')}) pour : {requete.strip()}"]
    if res.get("answer"):
        lignes.append(f"\n**Synthèse vérifiée :**\n{res['answer']}\n")

    sources = res.get("results") or []
    if sources:
        lignes.append("**Sources :**")
        for idx, s in enumerate(sources, start=1):
            titre = s.get("title") or f"Source {idx}"
            url = s.get("url") or ""
            snip = s.get("snippet") or ""
            lignes.append(f"{idx}. **{titre}** ({url})" + (f"\n   {snip}" if snip else ""))

    if approfondir and sources and not res.get("answer"):
        urls = [s["url"] for s in sources if s.get("url")][:2]
        if urls:
            with ThreadPoolExecutor(max_workers=2) as pool:
                pages = list(pool.map(lambda u: _lire_page_brute(u, max_mots=550, timeout=7.0), urls))
            extraits = [p for p in pages if p.get("ok") and p.get("texte")]
            if extraits:
                lignes.append("\n**Extraits lus directement depuis les pages :**")
                for p in extraits:
                    lignes.append(f"- **{p['titre']}** ({p['url']}) :\n  {p['texte']}")

    return "\n".join(lignes)


@outil(
    nom="lire_page_web",
    description="Ouvre et lit le contenu textuel propre d'une page Web (article, documentation officielle, API) à partir de son URL.",
    parametres={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "L'URL complète http:// ou https:// à lire"},
            "max_mots": {"type": "integer", "description": "Nombre max de mots à extraire (défaut: 1200)", "default": 1200},
        },
        "required": ["url"],
    },
    lent=True,
    phrase_attente="Je lis la page web.",
)
def lire_page_web(url: str, max_mots: int = 1200) -> str:
    """Lit et nettoie une page web publique (protégé SSRF et prompt-injection)."""
    p = _lire_page_brute(url, max_mots=max(100, min(int(max_mots or 1200), 4000)))
    if not p.get("ok"):
        return f"[ERREUR] Impossible de lire {url} : {p.get('erreur', 'échec réseau')}"
    desc = f"\n**Résumé meta :** {p['description']}" if p.get("description") else ""
    return f"**Page :** {p['titre']} ({p['url']}){desc}\n\n{p['texte']}"
