"""Outils de Rendu Visuel et Feedback par l'Image pour Claude RIOT Studio.

Permet à l'IA d'observer et de critiquer le résultat réel de ses créations web :
1. `capturer_page` : Captures PNG plein écran à deux échelles (Desktop 1440px et Mobile 390px).
2. `capturer_frames` : Fige une animation à différents instants (t=0, 300, 700, 1200, 2000 ms) et assemble une planche horizontale étiquetée pour juger le timing.
3. `capturer_scroll` : Captures étagées à différentes hauteurs de défilement pour valider les effets GSAP ScrollTrigger.
"""
import os
import logging
from pathlib import Path
from typing import List, Optional

from core.cli import _SESSION_CTX
from core.registre import outil

LOG = logging.getLogger("riot.rendu_visuel")
_RACINE = Path(__file__).resolve().parent.parent
ESPACE_DE_TRAVAIL = _RACINE
SORTIE_CAPTURES = _RACINE / "_captures"
SORTIE_DOCS = _RACINE / "output_documents"
SORTIE_CAPTURES.mkdir(parents=True, exist_ok=True)
SORTIE_DOCS.mkdir(parents=True, exist_ok=True)


def _resoudre(chemin: str) -> Path:
    """Résout le chemin d'un fichier HTML en prévenant les fuites d'arborescence."""
    c = Path(chemin)
    if c.is_absolute():
        p = c.resolve()
    else:
        # Chercher d'abord dans _RACINE, puis dans output_documents, puis dans motion design
        candidats = [
            _RACINE / c,
            SORTIE_DOCS / c,
            _RACINE / "output_products" / c,
            _RACINE / "skills" / "creation-motion" / c,
        ]
        p = None
        for cand in candidats:
            if cand.exists() and cand.is_file():
                p = cand.resolve()
                break
        if not p:
            p = (_RACINE / c).resolve()

    if not p.is_relative_to(_RACINE):
        raise ValueError(f"Accès refusé : `{chemin}` est hors du projet.")
    if not p.is_file():
        raise FileNotFoundError(f"Fichier HTML introuvable : `{p}`")
    return p


def _nom(page_path: Path, suffixe: str) -> Path:
    """Génère un chemin de capture dans _captures."""
    SORTIE_CAPTURES.mkdir(parents=True, exist_ok=True)
    return SORTIE_CAPTURES / f"{page_path.stem}.{suffixe}.png"


_JS_FIGER = """
(t) => {
  // 1. CSS animations / transitions / Web Animations API
  document.getAnimations().forEach(a => { a.pause(); a.currentTime = t; });
  // 2. GSAP (timeline globale), si présent
  if (window.gsap) { gsap.globalTimeline.pause(); gsap.globalTimeline.time(t / 1000); }
}
"""


@outil(
    nom="capturer_page",
    description="Capture une page HTML sous forme d'images PNG en résolutions Desktop (1440px) et Mobile (390px) pour permettre à l'IA d'observer et critiquer son rendu visuel.",
    parametres={
        "type": "object",
        "properties": {
            "chemin_html": {
                "type": "string",
                "description": "Chemin relatif ou nom du fichier HTML à capturer (ex: 'landing.html', 'exemples/entree-de-page.html')"
            },
            "delai_ms": {
                "type": "integer",
                "description": "Délai d'attente en millisecondes pour laisser s'achever l'animation d'entrée (défaut: 1500)",
                "default": 1500
            }
        },
        "required": ["chemin_html"]
    },
    mcp_expose=True,
    affichage="toujours"
)
def capturer_page(chemin_html: str, delai_ms: int = 1500) -> str:
    """Effectue des captures d'écran desktop et mobile d'une page HTML via Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "❌ Playwright n'est pas installé dans l'environnement virtuel (`pip install playwright`)."

    try:
        p = _resoudre(chemin_html)
    except Exception as e:
        return f"❌ {e}"

    largeurs = (1440, 390)
    sorties = []

    try:
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch()
            for largeur in largeurs:
                hauteur = 900 if largeur >= 768 else 780
                page = navigateur.new_page(viewport={"width": largeur, "height": hauteur})
                page.goto(p.as_uri())
                page.wait_for_timeout(delai_ms)
                label = "desktop" if largeur >= 768 else "mobile"
                sortie = _nom(p, f"{largeur}_{label}")
                page.screenshot(path=str(sortie), full_page=True)
                
                # Copie miroir dans output_documents pour téléchargement aisé
                import shutil
                shutil.copy2(sortie, SORTIE_DOCS / sortie.name)

                sorties.append((sortie.name, label, largeur))
                page.close()
            navigateur.close()

        lignes = [
            f"### 📸 Captures d'écran générées pour `{p.name}` :",
            f"Fichier source : `{p}`\n"
        ]
        for nom_fic, label, w in sorties:
            lien = f"/api/claude/document/telecharger?chemin={nom_fic}"
            lignes.append(f"- **Version {label.capitalize()} ({w}px) :** [{nom_fic}]({lien})")
            lignes.append(f"  ![{label}]({lien})\n")

        return "\n".join(lignes)

    except Exception as e:
        LOG.error(f"Erreur capture Playwright : {e}", exc_info=True)
        return f"❌ Erreur lors de la capture Playwright : {e}. (Vérifiez que Chromium est bien installé via `playwright install chromium`)."


@outil(
    nom="capturer_frames",
    description="Fige l'animation d'une page HTML à plusieurs instants précis (en ms) et assemble une planche de frames étiquetée (ex: t=0ms, 300ms, 700ms, 1200ms) pour vérifier la chorégraphie et le timing du motion design.",
    parametres={
        "type": "object",
        "properties": {
            "chemin_html": {
                "type": "string",
                "description": "Chemin relatif ou nom du fichier HTML à observer"
            },
            "instants_ms": {
                "type": "string",
                "description": "Instants d'observation séparés par des virgules en millisecondes (défaut: '0,300,700,1200,2000')",
                "default": "0,300,700,1200,2000"
            }
        },
        "required": ["chemin_html"]
    },
    mcp_expose=True,
    affichage="toujours"
)
def capturer_frames(chemin_html: str, instants_ms: str = "0,300,700,1200,2000") -> str:
    """Génère une planche de décomposition temporelle (contact sheet) d'une animation."""
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image, ImageDraw
    except ImportError as ie:
        return f"❌ Dépendances manquantes (`playwright` ou `Pillow`) : {ie}"

    try:
        p = _resoudre(chemin_html)
    except Exception as e:
        return f"❌ {e}"

    instants = []
    for x in instants_ms.split(","):
        try:
            instants.append(int(x.strip()))
        except ValueError:
            continue
    if not instants:
        instants = [0, 300, 700, 1200, 2000]

    images: List[Image.Image] = []
    try:
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch()
            page = navigateur.new_page(viewport={"width": 1280, "height": 800})
            page.goto(p.as_uri(), wait_until="domcontentloaded")
            page.wait_for_timeout(200)

            for t in instants:
                page.evaluate(_JS_FIGER, t)
                tmp = _nom(p, f"frame_{t}")
                page.screenshot(path=str(tmp))
                images.append(Image.open(tmp).convert("RGB"))
            navigateur.close()

        # Assemblage de la planche horizontale
        echelle = min(1.0, 640 / images[0].width)
        vignettes = [im.resize((int(im.width * echelle), int(im.height * echelle))) for im in images]
        bandeau = 28
        w = sum(v.width for v in vignettes) + 8 * (len(vignettes) - 1)
        h = vignettes[0].height + bandeau
        planche = Image.new("RGB", (w, h), (24, 24, 27))
        dessin = ImageDraw.Draw(planche)
        
        x = 0
        for t, v in zip(instants, vignettes):
            planche.paste(v, (x, bandeau))
            dessin.text((x + 8, 8), f"t = {t} ms", fill=(217, 119, 87))  # Claude Coral
            x += v.width + 8

        sortie = _nom(p, "planche_motion")
        planche.save(sortie)

        # Copie dans output_documents
        import shutil
        shutil.copy2(sortie, SORTIE_DOCS / sortie.name)

        lien = f"/api/claude/document/telecharger?chemin={sortie.name}"
        return (
            f"### 🎞️ Planche de Chorégraphie Motion générée pour `{p.name}` :\n\n"
            f"- **Instants analysés :** {', '.join(f't={t}ms' for t in instants)}\n"
            f"- **Fichier planche :** [{sortie.name}]({lien})\n\n"
            f"![Planche Motion]({lien})\n\n"
            f"> 👁️ **Critique visuelle :** Vérifiez l'ordre d'apparition, les masques et l'absence de saccades aux jalons t={instants[1]}ms et t={instants[-1]}ms."
        )

    except Exception as e:
        LOG.error(f"Erreur capturer_frames : {e}", exc_info=True)
        return f"❌ Erreur lors de la capture des frames : {e}"
