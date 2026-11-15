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
_FICHIER_CONFIG_MCP = _RACINE / "mcp_servers.json"

# État interne du client MCP
_BOUCLE_ASYNC: Optional[asyncio.AbstractEventLoop] = None
_THREAD_FOND: Optional[threading.Thread] = None
_SESSIONS_ACTIVES: Dict[str, Any] = {}          # nom_serveur -> ClientSession
_STACKS_ACTIVES: Dict[str, Any] = {}            # nom_serveur -> AsyncExitStack
_STATUTS_SERVEURS: Dict[str, Dict[str, Any]] = {} # nom_serveur -> métadonnées & statut
_OUTILS_MCP_ENREGISTRES: set = set()


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


def charger_config_mcp() -> Dict[str, Any]:
    """Lit le fichier standard mcp_servers.json."""
    if not _FICHIER_CONFIG_MCP.exists():
        return {"mcpServers": {}}
    try:
        with open(_FICHIER_CONFIG_MCP, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        LOG.exception("Erreur lecture mcp_servers.json : %s", e)
        return {"mcpServers": {}}


def sauvegarder_config_mcp(config: Dict[str, Any]):
    """Sauvegarde la configuration dans mcp_servers.json."""
    try:
        with open(_FICHIER_CONFIG_MCP, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        LOG.exception("Erreur écriture mcp_servers.json : %s", e)


async def _connecter_serveur_stdio(nom: str, details: dict):
    """Établit la connexion avec un serveur MCP en transport stdio (processus fils)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cmd = details.get("command", "")
    args = details.get("args", [])
    env = details.get("env")

    # Résolution binaire Windows si nécessaire
    exe = shutil.which(cmd) or cmd
    env_complet = os.environ.copy()
    if env and isinstance(env, dict):
        env_complet.update(env)

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


def ajouter_serveur_mcp(nom: str, commande: str, args: Optional[List[str]] = None, description: str = ""):
    """Ajoute dynamiquement un serveur MCP dans la configuration et tente la connexion."""
    cfg = charger_config_mcp()
    cfg.setdefault("mcpServers", {})[nom] = {
        "command": commande,
        "args": args or [],
        "description": description or f"Serveur MCP {nom}",
        "enabled": True
    }
    sauvegarder_config_mcp(cfg)
    recharger_connexions_mcp()
