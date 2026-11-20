"""Outil `grill-me` : clarification active et cadrage des besoins avant d'agir.

Permet a RIOT de poser 1 a 4 questions ciblees a l'utilisateur (avec recommandations
par defaut et options) afin de lever toute ambiguite avant de coder ou d'executer.
Fonctionne de maniere 100% non bloquante sur toutes les surfaces (CLI, IDE, Studio).
"""
from __future__ import annotations

from typing import Any, List, Optional

from core.registre import outil

_CONSIGNE_GRILL_ME = (
    "MODE GRILL-ME ACTIF : Avant de modifier des fichiers, de coder ou d'executer une tache complexe, "
    "analyse la demande pour identifier de VRAIS points flous (perimetre, stack, UX, securite, contraintes). "
    "INTERDICTION d'appeler `grill-me` pour : (1) une question de suivi ou de statut ('la video est prete ?', 'c'est bon ?'), "
    "(2) un ordre direct et clair ('ouvre youtube', 'lance remotion', 'ouvre ffmpeg', 'verifie ...'), "
    "(3) une question factuelle ou discussion simple. "
    "Si une vraie ambiguite d'architecture subsiste et que l'utilisateur n'a pas encore repondu, appelle `grill-me` "
    "avec 2 a 4 questions courtes et une recommandation claire, puis attends sa reponse. "
    "Si l'utilisateur vient justement de repondre a tes questions `grill-me`, passe directement a l'action."
)


def consigne_grill_me(actif: bool) -> str:
    """Retourne l'instruction systeme adaptee au mode grill-me."""
    if actif:
        return f"\n\n{_CONSIGNE_GRILL_ME}"
    return (
        "\n\nOutil `grill-me` disponible : reserve UNIQUEMENT aux nouveaux projets ou demandes complexes ayant de vraies "
        "ambiguites d'architecture/produit. Ne l'appelle JAMAIS sur une question de suivi/statut ('c'est pret ?') "
        "ni sur une commande directe ('ouvre ...', 'lance ...', 'execute ...')."
    )


def formater_interview_grill_me(
    objectif: str,
    questions: List[Any],
    pourquoi: str = "",
) -> str:
    """Met en forme proprement les questions de cadrage pour l'utilisateur."""
    lignes = [f"### Cadrage rapide (`grill-me`) — {(objectif or 'Votre demande').strip()}"]
    if (pourquoi or "").strip():
        lignes.append(f"*Pourquoi ces questions :* {pourquoi.strip()}\n")

    if not questions:
        questions = [
            {
                "question": "Quel résultat exact ou livrable prioritaire attendez-vous en premier ?",
                "options": ["Version minimale rapide (MVP)", "Architecture complète prête pour la prod"],
                "recommandation": "Version minimale rapide (MVP)",
            }
        ]

    for idx, q in enumerate(questions[:5], start=1):
        if isinstance(q, dict):
            titre_q = str(q.get("question") or q.get("texte") or q.get("label") or f"Question {idx}").strip()
            opts = q.get("options") if isinstance(q.get("options"), list) else []
            reco = str(q.get("recommandation") or q.get("recommendation") or "").strip()
            lignes.append(f"**{idx}. {titre_q}**")
            for opt in opts[:4]:
                o_str = str(opt).strip()
                if o_str:
                    tag = " *(Recommandé)*" if reco and reco.lower() in o_str.lower() else ""
                    lignes.append(f"   - {o_str}{tag}")
            if reco and not any(reco.lower() in str(o).lower() for o in opts):
                lignes.append(f"   - *Recommandation par défaut :* {reco}")
        else:
            lignes.append(f"**{idx}. {str(q).strip()}**")

    lignes.append("\n*Répondez librement (ex. « 1: A, 2: ok pour la recommandation ») pour que je démarre exactement sur votre besoin.*")
    return "\n".join(lignes)


@outil(
    nom="grill-me",
    description="Pose 1 a 4 questions ciblees a l'utilisateur uniquement avant un NOUVEAU projet ou une tache complexe "
                "comportant de vraies ambiguites d'architecture/UX. NE PAS utiliser pour une question de statut ('est-ce pret ?'), "
                "une question simple, ni un ordre direct ('ouvre youtube', 'lance ffmpeg', 'verifie ...').",
    parametres={
        "type": "object",
        "properties": {
            "objectif": {
                "type": "string",
                "description": "Reformulation courte de ce que l'utilisateur veut accomplir.",
            },
            "questions": {
                "type": "array",
                "description": "Liste de 1 a 4 questions ciblees (objets {question, options, recommandation} ou chaines).",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Question claire et specifique"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "2 a 4 choix concrets (optionnel)",
                        },
                        "recommandation": {"type": "string", "description": "Option recommandee par defaut"},
                    },
                    "required": ["question"],
                },
            },
            "pourquoi": {
                "type": "string",
                "description": "Ce qui reste ambigu ou risquerait un mauvais choix sans confirmation.",
            },
        },
        "required": ["objectif", "questions"],
    },
    affichage="auto",
)
def grill_me(
    objectif: str,
    questions: Optional[List[Any]] = None,
    pourquoi: str = "",
) -> str:
    """Preparent une fiche structuree de questions de clarification et stoppent l'action en cours."""
    fiche = formater_interview_grill_me(objectif, questions or [], pourquoi=pourquoi)
    return (
        f"{fiche}\n\n"
        "[INSTRUCTION INTERNE : N'appelle plus aucun autre outil dans ce tour et ne modifie aucun fichier. "
        "Affiche ces questions clairement a l'utilisateur et attends sa reponse.]"
    )
