"""Backend pour l'Application Web et Desktop façon Claude (Claude RIOT).



Fournit les API REST et le streaming Server-Sent Events (SSE) pour l'interface :



- Navigation et sélection des projets locaux (E:\\PROJETS)



- Sélecteur de modes : Swarm Multi-Agents (Méthode 2) ou Développeur Coder



- Streaming des réflexions, des tool calls animés et des étapes du Swarm



- Explorateur de fichiers et volet d'Artifacts interactif



- Mode Application Desktop autonome via navigateur Chromium (--app)



"""



import asyncio



import json



import logging



import os



import shutil



import subprocess



import time



from datetime import datetime



from pathlib import Path



from typing import Optional, AsyncGenerator



from fastapi import Request



from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse



from core import auth, budget, config, memoire, registre



from core.cli import _SESSION_CTX, _recup_branche_git



from core.config import reglage, dossier_projets



from core.llm import llm



LOG = logging.getLogger("riot.claude")



_RACINE = Path(__file__).resolve().parent.parent



_HTML_CLAUDE = _RACINE / "web" / "claude.html"



_PROJETS_DIR = dossier_projets()



def _trouver_navigateur() -> Optional[str]:



    """Détecte Google Chrome, Microsoft Edge ou Brave pour le mode Desktop App."""



    candidats = [



        r"C:\Program Files\Google\Chrome\Application\chrome.exe",



        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",



        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",



        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",



        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",



    ]



    for c in candidats:



        if Path(c).exists():



            return c



    for nom in ("chrome", "msedge", "brave", "chromium"):



        exe = shutil.which(nom)



        if exe:



            return exe



    return None



def lancer_app_desktop(port: int = 8790):



    """Lance l'interface en application de bureau native fenêtrée."""



    navigateur = _trouver_navigateur()



    url = f"http://localhost:{port}/"



    if navigateur:



        try:



            profile_dir = Path.home() / ".riot_desktop_profile"



            profile_dir.mkdir(parents=True, exist_ok=True)



            subprocess.Popen([



                navigateur,



                f"--app={url}",



                f"--user-data-dir={str(profile_dir)}",



                "--window-size=1360,880",



                "--new-window",



            ])



            return True



        except Exception as e:



            LOG.exception("Erreur lancement app desktop : %s", e)



    import webbrowser



    webbrowser.open(url)



    return True



def _lister_projets():



    """Liste tous les projets disponibles dans le répertoire racine des projets, avec Discussion Libre en tête."""



    projet_actif = _SESSION_CTX.get("projet_actif")



    projets = [



        {



            "nom": "Discussion Libre (Sans projet)",



            "chemin": "",



            "branche": "",



            "libre": True,



            "actif": (projet_actif is None)



        }



    ]



    if not _PROJETS_DIR.exists():



        return projets



    dossiers_ignores = {



        "temps_js", "temps_py", "input_js", "input_py", "output_js", "output_py",



        "erreurs_js", "erreurs_py", "traites_js", "traites_py", "$recycle.bin",



        "system volume information", ".git"



    }



    for p in sorted(_PROJETS_DIR.iterdir(), key=lambda x: x.name.lower()):



        if p.is_dir() and not p.name.startswith(".") and p.name.lower() not in dossiers_ignores:



            branche = _recup_branche_git(p)



            est_actif = False



            if projet_actif is not None:



                try:



                    est_actif = (p.resolve() == projet_actif.resolve())



                except Exception:



                    pass



            projets.append({



                "nom": p.name,



                "chemin": str(p),



                "branche": branche or "main",



                "libre": False,



                "actif": est_actif



            })



    return projets



def _extraire_arborescence(racine: Optional[Path], max_profondeur: int = 2):



    """Génère l'arborescence des fichiers du projet actif pour le volet Artifacts."""



    if not racine or not Path(racine).exists():



        return []



    arbo = []



    dossiers_exclus = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", "dist", "build"}



    def explorer(dossier: Path, profondeur: int):



        if profondeur > max_profondeur:



            return



        try:



            entrees = sorted(dossier.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))



            for e in entrees:



                if e.name in dossiers_exclus or e.name.startswith("."):



                    continue



                rel_path = str(e.relative_to(racine)).replace("\\", "/")



                if e.is_dir():



                    arbo.append({"type": "dossier", "nom": e.name, "chemin": rel_path})



                    explorer(e, profondeur + 1)



                else:



                    arbo.append({"type": "fichier", "nom": e.name, "chemin": rel_path, "taille": e.stat().st_size})



        except Exception:



            pass



    explorer(racine, 1)



    return arbo[:120]



_HISTORIQUE_CHAT: list = []



def _construire_historique_tour(chat_id: Optional[str], instruction: str, max_messages: int = 8) -> list:



    """Construit l'historique multi-tours compact pour préserver le contexte sans saturer les limites TPM."""



    if chat_id:



        msgs = memoire.obtenir_messages_chat(chat_id, limit=max_messages)



        # On ne garde que les messages précédents



        bruts = [



            {"role": m["role"], "content": m["content"]}



            for m in msgs



            if isinstance(m.get("content"), str) and m.get("content").strip()



        ]



    else:



        bruts = [



            {"role": m["role"], "content": m["content"]}



            for m in _HISTORIQUE_CHAT[-max_messages:]



            if isinstance(m.get("content"), str) and m.get("content").strip()



        ]



    recent = []



    budget_chars = 8000



    for m in reversed(bruts):



        txt = m["content"].strip()



        if len(txt) > 1200:



            txt = txt[:900] + "\n... [tronqué]\n" + txt[-250:]



        if budget_chars - len(txt) < 0 and recent:



            break



        budget_chars -= len(txt)



        recent.append({"role": m["role"], "content": txt})



    recent.reverse()



    if not recent or recent[-1]["role"] != "user" or recent[-1]["content"] != instruction:



        recent.append({"role": "user", "content": instruction})



    return recent



def _memoriser_tour(chat_id: Optional[str], question: str, reponse: str):



    """Mémorise l'échange (secrets redactés) dans SQLite persistante et le cache de session."""



    if question and reponse:



        q_safe = memoire._masquer_texte(question, max_len=16000) or question.strip()



        r_safe = memoire._masquer_texte(reponse, max_len=16000) or reponse.strip()



        if chat_id:



            memoire.ajouter_message_chat(chat_id, "user", q_safe)



            memoire.ajouter_message_chat(chat_id, "assistant", r_safe)



        _HISTORIQUE_CHAT.append({"role": "user", "content": q_safe})



        _HISTORIQUE_CHAT.append({"role": "assistant", "content": r_safe})



        if len(_HISTORIQUE_CHAT) > 20:



            del _HISTORIQUE_CHAT[:-20]

        memoire.lancer_auto_memoire_asynchrone(q_safe, r_safe, surface="studio")



def formater_fichiers_joints(fichiers: list) -> str:



    """Met en forme les fichiers transmis par l'utilisateur pour injection dans le contexte du modèle."""



    if not fichiers:



        return ""



    blocs = []



    for f in fichiers:



        if not isinstance(f, dict):



            continue



        nom = f.get("nom", "fichier_sans_nom")



        contenu = str(f.get("contenu", "")).strip()



        ext = Path(nom).suffix.lstrip(".").lower() or "txt"



        if len(contenu) > 150_000:



            contenu = contenu[:150_000] + "\n\n[... CONTENU TRONQUÉ CAR SUPÉRIEUR À 150 KO ...]"



        nb_lignes = len(contenu.splitlines())



        blocs.append(



            f"=== 📄 FICHIER FOURNI PAR L'UTILISATEUR : {nom} ({nb_lignes} lignes) ===\n"



            f"```{ext}\n{contenu}\n```\n"



            f"=== FIN DU FICHIER {nom} ==="



        )



    return "\n\n".join(blocs)



def monter_routes(app):



    """Enregistre l'ensemble des routes Claude Web & Desktop sur FastAPI."""



    try:



        registre.charger_outils()



    except Exception as e:



        LOG.warning("Erreur chargement outils Claude: %s", e)



    @app.get("/", response_class=HTMLResponse)
    @app.get("/studio", response_class=HTMLResponse)



    @app.get("/claude", response_class=HTMLResponse)



    def page_claude(request: Request):



        if not _HTML_CLAUDE.exists():



            return HTMLResponse("<h1>Interface RIOT Studio en préparation.</h1>", status_code=404)



        return HTMLResponse(_HTML_CLAUDE.read_text(encoding="utf-8"))



    @app.post("/api/claude/nouveau_chat")



    def reinitialiser_chat():



        _HISTORIQUE_CHAT.clear()



        return {"ok": True, "message": "Historique de conversation réinitialisé."}



    @app.get("/api/claude/chats")



    def lister_tous_les_chats():



        """Liste l'ensemble des discussions sauvegardées sur SQLite."""



        return {"ok": True, "chats": memoire.lister_sessions_chat(limit=50)}



    @app.get("/captures/{nom_fichier}")



    @app.get("/api/claude/captures/{nom_fichier}")



    def route_capture_image(nom_fichier: str):



        """Sert les captures d'écran générées par les outils navigateur et écran."""



        from fastapi.responses import FileResponse



        nom_nettoye = Path(nom_fichier).name



        chemin = (_RACINE / "_captures" / nom_nettoye).resolve()



        if chemin.exists() and chemin.is_file():



            media = "image/jpeg" if chemin.suffix.lower() in (".jpg", ".jpeg") else "image/png"



            return FileResponse(chemin, media_type=media)



        return JSONResponse({"erreur": "Capture introuvable."}, status_code=404)

    @app.get("/api/claude/vibetg/pubs/statut")
    async def vibetg_statut_api():
        from tools.vibetg_ads import MOTEUR_PUBS
        return JSONResponse(MOTEUR_PUBS.statut_dict())

    @app.post("/api/claude/vibetg/pubs/activer")
    async def vibetg_activer_api(req: Request):
        from tools.vibetg_ads import MOTEUR_PUBS
        try:
            data = await req.json()
            nombre = int(data.get("nombre_pubs", 7))
        except Exception:
            nombre = 7
        rep = MOTEUR_PUBS.demarrer(nombre_pubs=nombre)
        return JSONResponse({"message": rep, "statut": MOTEUR_PUBS.statut_dict()})

    @app.post("/api/claude/vibetg/pubs/arreter")
    async def vibetg_arreter_api():
        from tools.vibetg_ads import MOTEUR_PUBS
        rep = MOTEUR_PUBS.arreter()
        return JSONResponse({"message": rep, "statut": MOTEUR_PUBS.statut_dict()})

    @app.post("/api/claude/vibetg/pubs/mode_nuit")
    async def vibetg_mode_nuit_api(req: Request):
        from tools.vibetg_ads import MOTEUR_PUBS
        try:
            data = await req.json()
            heure = str(data.get("heure_fin", "09:00"))
        except Exception:
            heure = "09:00"
        try:
            p_min = float(data.get("pause_min", 5))
            p_max = float(data.get("pause_max", 7))
        except Exception:
            p_min = 5
            p_max = 7
        rep = MOTEUR_PUBS.configurer_mode_nuit(heure_fin=heure, pause_min_min=p_min, pause_max_min=p_max)
        return JSONResponse({"message": rep, "statut": MOTEUR_PUBS.statut_dict()})



    @app.post("/api/claude/chats/nouveau")



    async def creer_chat_api(request: Request):



        """Crée une nouvelle discussion persistante dans la base de données."""



        try:



            body = await request.json()



        except Exception:



            body = {}



        titre = str(body.get("titre", "Nouvelle discussion")).strip() or "Nouvelle discussion"



        mode = str(body.get("mode", "swarm")).strip()



        projet = _SESSION_CTX.get("projet_actif")



        nom_proj = projet.name if projet else ""



        cid = memoire.creer_session_chat(titre=titre, mode=mode, projet=nom_proj)



        _HISTORIQUE_CHAT.clear()



        return {"ok": True, "chat_id": cid}



    @app.get("/api/claude/chats/{chat_id}")



    def get_details_chat(chat_id: str):



        """Récupère tous les messages d'un chat pour continuer la discussion."""



        session = memoire.obtenir_session_chat(chat_id)



        if not session:



            return JSONResponse({"ok": False, "erreur": "Chat introuvable."}, status_code=404)



        return {"ok": True, "chat": session}



    @app.delete("/api/claude/chats/{chat_id}")



    def delete_chat_api(chat_id: str):



        """Supprime une discussion et ses messages."""



        ok = memoire.supprimer_session_chat(chat_id)



        return {"ok": ok}



    @app.patch("/api/claude/chats/{chat_id}")



    async def patch_chat_titre(chat_id: str, request: Request):



        """Renomme le titre d'une discussion."""



        try:



            body = await request.json()



            titre = str(body.get("titre", "")).strip()



            if titre:



                memoire.renommer_session_chat(chat_id, titre)



            return {"ok": True}



        except Exception as e:



            return JSONResponse({"ok": False, "erreur": str(e)}, status_code=500)



    @app.get("/claude/manifest.json")



    def manifest_pwa():



        return {



            "name": "RIOT Studio",



            "short_name": "RIOT",



            "start_url": "/claude",



            "display": "standalone",



            "background_color": "#0B0C0E",



            "theme_color": "#E8A838",



            "description": "Assistant IA Claude & Swarm Multi-Agents autonome pour développeur",



            "icons": [



                {



                    "src": "/logo.svg",



                    "sizes": "192x192 512x512",



                    "type": "image/svg+xml"



                }



            ]



        }



    @app.get("/claude/sw.js")



    def service_worker():



        code_sw = """



        const CACHE_NAME = 'claude-riot-v1';



        self.addEventListener('install', (e) => { self.skipWaiting(); });



        self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });



        self.addEventListener('fetch', (e) => {



            if (e.request.method === 'GET' && e.request.url.includes('/claude')) {



                e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));



            }



        });



        """



        from fastapi import Response



        return Response(content=code_sw, media_type="application/javascript")



    @app.get("/api/claude/session")



    def session_info():



        import psutil



        projet = _SESSION_CTX.get("projet_actif")



        from core.llm import identite_publique
        provider = llm()
        pub = identite_publique(provider)



        vm = psutil.virtual_memory()



        cpu = psutil.cpu_percent(interval=None)



        return {



            "ok": True,



            "projet": {



                "nom": projet.name if projet else "Discussion Libre",



                "chemin": str(projet) if projet else "",



                "branche": _recup_branche_git(projet) if projet else "",



                "libre": (projet is None)



            },



            "llm": {



                "modele": pub["modele"],



                "fournisseur": pub["nom"],



                "disponible": provider.disponible()



            },



            "systeme": {



                "cpu": round(cpu),



                "ram_pct": round(vm.percent),



                "ram_dispo_go": round(vm.available / (1024 ** 3), 1),



                "ram_totale_go": round(vm.total / (1024 ** 3), 1)



            },



            "tokens": {



                "prompt": _SESSION_CTX["tokens_prompt"],



                "reponse": _SESSION_CTX["tokens_reponse"],



                "total": _SESSION_CTX["tokens_prompt"] + _SESSION_CTX["tokens_reponse"]



            }



        }



    @app.get("/api/claude/projets")



    def get_projets():



        return {"ok": True, "projets": _lister_projets()}



    @app.post("/api/claude/changer_projet")



    async def changer_projet(request: Request):



        try:



            body = await request.json()



            nom_ou_chemin = str(body.get("projet", "")).strip()



            if not nom_ou_chemin or nom_ou_chemin.lower() in ("libre", "discussion libre", "discussion libre (sans projet)", "aucun", "sans", "reset"):



                _SESSION_CTX["projet_actif"] = None



                return {



                    "ok": True,



                    "projet": {



                        "nom": "Discussion Libre",



                        "chemin": "",



                        "branche": "",



                        "libre": True



                    }



                }



            candidat = Path(nom_ou_chemin)



            if not candidat.is_absolute():



                p_test = _PROJETS_DIR / nom_ou_chemin



                if p_test.exists():



                    candidat = p_test



            if candidat.exists() and candidat.is_dir():



                _SESSION_CTX["projet_actif"] = candidat



                return {



                    "ok": True,



                    "projet": {



                        "nom": candidat.name,



                        "chemin": str(candidat),



                        "branche": _recup_branche_git(candidat) or "main",



                        "libre": False



                    }



                }



            return JSONResponse({"ok": False, "erreur": f"Dossier introuvable : {nom_ou_chemin}"}, status_code=404)



        except Exception as e:



            return JSONResponse({"ok": False, "erreur": str(e)}, status_code=500)



    @app.get("/api/claude/mcp")



    def get_mcp_statut():



        from core import mcp_client



        return {"ok": True, "mcp": mcp_client.statut_mcp()}



    @app.post("/api/claude/mcp/reload")



    def post_mcp_reload():



        from core import mcp_client



        ok = mcp_client.recharger_connexions_mcp()



        return {"ok": ok, "mcp": mcp_client.statut_mcp()}



    @app.get("/api/claude/arborescence")



    def get_arborescence():



        projet = _SESSION_CTX.get("projet_actif")



        if not projet:



            return {"ok": True, "fichiers": []}



        return {"ok": True, "fichiers": _extraire_arborescence(projet)}



    @app.get("/api/claude/fichier")



    def lire_fichier(chemin: str):



        projet = _SESSION_CTX.get("projet_actif")



        if not projet:



            return JSONResponse({"ok": False, "erreur": "Aucun projet sélectionné. Activez un projet pour consulter ses fichiers."}, status_code=400)



        cible = (projet / chemin).resolve()



        # Sécurité : interdire les traversées hors du projet



        try:



            cible.relative_to(projet.resolve())



        except ValueError:



            return JSONResponse({"ok": False, "erreur": "Accès interdit hors du projet."}, status_code=403)



        if not cible.exists() or not cible.is_file():



            return JSONResponse({"ok": False, "erreur": "Fichier introuvable."}, status_code=404)



        try:



            taille = cible.stat().st_size



            if taille > 1_500_000:



                return JSONResponse({"ok": False, "erreur": "Fichier trop volumineux (> 1.5 Mo)."}, status_code=400)



            contenu = cible.read_text(encoding="utf-8", errors="replace")



            ext = cible.suffix.lstrip(".").lower()



            return {



                "ok": True,



                "nom": cible.name,



                "chemin": chemin,



                "extension": ext,



                "contenu": contenu



            }



        except Exception as e:



            return JSONResponse({"ok": False, "erreur": str(e)}, status_code=500)



    @app.get("/api/claude/pdf/telecharger")



    def telecharger_pdf(chemin: str):



        """Permet de visualiser ou télécharger un fichier PDF généré."""



        from fastapi.responses import FileResponse



        dossier_sortie = _RACINE / "output_pdf"



        projet_actif = _SESSION_CTX.get("projet_actif")



        nom_nettoye = Path(chemin).name  # Protection contre path traversal



        cible = (dossier_sortie / nom_nettoye).resolve()



        if not cible.exists() and projet_actif and isinstance(projet_actif, Path):



            candidat_proj = (projet_actif / nom_nettoye).resolve()



            if candidat_proj.exists():



                cible = candidat_proj



        if not cible.exists() or not cible.is_file() or cible.suffix.lower() != ".pdf":



            return JSONResponse({"ok": False, "erreur": "Fichier PDF introuvable."}, status_code=404)



        return FileResponse(



            cible,



            media_type="application/pdf",



            filename=cible.name,



            headers={"Content-Disposition": f'inline; filename="{cible.name}"'},



        )



    @app.get("/api/claude/document/telecharger")



    def telecharger_document(chemin: str):



        """Permet de télécharger un document bureautique généré (PDF, Excel, PowerPoint)."""



        from fastapi.responses import FileResponse



        dossiers_sorties = [



            _RACINE / "output_documents",



            _RACINE / "output_pdf",



            _RACINE / "output_products",



            _RACINE / "_captures",



        ]



        projet_actif = _SESSION_CTX.get("projet_actif")



        if projet_actif and isinstance(projet_actif, Path):



            dossiers_sorties.append(projet_actif)



        nom_nettoye = Path(chemin).name  # Protection contre path traversal



        cible = None



        for d in dossiers_sorties:



            if not d.exists():



                continue



            cand = (d / nom_nettoye).resolve()



            if cand.exists() and cand.is_file():



                cible = cand



                break



            # Recherche dans les sous-dossiers de produits ou documents



            if d.is_dir():



                trouve = list(d.rglob(nom_nettoye))



                if trouve and trouve[0].is_file():



                    cible = trouve[0].resolve()



                    break



        extensions_autorisees = {".pdf", ".xlsx", ".pptx", ".csv", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".html", ".mermaid", ".zip", ".md", ".json", ".sql", ".tsx", ".ts"}



        if not cible or cible.suffix.lower() not in extensions_autorisees:



            return JSONResponse({"ok": False, "erreur": "Document introuvable ou extension non autorisée."}, status_code=404)



        types_mime = {



            ".pdf": "application/pdf",



            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",



            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",



            ".csv": "text/csv",



            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",



            ".txt": "text/plain; charset=utf-8",



            ".png": "image/png",



            ".jpg": "image/jpeg",



            ".jpeg": "image/jpeg",



            ".webp": "image/webp",



            ".svg": "image/svg+xml",



            ".html": "text/html; charset=utf-8",



            ".mermaid": "text/plain; charset=utf-8",



            ".zip": "application/zip",



            ".md": "text/markdown; charset=utf-8",



            ".json": "application/json; charset=utf-8",



            ".sql": "text/plain; charset=utf-8",



            ".tsx": "text/plain; charset=utf-8",



            ".ts": "text/plain; charset=utf-8",



        }



        mime = types_mime.get(cible.suffix.lower(), "application/octet-stream")



        disposition = "inline" if cible.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".pdf", ".svg", ".html") else f'attachment; filename="{cible.name}"'



        return FileResponse(



            cible,



            media_type=mime,



            filename=cible.name,



            headers={"Content-Disposition": disposition},



        )



    @app.post("/api/claude/pdf/exporter_texte")



    async def exporter_texte_en_pdf(request: Request):



        """Exporte n'importe quel texte ou message d'agent en fichier PDF téléchargeable."""



        try:



            body = await request.json()



            titre = str(body.get("titre", "Réponse Claude RIOT")).strip() or "Réponse Claude RIOT"



            contenu = str(body.get("texte", "")).strip()



            theme = str(body.get("theme", "moderne")).strip()



            if not contenu:



                return JSONResponse({"ok": False, "erreur": "Le contenu à exporter en PDF est vide."}, status_code=400)



            from tools import pdf as outil_pdf



            nom_fichier = f"reponse_{int(time.time())}.pdf"



            msg = outil_pdf.generer_pdf(



                titre=titre,



                contenu_markdown=contenu,



                sous_titre="Export instantané de réponse IA",



                nom_fichier=nom_fichier,



                theme=theme,



            )



            return {



                "ok": True,



                "nom_fichier": nom_fichier,



                "url": f"/api/claude/pdf/telecharger?chemin={nom_fichier}",



                "message": msg,



            }



        except Exception as e:



            return JSONResponse({"ok": False, "erreur": str(e)}, status_code=500)



    @app.post("/api/claude/chat")



    async def chat_stream(request: Request):



        """Génère le flux Server-Sent Events (SSE) avec fichiers joints, routage intelligent et synthèse unique."""



        try:



            body = await request.json()



        except Exception:



            body = {}



        message = str(body.get("message", "")).strip()



        mode = str(body.get("mode", "swarm")).lower()



        fichiers = body.get("fichiers", []) or []



        chat_id = str(body.get("chat_id", "")).strip()



        contexte_fichiers = formater_fichiers_joints(fichiers)



        if not message and not contexte_fichiers:



            return JSONResponse({"ok": False, "erreur": "Message ou fichier requis."}, status_code=400)



        if not message and contexte_fichiers:



            message = "Voici les fichiers joints. Analyse leur structure et leur contenu, et fournis une synthèse complète."



        message_complet = f"{contexte_fichiers}\n\nDemande de l'utilisateur :\n{message}" if contexte_fichiers else message



        projet = _SESSION_CTX.get("projet_actif")



        nom_projet_affich = projet.name if projet else "Discussion Libre"



        if not chat_id:



            titre_chat = message[:36] + ("..." if len(message) > 36 else "") if message else "Analyse de fichiers"



            chat_id = memoire.creer_session_chat(titre=titre_chat, mode=mode, projet=projet.name if projet else "")



        async def generateur_evenements() -> AsyncGenerator[str, None]:



            if len(registre.tous()) < 50:



                registre.charger_outils()



            from core.agents import (



                PROMPT_SYSTEME_RAW,



                classifier_intention_swarm,



                detecter_modele_non_censure,



                s_assurer_ollama_actif,



                nettoyer_preambules_creux,



            )



            # 1. Détermination du mode effectif (Priorité aux commandes slash, puis à l'orchestrateur Swarm)



            mode_effectif = mode



            if message.startswith("/raw") or message.startswith("/uncensored"):



                mode_effectif = "raw"



            elif message.startswith("/trade"):



                mode_effectif = "trader"



            elif message.startswith("/architect"):



                mode_effectif = "architect"



            elif message.startswith("/review"):



                mode_effectif = "review"



            elif message.startswith("/coder"):



                mode_effectif = "coder"



            elif message.startswith("/swarm"):



                mode_effectif = "swarm"



            elif mode in ("swarm", "pipeline"):



                # En mode Multi-Agents, le Coordinateur route intelligemment au lieu de lancer 4 agents à la chaîne !



                intention = classifier_intention_swarm(message)



                if intention == "raw":



                    mode_effectif = "raw"



                elif intention == "trader":



                    mode_effectif = "trader"



                elif intention == "review":



                    mode_effectif = "review"



                elif intention == "architect":



                    mode_effectif = "architect"



                elif intention == "direct":



                    mode_effectif = "coder"



                else:



                    mode_effectif = "swarm"



            _SESSION_CTX["tokens_prompt"] += max(1, len(message_complet) // 4)



            t0 = time.time()



            yield f"data: {json.dumps({'type': 'debut', 'mode': mode_effectif, 'projet': nom_projet_affich, 'chat_id': chat_id})}\n\n"



            # -----------------------------------------------------------------



            # MODE 4 : SOUS-AGENT RIOT-RAW (0 Censure Locale via Dolphin Ollama)



            # -----------------------------------------------------------------



            if mode_effectif in ("raw", "uncensored"):



                instruction = message_complet.replace("/raw", "").replace("/uncensored", "").strip() or "Présente-toi directement et confirme ton absence totale de filtre."



                from core.llm import OllamaProvider



                await asyncio.to_thread(s_assurer_ollama_actif)



                nom_modele = await asyncio.to_thread(detecter_modele_non_censure)



                provider_raw = OllamaProvider(modele=nom_modele)



                if not provider_raw.disponible():



                    msg_err = f"Le serveur Ollama local n'est pas joignable sur {provider_raw.hote}. Lance ollama serve."



                    yield f"data: {json.dumps({'type': 'erreur', 'message': msg_err})}\n\n"



                    return



                historique = _construire_historique_tour(chat_id, instruction, max_messages=8)



                yield f"data: {json.dumps({'type': 'thinking', 'modele': nom_modele, 'message': f'Réflexion locale dé-censurée ({nom_modele})...'})}\n\n"



                try:



                    # Assistant Prefill : court-circuite tout refus ou préambule moralisateur résiduel



                    prefill = "Voici directement l'analyse technique et les éléments concrets sans détour :"



                    rep = await asyncio.to_thread(provider_raw.repondre, PROMPT_SYSTEME_RAW, historique, [], None, prefill)



                    texte_brut = " ".join(b.text for b in rep.content if getattr(b, "type", None) == "text").strip()



                    texte_brut = nettoyer_preambules_creux(texte_brut)



                    # Export PDF automatique si demandé explicitement au modèle local



                    if any(k in instruction.lower() for k in ("pdf", "document pdf", "fichier pdf", "exporte en pdf", "export pdf")):



                        try:



                            from tools import pdf as outil_pdf



                            nom_f = f"rapport_raw_{int(time.time())}.pdf"



                            res_pdf = outil_pdf.generer_pdf(



                                titre="Rapport RIOT-Raw",



                                contenu_markdown=texte_brut,



                                sous_titre=f"Document généré localement par {nom_modele}",



                                nom_fichier=nom_f



                            )



                            texte_brut += f"\n\n---\n{res_pdf}"



                        except Exception as e_pdf:



                            LOG.exception("Erreur conversion PDF raw : %s", e_pdf)



                    _SESSION_CTX["tokens_reponse"] += max(1, len(texte_brut) // 4)



                    _memoriser_tour(chat_id, instruction, texte_brut)



                    texte_final = f"### 🔥 RIOT-Raw ({nom_modele})\n\n" + texte_brut



                    for mot in texte_final.split(" "):



                        yield f"data: {json.dumps({'type': 'chunk', 'texte': mot + ' '})}\n\n"



                        await asyncio.sleep(0.008)



                except Exception as e:



                    yield f"data: {json.dumps({'type': 'erreur', 'message': str(e)})}\n\n"



                yield f"data: {json.dumps({'type': 'fin', 'duree': round(time.time() - t0, 1), 'chat_id': chat_id})}\n\n"



                return



            # Pour les modes cloud / standard, vérifier le provider principal



            provider = llm()



            if not provider.disponible():



                yield f"data: {json.dumps({'type': 'erreur', 'message': 'Modèle LLM indisponible'})}\n\n"



                return



            # -----------------------------------------------------------------



            # MODE 1 : PIPELINE SWARM D'INGÉNIERIE (Travail en coulisses + 1 seule synthèse)



            # -----------------------------------------------------------------



            if mode_effectif in ("swarm", "pipeline"):



                instruction = message_complet.replace("/swarm", "").strip() if message.startswith("/swarm") else message_complet



                



                outils_pilotage_swarm = {



                    "lancer_navigateur_chrome", "browser_open", "browser_current_page",



                    "browser_tabs", "browser_close_tabs", "browser_interact",



                    "browser_click", "browser_type", "browser_scroll",
                    "vibetg_activer_algo_pubs", "vibetg_statut_algo_pubs", "vibetg_arreter_algo_pubs",



                    "ouvrir_application", "controler_media", "regler_volume",



                    "verrouiller_pc", "eteindre_pc", "capture_screen"



                }



                etapes = [



                    ("architect", "📐 RIOT-Architect", "Analyse & Planification", {"explorer_projet", "lire_code", "chercher_dans_code", "lister_dossier", "generer_pdf", "generer_excel", "generer_powerpoint", "generer_graphique", "generer_diagramme", "creer_produit_digital", "auditer_schema_sql", "optimiser_requete_postgis", "generer_politiques_rls", "generer_composant_mobile", "scaffolder_app_mobile_expo", "surveiller_marche_crypto", "recueillir_veille_web", "generer_bulletin_veille", "lister_competences", "charger_competence", "lire_reference", "capturer_page", "capturer_frames"} | outils_pilotage_swarm),



                    ("engineer", "💻 RIOT-Engineer", "Implémentation chirurgicale", {"lire_code", "patcher_code", "ecrire_code", "chercher_dans_code", "generer_pdf", "generer_excel", "generer_powerpoint", "generer_graphique", "generer_diagramme", "creer_produit_digital", "auditer_schema_sql", "optimiser_requete_postgis", "generer_politiques_rls", "generer_composant_mobile", "scaffolder_app_mobile_expo", "surveiller_marche_crypto", "recueillir_veille_web", "generer_bulletin_veille", "lister_competences", "charger_competence", "lire_reference", "capturer_page", "capturer_frames"} | outils_pilotage_swarm),



                    ("tester", "🧪 RIOT-Tester", "Tests unitaires & Auto-guérison", {"executer_test_ou_commande", "lire_code", "patcher_code", "generer_pdf", "generer_excel", "generer_powerpoint", "generer_graphique", "generer_diagramme", "creer_produit_digital", "auditer_schema_sql", "optimiser_requete_postgis", "generer_politiques_rls", "generer_composant_mobile", "scaffolder_app_mobile_expo", "surveiller_marche_crypto", "recueillir_veille_web", "generer_bulletin_veille", "capturer_page", "capturer_frames"} | outils_pilotage_swarm),



                    ("reviewer", "🛡️ RIOT-Reviewer", "Audit sécurité & Synthèse finale", {"lire_code", "chercher_dans_code", "executer_test_ou_commande", "generer_pdf", "generer_excel", "generer_powerpoint", "generer_graphique", "generer_diagramme", "creer_produit_digital", "auditer_schema_sql", "optimiser_requete_postgis", "generer_politiques_rls", "generer_composant_mobile", "scaffolder_app_mobile_expo", "surveiller_marche_crypto", "recueillir_veille_web", "generer_bulletin_veille", "lister_competences", "charger_competence", "lire_reference", "capturer_page", "capturer_frames"} | outils_pilotage_swarm),



                ]



                contexte_precedent = ""



                derniere_synthese = ""



                for code_etape, nom_agent, label, outils in etapes:



                    yield f"data: {json.dumps({'type': 'swarm_etape_start', 'etape': code_etape, 'agent': nom_agent, 'label': label})}\n\n"



                    



                    if code_etape == "reviewer":



                        if projet:



                            system_prompt = (



                                f"Tu es le Coordinateur Final et {nom_agent} sur le projet {projet.name} ({projet}).\n"



                                f"Mission initiale de l'utilisateur : {instruction}\n"



                                "Fournis UNE SEULE réponse finale claire, directe et synthétique pour l'utilisateur "



                                "résumant le travail réalisé par l'équipe et ton verdict de validation."



                            )



                        else:



                            system_prompt = (



                                f"Tu es le Coordinateur Final et {nom_agent}.\n"



                                "Mode actuel : DISCUSSION LIBRE.\n"



                                f"Mission initiale de l'utilisateur : {instruction}\n"



                                "Fournis UNE SEULE réponse finale claire, directe et synthétique pour l'utilisateur."



                            )



                    else:



                        if projet:



                            system_prompt = f"Tu es {nom_agent}.\nProjet actif : {projet.name} ({projet}).\nMission : {instruction}\nSois concis, technique et direct."



                        else:



                            system_prompt = f"Tu es {nom_agent}.\nMode actuel : Discussion et Résolution Libre.\nMission : {instruction}\nSois concis, technique et direct."



                    if contexte_precedent:



                        system_prompt += f"\nTravail accompli par les agents précédents en coulisses :\n{contexte_precedent[:2000]}"



                    schemas = [s for s in registre.schemas_api() if (s.get("name") in outils or str(s.get("name", "")).startswith("mcp_"))]



                    historique = [{"role": "user", "content": f"Accomplis ton étape pour cette tâche : {instruction}"}]



                    reponse_etape = ""



                    for tour in range(3):



                        try:



                            rep = await asyncio.to_thread(provider.repondre, system_prompt, historique, schemas)



                        except Exception as e:



                            yield f"data: {json.dumps({'type': 'erreur', 'message': f'Erreur {nom_agent}: {e}'})}\n\n"



                            break



                        textes = [b.text for b in rep.content if getattr(b, "type", None) == "text" and b.text]



                        if textes:



                            reponse_etape = " ".join(textes).strip()



                        if getattr(rep, "stop_reason", None) != "tool_use":



                            break



                        historique.append({"role": "assistant", "content": rep.content})



                        results = []



                        for b in rep.content:



                            if getattr(b, "type", None) != "tool_use":



                                continue



                            nom_o = b.name



                            args = b.input or {}



                            outil = registre.get(nom_o)



                            yield f"data: {json.dumps({'type': 'tool_start', 'agent': nom_agent, 'outil': nom_o, 'args': args})}\n\n"



                            t_o = time.time()



                            try:



                                res = await asyncio.to_thread(outil.fonction, **args) if outil else f"Outil {nom_o} inconnu"



                            except Exception as e:



                                res = f"Erreur : {e}"



                            dt_o = round(time.time() - t_o, 2)



                            if nom_o in ("lire_code", "ecrire_code", "patcher_code"):



                                chemin_f = args.get("chemin") or args.get("cible")



                                if chemin_f:



                                    yield f"data: {json.dumps({'type': 'artifact_update', 'fichier': str(chemin_f)})}\n\n"



                            yield f"data: {json.dumps({'type': 'tool_end', 'agent': nom_agent, 'outil': nom_o, 'duree': dt_o, 'resume': str(res).splitlines()[0][:100] if str(res) else 'OK'})}\n\n"



                            results.append({"type": "tool_result", "tool_use_id": getattr(b, "id", f"call_{nom_o}"), "content": str(res)})



                        if results:



                            historique.append({"role": "user", "content": results})



                    _SESSION_CTX["tokens_reponse"] += max(1, len(reponse_etape) // 4)



                    contexte_precedent += f"\n[{nom_agent}]: {reponse_etape}\n"



                    derniere_synthese = reponse_etape or derniere_synthese



                    # Les étapes intermédiaires sont envoyées en coulisses (carte repliable), pas dans le texte principal !



                    yield f"data: {json.dumps({'type': 'swarm_etape_end', 'etape': code_etape, 'agent': nom_agent, 'texte': reponse_etape})}\n\n"



                # Diffusion d'UNE SEULE réponse finale unifiée à l'utilisateur



                if derniere_synthese:



                    _memoriser_tour(chat_id, instruction, derniere_synthese)



                    for mot in derniere_synthese.split(" "):



                        yield f"data: {json.dumps({'type': 'chunk', 'texte': mot + ' '})}\n\n"



                        await asyncio.sleep(0.008)



                yield f"data: {json.dumps({'type': 'fin', 'duree': round(time.time() - t0, 1), 'chat_id': chat_id})}\n\n"



                return



            # -----------------------------------------------------------------



            # MODE 2 : SOUS-AGENT RIOT-TRADER (Quant & Risk Management 1%)



            # -----------------------------------------------------------------



            if mode_effectif in ("trader", "trade"):



                instruction = message_complet.replace("/trade", "").replace("/trader", "").strip() or "Analyse le marché Bitcoin (BTCUSDT) et calcule un plan de risk management 1%."



                prompt_trader = (



                    "Tu es RIOT-Trader, trader quantitatif senior et gestionnaire de risques d'élite.\n"



                    "DOCTRINE ABSOLUE DU TRADING :\n"



                    "1. Préservation du capital avant tout : Tu n'encourages JAMAIS au gambling ni au surlevier.\n"



                    "2. Règle d'or des 1% : Le risque sur un trade ne doit JAMAIS excéder 1.0% du capital total.\n"



                    "3. Analyse basée sur les données : Utilise systématiquement `trading_analyse_technique`, "



                    "`trading_carnet_ordres_express`, `trade_app_prix_crypto` ou `trading_calculateur_risque`.\n"



                    "4. Tout plan de trade doit obligatoirement expliciter : Direction, Entrée, Stop-Loss strict, TP et Sizing exact.\n"



                    "Sois direct, chiffré, synthétique et professionnel."



                )



                outils_trader = {



                    "trading_analyse_technique",



                    "trading_calculateur_risque",



                    "trading_carnet_ordres_express",



                    "trade_app_prix_crypto",



                    "trade_app_statut",



                    "trade_app_demarrer_service",



                    "generer_pdf",



                    "generer_excel",



                    "generer_powerpoint",



                    "generer_graphique",



                    "generer_diagramme"



                }



                schemas = [s for s in registre.schemas_api() if s.get("name") in outils_trader]



                historique = _construire_historique_tour(chat_id, instruction)



                yield f"data: {json.dumps({'type': 'thinking', 'modele': getattr(provider, 'modele', 'trader'), 'message': 'Analyse quantitative & calcul de risque (1%)...'})}\n\n"



                for tour in range(4):



                    try:



                        rep = await asyncio.to_thread(provider.repondre, prompt_trader, historique, schemas)



                    except Exception as e:



                        yield f"data: {json.dumps({'type': 'erreur', 'message': str(e)})}\n\n"



                        break



                    if getattr(rep, "stop_reason", None) != "tool_use":



                        texte_final = " ".join(b.text for b in rep.content if getattr(b, "type", None) == "text").strip()



                        _SESSION_CTX["tokens_reponse"] += max(1, len(texte_final) // 4)



                        _memoriser_tour(chat_id, instruction, texte_final)



                        for mot in texte_final.split(" "):



                            yield f"data: {json.dumps({'type': 'chunk', 'texte': mot + ' '})}\n\n"



                            await asyncio.sleep(0.008)



                        break



                    historique.append({"role": "assistant", "content": rep.content})



                    results = []



                    for b in rep.content:



                        if getattr(b, "type", None) != "tool_use":



                            continue



                        nom_o = b.name



                        args = b.input or {}



                        outil = registre.get(nom_o)



                        yield f"data: {json.dumps({'type': 'tool_start', 'outil': nom_o, 'args': args})}\n\n"



                        t_o = time.time()



                        try:



                            res = await asyncio.to_thread(outil.fonction, **args) if outil else f"Outil {nom_o} inconnu"



                        except Exception as e:



                            res = f"Erreur : {e}"



                        dt_o = round(time.time() - t_o, 2)



                        yield f"data: {json.dumps({'type': 'tool_end', 'outil': nom_o, 'duree': dt_o, 'resume': str(res).splitlines()[0][:100] if str(res) else 'OK'})}\n\n"



                        results.append({"type": "tool_result", "tool_use_id": getattr(b, "id", f"call_{nom_o}"), "content": str(res)})



                    if results:



                        historique.append({"role": "user", "content": results})



                yield f"data: {json.dumps({'type': 'fin', 'duree': round(time.time() - t0, 1), 'chat_id': chat_id})}\n\n"



                return



            # -----------------------------------------------------------------



            # MODE 3 / COORDINATEUR DIRECT / ARCHITECT / REVIEW



            # -----------------------------------------------------------------



            from core.cli import _charger_conventions_projet



            conventions = _charger_conventions_projet(projet)



            instruction_mono = message_complet



            for pref in ("/architect", "/review", "/coder"):



                if message.startswith(pref):



                    instruction_mono = message_complet.replace(pref, "", 1).strip()



            if mode_effectif == "architect":



                if projet:



                    systeme = (



                        "Tu es RIOT-Architect, l'architecte logiciel en chef.\n"



                        f"Projet actif : {projet.name} (Chemin : {projet}).\n"



                        "Explore les fichiers existants et conçois un PLAN D'ACTION CHIRURGICAL structuré "



                        "(fichiers cibles, signatures de fonctions, impacts et risques).\n"



                        f"{conventions}"



                    )



                else:



                    systeme = (



                        "Tu es RIOT-Architect, l'architecte logiciel en chef.\n"



                        "Mode actuel : CONCEPTION ET ARCHITECTURE LIBRE.\n"



                        "Analyse le problème soumis et conçois un plan d'action chirurgical structuré."



                    )



                outils_code_cibles = {



                    "explorer_projet", "lire_code", "chercher_dans_code", "lister_dossier",



                    "generer_pdf", "generer_excel", "generer_powerpoint", "generer_graphique",



                    "generer_diagramme", "creer_produit_digital", "auditer_schema_sql",



                    "optimiser_requete_postgis", "generer_politiques_rls", "generer_composant_mobile",



                    "scaffolder_app_mobile_expo", "surveiller_marche_crypto", "chercher_web", "lire_page_web", "recueillir_veille_web", "content-strategy", "grill-me", "anti-ai-slop", "seo-audit",



                    "generer_bulletin_veille", "lister_competences", "charger_competence",



                    "lire_reference", "capturer_page", "capturer_frames",



                    "lancer_navigateur_chrome", "browser_open", "browser_current_page",



                    "browser_tabs", "browser_close_tabs", "browser_interact",



                    "browser_click", "browser_type", "browser_scroll",
                    "vibetg_activer_algo_pubs", "vibetg_statut_algo_pubs", "vibetg_arreter_algo_pubs",



                    "ouvrir_application", "controler_media", "regler_volume",



                    "verrouiller_pc", "eteindre_pc", "capture_screen"



                }



                msg_thinking = "📐 RIOT-Architect conçoit le plan d'architecture..."



            elif mode_effectif == "review":



                if projet:



                    systeme = (



                        "Tu es RIOT-Reviewer, auditeur senior de code et expert en cybersécurité.\n"



                        f"Projet actif : {projet.name} (Chemin : {projet}).\n"



                        "Audite la sécurité (zéro secret en clair, injections, permissions, isolation Supabase RLS), la robustesse et le typage, "



                        "puis rends un verdict clair [APPROUVÉ] ou [CORRECTIONS REQUISES].\n"



                        "Si demandé, audite le schéma SQL (`auditer_schema_sql`), optimise PostGIS (`optimiser_requete_postgis`), ou génère les politiques RLS (`generer_politiques_rls`).\n"



                        f"{conventions}"



                    )



                else:



                    systeme = (



                        "Tu es RIOT-Reviewer, auditeur senior de code et expert en cybersécurité.\n"



                        "Mode actuel : AUDIT ET REVUE LIBRE.\n"



                        "Audite la situation, la sécurité et la robustesse, puis rends un verdict argumenté.\n"



                        "Si demandé, audite le schéma SQL (`auditer_schema_sql`), optimise PostGIS (`optimiser_requete_postgis`), ou génère les politiques RLS (`generer_politiques_rls`)."



                    )



                outils_code_cibles = {



                    "lire_code", "chercher_dans_code", "executer_test_ou_commande", "explorer_projet",



                    "generer_pdf", "generer_excel", "generer_powerpoint", "generer_graphique",



                    "generer_diagramme", "creer_produit_digital", "auditer_schema_sql",



                    "optimiser_requete_postgis", "generer_politiques_rls", "generer_composant_mobile",



                    "scaffolder_app_mobile_expo", "surveiller_marche_crypto", "chercher_web", "lire_page_web", "recueillir_veille_web", "content-strategy", "grill-me", "anti-ai-slop", "seo-audit",



                    "generer_bulletin_veille", "lister_competences", "charger_competence",



                    "lire_reference", "capturer_page", "capturer_frames",



                    "lancer_navigateur_chrome", "browser_open", "browser_current_page",



                    "browser_tabs", "browser_close_tabs", "browser_interact",



                    "browser_click", "browser_type", "browser_scroll",
                    "vibetg_activer_algo_pubs", "vibetg_statut_algo_pubs", "vibetg_arreter_algo_pubs",



                    "ouvrir_application", "controler_media", "regler_volume",



                    "verrouiller_pc", "eteindre_pc", "capture_screen"



                }



                msg_thinking = "🛡️ RIOT-Reviewer audite la sécurité et la conformité..."



            else:



                if projet:



                    systeme = (



                        "Tu es Claude RIOT, un ingénieur logiciel d'élite et Coordinateur en chef.\n"



                        f"Projet actif : {projet.name} (Chemin : {projet}).\n"



                        "RÈGLES STRICTES :\n"



                        "1. Réponds TOUJOURS directement et précisément à la demande de l'utilisateur en UNE SEULE réponse claire.\n"



                        "2. Si l'utilisateur pose une question générale ou discute, réponds-lui immédiatement sans appeler d'outil inutile.\n"



                        "3. N'appelle les outils de fichiers (`lire_code`, `patcher_code`, `explorer_projet`) que si la demande porte sur le code du projet.\n"



                        "4. NAVIGATION WEB & PILOTAGE CHROME : Tu as un accès direct, réel et interactif à Google Chrome via tes outils (`browser_open`, `browser_current_page`, `browser_click`, `browser_type`, `browser_scroll`, `browser_tabs`, `lancer_navigateur_chrome`). Si l'utilisateur te demande d'aller sur une page, d'ouvrir une URL (http:// ou https://) ou de naviguer sur Internet, N'AFFIRME JAMAIS que tu ne peux pas accéder au web : appelle IMMÉDIATEMENT `browser_open` !\n"



                        "5. CONTRÔLE SYSTÈME WINDOWS, REMOTION & FFMPEG : Tu pilotes directement le PC via `executer_terminal` (PowerShell/CMD, `npx remotion studio`, `npx remotion render`, `ffmpeg`, `ffprobe`, scripts Node/Python), `lister_dossier`, `chercher_fichiers`, `ouvrir_application`, `controler_media`, `regler_volume`, `verrouiller_pc`, `capture_screen`. N'affirme JAMAIS ne pas pouvoir piloter le PC : exécute directement.\n"



                        f"{conventions}"



                    )



                else:



                    systeme = (



                        "Tu es Claude RIOT, un assistant IA d'élite, ingénieur de pointe et partenaire de réflexion.\n"



                        "Mode : DISCUSSION LIBRE (aucun projet ou dossier spécifique imposé).\n"



                        "RÈGLES STRICTES :\n"



                        "1. Réponds librement, précisément et directement à toutes les questions, réflexions ou analyses de l'utilisateur.\n"



                        "2. Ne force aucune référence à un projet particulier sauf si l'utilisateur en mentionne un explicitement.\n"



                        "3. Réponds en une seule intervention claire, naturelle, structurée et sans détour.\n"



                        "4. NAVIGATION WEB & PILOTAGE CHROME : Tu as un accès direct, réel et interactif à Google Chrome via tes outils (`browser_open`, `browser_current_page`, `browser_click`, `browser_type`, `browser_scroll`, `browser_tabs`, `lancer_navigateur_chrome`). Si l'utilisateur te demande d'aller sur une page, d'ouvrir une URL (http:// ou https://) ou de naviguer sur Internet, N'AFFIRME JAMAIS que tu ne peux pas accéder au web ou effectuer des actions en ligne : appelle IMMÉDIATEMENT `browser_open` !\n"



                        "5. CONTRÔLE SYSTÈME WINDOWS, CODE, REMOTION & FFMPEG : Tu pilotes directement le PC et ses outils CLI via `executer_terminal` (PowerShell, `npx remotion studio`, `npx remotion render`, `ffmpeg`, `ffprobe`, Node, Python), `lister_dossier`, `chercher_fichiers`, `lire_code`, `ecrire_code`, `patcher_code`, `ouvrir_application`, `controler_media`, `regler_volume`, `verrouiller_pc`, `capture_screen`. N'affirme JAMAIS 'Je ne peux pas directement piloter ton PC' : utilise tes outils directement."



                    )



                outils_code_cibles = {



                    "explorer_projet", "lire_code", "ecrire_code", "patcher_code",



                    "chercher_dans_code", "executer_test_ou_commande", "executer_terminal",



                    "ouvrir_terminal_interactif", "lister_dossier", "chercher_fichiers",



                    "supprimer_fichier", "ouvrir_fichier", "inspecter_port",



                    "lister_processus", "tuer_processus", "get_system_stats", "trade_app_statut",



                    "trade_app_prix_crypto", "trading_analyse_technique", "trading_calculateur_risque",



                    "trading_carnet_ordres_express", "analyser_espace_stockage", "nettoyer_caches_temporaires",



                    "generer_pdf", "extraire_texte_pdf", "fusionner_pdfs",



                    "generer_excel", "lire_excel", "generer_powerpoint", "lire_powerpoint",



                    "generer_graphique", "generer_diagramme", "creer_produit_digital",



                    "auditer_schema_sql", "optimiser_requete_postgis", "generer_politiques_rls",



                    "generer_composant_mobile", "scaffolder_app_mobile_expo",



                    "surveiller_marche_crypto", "chercher_web", "lire_page_web", "recueillir_veille_web", "generer_bulletin_veille", "grill-me", "content-strategy", "anti-ai-slop", "seo-audit",



                    "lister_competences", "charger_competence", "lire_reference",



                    "capturer_page", "capturer_frames",



                    "lancer_navigateur_chrome", "browser_open", "browser_current_page",



                    "browser_tabs", "browser_close_tabs", "browser_interact",



                    "browser_click", "browser_type", "browser_scroll",
                    "vibetg_activer_algo_pubs", "vibetg_statut_algo_pubs", "vibetg_arreter_algo_pubs",



                    "ouvrir_application", "controler_media", "regler_volume",



                    "verrouiller_pc", "eteindre_pc", "capture_screen"



                }



                msg_thinking = "Réflexion et analyse en cours..."



            import re



            historique = _construire_historique_tour(chat_id, instruction_mono)



            # Détection immédiate des ordres pour l'algorithme des publicités VibeTG
            inst_min = instruction_mono.lower()
            if any(k in inst_min for k in ("activer l'algo", "active l'algo", "active l'algorithme", "lance l'algo", "lance l'algorithme des pubs", "active les pubs", "lance les pubs", "regarde les pubs en boucle", "regarde des pubs en boucle", "active algorithme des pubs", "lancer l'algo des pubs")):
                from tools.vibetg_ads import vibetg_activer_algo_pubs
                nb = 7
                m_nb = re.search(r"(\d+)\s*pubs?", inst_min)
                if m_nb:
                    try:
                        nb = int(m_nb.group(1))
                    except Exception:
                        pass
                res_algo = vibetg_activer_algo_pubs(nombre_pubs=nb)
                yield f"data: {json.dumps({'type': 'tool_start', 'outil': 'vibetg_activer_algo_pubs', 'args': {'nombre_pubs': nb}})}\n\n"
                yield f"data: {json.dumps({'type': 'token', 'token': res_algo})}\n\n"
                yield f"data: {json.dumps({'type': 'tool_end', 'outil': 'vibetg_activer_algo_pubs', 'duree': 0.05, 'resume': res_algo.splitlines()[0]})}\n\n"
                yield f"data: {json.dumps({'type': 'fin', 'texte': res_algo})}\n\n"
                return

            if any(k in inst_min for k in ("arrête l'algo", "arrete l'algo", "arrête l'algorithme", "arrete l'algorithme", "arrête les pubs", "arrete les pubs", "stop les pubs", "coupe les pubs", "stop l'algo", "stoppe les pubs", "arrêter l'algo", "arreter l'algo")):
                from tools.vibetg_ads import vibetg_arreter_algo_pubs
                res_algo = vibetg_arreter_algo_pubs()
                yield f"data: {json.dumps({'type': 'tool_start', 'outil': 'vibetg_arreter_algo_pubs', 'args': {}})}\n\n"
                yield f"data: {json.dumps({'type': 'token', 'token': res_algo})}\n\n"
                yield f"data: {json.dumps({'type': 'tool_end', 'outil': 'vibetg_arreter_algo_pubs', 'duree': 0.05, 'resume': res_algo.splitlines()[0]})}\n\n"
                yield f"data: {json.dumps({'type': 'fin', 'texte': res_algo})}\n\n"
                return

            if any(k in inst_min for k in ("statut de l'algo", "statut des pubs", "combien de pub", "suivi des pubs", "état des pubs", "etat des pubs", "avancement des pubs", "rapport des pubs", "progression des pubs")):
                from tools.vibetg_ads import vibetg_statut_algo_pubs
                res_algo = vibetg_statut_algo_pubs()
                yield f"data: {json.dumps({'type': 'tool_start', 'outil': 'vibetg_statut_algo_pubs', 'args': {}})}\n\n"
                yield f"data: {json.dumps({'type': 'token', 'token': res_algo})}\n\n"
                yield f"data: {json.dumps({'type': 'tool_end', 'outil': 'vibetg_statut_algo_pubs', 'duree': 0.05, 'resume': res_algo.splitlines()[0]})}\n\n"
                yield f"data: {json.dumps({'type': 'fin', 'texte': res_algo})}\n\n"
                return

            match_url = re.search(r"https?://[^\s]+", instruction_mono)
            url_cible = match_url.group(0).rstrip('.,;!?)') if match_url else ''



            # Détecter si la conversation précédente est déjà sur un flux navigateur interactif

            prev_txt = str(historique[-1].get("content", "")) if historique else ""

            contexte_nav_actif = "/captures/" in prev_txt or "éléments interactifs" in prev_txt or "Que souhaitez-vous" in prev_txt

            mots_actions_nav = (

                "va sur", "vas sur", "ouvre le site", "ouvre la page", "navigue vers",

                "consulte l'url", "consulte https", "ouvre https", "regarde une pub",

                "publicité", "publiciter", "dashboard", "dashbord", "clique", "clic",

                "continuer avec", "se connecter", "s'inscrire", "connexion", "inscription"

            )

            demande_nav = bool(url_cible) or contexte_nav_actif or any(k in instruction_mono.lower() for k in mots_actions_nav)



            # Résolution contextuelle pour VibeTG / Kelvix Rewards



            if not url_cible and any(k in instruction_mono.lower() for k in ("vibe tg", "vibetg", "kelvix rewards", "kelvix-rewards")):



                if any(k in instruction_mono.lower() for k in ("dashboard", "dashbord", "pub", "publicit")):



                    url_cible = "https://kelvix-rewards.vercel.app/dashboard"



                else:



                    url_cible = "https://kelvix-rewards.vercel.app/"



            # Si l'utilisateur mentionne une page sans URL explicite, chercher le dernier domaine utilisé dans l'historique



            if not url_cible and demande_nav and historique:



                for msg in reversed(historique):



                    cnt = str(msg.get("content", ""))



                    m_prev = re.search(r"https?://[^\s'\"`]+", cnt)



                    if m_prev:



                        base_u = m_prev.group(0).rstrip(".,;!?)")



                        if "dashboard" in instruction_mono.lower() or "dashbord" in instruction_mono.lower():



                            from urllib.parse import urlparse



                            p_url = urlparse(base_u)



                            url_cible = f"{p_url.scheme}://{p_url.netloc}/dashboard"



                        else:



                            url_cible = base_u



                        break



            if demande_nav:



                directive_nav = (



                    "DIRECTIVE ABSOLUE - NAVIGATION INTERACTIVE GOOGLE CHROME :\n"



                    "L'utilisateur souhaite naviguer et interagir avec Google Chrome.\n"



                    f"Cible exacte identifiée : {url_cible or 'page courante ou recherche'}.\n"

                    f"Attention : pour 'Vibe TG' ou regarder des pubs, l'adresse exacte est '{url_cible or 'https://kelvix-rewards.vercel.app/'}' (ne jamais inventer vibetg.com !).\n"



                    "Tu DOIS appeler les outils réels (`browser_open` pour ouvrir/basculer sur une page, `browser_current_page` pour inspecter, `browser_click` pour cliquer sur un bouton/lien, `browser_type` pour remplir un champ).\n"



                    "Chaque action produit automatiquement une capture d'écran ainsi que la liste des éléments interactifs repérés. Tu DOIS inclure la capture d'écran dans ta réponse, décrire ce que tu vois et demander systématiquement : 'Que souhaitez-vous que je fasse ensuite ?'.\n"



                    "INTERDICTION STRICTE d'affirmer que tu ne peux pas accéder au web ou de prétendre faussement avoir ouvert une page sans appeler l'outil !\n\n"



                )



                systeme = directive_nav + systeme



            try:

                from tools.code import extraire_et_ancrer_dossier_texte, _projet_actif_courant

                extraire_et_ancrer_dossier_texte(instruction_mono)

                proj_anc = _projet_actif_courant()

                if proj_anc:

                    systeme += f"\n\n[DOSSIER PROJET ACTIF ANCRÉ : {proj_anc}] (utilise ce chemin par défaut pour lire/patcher/lancer des commandes)."

            except Exception:

                pass



            req_routage = instruction_mono + (" navigateur web" if demande_nav else "") + (" code projet" if mode_effectif == "coder" else "")

            schemas = [s for s in registre.schemas_api(requete=req_routage) if (s.get("name") in outils_code_cibles or str(s.get("name", "")).startswith("mcp_"))]



            yield f"data: {json.dumps({'type': 'thinking', 'modele': getattr(provider, 'modele', mode_effectif), 'message': msg_thinking})}\n\n"



            from core.model_router import JournalContinuite

            dernier_capture_md = ""

            compteur_appels_studio = {}

            reponse_envoyee = False

            journal_studio = JournalContinuite(instruction_mono, dossier=str(_projet_actif_courant() or ""))



            for tour in range(10):



                try:

                    bloc_cont_s = journal_studio.rendre_bloc()

                    systeme_tour = f"{systeme}{bloc_cont_s}" if bloc_cont_s else systeme

                    rep = await asyncio.to_thread(provider.repondre, systeme_tour, historique, schemas)



                except Exception as e:



                    yield f"data: {json.dumps({'type': 'erreur', 'message': str(e)})}\n\n"



                    break



                if getattr(rep, "stop_reason", None) != "tool_use":



                    texte_final = " ".join(b.text for b in rep.content if getattr(b, "type", None) == "text").strip()



                    # Détection d'un bloc de code généré ou refus résiduel ou omission d'appel d'outil sur une demande de navigation



                    match_url_code = re.search(r"https?://[^\s'\"`]+", texte_final)



                    cible_effective = (match_url_code.group(0) if match_url_code else "") or url_cible



                    a_omission = demande_nav and cible_effective and ("http" in cible_effective or "www." in cible_effective)



                    phrases_refus = ('ne peux pas accéder à des pages web', 'ne peux pas accéder à internet', 'impossible d\'accéder à des pages externes', 'i cannot browse', 'i don\'t have access to the web')



                    est_refus = any(p in texte_final.lower() for p in phrases_refus)



                    if a_omission or est_refus:

                        outil_bo = registre.get('browser_open')

                        if outil_bo and cible_effective:

                            yield f"data: {json.dumps({'type': 'tool_start', 'outil': 'browser_open', 'args': {'url': cible_effective}})}\n\n"

                            t_bo = time.time()

                            try:

                                res_bo = await asyncio.to_thread(outil_bo.fonction, url=cible_effective)

                            except Exception as e_bo:

                                res_bo = f"Erreur : {e_bo}"

                            dt_bo = round(time.time() - t_bo, 2)

                            yield f"data: {json.dumps({'type': 'tool_end', 'outil': 'browser_open', 'duree': dt_bo, 'resume': str(res_bo)})}\n\n"

                            texte_final = f"{res_bo}"

                            m_cap_bo = re.search(r"!\[.*?\]\(/captures/[^\s\)]+\)", str(res_bo))

                            if m_cap_bo:

                                dernier_capture_md = m_cap_bo.group(0)



                    # Fallback clic interactif si le modèle a produit du texte sans exécuter l'action de clic

                    mots_clic_detect = ("continuer avec", "se connecter", "s'inscrire", "clique", "clic")

                    if any(k in instruction_mono.lower() for k in mots_clic_detect) and not getattr(rep, "stop_reason", None) == "tool_use":

                        outil_bc = registre.get('browser_click')

                        if outil_bc:

                            cible_clic = instruction_mono

                            for pref in ("clique sur", "clic sur", "cliquer sur", "clique", "clic"):

                                if cible_clic.lower().startswith(pref):

                                    cible_clic = cible_clic[len(pref):].strip(" :\"\'")

                            yield f"data: {json.dumps({'type': 'tool_start', 'outil': 'browser_click', 'args': {'texte_ou_selecteur': cible_clic}})}\n\n"

                            t_bc = time.time()

                            try:

                                res_bc = await asyncio.to_thread(outil_bc.fonction, texte_ou_selecteur=cible_clic)

                            except Exception as e_bc:

                                res_bc = f"Erreur : {e_bc}"

                            dt_bc = round(time.time() - t_bc, 2)

                            yield f"data: {json.dumps({'type': 'tool_end', 'outil': 'browser_click', 'duree': dt_bc, 'resume': str(res_bc).splitlines()[0][:100]})}\n\n"

                            texte_final = f"{res_bc}"

                            m_cap_bc = re.search(r"!\[.*?\]\(/captures/[^\s\)]+\)", str(res_bc))

                            if m_cap_bc:

                                dernier_capture_md = m_cap_bc.group(0)



                    # Élimination des captures fictives/hallucinées et substitution par la vraie capture

                    liens_fictifs = re.findall(r"!\[(.*?)\]\((/captures/[^\s\)]+)\)", texte_final)

                    for alt_txt, url_cap in liens_fictifs:

                        nom_fichier_cap = Path(url_cap).name

                        chemin_disque = _RACINE / "_captures" / nom_fichier_cap

                        if not chemin_disque.exists():

                            if dernier_capture_md:

                                texte_final = texte_final.replace(f"![{alt_txt}]({url_cap})", dernier_capture_md)

                            else:

                                texte_final = texte_final.replace(f"![{alt_txt}]({url_cap})", "")



                    if dernier_capture_md and dernier_capture_md not in texte_final:

                        texte_final = texte_final.strip() + "\n\n" + dernier_capture_md



                    if demande_nav:



                        if "que souhaitez-vous" not in texte_final.lower() and "faire ensuite" not in texte_final.lower():



                            texte_final = texte_final.strip() + "\n\n**Que souhaitez-vous que je fasse ensuite ?**"



                    _SESSION_CTX["tokens_reponse"] += max(1, len(texte_final) // 4)



                    resume_s = journal_studio.resume_court()

                    texte_hist_s = f"{texte_final}\n{resume_s}" if resume_s else texte_final

                    _memoriser_tour(chat_id, instruction_mono, texte_hist_s)



                    # Streaming par petits morceaux pour fluidité



                    for mot in texte_final.split(" "):



                        yield f"data: {json.dumps({'type': 'chunk', 'texte': mot + ' '})}\n\n"



                        await asyncio.sleep(0.01)



                    reponse_envoyee = True

                    break



                historique.append({"role": "assistant", "content": rep.content})



                results = []



                for b in rep.content:



                    if getattr(b, "type", None) != "tool_use":



                        continue



                    nom_o = b.name



                    args = b.input or {}



                    outil = registre.get(nom_o)

                    try:

                        empreinte_s = f"{nom_o}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"

                    except Exception:

                        empreinte_s = f"{nom_o}:{args}"

                    compteur_appels_studio[empreinte_s] = compteur_appels_studio.get(empreinte_s, 0) + 1



                    yield f"data: {json.dumps({'type': 'tool_start', 'outil': nom_o, 'args': args})}\n\n"



                    t_o = time.time()



                    if compteur_appels_studio[empreinte_s] > 2:

                        res = (

                            f"[BOUCLE STOPPÉE] `{nom_o}` déjà exécuté {compteur_appels_studio[empreinte_s] - 1} fois "

                            "avec exactement les mêmes paramètres. Change d'outil (ex. `executer_terminal`) ou réponds directement."

                        )

                    else:

                        try:



                            res = await asyncio.to_thread(outil.fonction, **args) if outil else f"Outil {nom_o} inconnu"



                        except Exception as e:



                            res = f"Erreur : {e}"



                    dt_o = round(time.time() - t_o, 2)

                    journal_studio.enregistrer_appel(nom_o, args, str(res))



                    if nom_o in ("lire_code", "ecrire_code", "patcher_code"):



                        chemin_f = args.get("chemin") or args.get("cible")



                        if chemin_f:



                            yield f"data: {json.dumps({'type': 'artifact_update', 'fichier': str(chemin_f)})}\n\n"



                    if nom_o in ("browser_open", "browser_click", "browser_type", "browser_current_page"):



                        m_cap_loop = re.search(r"!\[.*?\]\(/captures/[^\s\)]+\)", str(res))



                        if m_cap_loop:



                            dernier_capture_md = m_cap_loop.group(0)



                    yield f"data: {json.dumps({'type': 'tool_end', 'outil': nom_o, 'duree': dt_o, 'resume': str(res).splitlines()[0][:100] if str(res) else 'OK'})}\n\n"



                    results.append({"type": "tool_result", "tool_use_id": getattr(b, "id", f"call_{nom_o}"), "content": str(res)})



                if results:



                    historique.append({"role": "user", "content": results})



            if not reponse_envoyee:

                try:

                    bloc_cont_s = journal_studio.rendre_bloc()

                    rep_fin = await asyncio.to_thread(provider.repondre, f"{systeme}{bloc_cont_s}", historique, [])

                    texte_fin = " ".join(b.text for b in getattr(rep_fin, "content", []) if getattr(b, "type", None) == "text").strip()

                    if texte_fin:

                        resume_s = journal_studio.resume_court()

                        _memoriser_tour(chat_id, instruction_mono, f"{texte_fin}\n{resume_s}" if resume_s else texte_fin)

                        for mot in texte_fin.split(" "):

                            yield f"data: {json.dumps({'type': 'chunk', 'texte': mot + ' '})}\n\n"

                            await asyncio.sleep(0.01)

                except Exception:

                    pass



            yield f"data: {json.dumps({'type': 'fin', 'duree': round(time.time() - t0, 1), 'chat_id': chat_id})}\n\n"



        return StreamingResponse(generateur_evenements(), media_type="text/event-stream")