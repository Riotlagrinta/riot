"""Outil Mode WhatsApp Clone pour Kéranos.

Permet d'activer/désactiver la surveillance et la réponse automatique
sur une conversation spécifique (ex: Tanya 🥰 ou La mifa 🫂❤️).
Utilise le moteur de style calibré de Dave (core/whatsapp_clone.py).
"""
import time, threading, logging
from pathlib import Path
from core.registre import outil
from core.whatsapp_clone import WhatsAppCloneEngine

LOG = logging.getLogger("keranos.whatsapp")

_CLONE = WhatsAppCloneEngine()

# État du mode WhatsApp
_ETAT_WHATSAPP = {
    "actif": False,
    "cible": None,
    "contexte": "tanya",
    "mode_reponse": "copilote", # 'copilote' (demande avant) ou 'autonome' (envoi direct)
    "dernier_message_id": None,
    "messages_traites": []
}

def simuler_reponse_whatsapp(contact: str, message: str) -> str:
    """Génère la réponse calibrée sans envoi réel (test ou mode copilote)."""
    ctx = "mifa" if "mifa" in contact.lower() else "tanya"
    return _CLONE.repondre(message_recu=message, expediteur=contact, contexte=ctx)

@outil(
    nom="mode_whatsapp",
    description="Active ou désactive le mode de réponse automatique WhatsApp (Clone de Dave) "
                "sur une discussion désignée (ex: 'Tanya', 'La mifa'). "
                "Actions possibles : 'activer', 'desactiver', 'statut', ou 'tester'.",
    parametres={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["activer", "desactiver", "statut", "tester"],
                "description": "L'action à effectuer : 'activer' le mode, le 'desactiver', voir le 'statut' ou 'tester' une réponse."
            },
            "cible": {
                "type": "string",
                "description": "Le nom du contact ou du groupe visé (ex: 'Tanya', 'La mifa'). Requis pour activer ou tester."
            },
            "mode_reponse": {
                "type": "string",
                "enum": ["copilote", "autonome"],
                "description": "'copilote' (prépare la réponse et attend ta confirmation) ou 'autonome' (répond directement en temps réel). Défaut: copilote."
            },
            "message_test": {
                "type": "string",
                "description": "Pour l'action 'tester' : le message auquel le clone doit répondre."
            }
        },
        "required": ["action"]
    },
    mcp_expose=True,
    affichage="toujours"
)
def mode_whatsapp(action: str, cible: str = "Tanya 🥰", mode_reponse: str = "copilote", message_test: str = None) -> str:
    global _ETAT_WHATSAPP

    act = action.lower().strip()

    if act == "tester":
        if not message_test:
            return "Précise le message à tester (paramètre 'message_test')."
        cible_propre = cible or "Tanya 🥰"
        rep = simuler_reponse_whatsapp(cible_propre, message_test)
        return (
            f"📱 **Test Clone WhatsApp Dave**\n\n"
            f"- **Discussion** : {cible_propre}\n"
            f"- **Message reçu** : \"{message_test}\"\n"
            f"- **Réponse calibrée de Dave** : \"{rep}\""
        )

    if act == "desactiver":
        _ETAT_WHATSAPP["actif"] = False
        _ETAT_WHATSAPP["cible"] = None
        return "🛑 **Mode WhatsApp désactivé.** Kéranos ne répond plus aux messages sur cette discussion."

    if act == "statut":
        if not _ETAT_WHATSAPP["actif"]:
            return "ℹ️ Le mode WhatsApp est actuellement **inactif**."
        return (
            f"🟢 **Mode WhatsApp ACTIF**\n\n"
            f"- **Discussion ciblée** : {_ETAT_WHATSAPP['cible']}\n"
            f"- **Contexte** : {_ETAT_WHATSAPP['contexte']}\n"
            f"- **Mode** : {_ETAT_WHATSAPP['mode_reponse']} ({'Envoi direct' if _ETAT_WHATSAPP['mode_reponse'] == 'autonome' else 'Validation avant envoi'})\n"
            f"- **Messages traités** : {len(_ETAT_WHATSAPP['messages_traites'])}"
        )

    if act == "activer":
        cible_propre = cible or "Tanya 🥰"
        ctx = "mifa" if "mifa" in cible_propre.lower() else "tanya"
        _ETAT_WHATSAPP["actif"] = True
        _ETAT_WHATSAPP["cible"] = cible_propre
        _ETAT_WHATSAPP["contexte"] = ctx
        _ETAT_WHATSAPP["mode_reponse"] = mode_reponse

        return (
            f"✅ **Mode WhatsApp activé sur : {cible_propre} !**\n\n"
            f"- **Contexte de réponse** : {'Groupe La mifa' if ctx == 'mifa' else 'Discussion privée Tanya'}\n"
            f"- **Comportement** : {mode_reponse.upper()} ({'Kéranos répondra directement' if mode_reponse == 'autonome' else 'Kéranos te demandera validation avant d envoyer'})\n"
            f"- **Style appliqué** : Dave (ton sec, concis, français naturel, sans émojis inutiles).\n\n"
            f"Pour l'arrêter à tout moment : dis simplement *'Désactive le mode WhatsApp'*."
        )
