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
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from core import config, memoire, registre
from core.cli import _SESSION_CTX, _recup_branche_git
from core.config import dossier_projets, reglage
from core.llm import definir_profil_public, est_createur, identite_publique, llm, reinitialiser as reinit_llm
from core.panneau import _local_seulement

LOG = logging.getLogger("riot.ide")

_RACINE = Path(__file__).resolve().parent.parent
_WEB_DIR = _RACINE / "web"
_PENDING_PATCHES: Dict[str, Dict[str, Any]] = {}
_CHECKPOINTS: Dict[str, Dict[str, Any]] = {}

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


_RECENTS_FICHIER = Path.home() / ".riot" / "ide_recent_projects.json"


def _charger_recents() -> List[Path]:
    try:
        if not _RECENTS_FICHIER.exists():
            return []
        brut = json.loads(_RECENTS_FICHIER.read_text(encoding="utf-8"))
        if not isinstance(brut, list):
            return []
        out: List[Path] = []
        vus = set()
        for item in brut:
            p = Path(str(item)).expanduser()
            if p.exists() and p.is_dir():
                r = str(p.resolve())
                if r not in vus and (est_createur() or not p.resolve().is_relative_to(_RACINE.resolve())):
                    vus.add(r)
                    out.append(p.resolve())
        return out[:12]
    except Exception:
        return []


def _enregistrer_recent(chemin: Path) -> None:
    try:
        cible = str(chemin.resolve())
        actuels = [str(p) for p in _charger_recents() if str(p) != cible]
        nouveaux = [cible] + actuels
        _RECENTS_FICHIER.parent.mkdir(parents=True, exist_ok=True)
        _RECENTS_FICHIER.write_text(json.dumps(nouveaux[:12], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _lister_projets_disponibles() -> List[Dict[str, str]]:
    racine = dossier_projets()
    res: List[Dict[str, str]] = []
    vus = set()

    def _ajouter(p: Path) -> None:
        r = str(p.resolve()) if p.exists() else str(p)
        if r not in vus:
            vus.add(r)
            res.append({"nom": p.name or r, "chemin": r})

    for rec in _charger_recents():
        _ajouter(rec)
    if est_createur() and _RACINE.exists():
        _ajouter(_RACINE)
    if racine.exists() and racine.is_dir():
        try:
            for d in sorted(racine.iterdir(), key=lambda x: x.name.lower()):
                if d.is_dir() and not d.name.startswith(".") and str(d.resolve()) != str(_RACINE.resolve()):
                    _ajouter(d)
        except Exception:
            pass
    return res[:60]


def _extraire_outils_ide(lecture_seule: bool = False) -> List[Dict[str, Any]]:
    """Selectionne les vrais outils RIOT pour l'IDE (code, systeme, web, image, memoire)."""
    if len(registre.tous()) < 20:
        registre.charger_outils()

    cibles_lecture = {
        "explorer_projet", "lire_code", "chercher_dans_code", "lister_dossier",
        "chercher_fichiers", "chercher_web", "lire_page_web", "recueillir_veille_web",
        "git_status", "git_diff", "git_log", "requete_api_http", "github_repo_info",
        "lister_connecteurs_mcp", "recall", "chercher_recette_dev", "lister_regles",
        "get_system_stats", "lister_images_generees", "capturer_page", "browser_open",
        "grill-me", "content-strategy", "anti-ai-slop", "seo-audit",
    }
    cibles_ecriture = {
        "ecrire_code", "patcher_code", "supprimer_fichier", "executer_terminal",
        "executer_test_ou_commande", "generer_image", "remember", "forget",
        "apprendre_regle", "enregistrer_recette_dev", "installer_connecteur_mcp",
        "basculer_connecteur_mcp", "generer_diagramme", "generer_graphique",
    }
    autorises = cibles_lecture if lecture_seule else (cibles_lecture | cibles_ecriture)

    schemas = []
    for o in registre.tous():
        if o.nom in autorises or o.nom.startswith("mcp_"):
            schemas.append(
                registre.compacter_schema_outil(
                    o.nom,
                    o.description or o.nom,
                    o.parametres or {"type": "object", "properties": {}},
                )
            )
    return schemas[:64]


def _construire_prompt_ide(
    mode: str,
    projet: Path,
    fichier_actif: Optional[Dict[str, str]],
    message: str = "",
    grill_me: bool = False,
) -> str:
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

    ctx_memoire = ""
    try:
        texte_mem = memoire.texte_pour_systeme()[:2500]
        recettes = memoire.recup_recettes_pertinentes(message or (fichier_actif or {}).get("chemin", ""))
        ctx_memoire = f"{texte_mem}{recettes}"
    except Exception:
        ctx_memoire = ""

    try:
        from tools.grill_me import consigne_grill_me
        ctx_grill = consigne_grill_me(bool(grill_me or mode == "grill-me"))
    except Exception:
        ctx_grill = ""

    return (
        "Tu es RIOT IDE Copilot, un ingenieur logiciel senior travaillant directement dans l'espace de travail "
        f"`{projet}` (branche git : `{_recup_branche_git(projet) or '-'}`).\n"
        f"{regle_mode}\n"
        "Pour toute documentation externe, version recente ou fait incertain, utilise `chercher_web` / `lire_page_web` "
        "au lieu d'inventer et cite tes sources.\n"
        "Pour tout design UI / landing page / maquette, evite les hooks et cliches visuels IA generiques et "
        "verifie le rendu avec `anti-ai-slop`.\n"
        "Reponds toujours en francais, de maniere dense, structuree et verifiable."
        f"{ctx_grill}"
        f"{ctx_memoire}"
        f"{ctx_fichier}"
    )


def _resoudre_pour_patch(projet: Path, brut: str) -> Optional[Path]:
    """Resout un chemin absolu ou relatif et garantit qu'il reste dans `projet`."""
    try:
        base = projet.resolve()
        s = (brut or "").strip().strip('"').strip("'")
        if not s:
            return None
        p = Path(s)
        cible = p.resolve() if p.is_absolute() else (base / s.lstrip("/\\")).resolve()
        cible.relative_to(base)
        return cible
    except Exception:
        return None


def _simuler_et_stager_patch(projet: Path, nom_outil: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Calcule un diff complet sans ecrire sur disque et le place dans _PENDING_PATCHES."""
    fichier_arg = str(args.get("fichier") or args.get("chemin") or args.get("chemin_fichier") or "").strip()
    cible = _resoudre_pour_patch(projet, fichier_arg)
    if not cible:
        return {"ok": False, "erreur": f"Chemin invalide ou hors workspace : {fichier_arg}"}

    ancien = cible.read_text(encoding="utf-8", errors="replace") if (cible.exists() and cible.is_file()) else ""
    if nom_outil == "ecrire_code":
        nouveau = str(args.get("contenu", "")).replace("\r\n", "\n")
    else:
        if not cible.exists():
            return {"ok": False, "erreur": f"Fichier inexistant : {fichier_arg}"}
        ancien_norm = ancien.replace("\r\n", "\n")
        ancien_bloc = str(args.get("ancien_bloc", "")).replace("\r\n", "\n")
        nouveau_bloc = str(args.get("nouveau_bloc", "")).replace("\r\n", "\n")
        nb = ancien_norm.count(ancien_bloc)
        if nb == 0:
            return {"ok": False, "erreur": f"Bloc cible introuvable dans {cible.name}."}
        if nb > 1:
            return {"ok": False, "erreur": f"Bloc cible ambigu ({nb} occurrences) dans {cible.name}."}
        nouveau = ancien_norm.replace(ancien_bloc, nouveau_bloc, 1)

    rel = str(cible.relative_to(projet.resolve())).replace("\\", "/")
    diff_lignes = list(difflib.unified_diff(
        ancien.replace("\r\n", "\n").splitlines(),
        nouveau.splitlines(),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
        lineterm="",
    ))
    plus = sum(1 for l in diff_lignes if l.startswith("+") and not l.startswith("+++"))
    moins = sum(1 for l in diff_lignes if l.startswith("-") and not l.startswith("---"))

    patch_id = uuid.uuid4().hex[:10]
    patch_obj = {
        "id": patch_id,
        "chemin": rel,
        "abs_path": str(cible),
        "outil": nom_outil,
        "ancien": ancien,
        "nouveau": nouveau,
        "existait": cible.exists(),
        "diff": "\n".join(diff_lignes[:350]),
        "plus": plus,
        "moins": moins,
        "statut": "pending",
    }
    _PENDING_PATCHES[patch_id] = patch_obj
    return {"ok": True, "patch": {
        "id": patch_id,
        "chemin": rel,
        "outil": nom_outil,
        "diff": patch_obj["diff"],
        "plus": plus,
        "moins": moins,
        "statut": "pending",
    }}


def monter_routes(app) -> None:
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
    memoire.lancer_synchro_arriere_plan()

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
        pub = identite_publique(prov)
        payload = {
            "ok": True,
            "projet": {"nom": projet.name, "chemin": str(projet), "branche": _recup_branche_git(projet)},
            "projets": _lister_projets_disponibles(),
            "fournisseur": {
                "mode": mode_actuel() if pub["admin"] else pub.get("profil", "auto"),
                "nom": pub["nom"],
                "modele": pub["modele"],
                "profil": pub.get("profil", "auto"),
                "admin": pub["admin"],
                "opaque": pub["opaque"],
                "disponible": bool(prov.disponible()) if hasattr(prov, "disponible") else True,
            },
            "profils_publics": ["auto", "fast", "code", "deep"],
        }
        if pub["admin"]:
            payload["modes_llm"] = ["groq", "mistral", "gemini", "openrouter", "custom", "anthropic", "local"]
            payload["custom_base_url"] = reglage("custom.base_url", "http://127.0.0.1:31415/v1")
        return payload

    @app.post("/api/ide/projet")
    async def api_ide_projet(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json()
        chemin = Path(str((body or {}).get("chemin", "")).strip())
        if not chemin.exists() or not chemin.is_dir():
            return JSONResponse({"ok": False, "erreur": "Dossier projet introuvable."}, status_code=404)
        if not est_createur():
            try:
                chemin.resolve().relative_to(_RACINE.resolve())
                return JSONResponse({"ok": False, "erreur": "Acces au code source RIOT reserve aux createurs."}, status_code=403)
            except ValueError:
                pass
        _SESSION_CTX["projet_actif"] = chemin.resolve()
        _enregistrer_recent(chemin.resolve())
        return {"ok": True, "nom": chemin.name, "chemin": str(chemin.resolve()), "branche": _recup_branche_git(chemin)}

    @app.get("/api/ide/naviguer-dossiers")
    def api_ide_naviguer_dossiers(request: Request, chemin: str = ""):
        if (r := garde(request)):
            return r
        brut = (chemin or "").strip()
        cible = Path(brut).expanduser() if brut else _projet_courant()
        if not cible.exists() or not cible.is_dir():
            cible = Path.home()
        cible = cible.resolve()

        racines: List[Dict[str, str]] = []
        if os.name == "nt":
            import string
            for lettre in string.ascii_uppercase:
                drv = Path(f"{lettre}:\\")
                if drv.exists():
                    racines.append({"nom": f"{lettre}:\\", "chemin": str(drv)})
        else:
            racines.append({"nom": "/", "chemin": "/"})
        home_dir = Path.home()
        for label, sous in (
            (f"Accueil ({home_dir.name})", None),
            ("Bureau", "Desktop"),
            ("Documents", "Documents"),
            ("Téléchargements", "Downloads"),
        ):
            cand = home_dir if sous is None else (home_dir / sous)
            if cand.exists() and cand.is_dir():
                racines.append({"nom": label, "chemin": str(cand.resolve())})
        dp = dossier_projets()
        if dp.exists() and dp.is_dir():
            racines.append({"nom": f"Projets ({dp.name})", "chemin": str(dp.resolve())})

        parent = str(cible.parent) if cible.parent != cible else ""
        dossiers: List[Dict[str, Any]] = []
        try:
            for item in sorted(cible.iterdir(), key=lambda x: x.name.lower()):
                if not item.is_dir():
                    continue
                if item.name.startswith(".") or item.name in {"$RECYCLE.BIN", "System Volume Information"}:
                    continue
                if not est_createur() and item.resolve() == _RACINE.resolve():
                    continue
                try:
                    est_git = (item / ".git").exists()
                except Exception:
                    est_git = False
                dossiers.append({
                    "nom": item.name,
                    "chemin": str(item.resolve()),
                    "est_git": est_git,
                })
        except PermissionError:
            return JSONResponse({"ok": False, "erreur": f"Accès refusé à {cible}"}, status_code=403)

        recents = [{"nom": p.name or str(p), "chemin": str(p)} for p in _charger_recents()[:6]]
        return {
            "ok": True,
            "courant": str(cible),
            "parent": parent,
            "racines": racines,
            "recents": recents,
            "dossiers": dossiers[:250],
        }

    @app.post("/api/ide/creer-dossier")
    async def api_ide_creer_dossier(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json() or {}
        parent_brut = str(body.get("parent", "")).strip()
        nom = str(body.get("nom", "")).strip()
        if not nom or any(c in nom for c in ("/", "\\", "..", "\0")):
            return JSONResponse({"ok": False, "erreur": "Nom de dossier invalide."}, status_code=400)
        parent = Path(parent_brut).expanduser().resolve() if parent_brut else _projet_courant().resolve()
        if not parent.exists() or not parent.is_dir():
            return JSONResponse({"ok": False, "erreur": "Dossier parent introuvable."}, status_code=404)
        cible = (parent / nom).resolve()
        try:
            cible.mkdir(parents=False, exist_ok=True)
        except Exception as e:
            return JSONResponse({"ok": False, "erreur": f"Création impossible : {e}"}, status_code=400)
        return {"ok": True, "nom": cible.name, "chemin": str(cible)}

    @app.post("/api/ide/choisir-dossier-os")
    async def api_ide_choisir_dossier_os(request: Request):
        if (r := garde(request)):
            return r
        import asyncio

        init_dir = str(_projet_courant())

        def _ouvrir_dialogue() -> str:
            if os.name == "nt":
                try:
                    ps_init = init_dir.replace("'", "''")
                    ps_script = (
                        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$owner = New-Object System.Windows.Forms.Form -Property @{TopMost=$true;ShowInTaskbar=$false;WindowState='Minimized'}; "
                        "$dlg = New-Object System.Windows.Forms.FolderBrowserDialog; "
                        "$dlg.Description = 'Sélectionner un dossier projet — RIOT IDE'; "
                        "$dlg.UseDescriptionForTitle = $true; "
                        "$dlg.ShowNewFolderButton = $true; "
                        f"if (Test-Path -LiteralPath '{ps_init}') {{ $dlg.SelectedPath = '{ps_init}' }}; "
                        "if ($dlg.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $dlg.SelectedPath }; "
                        "$owner.Dispose()"
                    )
                    res = subprocess.run(
                        ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=120,
                    )
                    if res.returncode == 0:
                        choisi_ps = (res.stdout or "").strip()
                        return choisi_ps
                except Exception:
                    pass

            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            choisi = filedialog.askdirectory(
                title="Ouvrir un dossier projet — RIOT IDE",
                initialdir=init_dir,
            )
            root.destroy()
            return str(choisi or "").strip()

        try:
            choisi = await asyncio.to_thread(_ouvrir_dialogue)
        except Exception as e:
            return JSONResponse({"ok": False, "erreur": f"Sélecteur système indisponible : {e}"}, status_code=500)
        if not choisi:
            return {"ok": False, "annule": True, "erreur": "Sélection annulée."}
        return {"ok": True, "chemin": str(Path(choisi).resolve())}

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
        try:
            req_timeout = int((body or {}).get("timeout", 120))
        except Exception:
            req_timeout = 120
        timeout_s = max(5, min(300, req_timeout))
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
                timeout=timeout_s,
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-12000:],
                "stderr": proc.stderr[-6000:],
                "duree_ms": int((time.time() - t0) * 1000),
                "cwd": str(projet),
                "timeout_s": timeout_s,
            }
        except subprocess.TimeoutExpired:
            return JSONResponse({"ok": False, "erreur": f"Timeout ({timeout_s}s depassees)."}, status_code=408)
        except Exception as e:
            return JSONResponse({"ok": False, "erreur": str(e)}, status_code=500)

    @app.post("/api/ide/modele")
    async def api_ide_modele(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json() or {}
        if not est_createur():
            profil = str(body.get("profil") or body.get("mode") or "auto").strip().lower()
            pub = definir_profil_public(profil)
            return {
                "ok": True,
                "mode": pub.get("profil", "auto"),
                "nom": pub["nom"],
                "modele": pub["modele"],
                "admin": False,
            }

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
        pub = identite_publique(llm())
        return {
            "ok": True,
            "mode": mode or reglage("mode", "mistral"),
            "nom": pub["nom"],
            "modele": pub["modele"],
            "admin": True,
        }

    @app.post("/api/ide/chat")
    async def api_ide_chat(request: Request):
        if (r := garde(request)):
            return r
        body = await request.json() or {}
        message = str(body.get("message", "")).strip()
        mode = str(body.get("mode", "code")).lower()
        review_mode = bool(body.get("review_mode", True))
        grill_me = bool(body.get("grill_me", False)) or mode == "grill-me" or message.lower().startswith("/grill-me")
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
                systeme = _construire_prompt_ide(mode, projet, fichier_actif, message=message, grill_me=grill_me)
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

                from core.model_router import JournalContinuite

                mode_hints = {"ask": "fast", "plan": "deep", "code": "code", "swarm": "code"}
                tache_hint = mode_hints.get(mode, "code")
                journal = JournalContinuite(objectif=message, dossier=str(projet))

                texte_final = ""
                appels_vus: Dict[str, int] = {}
                boucle_epuisee = False
                for tour in range(8):
                    _emit({"type": "step", "label": f"Reflexion agent (etape {tour + 1})..."})
                    systeme_tour = systeme + journal.rendre_bloc()
                    rep = llm().repondre(systeme_tour, hist, outils_schemas, tache_hint=tache_hint)
                    textes = [b.text for b in rep.content if getattr(b, "type", None) == "text" and b.text]
                    appels = [b for b in rep.content if getattr(b, "type", None) == "tool_use"]
                    if textes:
                        texte_final = "\n".join(textes)
                    if not appels:
                        break

                    hist.append({"role": "assistant", "content": rep.content})
                    res_blocs = []
                    boucle_repetee = False
                    for appel in appels:
                        nom = appel.name
                        args = appel.input or {}
                        sig = f"{nom}:{json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)}"
                        appels_vus[sig] = appels_vus.get(sig, 0) + 1
                        if appels_vus[sig] > 2:
                            out_str = f"[GARDE-BOUCLE] Outil '{nom}' deja appele {appels_vus[sig] - 1} fois avec les memes arguments. Changez d'approche ou concluez."
                            boucle_repetee = True
                            _emit({"type": "tool", "statut": "done", "nom": nom, "args": args, "extrait": out_str})
                            res_blocs.append({"type": "tool_result", "tool_use_id": appel.id, "content": out_str})
                            continue

                        _emit({"type": "tool", "statut": "running", "nom": nom, "args": args})

                        if review_mode and nom in ("ecrire_code", "patcher_code") and isinstance(args, dict):
                            staged = _simuler_et_stager_patch(projet, nom, args)
                            if staged.get("ok"):
                                pinfo = staged["patch"]
                                out_str = (
                                    f"Proposition de patch #{pinfo['id']} sur `{pinfo['chemin']}` "
                                    f"(+{pinfo['plus']} / -{pinfo['moins']} lignes) mise en attente de validation utilisateur."
                                )
                                _emit({"type": "pending_patch", "patch": pinfo})
                            else:
                                out_str = f"[ERREUR] {staged.get('erreur', 'Echec staging patch')}"
                        else:
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
                            if nom in ("ecrire_code", "patcher_code", "supprimer_fichier") and isinstance(args, dict):
                                ch = args.get("chemin") or args.get("fichier") or args.get("chemin_fichier") or ""
                                if ch:
                                    _emit({"type": "file_changed", "chemin": str(ch)})

                        journal.enregistrer_appel(nom, args if isinstance(args, dict) else {}, out_str)
                        _emit({
                            "type": "tool",
                            "statut": "done",
                            "nom": nom,
                            "args": args,
                            "extrait": out_str[:400],
                        })
                        if nom == "generer_image" and "/captures/" in out_str:
                            _emit({"type": "artifact", "kind": "image", "detail": out_str})
                        res_blocs.append({"type": "tool_result", "tool_use_id": appel.id, "content": out_str[:6000]})
                    hist.append({"role": "user", "content": res_blocs})
                    if boucle_repetee or tour == 7:
                        boucle_epuisee = True
                        if boucle_repetee:
                            break

                if boucle_epuisee and not texte_final.strip():
                    _emit({"type": "step", "label": "Synthese finale de l'agent..."})
                    hist.append({
                        "role": "user",
                        "content": "Fais maintenant une synthese claire et concise de ce qui a ete accompli, des fichiers touches et des eventuelles etapes restantes.",
                    })
                    rep_fin = llm().repondre(systeme + journal.rendre_bloc(), hist, [], tache_hint=tache_hint)
                    textes_fin = [b.text for b in rep_fin.content if getattr(b, "type", None) == "text" and b.text]
                    if textes_fin:
                        texte_final = "\n".join(textes_fin)

                _emit({"type": "done", "texte": texte_final or "Tache terminee."})
                if texte_final:
                    memoire.lancer_auto_memoire_asynchrone(message, texte_final, surface="ide")
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

    @app.get("/api/ide/patches")
    def api_ide_patches(request: Request):
        if (r := garde(request)):
            return r
        return {
            "ok": True,
            "patches": [
                {
                    "id": p["id"],
                    "chemin": p["chemin"],
                    "outil": p["outil"],
                    "plus": p["plus"],
                    "moins": p["moins"],
                    "diff": p["diff"],
                }
                for p in _PENDING_PATCHES.values()
            ],
        }

    @app.post("/api/ide/patch/{patch_id}/accept")
    def api_ide_patch_accept(request: Request, patch_id: str):
        if (r := garde(request)):
            return r
        patch = _PENDING_PATCHES.pop(patch_id, None)
        if not patch:
            return JSONResponse({"ok": False, "erreur": "Patch introuvable ou deja traite."}, status_code=404)
        cible = Path(patch["abs_path"])
        cible.parent.mkdir(parents=True, exist_ok=True)
        _CHECKPOINTS[patch_id] = {
            "abs_path": patch["abs_path"],
            "chemin": patch["chemin"],
            "ancien": patch["ancien"],
            "existait": patch["existait"],
        }
        cible.write_text(patch["nouveau"], encoding="utf-8")
        return {
            "ok": True,
            "id": patch_id,
            "chemin": patch["chemin"],
            "contenu": patch["nouveau"],
            "diff": patch["diff"],
        }

    @app.post("/api/ide/patch/{patch_id}/reject")
    def api_ide_patch_reject(request: Request, patch_id: str):
        if (r := garde(request)):
            return r
        patch = _PENDING_PATCHES.pop(patch_id, None)
        if not patch:
            return JSONResponse({"ok": False, "erreur": "Patch introuvable."}, status_code=404)
        return {"ok": True, "id": patch_id, "chemin": patch["chemin"]}

    @app.post("/api/ide/patch/{patch_id}/revert")
    def api_ide_patch_revert(request: Request, patch_id: str):
        if (r := garde(request)):
            return r
        cp = _CHECKPOINTS.pop(patch_id, None)
        if not cp:
            return JSONResponse({"ok": False, "erreur": "Checkpoint introuvable."}, status_code=404)
        cible = Path(cp["abs_path"])
        if not cp["existait"]:
            if cible.exists():
                cible.unlink()
            return {"ok": True, "chemin": cp["chemin"], "supprime": True}
        cible.write_text(cp["ancien"], encoding="utf-8")
        return {"ok": True, "chemin": cp["chemin"], "contenu": cp["ancien"]}

    @app.get("/api/ide/chemins")
    def api_ide_chemins(request: Request):
        if (r := garde(request)):
            return r
        projet = _projet_courant()
        liste: List[str] = []
        for root, dirs, files in os.walk(projet):
            dirs[:] = [d for d in dirs if d not in _DOSSIERS_IGNORES and not d.startswith(".")]
            for fn in sorted(files):
                p = Path(root) / fn
                if p.suffix.lower() in _EXT_BINAIRES:
                    continue
                try:
                    liste.append(str(p.relative_to(projet)).replace("\\", "/"))
                    if len(liste) >= 500:
                        return {"ok": True, "chemins": liste}
                except Exception:
                    continue
        return {"ok": True, "chemins": liste}

    @app.get("/api/ide/mcp")
    def api_ide_mcp_list(request: Request):
        if (r := garde(request)):
            return r
        from core import mcp_client
        return {
            "ok": True,
            "catalogue": mcp_client.lister_catalogue_connecteurs(),
            "statut": mcp_client.statut_mcp(),
            "config_path": str(mcp_client.fichier_config_mcp()),
        }

    @app.post("/api/ide/mcp/add")
    async def api_ide_mcp_add(request: Request):
        if (r := garde(request)):
            return r
        from core import mcp_client
        body = await request.json() or {}
        slug = str(body.get("slug") or "").strip()
        credential = str(body.get("credential") or "").strip()
        recharger = bool(body.get("recharger", True))
        res = mcp_client.installer_connecteur_catalogue(slug, credential=credential, activer=True, recharger=recharger)
        code = 200 if res.get("ok") else 400
        return JSONResponse(res, status_code=code)

    @app.post("/api/ide/mcp/toggle")
    async def api_ide_mcp_toggle(request: Request):
        if (r := garde(request)):
            return r
        from core import mcp_client
        body = await request.json() or {}
        nom = str(body.get("nom") or "").strip()
        enabled = bool(body.get("enabled", True))
        recharger = bool(body.get("recharger", True))
        ok = mcp_client.basculer_connecteur_mcp(nom, enabled=enabled, recharger=recharger)
        if not ok:
            return JSONResponse({"ok": False, "erreur": f"Connecteur '{nom}' introuvable."}, status_code=404)
        return {"ok": True, "nom": nom, "enabled": enabled}

    @app.post("/api/ide/mcp/reload")
    def api_ide_mcp_reload(request: Request):
        if (r := garde(request)):
            return r
        from core import mcp_client
        ok = mcp_client.recharger_connexions_mcp()
        return {"ok": bool(ok), "statut": mcp_client.statut_mcp()}

    @app.delete("/api/ide/mcp/{nom}")
    def api_ide_mcp_delete(request: Request, nom: str):
        if (r := garde(request)):
            return r
        from core import mcp_client
        ok = mcp_client.supprimer_connecteur_mcp(nom.strip(), recharger=True)
        if not ok:
            return JSONResponse({"ok": False, "erreur": f"Connecteur '{nom}' introuvable."}, status_code=404)
        return {"ok": True, "nom": nom}
