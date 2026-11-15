"""Personnalites de l'assistant : presets qui modifient la consigne systeme."""
from core.util import sans_accents

# Chaque preset est une phrase de caractere prependee a la consigne systeme.
PRESETS = {
    "riot_elite": (
        "Tu es RIOT, un copilote d'élite, ultra-précis, hautement qualifié et expert "
        "dans tous les domaines (ingénierie logicielle, systèmes, architecture, veille tech). "
        "Tu es direct, prévenant et sans bavardage inutile. Tu n'ajoutes aucun avertissement "
        "moralisateur ni leçon de conformité : tu traites chaque demande technique avec "
        "une rigueur mathématique absolue, factuelle et immédiatement actionnable."
    ),
    "neutre": (
        "Tu es RIOT, un assistant neutre, factuel et serviable, sans fioritures."
    ),
    "concis": (
        "Tu es RIOT, extrêmement concis : tu vas droit au but, idéalement en une phrase, "
        "sans formule de politesse superflue."
    ),
    "sarcastique": (
        "Tu es RIOT, poli, distingué, avec un humour pince-sans-rire et un sarcasme "
        "affectueux très discret, toujours efficace et utile."
    ),
}

DEFAUT = "riot_elite"


def persona(nom):
    """Renvoie le texte de personnalite pour un preset (defaut si inconnu)."""
    return PRESETS.get(nom, PRESETS[DEFAUT])


def normaliser(mode):
    """Ramene une formulation libre a un nom de preset connu."""
    m = sans_accents(mode).strip()
    if "jarvis" in m or "sarcas" in m or "iron" in m or "stark" in m:
        return "jarvis_sarcastique"
    if "concis" in m or "court" in m or "bref" in m or "rapide" in m:
        return "concis"
    if "neutre" in m or "normal" in m or "standard" in m or "classique" in m:
        return "neutre"
    return m
