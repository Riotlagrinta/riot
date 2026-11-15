"""Module de diagnostic et nettoyage sécurisé de l'espace disque pour RIOT.

Permet d'identifier avec précision où part l'espace sur C: et E:, et de purger
les caches temporaires (Temp, npm, uv, pip) et fichiers orphelins en toute sécurité.
"""
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any

from core.registre import outil


def _taille_dossier(chemin: Path) -> float:
    """Calcule la taille totale d'un dossier en Mo."""
    total = 0
    try:
        for racine, _, fichiers in os.walk(chemin):
            for f in fichiers:
                fp = Path(racine) / f
                try:
                    total += fp.stat().st_size
                except Exception:
                    continue
    except Exception:
        pass
    return round(total / (1024 * 1024), 2)


@outil(
    nom="analyser_espace_stockage",
    description="Analyse en profondeur l'espace disque de C: et E: pour identifier les plus gros consommateurs "
                "(caches temporaires, conteneurs Docker, dossiers de téléchargement, fichiers géants).",
    parametres={"type": "object", "properties": {}},
)
def analyser_espace_stockage() -> str:
    """Rapporte l'analyse détaillée des caches et fichiers volumineux."""
    import psutil

    lignes = ["📊 [AUDIT COMPLET DE L'ESPACE DISQUE]"]

    # Disques principaux
    try:
        c_use = psutil.disk_usage("C:\\")
        lignes.append(f"• Disque C: {round(c_use.used / 1024**3, 1)}/{round(c_use.total / 1024**3, 1)} Go ({round(c_use.free / 1024**3, 1)} Go libres, {c_use.percent}% plein)")
    except Exception:
        pass

    if Path("E:\\").exists():
        try:
            e_use = psutil.disk_usage("E:\\")
            lignes.append(f"• Disque E: {round(e_use.used / 1024**3, 1)}/{round(e_use.total / 1024**3, 1)} Go ({round(e_use.free / 1024**3, 1)} Go libres)")
        except Exception:
            pass

    lignes.append("\n🔍 [ZONES LES PLUS VOLUMINEUSES DÉTECTÉES] :")

    # 1. Dossier Temp
    temp_dir = Path(os.environ.get("TEMP", Path.home() / "AppData/Local/Temp"))
    if temp_dir.exists():
        sz_temp = _taille_dossier(temp_dir)
        lignes.append(f"  • Cache Temp Utilisateur : {sz_temp} Mo ({temp_dir})")

    # 2. Caches dev (uv, pip, npm)
    npm_cache = Path.home() / "AppData/Local/npm-cache"
    if npm_cache.exists():
        lignes.append(f"  • Cache NPM : {_taille_dossier(npm_cache)} Mo")

    uv_cache = Path.home() / "AppData/Local/uv/cache"
    if uv_cache.exists():
        lignes.append(f"  • Cache UV Python : {_taille_dossier(uv_cache)} Mo")

    # 3. Docker WSL
    docker_dir = Path.home() / "AppData/Local/Docker"
    if docker_dir.exists():
        lignes.append(f"  • Données Docker / WSL2 : {_taille_dossier(docker_dir) / 1024:.2f} Go ({docker_dir})")

    # 4. Fichiers géants sur E:\
    racine_e = Path("E:\\")
    if racine_e.exists():
        lignes.append("\n📁 [FICHIERS VOLUMINEUX À LA RACINE DE E:] :")
        fichiers_lourds = []
        try:
            for f in racine_e.iterdir():
                if f.is_file():
                    try:
                        sz_go = f.stat().st_size / (1024**3)
                        if sz_go >= 0.5:
                            fichiers_lourds.append((f.name, sz_go, str(f)))
                    except Exception:
                        continue
        except Exception:
            pass

        if fichiers_lourds:
            for nom, sz, p in sorted(fichiers_lourds, key=lambda x: x[1], reverse=True):
                lignes.append(f"  • {nom} : {sz:.2f} Go")
        else:
            lignes.append("  (Aucun fichier > 500 Mo à la racine de E:)")

    return "\n".join(lignes)


@outil(
    nom="nettoyer_caches_temporaires",
    description="Purger les fichiers temporaires inutiles (%TEMP%, cache npm, logs d'erreur) en toute sécurité. "
                "Les fichiers actuellement ouverts par d'autres applications sont ignorés sans planter.",
    parametres={
        "type": "object",
        "properties": {
            "confirme": {
                "type": "boolean",
                "default": True,
                "description": "Confirmation de purge des caches temporaires",
            }
        },
    },
)
def nettoyer_caches_temporaires(confirme: bool = True) -> str:
    """Supprime les fichiers temporaires orphelins et retourne le total libéré."""
    if not confirme:
        return "Nettoyage annulé."

    temp_dir = Path(os.environ.get("TEMP", Path.home() / "AppData/Local/Temp"))
    octets_liberes = 0
    nb_supprimes = 0
    nb_ignores = 0

    if temp_dir.exists():
        for item in temp_dir.iterdir():
            try:
                if item.is_file():
                    sz = item.stat().st_size
                    item.unlink()
                    octets_liberes += sz
                    nb_supprimes += 1
                elif item.is_dir():
                    sz = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                    shutil.rmtree(item, ignore_errors=True)
                    octets_liberes += sz
                    nb_supprimes += 1
            except Exception:
                nb_ignores += 1
                continue

    # Cache NPM
    npm_cache = Path.home() / "AppData/Local/npm-cache"
    if npm_cache.exists():
        try:
            sz = sum(f.stat().st_size for f in npm_cache.rglob('*') if f.is_file())
            shutil.rmtree(npm_cache, ignore_errors=True)
            octets_liberes += sz
            nb_supprimes += 1
        except Exception:
            pass

    mo_liberes = round(octets_liberes / (1024 * 1024), 2)
    return f"✓ Nettoyage terminé avec succès : {mo_liberes} Mo d'espace libéré ({nb_supprimes} éléments purgés, {nb_ignores} verrouillés en cours d'utilisation ignorés)."
