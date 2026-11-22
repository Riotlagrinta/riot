"""Terminal RIOT : Interface CLI épurée et multi-thèmes pour développeurs et système.

Supporte 3 thèmes commutables via `/theme` (`obsidian`, `paper`, `tactical`).
"""
import os
import sys
import json
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# Forcer l'encodage UTF-8 sous Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PromptStyle
from rich.box import ROUNDED, SIMPLE, HORIZONTALS
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from core import auth, budget, config, etude, memoire, registre, theme
from core.config import reglage, dossier_projets
from core.llm import llm

_RACINE = Path(__file__).resolve().parent.parent


def _dossier_logs() -> Path:
    """Retourne un dossier logs/ inscriptible (local en dev, ~/.riot/logs sinon)."""
    if (_RACINE / "pyproject.toml").exists() and os.access(_RACINE, os.W_OK):
        return _RACINE / "logs"
    return Path.home() / ".riot" / "logs"


_HISTORIQUE_FICHIER = _dossier_logs() / ".riot_cli_history"
_HISTORIQUE_FICHIER.parent.mkdir(parents=True, exist_ok=True)

console = Console()


def _pal():
    """Retourne la palette du theme actif."""
    return theme.palette()


def _style_prompt_courant() -> PromptStyle:
    p = _pal()
    return PromptStyle.from_dict({
        "prompt-brand": f"{p['cli_accent']} bold",
        "prompt-project": p["cli_secondary"],
        "prompt-arrow": f"{p['cli_accent']} bold",
    })


_P_INIT = _pal()
RIOT_CORAL = _P_INIT["cli_accent"]
RIOT_DIM = _P_INIT["cli_dim"]
RIOT_GREEN = _P_INIT["cli_ok"]
RIOT_CYAN = _P_INIT["cli_secondary"]
RIOT_GOLD = _P_INIT["cli_warn"]
RIOT_WHITE = _P_INIT["cli_text"]
RIOT_RED = _P_INIT["cli_err"]
RIOT_BG = _P_INIT["cli_bg"]
_STYLE_PROMPT = _style_prompt_courant()

_COMMANDES_INTERNES = [
    "/login", "/logout",
    "/mcp",
    "/theme",
    "/update",
    "/ide",
    "/app", "/studio",
    "/file", "/fichier",
    "/trade", "/trader",
    "/swarm", "/pipeline",
    "/architect", "/engineer", "/test", "/tester", "/review", "/reviewer",
    "/code", "/coder", "/dev",
    "/project", "/projet",
    "/model", "/fournisseur",
    "/tools", "/outils",
    "/pc", "/status", "/system",
    "/remote", "/mobile",
    "/tokens", "/cost",
    "/grill-me",
    "/mentor",
    "/memory", "/mem", "/memoire",
    "/recettes",
    "/clear", "/cls",
    "/help", "/aide",
    "/exit", "/quit", "/q",
]

# État global de la session CLI (Mode Discussion Libre sans projet forcé par défaut)
_SESSION_CTX = {
    "projet_actif": None,
    "mode_code": True,
    "grill_me": False,
    "tokens_prompt": 0,
    "tokens_reponse": 0,
}


def _recup_branche_git(dossier: Optional[Path]) -> str:
    """Récupère le nom de la branche git si le dossier est un dépôt."""
    if not dossier:
        return ""
    try:
        if (dossier / ".git").exists():
            res = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(dossier),
                capture_output=True,
                text=True,
                timeout=2,
            )
            branche = (res.stdout or "").strip()
            if branche:
                return f"git:{branche}"
    except Exception:
        pass
    return ""


def afficher_banniere_riot():
    """Affiche l'en-tête compact et multi-thèmes de RIOT CLI."""
    import psutil

    if not registre.tous():
        registre.charger_outils()

    p = _pal()
    acc = p["cli_accent"]
    sec = p["cli_secondary"]
    warn = p["cli_warn"]

    from core.llm import identite_publique
    provider = llm()
    pub = identite_publique(provider)
    nom_modele = pub["modele"]
    fournisseur_nom = pub["nom"]

    projet = _SESSION_CTX["projet_actif"]
    branche = _recup_branche_git(projet)
    branche_str = f" │ [italic {sec}]{branche}[/italic {sec}]" if branche else ""

    vm = psutil.virtual_memory()
    ram_str = f"{round(vm.used / (1024 ** 3), 1)}/{round(vm.total / (1024 ** 3), 1)} Go"

    if pub["opaque"]:
        ctx_taille = "Auto"
    else:
        ctx_taille = "32k" if "codestral" in nom_modele.lower() else ("128k" if "llama" in nom_modele.lower() or "groq" in fournisseur_nom.lower() else "1M")

    mode_label = f"[bold {acc}]⚡ RIOT Coder[/bold {acc}]" if _SESSION_CTX["mode_code"] else f"[bold {sec}]⚡ RIOT Copilot[/bold {sec}]"
    th_id = p["id"]

    ligne1 = f"  {mode_label}  [dim]•[/dim]  Modèle: [bold white]{nom_modele}[/bold white] ({fournisseur_nom})  [dim]•[/dim]  Ctx: [{warn}]{ctx_taille}[/{warn}]  [dim]•[/dim]  Thème: [bold {acc}]{th_id}[/bold {acc}]"
    if projet:
        ligne2 = f"  📁 Projet : [bold {warn}]{projet.name}[/bold {warn}] ([dim]{projet}[/dim]){branche_str}  [dim]•[/dim]  RAM: [green]{ram_str}[/green]"
    else:
        ligne2 = f"  💬 Mode : [bold {warn}]Discussion Libre[/bold {warn}] (Aucun projet/dossier fixé)  [dim]•[/dim]  RAM: [green]{ram_str}[/green]"

    console.print()
    console.print(Panel(
        f"{ligne1}\n{ligne2}",
        border_style=acc,
        box=ROUNDED,
        padding=(0, 1),
    ))
    console.print("[dim]  Astuce : Tapez votre ordre en français, [bold white]/theme[/bold white] pour changer de design ou [bold white]/help[/bold white].[/dim]")
    console.print()


def commande_theme(arg: str = ""):
    """Affiche ou bascule le thème actif (`obsidian`, `paper`, `tactical`)."""
    p = _pal()
    acc = p["cli_accent"]
    sec = p["cli_secondary"]
    arg_clean = (arg or "").strip()
    if not arg_clean:
        table = Table(title="🎨 Thèmes RIOT disponibles", border_style=acc, box=ROUNDED)
        table.add_column("ID", style=f"bold {acc}")
        table.add_column("Nom", style="bold white")
        table.add_column("Description", style="dim")
        table.add_column("État", style=f"bold {sec}")
        act = theme.theme_actif()
        for t in theme.lister_themes():
            etat = "● Actif" if t["id"] == act else "○"
            table.add_row(t["id"], t["nom"], t["description"], etat)
        console.print()
        console.print(table)
        console.print("[dim]  Usage : [bold white]/theme obsidian[/bold white] | [bold white]/theme paper[/bold white] | [bold white]/theme tactical[/bold white][/dim]\n")
        return

    nouveau = theme.definir_theme(arg_clean)
    pal_new = theme.palette(nouveau)
    console.print(f"[bold {pal_new['cli_accent']}]✓ Thème RIOT basculé sur :[/bold {pal_new['cli_accent']}] [bold white]{pal_new['nom']}[/bold white] ({nouveau})\n")


def commande_update(arg: str = ""):
    """Vérifie ou exécute la mise à jour de RIOT."""
    from core import updater
    p = _pal()
    acc = p["cli_accent"]
    sec = p["cli_secondary"]
    arg_clean = (arg or "").strip().lower()

    if arg_clean in ("check", "statut", "status"):
        etat = updater.etat_mise_a_jour(forcer=True)
        console.print(f"  [bold {acc}]RIOT Version :[/bold {acc}] v{etat['version_locale']} ({etat['mode_install']})")
        if etat.get("disponible"):
            console.print(f"  [bold {p['cli_warn']}]↑ {etat['details']}[/bold {p['cli_warn']}]")
        else:
            console.print(f"  [bold {sec}]✓ {etat['details']}[/bold {sec}]")
        return

    etat = updater.etat_mise_a_jour(forcer=True)
    if not etat.get("disponible") and arg_clean != "force":
        console.print(f"  [bold {sec}]✓ {etat['details']}[/bold {sec}]")
        return

    res = updater.executer_mise_a_jour()
    if res.get("ok"):
        console.print(f"  [bold {sec}]✓ {res.get('message', 'Mise à jour effectuée.')}[/bold {sec}]")
    else:
        console.print(f"  [bold {p['cli_err']}]✕ {res.get('message', 'Échec de mise à jour.')}[/bold {p['cli_err']}]")


def commande_keys(arg: str = ""):
    """Affiche l'etat des cles API et quotas restants (reserve au createur)."""
    from core import key_quota
    from core.llm import est_createur
    p = _pal()
    if not est_createur():
        console.print(f"  [bold {p['cli_err']}]✕ Commande réservée au mode créateur (admin_mode / RIOT_ADMIN=1).[/bold {p['cli_err']}]")
        return

    sonder = (arg or "").strip().lower() not in ("cache", "cached", "fast")
    with console.status(f"[bold {p['cli_accent']}]Vérification des clés API & quotas...[/bold {p['cli_accent']}]"):
        data = key_quota.inspecter_cles(sonder=sonder)

    acc = p["cli_accent"]
    sec = p["cli_secondary"]
    table = Table(title="🔑 État & Quotas des Clés API (Mode Créateur)", border_style=acc, box=ROUNDED)
    table.add_column("Provider", style=f"bold {acc}")
    table.add_column("Clé", style="dim")
    table.add_column("Modèle", style="white")
    table.add_column("État", style="bold")
    table.add_column("Requêtes rest.", style=f"bold {sec}")
    table.add_column("Tokens rest.", style="cyan")
    table.add_column("Reset / Notes", style="dim")

    for row in data.get("cles", []):
        etat = row.get("etat", "-")
        etat_fmt = f"[green]● {etat}[/green]" if etat == "OK" else (f"[yellow]⚠ {etat}[/yellow]" if "429" in etat else f"[red]✕ {etat}[/red]")
        req_str = f"{row['req_remaining']} / {row['req_limit']}" if row.get("req_remaining") is not None else "-"
        tok_str = f"{row['tok_remaining']} / {row['tok_limit']}" if row.get("tok_remaining") is not None else "-"
        note = f"{row.get('reset', '-')} · {row.get('note', '')}".strip(" ·")
        table.add_row(row["provider"], row["cle_masquee"], row["modele"], etat_fmt, req_str, tok_str, note[:48])

    console.print()
    console.print(table)
    bj = data.get("budget_jour") or {}
    if bj:
        res_jour = " │ ".join(f"{k}: {v.get('appels', 0)} req / {v.get('tin', 0) + v.get('tout', 0)} tok" for k, v in bj.items())
        console.print(f"  [dim]Conso locale du jour : {res_jour}[/dim]\n")


def commande_login(arg: str = ""):
    """Connecte ce poste client à RIOT Engine via un jeton personnel Neon (`riot_cli_...`)."""
    import requests
    import webbrowser
    from core import llm as llm_mod

    p = _pal()
    acc = p["cli_accent"]
    gw_url = (
        os.environ.get("RIOT_GATEWAY_URL", "")
        or str(reglage("gateway.url", "") or "")
        or getattr(llm_mod, "DEFAULT_GATEWAY_URL", "https://riot-engine-proxy.onrender.com/v1")
    ).strip().rstrip("/")
    verify_url = gw_url[:-3] if gw_url.endswith("/v1") else gw_url
    portal_url = os.environ.get("RIOT_PORTAL_URL", "https://riot-portal.vercel.app/account").strip()

    tok = (arg or "").strip()
    if not tok:
        console.print(Panel(
            f"[bold {acc}]Connexion obligatoire à RIOT Engine[/bold {acc}]\n"
            f"1. Crée un compte ou connecte-toi sur : [bold white]{portal_url}[/bold white]\n"
            "2. Génère un jeton CLI/IDE ([cyan]riot_cli_...[/cyan]) et colle-le ci-dessous.",
            border_style=acc,
            box=ROUNDED,
        ))
        try:
            webbrowser.open(portal_url)
        except Exception:
            pass
        try:
            tok = input("Jeton RIOT (riot_cli_...) : ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return

    if not tok:
        console.print("[yellow]Connexion annulée (aucun jeton saisi).[/yellow]")
        return

    with console.status(f"[bold {acc}]Vérification du jeton sur RIOT Engine...[/bold {acc}]"):
        try:
            r = requests.get(
                f"{verify_url}/auth/verify",
                headers={"Authorization": f"Bearer {tok}"},
                timeout=35,
            )
        except Exception as e:
            console.print(f"[bold red]✕ Serveur injoignable : {e}[/bold red]")
            return

    if r.status_code != 200:
        detail = ""
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = r.text[:160]
        console.print(f"[bold red]✕ Jeton refusé (HTTP {r.status_code}) : {detail}[/bold red]")
        return

    data = r.json()
    u = data.get("user") or {}
    config.definir("gateway.url", gw_url)
    config.definir("gateway.token", tok)
    llm_mod.reinitialiser()
    memoire.lancer_synchro_arriere_plan()
    quota_txt = (
        f"{u.get('used_24h', 0)} req/24h · Illimité"
        if (u.get("unlimited") or not u.get("daily_quota"))
        else f"{u.get('used_24h', 0)}/{u.get('daily_quota')} req/24h"
    )
    console.print(
        f"[bold green]✓ Connecté ![/bold green] "
        f"[white]{u.get('display_name') or u.get('email')}[/white] · "
        f"Plan [bold {acc}]{str(u.get('plan', 'free')).upper()}[/bold {acc}] "
        f"({quota_txt})\n"
    )


def commande_logout():
    """Supprime le jeton local du poste client."""
    from core import llm as llm_mod
    config.definir("gateway.token", "")
    llm_mod.reinitialiser()
    console.print("[bold yellow]✓ Déconnecté de RIOT Engine. Utilisez /login pour vous reconnecter.[/bold yellow]\n")


def commande_outils():
    """Affiche la liste catégorisée des outils disponibles sans erreur d'attribut."""
    p = _pal()
    outils = registre.tous()
    table = Table(title=f"🛠️ Boîte à Outils RIOT ({len(outils)} disponibles)", border_style=p["cli_accent"], box=ROUNDED)
    table.add_column("Nom Outil", style=f"bold {p['cli_warn']}")
    table.add_column("Module", style=f"dim {p['cli_secondary']}")
    table.add_column("Description", style="white")

    for o in sorted(outils, key=lambda x: x.nom)[:40]:
        module_nom = getattr(o.fonction, "__module__", "tools").replace("tools.", "")
        desc = (o.description or "").split("\n")[0][:75]
        table.add_row(o.nom, module_nom, desc)

    console.print(table)
    if len(outils) > 40:
        console.print(f"[dim](... et {len(outils) - 40} autres outils spécialisés disponibles automatiquement)[/dim]\n")


def commande_mcp(arg: str = ""):
    """Gère les connecteurs MCP : statut, catalogue (/mcp catalog), ajout (/mcp add) et activation."""
    from core import mcp_client
    p = _pal()
    acc = p["cli_accent"]
    brut = (arg or "").strip()
    parties = brut.split(maxsplit=2)
    action = parties[0].lower() if parties else ""

    if action in ("catalog", "catalogue", "list", "store"):
        cat = mcp_client.lister_catalogue_connecteurs()
        table = Table(
            title=f"🧩 Catalogue des Connecteurs MCP ({len(cat)} prêts à l'emploi)",
            border_style=acc,
            box=ROUNDED,
        )
        table.add_column("Slug", style=f"bold {p['cli_warn']}")
        table.add_column("Catégorie", style=p["cli_secondary"])
        table.add_column("État", style="white")
        table.add_column("Clé / Env requise", style="dim")
        table.add_column("Description", style="dim")
        for c in cat:
            etat = "[bold green]● Actif[/bold green]" if c["actif"] else ("[yellow]○ Installé[/yellow]" if c["installe"] else "[dim]Disponible[/dim]")
            envs = ", ".join(c["env_requis"]) if c["env_requis"] else "Aucune (0 clé)"
            table.add_row(c["slug"], c["categorie"], etat, envs, c["description"][:58])
        console.print()
        console.print(table)
        console.print("[dim]  Installer en 1 ligne : [bold white]/mcp add <slug> [cle_api_ou_url][/bold white] (ex: `/mcp add firecrawl fc-...`)[/dim]\n")
        return

    if action == "add":
        if len(parties) < 2:
            console.print("[yellow]Usage : /mcp add <slug> [cle_api_ou_url][/yellow] (voir `/mcp catalog`)")
            return
        slug = parties[1].strip()
        cred = parties[2].strip() if len(parties) >= 3 else ""
        with console.status(f"[bold {acc}]Installation et connexion du connecteur '{slug}'...[/bold {acc}]"):
            res = mcp_client.installer_connecteur_catalogue(slug, credential=cred, activer=True, recharger=True)
        if not res.get("ok"):
            console.print(f"[bold red]✕ {res.get('erreur')}[/bold red]\n")
            return
        manq = res.get("env_manquantes") or []
        console.print(f"[bold green]✓ Connecteur '{res['slug']}' enregistré[/bold green] dans [dim]{res['config_path']}[/dim]")
        if manq:
            console.print(f"[yellow]⚠ Variable(s) requise(s) non définie(s) : {', '.join(manq)}[/yellow]")
        console.print()
        return

    if action in ("enable", "on", "disable", "off"):
        if len(parties) < 2:
            console.print(f"[yellow]Usage : /mcp {action} <nom_connecteur>[/yellow]")
            return
        nom_c = parties[1].strip()
        ok_b = mcp_client.basculer_connecteur_mcp(nom_c, enabled=action in ("enable", "on"), recharger=True)
        console.print(f"[bold green]✓ Connecteur '{nom_c}' mis à jour.[/bold green]\n" if ok_b else f"[red]✕ Connecteur '{nom_c}' introuvable.[/red]\n")
        return

    if action in ("remove", "rm", "del"):
        if len(parties) < 2:
            console.print("[yellow]Usage : /mcp remove <nom_connecteur>[/yellow]")
            return
        nom_c = parties[1].strip()
        ok_d = mcp_client.supprimer_connecteur_mcp(nom_c, recharger=True)
        console.print(f"[bold green]✓ Connecteur '{nom_c}' supprimé.[/bold green]\n" if ok_d else f"[red]✕ Connecteur '{nom_c}' introuvable.[/red]\n")
        return

    arg_clean = brut.lower()
    if not mcp_client._STATUTS_SERVEURS or arg_clean in ("reload", "refresh", "r"):
        with console.status(f"[bold {acc}]Connexion aux serveurs MCP...[/bold {acc}]"):
            if arg_clean in ("reload", "refresh", "r"):
                mcp_client.recharger_connexions_mcp()
            else:
                mcp_client.initialiser_connexions_mcp()

    st = mcp_client.statut_mcp()
    serveurs = st.get("serveurs", {})
    total_outils = st.get("total_outils_mcp", 0)

    table = Table(
        title=f"🔌 Connexions MCP (Model Context Protocol) · {len(serveurs)} serveurs ({total_outils} outils)",
        border_style=acc,
        box=ROUNDED
    )
    table.add_column("Serveur MCP", style=f"bold {p['cli_warn']}")
    table.add_column("Transport", style="dim")
    table.add_column("Statut", style="white")
    table.add_column("Outils", style=p["cli_secondary"])
    table.add_column("Détails / Description", style="dim")

    for nom, info in serveurs.items():
        statut = info.get("statut", "inconnu")
        if statut == "connecté":
            statut_badge = "[bold green]● Connecté[/bold green]"
        elif statut == "désactivé":
            statut_badge = "[dim]○ Désactivé[/dim]"
        else:
            statut_badge = "[bold red]✕ Erreur[/bold red]"

        trans = info.get("transport", "-")
        count = str(info.get("outils_count", 0))
        err = info.get("erreur") or info.get("description") or "-"
        table.add_row(nom, trans, statut_badge, count, str(err)[:60])

    console.print()
    console.print(table)
    console.print(f"[dim]  Config : {mcp_client.fichier_config_mcp()} │ Catalogue : [bold white]/mcp catalog[/bold white] │ Ajout : [bold white]/mcp add <slug> [cle][/bold white] │ Recharger : [bold white]/mcp reload[/bold white][/dim]\n")


def commande_aide():
    """Affiche le guide minimaliste RIOT CLI."""
    p = _pal()
    acc = p["cli_accent"]
    sec = p["cli_warn"]
    aide = (
        f"[bold {acc}]Multi-Agents & Spécialistes :[/bold {acc}]\n"
        f"  • [bold {sec}]/trade <crypto>[/bold {sec}]       : Invoque RIOT-Trader (Analyse quant, RSI, Carnet, Risk Management 1%)\n"
        f"  • [bold {sec}]/swarm <mission>[/bold {sec}]     : Lance la chaîne complète (Architecte ➔ Ingénieur ➔ Testeur ➔ Reviewer)\n"
        f"  • [bold {sec}]/architect <mission>[/bold {sec}] : Analyse la codebase et conçoit le plan d'action chirurgical\n"
        f"  • [bold {sec}]/engineer <mission>[/bold {sec}]  : Applique les modifications de code via patcher_code\n"
        f"  • [bold {sec}]/test <mission>[/bold {sec}]      : Exécute les tests unitaires et vérifie la qualité\n"
        f"  • [bold {sec}]/review <mission>[/bold {sec}]    : Audit de sécurité (secrets/tokens), typage et verdict final\n\n"
        f"[bold {acc}]Commandes Rapides & Design :[/bold {acc}]\n"
        f"  • [bold {sec}]/theme [nom][/bold {sec}]         : Change le design (obsidian, paper, tactical)\n"
        f"  • [bold {sec}]/ide[/bold {sec}]                  : Ouvre RIOT IDE (éditeur multi-panneaux + terminal + agent)\n"
        f"  • [bold {sec}]/grill-me [on|off|sujet][/bold {sec}] : Pose des questions ciblées avant d'agir (cadrage auto)\n"
        f"  • [bold {sec}]/memory [sync|forget][/bold {sec}] : Affiche la mémoire persistante ou force la synchro Cloud\n"
        f"  • [bold {sec}]/update [check][/bold {sec}]       : Vérifie et installe les mises à jour RIOT\n"
        f"  • [bold {sec}]/mcp [catalog|add|reload][/bold {sec}] : Gère et installe les connecteurs MCP (Firecrawl, GitHub, Neon...)\n"
        f"  • [bold {sec}]/app[/bold {sec}]                  : Lance RIOT Studio en application bureau & web\n"
        f"  • [bold {sec}]/code[/bold {sec}]                 : Bascule le mode Développeur / Coder mono-agent\n"
        f"  • [bold {sec}]/project <nom>[/bold {sec}]         : Change de projet actif (ex: [italic]/project Trade App[/italic])\n"
        f"  • [bold {sec}]/model <nom>[/bold {sec}]           : Affiche ou bascule le modèle LLM actif\n"
        f"  • [bold {sec}]/tools[/bold {sec}]                 : Liste l'ensemble des outils de code, image et système\n"
        f"  • [bold {sec}]/tokens[/bold {sec}]                : Affiche le décompte de tokens de la session\n"
        f"  • [bold {sec}]/pc[/bold {sec}]                    : Jauge processeur, mémoire vive et disques\n"
        f"  • [bold {sec}]/remote[/bold {sec}]                : Affiche les URL web mobile et tunnel 4G/5G\n"
        f"  • [bold {sec}]/clear[/bold {sec}]                 : Nettoie l'écran du terminal\n"
        f"  • [bold {sec}]/exit[/bold {sec}]                  : Quitte le terminal RIOT\n\n"
        f"[bold {acc}]Exemples d'ordres :[/bold {acc}]\n"
        "  • [italic]/theme tactical[/italic]\n"
        "  • [italic]/swarm Ajoute la gestion du stop-loss 1% dans le module de trading[/italic]\n"
        "  • [italic]« Génère une maquette visuelle de dashboard fintech en thème sombre »[/italic]"
    )
    console.print(Panel(aide, title=f"[bold {acc}]RIOT CLI · GUIDE DES COMMANDES[/bold {acc}]", border_style=acc, box=ROUNDED))


def commande_changer_projet(arg: str):
    """Change le répertoire projet actif de la session."""
    arg_clean = arg.strip().strip('"').strip("'")
    if not arg_clean:
        if _SESSION_CTX["projet_actif"]:
            console.print(f"[bold #e5c07b]Projet actif actuel :[/bold #e5c07b] {_SESSION_CTX['projet_actif']}")
        else:
            console.print("[bold #e5c07b]Mode actuel :[/bold #e5c07b] Discussion Libre (aucun projet fixé).")
        return

    if arg_clean.lower() in ("none", "libre", "reset", "aucun", "sans"):
        _SESSION_CTX["projet_actif"] = None
        console.print("[bold green]✓ Mode Discussion Libre activé (aucun projet ou dossier imposé).[/bold green]")
        return

    # Recherche dans le dossier projets configuré ou chemin direct
    racine = Path(arg_clean)
    if not racine.is_absolute():
        d_projets = dossier_projets()
        p_candidat = d_projets / arg_clean
        if p_candidat.exists():
            racine = p_candidat
        elif d_projets.exists():
            # Recherche partielle dans le dossier projets
            for d in d_projets.iterdir():
                if d.is_dir() and arg_clean.lower() in d.name.lower():
                    racine = d
                    break

    if racine.exists() and racine.is_dir():
        _SESSION_CTX["projet_actif"] = racine
        console.print(f"[bold green]✓ Projet actif basculé sur :[/bold green] [bold white]{racine.name}[/bold white] ({racine})")
    else:
        console.print(f"[bold red]❌ Impossible de trouver le dossier projet : {arg_clean}[/bold red]")


def commande_tokens():
    """Affiche la consommation de tokens."""
    prompt_t = _SESSION_CTX["tokens_prompt"]
    rep_t = _SESSION_CTX["tokens_reponse"]
    total = prompt_t + rep_t
    console.print(
        f"[bold #d97757]Session Tokens :[/bold #d97757] [cyan]Entrée: {prompt_t}[/cyan] │ "
        f"[green]Sortie: {rep_t}[/green] │ [bold white]Total: {total} tokens[/bold white]"
    )


def commande_memory(arg: str = ""):
    """Consulte, synchronise ou nettoie la mémoire persistante hybride (SQLite + Cloud)."""
    p = _pal()
    acc = p["cli_accent"]
    sub = (arg or "").strip()
    low = sub.lower()

    if low == "sync":
        with console.status(f"[bold {acc}]Synchronisation de la mémoire avec RIOT Cloud...[/bold {acc}]"):
            res = memoire.synchroniser_cloud()
        if res.get("ok"):
            console.print(
                f"[bold green]✓ Mémoire synchronisée[/bold green] "
                f"(envoyés: {res.get('envoyes', 0)}, reçus: {res.get('recus', 0)}, "
                f"appliqués: {res.get('appliques', 0)}, supprimés: {res.get('supprimes', 0)})\n"
            )
        else:
            detail = res.get("erreur") or res.get("raison") or "hors ligne"
            console.print(f"[yellow]Synchro Cloud ignorée ({detail}). Mémoire locale intacte.[/yellow]\n")
        return

    if low.startswith("forget "):
        sujet = sub[7:].strip()
        nb = memoire.oublier_par_motif(sujet)
        console.print(f"[bold green]✓ {nb} élément(s) oublié(s) pour '{sujet}'.[/bold green]\n")
        return

    etat = memoire.etat_synchro_cloud()
    m = memoire.charger()
    lignes = [
        f"[bold white]Base locale :[/bold white] {etat['db_path']}",
        f"[bold white]Cloud Sync :[/bold white] {'Actif (' + str(etat['gateway']) + ')' if etat['cloud_actif'] else 'Local uniquement (connecte-toi avec /login)'}",
        f"[bold white]Dernière synchro :[/bold white] {etat['derniere_synchro'] or 'jamais'}",
        f"[bold white]Volume :[/bold white] {etat['nb_entites']} entité(s) · {etat['nb_recettes']} recette(s) dev\n",
    ]
    for cat in ("preferences", "projects", "people", "regles_dev"):
        for k, v in (m.get(cat) or {}).items():
            lignes.append(f"• [{cat}] [cyan]{k}[/cyan] = {v}")
    for f_txt in (m.get("facts") or []):
        lignes.append(f"• [facts] {f_txt}")
    console.print(Panel("\n".join(lignes), title=f"[bold {acc}]MÉMOIRE LONG TERME RIOT[/bold {acc}]", border_style=acc, box=ROUNDED))


def _charger_conventions_projet(dossier: Optional[Path]) -> str:
    """Charge automatiquement les instructions et conventions du projet (Pilier 5)."""
    if not dossier:
        return ""
    fichiers_cibles = ["AGENTS.md", "INSTRUCTIONS.md", "CONVENTIONS.md", ".riot/conventions.md", "README.md"]
    for nom in fichiers_cibles:
        try:
            f = dossier / nom
            if f.exists() and f.is_file():
                with open(f, "r", encoding="utf-8", errors="replace") as stream:
                    contenu = stream.read(3000)
                return f"\n--- CONVENTIONS ET RÈGLES DU PROJET (chargées depuis {nom}) ---\n{contenu}\n--- FIN DES CONVENTIONS ---"
        except Exception:
            pass
    return ""


def _compacter_historique(historique: List[dict], max_messages: int = 12) -> List[dict]:
    """Compacte automatiquement l'historique quand la conversation s'allonge pour économiser le contexte (Pilier 5)."""
    if len(historique) <= max_messages:
        return historique

    # Conserver les 5 derniers messages intacts
    recents = historique[-5:]
    anciens = historique[:-5]

    points = []
    for m in anciens:
        role = m.get("role")
        c = m.get("content")
        if isinstance(c, str) and c.strip():
            resume_ligne = c.strip().splitlines()[0][:90]
            points.append(f"• [{role}] {resume_ligne}")
        elif isinstance(c, list):
            elements = []
            for item in c:
                if getattr(item, "type", None) == "tool_use":
                    elements.append(f"appel {getattr(item, 'name', '?')}")
                elif isinstance(item, dict) and item.get("type") == "tool_result":
                    l1 = str(item.get("content", "")).strip().splitlines()[0][:70] if str(item.get("content", "")).strip() else "OK"
                    elements.append(f"résultat: {l1}")
            if elements:
                points.append(f"• [{role}] " + " | ".join(elements[:4]))

    resume_text = (
        "[RÉSUMÉ DES ÉCHANGES PRÉCÉDENTS (Auto-Compaction)]\n" +
        "\n".join(points[-10:]) +
        "\n[Fin du résumé contextuel, poursuivre avec les messages récents]"
    )

    return [
        {"role": "user", "content": resume_text},
        {"role": "assistant", "content": "Bien reçu. Contexte compacté et mémorisé. Prêt pour la suite."},
    ] + recents


def executer_ordre(phrase: str, historique_conversation: List[dict]):
    """Exécute un ordre en boucle agentique avec design élégant RIOT CLI."""
    if not phrase.strip():
        return

    provider = llm()
    if not provider.disponible():
        console.print("[bold red]❌ Aucun fournisseur LLM n'est disponible. Vérifiez vos clés dans config.yaml.[/bold red]")
        return

    maintenant = datetime.now()
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    str_date = f"{jours[maintenant.weekday()]} {maintenant.day} {mois[maintenant.month - 1]} {maintenant.year} à {maintenant.strftime('%H:%M:%S')}"

    projet_actuel = _SESSION_CTX["projet_actif"]
    conventions_ctx = _charger_conventions_projet(projet_actuel)

    if projet_actuel:
        systeme = (
            "Tu es RIOT-Coder, un ingénieur logiciel d'élite, architecte système senior et copilote de programmation.\n"
            f"Tu es directement connecté à la machine locale de l'utilisateur sous Windows. Date réelle : {str_date}.\n"
            f"Projet actif actuel : {projet_actuel.name} (Chemin : {projet_actuel}).\n"
            "RÈGLES D'OR ABSOLUES :\n"
            "1. ZÉRO HALLUCINATION : Ne JAMAIS affirmer ou supposer le contenu d'un fichier ou d'un projet sans l'avoir d'abord inspecté "
            "avec les outils dédiés (explorer_projet, lire_code, chercher_dans_code, lister_dossier).\n"
            "2. CHIRURGIE ET PRÉCISION : Quand tu modifies du code, privilégie `patcher_code` pour modifier les fonctions nécessaires sans écraser tout le fichier. "
            "Pour créer un nouveau script, utilise `ecrire_code`.\n"
            "3. PROACTIF ET AGENTIQUE : Ne récite pas de cours théoriques de 10 points. Si l'utilisateur te demande d'analyser, d'optimiser ou de corriger, "
            "utilise tes outils pour inspecter et agir directement.\n"
            "4. ANTI-HALLUCINATION WEB : Pour toute information récente, actualité, version de librairie, documentation externe ou fait incertain, "
            "appelle `chercher_web` (et `lire_page_web` pour vérifier une source) avant de répondre, puis cite les URLs sources.\n"
            "5. STYLE CONCIS & TECHNIQUE : Reste percutant, professionnel, orienté action. Présente les diffs et chemins clairement. Pas de bavardage superflu."
            f"{conventions_ctx}"
        )
    else:
        systeme = (
            "Tu es RIOT, un assistant d'élite, ingénieur de pointe et partenaire de réflexion.\n"
            f"Tu es connecté sur la machine locale de l'utilisateur sous Windows. Date réelle : {str_date}.\n"
            "Mode : DISCUSSION LIBRE (aucun projet ou dossier spécifique imposé).\n"
            "RÈGLES D'OR ABSOLUES :\n"
            "1. Réponds librement, précisément et directement à toutes les questions, réflexions ou analyses de l'utilisateur.\n"
            "2. N'appelle d'outils de fichiers que si l'utilisateur te demande expressément d'explorer ou de manipuler des fichiers.\n"
            "3. STYLE CONCIS, ÉLÉGANT & PERCUTANT : Reste bienveillant, critique et constructif. Pas de bavardage superflu.\n"
            "4. ANTI-HALLUCINATION WEB : Pour toute actualité, donnée récente, prix, documentation externe ou fait incertain, appelle obligatoirement "
            "`chercher_web` (et `lire_page_web` si besoin) au lieu d'inventer, et cite les sources.\n"
            "5. CONTRÔLE SYSTÈME & NAVIGATEUR : Si l'utilisateur demande d'ouvrir une application (`ouvrir_application`), régler le volume (`regler_volume`), contrôler les médias (`controler_media`), verrouiller la session (`verrouiller_pc`), voir l'écran (`capture_screen`) ou piloter Google Chrome (`browser_open`, `browser_click`, `browser_type`, `browser_scroll`), appelle directement l'outil adapté."
        )

    texte_mem = memoire.texte_pour_systeme()[:2500]
    if texte_mem:
        systeme += f"\n{texte_mem}"
    recettes_ctx = memoire.recup_recettes_pertinentes(phrase)
    if recettes_ctx:
        systeme += f"\n{recettes_ctx}"
    try:
        from tools.grill_me import consigne_grill_me
        systeme += consigne_grill_me(bool(_SESSION_CTX.get("grill_me", False)))
    except Exception:
        pass

    # Auto-compaction si l'historique devient trop long (Pilier 5)
    historique_conversation[:] = _compacter_historique(historique_conversation, max_messages=12)

    historique_conversation.append({"role": "user", "content": phrase})
    auth.audit("CLI_ORDRE", "localhost", phrase)

    try:
        from tools.code import extraire_et_ancrer_dossier_texte, _projet_actif_courant
        extraire_et_ancrer_dossier_texte(phrase)
        proj_anc = _projet_actif_courant()
        if proj_anc:
            systeme += f"\n\n[PROJET ACTIF ANCRÉ : {proj_anc}] (utilise ce dossier comme cwd/racine par défaut)."
    except Exception:
        proj_anc = None

    dossier_mentor = projet_actuel or proj_anc or Path.cwd()
    directives_mentor = None
    mentor_actif_tour = False
    try:
        from core import mentor as mentor_mod
        if mentor_mod.mentor_est_actif():
            mentor_actif_tour = True
            with console.status("[bold cyan]🎓 Cadrage Mentor Antigravity...[/bold cyan]", spinner="dots"):
                directives_mentor = mentor_mod.preparer_directives_mentor(phrase, dossier_mentor)
            bloc_m = mentor_mod.formater_directives_pour_prompt(directives_mentor)
            if bloc_m:
                systeme += bloc_m
                console.print("[dim]🎓 Mentor : directives & interdits injectés dans RIOT.[/dim]")
    except Exception:
        mentor_actif_tour = False

    # Récupération et filtrage des schémas d'outils
    tous_schemas = registre.schemas_api(
        local_seulement=(provider.nom == "Ollama"),
        requete=phrase,
    )
    if _SESSION_CTX["mode_code"]:
        outils_code_cibles = {
            "explorer_projet", "lire_code", "ecrire_code", "patcher_code",
            "chercher_dans_code", "executer_test_ou_commande", "executer_terminal",
            "inspecter_port", "lister_dossier", "chercher_fichiers", "ouvrir_fichier", "supprimer_fichier", "ouvrir_terminal_interactif",
            "grill-me", "content-strategy", "anti-ai-slop", "seo-audit",
            "git_status", "git_diff", "git_log", "requete_api_http", "github_repo_info",
            "lister_connecteurs_mcp", "installer_connecteur_mcp", "basculer_connecteur_mcp",
            "remember", "recall", "forget", "apprendre_regle", "lister_regles",
            "enregistrer_recette_dev", "chercher_recette_dev",
            "trade_app_statut", "trade_app_prix_crypto", "trade_app_demarrer_service",
            "trading_analyse_technique", "trading_calculateur_risque", "trading_carnet_ordres_express",
            "analyser_espace_stockage", "nettoyer_caches_temporaires",
            "generer_pdf", "extraire_texte_pdf", "fusionner_pdfs",
            "generer_excel", "lire_excel", "generer_powerpoint", "lire_powerpoint",
            "generer_graphique", "generer_diagramme", "creer_produit_digital",
            "auditer_schema_sql", "optimiser_requete_postgis", "generer_politiques_rls",
            "generer_composant_mobile", "scaffolder_app_mobile_expo",
            "surveiller_marche_crypto", "chercher_web", "lire_page_web", "recueillir_veille_web", "generer_bulletin_veille",
            "lister_competences", "charger_competence", "lire_reference",
            "capturer_page", "capturer_frames",
            "generer_image", "lister_images_generees",
            "lancer_navigateur_chrome", "browser_open", "browser_current_page",
            "browser_tabs", "browser_close_tabs", "browser_interact",
            "browser_click", "browser_type", "browser_scroll",
            "ouvrir_application", "controler_media", "regler_volume",
            "verrouiller_pc", "eteindre_pc", "capture_screen"
        }
        schemas = [s for s in tous_schemas if (s.get("name") in outils_code_cibles or str(s.get("name", "")).startswith("mcp_"))]
    else:
        schemas = tous_schemas

    from core.model_router import JournalContinuite
    p = _pal()
    acc = p["cli_accent"]
    compteur_appels = {}
    journal = JournalContinuite(phrase, dossier=str(projet_actuel or ""))
    for tour in range(10):
        t0 = time.time()
        bloc_cont = journal.rendre_bloc()
        systeme_tour = f"{systeme}{bloc_cont}" if bloc_cont else systeme
        try:
            with console.status(f"[bold {acc}]⠋ Réflexion en cours...[/bold {acc}]", spinner="dots"):
                rep = provider.repondre(systeme_tour, historique_conversation, schemas)
        except Exception as e:
            console.print(f"[bold red]❌ Erreur LLM : {e}[/bold red]")
            return

        dt = round(time.time() - t0, 2)

        # Vérifier si l'outil est requis
        if getattr(rep, "stop_reason", None) != "tool_use":
            texte = " ".join(b.text for b in rep.content if getattr(b, "type", None) == "text").strip()
            reponse_finale = texte or "Action terminée avec succès."
            resume_cont = journal.resume_court()
            contenu_hist = f"{reponse_finale}\n{resume_cont}" if resume_cont else reponse_finale
            historique_conversation.append({"role": "assistant", "content": contenu_hist})

            # Affichage RIOT CLI : minimaliste, aéré, élégant
            console.print()
            console.print(Markdown(reponse_finale))
            console.print(f"[dim]  ⚡ {provider.nom} · {dt}s[/dim]\n")
            memoire.lancer_auto_memoire_asynchrone(phrase, reponse_finale, surface="cli")
            if mentor_actif_tour:
                try:
                    from core import mentor as mentor_mod
                    with console.status("[bold cyan]🎓 Audit & apprentissage Mentor Antigravity...[/bold cyan]", spinner="dots"):
                        verdict = mentor_mod.auditer_et_distiller(phrase, dossier_mentor, reponse_finale, directives=directives_mentor)
                    if verdict:
                        console.print(f"[dim]🎓 Mentor [{verdict.verdict}] : {verdict.resume[:160]} (+{len(verdict.lecons)} leçons)[/dim]\n")
                except Exception:
                    pass
            return

        # Appel d'outils requis
        historique_conversation.append({"role": "assistant", "content": rep.content})
        resultats_du_tour = []

        for b in rep.content:
            if getattr(b, "type", None) != "tool_use":
                continue

            nom_outil = b.name
            args = b.input or {}
            outil = registre.get(nom_outil)
            try:
                empreinte_appel = f"{nom_outil}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
            except Exception:
                empreinte_appel = f"{nom_outil}:{args}"
            compteur_appels[empreinte_appel] = compteur_appels.get(empreinte_appel, 0) + 1

            # Style visuel RIOT CLI pour l'exécution d'outils
            arg_str = ", ".join(f"{k}='{str(v)[:50]}'" for k, v in args.items())
            console.print(f"[bold {acc}]● Executing[/bold {acc}] [bold white]{nom_outil}[/bold white]([dim]{arg_str}[/dim])...")

            t_outil = time.time()
            if compteur_appels[empreinte_appel] > 2:
                res = (
                    f"[BOUCLE STOPPÉE] `{nom_outil}` a déjà été appelé {compteur_appels[empreinte_appel] - 1} fois "
                    "avec exactement les mêmes arguments. Change d'outil (ex. `executer_terminal` pour un outil CLI "
                    "comme `ffmpeg` ou `remotion`) ou réponds directement à l'utilisateur."
                )
            else:
                try:
                    res = outil.fonction(**args) if outil else f"[ERREUR] Outil inconnu : {nom_outil}"
                except Exception as e:
                    res = f"[ERREUR] Échec de l'outil {nom_outil} : {e}"

            dt_outil = round(time.time() - t_outil, 2)
            journal.enregistrer_appel(nom_outil, args, str(res))
            
            # Affichage du résultat résumé
            premiere_ligne = str(res).strip().splitlines()[0] if str(res).strip() else "OK"
            if "[ERREUR]" in str(res):
                console.print(f"  [bold red]✕[/bold red] [red]{premiere_ligne[:90]}[/red] [dim]({dt_outil}s)[/dim]")
            else:
                console.print(f"  [bold green]✓[/bold green] [dim]{premiere_ligne[:90]} ({dt_outil}s)[/dim]")

            resultats_du_tour.append({
                "type": "tool_result",
                "tool_use_id": getattr(b, "id", f"call_{nom_outil}"),
                "content": str(res),
            })

        if resultats_du_tour:
            historique_conversation.append({
                "role": "user",
                "content": resultats_du_tour,
            })

    # Synthese finale garantie si les 10 tours d'outils ont ete consommes
    try:
        t_fin = time.time()
        with console.status(f"[bold {acc}]⠋ Synthèse finale...[/bold {acc}]", spinner="dots"):
            rep_fin = provider.repondre(systeme, historique_conversation, [])
        texte_fin = " ".join(b.text for b in rep_fin.content if getattr(b, "type", None) == "text").strip()
        reponse_finale = texte_fin or "Actions exécutées. Vérifiez les résultats ci-dessus."
        historique_conversation.append({"role": "assistant", "content": reponse_finale})
        console.print()
        console.print(Markdown(reponse_finale))
        console.print(f"[dim]  ⚡ {provider.nom} · {round(time.time() - t_fin, 2)}s[/dim]\n")
        memoire.lancer_auto_memoire_asynchrone(phrase, reponse_finale, surface="cli")
        if mentor_actif_tour:
            try:
                from core import mentor as mentor_mod
                with console.status("[bold cyan]🎓 Audit & apprentissage Mentor Antigravity...[/bold cyan]", spinner="dots"):
                    verdict = mentor_mod.auditer_et_distiller(phrase, dossier_mentor, reponse_finale, directives=directives_mentor)
                if verdict:
                    console.print(f"[dim]🎓 Mentor [{verdict.verdict}] : {verdict.resume[:160]} (+{len(verdict.lecons)} leçons)[/dim]\n")
            except Exception:
                pass
    except Exception:
        pass


def _verifier_configuration_initiale():
    """Assistant d'onboarding rapide : connexion obligatoire par jeton pour les clients finaux."""
    from core import llm as llm_mod
    if llm().disponible():
        return
    if not llm_mod.est_createur():
        p = _pal()
        console.print(Panel(
            f"[bold {p['cli_accent']}]Connexion RIOT Engine requise[/bold {p['cli_accent']}]\n"
            "Crée ton compte et ton jeton CLI sur : [bold white]https://riot-portal.vercel.app/account[/bold white]\n"
            "[dim]Colle ton jeton `riot_cli_...` ci-dessous (ou tape `/login` plus tard).[/dim]",
            border_style=p["cli_accent"],
            box=ROUNDED,
        ))
        if sys.stdin and sys.stdin.isatty():
            commande_login("")
        return
    p = _pal()
    console.print(Panel(
        f"[bold {p['cli_warn']}]Premiere configuration de RIOT sur cette machine[/bold {p['cli_warn']}]\n"
        f"[dim]Fichier cible : {config.FICHIER}[/dim]\n"
        "Fournisseurs supportes : [bold]groq[/bold], [bold]mistral[/bold], [bold]gemini[/bold], [bold]openrouter[/bold], [bold]custom[/bold] (FreeLLMAPI), [bold]anthropic[/bold], [bold]local[/bold]",
        border_style=p["cli_accent"],
        box=ROUNDED,
    ))
    try:
        mode = input("Fournisseur par defaut [groq] : ").strip().lower() or "groq"
        if mode not in ("groq", "mistral", "gemini", "openrouter", "custom", "freellmapi", "anthropic", "local"):
            mode = "groq"
        if mode == "freellmapi":
            mode = "custom"
        config.definir("mode", mode)
        if mode == "custom":
            url = input("URL base OpenAI (ex: http://127.0.0.1:31415/v1 ou :3001/v1) : ").strip()
            if url:
                config.definir("custom.base_url", url)
            mod = input("Modele cible [auto] : ").strip() or "auto"
            config.definir("custom.modele", mod)
        if mode != "local":
            cle = input(f"Cle API {mode} (Entree pour passer) : ").strip()
            if cle:
                config.definir(f"{mode}.cle", cle)
        llm_mod.reinitialiser()
        console.print("[bold green]✓ Configuration enregistree.[/bold green]\n")
    except (KeyboardInterrupt, EOFError):
        console.print()


def lancer_terminal_interactif():
    """Boucle principale du Terminal RIOT inspirée de RIOT CLI."""
    _verifier_configuration_initiale()
    afficher_banniere_riot()

    # Vérification non-bloquante des mises à jour (cache 24h)
    try:
        from core import updater
        etat_cache = updater.etat_mise_a_jour(forcer=False, sans_reseau=True)
        if etat_cache.get("disponible"):
            console.print(f"  [bold {_pal()['cli_warn']}]↑ {etat_cache['details']}[/bold {_pal()['cli_warn']}] — tape [bold white]/update[/bold white]")
        else:
            updater.lancer_verification_arriere_plan()
    except Exception:
        pass

    # Démarrage automatique en tâche de fond du serveur Web et du tunnel
    from core import serveur, tunnel
    try:
        serveur.demarrer_arriere_plan()
        tunnel.demarrer_arriere_plan()
    except Exception:
        pass

    # Initialisation des connexions MCP en arrière-plan
    try:
        from core import mcp_client
        mcp_client.initialiser_connexions_mcp()
    except Exception:
        pass
    memoire.lancer_synchro_arriere_plan()

    completer = WordCompleter(_COMMANDES_INTERNES, ignore_case=True)
    session = PromptSession(
        history=FileHistory(str(_HISTORIQUE_FICHIER)),
        completer=completer,
        style=_STYLE_PROMPT,
    )

    historique_conv = []

    while True:
        try:
            projet = _SESSION_CTX["projet_actif"].name if _SESSION_CTX["projet_actif"] else "libre"
            invite = [
                ("class:prompt-brand", "riot"),
                ("class:prompt-project", f" ({projet})"),
                ("class:prompt-arrow", " ❯ "),
            ]

            texte = session.prompt(invite, style=_style_prompt_courant()).strip()
            if not texte:
                continue

            cmd = texte.lower()
            if cmd in ("/exit", "/quit", "/q"):
                console.print(f"[bold {_pal()['cli_accent']}]Session RIOT terminée. Bon code ![/bold {_pal()['cli_accent']}]\n")
                break
            elif cmd in ("/clear", "/cls"):
                os.system("cls" if os.name == "nt" else "clear")
                afficher_banniere_riot()
                continue
            elif cmd.startswith("/theme"):
                parties = texte.split(maxsplit=1)
                arg_th = parties[1] if len(parties) > 1 else ""
                commande_theme(arg_th)
                continue
            elif cmd.startswith("/login"):
                parties = texte.split(maxsplit=1)
                arg_log = parties[1] if len(parties) > 1 else ""
                commande_login(arg_log)
                continue
            elif cmd in ("/logout", "/deconnexion"):
                commande_logout()
                continue
            elif cmd.startswith("/update"):
                parties = texte.split(maxsplit=1)
                arg_up = parties[1] if len(parties) > 1 else ""
                commande_update(arg_up)
                continue
            elif cmd.startswith("/keys") or cmd.startswith("/quota"):
                parties = texte.split(maxsplit=1)
                arg_kq = parties[1] if len(parties) > 1 else ""
                commande_keys(arg_kq)
                continue
            elif cmd.startswith("/memory") or cmd.startswith("/mem") or cmd.startswith("/memoire"):
                parties = texte.split(maxsplit=1)
                arg_mem = parties[1] if len(parties) > 1 else ""
                commande_memory(arg_mem)
                continue
            elif cmd.startswith("/grill-me") or cmd.startswith("/grill"):
                parties = texte.split(maxsplit=1)
                arg_gm = parties[1].strip() if len(parties) > 1 else ""
                low_gm = arg_gm.lower()
                if not arg_gm:
                    _SESSION_CTX["grill_me"] = not _SESSION_CTX.get("grill_me", False)
                    etat_gm = "ACTIVÉ (questions avant action sur chaque nouveau prompt)" if _SESSION_CTX["grill_me"] else "DÉSACTIVÉ"
                    console.print(f"[bold green]✓ Mode grill-me {etat_gm}.[/bold green]\n")
                elif low_gm in ("on", "true", "1", "activer"):
                    _SESSION_CTX["grill_me"] = True
                    console.print("[bold green]✓ Mode grill-me ACTIVÉ : RIOT posera des questions de clarification avant d'agir.[/bold green]\n")
                elif low_gm in ("off", "false", "0", "desactiver"):
                    _SESSION_CTX["grill_me"] = False
                    console.print("[bold yellow]✓ Mode grill-me DÉSACTIVÉ.[/bold yellow]\n")
                else:
                    prev_gm = _SESSION_CTX.get("grill_me", False)
                    _SESSION_CTX["grill_me"] = True
                    try:
                        executer_ordre(arg_gm, historique_conv)
                    finally:
                        _SESSION_CTX["grill_me"] = prev_gm
                continue
            elif cmd in ("/ide", "/editeur"):
                from core import serveur, studio_app
                import webbrowser
                serveur.demarrer()
                url_ide = "http://localhost:8790/ide"
                try:
                    webbrowser.open(url_ide)
                except Exception:
                    pass
                console.print(f"  [bold {_pal()['cli_accent']}]⚡ RIOT IDE ouvert :[/bold {_pal()['cli_accent']}] [bold white]{url_ide}[/bold white]")
                continue
            elif cmd.startswith("/mcp"):
                parties = texte.split(maxsplit=1)
                arg_mcp = parties[1] if len(parties) > 1 else ""
                commande_mcp(arg_mcp)
                continue
            elif cmd.startswith("/mentor"):
                from core import mentor as mentor_mod
                parties = texte.split(maxsplit=1)
                sub = parties[1].strip().lower() if len(parties) > 1 else "status"
                if sub in ("on", "activer", "1"):
                    st_m = mentor_mod.basculer_mentor(True)
                    if st_m["auth_disponible"]:
                        console.print(f"[bold green]✓ Mentor Antigravity ACTIVÉ[/bold green] [dim](backend={st_m['backend']}, agy={st_m['agy_disponible']}, sdk={st_m['sdk_disponible']})[/dim]\n")
                    else:
                        console.print("[bold yellow]⚠ Mentor activé mais aucun backend Antigravity détecté.[/bold yellow] [dim]Connectez `agy` (Antigravity IDE / Google AI Pro) ou configurez `GEMINI_API_KEY`.[/dim]\n")
                elif sub in ("off", "desactiver", "0"):
                    mentor_mod.basculer_mentor(False)
                    console.print("[bold yellow]✓ Mentor Antigravity DÉSACTIVÉ.[/bold yellow]\n")
                elif sub == "prune":
                    nb = memoire.purger_lecons_obsoletes()
                    console.print(f"[bold cyan]✓ {nb} leçon(s) obsolète(s) archivée(s).[/bold cyan]\n")
                elif sub == "export":
                    res_exp = memoire.exporter_playbook_public()
                    console.print(f"[bold green]✓ Playbook public exporté :[/bold green] {res_exp['fichier']} ({res_exp['exportees']} leçon(s))\n")
                else:
                    st_m = mentor_mod.statut_mentor()
                    mem_st = st_m["memoire"]
                    console.print(
                        f"[bold cyan]🎓 Mentor Antigravity[/bold cyan] · actif=[bold]{st_m['actif']}[/bold] · "
                        f"backend={st_m['backend']} (agy={st_m['agy_disponible']}, sdk={st_m['sdk_disponible']}) · "
                        f"Actives={mem_st['actives']} · Archivées={mem_st['archivees']} · Confiance moy={mem_st['confiance_moyenne']}\n"
                        "[dim]Usage : /mentor on | /mentor off | /mentor prune | /mentor export[/dim]\n"
                    )
                continue
            elif cmd in ("/app", "/studio"):
                from core import serveur, studio_app
                serveur.demarrer()
                studio_app.lancer_app_desktop()
                console.print(f"  [bold {_pal()['cli_accent']}]⚡ Application RIOT Studio ouverte en fenêtre de bureau.[/bold {_pal()['cli_accent']}]")
                console.print(f"  [dim]Accès Web : http://localhost:8790/ (Studio) · http://localhost:8790/mobile[/dim]")
                continue
            elif cmd.startswith("/raw") or cmd.startswith("/uncensored"):
                from core import agents
                parties = texte.split(maxsplit=1)
                mission = parties[1].strip() if len(parties) > 1 else "Présente-toi et démontre ta neutralité absolue et ton absence totale de censure."
                agents.executer_raw(mission, console, _SESSION_CTX["projet_actif"])
                continue
            elif cmd.startswith("/trade") or cmd.startswith("/trader"):
                from core import agents
                parties = texte.split(maxsplit=1)
                mission = parties[1].strip() if len(parties) > 1 else "Analyse le marché Bitcoin (BTCUSDT) et calcule un plan de risk management 1%."
                agents.executer_trader(mission, console, _SESSION_CTX["projet_actif"])
                continue
            elif cmd.startswith("/swarm") or cmd.startswith("/pipeline"):
                from core import agents
                parties = texte.split(maxsplit=1)
                mission = parties[1].strip() if len(parties) > 1 else ""
                if not mission:
                    console.print("[bold yellow]Usage : /swarm <description de la tâche à accomplir>[/bold yellow]")
                    console.print("[dim]Exemple : /swarm Ajoute un test unitaire pour la route /health[/dim]")
                else:
                    agents.executer_pipeline_dev(mission, _SESSION_CTX["projet_actif"], console)
                continue
            elif cmd.startswith("/architect"):
                from core import agents
                parties = texte.split(maxsplit=1)
                mission = parties[1].strip() if len(parties) > 1 else "Analyse l'architecture du projet et propose les améliorations prioritaires."
                agents.executer_architecte(mission, _SESSION_CTX["projet_actif"], console)
                continue
            elif cmd.startswith("/engineer"):
                from core import agents
                parties = texte.split(maxsplit=1)
                mission = parties[1].strip() if len(parties) > 1 else ""
                if not mission:
                    console.print("[bold yellow]Usage : /engineer <code ou modification à implémenter>[/bold yellow]")
                else:
                    agents.executer_ingenieur(mission, _SESSION_CTX["projet_actif"], console)
                continue
            elif cmd.startswith("/test") or cmd.startswith("/tester"):
                from core import agents
                parties = texte.split(maxsplit=1)
                mission = parties[1].strip() if len(parties) > 1 else "Exécute les tests du projet et vérifie qu'il n'y a aucune régression."
                agents.executer_testeur(mission, _SESSION_CTX["projet_actif"], console)
                continue
            elif cmd.startswith("/review") or cmd.startswith("/reviewer"):
                from core import agents
                parties = texte.split(maxsplit=1)
                mission = parties[1].strip() if len(parties) > 1 else "Effectue un audit de sécurité et de conformité du projet actif."
                agents.executer_reviewer(mission, _SESSION_CTX["projet_actif"], console)
                continue
            elif cmd.startswith("/file") or cmd.startswith("/fichier"):
                parties = texte.split(maxsplit=2)
                if len(parties) < 2:
                    console.print("[bold yellow]Usage : /file <chemin_fichier> [question ou consigne optionnelle][/bold yellow]")
                    console.print("[dim]Exemple : /file core/agents.py explique cette logique[/dim]")
                    continue
                chemin_str = parties[1].strip()
                question = parties[2].strip() if len(parties) > 2 else "Analyse ce fichier et explique son contenu en détail."
                p_cible = Path(chemin_str)
                if not p_cible.is_absolute():
                    base_dir = _SESSION_CTX["projet_actif"] or Path.cwd()
                    p_cible = (base_dir / chemin_str).resolve()
                    if not p_cible.exists():
                        p_cible = (_RACINE / chemin_str).resolve()
                if not p_cible.exists() or not p_cible.is_file():
                    console.print(f"[bold red]✕ Fichier introuvable : {chemin_str}[/bold red]")
                    continue
                try:
                    contenu = p_cible.read_text(encoding="utf-8", errors="replace")
                    prompt_enrichi = (
                        f"=== 📄 FICHIER FOURNI : {p_cible.name} ({p_cible}) ===\n"
                        f"```{p_cible.suffix.lstrip('.')}\n{contenu}\n```\n"
                        f"=== FIN DU FICHIER ===\n\n"
                        f"Consigne de l'utilisateur :\n{question}"
                    )
                    console.print(f"  [dim]Fichier joint : [bold {_pal()['cli_warn']}]{p_cible.name}[/bold {_pal()['cli_warn']}] ({len(contenu.splitlines())} lignes)[/dim]")
                    executer_ordre(prompt_enrichi, [])
                except Exception as e:
                    console.print(f"[bold red]✕ Erreur lecture fichier : {e}[/bold red]")
                continue
            elif cmd.startswith("/project") or cmd.startswith("/projet"):
                parties = texte.split(maxsplit=1)
                arg = parties[1] if len(parties) > 1 else ""
                commande_changer_projet(arg)
                continue
            elif cmd in ("/code", "/coder", "/dev"):
                _SESSION_CTX["mode_code"] = not _SESSION_CTX["mode_code"]
                statut = "ACTIVÉ (Focus ingénierie logicielle)" if _SESSION_CTX["mode_code"] else "DÉSACTIVÉ (Mode généraliste)"
                console.print(f"[bold {_pal()['cli_accent']}]⚡ Mode Sous-Agent Coder :[/bold {_pal()['cli_accent']}] [bold white]{statut}[/bold white]")
                continue
            elif cmd in ("/pc", "/status", "/system"):
                import psutil
                cpu = psutil.cpu_percent(interval=0.2)
                vm = psutil.virtual_memory()
                racine_disque = "C:\\" if sys.platform == "win32" else "/"
                disk_main = psutil.disk_usage(racine_disque) if Path(racine_disque).exists() else None
                disk_e = psutil.disk_usage("E:\\") if Path("E:\\").exists() else None
                msg_disques = f" │ Disque : [green]{round(disk_main.free/1024**3,1)} Go lib.[/green]" if disk_main else ""
                if disk_e:
                    msg_disques += f" │ E: [green]{round(disk_e.free/1024**3,1)} Go lib.[/green]"
                console.print(f"  [bold {_pal()['cli_accent']}]Système :[/bold {_pal()['cli_accent']}] CPU [green]{cpu}%[/green] │ RAM [green]{vm.percent}%[/green] ({round(vm.available/1024**3,1)} Go lib.){msg_disques}")
                continue
            elif cmd in ("/tools", "/outils"):
                commande_outils()
                continue
            elif cmd in ("/tokens", "/cost"):
                commande_tokens()
                continue
            elif cmd in ("/remote", "/mobile", "/tunnel"):
                from core import tunnel
                st = tunnel.statut_tunnel()
                console.print(f"  📱 [bold white]Local :[/bold white] http://localhost:8790/mobile")
                console.print(f"  🌐 [bold white]Distant :[/bold white] {st.get('url_publique') or 'En cours ou local seul'}")
                continue
            elif cmd.startswith("/model") or cmd.startswith("/fournisseur"):
                from core import llm as llm_mod
                parties = texte.split(maxsplit=1)
                provider = llm()
                if not llm_mod.est_createur():
                    if len(parties) > 1:
                        pub = llm_mod.definir_profil_public(parties[1].strip())
                        console.print(f"  [bold {_pal()['cli_accent']}]✓ Profil RIOT actif :[/bold {_pal()['cli_accent']}] [bold white]{pub['modele']}[/bold white] ({pub['nom']})")
                    else:
                        pub = llm_mod.identite_publique(provider)
                        console.print(f"  ⚡ Moteur actif : [bold {_pal()['cli_warn']}]{pub['modele']}[/bold {_pal()['cli_warn']}] ({pub['nom']})")
                        console.print("  [dim]Profils disponibles : auto · fast · code · deep[/dim]")
                    continue

                fournisseurs_ok = ("groq", "mistral", "gemini", "openrouter", "custom", "freellmapi", "anthropic", "local")
                if len(parties) > 1:
                    cible = parties[1].strip()
                    cible_low = cible.lower()
                    if cible_low in fournisseurs_ok:
                        mode_final = "custom" if cible_low == "freellmapi" else cible_low
                        config.definir("mode", mode_final)
                        llm_mod.reinitialiser()
                        nouveau_prov = llm()
                        console.print(f"  [bold {_pal()['cli_accent']}]✓ Fournisseur actif :[/bold {_pal()['cli_accent']}] [bold white]{nouveau_prov.nom}[/bold white] ({getattr(nouveau_prov, 'modele', '-')})")
                    else:
                        sec = "ollama" if getattr(provider, "nom", "").lower() == "ollama" else reglage("mode", "mistral")
                        if sec == "freellmapi":
                            sec = "custom"
                        config.definir(f"{sec}.modele", cible)
                        llm_mod.reinitialiser()
                        nouveau_prov = llm()
                        console.print(f"  [bold {_pal()['cli_accent']}]✓ Modèle basculé :[/bold {_pal()['cli_accent']}] [bold white]{getattr(nouveau_prov, 'modele', cible)}[/bold white] ({nouveau_prov.nom})")
                else:
                    console.print(f"  ⚡ Modèle actuel : [bold {_pal()['cli_warn']}]{getattr(provider, 'modele', '-')}[/bold {_pal()['cli_warn']}] ({provider.nom})")
                    console.print("  [dim]Fournisseurs : groq · mistral · gemini · openrouter · custom (FreeLLMAPI) · anthropic · local[/dim]")
                continue
            elif cmd in ("/help", "/aide"):
                commande_aide()
                continue

            # Exécution de l'ordre
            executer_ordre(texte, historique_conv)

        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[bold {_pal()['cli_accent']}]Fermeture du terminal RIOT.[/bold {_pal()['cli_accent']}]")
            break
        except Exception as e:
            console.print(f"[bold red]Erreur inattendue : {e}[/bold red]")


def main():
    """Point d'entrée console de RIOT CLI."""
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        ordre_unique = " ".join(sys.argv[1:])
        if not registre.tous():
            registre.charger_outils()
        executer_ordre(ordre_unique, [])
    else:
        lancer_terminal_interactif()


if __name__ == "__main__":
    main()
