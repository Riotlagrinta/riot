"""Generation d'images et de maquettes visuelles par IA pour RIOT.

Supporte :
- Pollinations.ai (gratuit, sans cle API requise, modeles flux / turbo)
- Google Gemini Imagen (si une cle gemini.cle / GEMINI_API_KEY est configuree)

Les images generees sont enregistrees dans `_captures/` pour pouvoir etre
consultees localement et affichees dans RIOT Studio (`/captures/<nom>`).
"""
import base64
import logging
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import requests

from core.config import reglage
from core.registre import outil

LOG = logging.getLogger("riot.image_gen")
_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER_SORTIE = _RACINE / "_captures"
_DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)


def _cle_gemini() -> str:
    """Recupere la premiere cle Gemini disponible dans config.yaml ou env."""
    cles = reglage("gemini.cles", [])
    if isinstance(cles, list) and cles:
        premiere = str(cles[0]).strip()
        if premiere:
            return premiere
    cle = str(reglage("gemini.cle", "") or os.environ.get("GEMINI_API_KEY", "")).strip()
    return cle


def _generer_pollinations(
    prompt: str,
    largeur: int,
    hauteur: int,
    modele: str,
    seed: Optional[int],
) -> tuple[bytes, str]:
    """Genere une image via Pollinations.ai et retourne (octets, extension)."""
    params = {
        "width": max(256, min(2048, int(largeur))),
        "height": max(256, min(2048, int(hauteur))),
        "model": modele or "flux",
        "nologo": "true",
    }
    if seed is not None:
        params["seed"] = int(seed)

    url = f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
    rep = requests.get(
        url,
        params=params,
        timeout=90,
        headers={"User-Agent": "RIOT-ImageGen/1.0"},
    )
    if rep.status_code != 200:
        raise RuntimeError(f"Pollinations HTTP {rep.status_code}: {rep.text[:160]}")

    ctype = (rep.headers.get("Content-Type") or "").lower()
    if "image/" not in ctype and len(rep.content) < 1024:
        raise RuntimeError(f"Reponse non image recue ({ctype or 'inconnue'}).")

    ext = "png" if "png" in ctype else ("webp" if "webp" in ctype else "jpg")
    return rep.content, ext


def _generer_gemini_imagen(prompt: str, ratio: str = "16:9") -> tuple[bytes, str]:
    """Genere une image via l'API REST Google Gemini Imagen 3."""
    cle = _cle_gemini()
    if not cle:
        raise RuntimeError("Aucune cle Gemini configuree.")

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"imagen-3.0-generate-002:predict?key={cle}"
    )
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": ratio or "16:9",
        },
    }
    rep = requests.post(endpoint, json=payload, timeout=90)
    if rep.status_code != 200:
        raise RuntimeError(f"Gemini Imagen HTTP {rep.status_code}: {rep.text[:200]}")

    data = rep.json()
    preds = data.get("predictions") or []
    if not preds or "bytesBase64Encoded" not in preds[0]:
        raise RuntimeError("Reponse Gemini Imagen sans donnees d'image.")

    raw = base64.b64decode(preds[0]["bytesBase64Encoded"])
    mime = (preds[0].get("mimeType") or "image/png").lower()
    ext = "jpg" if "jpeg" in mime or "jpg" in mime else "png"
    return raw, ext


def _ratio_depuis_dimensions(largeur: int, hauteur: int) -> str:
    if largeur == hauteur:
        return "1:1"
    if largeur > hauteur:
        return "16:9" if (largeur / max(1, hauteur)) >= 1.5 else "4:3"
    return "9:16" if (hauteur / max(1, largeur)) >= 1.5 else "3:4"


@outil(
    nom="generer_image",
    description=(
        "Genere une image, illustration ou maquette UI par IA a partir d'une description textuelle "
        "et la sauvegarde localement dans `_captures/`. Supporte Pollinations (flux/turbo, sans cle) "
        "et Google Imagen (si cle Gemini configuree)."
    ),
    parametres={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Description detaillee de l'image ou maquette UI a generer (en anglais recommande pour un meilleur rendu).",
            },
            "largeur": {
                "type": "integer",
                "description": "Largeur en pixels (defaut: 1280).",
                "default": 1280,
            },
            "hauteur": {
                "type": "integer",
                "description": "Hauteur en pixels (defaut: 720).",
                "default": 720,
            },
            "modele": {
                "type": "string",
                "description": "Modele Pollinations ('flux' ou 'turbo', defaut: 'flux').",
                "default": "flux",
            },
            "provider": {
                "type": "string",
                "description": "'auto' (Pollinations puis Gemini ou inverse), 'pollinations', ou 'imagen'.",
                "default": "auto",
            },
            "nom_fichier": {
                "type": "string",
                "description": "Nom de fichier optionnel (sans chemin, ex: 'maquette_home').",
            },
            "seed": {
                "type": "integer",
                "description": "Graine aleatoire optionnelle pour reproduire un resultat.",
            },
        },
        "required": ["prompt"],
    },
    lent=True,
    phrase_attente="Generation de l'image en cours...",
    mcp_expose=True,
    affichage="toujours",
)
def generer_image(
    prompt: str,
    largeur: int = 1280,
    hauteur: int = 720,
    modele: str = "flux",
    provider: str = "auto",
    nom_fichier: Optional[str] = None,
    seed: Optional[int] = None,
) -> str:
    """Genere une image IA, la sauvegarde dans `_captures/` et retourne le chemin."""
    prompt_propre = (prompt or "").strip()
    if not prompt_propre:
        return "Erreur : le prompt de generation est vide."

    _DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    prov = (provider or "auto").strip().lower()
    octets: Optional[bytes] = None
    ext = "jpg"
    moteur_utilise = ""
    erreurs = []

    if prov == "imagen":
        ordre = ["imagen"]
    elif prov == "pollinations":
        ordre = ["pollinations"]
    else:
        ordre = ["pollinations", "imagen"] if _cle_gemini() else ["pollinations"]

    for moteur in ordre:
        try:
            if moteur == "imagen":
                octets, ext = _generer_gemini_imagen(
                    prompt_propre, _ratio_depuis_dimensions(largeur, hauteur)
                )
                moteur_utilise = "Google Gemini Imagen 3"
            else:
                octets, ext = _generer_pollinations(
                    prompt_propre, largeur, hauteur, modele, seed
                )
                moteur_utilise = f"Pollinations ({modele or 'flux'})"
            break
        except Exception as exc:
            erreurs.append(f"{moteur}: {exc}")
            LOG.warning("Echec generation image (%s): %s", moteur, exc)

    if octets is None:
        return "Echec de generation d'image -> " + " | ".join(erreurs)

    base = Path(nom_fichier).stem if nom_fichier else f"riot_img_{int(time.time())}"
    base_sure = "".join(c for c in base if c.isalnum() or c in ("-", "_")) or f"riot_img_{int(time.time())}"
    cible = _DOSSIER_SORTIE / f"{base_sure}.{ext}"
    if cible.exists():
        cible = _DOSSIER_SORTIE / f"{base_sure}_{int(time.time())}.{ext}"

    cible.write_bytes(octets)
    taille_ko = round(len(octets) / 1024, 1)
    return (
        f"Image generee ({moteur_utilise}, {largeur}x{hauteur}, {taille_ko} Ko) : `{cible}`\n"
        f"Apercu Studio : `/captures/{cible.name}`"
    )


@outil(
    nom="lister_images_generees",
    description="Liste les dernieres images ou maquettes enregistrees dans `_captures/`.",
    parametres={
        "type": "object",
        "properties": {
            "limite": {
                "type": "integer",
                "description": "Nombre maximal de fichiers a lister (defaut: 10).",
                "default": 10,
            }
        },
    },
    mcp_expose=True,
)
def lister_images_generees(limite: int = 10) -> str:
    """Retourne la liste des dernieres images de `_captures/`."""
    if not _DOSSIER_SORTIE.exists():
        return "Aucune image generee pour le moment."
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    fichiers = sorted(
        (f for f in _DOSSIER_SORTIE.iterdir() if f.is_file() and f.suffix.lower() in exts),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: max(1, int(limite))]
    if not fichiers:
        return "Aucune image dans `_captures/`."
    lignes = [
        f"- `{f.name}` ({round(f.stat().st_size / 1024, 1)} Ko) -> `/captures/{f.name}`"
        for f in fichiers
    ]
    return "\n".join(lignes)

