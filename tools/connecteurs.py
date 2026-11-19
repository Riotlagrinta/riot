"""Outils natifs de connectivite et d'integration pour RIOT (Git, HTTP/REST, GitHub, MCP).

Completes les serveurs MCP externes avec des connecteurs Python natifs zero-dependance :
  - Git (status, diff, log) isole sur le projet actif
  - Requete API HTTP/JSON securisee (protection anti-SSRF)
  - GitHub REST (infos depot, PRs/issues publiques ou privees via GITHUB_PERSONAL_ACCESS_TOKEN)
  - Pilotage en langage naturel des connecteurs MCP (catalogue, installation, activation)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from core.registre import outil
from tools.web import _valider_url_publique


def _dossier_projet_actif() -> Path:
    try:
        from core.cli import _SESSION_CTX
        p = _SESSION_CTX.get("projet_actif")
        if isinstance(p, Path) and p.exists():
            return p
    except Exception:
        pass
    return Path.cwd()


def _run_git(args: list[str], cwd: Path, timeout: int = 10) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return f"[ERREUR git] {err or out or f'code {proc.returncode}'}"
    return out or "(aucune sortie)"


@outil(
    nom="git_status",
    description="Affiche l'etat Git du projet actif (branche, fichiers modifies, non suivis, en attente).",
    parametres={"type": "object", "properties": {}},
)
def git_status() -> str:
    """Retourne git status --short --branch sur le projet actif."""
    return _run_git(["status", "--short", "--branch"], _dossier_projet_actif())


@outil(
    nom="git_diff",
    description="Affiche les modifications Git (diff unifie) du projet actif ou d'un fichier precis.",
    parametres={
        "type": "object",
        "properties": {
            "fichier": {"type": "string", "description": "Chemin relatif optionnel du fichier"},
            "staged": {"type": "boolean", "description": "True pour voir le diff indexe (--cached)", "default": False},
        },
    },
)
def git_diff(fichier: str = "", staged: bool = False) -> str:
    """Retourne le diff Git borne a 6000 caracteres."""
    args = ["diff"]
    if staged:
        args.append("--cached")
    if (fichier or "").strip():
        args.extend(["--", fichier.strip()])
    out = _run_git(args, _dossier_projet_actif())
    return out[:6000] + ("\n... [diff tronque]" if len(out) > 6000 else "")


@outil(
    nom="git_log",
    description="Affiche les derniers commits Git du projet actif (hash, date, auteur, message).",
    parametres={
        "type": "object",
        "properties": {
            "limite": {"type": "integer", "description": "Nombre de commits a afficher (defaut: 10)", "default": 10},
        },
    },
)
def git_log(limite: int = 10) -> str:
    """Retourne les N derniers commits en format compact."""
    n = max(1, min(int(limite or 10), 30))
    return _run_git(["log", f"-n{n}", "--oneline", "--decorate"], _dossier_projet_actif())


@outil(
    nom="requete_api_http",
    description="Envoie une requete HTTP/REST (GET, POST, PUT, PATCH, DELETE) vers une API publique distante "
                "avec protection anti-SSRF et retourne le statut et la reponse JSON/texte.",
    parametres={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL publique https:// de l'endpoint API"},
            "methode": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
            "headers_json": {"type": "string", "description": "Objet JSON optionnel des en-tetes HTTP"},
            "body_json": {"type": "string", "description": "Objet JSON optionnel du corps de la requete"},
        },
        "required": ["url"],
    },
    lent=True,
    phrase_attente="J'interroge l'API distante.",
)
def requete_api_http(
    url: str,
    methode: str = "GET",
    headers_json: str = "",
    body_json: str = "",
) -> str:
    """Connecteur HTTP/REST securise contre SSRF (localhost et reseaux prives bloques)."""
    ok, cible = _valider_url_publique(url)
    if not ok:
        return f"[ERREUR SECURITE] {cible}"

    method = (methode or "GET").strip().upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return f"[ERREUR] Methode HTTP non supportee : {method}"

    headers: Dict[str, str] = {"Accept": "application/json, text/plain;q=0.9", "User-Agent": "RIOT-Connector/1.0"}
    if headers_json.strip():
        try:
            parsed_h = json.loads(headers_json)
            if isinstance(parsed_h, dict):
                for k, v in parsed_h.items():
                    headers[str(k)] = str(v)
        except Exception as e:
            return f"[ERREUR] headers_json invalide : {e}"

    payload: Optional[Any] = None
    if body_json.strip():
        try:
            payload = json.loads(body_json)
        except Exception as e:
            return f"[ERREUR] body_json invalide : {e}"

    try:
        r = requests.request(method, cible, headers=headers, json=payload, timeout=12, allow_redirects=False)
        corps = r.text[:4500]
        return f"HTTP {r.status_code} ({cible})\n{corps}"
    except Exception as e:
        return f"[ERREUR HTTP] {e}"


@outil(
    nom="github_repo_info",
    description="Consulte les informations d'un depot GitHub (etoiles, langage, branche, issues ouvertes) "
                "sans avoir besoin d'un serveur MCP Node.js.",
    parametres={
        "type": "object",
        "properties": {
            "depot": {"type": "string", "description": "Format 'proprietaire/repo' (ex: 'Riotlagrinta/riot')"},
            "inclure_issues": {"type": "boolean", "description": "Inclure les 5 dernieres issues/PRs ouvertes", "default": True},
        },
        "required": ["depot"],
    },
    lent=True,
    phrase_attente="Je consulte GitHub.",
)
def github_repo_info(depot: str, inclure_issues: bool = True) -> str:
    """Connecteur natif GitHub REST API v3."""
    slug = (depot or "").strip().strip("/")
    if slug.startswith("https://github.com/"):
        slug = slug[len("https://github.com/"):].strip("/")
    if slug.count("/") != 1:
        return "[ERREUR] Format attendu : 'proprietaire/repo' (ex: 'fastapi/fastapi')."

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "RIOT-GitHub/1.0"}
    tok = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    try:
        r = requests.get(f"https://api.github.com/repos/{slug}", headers=headers, timeout=10)
        if r.status_code != 200:
            return f"[ERREUR GitHub HTTP {r.status_code}] {r.text[:300]}"
        d = r.json()
        lignes = [
            f"### GitHub : {d.get('full_name', slug)}",
            f"- **Description :** {d.get('description') or '-'}",
            f"- **Langage :** {d.get('language') or '-'} | **Branche :** {d.get('default_branch') or '-'}",
            f"- **Stars :** {d.get('stargazers_count', 0)} | **Issues ouvertes :** {d.get('open_issues_count', 0)}",
            f"- **URL :** {d.get('html_url')}",
        ]
        if inclure_issues:
            ri = requests.get(
                f"https://api.github.com/repos/{slug}/issues",
                headers=headers,
                params={"state": "open", "per_page": 5},
                timeout=10,
            )
            if ri.status_code == 200 and isinstance(ri.json(), list):
                issues = ri.json()
                if issues:
                    lignes.append("\n**Dernières issues/PRs ouvertes :**")
                    for it in issues:
                        kind = "PR" if "pull_request" in it else "Issue"
                        lignes.append(f"- #{it.get('number')} [{kind}] {it.get('title')} ({it.get('html_url')})")
        return "\n".join(lignes)
    except Exception as e:
        return f"[ERREUR GitHub] {e}"


@outil(
    nom="lister_connecteurs_mcp",
    description="Liste les connecteurs MCP disponibles dans le catalogue RIOT (firecrawl, context7, github, supabase, neon, notion, stripe...) et leur etat actif.",
    parametres={"type": "object", "properties": {}},
)
def lister_connecteurs_mcp() -> str:
    """Retourne le catalogue MCP et l'etat des connexions actives."""
    from core import mcp_client
    cat = mcp_client.lister_catalogue_connecteurs()
    st = mcp_client.statut_mcp().get("serveurs", {})
    lignes = [f"### Catalogue des Connecteurs MCP ({len(cat)}) :"]
    for c in cat:
        slug = c["slug"]
        etat_live = (st.get(slug) or {}).get("statut") or ("actif" if c["actif"] else ("installe" if c["installe"] else "disponible"))
        envs = ", ".join(c["env_requis"]) if c["env_requis"] else "0 cle"
        lignes.append(f"- **{slug}** [{c['categorie']}] ({etat_live}) — {c['description']} | Env: {envs}")
    return "\n".join(lignes)


@outil(
    nom="installer_connecteur_mcp",
    description="Installe et active un connecteur MCP du catalogue (ex: context7, fetch, firecrawl, github, supabase, neon, notion, stripe).",
    parametres={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Nom court du connecteur dans le catalogue (ex: context7, firecrawl, github)"},
            "credential": {"type": "string", "description": "Cle API ou URL PostgreSQL optionnelle", "default": ""},
        },
        "required": ["slug"],
    },
    lent=True,
    phrase_attente="J'installe le connecteur MCP.",
)
def installer_connecteur_mcp(slug: str, credential: str = "") -> str:
    """Installe un connecteur du catalogue et tente la connexion a chaud."""
    from core import mcp_client
    res = mcp_client.installer_connecteur_catalogue(slug, credential=credential, activer=True, recharger=True)
    if not res.get("ok"):
        return f"[ERREUR] {res.get('erreur', 'echec installation')}"
    manq = res.get("env_manquantes") or []
    msg = f"Connecteur '{res['slug']}' installe dans {res['config_path']}."
    if manq:
        msg += f" Variables manquantes a renseigner : {', '.join(manq)}."
    return msg


@outil(
    nom="basculer_connecteur_mcp",
    description="Active ou desactive un connecteur MCP deja installe dans ~/.riot/mcp_servers.json.",
    parametres={
        "type": "object",
        "properties": {
            "nom": {"type": "string", "description": "Nom du connecteur MCP"},
            "actif": {"type": "boolean", "description": "True pour activer, False pour desactiver"},
        },
        "required": ["nom", "actif"],
    },
)
def basculer_connecteur_mcp(nom: str, actif: bool) -> str:
    """Active ou desactive un connecteur MCP."""
    from core import mcp_client
    ok = mcp_client.basculer_connecteur_mcp(nom, enabled=bool(actif), recharger=True)
    if not ok:
        return f"[ERREUR] Connecteur '{nom}' introuvable."
    return f"Connecteur '{nom}' {'active' if actif else 'desactive'}."
