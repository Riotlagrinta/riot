"""Design system centralise de RIOT : 3 themes commutables pour CLI, Swarm, HUD, Overlay et Web."""
from typing import Dict, Any

from core import config
from core.config import reglage

THEMES: Dict[str, Dict[str, Any]] = {
    "obsidian": {
        "id": "obsidian",
        "nom": "Obsidian & Ambre",
        "description": "Studio industriel sombre, carbone profond et ambre solaire.",
        "bg": "#0B0C0E",
        "surface": "#13151A",
        "surface2": "#1B1E25",
        "border": "#272B34",
        "text": "#F4F3EE",
        "dim": "#9A9890",
        "accent": "#E8A838",
        "secondary": "#60A5FA",
        "ok": "#22C55E",
        "warn": "#E8A838",
        "err": "#EF4444",
        "cli_accent": "#E8A838",
        "cli_secondary": "#60A5FA",
        "cli_ok": "#22C55E",
        "cli_warn": "#E8A838",
        "cli_err": "#EF4444",
        "cli_text": "#F4F3EE",
        "cli_dim": "#9A9890",
        "cli_bg": "#13151A",
        "overlay_bg": "#13151A",
        "overlay_border": "#272B34",
        "overlay_text": "#F4F3EE",
        "overlay_dim": "#9A9890",
        "overlay_accent": "#E8A838",
    },
    "paper": {
        "id": "paper",
        "nom": "Encre & Emeraude",
        "description": "Editorial technique suisse, papier chaud haute lisibilite et vert emeraude.",
        "bg": "#F6F5F0",
        "surface": "#FFFFFF",
        "surface2": "#EAE8E0",
        "border": "#D8D5CB",
        "text": "#111315",
        "dim": "#5A5D65",
        "accent": "#059669",
        "secondary": "#0F766E",
        "ok": "#059669",
        "warn": "#D97706",
        "err": "#DC2626",
        "cli_accent": "#10B981",
        "cli_secondary": "#34D399",
        "cli_ok": "#22C55E",
        "cli_warn": "#F59E0B",
        "cli_err": "#EF4444",
        "cli_text": "#F1F5F9",
        "cli_dim": "#94A3B8",
        "cli_bg": "#0D1110",
        "overlay_bg": "#F6F5F0",
        "overlay_border": "#D8D5CB",
        "overlay_text": "#111315",
        "overlay_dim": "#5A5D65",
        "overlay_accent": "#059669",
    },
    "tactical": {
        "id": "tactical",
        "nom": "Tactical Ops",
        "description": "Console systeme sobre, noir acier, vert phosphore et bleu agents.",
        "bg": "#090B0D",
        "surface": "#11151B",
        "surface2": "#181E27",
        "border": "#1F2732",
        "text": "#E2E8F0",
        "dim": "#8B9BB0",
        "accent": "#4ADE80",
        "secondary": "#60A5FA",
        "ok": "#4ADE80",
        "warn": "#F59E0B",
        "err": "#F87171",
        "cli_accent": "#4ADE80",
        "cli_secondary": "#60A5FA",
        "cli_ok": "#4ADE80",
        "cli_warn": "#F59E0B",
        "cli_err": "#F87171",
        "cli_text": "#E2E8F0",
        "cli_dim": "#8B9BB0",
        "cli_bg": "#090B0D",
        "overlay_bg": "#11151B",
        "overlay_border": "#1F2732",
        "overlay_text": "#E2E8F0",
        "overlay_dim": "#8B9BB0",
        "overlay_accent": "#4ADE80",
    },
}

DEFAUT = "obsidian"

_ALIASES = {
    "obsidian": "obsidian",
    "ambre": "obsidian",
    "amber": "obsidian",
    "or": "obsidian",
    "gold": "obsidian",
    "1": "obsidian",
    "paper": "paper",
    "encre": "paper",
    "emeraude": "paper",
    "emerald": "paper",
    "clair": "paper",
    "light": "paper",
    "swiss": "paper",
    "2": "paper",
    "tactical": "tactical",
    "ops": "tactical",
    "tactical_ops": "tactical",
    "phosphore": "tactical",
    "3": "tactical",
}


def normaliser_theme(nom: str) -> str:
    """Ramene un alias utilisateur vers un identifiant de theme valide."""
    if not nom:
        return DEFAUT
    cle = str(nom).strip().lower().replace("-", "_").replace(" ", "_")
    return _ALIASES.get(cle, DEFAUT if cle not in THEMES else cle)


def theme_actif() -> str:
    """Lit le theme actif dans config.yaml (defaut: obsidian)."""
    val = reglage("interface.theme", DEFAUT)
    return normaliser_theme(val)


def definir_theme(nom: str) -> str:
    """Enregistre le theme actif dans config.yaml et retourne l'ID retenu."""
    cible = normaliser_theme(nom)
    config.definir("interface.theme", cible)
    return cible


def palette(nom: str = None) -> Dict[str, Any]:
    """Retourne le dictionnaire complet de couleurs du theme demande ou actif."""
    tid = normaliser_theme(nom) if nom else theme_actif()
    return THEMES.get(tid, THEMES[DEFAUT])


def lister_themes():
    """Retourne les metadonnees des themes disponibles."""
    return [
        {"id": k, "nom": v["nom"], "description": v["description"]}
        for k, v in THEMES.items()
    ]

