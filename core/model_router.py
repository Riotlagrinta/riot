"""Routage adaptatif de modeles par requete selon l'intention et la complexite.

Classifie deterministiquement (< 1 ms, sans appel LLM supplementaire) chaque requete en 4 profils :
  - ``fast``  : salutations, questions simples, maths rapides, suivi/statut court
  - ``agent`` : pilotage PC/Windows, navigateur web, fichiers, outils generaux
  - ``code``  : edition/debug de code, scripts, Remotion, FFmpeg, SQL, tests, Git
  - ``deep``  : architecture complexe, audit complet, strategie, contexte long
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

_RE_CODE = re.compile(
    r"(?i)(?:\b("
    r"code|bug|debug\w*|fix\w*|corrig\w*|script|python|typescript|tsx|jsx|react|next\.?js|"
    r"node|npm|npx|remotion|ffmpeg|ffprobe|sql|postgis|rls|pytest|unittest|test\w*|"
    r"refactor\w*|patch\w*|diff|git|commit|docker|build|compil\w*|fonction|classe|"
    r"api|endpoint|fastapi|regex|render|html|css|tailwind|json|yaml|terminal|powershell|bash"
    r")\b|\.(?:py|ts|tsx|js|jsx|sql|json|css|html|bat|sh)\b|```)"
)

_RE_DEEP = re.compile(
    r"(?i)\b("
    r"architect\w*|audit\w*|strat[eé]gi\w*|planif\w*|analy\w*\s+approfond\w*|"
    r"pre-mortem|comparatif|pour\s+et\s+contre|benchmark|grill-me|"
    r"cahier\s+des\s+charges|business\s+plan|seo-audit|content-strategy|"
    r"anti-ai-slop|conception|refonte|roadmap"
    r")\b"
)

_RE_AGENT = re.compile(
    r"(?i)\b("
    r"ouvre\w*|lance\w*|ferme\w*|navigue\w*|clique\w*|clic|scrolle\w*|chrome|youtube|"
    r"site|url|http|cherche\s+web|internet|dossier|fichier|supprime\w*|processus|"
    r"port|volume|capture\w*|[eé]cran|mail|gmail|agenda|calendrier|m[eé]t[eé]o|"
    r"minuteur|timer|budget|rappelle|m[eé]moire|retiens|mcp|vibe\s?tg|kelvix"
    r")\b"
)

_RE_TRIVIAL = re.compile(
    r"(?i)^\s*(?:"
    r"salut|bonjour|bonsoir|coucou|hello|hi|hey|yo|merci\w*|ok+|d'accord|"
    r"c[' ]?est\s+bon\s*\??|est[- ]ce\s+pr[eê]t\s*\??|la\s+vid[eé]o\s+est\s+pr[eê]te\s*\??|"
    r"ça\s+va\s*\??|comment\s+vas[- ]tu\s*\??|qui\s+es[- ]tu\s*\??|"
    r"(?:cmb|combien)\s+(?:font|fait)\s+[\d\s\+\-\*\/\(\)\.,]+\s*\??"
    r")\s*$"
)


def _extraire_texte_messages(messages: Optional[Iterable[Any]]) -> tuple[str, int]:
    """Retourne (dernier_prompt_utilisateur, longueur_totale_conversation)."""
    dernier_user = ""
    total_chars = 0
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if isinstance(c, str):
            txt = c
        elif isinstance(c, list):
            txt = " ".join(
                str(x.get("text", "") or x.get("content", ""))
                for x in c
                if isinstance(x, dict)
            )
        else:
            txt = str(c or "")
        total_chars += len(txt)
        if m.get("role") == "user" and txt.strip():
            dernier_user = txt.strip()
    return dernier_user, total_chars


def classifier_tache_requete(
    messages: Optional[Iterable[Any]] = None,
    tools: Optional[Iterable[Any]] = None,
    systeme: str = "",
    prompt_hint: str = "",
) -> str:
    """Determine la categorie optimale ('fast' | 'agent' | 'code' | 'deep') pour une requete."""
    dernier_user, total_chars = _extraire_texte_messages(messages)
    if prompt_hint and not dernier_user:
        dernier_user = str(prompt_hint).strip()

    prompt_low = dernier_user.lower()
    sys_low = (systeme or "").lower()
    tools_list = list(tools or [])
    has_tools = len(tools_list) > 0

    # 1. Requetes courtes triviales / salutations / calcul mental -> modele rapide
    if prompt_low and len(prompt_low) <= 95 and _RE_TRIVIAL.match(prompt_low):
        return "fast"

    # 2. Taches d'ingenierie logicielle / code / CLI Remotion & FFmpeg -> modele code
    if _RE_CODE.search(prompt_low) or "mode : codage" in sys_low or "mode : ide" in sys_low:
        # Si l'utilisateur demande explicitement une architecture/audit global en plus -> deep
        if _RE_DEEP.search(prompt_low) and len(prompt_low) > 120:
            return "deep"
        return "code"

    # 3. Raisonnement approfondi / audit / architecture / contexte long -> modele deep
    if _RE_DEEP.search(prompt_low) or total_chars > 6500:
        return "deep"

    # 4. Pilotage PC, navigateur web ou orchestration d'outils -> modele agent robuste en tool-calling
    if _RE_AGENT.search(prompt_low) or (has_tools and len(prompt_low) > 70):
        return "agent"

    # 5. Par defaut : court = fast, sinon agent si outils presents
    if len(prompt_low) <= 180 and total_chars <= 2400:
        return "fast"
    return "agent" if has_tools else "deep"


def profil_vers_tache(
    profil: str,
    messages: Optional[Iterable[Any]] = None,
    tools: Optional[Iterable[Any]] = None,
    systeme: str = "",
    prompt_hint: str = "",
) -> str:
    """Resout un nom de profil ('riot-auto', 'riot-code', 'riot-fast', 'riot-deep') en tache cible."""
    m = (profil or "riot-auto").strip().lower()
    if "fast" in m:
        return "fast"
    if "code" in m:
        return "code"
    if "deep" in m:
        return "deep"
    if "agent" in m:
        return "agent"
    if prompt_hint and prompt_hint.strip().lower() in ("fast", "agent", "code", "deep"):
        return prompt_hint.strip().lower()
    return classifier_tache_requete(messages=messages, tools=tools, systeme=systeme)
