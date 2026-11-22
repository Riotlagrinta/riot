"""Outils de Gestion et Chargement Dynamique des Compétences (Skills).

Implémente le principe de « divulgation progressive » pour les agents RIOT Studio :
1. Les compétences ne polluent pas le contexte initial.
2. L'agent appelle `lister_competences()` ou consulte l'index pour identifier la compétence requise.
3. L'agent appelle `charger_competence(nom)` pour charger le SKILL.md complet dans son contexte.
4. L'agent appelle `lire_reference(nom, fichier)` pour consulter une référence technique ciblée (ex: typographie, choregraphies).
"""
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.cli import _SESSION_CTX
from core.registre import outil

LOG = logging.getLogger("riot.competences")
_RACINE = Path(__file__).resolve().parent.parent
RACINE_SKILLS = _RACINE / "skills"
EXTENSIONS_AUTORISEES = {".md", ".html", ".css", ".js", ".py", ".txt", ".json", ".tsx", ".ts", ".sql"}
TAILLE_MAX = 200_000  # caractères


def _lire_entete(skill_md: Path) -> dict:
    """Lit l'en-tête YAML --- clé: valeur --- d'un SKILL.md."""
    try:
        texte = skill_md.read_text(encoding="utf-8")
        if not texte.startswith("---"):
            return {}
        fin = texte.find("\n---", 3)
        if fin == -1:
            return {}
        meta = {}
        for ligne in texte[3:fin].splitlines():
            if ":" in ligne:
                cle, _, valeur = ligne.partition(":")
                meta[cle.strip()] = valeur.strip()
        return meta
    except Exception as e:
        LOG.warning(f"Erreur lecture entete {skill_md} : {e}")
        return {}


@outil(
    nom="lister_competences",
    description="Retourne la liste des compétences (skills) disponibles dans RIOT Studio avec leur nom et description.",
    parametres={"type": "object", "properties": {}},
    mcp_expose=True,
    affichage="auto"
)
def lister_competences() -> str:
    """Retourne la liste formatée des compétences disponibles."""
    if not RACINE_SKILLS.exists():
        return "Aucun dossier de compétences trouvé."

    resultat = []
    for dossier in sorted(RACINE_SKILLS.iterdir()):
        skill_md = dossier / "SKILL.md"
        if dossier.is_dir() and skill_md.exists():
            meta = _lire_entete(skill_md)
            nom = meta.get("name", dossier.name)
            desc = meta.get("description", "")
            resultat.append(f"- **{nom}** (`{dossier.name}`) : {desc}")

    if not resultat:
        return "Aucune compétence avec un SKILL.md valide n'a été détectée."

    return "### 📚 Compétences Disponibles (Progressive Disclosure) :\n" + "\n".join(resultat)


def index_pour_prompt() -> str:
    """Texte à injecter dans le prompt système : la liste des compétences disponibles."""
    if not RACINE_SKILLS.exists():
        return ""
    lignes = ["Compétences spécialisées disponibles (appelle `charger_competence(nom)` AVANT de commencer la tâche correspondante) :"]
    for dossier in sorted(RACINE_SKILLS.iterdir()):
        skill_md = dossier / "SKILL.md"
        if dossier.is_dir() and skill_md.exists():
            meta = _lire_entete(skill_md)
            lignes.append(f"- `{meta.get('name', dossier.name)}` : {meta.get('description', '')}")
    return "\n".join(lignes)


@outil(
    nom="charger_competence",
    description="Charge en contexte les instructions et la doctrine complète d'une compétence spécialisée (contenu de son SKILL.md). Exemple : 'creation-motion', 'creation-frontend', 'inspecteur-sql-postgis'.",
    parametres={
        "type": "object",
        "properties": {
            "nom": {
                "type": "string",
                "description": "Nom ou slug du dossier de la compétence (ex: 'creation-motion', 'creation-frontend')"
            }
        },
        "required": ["nom"]
    },
    mcp_expose=True,
    affichage="auto"
)
def charger_competence(nom: str) -> str:
    """Charge les instructions complètes d'une compétence (SKILL.md)."""
    nom_nettoye = nom.strip().lower()
    dossier = (RACINE_SKILLS / nom_nettoye).resolve()
    
    # Tentative par correspondance de slug ou nom exact
    if not (dossier.exists() and (dossier / "SKILL.md").exists()):
        trouve = None
        for d in RACINE_SKILLS.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                meta = _lire_entete(d / "SKILL.md")
                if meta.get("name", "").lower() == nom_nettoye or d.name.lower() == nom_nettoye:
                    trouve = d
                    break
        if trouve:
            dossier = trouve
        else:
            dispo = [d.name for d in RACINE_SKILLS.iterdir() if (d / "SKILL.md").exists()]
            return f"❌ Compétence inconnue : `{nom}`. Disponibles : {', '.join(dispo)}"

    skill_file = dossier / "SKILL.md"
    texte = skill_file.read_text(encoding="utf-8")
    return f"## 📖 Instructions de la Compétence `{nom_nettoye}` :\n\n{texte}"


@outil(
    nom="lire_reference",
    description="Lit un fichier de référence technique ou un exemple d'une compétence (ex: 'references/choregraphies.md', 'references/typographie.md', 'exemples/entree-de-page.html').",
    parametres={
        "type": "object",
        "properties": {
            "nom_competence": {
                "type": "string",
                "description": "Nom de la compétence (ex: 'creation-motion', 'creation-frontend')"
            },
            "fichier": {
                "type": "string",
                "description": "Chemin relatif du fichier (ex: 'references/choregraphies.md')"
            }
        },
        "required": ["nom_competence", "fichier"]
    },
    mcp_expose=True,
    affichage="auto"
)
def lire_reference(nom_competence: str, fichier: str) -> str:
    """Lit un fichier technique dans le sous-dossier de la compétence en toute sécurité."""
    nom_nettoye = nom_competence.strip().lower()
    dossier = (RACINE_SKILLS / nom_nettoye).resolve()

    if not dossier.is_relative_to(RACINE_SKILLS) or not dossier.exists():
        return f"❌ Dossier de compétence `{nom_competence}` introuvable."

    cible = (dossier / fichier).resolve()
    if not cible.is_relative_to(dossier):
        return "❌ Accès refusé : tentative de traversée de chemin."

    if cible.suffix.lower() not in EXTENSIONS_AUTORISEES or not cible.is_file():
        return f"❌ Fichier introuvable ou extension non autorisée : `{fichier}`"

    texte = cible.read_text(encoding="utf-8")
    if len(texte) > TAILLE_MAX:
        texte = texte[:TAILLE_MAX] + "\n\n[... contenu tronqué à 200k caractères ...]"

    return f"### 📄 Référence `{fichier}` ({nom_competence}) :\n\n{texte}"
