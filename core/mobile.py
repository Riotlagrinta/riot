"""Module Web & Mobile de Kéranos : Interface tactile et contrôle à distance.

Permet de piloter le PC, lancer des actions rapides, capturer l'écran en direct
et dialoguer avec Kéranos par texte et voix depuis n'importe quel smartphone
sur le réseau local ou via tunnel distant (PWA Mobile-First).
"""
import asyncio
import base64
import json
import logging
import re
import socket
import time
from datetime import datetime
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from core import auth, budget, config, etude, memoire, registre
from core.config import reglage
from core.llm import llm

LOG = logging.getLogger("jarvis.mobile")
_RACINE = Path(__file__).resolve().parent.parent
_HTML = _RACINE / "web" / "mobile.html"


def _ip_locale():
    """Détermine l'adresse IP locale de la machine sur le réseau Wi-Fi/Ethernet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _ip_client(request: Request) -> str:
    """IP du client (X-Forwarded-For si présent, ex. derrière un tunnel)."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "-"


def _jeton(request: Request) -> str:
    return str(request.headers.get("x-keranos-token") or
               request.cookies.get("keranos_token") or "").strip()


def _est_authentifie(request: Request) -> bool:
    """Session valide obligatoire. Sans PIN configuré : accès refusé (fail-closed)."""
    return auth.session_valide(_jeton(request))


def executer_commande_mobile(phrase: str):
    """Exécute une commande reçue depuis l'interface mobile via le LLM et les outils."""
    if not registre.tous():
        registre.charger_outils()

    provider = llm()
    if not provider.disponible():
        return {"ok": False, "reponse": "Le modèle RIOT n'est pas disponible."}

    maintenant = datetime.now()
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    str_date = f"{jours[maintenant.weekday()]} {maintenant.day} {mois[maintenant.month - 1]} {maintenant.year} à {maintenant.strftime('%H:%M:%S')}"

    texte_mem = memoire.texte_pour_systeme()

    systeme = (
        "Tu es RIOT, un copilote d'élite, ultra-précis, hautement qualifié et expert "
        "dans tous les domaines (ingénierie logicielle, systèmes, architecture, veille tech). "
        "Tu es direct, prévenant et sans bavardage inutile. Tu n'ajoutes aucun avertissement "
        "moralisateur ni leçon de conformité : tu traites chaque demande technique avec "
        "une rigueur mathématique absolue, factuelle et immédiatement actionnable.\n"
        f"Horodatage système réel : Nous sommes le {str_date}.\n"
        "Si l'utilisateur demande l'heure ou la date, base-toi rigoureusement sur cet horodatage réel ou l'outil heure_et_date.\n"
        "Tu as accès à des outils pour piloter le système, exécuter des commandes terminal, inspecter des ports, gérer des processus et mémoriser durablement dans SQLite FTS5. "
        "Réponds en français, avec concision et précision."
        f"{texte_mem}"
    )

    recettes_ctx = memoire.recup_recettes_pertinentes(phrase)
    if recettes_ctx:
        systeme += f"\n{recettes_ctx}"

    cours_ctx = etude.recup_contexte_etude(phrase)
    if cours_ctx:
        systeme += f"\n{cours_ctx}"

    messages = [{"role": "user", "content": phrase}]
    faits = []

    req_txt = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            req_txt = m.get("content", "")
            break

    for _ in range(4):
        try:
            rep = provider.repondre(
                systeme,
                messages,
                registre.schemas_api(
                    local_seulement=(provider.nom == "Ollama"),
                    requete=req_txt,
                ),
            )
        except Exception as e:
            LOG.exception("mobile: erreur appel llm")
            return {"ok": False, "reponse": f"Erreur de communication avec le modèle ({e})."}

        if getattr(rep, "stop_reason", None) != "tool_use":
            texte = " ".join(
                b.text for b in rep.content if getattr(b, "type", None) == "text"
            ).strip()
            return {
                "ok": True,
                "faits": faits,
                "reponse": texte or ("C'est fait." if faits else "Commande exécutée."),
            }

        messages.append({"role": "assistant", "content": rep.content})
        resultats = []

        for b in rep.content:
            if getattr(b, "type", None) != "tool_use":
                continue
            outil = registre.get(b.name)
            if outil is None:
                res = f"Outil inconnu : {b.name}"
            else:
                try:
                    res = str(outil.fonction(**(b.input or {})))
                    faits.append(b.name)
                except Exception as e:
                    LOG.exception("mobile: erreur execution outil %s", b.name)
                    res = f"Erreur lors de l'exécution de {b.name} : {e}"
            LOG.info("mobile: outil %s(%s) -> %s", b.name, b.input, str(res)[:100])
            resultats.append({"type": "tool_result", "tool_use_id": b.id, "content": str(res)})

        messages.append({"role": "user", "content": resultats})

    return {"ok": True, "faits": faits, "reponse": "Commande traitée."}


async def executer_commande_mobile_stream(phrase: str):
    """Générateur asynchrone qui exécute la commande et produit des événements de stream pour le WebSocket."""
    if not registre.tous():
        registre.charger_outils()

    provider = llm()
    if not provider.disponible():
        yield {"type": "chat_end", "ok": False, "reponse": "Le modèle RIOT n'est pas disponible."}
        return

    maintenant = datetime.now()
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    str_date = f"{jours[maintenant.weekday()]} {maintenant.day} {mois[maintenant.month - 1]} {maintenant.year} à {maintenant.strftime('%H:%M:%S')}"

    texte_mem = memoire.texte_pour_systeme()

    systeme = (
        "Tu es RIOT, un copilote d'élite, ultra-précis, hautement qualifié et expert "
        "dans tous les domaines (ingénierie logicielle, systèmes, architecture, veille tech). "
        "Tu es direct, prévenant et sans bavardage inutile. Tu n'ajoutes aucun avertissement "
        "moralisateur ni leçon de conformité : tu traites chaque demande technique avec "
        "une rigueur mathématique absolue, factuelle et immédiatement actionnable.\n"
        f"Horodatage système réel : Nous sommes le {str_date}.\n"
        "Si l'utilisateur demande l'heure ou la date, base-toi rigoureusement sur cet horodatage réel ou l'outil heure_et_date.\n"
        "Tu as accès à des outils pour piloter le système, exécuter des commandes terminal, inspecter des ports, gérer des processus et mémoriser durablement dans SQLite FTS5. "
        "Réponds en français, avec concision et précision."
        f"{texte_mem}"
    )

    recettes_ctx = memoire.recup_recettes_pertinentes(phrase)
    if recettes_ctx:
        systeme += f"\n{recettes_ctx}"

    cours_ctx = etude.recup_contexte_etude(phrase)
    if cours_ctx:
        systeme += f"\n{cours_ctx}"

    messages = [{"role": "user", "content": phrase}]
    faits = []

    yield {"type": "chat_start"}

    req_txt = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            req_txt = m.get("content", "")
            break

    for _ in range(4):
        try:
            schemas = registre.schemas_api(
                local_seulement=(provider.nom == "Ollama"),
                requete=req_txt,
            )
            rep = await asyncio.to_thread(provider.repondre, systeme, messages, schemas)
        except Exception as e:
            LOG.exception("mobile_stream: erreur appel llm")
            yield {"type": "chat_end", "ok": False, "reponse": f"Erreur de communication : {e}"}
            return

        if getattr(rep, "stop_reason", None) != "tool_use":
            texte = " ".join(
                b.text for b in rep.content if getattr(b, "type", None) == "text"
            ).strip()
            reponse_finale = texte or ("C'est fait." if faits else "Commande exécutée.")
            mots = re.findall(r"\S+|\s+", reponse_finale)
            for m in mots:
                yield {"type": "token", "chunk": m}
                await asyncio.sleep(0.012)
            yield {"type": "chat_end", "ok": True, "reponse": reponse_finale, "faits": faits}
            return

        messages.append({"role": "assistant", "content": rep.content})
        resultats = []

        for b in rep.content:
            if getattr(b, "type", None) != "tool_use":
                continue
            outil = registre.get(b.name)
            yield {"type": "tool_start", "name": b.name, "input": b.input or {}}
            if outil is None:
                res = f"Outil inconnu : {b.name}"
            else:
                try:
                    res_raw = await asyncio.to_thread(outil.fonction, **(b.input or {}))
                    res = str(res_raw)
                    faits.append(b.name)
                except Exception as e:
                    LOG.exception("mobile_stream: erreur outil %s", b.name)
                    res = f"Erreur lors de l'exécution de {b.name} : {e}"
            yield {"type": "tool_end", "name": b.name, "result": str(res)[:160]}
            resultats.append({"type": "tool_result", "tool_use_id": b.id, "content": str(res)})

        messages.append({"role": "user", "content": resultats})

    yield {"type": "chat_end", "ok": True, "reponse": "Commande traitée.", "faits": faits}



def monter_routes(app):
    """Enregistre les routes Web & Mobile sur l'instance FastAPI."""

    @app.get("/mobile", response_class=HTMLResponse)
    def page_mobile(request: Request):
        if not _HTML.exists():
            return HTMLResponse("<h1>Interface mobile en construction.</h1>", status_code=404)
        return HTMLResponse(_HTML.read_text(encoding="utf-8"))

    @app.get("/mobile/manifest.json")
    def manifest():
        return {
            "name": "RIOT Mobile",
            "short_name": "RIOT",
            "start_url": "/mobile",
            "display": "standalone",
            "background_color": "#080b10",
            "theme_color": "#00d2ff",
            "description": "Contrôle à distance et assistant vocal pour PC",
            "icons": [
                {
                    "src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='45' fill='%23080b10' stroke='%2300d2ff' stroke-width='6'/><circle cx='50' cy='50' r='20' fill='%23ff9d00'/></svg>",
                    "sizes": "192x192 512x512",
                    "type": "image/svg+xml"
                }
            ]
        }

    @app.post("/api/mobile/auth")
    async def route_connexion(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        pin_saisi = str(body.get("pin", "")).strip()
        ok, valeur, code = auth.connexion(pin_saisi, _ip_client(request))
        if not ok:
            return JSONResponse({"ok": False, "message": valeur}, status_code=code)
        rep = JSONResponse({"ok": True, "token": valeur, "message": "Connexion réussie."})
        rep.set_cookie("keranos_token", valeur, max_age=auth.DUREE_SESSION,
                       httponly=True, samesite="strict")
        return rep

    @app.post("/api/mobile/logout")
    def route_deconnexion(request: Request):
        jeton = _jeton(request)
        if jeton:
            auth.revoquer_session(jeton)
            auth.audit("DECONNEXION", _ip_client(request))
        rep = JSONResponse({"ok": True})
        rep.delete_cookie("keranos_token")
        return rep

    @app.get("/api/mobile/telemetry")
    async def telemetrie(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)

        cpu = 0
        ram = 0
        disque_libre = 0
        try:
            import psutil
            cpu = round(psutil.cpu_percent(interval=None))
            ram = round(psutil.virtual_memory().percent)
            disque_libre = round(psutil.disk_usage("C:\\").free / (1024 ** 3))
        except Exception:
            pass

        provider = llm()
        b_res = budget.resume()

        url_pub = ""
        try:
            from core import serveur
            url_pub = serveur.url_publique()
        except Exception:
            pass

        return {
            "ok": True,
            "ip_locale": _ip_locale(),
            "port": int(reglage("serveur.port", 8790)),
            "url_publique": url_pub,
            "tunnel_distant": bool(url_pub),
            "cpu_pct": cpu,
            "ram_pct": ram,
            "disque_libre_go": disque_libre,
            "llm_provider": provider.nom,
            "llm_modele": getattr(provider, "modele", "-"),
            "budget_jour": b_res.get("total_jour", 0.0),
            "plafond_jour": b_res.get("plafond_jour", 0.0),
            "requiert_pin": True,
        }

    @app.post("/api/mobile/action")
    async def action(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)

        try:
            body = await request.json()
        except Exception:
            body = {}

        type_act = body.get("type", "")
        auth.audit("ACTION", _ip_client(request), str(type_act))

        try:
            from tools import systeme, verrouillage, ecran

            if type_act == "volume_monter":
                res = systeme.regler_volume("monter", crans=5)
                return {"ok": True, "message": res}

            elif type_act == "volume_baisser":
                res = systeme.regler_volume("baisser", crans=5)
                return {"ok": True, "message": res}

            elif type_act == "volume_muet":
                res = systeme.controler_media("muet")
                return {"ok": True, "message": res}

            elif type_act in ("media_pause", "pause"):
                res = systeme.controler_media("pause")
                return {"ok": True, "message": res}

            elif type_act in ("media_suivant", "suivant"):
                res = systeme.controler_media("suivant")
                return {"ok": True, "message": res}

            elif type_act in ("media_precedent", "precedent"):
                res = systeme.controler_media("precedent")
                return {"ok": True, "message": res}

            elif type_act == "verrouiller":
                res = verrouillage.verrouiller_pc()
                return {"ok": True, "message": res}

            elif type_act == "capture_ecran":
                cap = ecran.capture_screen(0)
                if isinstance(cap, dict) and "image" in cap:
                    b64 = cap["image"].get("data", "")
                    return {"ok": True, "image": f"data:image/jpeg;base64,{b64}"}
                return {"ok": False, "message": "Échec de la capture d'écran."}

            elif type_act == "ouvrir_app":
                nom = body.get("app", "")
                res = systeme.ouvrir_application(nom)
                return {"ok": True, "message": res}

            elif type_act == "eteindre_pc":
                res = systeme.eteindre_pc()
                return {"ok": True, "message": res}

            elif type_act == "annuler_extinction":
                res = systeme.annuler_extinction()
                return {"ok": True, "message": res}

            else:
                return {"ok": False, "message": f"Action inconnue : {type_act}"}

        except Exception as e:
            LOG.exception("mobile: erreur action %s", type_act)
            return {"ok": False, "message": f"Erreur : {e}"}

    @app.post("/api/mobile/chat")
    async def chat(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)

        try:
            body = await request.json()
        except Exception:
            body = {}

        message = str(body.get("message", "")).strip()
        if not message:
            return JSONResponse({"ok": False, "message": "Message vide."}, status_code=400)

        audio_sortie = str(body.get("audio_sortie", "mobile")).lower().strip()
        auth.audit("CHAT", _ip_client(request), message)
        resultat = await asyncio.to_thread(executer_commande_mobile, message)

        if audio_sortie == "pc" and resultat.get("ok"):
            try:
                from core import voix
                texte_a_dire = resultat.get("reponse", "")
                if texte_a_dire:
                    await asyncio.to_thread(voix.parler, texte_a_dire)
            except Exception:
                LOG.exception("mobile: erreur synthese vocale PC")

        return resultat

    @app.post("/api/mobile/terminal")
    async def terminal_direct(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)

        try:
            body = await request.json()
        except Exception:
            body = {}

        commande = str(body.get("commande", "")).strip()
        if not commande:
            return JSONResponse({"ok": False, "message": "Commande vide."}, status_code=400)

        shell = str(body.get("shell", "powershell")).strip()
        cwd = str(body.get("cwd", "")).strip()
        timeout = int(body.get("timeout", 30))

        auth.audit("TERMINAL_MANUEL", _ip_client(request), commande)
        from tools import terminal
        sortie = await asyncio.to_thread(
            terminal.executer_terminal,
            commande=commande,
            shell=shell,
            cwd=cwd,
            timeout=timeout,
            confirme=True,
        )
        return {"ok": True, "commande": commande, "sortie": sortie}

    @app.get("/api/mobile/recettes")
    def lister_recettes(request: Request, q: str = ""):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        if q.strip():
            recettes = memoire.rechercher_recettes_code(q.strip(), limite=20)
        else:
            recettes = memoire.lister_recettes_code(limite=30)
        return {"ok": True, "recettes": recettes}

    @app.post("/api/mobile/recettes")
    async def creer_recette(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        titre = str(body.get("titre", "")).strip()
        probleme = str(body.get("probleme", "")).strip()
        solution = str(body.get("solution", "")).strip()
        if not titre or not solution:
            return JSONResponse({"ok": False, "message": "Titre et solution obligatoires."}, status_code=400)
        rec_id = memoire.ajouter_recette_code(
            titre=titre,
            probleme=probleme,
            solution=solution,
            cause=str(body.get("cause", "")).strip(),
            langage=str(body.get("langage", "")).strip(),
            tags=str(body.get("tags", "")).strip(),
        )
        auth.audit("RECETTE_CREEE", _ip_client(request), titre)
        return {"ok": True, "id": rec_id, "message": f"Recette #{rec_id} enregistrée."}

    @app.get("/api/mobile/regles")
    def lister_regles_dev(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        return {"ok": True, "regles": memoire.lister_regles_dev()}

    @app.post("/api/mobile/regles")
    async def creer_regle_dev(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        try:
            body = await request.json()
        except Exception:
            body = {}
        cle = str(body.get("cle", "")).strip()
        regle = str(body.get("regle", "")).strip()
        if not cle or not regle:
            return JSONResponse({"ok": False, "message": "Clé et règle obligatoires."}, status_code=400)
        memoire.ajouter_regle_dev(cle, regle)
        auth.audit("REGLE_DEV_CREEE", _ip_client(request), cle)
        return {"ok": True, "cle": cle, "message": "Règle enregistrée."}

    @app.delete("/api/mobile/regles/{cle}")
    def supprimer_regle_dev(request: Request, cle: str):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        ok = memoire.supprimer_regle_dev(cle)
        auth.audit("REGLE_DEV_SUPPRIMEE", _ip_client(request), cle)
        return {"ok": ok, "message": "Règle supprimée." if ok else "Règle introuvable."}

    @app.get("/api/mobile/etude/fichiers")
    def lister_fichiers_etude(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        return {"ok": True, "fichiers": etude.lister_fichiers_etude()}

    @app.post("/api/mobile/etude/sync")
    def synchroniser_etude(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        res = etude.synchroniser_dossier_etude()
        auth.audit("ETUDE_SYNC", _ip_client(request), f"fichiers={res.get('fichiers_indexes')}")
        return res

    @app.get("/api/mobile/tunnel/statut")
    def statut_tunnel(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        from core import tunnel
        return {"ok": True, **tunnel.statut_tunnel()}

    @app.post("/api/mobile/tunnel/demarrer")
    def demarrer_tunnel(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        from core import tunnel
        port = int(reglage("serveur.port", 8790))
        url = tunnel.demarrer_tunnel_cloudflare(port)
        if url:
            return {"ok": True, "url": url, "message": f"Tunnel Cloudflare actif : {url}/mobile"}
        return JSONResponse({"ok": False, "message": "Échec du démarrage du tunnel Cloudflare."}, status_code=500)

    @app.post("/api/mobile/tunnel/arreter")
    def arreter_tunnel(request: Request):
        if not _est_authentifie(request):
            return JSONResponse({"ok": False, "message": "Non authentifié."}, status_code=401)
        from core import tunnel
        tunnel.arreter_tunnel()
        return {"ok": True, "message": "Tunnel arrêté."}

    @app.websocket("/ws/riot")
    async def websocket_riot(websocket: WebSocket):
        await websocket.accept()

        token = websocket.query_params.get("token") or websocket.cookies.get("keranos_token")
        if not auth.session_valide(token):
            # Tolérance : attendre un message d'authentification initial dans les 5 secondes
            try:
                msg_initial = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
                if msg_initial.get("type") == "auth":
                    token = msg_initial.get("token", "")
            except Exception:
                pass

        if not auth.session_valide(token):
            await websocket.send_json({"type": "auth_error", "message": "Session non authentifiée ou expirée."})
            await websocket.close(code=4001)
            return

        await websocket.send_json({"type": "auth_ok", "message": "Connecté au flux temps réel RIOT."})

        # Tâche de diffusion télémétrie en temps réel
        arret_telemetrie = asyncio.Event()

        async def boucle_telemetrie():
            import psutil
            try:
                last_io = psutil.net_io_counters()
            except Exception:
                last_io = None
            last_t = time.time()

            while not arret_telemetrie.is_set():
                await asyncio.sleep(1.5)
                try:
                    now = time.time()
                    dt = max(now - last_t, 0.5)
                    kb_in, kb_out = 0.0, 0.0
                    try:
                        cur_io = psutil.net_io_counters()
                        if last_io:
                            kb_in = round((cur_io.bytes_recv - last_io.bytes_recv) / (dt * 1024), 1)
                            kb_out = round((cur_io.bytes_sent - last_io.bytes_sent) / (dt * 1024), 1)
                        last_io = cur_io
                        last_t = now
                    except Exception:
                        pass

                    cpu = round(psutil.cpu_percent(interval=None))
                    vm = psutil.virtual_memory()
                    ram_pct = round(vm.percent)
                    ram_libre_go = round(vm.available / (1024 ** 3), 1)
                    disque_libre_go = round(psutil.disk_usage("C:\\").free / (1024 ** 3))

                    from core import tunnel
                    st_tunnel = tunnel.statut_tunnel()

                    await websocket.send_json({
                        "type": "telemetry",
                        "data": {
                            "cpu_pct": cpu,
                            "ram_pct": ram_pct,
                            "ram_libre_go": ram_libre_go,
                            "disque_libre_go": disque_libre_go,
                            "kb_in": kb_in,
                            "kb_out": kb_out,
                            "tunnel_actif": st_tunnel.get("actif", False),
                            "tunnel_url": st_tunnel.get("url_publique"),
                        }
                    })
                except Exception:
                    break

        tache_telemetrie = asyncio.create_task(boucle_telemetrie())

        try:
            while True:
                data = await websocket.receive_json()
                t = data.get("type")

                if t == "ping":
                    await websocket.send_json({"type": "pong"})

                elif t == "chat":
                    msg = str(data.get("message", "")).strip()
                    if msg:
                        auth.audit("WS_CHAT", websocket.client.host if websocket.client else "-", msg)
                        async for evt in executer_commande_mobile_stream(msg):
                            await websocket.send_json(evt)

                elif t == "terminal":
                    cmd = str(data.get("commande", "")).strip()
                    shell = str(data.get("shell", "powershell")).strip()
                    cwd = str(data.get("cwd", "")).strip()
                    timeout = int(data.get("timeout", 30))
                    if cmd:
                        auth.audit("WS_TERMINAL", websocket.client.host if websocket.client else "-", cmd)
                        from tools import terminal
                        res = await asyncio.to_thread(terminal.executer_terminal, cmd, shell=shell, cwd=cwd, timeout=timeout, confirme=True)
                        await websocket.send_json({"type": "terminal_result", "commande": cmd, "sortie": res})

                elif t == "etude_sync":
                    from core import etude
                    res = await asyncio.to_thread(etude.synchroniser_dossier_etude)
                    await websocket.send_json({"type": "etude_sync_result", **res})

        except WebSocketDisconnect:
            pass
        except Exception as e:
            LOG.warning("ws: déconnexion : %s", e)
        finally:
            arret_telemetrie.set()
            tache_telemetrie.cancel()



