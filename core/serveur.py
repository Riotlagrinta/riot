"""Serveur web unifie de Jarvis : UN seul FastAPI / UN seul port pour tout.

Regroupe, sous un unique tunnel ngrok :
  - le pont iPhone      -> POST /api/inbox        (core.pont_iphone)
  - le webhook Twilio   -> WebSocket /stream      (tools.appel_direct, appels V2)
  - les futures PWA     -> a monter ici (routes /...)

Ainsi ton domaine ngrok statique sert TOUT. Config : section `serveur`
(actif/port/public_url/ngrok_authtoken). Les anciennes cles (pont_iphone.port,
twilio.public_url/ngrok_authtoken, appels.port_stream) restent lues en repli.
"""
import logging
import socket
import threading

# Magasin de certificats Windows : indispensable AVANT pyngrok, dont l'installeur
# telecharge le binaire ngrok en TLS (Malwarebytes intercepte -> sinon "certificate
# verify failed" et le tunnel ne s'ouvre jamais).
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from core.config import reglage

LOG = logging.getLogger("jarvis")

_APP = None
_SERVEUR = None
_URL = None


def _port():
    return int(reglage("serveur.port",
                       reglage("pont_iphone.port", reglage("appels.port_stream", 8790))))


def app():
    """Construit (une fois) l'app FastAPI avec toutes les routes montees."""
    global _APP
    if _APP is None:
        from pathlib import Path
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, Response
        _APP = FastAPI(title="RIOT")
        _RACINE = Path(__file__).resolve().parent.parent

        @_APP.get("/theme.css")
        def route_theme_css():
            f = _RACINE / "web" / "theme.css"
            if not f.exists():
                return Response("", media_type="text/css", status_code=404)
            return Response(f.read_text(encoding="utf-8"), media_type="text/css")

        @_APP.get("/theme.js")
        def route_theme_js():
            f = _RACINE / "web" / "theme.js"
            if not f.exists():
                return Response("", media_type="application/javascript", status_code=404)
            return Response(f.read_text(encoding="utf-8"), media_type="application/javascript")

        @_APP.get("/logo.svg")
        def route_logo_svg():
            f = _RACINE / "web" / "riot-logo.svg"
            if not f.exists():
                return Response("", media_type="image/svg+xml", status_code=404)
            return Response(f.read_text(encoding="utf-8"), media_type="image/svg+xml")

        @_APP.get("/api/version")
        def route_get_version(forcer: bool = False):
            from core import updater
            return updater.etat_mise_a_jour(forcer=forcer)

        @_APP.post("/api/update")
        def route_post_update(request: Request):
            from core import updater
            from core.panneau import _local_seulement
            if not _local_seulement(request):
                return JSONResponse({"ok": False, "erreur": "Mise a jour accessible en local uniquement."}, status_code=403)
            return JSONResponse(updater.executer_mise_a_jour())

        @_APP.get("/api/theme")
        def route_get_theme():
            from core import theme
            return {"ok": True, "theme": theme.theme_actif(), "themes": theme.lister_themes()}

        @_APP.post("/api/theme")
        async def route_set_theme(request: Request):
            from core import theme
            try:
                body = await request.json()
            except Exception:
                body = {}
            t = theme.definir_theme((body or {}).get("theme", ""))
            return JSONResponse({"ok": True, "theme": t})
        from core.pont_iphone import monter_routes
        monter_routes(_APP)                       # /api/inbox, /api/ping
        try:
            from core.panneau import monter_routes as monter_panneau
            monter_panneau(_APP)                  # /panneau + /api/panneau/* (LOCAL uniquement)
        except Exception:
            LOG.exception("montage du panneau de configuration")
        try:
            from core.gestes import monter_routes as monter_gestes
            monter_gestes(_APP)                   # /api/gestes (loopback + token)
        except Exception:
            LOG.exception("montage des routes gestes")
        try:
            from core.cockpit import monter_routes as monter_cockpit
            monter_cockpit(_APP)                  # /cockpit + /api/cockpit/* (LOCAL uniquement)
        except Exception:
            LOG.exception("montage du cockpit")
        try:
            from core.mobile import monter_routes as monter_mobile
            monter_mobile(_APP)                   # /mobile + /api/mobile/* (PWA Smartphone)
        except Exception:
            LOG.exception("montage du module mobile")
        try:
            from core.claude_app import monter_routes as monter_claude
            monter_claude(_APP)                   # / + /claude + /api/claude/* (Interface Claude Web & Desktop)
        except Exception:
            LOG.exception("montage de l'interface Claude")
        try:
            from core.ide import monter_routes as monter_ide
            monter_ide(_APP)                      # /ide + /api/ide/* (RIOT IDE style Antigravity, local)
        except Exception:
            LOG.exception("montage de RIOT IDE")
        try:
            from tools.appel_direct import monter_ws
            monter_ws(_APP)                        # /stream (Twilio Media Streams)
        except Exception:
            LOG.exception("montage du websocket /stream")
    return _APP


def _port_ouvert(port, timeout=0.3):
    try:
        socket.create_connection(("127.0.0.1", port), timeout).close()
        return True
    except OSError:
        return False


def demarrer():
    """Lance le serveur unifie en tache de fond (idempotent). Attend qu'il ecoute."""
    global _SERVEUR
    port = _port()
    if _SERVEUR and _SERVEUR.is_alive():
        return
    import time
    import uvicorn
    config = uvicorn.Config(app(), host="0.0.0.0", port=port, log_level="warning")
    serveur = uvicorn.Server(config)

    def run():
        try:
            serveur.run()   # uvicorn n'installe pas les handlers de signaux hors main thread
        except Exception:
            LOG.exception("serveur web")

    _SERVEUR = threading.Thread(target=run, daemon=True, name="serveur-web")
    _SERVEUR.start()
    for _ in range(40):                # attend l'ouverture du port (max ~6 s)
        if _port_ouvert(port):
            break
        time.sleep(0.15)
    # Ouvre le tunnel distant en arrière-plan pour ne jamais bloquer l'accès local
    try:
        threading.Thread(target=_ouvrir_tunnel, daemon=True, name="tunnel-distant").start()
    except Exception:
        LOG.exception("ouverture du tunnel distant")
    print(f"Serveur web : port {port} (Interface Web/Mobile: http://localhost:{port}/mobile).")


def _ouvrir_tunnel():
    """Ouvre le tunnel distant : Cloudflare Tunnel par défaut (solution A), ou ngrok en repli."""
    global _URL
    if reglage("serveur.public_url", "") or reglage("twilio.public_url", ""):
        return  # URL manuelle configurée

    if _URL:
        return

    # 1. Priorité Solution A : Cloudflare Tunnel
    type_tunnel = reglage("serveur.tunnel", "cloudflare").lower().strip()
    if type_tunnel in ("cloudflare", "auto"):
        try:
            from core import tunnel
            if tunnel.binaire_disponible():
                url_cf = tunnel.demarrer_tunnel_cloudflare(_port())
                if url_cf:
                    _URL = url_cf
                    return
        except Exception:
            LOG.exception("ouverture du tunnel Cloudflare")

    # 2. Repli Solution B : Ngrok si authtoken renseigné
    tok = reglage("serveur.ngrok_authtoken", "") or reglage("twilio.ngrok_authtoken", "")
    if not tok:
        return
    try:
        from pyngrok import ngrok
        ngrok.set_auth_token(tok)
        domaine = reglage("serveur.ngrok_domaine", "")
        options = {"domain": domaine} if domaine else {}
        _URL = ngrok.connect(_port(), "http", **options).public_url
        LOG.info("tunnel ngrok ouvert : %s", _URL)
        print(f"Tunnel ngrok ouvert : {_URL}")
    except Exception as e:
        _URL = None
        LOG.exception("ouverture du tunnel ngrok : %s", e)


def url_publique():
    """Base publique https:// : URL manuelle, sinon le tunnel ngrok auto."""
    manuel = reglage("serveur.public_url", "") or reglage("twilio.public_url", "")
    if manuel:
        return manuel.rstrip("/")
    if not _URL:
        _ouvrir_tunnel()
    return _URL or ""


def url_ws():
    """Base wss:// (pour l'URL du <Stream> de Twilio)."""
    return url_publique().replace("https://", "wss://").replace("http://", "ws://")
