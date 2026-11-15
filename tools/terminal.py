"""Outils de terminal universel et de gestion des processus Windows pour RIOT.

Permet à RIOT et à l'utilisateur de :
- Exécuter des commandes PowerShell et CMD sans restriction artificielle.
- Détecter et protéger contre les commandes destructrices autonomes (Option 1).
- Lister les processus par mémoire ou CPU.
- Inspecter et libérer des ports réseau occupés (ex: tuer le process sur le port 3000/8000).
- Tuer des processus par PID ou nom.
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from core.registre import outil

_RACINE = Path(__file__).resolve().parent.parent

# Motifs de commandes potentiellement destructrices nécessitant confirmation si appelées sans confirme=True
_MOTIFS_DESTRUCTEURS = [
    (r"\brmdir\s+/[sS]", "Suppression récursive de dossiers (rmdir /s)"),
    (r"\bdel\s+/[sS]", "Suppression récursive de fichiers (del /s)"),
    (r"\bRemove-Item\b.*(-Recurse|-r\b)", "Suppression récursive PowerShell (Remove-Item -Recurse)"),
    (r"\brm\s+-[a-zA-Z]*r", "Suppression récursive (rm -rf / rm -r)"),
    (r"\b(format\s+[a-zA-Z]:|Format-Volume)", "Formatage de lecteur de disque"),
    (r"\bdiskpart\b", "Utilitaire de partitionnement de disque"),
    (r"\breg\s+delete\b", "Suppression de clé de registre Windows"),
    (r"\b(Stop-Computer|Restart-Computer)\b", "Extinction ou redémarrage immédiat"),
    (r"\bshutdown\s+/[sSrR]", "Extinction ou redémarrage système"),
    (r"\b(DROP\s+DATABASE|DROP\s+TABLE|TRUNCATE\s+TABLE)\b", "Suppression de base de données / table SQL"),
    (r"\btakeown\b", "Modification des droits de propriété du système"),
    (r"\bbcdedit\b", "Modification de la configuration de démarrage Windows"),
]

# Processus système critiques protégés contre l'arrêt accidentel
_PROCESSUS_PROTEGES = {
    "system", "system idle process", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe", "explorer.exe",
    "dwm.exe", "fontdrvhost.exe"
}


def verifier_commande_destructrice(commande: str) -> tuple[bool, str]:
    """Vérifie si une commande contient un motif destructeur."""
    cmd_clean = commande.strip()
    for motif, raison in _MOTIFS_DESTRUCTEURS:
        if re.search(motif, cmd_clean, re.IGNORECASE):
            return True, raison
    return False, ""


@outil(
    nom="executer_terminal",
    description="Exécute une commande PowerShell ou CMD sur le PC et retourne la sortie (stdout/stderr). "
                "À utiliser pour diagnostiquer, lancer des scripts, compiler, gérer git, npm, python, etc. "
                "Si la commande est destructrice, elle requiert l'accord préalable de l'utilisateur (confirme=True).",
    parametres={
        "type": "object",
        "properties": {
            "commande": {
                "type": "string",
                "description": "La commande complète à exécuter dans le terminal",
            },
            "shell": {
                "type": "string",
                "enum": ["powershell", "cmd"],
                "default": "powershell",
                "description": "L'interpréteur à utiliser (powershell par défaut, ou cmd)",
            },
            "cwd": {
                "type": "string",
                "description": "Dossier de travail où exécuter la commande (optionnel, racine du projet par défaut)",
            },
            "timeout": {
                "type": "integer",
                "default": 30,
                "description": "Délai maximal en secondes avant arrêt forcé (défaut 30s, max 300s)",
            },
            "confirme": {
                "type": "boolean",
                "default": False,
                "description": "Indique si l'utilisateur a expressément confirmé l'exécution d'une commande destructrice",
            },
        },
        "required": ["commande"],
    },
)
def executer_terminal(
    commande: str,
    shell: str = "powershell",
    cwd: str = "",
    timeout: int = 30,
    confirme: bool = False,
) -> str:
    """Exécute une commande système avec contrôle des motifs destructeurs et timeout."""
    cmd = commande.strip()
    if not cmd:
        return "Commande vide."

    # Contrôle de sécurité Option 1
    est_destructeur, motif = verifier_commande_destructrice(cmd)
    if est_destructeur and not confirme:
        return (
            f"[CONFIRMATION_REQUISE] Cette commande est considérée sensible ou destructrice "
            f"({motif}) :\n`{cmd}`\n"
            f"Demande d'abord confirmation explicite à l'utilisateur avant d'exécuter avec confirme=True."
        )

    repertoire = cwd.strip() if cwd and os.path.isdir(cwd.strip()) else str(_RACINE)
    limite_temps = min(max(1, int(timeout)), 300)

    if sys.platform != "win32":
        args = ["/bin/sh", "-c", cmd]
    elif shell.lower() == "cmd":
        args = ["cmd.exe", "/c", cmd]
    else:
        # PowerShell avec contournement de restriction de script pour la session courante
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd]

    try:
        proc = subprocess.run(
            args,
            cwd=repertoire,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=limite_temps,
        )
        sortie = (proc.stdout or "").strip()
        erreurs = (proc.stderr or "").strip()
        code = proc.returncode

        # Formatage du retour
        lignes = []
        if sortie:
            lignes.append(sortie)
        if erreurs:
            lignes.append(f"[stderr]\n{erreurs}")
        if not lignes:
            lignes.append("(Commande exécutée sans sortie texte)")

        res_complet = "\n".join(lignes)
        # Tronquage si trop long pour éviter d'exploser le contexte LLM (max 4000 caractères)
        if len(res_complet) > 4000:
            res_complet = res_complet[:3800] + f"\n... [tronqué, total {len(res_complet)} caractères]"

        entete = f"[Code retour: {code}]"
        return f"{entete}\n{res_complet}"

    except subprocess.TimeoutExpired:
        return f"[ERREUR] La commande a dépassé le délai maximal autorisé de {limite_temps} secondes."
    except Exception as e:
        return f"[ERREUR] Échec d'exécution du terminal : {e}"


@outil(
    nom="ouvrir_terminal_interactif",
    description="Ouvre une nouvelle fenêtre de terminal (PowerShell ou CMD) visible à l'écran, "
                "dans un dossier choisi, en exécutant optionnellement une commande (ex: 'agy', 'python', 'npm run dev'). "
                "L'opération est instantanée et s'exécute en processus détaché sans bloquer RIOT.",
    parametres={
        "type": "object",
        "properties": {
            "dossier": {
                "type": "string",
                "default": "",
                "description": "Dossier dans lequel ouvrir le terminal (défaut: dossier projets ou courant)",
            },
            "commande": {
                "type": "string",
                "default": "",
                "description": "Commande optionnelle à exécuter dans la nouvelle fenêtre (ex: 'agy', 'npm run dev')",
            },
            "shell": {
                "type": "string",
                "enum": ["powershell", "cmd", "bash"],
                "default": "powershell",
                "description": "Interpréteur à ouvrir : powershell, cmd ou bash",
            },
        },
    },
)
def ouvrir_terminal_interactif(dossier: str = "", commande: str = "", shell: str = "powershell") -> str:
    """Lance une nouvelle fenêtre de console indépendante (multiplateforme)."""
    from core.config import dossier_projets
    rep = dossier.strip() if dossier and os.path.isdir(dossier.strip()) else str(dossier_projets())
    cmd_clean = commande.strip()

    creation_flags = 0x00000010 if sys.platform == "win32" else 0
    if sys.platform != "win32":
        sh = os.environ.get("SHELL", "/bin/bash")
        args = [sh]
        if cmd_clean:
            args += ["-c", cmd_clean]
    elif shell.lower() == "cmd":
        args = ["cmd.exe"]
        if cmd_clean:
            args += ["/k", cmd_clean]
    else:
        args = ["powershell.exe", "-NoExit"]
        if cmd_clean:
            args += ["-Command", cmd_clean]

    try:
        subprocess.Popen(
            args,
            cwd=rep,
            creationflags=creation_flags,
            close_fds=True
        )
        return f"✓ Nouvelle fenêtre {shell.upper()} ouverte dans '{rep}'" + (f" avec la commande '{cmd_clean}'." if cmd_clean else ".")
    except Exception as e:
        return f"[ERREUR] Impossible d'ouvrir la fenêtre de terminal : {e}"


@outil(
    nom="inspecter_port",
    description="Identifie quel processus ou programme écoute sur un port réseau spécifique (ex: 3000, 8000, 8790).",
    parametres={
        "type": "object",
        "properties": {
            "port": {
                "type": "integer",
                "description": "Le numéro de port réseau à inspecter (ex: 3000)",
            }
        },
        "required": ["port"],
    },
)
def inspecter_port(port: int) -> str:
    """Trouve les processus écoutant sur un port donné."""
    try:
        import psutil
        port = int(port)
        trouves = []
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == port:
                pid = c.pid
                nom = "Inconnu"
                if pid:
                    try:
                        p = psutil.Process(pid)
                        nom = p.name()
                    except Exception:
                        pass
                trouves.append({
                    "port": port,
                    "statut": c.status,
                    "pid": pid,
                    "nom": nom,
                    "ip": c.laddr.ip,
                })

        if not trouves:
            return f"Le port {port} est libre (aucun processus actif ne l'écoute)."

        lignes = [f"Port {port} occupé par :"]
        for t in trouves:
            lignes.append(f"- PID {t['pid']} ({t['nom']}) | Statut: {t['statut']} | Adresse: {t['ip']}:{t['port']}")
        return "\n".join(lignes)

    except Exception as e:
        return f"[ERREUR] Impossible d'inspecter le port {port} : {e}"


@outil(
    nom="tuer_processus",
    description="Arrête un processus par son numéro PID, son nom, ou en libérant un port réseau occupé (ex: port 3000). "
                "Protège automatiquement les processus Windows critiques du système.",
    parametres={
        "type": "object",
        "properties": {
            "port": {
                "type": "integer",
                "description": "Port réseau à libérer en tuant le processus qui l'occupe (ex: 3000, 8000)",
            },
            "pid": {
                "type": "integer",
                "description": "PID (identifiant de processus) exact à tuer",
            },
            "nom": {
                "type": "string",
                "description": "Nom du programme à fermer (ex: 'node.exe', 'python.exe')",
            },
            "force": {
                "type": "boolean",
                "default": True,
                "description": "Forcer l'arrêt immédiat (SIGKILL / taskkill /f)",
            },
        },
    },
)
def tuer_processus(
    port: Optional[int] = None,
    pid: Optional[int] = None,
    nom: Optional[str] = None,
    force: bool = True,
) -> str:
    """Tue un ou plusieurs processus ciblés de façon sécurisée."""
    import psutil

    pids_a_tuer = set()

    # Cible par port
    if port is not None:
        port = int(port)
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == port and c.pid:
                pids_a_tuer.add(c.pid)
        if not pids_a_tuer:
            return f"Aucun processus trouvé sur le port {port}."

    # Cible par PID direct
    if pid is not None:
        pids_a_tuer.add(int(pid))

    # Cible par nom de processus
    if nom is not None and nom.strip():
        cible = nom.strip().lower()
        if not cible.endswith(".exe") and "." not in cible:
            cible_exe = cible + ".exe"
        else:
            cible_exe = cible
        for p in psutil.process_iter(["pid", "name"]):
            try:
                p_nom = (p.info["name"] or "").lower()
                if p_nom == cible or p_nom == cible_exe:
                    pids_a_tuer.add(p.info["pid"])
            except Exception:
                continue

    if not pids_a_tuer:
        return "Aucune cible spécifiée (précise un port, un pid ou un nom de processus)."

    resultats = []
    for p_id in pids_a_tuer:
        try:
            proc = psutil.Process(p_id)
            nom_proc = proc.name()
            # Protection système
            if nom_proc.lower() in _PROCESSUS_PROTEGES or p_id in (0, 4):
                resultats.append(f"[REFUSÉ] Le processus {nom_proc} (PID {p_id}) est un processus Windows vital protégé.")
                continue

            if force:
                proc.kill()
            else:
                proc.terminate()
            resultats.append(f"[OK] Processus {nom_proc} (PID {p_id}) arrêté avec succès.")
        except psutil.NoSuchProcess:
            resultats.append(f"[INFO] Le processus PID {p_id} n'existe plus.")
        except psutil.AccessDenied:
            resultats.append(f"[ERREUR] Accès refusé pour arrêter le PID {p_id} (privilèges administrateur requis).")
        except Exception as e:
            resultats.append(f"[ERREUR] Échec sur le PID {p_id} : {e}")

    return "\n".join(resultats)


@outil(
    nom="lister_processus",
    description="Donne la liste des programmes actifs les plus gourmands sur le PC, classés par mémoire RAM ou CPU.",
    parametres={
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "default": 10,
                "description": "Nombre de processus à afficher (défaut 10, max 30)",
            },
            "tri": {
                "type": "string",
                "enum": ["memoire", "cpu"],
                "default": "memoire",
                "description": "Critère de tri : 'memoire' ou 'cpu'",
            },
        },
    },
)
def lister_processus(top_n: int = 10, tri: str = "memoire") -> str:
    """Retourne un tableau concis des processus actifs les plus consommateurs."""
    try:
        import psutil
        limite = min(max(1, int(top_n)), 30)
        procs = []

        for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
            try:
                info = p.info
                mem_mo = round((info["memory_info"].rss if info["memory_info"] else 0) / (1024 * 1024), 1)
                cpu = info["cpu_percent"] or 0.0
                procs.append({
                    "pid": info["pid"],
                    "nom": info["name"] or "Inconnu",
                    "mem_mo": mem_mo,
                    "cpu": cpu,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if tri.lower() == "cpu":
            procs.sort(key=lambda x: x["cpu"], reverse=True)
            critere = "CPU"
        else:
            procs.sort(key=lambda x: x["mem_mo"], reverse=True)
            critere = "Mémoire RAM"

        lignes = [f"Top {limite} des processus par {critere} :", f"{'PID':<8} {'Nom':<25} {'RAM (Mo)':<10} {'CPU %':<8}"]
        lignes.append("-" * 55)
        for p in procs[:limite]:
            lignes.append(f"{p['pid']:<8} {p['nom'][:24]:<25} {p['mem_mo']:<10} {p['cpu']:<8}")

        return "\n".join(lignes)

    except Exception as e:
        return f"[ERREUR] Impossible de lister les processus : {e}"
