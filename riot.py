"""Point d'entrée principal de RIOT.

Copilote personnel sans censure, contrôle PC & mobile, expert technique.

Modes d'utilisation :
    uv run python riot.py                   -> Lance le Terminal Interactif Cyberpunk (Recommandé)
    uv run python riot.py "mon ordre"       -> Exécute un ordre direct en une ligne et quitte
    uv run python riot.py --vocal           -> Lance le mode écoute vocale pure (Wake word "Hey Jarvis")
"""
import sys
from pathlib import Path

# Fix encodage console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_RACINE = Path(__file__).resolve().parent
if str(_RACINE) not in sys.path:
    sys.path.insert(0, str(_RACINE))


def main():
    args = sys.argv[1:]

    # Mode 1 : Écoute vocale pure (Wake word)
    if "--vocal" in args or "-v" in args:
        import keranos
        keranos.main()
        return

    # Mode Application Bureau RIOT Studio (Windowed Chromium)
    if "--app" in args or "-a" in args or (args and args[0].lower() in ("/app", "app", "/studio", "studio", "/claude", "claude")):
        from core import serveur, claude_app, theme
        serveur.demarrer()
        claude_app.lancer_app_desktop()
        from core import cli
        acc = theme.palette()["cli_accent"]
        cli.console.print(f"  [bold {acc}]⚡ Application RIOT Studio lancée en mode bureau.[/bold {acc}]")
        cli.console.print("  [dim]Accès Web direct : http://localhost:8790/ (Studio) · http://localhost:8790/ide (IDE) · http://localhost:8790/mobile[/dim]")
        cli.console.print("  [dim]Serveur actif en continu. Appuyez sur Ctrl+C pour quitter.[/dim]")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            cli.console.print("\n[dim]Arrêt du serveur web RIOT Studio.[/dim]")
        return

    # Mode IDE Agentique (style Antigravity)
    if "--ide" in args or (args and args[0].lower() in ("/ide", "ide")):
        from core import serveur, theme, cli
        import webbrowser, time
        serveur.demarrer()
        url_ide = "http://localhost:8790/ide"
        try:
            webbrowser.open(url_ide)
        except Exception:
            pass
        acc = theme.palette()["cli_accent"]
        cli.console.print(f"  [bold {acc}]⚡ RIOT IDE actif :[/bold {acc}] [bold white]{url_ide}[/bold white]")
        cli.console.print("  [dim]Serveur actif en continu. Appuyez sur Ctrl+C pour quitter.[/dim]")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            cli.console.print("\n[dim]Arrêt du serveur RIOT IDE.[/dim]")
        return

    # Mode 2 : Exécution d'un ordre unique en ligne de commande ou commande directe
    if args and not args[0].startswith("-"):
        from core import cli, registre, theme
        if not registre.tous():
            registre.charger_outils()
        
        cmd = args[0].lower()
        if cmd == "/theme":
            cli.commande_theme(" ".join(args[1:]))
            return
        if cmd in ("/login", "login"):
            cli.commande_login(" ".join(args[1:]))
            return
        if cmd in ("/logout", "logout"):
            cli.commande_logout()
            return
        if cmd in ("/update", "update"):
            cli.commande_update(" ".join(args[1:]))
            return
        if cmd in ("/keys", "keys", "/quota", "/quotas"):
            cli.commande_keys(" ".join(args[1:]))
            return
        if cmd in ("/tools", "/outils"):
            cli.commande_outils()
            return
        if cmd in ("/help", "/aide"):
            cli.commande_aide()
            return
        if cmd in ("/remote", "/tunnel", "/mobile"):
            from core import tunnel
            st = tunnel.statut_tunnel()
            cli.console.print(f"  📱 [bold white]Cockpit Local :[/bold white] http://localhost:8790/mobile")
            cli.console.print(f"  🌐 [bold white]Tunnel 4G/5G  :[/bold white] {st.get('url_publique') or 'En cours ou local seul'}")
            return
        if cmd in ("/pc", "/status", "/system"):
            import psutil
            cpu = psutil.cpu_percent(interval=0.2)
            vm = psutil.virtual_memory()
            racine_disque = "C:\\" if sys.platform == "win32" else "/"
            disk_main = psutil.disk_usage(racine_disque)
            label = "C:" if sys.platform == "win32" else "/"
            acc = theme.palette()["cli_accent"]
            cli.console.print(f"  [bold {acc}]Système :[/bold {acc}] CPU [green]{cpu}%[/green] │ RAM [green]{vm.percent}%[/green] ({round(vm.available/1024**3,1)} Go lib.) │ {label} [green]{round(disk_main.free/1024**3,1)} Go lib.[/green]")
            return

        if cmd == "/mcp":
            cli.commande_mcp(" ".join(args[1:]))
            return

        if cmd in ("/raw", "/uncensored"):
            from core import agents
            mission = " ".join(args[1:]) if len(args) > 1 else "Présente-toi et démontre ta neutralité absolue et ton absence totale de censure."
            agents.executer_raw(mission, cli.console, cli._SESSION_CTX["projet_actif"])
            return

        if cmd in ("/trade", "/trader"):
            from core import agents
            mission = " ".join(args[1:]) if len(args) > 1 else "Analyse le marché Bitcoin (BTCUSDT) et calcule un plan de risk management 1%."
            agents.executer_trader(mission, cli.console, cli._SESSION_CTX["projet_actif"])
            return

        if cmd in ("/swarm", "/pipeline"):
            from core import agents
            mission = " ".join(args[1:]) if len(args) > 1 else ""
            if not mission:
                cli.console.print("[bold yellow]Usage : riot /swarm <mission>[/bold yellow]")
                return
            agents.executer_pipeline_dev(mission, cli._SESSION_CTX["projet_actif"], cli.console)
            return
        if cmd == "/architect":
            from core import agents
            mission = " ".join(args[1:]) if len(args) > 1 else "Analyse l'architecture du projet et propose les améliorations prioritaires."
            agents.executer_architecte(mission, cli._SESSION_CTX["projet_actif"], cli.console)
            return
        if cmd == "/engineer":
            from core import agents
            mission = " ".join(args[1:]) if len(args) > 1 else ""
            if not mission:
                cli.console.print("[bold yellow]Usage : riot /engineer <modification à appliquer>[/bold yellow]")
                return
            agents.executer_ingenieur(mission, cli._SESSION_CTX["projet_actif"], cli.console)
            return
        if cmd in ("/test", "/tester"):
            from core import agents
            mission = " ".join(args[1:]) if len(args) > 1 else "Exécute les tests du projet et vérifie qu'il n'y a aucune régression."
            agents.executer_testeur(mission, cli._SESSION_CTX["projet_actif"], cli.console)
            return
        if cmd in ("/file", "/fichier"):
            from core import cli
            if len(args) < 2:
                cli.console.print("[bold yellow]Usage : riot /file <chemin_fichier> [question ou consigne][/bold yellow]")
                return
            chemin_str = args[1]
            question = " ".join(args[2:]) if len(args) > 2 else "Analyse ce fichier et explique son contenu en détail."
            p_cible = Path(chemin_str)
            if not p_cible.is_absolute():
                base_dir = cli._SESSION_CTX["projet_actif"] or Path.cwd()
                p_cible = (base_dir / chemin_str).resolve()
                if not p_cible.exists():
                    p_cible = (_RACINE / chemin_str).resolve()
            if not p_cible.exists() or not p_cible.is_file():
                cli.console.print(f"[bold red]✕ Fichier introuvable : {chemin_str}[/bold red]")
                return
            try:
                contenu = p_cible.read_text(encoding="utf-8", errors="replace")
                prompt_enrichi = (
                    f"=== 📄 FICHIER FOURNI : {p_cible.name} ({p_cible}) ===\n"
                    f"```{p_cible.suffix.lstrip('.')}\n{contenu}\n```\n"
                    f"=== FIN DU FICHIER ===\n\n"
                    f"Consigne de l'utilisateur :\n{question}"
                )
                cli.console.print(f"  [dim]Fichier joint : [bold #e5c07b]{p_cible.name}[/bold #e5c07b] ({len(contenu.splitlines())} lignes)[/dim]")
                cli.executer_ordre(prompt_enrichi, [])
            except Exception as e:
                cli.console.print(f"[bold red]✕ Erreur lecture fichier : {e}[/bold red]")
            return

        cli.executer_ordre(" ".join(args), [])
        return

    # Mode 3 (Défaut) : Terminal Interactif Cyberpunk
    from core import cli
    cli.lancer_terminal_interactif()


if __name__ == "__main__":
    main()
