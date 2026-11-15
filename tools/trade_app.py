"""Module d'outils spécialisé pour le projet Trade App (FastAPI + Binance + Paper Trading).

Permet à RIOT d'interagir directement avec la Trade App locale :
- Vérifier la santé du backend et de la base de données (GET /health)
- Interroger les prix et statistiques de marché Binance (GET /markets/... ou API Binance directe)
- Contrôler l'état du Paper Trading et des alertes de risque
- Lancer les services (Docker Postgres / Uvicorn backend) en arrière-plan détaché
"""
import os
import subprocess
import requests
from pathlib import Path
from typing import Optional

from core.config import dossier_projets
from core.registre import outil

TRADE_APP_DIR = dossier_projets() / "Trade App"
BACKEND_DIR = TRADE_APP_DIR / "backend"
FRONTEND_DIR = TRADE_APP_DIR / "frontend"
API_BASE_URL = "http://127.0.0.1:8000"


@outil(
    nom="trade_app_statut",
    mcp_expose=True,
    description="Vérifie si le backend FastAPI et les services de Trade App sont en ligne et opérationnels.",
    parametres={"type": "object", "properties": {}},
)
def trade_app_statut() -> str:
    """Interroge le endpoint public /health de Trade App."""
    try:
        r = requests.get(f"{API_BASE_URL}/health", timeout=3)
        if r.status_code == 200:
            data = r.json()
            statut_db = data.get("database", "inconnu")
            return f"✓ Trade App API est EN LIGNE (http://127.0.0.1:8000). Statut: {data.get('status', 'ok')}, DB: {statut_db}."
        else:
            return f"⚠️ Trade App API a répondu avec le statut HTTP {r.status_code} : {r.text[:200]}"
    except requests.exceptions.ConnectionError:
        return (
            "✕ Trade App API est HORS LIGNE (aucun serveur sur http://127.0.0.1:8000). "
            "Vous pouvez utiliser l'outil 'trade_app_demarrer_service' pour lancer le backend et Postgres."
        )
    except Exception as e:
        return f"Erreur lors de la vérification de Trade App : {e}"


@outil(
    nom="trade_app_prix_crypto",
    mcp_expose=True,
    description="Récupère le prix actuel, la variation 24h et le volume d'une paire crypto (ex: BTCUSDT, ETHUSDT, SOLUSDT) "
                "en interrogeant l'API Binance en direct pour l'analyse de marché Trade App.",
    parametres={
        "type": "object",
        "properties": {
            "symbole": {
                "type": "string",
                "default": "BTCUSDT",
                "description": "La paire de trading (ex: 'BTCUSDT', 'ETHUSDT', 'SOLUSDT')",
            }
        },
        "required": ["symbole"],
    },
)
def trade_app_prix_crypto(symbole: str = "BTCUSDT") -> str:
    """Interroge les données de marché en direct."""
    sym = symbole.strip().upper().replace("/", "").replace("-", "")
    
    # 1. Tenter via le backend Trade App si en ligne
    try:
        r = requests.get(f"{API_BASE_URL}/markets/tickers/{sym}", timeout=2)
        if r.status_code == 200:
            d = r.json()
            return f"📊 [Trade App API] {sym} : Prix={d.get('last_price')} | Var 24h={d.get('price_change_percent')}% | Vol={d.get('volume')}"
    except Exception:
        pass

    # 2. Repli direct sur l'API publique Binance (lecture seule, sans authentification)
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}"
        r = requests.get(url, timeout=4)
        if r.status_code == 200:
            d = r.json()
            prix = float(d.get("lastPrice", 0))
            var_pct = float(d.get("priceChangePercent", 0))
            vol = float(d.get("volume", 0))
            haut = float(d.get("highPrice", 0))
            bas = float(d.get("lowPrice", 0))
            signe = "+" if var_pct >= 0 else ""
            return (
                f"📈 [Binance Live] {sym} :\n"
                f"• Prix actuel : {prix:,.2f} $\n"
                f"• Variation 24h : {signe}{var_pct:.2f}%\n"
                f"• Plus haut 24h : {haut:,.2f} $ │ Plus bas 24h : {bas:,.2f} $\n"
                f"• Volume 24h : {vol:,.2f} {sym.replace('USDT', '')}"
            )
        else:
            return f"Paire '{sym}' introuvable ou erreur API Binance ({r.status_code})."
    except Exception as e:
        return f"Erreur de récupération du prix pour {sym} : {e}"


@outil(
    nom="trade_app_demarrer_service",
    description="Démarre les services de Trade App en arrière-plan détaché (docker postgres, backend uvicorn ou frontend vite).",
    parametres={
        "type": "object",
        "properties": {
            "composant": {
                "type": "string",
                "enum": ["backend", "postgres", "frontend", "tout"],
                "default": "backend",
                "description": "Le service à démarrer (backend, postgres, frontend ou tout)",
            }
        },
        "required": ["composant"],
    },
)
def trade_app_demarrer_service(composant: str = "backend") -> str:
    """Lance les composants de Trade App sans bloquer RIOT."""
    if not TRADE_APP_DIR.exists():
        return f"[ERREUR] Le dossier Trade App '{TRADE_APP_DIR}' est introuvable."

    creation_flags = 0x00000010  # CREATE_NEW_CONSOLE
    comp = composant.lower().strip()
    actions = []

    if comp in ("postgres", "tout"):
        try:
            subprocess.run(["docker", "compose", "up", "-d", "postgres"], cwd=str(TRADE_APP_DIR), timeout=15)
            actions.append("PostgreSQL Docker démarré (docker compose up -d postgres)")
        except Exception as e:
            actions.append(f"PostgreSQL : échec ({e})")

    if comp in ("backend", "tout"):
        venv_python = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
        py_exe = str(venv_python) if venv_python.exists() else "python"
        cmd = f'"{py_exe}" -m uvicorn app.main:app --reload --port 8000'
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-Command", cmd],
                cwd=str(BACKEND_DIR),
                creationflags=creation_flags,
                close_fds=True
            )
            actions.append(f"Backend FastAPI lancé dans une nouvelle console sur http://127.0.0.1:8000")
        except Exception as e:
            actions.append(f"Backend : échec ({e})")

    if comp in ("frontend", "tout"):
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-Command", "npm run dev"],
                cwd=str(FRONTEND_DIR),
                creationflags=creation_flags,
                close_fds=True
            )
            actions.append("Frontend Vite lancé dans une nouvelle console sur http://localhost:5173")
        except Exception as e:
            actions.append(f"Frontend : échec ({e})")

    return "✓ " + "\n✓ ".join(actions)
