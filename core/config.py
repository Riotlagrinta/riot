"""Chargement de config.yaml : tous les secrets et reglages, au meme endroit.

Aucune cle en dur dans le code : tout passe par reglage("section.cle").
Le fichier config.yaml n'est pas versionne (voir .gitignore).
"""
import os
import shutil
import sys
from pathlib import Path

import yaml

_CONFIG = None


def _determiner_fichier_config() -> Path:
    """Trouve le fichier de configuration de manière universelle."""
    env_cfg = os.environ.get("RIOT_CONFIG")
    if env_cfg:
        return Path(env_cfg)
    racine = Path(__file__).resolve().parent.parent
    racine_locale = racine / "config.yaml"
    if racine_locale.exists():
        return racine_locale
    home_cfg = Path.home() / ".riot" / "config.yaml"
    if home_cfg.exists():
        return home_cfg
    if (racine / "pyproject.toml").exists() and os.access(racine, os.W_OK):
        return racine_locale
    return home_cfg


FICHIER = _determiner_fichier_config()


def dossier_projets() -> Path:
    """Retourne dynamiquement le dossier racine des projets selon la machine."""
    env_dir = os.environ.get("RIOT_PROJECTS_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    conf_dir = reglage("dossier_projets")
    if conf_dir and Path(conf_dir).exists():
        return Path(conf_dir)
    if Path(r"E:\PROJETS").exists():
        return Path(r"E:\PROJETS")
    home_projets = Path.home() / "Projets"
    if home_projets.exists():
        return home_projets
    return Path.cwd()


def chercher_executable(nom: str, fallbacks: list = None) -> str:
    """Trouve un exécutable dans le PATH ou parmi des chemins de repli standards."""
    trouve = shutil.which(nom)
    if trouve:
        return trouve
    for fb in (fallbacks or []):
        p = Path(fb) if isinstance(fb, Path) else Path(str(fb))
        if p.exists():
            return str(p)
    return nom


def _charger():
    global _CONFIG
    if _CONFIG is None:
        try:
            _CONFIG = yaml.safe_load(FICHIER.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            _CONFIG = {}
    return _CONFIG


def reglage(chemin, defaut=None):
    """Lit une valeur imbriquee, ex. reglage("hue.pont").

    Renvoie `defaut` si le chemin n'existe pas ; renvoie la valeur telle quelle
    si elle vaut explicitement null (ex. audio.haut_parleur: null -> None).
    """
    valeur = _charger()
    for cle in chemin.split("."):
        if not isinstance(valeur, dict) or cle not in valeur:
            return defaut
        valeur = valeur[cle]
    return valeur


def definir(chemin, valeur):
    """Modifie une valeur (ex. 'assistant.personnalite') et reecrit config.yaml."""
    conf = _charger()
    noeud = conf
    cles = chemin.split(".")
    for cle in cles[:-1]:
        noeud = noeud.setdefault(cle, {})
    noeud[cles[-1]] = valeur
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    with open(FICHIER, "w", encoding="utf-8") as f:
        yaml.safe_dump(conf, f, allow_unicode=True, sort_keys=False)
