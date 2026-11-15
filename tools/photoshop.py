"""Outil de contrôle et d'automatisation d'Adobe Photoshop pour RIOT / Kéranos.

Permet de :
- Vérifier le statut de Photoshop (processus, version, COM).
- Exécuter des scripts ExtendScript (JSX) pour générer des maquettes, affiches et visuels.
- Créer des compositions graphiques automatisées multi-calques.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from core.registre import outil

LOG = logging.getLogger("jarvis.photoshop")

_RACINE = Path(__file__).resolve().parent.parent
DOSSIER_AFFICHES = _RACINE / "affiches"
DOSSIER_AFFICHES.mkdir(parents=True, exist_ok=True)

CHEMIN_PHOTOSHOP = Path(r"C:\Program Files\Adobe\Adobe Photoshop 2026\Photoshop.exe")


def _trouver_photoshop() -> Optional[Path]:
    """Trouve l'exécutable Photoshop sur la machine."""
    if CHEMIN_PHOTOSHOP.exists():
        return CHEMIN_PHOTOSHOP
    
    # Recherche dans les chemins standards
    dossier_adobe = Path(r"C:\Program Files\Adobe")
    if dossier_adobe.exists():
        for d in dossier_adobe.glob("Adobe Photoshop*"):
            exe = d / "Photoshop.exe"
            if exe.exists():
                return exe
    return None


@outil(
    nom="photoshop_statut",
    description="Vérifie si Adobe Photoshop est installé et en cours d'exécution sur le PC.",
    lent=False,
    affichage="toujours"
)
def photoshop_statut() -> Dict[str, Any]:
    """Inspecte l'état d'Adobe Photoshop sur la machine."""
    exe = _trouver_photoshop()
    if not exe:
        return {"installe": False, "message": "Adobe Photoshop n'a pas été trouvé sur la machine."}

    # Vérifier les processus actifs
    import psutil
    ps_procs = [p for p in psutil.process_iter(['pid', 'name', 'memory_info']) if 'photoshop' in p.info['name'].lower()]
    
    en_cours = len(ps_procs) > 0
    pid = ps_procs[0].info['pid'] if en_cours else None
    mem_mo = round(ps_procs[0].info['memory_info'].rss / (1024 * 1024), 1) if en_cours else 0

    etat = "en cours d'exécution" if en_cours else "fermé"
    return {
        "installe": True,
        "chemin": str(exe),
        "en_cours": en_cours,
        "pid": pid,
        "memoire_mo": mem_mo,
        "message": f"Photoshop 2026 est {etat} (PID: {pid}, RAM: {mem_mo} Mo)."
    }


@outil(
    nom="photoshop_executer_jsx",
    description="Exécute un script ExtendScript (JSX) dans Adobe Photoshop pour manipuler des calques, textes et effets.",
    parametres={
        "type": "object",
        "properties": {
            "code_jsx": {"type": "string", "description": "Code ExtendScript (JavaScript Photoshop) à exécuter."},
            "nom_script": {"type": "string", "description": "Nom optionnel du fichier de script.", "default": "script_riot.jsx"}
        },
        "required": ["code_jsx"]
    },
    lent=True,
    phrase_attente="J'exécute le script graphique dans Photoshop.",
    affichage="toujours"
)
def photoshop_executer_jsx(code_jsx: str, nom_script: str = "script_riot.jsx") -> str:
    """Enregistre et transmet un script JSX à Photoshop."""
    exe = _trouver_photoshop()
    if not exe:
        return "❌ Adobe Photoshop n'est pas installé sur ce système."

    script_path = DOSSIER_AFFICHES / nom_script
    try:
        script_path.write_text(code_jsx, encoding="utf-8")
    except Exception as e:
        return f"❌ Erreur lors de l'enregistrement du script : {e}"

    # Tenter via COM si possible
    try:
        import win32com.client
        ps = win32com.client.GetActiveObject("Photoshop.Application")
        ps.DoJavaScript(code_jsx)
        return f"✅ Script '{nom_script}' exécuté avec succès dans Photoshop via COM !"
    except Exception:
        # Repli : lancer le script via la ligne de commande Photoshop
        try:
            subprocess.Popen([str(exe), str(script_path)])
            return (
                f"✅ Script '{nom_script}' envoyé à Photoshop !\n\n"
                f"• Emplacement du fichier : `{script_path}`\n"
                f"• Vous pouvez également le lancer dans Photoshop via : *Fichier > Scripts > Parcourir...*"
            )
        except Exception as err:
            return f"❌ Échec de la transmission à Photoshop : {err}"
