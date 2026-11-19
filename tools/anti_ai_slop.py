"""Outil `anti-ai-slop` : audit, nettoyage et suppression des hooks et cliches visuels IA dans les designs.

Detecte et elimine les reflexes generiques des interfaces generees par IA :
  - Hooks et slogans marketing cliches ('Propulse par l'IA', 'Revolutionnez', 'Elevate your'...)
  - Badges pilules / emojis decoratifs dans les Hero (✨, 🚀...)
  - Degrades violet/indigo/glow flous, cartes SaaS symetriques repetitives et textes clip-text
  - Retourne un score anti-slop (0-100), le code assaini et des prescriptions artistiques concretes.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.registre import outil

_HOOKS_IA_GENERIQUES: List[Tuple[str, re.Pattern[str], str]] = [
    ("Hook cliché « Propulsé par l'IA / Powered by AI »", re.compile(r"(?i)\b(propuls[eé]\s+par\s+l['’]ia|powered\s+by\s+ai)\b"), "Remplacer par le bénéfice métier mesurable réel."),
    ("Hook cliché « Révolutionnez / Transformez votre »", re.compile(r"(?i)\b(r[eé]volutionne[rz]|transforme[rz]\s+radicalement|redefine\s+the\s+future)\b"), "Remplacer par l'action concrète offerte à l'utilisateur en < 10 secondes."),
    ("Hook cliché « Libérez le potentiel / Passez au niveau supérieur »", re.compile(r"(?i)\b(lib[eé]re[rz]\s+(tout\s+)?le\s+potentiel|passe[rz]\s+au\s+niveau\s+sup[eé]rieur|unlock\s+(the\s+)?(full\s+)?potential|take\s+.{1,25}\s+to\s+the\s+next\s+level)\b"), "Formuler le gain précis (temps, coût, fiabilité)."),
    ("Hook cliché « Expérience fluide et intuitive / Seamless »", re.compile(r"(?i)\b((une\s+)?exp[eé]rience\s+fluide(\s+et\s+intuitive)?|seamless\s+experience|effortless\s+workflow)\b"), "Décrire le mécanisme exact (ex. 'Validation diff ligne par ligne')."),
    ("Hook cliché « Solution tout-en-un / Next-gen / Game-changer »", re.compile(r"(?i)\b(solution\s+tout-en-un|all-in-one\s+(platform|solution)|next-?gen(eration)?|game-?changer|supercharge\s+your)\b"), "Nommer le périmètre réel du produit sans superlatifs vides."),
    ("Hook cliché « Dans un monde en constante évolution / Elevate »", re.compile(r"(?i)\b(dans\s+un\s+monde\s+en\s+constante\s+[eé]volution|elevate\s+your|unleash\s+your)\b"), "Supprimer l'introduction creuse et entrer directement dans le sujet."),
    ("Remplissage générique (Lorem ipsum / Acme / John Doe)", re.compile(r"(?i)\b(lorem\s+ipsum|acme\s+corp|john\s+doe)\b"), "Remplacer par de vraies données issues du brief client."),
]

_PATTERNS_VISUELS_SLOP: List[Tuple[str, re.Pattern[str], str]] = [
    ("Dégradé violet/indigo/rose cliché IA", re.compile(r"(?i)(from-(?:purple|indigo|violet)-\d+[^\"'\s]*\s+to-(?:pink|purple|indigo|cyan)-\d+|#6366f1|#a855f7|linear-gradient\([^)]*(?:indigo|purple|violet|#6366f1|#a855f7|#8b5cf6)[^)]*\))"), "Choisir une palette franche de 4 à 6 couleurs liées au domaine du projet."),
    ("Halo flou décoratif excessif (`blur-3xl`)", re.compile(r"(?i)\bblur-3xl\b"), "Retirer les halos flous gratuits ; privilégier une hiérarchie typographique nette."),
    ("Titre Hero en texte dégradé (`bg-clip-text text-transparent`)", re.compile(r"(?i)bg-clip-text\s+text-transparent|text-transparent\s+bg-clip-text"), "Utiliser un contraste typographique franc et lisible plutôt qu'un dégradé arc-en-ciel."),
    ("Badge pilule emoji décoratif dans le Hero (🚀/✨/🔥)", re.compile(r"[🚀✨🔥💡⚡]\s*(Nouveau|New|IA|AI|Beta|Launch|Propuls[eé])", re.IGNORECASE), "Supprimer le badge pilule générique ou le remplacer par une info utile réelle (version, statut)."),
    ("Typographie par défaut sans intention (`Inter` / `Roboto` seule)", re.compile(r"(?i)font-family\s*:\s*['\"]?(?:Inter|Roboto)['\"]?"), "Associer une police de titre expressive au contexte métier."),
]

_RE_BADGE_SLOP_LINE = re.compile(
    r"(?im)^\s*<(?:span|div|p)[^>]*>\s*[🚀✨🔥💡⚡]?\s*"
    r"(?:Nouveau|New|Propuls[eé]\s+par\s+l['’]IA|Powered\s+by\s+AI|Next-?Gen|IA\s+G[eé]n[eé]rative)"
    r"[^<]{0,60}</(?:span|div|p)>\s*\n?"
)
_RE_CLIP_TEXT = re.compile(r"\b(?:bg-gradient-to-[trbl]{1,2}\s+|from-\S+\s+|via-\S+\s+|to-\S+\s+|bg-clip-text|text-transparent)\b")
_RE_BLUR_HALO = re.compile(r"(?im)^\s*<div[^>]*\bblur-3xl\b[^>]*>\s*</div>\s*\n?")


def analyser_slop(contenu: str) -> Dict[str, Any]:
    """Audite un code HTML/CSS/JSX/TSX/texte et identifie tous les hooks et reflexes IA."""
    lignes = (contenu or "").splitlines()
    constats: List[Dict[str, Any]] = []

    for idx, ligne in enumerate(lignes, start=1):
        for label, pat, conseil in _HOOKS_IA_GENERIQUES:
            if pat.search(ligne):
                constats.append({
                    "categorie": "hook_texte",
                    "ligne": idx,
                    "probleme": label,
                    "extrait": ligne.strip()[:120],
                    "conseil": conseil,
                })
        for label, pat, conseil in _PATTERNS_VISUELS_SLOP:
            if pat.search(ligne):
                constats.append({
                    "categorie": "design_visuel",
                    "ligne": idx,
                    "probleme": label,
                    "extrait": ligne.strip()[:120],
                    "conseil": conseil,
                })

    penalite = min(90, len(constats) * 14)
    score_qualite = max(10, 100 - penalite)
    return {
        "score_qualite": score_qualite,
        "nb_defauts": len(constats),
        "constats": constats,
    }


def nettoyer_design_slop(contenu: str) -> Tuple[str, List[str]]:
    """Supprime automatiquement les hooks/artefacts IA generiques sur du code UI."""
    modifs: List[str] = []
    out = contenu or ""

    out2, n_badge = _RE_BADGE_SLOP_LINE.subn("", out)
    if n_badge:
        modifs.append(f"{n_badge} badge(s) pilule/hook IA générique(s) supprimé(s)")
        out = out2

    out2, n_blur = _RE_BLUR_HALO.subn("", out)
    if n_blur:
        modifs.append(f"{n_blur} halo(s) flou(s) décoratif(s) `blur-3xl` supprimé(s)")
        out = out2

    if "bg-clip-text" in out and "text-transparent" in out:
        out = re.sub(r"\s*bg-clip-text|\s*text-transparent", "", out)
        modifs.append("Classes `bg-clip-text text-transparent` retirées pour restaurer un contraste typographique franc")

    remplacements_texte = [
        (re.compile(r"(?i)\bPropuls[eé]\s+par\s+l['’]IA\b\s*[-–—:•|]*\s*"), ""),
        (re.compile(r"(?i)\bPowered\s+by\s+AI\b\s*[-–—:•|]*\s*"), ""),
        (re.compile(r"[🚀✨🔥]+\s*"), ""),
    ]
    for pat, repl in remplacements_texte:
        out2, n = pat.subn(repl, out)
        if n:
            modifs.append(f"{n} occurrence(s) de hook/emoji décoratif IA nettoyée(s)")
            out = out2

    return out, modifs


def _resoudre_fichier_projet(chemin: str) -> Path:
    p = Path((chemin or "").strip().strip('"').strip("'"))
    if p.is_absolute():
        return p
    try:
        from core.cli import _SESSION_CTX
        proj = _SESSION_CTX.get("projet_actif")
        if isinstance(proj, Path) and proj.exists():
            return proj / p
    except Exception:
        pass
    return Path.cwd() / p


@outil(
    nom="anti-ai-slop",
    mcp_expose=True,
    description="Audite et supprime automatiquement les hooks génériques IA, slogans vides ('Propulsé par l'IA', "
                "'Révolutionnez'...), badges emojis, halos blur-3xl et dégradés SaaS clichés d'un design ou fichier UI.",
    parametres={
        "type": "object",
        "properties": {
            "contenu": {
                "type": "string",
                "description": "Code HTML/CSS/React/JSX/TSX ou copywriting du design a auditer et nettoyer.",
                "default": "",
            },
            "fichier": {
                "type": "string",
                "description": "Chemin d'un fichier UI existant a auditer/nettoyer (optionnel si contenu fourni).",
                "default": "",
            },
            "sujet": {
                "type": "string",
                "description": "Sujet ou domaine reel du produit pour ancrer les recommandations artistiques.",
                "default": "",
            },
            "appliquer": {
                "type": "boolean",
                "description": "True pour reecrire directement `fichier` apres nettoyage (defaut: False = apercu nettoye).",
                "default": False,
            },
        },
    },
    affichage="toujours",
)
def anti_ai_slop(
    contenu: str = "",
    fichier: str = "",
    sujet: str = "",
    appliquer: bool = False,
) -> str:
    """Supprime le slop generique IA et retourne diagnostic + version assainie."""
    cible_path = None
    source = contenu or ""
    if not source.strip() and (fichier or "").strip():
        cible_path = _resoudre_fichier_projet(fichier)
        if not cible_path.exists() or not cible_path.is_file():
            return f"[ERREUR] Fichier introuvable : {fichier}"
        source = cible_path.read_text(encoding="utf-8", errors="replace")

    if not source.strip():
        return "[ERREUR] Fournis `contenu` ou un chemin `fichier` à auditer."

    audit = analyser_slop(source)
    nettoye, modifs = nettoyer_design_slop(source)

    if appliquer and cible_path is not None and nettoye != source:
        cible_path.write_text(nettoye, encoding="utf-8")

    lignes = [
        f"### Audit Anti-AI-Slop — Score d'originalité : **{audit['score_qualite']}/100** ({audit['nb_defauts']} réflexe(s) IA détecté(s))"
    ]
    if sujet.strip():
        lignes.append(f"**Ancrage sujet :** {sujet.strip()}")

    if audit["constats"]:
        lignes.append("\n**Éléments génériques détectés :**")
        for c in audit["constats"][:12]:
            lignes.append(f"- L{c['ligne']} · **{c['probleme']}** : `{c['extrait']}` → {c['conseil']}")
    else:
        lignes.append("\n✓ Aucun hook générique ni réflexe visuel IA détecté.")

    if modifs:
        lignes.append("\n**Nettoyage appliqué automatiquement :**")
        for m in modifs:
            lignes.append(f"- {m}")
        if appliquer and cible_path is not None:
            lignes.append(f"\n✓ Fichier mis à jour : `{cible_path}`")

    lignes.extend([
        "\n**Directives de direction artistique (zéro look SaaS générique) :**",
        "1. Titre Hero direct sans badge pilule ni promesse vague : nommer l'usage réel dès les 6 premiers mots.",
        "2. Une seule palette métier contrastée (pas de dégradé violet/cyan par défaut) et un seul élément visuel mémorable.",
        "3. Remplacer les grilles symétriques de 3 cartes identiques par une hiérarchie adaptée au contenu réel.",
    ])

    if nettoye != source and not appliquer:
        extrait_net = nettoye[:3500] + ("\n... [tronqué]" if len(nettoye) > 3500 else "")
        lignes.append(f"\n**Code nettoyé prêt à l'emploi :**\n```\n{extrait_net}\n```")

    return "\n".join(lignes)
