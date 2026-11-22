"""Outil de Génération & Visualisation de Diagrammes Techniques (Mermaid / Architecture) pour Kéranos RIOT.

Permet de concevoir, valider et visualiser des diagrammes d'architecture logicielle, flux de données,
diagrammes de séquence, machines à états, modèles entité-relation (ERD) et roadmaps techniques.
Génère à la fois :
1. Le code Mermaid standard rendu en direct dans l'interface Web RIOT Studio.
2. Une visionneuse HTML interactive dédiée avec Zoom, Pan et Export SVG autonome dans `output_documents/`.
"""
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from core.cli import _SESSION_CTX
from core.registre import outil

LOG = logging.getLogger("riot.diagrammes")
_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER_DOCS = _RACINE / "output_documents"
_DOSSIER_DOCS.mkdir(parents=True, exist_ok=True)

# Directives valides de départ Mermaid
TYPES_MERMAID = {
    "flowchart": ("flowchart TD", "flowchart", "graph TD", "graph LR", "graph"),
    "sequence": ("sequenceDiagram",),
    "class": ("classDiagram",),
    "state": ("stateDiagram-v2", "stateDiagram"),
    "erd": ("erDiagram",),
    "gitgraph": ("gitGraph",),
    "gantt": ("gantt",),
    "mindmap": ("mindmap",),
    "pie": ("pie",),
}


def nettoyer_code_mermaid(code: str, type_voulu: str = "flowchart") -> str:
    """Nettoie le code Markdown/Mermaid fourni, extrait le bloc interne et garantit l'en-tête."""
    if not code:
        return ""

    texte = code.strip()

    # Si encapsulé dans des balises markdown ```mermaid ... ```
    m = re.search(r"```(?:mermaid)?\s*\n?(.*?)\n?```", texte, re.DOTALL | re.IGNORECASE)
    if m:
        texte = m.group(1).strip()

    # Vérification si la directive de départ est présente
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    if not lignes:
        return ""

    premiere_ligne = lignes[0].lower()
    directives = TYPES_MERMAID.get(type_voulu.lower(), ("flowchart TD",))

    # Si la première ligne ne correspond à aucune directive standard
    type_detecte = any(premiere_ligne.startswith(d.lower()) for t_list in TYPES_MERMAID.values() for d in t_list)

    if not type_detecte:
        directive_par_defaut = directives[0]
        texte = f"{directive_par_defaut}\n{texte}"

    return texte


def valider_syntaxe_mermaid(code: str) -> Tuple[bool, str]:
    """Effectue un contrôle statique préventif pour éviter les erreurs fréquentes de rendu."""
    if not code or not code.strip():
        return False, "Le code Mermaid est vide."

    lignes = [l for l in code.strip().splitlines() if l.strip()]
    if not lignes:
        return False, "Aucune instruction détectée."

    # Vérification basique des parenthèses/crochets appariés
    ouvrants = code.count("[") + code.count("(") + code.count("{")
    fermants = code.count("]") + code.count(")") + code.count("}")
    if ouvrants != fermants:
        LOG.warning("Déséquilibre potentiel de crochets/parenthèses dans le code Mermaid (%d vs %d)", ouvrants, fermants)

    return True, "Syntaxe validée."


def generer_page_html_interactive(
    titre: str,
    code_mermaid: str,
    sous_titre: str = "",
    theme: str = "sombre",
    nom_fichier: str = "",
) -> Path:
    """Crée une page HTML autonome haute fidélité avec Pan, Zoom, Dark Mode et export SVG."""
    if not nom_fichier:
        horodatage = int(time.time())
        nom_fichier = f"diagramme_{horodatage}.html"

    if not nom_fichier.endswith(".html"):
        nom_fichier += ".html"

    projet_actif = _SESSION_CTX.get("projet_actif")
    dossier_sortie = projet_actif if projet_actif and isinstance(projet_actif, Path) else _DOSSIER_DOCS
    chemin_html = dossier_sortie / nom_fichier

    code_echappe_js = code_mermaid.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    theme_mermaid = "dark" if theme.lower() in ("sombre", "dark") else "default"

    html_template = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{titre} — Visionneuse de Diagramme RIOT</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    :root {{
      --bg: #0f172a;
      --card: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #d97757;
      --accent-hover: #b85e40;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', -apple-system, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    header {{
      background: var(--card);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 10;
    }}
    .title-area h1 {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .title-area p {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 2px;
    }}
    .btn-group {{
      display: flex;
      gap: 8px;
    }}
    button {{
      background: #273549;
      color: var(--text);
      border: 1px solid var(--border);
      padding: 7px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}
    button:hover {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    button.primary {{
      background: var(--accent);
      border-color: var(--accent);
    }}
    button.primary:hover {{
      background: var(--accent-hover);
    }}
    #viewer-container {{
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      background: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%);
      overflow: auto;
      padding: 40px;
    }}
    #diagram-wrapper {{
      transform-origin: center center;
      transition: transform 0.1s ease-out;
      user-select: none;
    }}
    .mermaid {{
      opacity: 0;
      transition: opacity 0.3s ease;
    }}
    .mermaid.rendered {{
      opacity: 1;
    }}
    .floating-controls {{
      position: absolute;
      bottom: 20px;
      right: 20px;
      background: rgba(30, 41, 59, 0.85);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 6px;
      display: flex;
      gap: 6px;
      z-index: 20;
    }}
    .toast {{
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%) translateY(100px);
      background: #10b981;
      color: #fff;
      padding: 10px 18px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      opacity: 0;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      z-index: 100;
    }}
    .toast.show {{
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }}
  </style>
</head>
<body>
  <header>
    <div class="title-area">
      <h1>📐 {titre}</h1>
      <p>{sous_titre or "Diagramme technique interactif RIOT Studio"}</p>
    </div>
    <div class="btn-group">
      <button onclick="copierCode()">📋 Copier Mermaid</button>
      <button class="primary" onclick="telechargerSvg()">💾 Télécharger SVG</button>
    </div>
  </header>

  <main id="viewer-container">
    <div id="diagram-wrapper">
      <div class="mermaid" id="mermaid-target">
{code_mermaid}
      </div>
    </div>
  </main>

  <div class="floating-controls">
    <button onclick="changerZoom(0.2)" title="Zoom avant">➕</button>
    <button onclick="resetZoom()" title="Réinitialiser">100%</button>
    <button onclick="changerZoom(-0.2)" title="Zoom arrière">➖</button>
  </div>

  <div id="toast" class="toast">Code Mermaid copié !</div>

  <script>
    mermaid.initialize({{
      startOnLoad: true,
      theme: '{theme_mermaid}',
      securityLevel: 'loose',
      themeVariables: {{
        darkMode: true,
        background: '#0f172a',
        primaryColor: '#1e293b',
        primaryTextColor: '#f8fafc',
        primaryBorderColor: '#d97757',
        lineColor: '#e5c07b',
        secondaryColor: '#334155',
        tertiaryColor: '#1e293b'
      }}
    }});

    let zoomLevel = 1.0;
    function changerZoom(delta) {{
      zoomLevel = Math.max(0.3, Math.min(3.0, zoomLevel + delta));
      document.getElementById('diagram-wrapper').style.transform = `scale(${{zoomLevel}})`;
    }}

    function resetZoom() {{
      zoomLevel = 1.0;
      document.getElementById('diagram-wrapper').style.transform = `scale(1.0)`;
    }}

    function afficherToast(msg) {{
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 2200);
    }}

    function copierCode() {{
      const raw = `{code_echappe_js}`;
      navigator.clipboard.writeText(raw).then(() => {{
        afficherToast('Code Mermaid copié dans le presse-papier !');
      }});
    }}

    function telechargerSvg() {{
      const svg = document.querySelector('#mermaid-target svg');
      if (!svg) {{
        alert('Diagramme non encore rendu.');
        return;
      }}
      const svgData = new XMLSerializer().serializeToString(svg);
      const svgBlob = new Blob([svgData], {{ type: 'image/svg+xml;charset=utf-8' }});
      const svgUrl = URL.createObjectURL(svgBlob);
      const downloadLink = document.createElement('a');
      downloadLink.href = svgUrl;
      downloadLink.download = '{titre.lower().replace(" ", "_")}.svg';
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);
      afficherToast('Téléchargement du SVG démarré !');
    }}

    document.addEventListener("DOMContentLoaded", () => {{
      setTimeout(() => {{
        const target = document.getElementById('mermaid-target');
        if (target) target.classList.add('rendered');
      }}, 300);
    }});
  </script>
</body>
</html>"""

    chemin_html.write_text(html_template, encoding="utf-8")
    return chemin_html


@outil(
    nom="generer_diagramme",
    description="Génère un diagramme technique Mermaid d'architecture, de séquence, de base de données ou de processus, avec rendu en direct et visionneuse HTML interactive plein écran (Zoom/Pan/SVG).",
    parametres={
        "type": "object",
        "properties": {
            "titre": {
                "type": "string",
                "description": "Titre clair du diagramme (ex: 'Architecture Microservices RIOT', 'Flux d'authentification JWT').",
            },
            "type_diagramme": {
                "type": "string",
                "enum": ["flowchart", "sequence", "class", "state", "erd", "gitgraph", "gantt", "mindmap"],
                "description": "Type de diagramme technique (défaut: flowchart).",
            },
            "code_mermaid": {
                "type": "string",
                "description": "Code syntaxique Mermaid complet du diagramme. Doit être structuré, propre et sans balises externes.",
            },
            "sous_titre": {
                "type": "string",
                "description": "Sous-titre optionnel explicitant le contexte ou le composant.",
            },
            "theme": {
                "type": "string",
                "enum": ["sombre", "moderne", "corporate"],
                "description": "Thème visuel (défaut: sombre).",
            },
            "nom_fichier": {
                "type": "string",
                "description": "Nom du fichier HTML exporté (ex: 'architecture_keranos.html'). Généré automatiquement si omis.",
            },
        },
        "required": ["titre", "type_diagramme", "code_mermaid"],
    },
)
def generer_diagramme(
    titre: str,
    type_diagramme: str,
    code_mermaid: str,
    sous_titre: str = "",
    theme: str = "sombre",
    nom_fichier: str = "",
) -> str:
    """Génère le diagramme Mermaid, le valide et produit le viewer interactif."""
    code_nettoye = nettoyer_code_mermaid(code_mermaid, type_diagramme)
    ok, err = valider_syntaxe_mermaid(code_nettoye)
    if not ok:
        return f"❌ Erreur lors de la validation du diagramme Mermaid : {err}"

    if not nom_fichier:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", titre.lower())[:30].strip("_")
        nom_fichier = f"{slug}_{int(time.time())}.html"
    elif not nom_fichier.endswith(".html"):
        nom_fichier += ".html"

    chemin_html = generer_page_html_interactive(
        titre=titre,
        code_mermaid=code_nettoye,
        sous_titre=sous_titre,
        theme=theme,
        nom_fichier=nom_fichier,
    )

    url_viewer = f"/api/studio/document/telecharger?chemin={chemin_html.name}"

    return (
        f"✅ **Diagramme technique généré avec succès !**\n\n"
        f"### 📐 {titre}\n"
        f"*{sous_titre or 'Architecture & Flux Techniques'}*\n\n"
        f"```mermaid\n"
        f"{code_nettoye}\n"
        f"```\n\n"
        f"---\n"
        f"- 🖥️ **Visionneuse plein écran interactive (Zoom, Pan & Export SVG)** : [Ouvrir le diagramme]({url_viewer})\n"
        f"- 📁 **Fichier HTML local** : `{chemin_html}`"
    )
