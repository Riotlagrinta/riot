"""Terminal RIOT : Interface CLI inspirée du design épuré et moderne de Claude Code.

Conçu pour les développeurs :
- Palette de couleurs terracotta/anthracite (#d97757, #282c34, #abb2bf)
- En-tête statut compact avec projet actif et branche git
- Invite de commande interactive 'riot ❯' avec historique et auto-complétion
- Rendu des appels d'outils style Claude Code (bullet tree, timing, diffs)
- Mode Sous-Agent Coder (/code) spécialisé ingénierie logicielle
"""
import os
import sys
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

from core import auth, budget, config, etude, memoire, registre
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

# Couleurs inspirées de Claude Code
CLAUDE_CORAL = "#d97757"
CLAUDE_DIM = "#7f848e"
CLAUDE_GREEN = "#98c379"
CLAUDE_CYAN = "#56b6c2"
CLAUDE_GOLD = "#e5c07b"
CLAUDE_WHITE = "#e6edf3"
CLAUDE_RED = "#e06c75"
CLAUDE_BG = "#1e1e1e"

# Style de l'invite prompt_toolkit
_STYLE_PROMPT = PromptStyle.from_dict({
    "prompt-brand": "#d97757 bold",
    "prompt-project": "#e5c07b",
    "prompt-arrow": "#d97757 bold",
})

_COMMANDES_INTERNES = [
    "/mcp",
    "/app", "/claude",
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
    "/recettes",
    "/clear", "/cls",
    "/help", "/aide",
    "/exit", "/quit", "/q",
]

# État global de la session CLI (Mode Discussion Libre sans projet forcé par défaut)
_SESSION_CTX = {
    "projet_actif": None,
    "mode_code": True,
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


def afficher_banniere_claude():
    """Affiche l'en-tête épuré et moderne façon Claude Code."""
    import psutil

    if not registre.tous():
        registre.charger_outils()

    provider = llm()
    nom_modele = getattr(provider, "modele", "-")
    fournisseur_nom = provider.nom

    projet = _SESSION_CTX["projet_actif"]
    branche = _recup_branche_git(projet)
    branche_str = f" │ [italic cyan]{branche}[/italic cyan]" if branche else ""

    vm = psutil.virtual_memory()
    ram_str = f"{round(vm.used / (1024 ** 3), 1)}/{round(vm.total / (1024 ** 3), 1)} Go"

    # Context window estimate
    ctx_taille = "32k" if "codestral" in nom_modele.lower() else ("128k" if "llama" in nom_modele.lower() or "groq" in fournisseur_nom.lower() else "1M")

    mode_label = "[bold #d97757]⚡ RIOT Coder v2.0[/bold #d97757]" if _SESSION_CTX["mode_code"] else "[bold cyan]⚡ RIOT Copilot v2.0[/bold cyan]"

    ligne1 = f"  {mode_label}  [dim]•[/dim]  Modèle: [bold white]{nom_modele}[/bold white] ({fournisseur_nom})  [dim]•[/dim]  Contexte: [yellow]{ctx_taille}[/yellow]"
    if projet:
        ligne2 = f"  📁 Projet : [bold #e5c07b]{projet.name}[/bold #e5c07b] ([dim]{projet}[/dim]){branche_str}  [dim]•[/dim]  RAM: [green]{ram_str}[/green]"
    else:
        ligne2 = f"  💬 Mode : [bold #e5c07b]Discussion Libre[/bold #e5c07b] (Aucun projet/dossier fixé)  [dim]•[/dim]  RAM: [green]{ram_str}[/green]"

    console.print()
    console.print(Panel(
        f"{ligne1}\n{ligne2}",
        border_style="#d97757",
        box=ROUNDED,
        padding=(0, 1),
    ))
    console.print("[dim]  Astuce : Tapez votre ordre en français ou [bold white]/help[/bold white] pour la liste des raccourcis.[/dim]")
    console.print()


def commande_outils():
    """Affiche la liste catégorisée des outils disponibles sans erreur d'attribut."""
    outils = registre.tous()
    table = Table(title=f"🛠️ Boîte à Outils RIOT ({len(outils)} disponibles)", border_style="#d97757", box=ROUNDED)
    table.add_column("Nom Outil", style="bold #e5c07b")
    table.add_column("Module", style="dim cyan")
    table.add_column("Description", style="white")

    for o in sorted(outils, key=lambda x: x.nom)[:40]:
        module_nom = getattr(o.fonction, "__module__", "tools").replace("tools.", "")
        desc = (o.description or "").split("\n")[0][:75]
        table.add_row(o.nom, module_nom, desc)

    console.print(table)
    if len(outils) > 40:
        console.print(f"[dim](... et {len(outils) - 40} autres outils spécialisés disponibles automatiquement)[/dim]\n")


def commande_mcp(arg: str = ""):
    """Gère l'affichage et le rechargement des connexions Model Context Protocol (MCP)."""
    from core import mcp_client
    arg_clean = arg.strip().lower()

    if not mcp_client._STATUTS_SERVEURS or arg_clean in ("reload", "refresh", "r"):
        with console.status(f"[bold {CLAUDE_CORAL}]Connexion aux serveurs MCP...[/bold {CLAUDE_CORAL}]"):
            if arg_clean in ("reload", "refresh", "r"):
                mcp_client.recharger_connexions_mcp()
            else:
                mcp_client.initialiser_connexions_mcp()

    st = mcp_client.statut_mcp()
    serveurs = st.get("serveurs", {})
    total_outils = st.get("total_outils_mcp", 0)

    table = Table(
        title=f"🔌 Connexions MCP (Model Context Protocol) · {len(serveurs)} serveurs ({total_outils} outils)",
        border_style="#d97757",
        box=ROUNDED
    )
    table.add_column("Serveur MCP", style="bold #e5c07b")
    table.add_column("Transport", style="dim")
    table.add_column("Statut", style="white")
    table.add_column("Outils", style="cyan")
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
    console.print("[dim]  Configuration : mcp_servers.json │ Recharger à chaud : [bold white]/mcp reload[/bold white][/dim]\n")


def commande_aide():
    """Affiche le guide minimaliste façon Claude Code."""
    aide = (
        "[bold #d97757]Multi-Agents & Spécialistes :[/bold #d97757]\n"
        "  • [bold #e5c07b]/trade <crypto>[/bold #e5c07b]       : Invoque RIOT-Trader (Analyse quant, RSI, Carnet, Risk Management 1%)\n"
        "  • [bold #e5c07b]/swarm <mission>[/bold #e5c07b]     : Lance la chaîne complète (Architecte ➔ Ingénieur ➔ Testeur ➔ Reviewer)\n"
        "  • [bold #e5c07b]/architect <mission>[/bold #e5c07b] : Analyse la codebase et conçoit le plan d'action chirurgical\n"
        "  • [bold #e5c07b]/engineer <mission>[/bold #e5c07b]  : Applique les modifications de code via patcher_code\n"
        "  • [bold #e5c07b]/test <mission>[/bold #e5c07b]      : Exécute les tests unitaires et vérifie la qualité\n"
        "  • [bold #e5c07b]/review <mission>[/bold #e5c07b]    : Audit de sécurité (secrets/tokens), typage et verdict final\n\n"
        "[bold #d97757]Commandes Rapides & Session :[/bold #d97757]\n"
        "  • [bold #e5c07b]/mcp [reload][/bold #e5c07b]         : Gère les connexions aux serveurs MCP externes (mcp_servers.json)\n"
        "  • [bold #e5c07b]/app[/bold #e5c07b]                  : Lance l'Application Bureau & Web façon Claude (Artifacts)\n"
        "  • [bold #e5c07b]/code[/bold #e5c07b]                 : Bascule le mode Développeur / Coder mono-agent\n"
        "  • [bold #e5c07b]/project <nom>[/bold #e5c07b]         : Change de projet actif (ex: [italic]/project Trade App[/italic])\n"
        "  • [bold #e5c07b]/model <nom>[/bold #e5c07b]           : Affiche ou bascule le modèle LLM actif\n"
        "  • [bold #e5c07b]/tools[/bold #e5c07b]                 : Liste l'ensemble des outils de code et système\n"
        "  • [bold #e5c07b]/tokens[/bold #e5c07b]                : Affiche le décompte de tokens de la session\n"
        "  • [bold #e5c07b]/pc[/bold #e5c07b]                    : Jauge processeur, mémoire vive et disques\n"
        "  • [bold #e5c07b]/remote[/bold #e5c07b]                : Affiche les URL web mobile et tunnel 4G/5G\n"
        "  • [bold #e5c07b]/clear[/bold #e5c07b]                 : Nettoie l'écran du terminal\n"
        "  • [bold #e5c07b]/exit[/bold #e5c07b]                  : Quitte le terminal RIOT\n\n"
        "[bold #d97757]Exemples d'ordres :[/bold #d97757]\n"
        "  • [italic]/trade Analyse BTCUSDT avec sizing pour 10 000$ de capital[/italic]\n"
        "  • [italic]/swarm Ajoute la gestion du stop-loss 1% dans le module de trading[/italic]\n"
        "  • [italic]/architect Analyse la structure de Trade App et propose des améliorations[/italic]\n"
        "  • [italic]« Vérifie la santé de Trade App et donne le prix du Bitcoin »[/italic]"
    )
    console.print(Panel(aide, title="[bold #d97757]CLAUDE CODE STYLE · GUIDE RIOT[/bold #d97757]", border_style="#d97757", box=ROUNDED))


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


def _charger_conventions_projet(dossier: Optional[Path]) -> str:
    """Charge automatiquement les instructions et conventions du projet (Pilier 5)."""
    if not dossier:
        return ""
    fichiers_cibles = ["AGENTS.md", "INSTRUCTIONS.md", "CONVENTIONS.md", ".claude/conventions.md", "README.md"]
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
            resume_ligne = c.strip().splitlines()[0][:80]
            points.append(f"• [{role}] {resume_ligne}")

    resume_text = (
        "[RÉSUMÉ DES ÉCHANGES PRÉCÉDENTS (Auto-Compaction)]\n" +
        "\n".join(points[:8]) +
        "\n[Fin du résumé contextuel, poursuivre avec les messages récents]"
    )

    return [
        {"role": "user", "content": resume_text},
        {"role": "assistant", "content": "Bien reçu. Contexte compacté et mémorisé. Prêt pour la suite."},
    ] + recents


def executer_ordre(phrase: str, historique_conversation: List[dict]):
    """Exécute un ordre en boucle agentique avec design élégant Claude Code."""
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
            "4. STYLE CONCIS & TECHNIQUE : Reste percutant, professionnel, orienté action. Présente les diffs et chemins clairement. Pas de bavardage superflu."
            f"{conventions_ctx}"
        )
    else:
        systeme = (
            "Tu es Claude RIOT, un assistant d'élite, ingénieur de pointe et partenaire de réflexion.\n"
            f"Tu es connecté sur la machine locale de l'utilisateur sous Windows. Date réelle : {str_date}.\n"
            "Mode : DISCUSSION LIBRE (aucun projet ou dossier spécifique imposé).\n"
            "RÈGLES D'OR ABSOLUES :\n"
            "1. Réponds librement, précisément et directement à toutes les questions, réflexions ou analyses de l'utilisateur.\n"
            "2. N'appelle d'outils de fichiers que si l'utilisateur te demande expressément d'explorer ou de manipuler des fichiers.\n"
            "3. STYLE CONCIS, ÉLÉGANT & PERCUTANT : Reste bienveillant, critique et constructif. Pas de bavardage superflu.\n"
            "4. CONTRÔLE SYSTÈME & NAVIGATEUR : Si l'utilisateur demande d'ouvrir une application (`ouvrir_application`), régler le volume (`regler_volume`), contrôler les médias (`controler_media`), verrouiller la session (`verrouiller_pc`), voir l'écran (`capture_screen`) ou piloter Google Chrome (`browser_open`, `browser_click`, `browser_type`, `browser_scroll`), appelle directement l'outil adapté."
        )

    recettes_ctx = memoire.recup_recettes_pertinentes(phrase)
    if recettes_ctx:
        systeme += f"\n{recettes_ctx}"

    # Auto-compaction si l'historique devient trop long (Pilier 5)
    historique_conversation[:] = _compacter_historique(historique_conversation, max_messages=12)

    historique_conversation.append({"role": "user", "content": phrase})
    auth.audit("CLI_ORDRE", "localhost", phrase)

    # Récupération et filtrage des schémas d'outils
    tous_schemas = registre.schemas_api(
        local_seulement=(provider.nom == "Ollama"),
        requete=phrase,
    )
    if _SESSION_CTX["mode_code"]:
        outils_code_cibles = {
            "explorer_projet", "lire_code", "ecrire_code", "patcher_code",
            "chercher_dans_code", "executer_test_ou_commande", "executer_terminal",
            "inspecter_port", "lister_dossier", "supprimer_fichier", "ouvrir_terminal_interactif",
            "trade_app_statut", "trade_app_prix_crypto", "trade_app_demarrer_service",
            "trading_analyse_technique", "trading_calculateur_risque", "trading_carnet_ordres_express",
            "analyser_espace_stockage", "nettoyer_caches_temporaires",
            "generer_pdf", "extraire_texte_pdf", "fusionner_pdfs",
            "generer_excel", "lire_excel", "generer_powerpoint", "lire_powerpoint",
            "generer_graphique", "generer_diagramme", "creer_produit_digital",
            "auditer_schema_sql", "optimiser_requete_postgis", "generer_politiques_rls",
            "generer_composant_mobile", "scaffolder_app_mobile_expo",
            "surveiller_marche_crypto", "recueillir_veille_web", "generer_bulletin_veille",
            "lister_competences", "charger_competence", "lire_reference",
            "capturer_page", "capturer_frames",
            "lancer_navigateur_chrome", "browser_open", "browser_current_page",
            "browser_tabs", "browser_close_tabs", "browser_interact",
            "browser_click", "browser_type", "browser_scroll",
            "ouvrir_application", "controler_media", "regler_volume",
            "verrouiller_pc", "eteindre_pc", "capture_screen"
        }
        schemas = [s for s in tous_schemas if s.get("name") in outils_code_cibles]
    else:
        schemas = tous_schemas

    for tour in range(6):
        t0 = time.time()
        try:
            with console.status(f"[bold {CLAUDE_CORAL}]⠋ Réflexion en cours...[/bold {CLAUDE_CORAL}]", spinner="dots"):
                rep = provider.repondre(systeme, historique_conversation, schemas)
        except Exception as e:
            console.print(f"[bold red]❌ Erreur LLM : {e}[/bold red]")
            return

        dt = round(time.time() - t0, 2)

        # Vérifier si l'outil est requis
        if getattr(rep, "stop_reason", None) != "tool_use":
            texte = " ".join(b.text for b in rep.content if getattr(b, "type", None) == "text").strip()
            reponse_finale = texte or "Action terminée avec succès."
            historique_conversation.append({"role": "assistant", "content": reponse_finale})

            # Affichage Claude Code : minimaliste, aéré, élégant
            console.print()
            console.print(Markdown(reponse_finale))
            console.print(f"[dim]  ⚡ {provider.nom} · {dt}s[/dim]\n")
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

            # Style visuel Claude Code pour l'exécution d'outils
            arg_str = ", ".join(f"{k}='{str(v)[:50]}'" for k, v in args.items())
            console.print(f"[bold {CLAUDE_CORAL}]● Executing[/bold {CLAUDE_CORAL}] [bold white]{nom_outil}[/bold white]([dim]{arg_str}[/dim])...")

            t_outil = time.time()
            try:
                res = outil.fonction(**args) if outil else f"[ERREUR] Outil inconnu : {nom_outil}"
            except Exception as e:
                res = f"[ERREUR] Échec de l'outil {nom_outil} : {e}"

            dt_outil = round(time.time() - t_outil, 2)
            
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


def _verifier_configuration_initiale():
    """Assistant d'onboarding rapide si aucune cle API n'est configuree sur cette machine."""
    from core import llm as llm_mod
    if llm().disponible():
        return
    console.print(Panel(
        "[bold #e5c07b]Premiere configuration de RIOT sur cette machine[/bold #e5c07b]\n"
        f"[dim]Fichier cible : {config.FICHIER}[/dim]\n"
        "Fournisseurs supportes : [bold]groq[/bold], [bold]mistral[/bold], [bold]gemini[/bold], [bold]openrouter[/bold], [bold]anthropic[/bold]",
        border_style="#d97757",
        box=ROUNDED,
    ))
    try:
        mode = input("Fournisseur par defaut [groq] : ").strip().lower() or "groq"
        if mode not in ("groq", "mistral", "gemini", "openrouter", "anthropic", "local"):
            mode = "groq"
        config.definir("mode", mode)
        if mode != "local":
            cle = input(f"Cle API {mode} (Entree pour passer) : ").strip()
            if cle:
                config.definir(f"{mode}.cle", cle)
        llm_mod.reinitialiser()
        console.print("[bold green]✓ Configuration enregistree.[/bold green]\n")
    except (KeyboardInterrupt, EOFError):
        console.print()


def lancer_terminal_interactif():
    """Boucle principale du Terminal RIOT inspirée de Claude Code."""
    _verifier_configuration_initiale()
    afficher_banniere_claude()

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

            texte = session.prompt(invite).strip()
            if not texte:
                continue

            cmd = texte.lower()
            if cmd in ("/exit", "/quit", "/q"):
                console.print(f"[bold {CLAUDE_CORAL}]Session RIOT terminée. Bon code ![/bold {CLAUDE_CORAL}]\n")
                break
            elif cmd in ("/clear", "/cls"):
                os.system("cls" if os.name == "nt" else "clear")
                afficher_banniere_claude()
                continue
            elif cmd.startswith("/mcp"):
                parties = texte.split(maxsplit=1)
                arg_mcp = parties[1] if len(parties) > 1 else ""
                commande_mcp(arg_mcp)
                continue
            elif cmd in ("/app", "/claude"):
                from core import serveur, claude_app
                serveur.demarrer()
                claude_app.lancer_app_desktop()
                console.print(f"  [bold #d97757]⚡ Application Claude RIOT ouverte en fenêtre de bureau.[/bold #d97757]")
                console.print(f"  [dim]Accès Web : http://localhost:8790/ ou http://localhost:8790/claude[/dim]")
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
                    console.print(f"  [dim]Fichier joint : [bold #e5c07b]{p_cible.name}[/bold #e5c07b] ({len(contenu.splitlines())} lignes)[/dim]")
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
                console.print(f"[bold {CLAUDE_CORAL}]⚡ Mode Sous-Agent Coder :[/bold {CLAUDE_CORAL}] [bold white]{statut}[/bold white]")
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
                console.print(f"  [bold #d97757]Système :[/bold #d97757] CPU [green]{cpu}%[/green] │ RAM [green]{vm.percent}%[/green] ({round(vm.available/1024**3,1)} Go lib.){msg_disques}")
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
                parties = texte.split(maxsplit=1)
                provider = llm()
                if len(parties) > 1:
                    nouveau = parties[1].strip()
                    console.print(f"[yellow]Bascule de modèle : {nouveau} (rechargez la session pour persister).[/yellow]")
                else:
                    console.print(f"  ⚡ Modèle actuel : [bold #e5c07b]{getattr(provider, 'modele', '-')}[/bold #e5c07b] ({provider.nom})")
                continue
            elif cmd in ("/help", "/aide"):
                commande_aide()
                continue

            # Exécution de l'ordre
            executer_ordre(texte, historique_conv)

        except (KeyboardInterrupt, EOFError):
            console.print(f"\n[bold {CLAUDE_CORAL}]Fermeture du terminal RIOT.[/bold {CLAUDE_CORAL}]")
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
