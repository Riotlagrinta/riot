"""Outil de contrôle et supervision de la tablette Amazon Fire HD 10 pour VibeTG.

Permet à RIOT de :
- Vérifier la connexion sans fil Wi-Fi (ADB TCP/IP sur 10.94.143.79:5555).
- Démarrer et arrêter le visionnage publicitaire automatisé en arrière-plan.
- Consulter le statut en direct (pubs vues, Vibe Coins gagnés, état de l'écran).
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from core.config import chercher_executable
from core.registre import outil

LOG = logging.getLogger("jarvis.vibetg_tablette")

BASE_DIR = Path(__file__).resolve().parent.parent
STATUS_FILE = BASE_DIR / "tablette_pubs_statut.json"
WORKER_SCRIPT = BASE_DIR / "scripts" / "vibetg_tablette_worker.py"
PYTHON_VENV = BASE_DIR / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
ADB_PATH = chercher_executable(
    "adb",
    [
        Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
        Path.home() / "Android/Sdk/platform-tools/adb",
    ],
)
TABLET_IP = "10.94.143.79:5555"

_PROCESSUS_WORKER: Optional[subprocess.Popen] = None


def _verifier_connexion_wifi() -> bool:
    """Vérifie si la tablette est accessible en Wi-Fi sans fil."""
    try:
        subprocess.run([ADB_PATH, "connect", TABLET_IP], timeout=3, capture_output=True)
        res = subprocess.run([ADB_PATH, "devices"], timeout=3, capture_output=True, text=True)
        return TABLET_IP in res.stdout and "device" in res.stdout
    except Exception:
        return False


@outil(
    nom="vibetg_tablette_statut",
    description="Consulte le statut en temps réel de la tablette (connexion sans fil Wi-Fi, pubs regardées, Vibe Coins accumulés).",
    lent=False,
    affichage="toujours"
)
def vibetg_tablette_statut() -> str:
    """Rapporte l'état de la tablette et les métriques de gains VibeTG."""
    wifi_ok = _verifier_connexion_wifi()
    wifi_badge = "🟢 Connectée sans fil (10.94.143.79:5555)" if wifi_ok else "🔴 Hors-ligne / Injoignable"

    data = {}
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    actif = data.get("actif", False)
    if _PROCESSUS_WORKER and _PROCESSUS_WORKER.poll() is not None:
        actif = False

    etat_badge = "🟢 EN COURS" if actif else "⚪ ARRÊTÉ"

    msg = (
        f"### 📱 Statut Tablette VibeTG (Amazon Fire HD 10)\n\n"
        f"• **Liaison Wi-Fi :** {wifi_badge}\n"
        f"• **État Worker :** {etat_badge} — *{data.get('etat_courant', 'Prêt')}*\n"
        f"• **Pubs aujourd'hui (tablette) :** **{data.get('pubs_regardees', 0)}** pubs\n"
        f"• **Gains cumulés session :** **+{data.get('total_coins', 0)} Vibe Coins** (~{data.get('total_fcfa', 0)} FCFA)\n"
        f"• **Dernière activité :** {data.get('dernier_message', 'En attente')}\n"
        f"• **Dernière synchro :** {data.get('derniere_maj', 'N/A')}\n"
    )

    if actif:
        msg += "\n💡 *Dites : « Arrête la tablette » pour stopper immédiatement.*"
    else:
        msg += "\n💡 *Dites : « Lance les pubs sur la tablette » pour démarrer.*"

    return msg


@outil(
    nom="vibetg_tablette_demarrer",
    description="Démarre le visionnage automatisé des publicités VibeTG sur la tablette sans fil via Wi-Fi.",
    parametres={
        "type": "object",
        "properties": {
            "nb_pubs": {
                "type": "integer",
                "description": "Nombre de publicités à regarder pour la session (par défaut 20)."
            },
            "heure_fin": {
                "type": "string",
                "description": "Heure d'arrêt limite au format HH:MM (ex: '23:59' ou '06:00'). Par défaut '23:59'."
            }
        }
    },
    lent=True,
    affichage="toujours"
)
def vibetg_tablette_demarrer(nb_pubs: int = 20, heure_fin: str = "23:59") -> str:
    """Lance le worker autonome en arrière-plan sans bloquer RIOT."""
    global _PROCESSUS_WORKER

    if _PROCESSUS_WORKER and _PROCESSUS_WORKER.poll() is None:
        return "⚠️ Le worker sur tablette est déjà en cours d'exécution !"

    if not _verifier_connexion_wifi():
        return "❌ Impossible de joindre la tablette sur le réseau Wi-Fi local (10.94.143.79:5555). Vérifiez qu'elle est allumée et sur le même réseau."

    python_bin = str(PYTHON_VENV) if PYTHON_VENV.exists() else "python"
    
    try:
        env = os.environ.copy()
        env["VIBETG_CIBLE_PUBS"] = str(nb_pubs)
        env["VIBETG_HEURE_FIN"] = heure_fin
        _PROCESSUS_WORKER = subprocess.Popen(
            [python_bin, str(WORKER_SCRIPT)],
            cwd=str(BASE_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return (
            f"🚀 **Worker tablette démarré sans fil !**\n"
            f"• **Objectif :** {nb_pubs} publicités\n"
            f"• **Liaison Wi-Fi :** `10.94.143.79:5555`\n"
            f"• **Arrêt limite :** {heure_fin}\n"
            f"• **Simulation humaine :** Délais aléatoires de 45s à 85s avec défilements naturels."
        )
    except Exception as e:
        LOG.error(f"Erreur lancement worker tablette: {e}")
        return f"❌ Erreur lors du lancement : {e}"


@outil(
    nom="vibetg_tablette_arreter",
    description="Arrête immédiatement le worker de visionnage publicitaire sur la tablette sans fil.",
    parametres={"type": "object", "properties": {}},
    lent=False,
    affichage="toujours"
)
def vibetg_tablette_arreter() -> str:
    """Arrête le worker et actualise le statut."""
    global _PROCESSUS_WORKER

    arrete = False
    if _PROCESSUS_WORKER and _PROCESSUS_WORKER.poll() is None:
        _PROCESSUS_WORKER.terminate()
        try:
            _PROCESSUS_WORKER.wait(timeout=3)
        except Exception:
            _PROCESSUS_WORKER.kill()
        _PROCESSUS_WORKER = None
        arrete = True

    # Met à jour le statut JSON
    try:
        if STATUS_FILE.exists():
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["actif"] = False
            data["etat_courant"] = "Arrêté par l'utilisateur."
            data["dernier_message"] = "Session stoppée depuis RIOT."
            data["derniere_maj"] = datetime.now().strftime("%H:%M:%S")
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    if arrete:
        return "⏹️ **Worker tablette arrêté avec succès.** L'appareil est en veille et aucun script ne tourne."
    return "ℹ️ Le worker tablette était déjà inactif."
