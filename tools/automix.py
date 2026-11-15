"""Outil AutoMix Pro pour Kéranos (Techniques DJ Authentiques).

Propose deux vrais styles de mixage professionnels :
1. 'beatmatch' : Time-stretching, verrouillage des BPM et alignement de phase des kicks.
2. 'echo_drop' : Coupure nette sur fin de phrase avec traînée d'écho analogique et drop percutant.
"""
from pathlib import Path
import os
import wave
import numpy as np
from core.registre import outil
from musique.automix_engine import AutoMixEngine
from musique.dj_routine_engine import DJRoutineEngine

_RACINE = Path(__file__).resolve().parent.parent
_ENGINE = AutoMixEngine()
_DJ_ENGINE = DJRoutineEngine()

_DOSSIERS_MUSIQUE = [
    _RACINE / "musique" / "a_mixer",
    _RACINE / "musique",
    Path.home() / "Music",
    Path.home() / "Downloads",
] + ([Path(r"E:\Downloads\38833FF26BA1D.UnigramPreview_g9c9v27vpyspw!App")] if Path(r"E:\Downloads\38833FF26BA1D.UnigramPreview_g9c9v27vpyspw!App").exists() else [])

def _trouver_fichier_musique(recherche: str):
    """Recherche un fichier audio par nom partiel ou chemin direct."""
    if not recherche:
        return None
    direct_path = Path(recherche)
    if direct_path.exists() and direct_path.is_file():
        return direct_path

    r = recherche.lower().strip()
    extensions = ("*.mp3", "*.wav", "*.flac", "*.m4a", "*.aac")
    for dossier in _DOSSIERS_MUSIQUE:
        if dossier.exists():
            for ext in extensions:
                for f in dossier.glob(ext):
                    if r in f.stem.lower() or r in f.name.lower():
                        return f
    return None

@outil(
    nom="enchainement_automix",
    description="Mixe deux morceaux avec une vraie technique de DJ professionnel : "
                "'routine_brake' (Quick-mix club avec Stutter roll + arrêt de platine vinyle et drop direct), "
                "'routine_backspin' (Quick-mix avec coup de platine en arrière et explosion sur le refrain), "
                "'beatmatch' (verrouillage de tempo, time-stretch et kicks calés au millimètre) ou "
                "'echo_drop' (effet écho/delay dub sur la fin de phrase et drop percutant).",
    parametres={
        "type": "object",
        "properties": {
            "morceau_a": {
                "type": "string",
                "description": "Nom ou extrait du premier morceau (ex: 'Tiakola - Jet Lag')."
            },
            "morceau_b": {
                "type": "string",
                "description": "Nom ou extrait du second morceau (ex: 'Tiakola - Coeur De Pirate')."
            },
            "technique": {
                "type": "string",
                "enum": ["routine_brake", "routine_backspin", "beatmatch", "echo_drop"],
                "description": "Style de mix : 'routine_brake' (stutter roll + vinyl stop), 'routine_backspin' (rewind platine), 'beatmatch' (fondu en mesure), ou 'echo_drop' (écho radio)."
            },
            "nb_mesures": {
                "type": "integer",
                "description": "Pour le mode beatmatch : nombre de mesures pour la transition (4, 8 ou 16). Défaut: 8."
            }
        },
        "required": ["morceau_a", "morceau_b"]
    },
    mcp_expose=True,
    affichage="toujours"
)
def enchainement_automix(morceau_a: str, morceau_b: str, technique: str = "routine_brake", nb_mesures: int = 8):
    f_a = _trouver_fichier_musique(morceau_a)
    f_b = _trouver_fichier_musique(morceau_b)

    if not f_a:
        return f"Impossible de trouver le morceau '{morceau_a}' dans ta bibliothèque."
    if not f_b:
        return f"Impossible de trouver le morceau '{morceau_b}' dans ta bibliothèque."

    piste_a = _ENGINE.charger_piste(str(f_a))
    piste_b = _ENGINE.charger_piste(str(f_b))

    dossier_sorties = _RACINE / "musique" / "mixes"
    dossier_sorties.mkdir(parents=True, exist_ok=True)

    if technique == "routine_brake":
        mix, sr, info = _DJ_ENGINE.creer_routine_club(piste_a, piste_b, cue_out_a_sec=34.8, cue_in_b_sec=28.5, style_fx="stutter_brake")
        tag = "routine_brake"
    elif technique == "routine_backspin":
        mix, sr, info = _DJ_ENGINE.creer_routine_club(piste_a, piste_b, cue_out_a_sec=34.8, cue_in_b_sec=28.5, style_fx="backspin")
        tag = "routine_backspin"
    elif technique == "echo_drop":
        mix, sr, info = _ENGINE.creer_enchainement_echo_drop(piste_a, piste_b)
        tag = "echo_drop"
    else:
        mix, sr, info = _ENGINE.creer_enchainement_beatmatch(piste_a, piste_b, nb_mesures=nb_mesures)
        tag = f"beatmatch_{nb_mesures}bars"

    nom_out = f"mix_{tag}_{piste_a['nom'][:12]}_to_{piste_b['nom'][:12]}.wav"
    out_file = dossier_sorties / nom_out

    pcm = (np.clip(mix, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(out_file), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    duree_totale_min = (len(mix) / sr) / 60.0

    details = "\n".join([f"- **{k.replace('_', ' ').capitalize()}** : {v}" for k, v in info.items()])

    return (
        f"[DJ MIX] **Mix Professionnel ({info['technique']}) généré !**\n\n"
        f"- **Piste 1** : {piste_a['nom']} ({info.get('bpm_source_a', info.get('bpm_a', ''))} BPM)\n"
        f"- **Piste 2** : {piste_b['nom']} ({info.get('bpm_source_b', info.get('bpm_b', ''))} BPM)\n"
        f"{details}\n"
        f"- **Durée totale du set** : {duree_totale_min:.1f} minutes\n"
        f"- **Fichier produit** : `{out_file.name}` dans `musique/mixes/`"
    )
