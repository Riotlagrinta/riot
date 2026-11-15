"""Gestionnaire de tunnel chiffré Cloudflare pour RIOT (Accès distant 4G/5G).

Permet d'exposer de façon sécurisée le serveur local RIOT sur Internet via les Quick Tunnels Cloudflare :
- Aucune inscription ni clé d'API requise.
- URL HTTPS officielle (ex: https://xxx.trycloudflare.com).
- Zéro configuration de box / routeur (NAT traversal automatique).
- Sécurisé par le système de session et code PIN scrypt de RIOT.
"""
import atexit
import logging
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from core import auth
from core.config import reglage

LOG = logging.getLogger("riot.tunnel")
RACINE = Path(__file__).resolve().parent.parent
DOSSIER_BIN = RACINE / "bin"
CLOUDFLARED_EXE = DOSSIER_BIN / "cloudflared.exe"
FICHIER_URL = RACINE / "logs" / "tunnel_url.txt"

_PROCESSUS: Optional[subprocess.Popen] = None
_URL_ACTUELLE: Optional[str] = None
_VERROU = threading.Lock()


def binaire_disponible() -> bool:
    """Vérifie si le binaire cloudflared est prêt à l'emploi."""
    return CLOUDFLARED_EXE.is_file() and os_access_executable(CLOUDFLARED_EXE)


def os_access_executable(path: Path) -> bool:
    try:
        return path.stat().st_size > 1000000
    except Exception:
        return False


def url_publique_tunnel() -> Optional[str]:
    """Retourne l'URL publique active du tunnel, ou None si éteint."""
    global _URL_ACTUELLE
    if _PROCESSUS and _PROCESSUS.poll() is None:
        return _URL_ACTUELLE
    return None


def demarrer_tunnel_cloudflare(port: int = 8790, timeout_secondes: int = 25) -> Optional[str]:
    """Lance cloudflared en arrière-plan et intercepte l'URL https://*.trycloudflare.com assignée."""
    global _PROCESSUS, _URL_ACTUELLE

    with _VERROU:
        if _PROCESSUS and _PROCESSUS.poll() is None and _URL_ACTUELLE:
            return _URL_ACTUELLE

        if not binaire_disponible():
            LOG.error("tunnel: cloudflared.exe introuvable dans %s", CLOUDFLARED_EXE)
            return None

        cmd = [
            str(CLOUDFLARED_EXE),
            "tunnel",
            "--url",
            f"http://127.0.0.1:{port}",
            "--no-autoupdate",
        ]

        LOG.info("Démarrage du tunnel Cloudflare sur le port %s...", port)

        try:
            # Création du processus sans fenêtre visible sur Windows
            creationflags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                bufsize=1,
            )
            _PROCESSUS = proc

            url_trouvee = None
            regex_url = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
            debut = time.time()

            # Lecture du flux de démarrage pour capturer l'URL
            while time.time() - debut < timeout_secondes:
                if proc.poll() is not None:
                    LOG.error("tunnel: cloudflared s'est arrêté prématurément (code %s)", proc.returncode)
                    break

                ligne = proc.stderr.readline()
                if not ligne:
                    time.sleep(0.1)
                    continue

                m = regex_url.search(ligne)
                if m:
                    url_trouvee = m.group(0).strip()
                    break

            if url_trouvee:
                _URL_ACTUELLE = url_trouvee
                try:
                    FICHIER_URL.parent.mkdir(parents=True, exist_ok=True)
                    FICHIER_URL.write_text(url_trouvee, encoding="utf-8")
                except Exception:
                    pass
                auth.audit("TUNNEL_OUVERT", "cloudflare", url_trouvee)
                LOG.info("Tunnel Cloudflare opérationnel : %s", url_trouvee)
                print(f"\n========================================================")
                print(f"  [RIOT DISTANT] Tunnel Cloudflare 4G/5G actif :")
                print(f"  --> {url_trouvee}/mobile")
                print(f"========================================================\n")
                return url_trouvee
            else:
                LOG.warning("tunnel: délai dépassé sans détection d'URL Cloudflare.")
                return None

        except Exception as e:
            LOG.exception("tunnel: échec lancement cloudflared : %s", e)
            return None


def arreter_tunnel():
    """Arrête proprement le processus cloudflared."""
    global _PROCESSUS, _URL_ACTUELLE
    with _VERROU:
        if _PROCESSUS:
            try:
                _PROCESSUS.terminate()
                _PROCESSUS.wait(timeout=3)
            except Exception:
                try:
                    _PROCESSUS.kill()
                except Exception:
                    pass
            _PROCESSUS = None
            _URL_ACTUELLE = None
            auth.audit("TUNNEL_FERME", "cloudflare")
            LOG.info("Tunnel Cloudflare fermé.")


def statut_tunnel() -> Dict[str, Any]:
    """Retourne l'état courant du tunnel distant."""
    actif = bool(_PROCESSUS and _PROCESSUS.poll() is None and _URL_ACTUELLE)
    return {
        "actif": actif,
        "type": "cloudflare" if actif else "aucun",
        "url_publique": _URL_ACTUELLE if actif else None,
        "url_mobile": f"{_URL_ACTUELLE}/mobile" if actif else None,
    }


# Nettoyage automatique à l'arrêt du processus Python
atexit.register(arreter_tunnel)
