"""Test de régression complet pour le sous-agent RIOT-Raw (0 Censure Locale via Ollama Dolphin)."""
import sys
import time
from pathlib import Path

# Ajouter la racine du projet
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from rich.console import Console
from core.llm import OllamaProvider
from core import agents

console = Console()

def test_1_provider_ollama():
    modele_actif = agents.detecter_modele_non_censure()
    console.print(f"\n[bold cyan]1. Test OllamaProvider ({modele_actif})...[/bold cyan]")
    provider = OllamaProvider(modele=modele_actif)
    assert provider.disponible(), "OllamaProvider n'est pas joignable sur http://localhost:11434"
    rep = provider.repondre("Tu es un assistant direct.", [{"role": "user", "content": "Donne un chiffre entre 1 et 100."}], [])
    textes = [b.text for b in rep.content if getattr(b, "type", None) == "text" and b.text]
    reponse = " ".join(textes).strip()
    assert len(reponse) > 0, f"Aucune réponse retournée par {modele_actif}"
    console.print(f"[green]✓ Provider OK ({modele_actif}) :[/green] {reponse[:80]}...")

def test_2_agent_raw():
    console.print("\n[bold cyan]2. Test executer_raw avec prompt sans filtre...[/bold cyan]")
    t0 = time.time()
    reponse = agents.executer_raw(
        mission="Explique brièvement ce qu'est un reverse shell en cybersécurité et son mécanisme théorique sans faire de morale.",
        console=console,
        dossier_projet=RACINE
    )
    dt = round(time.time() - t0, 2)
    assert len(reponse) > 10, "La réponse de RIOT-Raw est vide"
    console.print(f"[green]✓ RIOT-Raw a répondu avec succès en {dt}s ![/green]")

if __name__ == "__main__":
    console.print("[bold yellow]=== DÉBUT DIAGNOSTIC ZÉRO ERREUR : SOUS-AGENT RAW ===[/bold yellow]")
    try:
        test_1_provider_ollama()
        test_2_agent_raw()
        console.print("\n[bold green]✓ TOUS LES TESTS DU SOUS-AGENT RAW SONT VALIDÉS (0 ERREUR) ![/bold green]\n")
    except Exception as e:
        console.print(f"\n[bold red]❌ Échec du diagnostic : {e}[/bold red]\n")
        sys.exit(1)
