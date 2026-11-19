"""Outil `content-strategy` : architecte de strategie editoriale et calendrier multi-canaux.

Permet a RIOT de concevoir une strategie de contenu complete, actionnable et adaptee
au projet de l'utilisateur (piliers, personas, hooks, calendrier 4 semaines, KPIs),
avec sauvegarde Markdown dans `output_documents/` et memorisation long terme.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List

from core import memoire
from core.registre import outil

_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER_SORTIE = _RACINE / "output_documents"


def _slugifier(texte: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (texte or "projet").lower()).strip("_")
    return s[:48] or "projet"


def _construire_matrice_canaux(canaux_liste: List[str]) -> List[str]:
    guides = {
        "linkedin": "Posts carrousels/retours d'expérience (architecture, études de cas, chiffres) -> CTA DM ou démo.",
        "tiktok": "Vidéos courtes 30-55s (hook < 2s, démonstration écran/terrain, rythme cut) -> CTA lien bio / commentaire.",
        "instagram": "Reels éducatifs + carrousels visuels synthétiques + Stories coulisses -> CTA DM mot-clé.",
        "youtube": "Tutoriels profonds 8-15 min ou Shorts d'accroche vers vidéo longue -> CTA description / produit.",
        "whatsapp": "Messages directs courts, preuves clients, offres flash & liens de paiement direct (T-Money/Flooz/Carte).",
        "x": "Threads techniques percutants + builds quotidiens + mini-vidéos produit -> CTA waitlist / GitHub.",
        "twitter": "Threads techniques percutants + builds quotidiens + mini-vidéos produit -> CTA waitlist / GitHub.",
        "blog": "Articles SEO orientés résolution de problèmes concrets -> CTA téléchargement / inscription.",
    }
    lignes = []
    for c in canaux_liste:
        cle = c.strip().lower()
        detail = guides.get(cle, "Contenu natif orienté preuve terrain et démonstration directe -> CTA clair.")
        lignes.append(f"- **{c.strip()}** : {detail}")
    return lignes


@outil(
    nom="content-strategy",
    mcp_expose=True,
    description="Concoit une strategie de contenu complete et actionnable (positionnement, 4 piliers editoriaux, "
                "matrice canaux, calendrier sur 4 semaines, 8 hooks prets a publier et KPIs) et l'exporte en Markdown.",
    parametres={
        "type": "object",
        "properties": {
            "marque_ou_projet": {
                "type": "string",
                "description": "Nom du projet, produit, marque ou createur (ex: 'RIOT', 'MediGo Togo', 'Kelvix').",
            },
            "objectif": {
                "type": "string",
                "description": "Objectif prioritaire (ex: 'Acquerir 500 utilisateurs CLI', 'Vendre des abonnements Pro').",
            },
            "audience_cible": {
                "type": "string",
                "description": "Public cible precis (ex: 'Developpeurs full-stack, fondateurs PME en Afrique de l'Ouest').",
                "default": "Créateurs, développeurs et décideurs tech",
            },
            "canaux": {
                "type": "string",
                "description": "Canaux separes par virgules (ex: 'LinkedIn, TikTok, Instagram, WhatsApp').",
                "default": "LinkedIn, TikTok, Instagram, WhatsApp",
            },
            "cadence_semaine": {
                "type": "integer",
                "description": "Nombre de publications cibles par semaine (1 a 14, defaut: 4).",
                "default": 4,
            },
            "ton": {
                "type": "string",
                "description": "Ton editorial souhaite (ex: 'Direct, technique et sans blabla').",
                "default": "Direct, expert, orienté preuve et concret",
            },
            "sauvegarder": {
                "type": "boolean",
                "description": "True pour sauvegarder le plan en fichier .md et l'indexer en memoire.",
                "default": True,
            },
        },
        "required": ["marque_ou_projet", "objectif"],
    },
    affichage="toujours",
)
def content_strategy(
    marque_ou_projet: str,
    objectif: str,
    audience_cible: str = "Créateurs, développeurs et décideurs tech",
    canaux: str = "LinkedIn, TikTok, Instagram, WhatsApp",
    cadence_semaine: int = 4,
    ton: str = "Direct, expert, orienté preuve et concret",
    sauvegarder: bool = True,
) -> str:
    """Genere un blueprint complet de strategie editoriale pret a executer."""
    projet = (marque_ou_projet or "Mon Projet").strip()
    obj = (objectif or "Croissance & acquisition").strip()
    cible = (audience_cible or "Audience cible").strip()
    canaux_raw = [c.strip() for c in (canaux or "LinkedIn, TikTok").split(",") if c.strip()]
    if not canaux_raw:
        canaux_raw = ["LinkedIn", "TikTok"]
    cadence = max(1, min(int(cadence_semaine or 4), 14))
    ton_str = (ton or "Direct et concret").strip()
    date_str = datetime.now().strftime("%d/%m/%Y")

    matrice = _construire_matrice_canaux(canaux_raw)

    hooks = [
        f"« Pourquoi 90 % des {cible.lower()} perdent du temps sur ce problème (et comment {projet} le règle en 2 min) »",
        f"« J'ai testé la méthode classique vs {projet} sur un vrai cas client : voici les chiffres exacts. »",
        f"« Ne lancez jamais votre prochain projet sans vérifier ces 3 erreurs critiques. »",
        f"« Démo en direct sans coupure : de 0 à un résultat concret avec {projet}. »",
        f"« Ce que personne ne vous dit avant de choisir votre outil pour {obj.lower()}. »",
        f"« 1 erreur d'architecture que j'ai corrigée aujourd'hui sur {projet} (avant / après). »",
        f"« Voici le workflow exact utilisé chaque semaine pour tenir {cadence} publications sans s'épuiser. »",
        f"« Tu veux passer de la théorie à l'exécution sur {projet} ? Regarde l'étape 2. »",
    ]

    semaines = [
        ("Semaine 1 — Problème & Autorité", "Diagnostiquer la douleur n°1 de l'audience + première démo preuve terrain + étude de cas avant/après."),
        ("Semaine 2 — Éducation & Méthode", "Mini-tutoriel pas-à-pas + comparaison honnête d'alternatives + coulisses d'une décision technique."),
        ("Semaine 3 — Preuve Sociale & Cas Réels", "Démonstration sur cas réel utilisateur + réponse aux 3 objections fréquentes + checklist actionnable."),
        ("Semaine 4 — Conversion & Offre", "Synthèse des résultats obtenus + offre / appel à l'action clair + Q&A direct avec l'audience."),
    ]

    doc_lignes = [
        f"# Stratégie de Contenu — {projet}",
        f"*Générée le {date_str} · Cadence : {cadence} publications/semaine*",
        "",
        "## 1. Positionnement & Objectif",
        f"- **Marque / Projet :** {projet}",
        f"- **Objectif prioritaire :** {obj}",
        f"- **Audience cible (Persona) :** {cible}",
        f"- **Ton éditorial :** {ton_str}",
        "",
        "## 2. Les 4 Piliers Éditoriaux (Règle 40 / 30 / 20 / 10)",
        "1. **Autorité & Preuve Terrain (40 %)** : démos réelles, benchmarks chiffrés, résolutions de bugs/problèmes concrets.",
        "2. **Éducatif & Valeur Immédiate (30 %)** : tutoriels courts, checklists, workflows reproductibles sans blabla.",
        "3. **Coulisses / Build in Public (20 %)** : arbitrages d'architecture, échecs transformés en leçons, nouveautés produit.",
        "4. **Conversion & Offre (10 %)** : appels à l'action clairs vers essai gratuit, prise de rendez-vous ou paiement.",
        "",
        "## 3. Matrice Canaux & Formats",
        *matrice,
        "",
        f"## 4. Plan d'Action sur 4 Semaines ({cadence} contenus / semaine)",
    ]
    for titre_s, desc_s in semaines:
        doc_lignes.append(f"- **{titre_s}** : {desc_s}")

    doc_lignes.extend([
        "",
        "## 5. Banque de 8 Hooks Prêts à l'Emploi",
        *[f"{i}. {h}" for i, h in enumerate(hooks, start=1)],
        "",
        "## 6. KPIs à Suivre Chaque Vendredi",
        "- **Portée & Rétention** : taux de visionnage complet / temps de lecture sur les 3 premières secondes.",
        "- **Engagement qualifié** : sauvegardes, partages et commentaires posant une question technique/business.",
        "- **Conversion** : clics vers l'offre, inscriptions/connexions (`riot login` ou prise de contact) par pilier.",
    ])

    contenu_md = "\n".join(doc_lignes)
    chemin_sauve = ""
    if sauvegarder:
        try:
            _DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
            slug = _slugifier(projet)
            cible_md = _DOSSIER_SORTIE / f"strategie_contenu_{slug}.md"
            cible_md.write_text(contenu_md, encoding="utf-8")
            chemin_sauve = str(cible_md)
            memoire.memoriser_entite(
                "projects",
                f"content_strategy_{slug}",
                f"Stratégie '{projet}' -> Objectif: {obj} | Canaux: {', '.join(canaux_raw)} | Cadence: {cadence}/sem",
            )
        except Exception:
            pass

    pied = f"\n\n📁 **Stratégie enregistrée :** `{chemin_sauve}`" if chemin_sauve else ""
    return f"{contenu_md}{pied}"
