"""Routage adaptatif de modeles par requete selon l'intention et la complexite.

Classifie deterministiquement (< 1 ms, sans appel LLM supplementaire) chaque requete en 4 profils :
  - ``fast``  : salutations, questions simples, maths rapides, suivi/statut court
  - ``agent`` : pilotage PC/Windows, navigateur web, fichiers, outils generaux
  - ``code``  : edition/debug de code, scripts, Remotion, FFmpeg, SQL, tests, Git
  - ``deep``  : architecture complexe, audit complet, strategie, contexte long
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

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
    r"architect\w*|audit\w*|strat[eé]gi\w*|planif\w*|en\s+profondeur|"
    r"analy\w*\s+(?:approfond\w*|tout|compl[eè]t\w*)|"
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

    # 0. Taches internes d'auto-memoire silencieuse -> modele rapide/economique (jamais Mistral 2 RPM)
    if not has_tools and (
        "extracteur silencieux de mémoire" in sys_low
        or prompt_low.startswith("[surface:")
    ):
        return "fast"

    # 1. Requetes courtes triviales / salutations / calcul mental -> modele rapide
    if prompt_low and len(prompt_low) <= 95 and _RE_TRIVIAL.match(prompt_low):
        return "fast"

    # 2. Taches d'ingenierie logicielle / code / CLI Remotion & FFmpeg -> modele code
    if _RE_CODE.search(prompt_low) or "mode : codage" in sys_low or "mode : ide" in sys_low:
        # Si l'utilisateur demande explicitement une architecture/audit global en plus -> deep
        if _RE_DEEP.search(prompt_low) and len(prompt_low) > 120:
            return "deep"
        return "code"

    # 3. Raisonnement approfondi / audit / architecture / contexte tres long -> modele deep
    if _RE_DEEP.search(prompt_low) or total_chars > 18000:
        return "deep"

    # 4. Pilotage PC, navigateur web ou orchestration d'outils -> modele agent robuste en tool-calling
    if _RE_AGENT.search(prompt_low) or (has_tools and len(prompt_low) > 70):
        return "agent"

    # 5. Suivi court dans une session avec outils -> agent (evite fast/deep inadaptes sur 'LE LIEN DU SITE ?')
    if has_tools and len(prompt_low) <= 95:
        return "agent"

    # 6. Par defaut : court = fast, sinon agent si outils presents
    if len(prompt_low) <= 180 and total_chars <= 4500:
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


SOUS_AGENTS_TACHES: Dict[str, str] = {
    "engineer": "code",       # Meilleur modele de code (Sonnet 4.5 / codestral-latest)
    "architect": "deep",      # Raisonnement & grand contexte (Sonnet 4.5 / nemotron-3-ultra / deepseek)
    "reviewer": "deep",       # Audit securite & qualite
    "tester": "agent",        # Tests rapides & fiable en outils (gpt-oss-120b / qwen3.6-27b)
    "trader": "agent",        # Donnees financieres & calculs
    "coordinator": "fast",    # Reponse directe economique sans gaspiller le modele codeur
    "coordinateur": "fast",   # Alias francais de coordinator
    "coder": "code",
}


def tache_pour_sous_agent(role: str) -> str:
    """Retourne le profil de tache optimal ('code'|'deep'|'agent'|'fast') d'un sous-agent."""
    r = (role or "").strip().lower()
    for cle, tache in SOUS_AGENTS_TACHES.items():
        if cle in r:
            return tache
    return "agent"


class JournalContinuite:
    """Memoire de travail structuree qui survive aux rotations d'IA/modeles et a la compaction."""

    def __init__(self, objectif: str = "", dossier: str = ""):
        self.objectif = " ".join(str(objectif or "").split())[:220]
        self.dossier = str(dossier or "").strip()
        self.fichiers_lus: List[str] = []
        self.fichiers_modifies: List[str] = []
        self.commandes: List[str] = []
        self.actions: List[str] = []

    def _ajouter_unique(self, cible: List[str], val: str, limite: int = 8) -> None:
        v = str(val or "").strip()
        if not v:
            return
        if v in cible:
            cible.remove(v)
        cible.append(v)
        if len(cible) > limite:
            del cible[:-limite]

    def enregistrer_appel(self, outil: str, args: Optional[Dict[str, Any]], resultat: str) -> None:
        a = args if isinstance(args, dict) else {}
        nom = str(outil or "").strip()
        res_l1 = str(resultat or "").strip().splitlines()[0][:110] if str(resultat or "").strip() else "OK"
        try:
            from core.telemetry import masquer_secrets
            res_l1 = masquer_secrets(res_l1, max_len=110)
        except Exception:
            pass

        chemin = str(a.get("fichier") or a.get("chemin") or a.get("dossier") or "").strip()
        if nom in ("explorer_projet", "lister_dossier") and chemin:
            if not self.dossier:
                self.dossier = chemin
        elif nom == "lire_code" and chemin:
            self._ajouter_unique(self.fichiers_lus, chemin)
        elif nom in ("ecrire_code", "patcher_code", "supprimer_fichier") and chemin and "[ERREUR]" not in res_l1:
            self._ajouter_unique(self.fichiers_modifies, f"{chemin} ({nom})")
        elif nom in ("executer_terminal", "executer_test_ou_commande"):
            cmd = " ".join(str(a.get("commande") or "").split())[:60]
            try:
                from core.telemetry import masquer_secrets
                cmd = masquer_secrets(cmd, max_len=60)
            except Exception:
                pass
            if cmd:
                self._ajouter_unique(self.commandes, f"`{cmd}` -> {res_l1[:50]}", limite=4)

        arg_court = chemin or " ".join(str(a.get("commande") or a.get("url") or "").split())[:45]
        entree = f"{nom}({arg_court}) -> {res_l1}" if arg_court else f"{nom}() -> {res_l1}"
        self.actions.append(entree)
        if len(self.actions) > 8:
            del self.actions[:-8]

    def resume_court(self) -> str:
        if not self.actions and not self.fichiers_modifies:
            return ""
        morceaux = []
        if self.dossier:
            morceaux.append(f"Dossier={self.dossier}")
        if self.fichiers_modifies:
            morceaux.append("Modifiés=" + ", ".join(self.fichiers_modifies[-4:]))
        elif self.actions:
            morceaux.append("Actions=" + " ; ".join(self.actions[-3:]))
        return "[CONTINUITÉ SESSION : " + " | ".join(morceaux) + "]"

    def rendre_bloc(self) -> str:
        if not self.actions and not self.dossier:
            return ""
        lignes = ["\n\n[JOURNAL DE CONTINUITÉ INTER-MODÈLES — NE PAS RECOMMENCER À ZÉRO]"]
        if self.objectif:
            lignes.append(f"• Objectif initial : {self.objectif}")
        if self.dossier:
            lignes.append(f"• Dossier projet actif : {self.dossier}")
        if self.fichiers_lus:
            lignes.append("• Fichiers déjà lus : " + ", ".join(self.fichiers_lus[-6:]))
        if self.fichiers_modifies:
            lignes.append("• Fichiers modifiés/créés : " + ", ".join(self.fichiers_modifies[-6:]))
        if self.commandes:
            lignes.append("• Commandes récentes : " + " | ".join(self.commandes[-3:]))
        if self.actions:
            lignes.append("• Dernières étapes : " + " -> ".join(self.actions[-5:]))
        lignes.append("RÈGLE : Même en cas de rotation de modèle/provider, continue exactement à l'étape suivante sans redemander ni refaire ce qui est déjà fait.")
        return "\n".join(lignes)

