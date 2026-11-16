"""Backend de RIOT IDE : Workspace agentique multi-panneaux (style Antigravity).

Toutes les routes /api/ide/* sont protegees par _local_seulement(request) afin
de ne jamais exposer les fichiers locaux ni le terminal sur Internet / tunnel.
"""
import asyncio
import difflib
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from core import config, memoire, registre
from core.cli import _SESSION_CTX, _recup_branche_git
from core.config import dossier_projets, reglage
from core.llm import llm, reinitialiser as reinit_llm
from core.panneau import _local_seulement

LOG = logging.getLogger("riot.ide")

_RACINE = Path(__file__).resolve().parent.parent
_WEB_DIR = _RACINE / "web"

_DOSSIERS_IGNORES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    "_captures",
}

_EXT_BINAIRES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".exe", ".dll", ".pyd", ".so", ".zip", ".tar", ".gz",
    ".woff", ".woff2", ".ttf", ".mp3", ".mp4", ".wav", ".db", ".sqlite",
}


def _projet_courant() -> Path:
    p = _SESSION_CTX.get("projet_actif")
    if isinstance(p, Path) and p.exists() and p.is_dir():
        return p
    d = dossier_projets()
    if d.exists() and d.is_dir():
        return d
    return Path.cwd()


def _resoudre_chemin_sur(projet: Path, chemin_rel: str) -> Optional[Path]:
    """Resout un chemin relatif ou absolu en verifiant strictement qu'il reste dans `projet`."""
    try:
        brut = (chemin_rel or "").strip().lstrip("/\\")
        if not brut:
            return None
        base = projet.resolve()
        cible = (base / brut).resolve()
        cible.relative_to(base)
        return cible
    except Exception:
        return None


def _git_statut(projet: Path) -> Dict[str, str]:
    """Retourne un dict {chemin_relatif_posix: code_git} pour les fichiers modifies/ajoutes."""
    if not (projet / ".git").exists():
        return {}
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(projet),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode != 0:
            return {}
        statuts: Dict[str, str] = {}
        for ligne in r.stdout.splitlines():
            if len(ligne) < 4:
                continue
            code = ligne[:2].strip() or "M"
            rel = ligne[3:].strip().strip('"').replace("\\", "/")
            if " -> " in rel:
                rel = rel.split(" -> ", 1)[1]
            statuts[rel] = code
        return statuts
    except Exception:
        return {}


def _arborescence(projet: Path, max_noeuds: int = 600, max_profondeur: int = 5) -> List[Dict[str, Any]]:
    """Construit l'arborescence triee (dossiers puis fichiers) avec statut git."""
    git_map = _git_statut(projet)
    compteur = 0

    def _parcourir(dossier: Path, profondeur: int, prefixe: str) -> List[Dict[str, Any]]:
        nonlocal compteur
        if profondeur > max_profondeur or compteur >= max_noeuds:
            return []
        try:
            entrees = sorted(
                dossier.iterdir(),
                key=lambda x: (not x.is_dir(), x.name.lower()),
            )
        except Exception:
            return []

        noeuds: List[Dict[str, Any]] = []
        for e in entrees:
            if compteur >= max_noeuds:
                break
            nom = e.name
            if nom in _DOSSIERS_IGNORES or (nom.startswith(".") and nom not in {".env.example", ".gitignore"}):
                if e.is_dir():
                    continue
            rel = f"{prefixe}/{nom}".lstrip("/")
            compteur += 1
            if e.is_dir():
                enfants = _parcourir(e, profondeur + 1, rel)
                noeuds.append({
                    "nom": nom,
                    "chemin": rel,
                    "type": "dir",
                    "enfants": enfants,
                })
            else:
                noeuds.append({
                    "nom": nom,
                    "chemin": rel,
                    "type": "file",
                    "ext": e.suffix.lstrip(".").lower(),
                    "git": git_map.get(rel, ""),
                })
        return noeuds

    return _parcourir(projet, 0, "")


def _lister_projets_disponibles() -> List[Dict[str, str]]:
    racine = dossier_projets()
    res: List[Dict[str, str]] = []
    if _RACINE.exists():
        res.append({"nom": _RACINE.name, "chemin": str(_RACINE)})
    if racine.exists() and racine.is_dir():
        try:
            for d in sorted(racine.iterdir(), key=lambda x: x.name.lower()):
                if d.is_dir() and not d.name.startswith(".") and str(d) != str(_RACINE):
                    res.append({"nom": d.name, "chemin": str(d)})
        except Exception:
            pass
    return res[:60]


def _extraire_outils_ide(lecture_seule: bool = False) -> List[Dict[str, Any]]:
    """Selectionne les vrais outils RIOT pour l'IDE (code, systeme, web, image, memoire)."""
    if len(registre.tous()) < 20:
        registre.charger_outils()

    cibles_lecture = {
        "explorer_projet", "lire_code", "chercher_dans_code", "lister_dossier",
        "chercher_fichiers", "chercher_web", "recall", "get_system_stats",
        "lister_images_generees",
    }
    cibles_ecriture = {
        "ecrire_code", "patcher_code", "supprimer_fichier", "executer_terminal",
        "executer_test_ou_commande", "generer_image", "remember",
        "generer_diagramme", "generer_graphique",
    }
    autorises = cibles_lecture if lecture_seule else (cibles_lecture | cibles_ecriture)

    schemas = []
    for o in registre.tous():
        if o.nom in autorises:
            schemas.append({
                "name": o.nom,
                "description": o.description or o.nom,
                "input_schema": o.parametres or {"type": "object", "properties": {}},
            })
    return schemas[:32]


def _construire_prompt_ide(mode: str, projet: Path, fichier_actif: Optional[Dict[str, str]]) -> str:
    regle_mode = {
        "plan": (
            "MODE PLANIFICATION : Ne modifie aucun fichier pour l'instant. Analyse la codebase avec les outils "
            "de lecture/recherche et produis un plan d'architecture detaille (fichiers impactes, risques, etapes)."
        ),
        "ask": (
            "MODE QUESTION/EXPLORATION : Reponds de maniere claire et factuelle en lisant les fichiers necessaires, "
            "sans modifier de fichiers."
        ),
        "code": (
            "MODE INGENIEUR CODE : Tu peux lire, creer et patcher des fichiers dans le projet actif puis verifier "
            "par des commandes/tests (zero erreur). Mentionne exactement les chemins et symboles modifies."
        ),
        "swarm": (
            "MODE SWARM / AUTONOME : Travaille de maniere methodique par phases (diagnostic -> edition chirurgicale -> "
            "verification outille). Utilise generer_image si l'utilisateur demande une maquette ou illustration."
        ),
    }.get(mode, "Reponds de facon claire et precise.")

    ctx_fichier = ""
    if fichier_actif and fichier_actif.get("chemin"):
        snippet = str(fichier_actif.get("contenu", "") or "")[:6000]
        ctx_fichier = (
            f"\n\n[ONGLET ACTIF DANS L'EDITEUR : {fichier_actif['chemin']}]\n"
            f"```\n{snippet}\n```"
        )

    return (
        "Tu es RIOT IDE Copilot, un ingenieur logiciel senior travaillant directement dans l'espace de travail "
        f"`{projet}` (branche git : `{_recup_branche_git(projet) or '-'}`).\n"
        f"{regle_mode}\n"
        "Reponds toujours en francais, de maniere dense, structuree et verifiable."
        f"{ctx_fichier}"
    )


def monter_routes(app) -> None:
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

    def garde(request: Request):
        if not _local_seulement(request):
            return JSONResponse({"ok": False, "erreur": "RIOT IDE est accessible en local uniquement."}, status_code=403)
        return None

    @app.get("/ide", response_class=HTMLResponse)
    def route_ide_html(request: Request):
        if (r := garde(request)):
            return r
        f = _WEB_DIR / "ide.html"
        if not f.exists():
            return HTMLResponse("<h1>RIOT IDE</h1><p>web/ide.html introuvable.</p>", status_code=404)
        return HTMLResponse(f.read_text(encoding="utf-8"))

    @app.get("/ide.css")
    def route_ide_css(request: Request):
        if (r := garde(request)):
            return r
        f = _WEB_DIR / "ide.css"
        if not f.exists():
            return Response("", media_type="text/css", status_code=404)
        return Response(f.read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/ide.js")
    def route_ide_js(request: Request):
        if (r := garde(request)):
            return r
        f = _WEB_DIR / "ide.js"
        if not f.exists():
            return Response("", media_type="application/javascript", status_code=404)
        return Response(f.read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/api/ide/etat")
    def api_ide_etat(request: Request):
        if (r := garde(request)):
            return r
        from core.routage import mode_actuel
        projet = _projet_courant()
        prov = llm()
        return {
            "ok": True,
            "projet": {"nom": projet.name, "chemin": str(projet), "branche": _recup_branche_git(projet)},
            "projets": _lister_projets_disponibles(),
            "fournisseur": {
                "mode": mode_actuel(),
                "nom": getattr(prov, "nom", "-"),
                "modele": getattr(prov, "modele", "-"),
                "disponible": bool(prov.disponible()) if hasattr(prov, "disponible") else True,
            },
            "modes_llm": ["groq", "mistral", "gemini", "openrouter", "custom", "anthropic", "local"],
            "custom_base_url": reglage("custom.base_url", "http://localhost:3001/v1"),
        }

    @app.post("/api/ide/projet")
    async def api_ide_projet(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json()
        chemin = Path(str((body or {}).get("chemin", "")).strip())
        if not chemin.exists() or not chemin.is_dir():
            return JSONResponse({"ok": False, "erreur": "Dossier projet introuvable."}, status_code=404)
        _SESSION_CTX["projet_actif"] = chemin.resolve()
        return {"ok": True, "nom": chemin.name, "chemin": str(chemin.resolve()), "branche": _recup_branche_git(chemin)}

    @app.get("/api/ide/arborescence")
    def api_ide_arbo(request: Request):
        if (r := garde(request)):
            return r
        projet = _projet_courant()
        return {"ok": True, "projet": str(projet), "noeuds": _arborescence(projet)}

    @app.get("/api/ide/fichier")
    def api_ide_lire(request: Request, chemin: str = ""):
        if (r := garde(request)):
            return r
        projet = _projet_courant()
        cible = _resoudre_chemin_sur(projet, chemin)
        if not cible or not cible.exists() or not cible.is_file():
            return JSONResponse({"ok": False, "erreur": "Fichier introuvable ou hors workspace."}, status_code=404)
        if cible.suffix.lower() in _EXT_BINAIRES:
            return JSONResponse({"ok": False, "erreur": "Apercu texte indisponible pour fichier binaire."}, status_code=400)
        if cible.stat().st_size > 1_500_000:
            return JSONResponse({"ok": False, "erreur": "Fichier trop volumineux (> 1.5 Mo)."}, status_code=400)
        contenu = cible.read_text(encoding="utf-8", errors="replace")
        return {
            "ok": True,
            "chemin": str(cible.relative_to(projet.resolve())).replace("\\", "/"),
            "nom": cible.name,
            "ext": cible.suffix.lstrip(".").lower(),
            "lignes": len(contenu.splitlines()),
            "contenu": contenu,
        }

    @app.post("/api/ide/fichier")
    async def api_ide_ecrire(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json()
        chemin_rel = str((body or {}).get("chemin", "")).strip()
        contenu = str((body or {}).get("contenu", ""))
        creer = bool((body or {}).get("creer", False))
        projet = _projet_courant()
        cible = _resoudre_chemin_sur(projet, chemin_rel)
        if not cible:
            return JSONResponse({"ok": False, "erreur": "Chemin invalide ou hors workspace."}, status_code=403)
        if not cible.exists() and not creer:
            return JSONResponse({"ok": False, "erreur": "Fichier inexistant (activez creer=True)."}, status_code=404)

        ancien = ""
        if cible.exists() and cible.is_file():
            ancien = cible.read_text(encoding="utf-8", errors="replace")
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu, encoding="utf-8")

        diff_lignes = list(difflib.unified_diff(
            ancien.splitlines(),
            contenu.splitlines(),
            fromfile=f"a/{chemin_rel}",
            tofile=f"b/{chemin_rel}",
            lineterm="",
        ))
        return {
            "ok": True,
            "chemin": str(cible.relative_to(projet.resolve())).replace("\\", "/"),
            "lignes": len(contenu.splitlines()),
            "diff": "\n".join(diff_lignes[:250]),
        }

    @app.post("/api/ide/recherche")
    async def api_ide_recherche(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json()
        requete = str((body or {}).get("requete", "")).strip()
        if len(requete) < 2:
            return {"ok": True, "resultats": []}
        projet = _projet_courant()
        needle = requete.lower()
        resultats: List[Dict[str, Any]] = []

        for root, dirs, files in os.walk(projet):
            dirs[:] = [d for d in dirs if d not in _DOSSIERS_IGNORES and not d.startswith(".")]
            for fn in files:
                p = Path(root) / fn
                if p.suffix.lower() in _EXT_BINAIRES:
                    continue
                try:
                    if p.stat().st_size > 400_000:
                        continue
                    rel = str(p.relative_to(projet)).replace("\\", "/")
                    for idx, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                        if needle in line.lower():
                            resultats.append({
                                "chemin": rel,
                                "ligne": idx,
                                "extrait": line.strip()[:140],
                            })
                            if len(resultats) >= 60:
                                return {"ok": True, "resultats": resultats, "tronque": True}
                except Exception:
                    continue
        return {"ok": True, "resultats": resultats, "tronque": False}

    @app.post("/api/ide/terminal")
    async def api_ide_terminal(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json()
        commande = str((body or {}).get("commande", "")).strip()
        if not commande:
            return JSONResponse({"ok": False, "erreur": "Commande vide."}, status_code=400)
        projet = _projet_courant()
        t0 = time.time()
        try:
            proc = subprocess.run(
                commande,
                cwd=str(projet),
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=25,
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-12000:],
                "stderr": proc.stderr[-6000:],
                "duree_ms": int((time.time() - t0) * 1000),
                "cwd": str(projet),
            }
        except subprocess.TimeoutExpired:
            return JSONResponse({"ok": False, "erreur": "Timeout (25s depassees)."}, status_code=408)
        except Exception as e:
            return JSONResponse({"ok": False, "erreur": str(e)}, status_code=500)

    @app.post("/api/ide/modele")
    async def api_ide_modele(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json() or {}
        mode = str(body.get("mode", "")).strip().lower()
        base_url = str(body.get("base_url", "")).strip()
        modele = str(body.get("modele", "")).strip()
        cle = str(body.get("cle", "")).strip()

        if base_url:
            config.definir("custom.base_url", base_url)
        if cle:
            target = mode if mode in ("groq", "mistral", "gemini", "openrouter", "anthropic", "custom") else "custom"
            config.definir(f"{target}.cle", cle)
        if modele and mode in ("groq", "mistral", "gemini", "openrouter", "anthropic", "local", "custom"):
            sec = "ollama" if mode == "local" else mode
            config.definir(f"{sec}.modele", modele)
        if mode:
            config.definir("mode", mode)
        reinit_llm()
        prov = llm()
        return {
            "ok": True,
            "mode": mode or reglage("mode", "mistral"),
            "nom": getattr(prov, "nom", "-"),
            "modele": getattr(prov, "modele", "-"),
        }

    @app.post("/api/ide/chat")
    async def api_ide_chat(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json() or {}
        message = str(body.get("message", "")).strip()
        mode = str(body.get("mode", "code")).lower()
        fichier_actif = body.get("fichier_actif") if isinstance(body.get("fichier_actif"), dict) else None
        historique_client = body.get("historique") if isinstance(body.get("historique"), list) else []

        if not message:
            return JSONResponse({"ok": False, "erreur": "Message requis."}, status_code=400)

        projet = _projet_courant()
        queue_ev: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _emit(ev: Dict[str, Any]):
            loop.call_soon_threadsafe(queue_ev.put_nowait, ev)

        def _worker():
            try:
                systeme = _construire_prompt_ide(mode, projet, fichier_actif)
                if mode == "ask":
                    outils_schemas = []
                elif mode == "plan":
                    outils_schemas = _extraire_outils_ide(lecture_seule=True)
                else:
                    outils_schemas = _extraire_outils_ide(lecture_seule=False)

                hist: List[Dict[str, Any]] = []
                for h in historique_client[-8:]:
                    if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content"):
                        hist.append({"role": h["role"], "content": str(h["content"])[:4000]})
                hist.append({"role": "user", "content": message})

                texte_final = ""
                for tour in range(8):
                    _emit({"type": "step", "label": f"Reflexion agent (etape {tour + 1})..."})
                    rep = llm().repondre(systeme, hist, outils_schemas)
                    textes = [b.text for b in rep.content if getattr(b, "type", None) == "text" and b.text]
                    appels = [b for b in rep.content if getattr(b, "type", None) == "tool_use"]
                    if textes:
                        texte_final = "\n".join(textes)
                    if not appels:
                        break

                    hist.append({"role": "assistant", "content": rep.content})
                    res_blocs = []
                    for appel in appels:
                        nom = appel.name
                        args = appel.input or {}
                        _emit({"type": "tool", "statut": "running", "nom": nom, "args": args})
                        outil_obj = registre.get(nom)
                        if outil_obj is None:
                            out_str = f"Erreur: outil '{nom}' inconnu."
                        elif registre.est_n3(nom):
                            out_str = f"Action critique '{nom}' bloquee en execution automatique."
                        else:
                            try:
                                out_str = str(outil_obj.fonction(**args))
                            except Exception as ex:
                                out_str = f"Erreur execution '{nom}': {ex}"
                        _emit({
                            "type": "tool",
                            "statut": "done",
                            "nom": nom,
                            "args": args,
                            "extrait": out_str[:400],
                        })
                        if nom in ("ecrire_code", "patcher_code", "supprimer_fichier") and isinstance(args, dict):
                            ch = args.get("chemin") or args.get("fichier") or args.get("chemin_fichier") or ""
                            if ch:
                                _emit({"type": "file_changed", "chemin": str(ch)})
                        if nom == "generer_image" and "/captures/" in out_str:
                            _emit({"type": "artifact", "kind": "image", "detail": out_str})
                        res_blocs.append({"type": "tool_result", "tool_use_id": appel.id, "content": out_str[:6000]})
                    hist.append({"role": "user", "content": res_blocs})

                _emit({"type": "done", "texte": texte_final or "Tache terminee."})
            except Exception as e:
                LOG.exception("Erreur RIOT IDE chat")
                _emit({"type": "error", "erreur": str(e)})
            finally:
                _emit({"type": "_eof"})

        threading.Thread(target=_worker, daemon=True, name="riot-ide-agent").start()

        async def _stream() -> AsyncGenerator[str, None]:
            while True:
                ev = await queue_ev.get()
                if ev.get("type") == "_eof":
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

        return StreamingResponse(_stream(), media_type="text/event-stream")
