"""Gestionnaire de Connexions Client MCP (Model Context Protocol) pour RIOT.

Permet à RIOT et à ses sous-agents (Swarm, Coder, Trader) de se connecter
à des serveurs MCP tiers (PostgreSQL, GitHub, Fetch, Filesystem, Brave Search, etc.)
configurés dans mcp_servers.json (standard Claude Desktop / Cursor) et d'importer
automatiquement leurs outils dans le registre de l'assistant.
"""
import asyncio
import contextlib
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from core import registre
from core.registre import Outil

LOG = logging.getLogger("riot.mcp_client")
_RACINE = Path(__file__).resolve().parent.parent
_FICHIER_CONFIG_REPO = _RACINE / "mcp_servers.json"
_FICHIER_CONFIG_USER = Path.home() / ".riot" / "mcp_servers.json"

# Catalogue universel de connecteurs MCP prêts à installer en 1 commande (/mcp add <slug>)
CATALOGUE_CONNECTEURS_MCP: Dict[str, Dict[str, Any]] = {
    "fetch": {
        "categorie": "web",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "env_requis": [],
        "description": "Lecture et extraction HTTP/Web distante (0 clé requise)",
    },
    "context7": {
        "categorie": "dev",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
        "env_requis": [],
        "description": "Documentation à jour des librairies et frameworks (0 clé requise)",
    },
    "playwright": {
        "categorie": "web",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"],
        "env_requis": [],
        "description": "Automatisation navigateur web complète via Playwright (0 clé requise)",
    },
    "firecrawl": {
        "categorie": "web",
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env_requis": ["FIRECRAWL_API_KEY"],
        "description": "Scraping JS avancé, crawl de sites entiers et recherche web (Firecrawl)",
    },
    "brave_search": {
        "categorie": "web",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env_requis": ["BRAVE_API_KEY"],
        "description": "Moteur de recherche web & actualités via Brave Search API",
    },
    "tavily": {
        "categorie": "web",
        "command": "npx",
        "args": ["-y", "tavily-mcp@latest"],
        "env_requis": ["TAVILY_API_KEY"],
        "description": "Recherche IA orientée RAG et extraction web (Tavily)",
    },
    "perplexity": {
        "categorie": "web",
        "command": "npx",
        "args": ["-y", "server-perplexity-ask"],
        "env_requis": ["PERPLEXITY_API_KEY"],
        "description": "Synthèse web sourcée temps réel via Perplexity Sonar",
    },
    "github": {
        "categorie": "dev",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env_requis": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
        "description": "Issues, Pull Requests, dépôts et code search GitHub",
    },
    "postgres": {
        "categorie": "data",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", "${POSTGRES_URL}"],
        "env_requis": ["POSTGRES_URL"],
        "description": "Inspection et requêtes SQL sur PostgreSQL / Neon / PostGIS",
    },
    "neon": {
        "categorie": "data",
        "command": "npx",
        "args": ["-y", "@neondatabase/mcp-server-neon"],
        "env_requis": ["NEON_API_KEY"],
        "description": "Gestion de projets, branches et SQL sur Neon Serverless Postgres",
    },
    "supabase": {
        "categorie": "data",
        "command": "npx",
        "args": ["-y", "@supabase/mcp-server-supabase@latest"],
        "env_requis": ["SUPABASE_ACCESS_TOKEN"],
        "description": "Gestion des bases Supabase, SQL, RLS et Edge Functions",
    },
    "notion": {
        "categorie": "saas",
        "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "env_requis": ["NOTION_TOKEN"],
        "description": "Lecture et écriture de pages et bases de données Notion",
    },
    "slack": {
        "categorie": "saas",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env_requis": ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
        "description": "Lecture et envoi de messages dans les canaux Slack",
    },
    "stripe": {
        "categorie": "saas",
        "command": "npx",
        "args": ["-y", "@stripe/mcp"],
        "env_requis": ["STRIPE_SECRET_KEY"],
        "description": "Clients, abonnements, factures et paiements Stripe",
    },
    "google_workspace": {
        "categorie": "saas",
        "command": "uvx",
        "args": ["workspace-mcp"],
        "env_requis": ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"],
        "description": "Connexion Google Workspace (Drive, Docs, Sheets, Gmail, Calendar)",
    },
}

# État interne du client MCP
_BOUCLE_ASYNC: Optional[asyncio.AbstractEventLoop] = None
_THREAD_FOND: Optional[threading.Thread] = None
_SESSIONS_ACTIVES: Dict[str, Any] = {}          # nom_serveur -> ClientSession
_STACKS_ACTIVES: Dict[str, Any] = {}            # nom_serveur -> AsyncExitStack
_STATUTS_SERVEURS: Dict[str, Dict[str, Any]] = {} # nom_serveur -> métadonnées & statut
_OUTILS_MCP_ENREGISTRES: set = set()


def fichier_config_mcp() -> Path:
    """Retourne le chemin persistant (~/.riot/mcp_servers.json) protégé des mises à jour CLI."""
    env_cfg = os.environ.get("RIOT_MCP_CONFIG", "").strip()
    if env_cfg:
        return Path(env_cfg)
    return _FICHIER_CONFIG_USER


def _resoudre_placeholders_env(valeur: str, extra_env: Optional[Dict[str, str]] = None) -> str:
    """Remplace ${VAR} par extra_env ou os.environ sans modifier les autres chaînes."""
    import re
    s = str(valeur)
    def _sub(m):
        nom = m.group(1)
        if extra_env and nom in extra_env and str(extra_env[nom]).strip():
            return str(extra_env[nom]).strip()
        return os.environ.get(nom, m.group(0))
    return re.sub(r"\$\{([A-Za-z0-9_]+)\}", _sub, s)


def _initialiser_boucle_fond():
    """Initialise le thread d'arrière-plan dédié aux sessions MCP asyncio."""
    global _BOUCLE_ASYNC, _THREAD_FOND
    if _BOUCLE_ASYNC is not None and _BOUCLE_ASYNC.is_running():
        return

    _BOUCLE_ASYNC = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(_BOUCLE_ASYNC)
        _BOUCLE_ASYNC.run_forever()

    _THREAD_FOND = threading.Thread(target=run, daemon=True, name="mcp-client-loop")
    _THREAD_FOND.start()


def _presets_defaut_mcp() -> Dict[str, Any]:
    """Configuration MCP par défaut activée automatiquement au premier démarrage (connecteurs 0-clé)."""
    return {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "description": CATALOGUE_CONNECTEURS_MCP["fetch"]["description"],
                "enabled": bool(shutil.which("uvx")),
            },
            "context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp"],
                "description": CATALOGUE_CONNECTEURS_MCP["context7"]["description"],
                "enabled": bool(shutil.which("npx")),
            },
            "playwright": {
                "command": "npx",
                "args": ["-y", "@playwright/mcp@latest"],
                "description": CATALOGUE_CONNECTEURS_MCP["playwright"]["description"],
                "enabled": False,
            },
            "firecrawl": {
                "command": "npx",
                "args": ["-y", "firecrawl-mcp"],
                "description": CATALOGUE_CONNECTEURS_MCP["firecrawl"]["description"],
                "enabled": False,
            },
        }
    }


def charger_config_mcp() -> Dict[str, Any]:
    """Lit la config MCP utilisateur (~/.riot/mcp_servers.json), ou l'initialise avec les connecteurs par défaut."""
    cible = fichier_config_mcp()
    if not cible.exists() and cible == _FICHIER_CONFIG_USER:
        if _FICHIER_CONFIG_REPO.exists():
            try:
                cible.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_FICHIER_CONFIG_REPO, cible)
            except Exception:
                pass
        else:
            defaut = _presets_defaut_mcp()
            sauvegarder_config_mcp(defaut)
            return defaut
    chemin = cible if cible.exists() else _FICHIER_CONFIG_REPO
    if not chemin.exists():
        return _presets_defaut_mcp()
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else _presets_defaut_mcp()
    except Exception as e:
        LOG.exception("Erreur lecture %s : %s", chemin, e)
        return _presets_defaut_mcp()


def sauvegarder_config_mcp(config: Dict[str, Any]):
    """Sauvegarde la configuration dans le fichier persistant utilisateur."""
    cible = fichier_config_mcp()
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        with open(cible, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        LOG.exception("Erreur écriture %s : %s", cible, e)


async def _connecter_serveur_stdio(nom: str, details: dict):
    """Établit la connexion avec un serveur MCP en transport stdio (processus fils)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cmd = details.get("command", "")
    env = details.get("env")
    env_dict = env if isinstance(env, dict) else {}
    args = [_resoudre_placeholders_env(a, env_dict) for a in (details.get("args") or [])]

    # Pré-vérification binaire et variables non résolues
    exe = shutil.which(cmd)
    if not exe:
        _STATUTS_SERVEURS[nom] = {
            "statut": "erreur",
            "transport": "stdio",
            "commande": f"{cmd} {' '.join(args)}",
            "description": details.get("description", ""),
            "outils_count": 0,
            "outils": [],
            "erreur": f"Binaire '{cmd}' introuvable sur cette machine.",
            "connecte_a": None,
        }
        return

    non_resolus = [a for a in args if "${" in str(a) and "}" in str(a)]
    if non_resolus:
        _STATUTS_SERVEURS[nom] = {
            "statut": "erreur",
            "transport": "stdio",
            "commande": f"{cmd} {' '.join(args)}",
            "description": details.get("description", ""),
            "outils_count": 0,
            "outils": [],
            "erreur": f"Variable manquante dans args : {', '.join(non_resolus)}",
            "connecte_a": None,
        }
        return

    env_complet = os.environ.copy()
    for k, v in env_dict.items():
        val = _resoudre_placeholders_env(str(v), env_dict)
        if val and not (val.startswith("${") and val.endswith("}")):
            env_complet[str(k)] = val

    params = StdioServerParameters(command=exe, args=args, env=env_complet)
    stack = contextlib.AsyncExitStack()

    try:
        read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()

        tools_response = await session.list_tools()
        outils_decouverts = tools_response.tools or []

        _SESSIONS_ACTIVES[nom] = session
        _STACKS_ACTIVES[nom] = stack
        _STATUTS_SERVEURS[nom] = {
            "statut": "connecté",
            "transport": "stdio",
            "commande": f"{cmd} {' '.join(args)}",
            "description": details.get("description", ""),
            "outils_count": len(outils_decouverts),
            "outils": [t.name for t in outils_decouverts],
            "erreur": None,
            "connecte_a": time.strftime("%H:%M:%S")
        }

        # Enregistrement des outils dans le registre de RIOT
        for t in outils_decouverts:
            _enregistrer_outil_mcp(nom, t, session)

    except Exception as e:
        await stack.aclose()
        _STATUTS_SERVEURS[nom] = {
            "statut": "erreur",
            "transport": "stdio",
            "commande": f"{cmd} {' '.join(args)}",
            "description": details.get("description", ""),
            "outils_count": 0,
            "outils": [],
            "erreur": str(e),
            "connecte_a": None
        }
        LOG.warning("Échec connexion serveur MCP '%s' : %s", nom, e)


async def _connecter_serveur_sse(nom: str, details: dict):
    """Établit la connexion avec un serveur MCP distant via HTTP Server-Sent Events (SSE)."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    url = details.get("url", "")
    headers = details.get("headers", {})

    stack = contextlib.AsyncExitStack()
    try:
        read_stream, write_stream = await stack.enter_async_context(sse_client(url, headers=headers))
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()

        tools_response = await session.list_tools()
        outils_decouverts = tools_response.tools or []

        _SESSIONS_ACTIVES[nom] = session
        _STACKS_ACTIVES[nom] = stack
        _STATUTS_SERVEURS[nom] = {
            "statut": "connecté",
            "transport": "sse",
            "url": url,
            "description": details.get("description", ""),
            "outils_count": len(outils_decouverts),
            "outils": [t.name for t in outils_decouverts],
            "erreur": None,
            "connecte_a": time.strftime("%H:%M:%S")
        }

        for t in outils_decouverts:
            _enregistrer_outil_mcp(nom, t, session)

    except Exception as e:
        await stack.aclose()
        _STATUTS_SERVEURS[nom] = {
            "statut": "erreur",
            "transport": "sse",
            "url": url,
            "description": details.get("description", ""),
            "outils_count": 0,
            "outils": [],
            "erreur": str(e),
            "connecte_a": None
        }
        LOG.warning("Échec connexion SSE MCP '%s' : %s", nom, e)


def _enregistrer_outil_mcp(nom_serveur: str, tool_def: Any, session: Any):
    """Enregistre un outil découvert depuis un serveur MCP dans le registre global de RIOT."""
    nom_outil = f"mcp_{nom_serveur}_{tool_def.name}"
    description_complete = f"[MCP: {nom_serveur}] {tool_def.description or tool_def.name}"
    parametres = getattr(tool_def, "inputSchema", None) or {"type": "object", "properties": {}}

    def wrapper(**kwargs):
        """Fonction synchrone appelée par l'assistant, relayée vers la session MCP asyncio."""
        async def call_coro():
            res = await session.call_tool(tool_def.name, arguments=kwargs)
            textes = []
            if hasattr(res, "content"):
                for bloc in res.content:
                    if getattr(bloc, "type", None) == "text":
                        textes.append(getattr(bloc, "text", ""))
                    elif hasattr(bloc, "text"):
                        textes.append(str(bloc.text))
                    else:
                        textes.append(str(bloc))
            return "\n".join(textes) if textes else "OK (exécution terminée sans retour textuel)"

        future = asyncio.run_coroutine_threadsafe(call_coro(), _BOUCLE_ASYNC)
        try:
            return future.result(timeout=45)
        except Exception as err:
            return f"[ERREUR MCP] Échec appel de {nom_outil} : {err}"

    # Déclaration dans le registre global
    registre._REGISTRE[nom_outil] = Outil(
        fonction=wrapper,
        nom=nom_outil,
        description=description_complete,
        parametres=parametres,
        confirmation=False,
        lent=False,
        phrase_attente=f"Appel du serveur MCP {nom_serveur}...",
        annonce=None,
        mcp_expose=False,
        affichage="auto"
    )
    _OUTILS_MCP_ENREGISTRES.add(nom_outil)


async def _connecter_serveur_streamable_http(nom: str, details: dict):
    """Établit la connexion avec un serveur MCP distant via Streamable HTTP."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    import httpx

    url = _resoudre_placeholders_env(details.get("url", ""))
    raw_headers = details.get("headers") if isinstance(details.get("headers"), dict) else {}
    headers = {str(k): _resoudre_placeholders_env(str(v)) for k, v in raw_headers.items()}

    stack = contextlib.AsyncExitStack()
    try:
        http_client = httpx.AsyncClient(headers=headers, timeout=20.0) if headers else None
        if http_client is not None:
            await stack.enter_async_context(http_client)
        read_stream, write_stream, _ = await stack.enter_async_context(
            streamable_http_client(url, http_client=http_client)
        )
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()

        tools_response = await session.list_tools()
        outils_decouverts = tools_response.tools or []

        _SESSIONS_ACTIVES[nom] = session
        _STACKS_ACTIVES[nom] = stack
        _STATUTS_SERVEURS[nom] = {
            "statut": "connecté",
            "transport": "http",
            "url": url,
            "description": details.get("description", ""),
            "outils_count": len(outils_decouverts),
            "outils": [t.name for t in outils_decouverts],
            "erreur": None,
            "connecte_a": time.strftime("%H:%M:%S"),
        }
        for t in outils_decouverts:
            _enregistrer_outil_mcp(nom, t, session)
    except Exception as e:
        await stack.aclose()
        _STATUTS_SERVEURS[nom] = {
            "statut": "erreur",
            "transport": "http",
            "url": url,
            "description": details.get("description", ""),
            "outils_count": 0,
            "outils": [],
            "erreur": str(e),
            "connecte_a": None,
        }
        LOG.warning("Échec connexion HTTP MCP '%s' : %s", nom, e)


async def _demarrer_tous_serveurs_async():
    """Démarre toutes les connexions actives définies dans mcp_servers.json."""
    config = charger_config_mcp()
    serveurs = config.get("mcpServers", {})

    for nom, details in serveurs.items():
        if not details.get("enabled", True):
            _STATUTS_SERVEURS[nom] = {
                "statut": "désactivé",
                "description": details.get("description", ""),
                "outils_count": 0,
                "outils": [],
                "erreur": None
            }
            continue

        if "command" in details:
            await _connecter_serveur_stdio(nom, details)
        elif "url" in details:
            trans = str(details.get("transport") or "").strip().lower()
            url_s = str(details.get("url") or "").strip().lower()
            if trans in ("http", "streamable_http", "streamable-http") or (not trans and url_s.endswith("/mcp")):
                await _connecter_serveur_streamable_http(nom, details)
            else:
                await _connecter_serveur_sse(nom, details)


async def _fermer_tous_serveurs_async():
    """Ferme proprement toutes les connexions MCP ouvertes."""
    for nom, stack in list(_STACKS_ACTIVES.items()):
        try:
            await stack.aclose()
        except Exception:
            pass
    _SESSIONS_ACTIVES.clear()
    _STACKS_ACTIVES.clear()

    # Nettoyage des outils MCP du registre
    for nom_o in _OUTILS_MCP_ENREGISTRES:
        registre._REGISTRE.pop(nom_o, None)
    _OUTILS_MCP_ENREGISTRES.clear()


def initialiser_connexions_mcp():
    """Point d'entrée synchrone pour démarrer l'ensemble des serveurs MCP configurés."""
    _initialiser_boucle_fond()
    future = asyncio.run_coroutine_threadsafe(_demarrer_tous_serveurs_async(), _BOUCLE_ASYNC)
    try:
        future.result(timeout=15)
    except Exception as e:
        LOG.warning("Délai d'initialisation MCP dépassé ou erreur : %s", e)


def recharger_connexions_mcp():
    """Recharge à chaud l'ensemble des serveurs MCP sans redémarrer RIOT."""
    _initialiser_boucle_fond()
    async def reload_all():
        await _fermer_tous_serveurs_async()
        await _demarrer_tous_serveurs_async()

    future = asyncio.run_coroutine_threadsafe(reload_all(), _BOUCLE_ASYNC)
    try:
        future.result(timeout=20)
        return True
    except Exception as e:
        LOG.exception("Erreur rechargement MCP : %s", e)
        return False


def statut_mcp() -> Dict[str, Any]:
    """Retourne l'état complet des connexions MCP pour affichage CLI ou API Web."""
    return {
        "serveurs": _STATUTS_SERVEURS,
        "total_outils_mcp": len(_OUTILS_MCP_ENREGISTRES),
        "outils_enregistres": sorted(list(_OUTILS_MCP_ENREGISTRES))
    }


def ajouter_serveur_mcp(
    nom: str,
    commande: str,
    args: Optional[List[str]] = None,
    description: str = "",
    env: Optional[Dict[str, str]] = None,
    recharger: bool = True,
):
    """Ajoute dynamiquement un serveur MCP dans la configuration et tente la connexion."""
    cfg = charger_config_mcp()
    entree: Dict[str, Any] = {
        "command": commande,
        "args": args or [],
        "description": description or f"Serveur MCP {nom}",
        "enabled": True,
    }
    if env:
        entree["env"] = dict(env)
    cfg.setdefault("mcpServers", {})[nom] = entree
    sauvegarder_config_mcp(cfg)
    if recharger:
        recharger_connexions_mcp()


def lister_catalogue_connecteurs() -> List[Dict[str, Any]]:
    """Retourne la liste des connecteurs MCP du catalogue avec leur statut d'installation."""
    cfg = charger_config_mcp().get("mcpServers", {})
    out: List[Dict[str, Any]] = []
    for slug, spec in CATALOGUE_CONNECTEURS_MCP.items():
        deja = cfg.get(slug)
        out.append({
            "slug": slug,
            "categorie": spec["categorie"],
            "description": spec["description"],
            "env_requis": list(spec.get("env_requis") or []),
            "installe": slug in cfg,
            "actif": bool(deja and deja.get("enabled", True)),
        })
    return out


def installer_connecteur_catalogue(
    slug: str,
    credential: str = "",
    activer: bool = True,
    recharger: bool = True,
) -> Dict[str, Any]:
    """Installe un connecteur du catalogue officiel dans ~/.riot/mcp_servers.json."""
    cle = (slug or "").strip().lower().replace("-", "_")
    spec = CATALOGUE_CONNECTEURS_MCP.get(cle)
    if not spec:
        return {"ok": False, "erreur": f"Connecteur '{slug}' inconnu. Lance `/mcp catalog`."}

    cfg = charger_config_mcp()
    serveurs = cfg.setdefault("mcpServers", {})
    env_requis = list(spec.get("env_requis") or [])
    env_map: Dict[str, str] = {}
    cred = (credential or "").strip()
    if env_requis:
        if cred:
            env_map[env_requis[0]] = cred
        else:
            for var_nom in env_requis:
                if os.environ.get(var_nom, "").strip():
                    env_map[var_nom] = os.environ[var_nom].strip()

    entree: Dict[str, Any] = {
        "command": spec["command"],
        "args": list(spec["args"]),
        "description": spec["description"],
        "enabled": bool(activer),
    }
    if env_map:
        entree["env"] = env_map
    serveurs[cle] = entree
    sauvegarder_config_mcp(cfg)
    if activer and recharger:
        recharger_connexions_mcp()
    return {
        "ok": True,
        "slug": cle,
        "actif": bool(activer),
        "env_requis": env_requis,
        "env_manquantes": [v for v in env_requis if v not in env_map and not os.environ.get(v)],
        "config_path": str(fichier_config_mcp()),
    }


def basculer_connecteur_mcp(nom: str, enabled: bool, recharger: bool = True) -> bool:
    """Active ou désactive un serveur MCP existant dans la configuration utilisateur."""
    cfg = charger_config_mcp()
    srv = (cfg.get("mcpServers") or {}).get(nom)
    if not isinstance(srv, dict):
        return False
    srv["enabled"] = bool(enabled)
    sauvegarder_config_mcp(cfg)
    if recharger:
        recharger_connexions_mcp()
    return True


def supprimer_connecteur_mcp(nom: str, recharger: bool = True) -> bool:
    """Supprime un connecteur MCP de la configuration utilisateur."""
    cfg = charger_config_mcp()
    serveurs = cfg.get("mcpServers") or {}
    if nom not in serveurs:
        return False
    del serveurs[nom]
    sauvegarder_config_mcp(cfg)
    if recharger:
        recharger_connexions_mcp()
    return True
