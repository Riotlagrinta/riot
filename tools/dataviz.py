"""Outils de Visualisation de Données & Graphiques (DataViz) pour Kéranos / RIOT.

Génère des graphiques professionnels haute résolution (300 DPI) à partir de données Markdown ou JSON :
- Courbes d'évolution & Séries temporelles (avec remplissage en aire dégradée).
- Diagrammes en barres simples, groupées ou horizontales avec étiquettes de valeurs.
- Graphiques circulaires modernes en Anneau (Donut charts) avec pourcentages et légendes.
- Thèmes graphiques coordonnés : 'sombre' (RIOT Dark), 'moderne' (Clean Light) et 'corporate' (Navy).
- Export en PNG haute qualité intégrable directement dans le chat RIOT, dans les PDF et les slides PowerPoint.
"""
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib
matplotlib.use("Agg")  # Backend non-interactif obligatoire pour serveur/threads
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from core.cli import _SESSION_CTX
from core.registre import outil

LOG = logging.getLogger("riot.dataviz")
_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER_DOCS = _RACINE / "output_documents"
_DOSSIER_DOCS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# PALETTES GRAPHIQUES DE STYLE DATAVIZ
# ---------------------------------------------------------------------------
THEMES_DATAVIZ = {
    "sombre": {
        "bg_fig": "#0f172a",          # Dark Slate
        "bg_ax": "#1e293b",           # Carte Slate
        "text": "#f8fafc",            # Blanc cassé
        "text_muted": "#94a3b8",      # Gris ardoise
        "grid": "#334155",            # Ligne de grille subtile
        "palette": ["#d97757", "#06b6d4", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#3b82f6"],
    },
    "moderne": {
        "bg_fig": "#f8fafc",          # Blanc cassé
        "bg_ax": "#ffffff",           # Blanc pur
        "text": "#0f172a",            # Charcoal foncé
        "text_muted": "#64748b",      # Gris neutre
        "grid": "#e2e8f0",            # Grille très légère
        "palette": ["#d97757", "#2563eb", "#10b981", "#d97706", "#7c3aed", "#db2777", "#0284c7"],
    },
    "corporate": {
        "bg_fig": "#ffffff",
        "bg_ax": "#f8fafc",
        "text": "#111827",
        "text_muted": "#4b5563",
        "grid": "#e5e7eb",
        "palette": ["#1e3a8a", "#0284c7", "#0d9488", "#4f46e5", "#b45309", "#059669", "#64748b"],
    },
}


def _extraire_donnees_graphique(donnees_brutes: Any) -> Tuple[List[str], Dict[str, List[float]]]:
    """Parse et extrait les étiquettes d'axe X et les séries de valeurs numériques Y."""
    # 1. Cas Markdown Table (| Catégorie | Série 1 | Série 2 |)
    if isinstance(donnees_brutes, str):
        texte = donnees_brutes.strip()
        # Essai JSON
        if (texte.startswith("{") or texte.startswith("[")) and ("}" in texte or "]" in texte):
            try:
                obj = json.loads(texte)
                return _extraire_donnees_graphique(obj)
            except Exception:
                pass

        lignes = [l.strip() for l in texte.splitlines() if l.strip()]
        matrice = []
        for l in lignes:
            if l.startswith("|") and "|" in l[1:]:
                if re.match(r"^\|(\s*[-:]+[-|\s:]*)\|$", l):
                    continue
                cols = [c.strip() for c in l.strip("|").split("|")]
                matrice.append(cols)

        if len(matrice) >= 2:
            headers = matrice[0]
            labels = []
            series_dict = {h: [] for h in headers[1:]}

            for row in matrice[1:]:
                if not row or len(row) < 2:
                    continue
                # Ignorer lignes de totaux
                if row[0].lower().startswith(("total", "moyenne", "somme")):
                    continue
                labels.append(row[0])
                for idx, h in enumerate(headers[1:], start=1):
                    val_str = row[idx] if idx < len(row) else "0"
                    val_clean = re.sub(r"[^\d\.\,\-]", "", val_str).replace(",", ".")
                    try:
                        val_num = float(val_clean) if val_clean else 0.0
                    except ValueError:
                        val_num = 0.0
                    series_dict[h].append(val_num)

            return labels, series_dict

    # 2. Cas Dictionnaire direct { "labels": [...], "series": {...} ou "valeurs": [...] }
    if isinstance(donnees_brutes, dict):
        if "labels" in donnees_brutes:
            labels = [str(x) for x in donnees_brutes["labels"]]
            if "series" in donnees_brutes and isinstance(donnees_brutes["series"], dict):
                series = {}
                for k, v in donnees_brutes["series"].items():
                    series[k] = [float(x) for x in v]
                return labels, series
            if "valeurs" in donnees_brutes:
                return labels, {"Valeurs": [float(x) for x in donnees_brutes["valeurs"]]}

        # Dictionnaire simple Clé -> Valeur (ex: {"France": 150, "Togo": 90})
        labels = list(donnees_brutes.keys())
        vals = []
        for v in donnees_brutes.values():
            try:
                vals.append(float(re.sub(r"[^\d\.\,\-]", "", str(v)).replace(",", ".")))
            except ValueError:
                vals.append(0.0)
        return labels, {"Valeurs": vals}

    # 3. Cas Liste de dictionnaires (ex: [{"mois": "Jan", "ventes": 1500}, ...])
    if isinstance(donnees_brutes, list) and donnees_brutes and isinstance(donnees_brutes[0], dict):
        cles = list(donnees_brutes[0].keys())
        col_label = cles[0]
        labels = [str(d.get(col_label, "")) for d in donnees_brutes]
        series = {}
        for c in cles[1:]:
            series[c] = []
            for d in donnees_brutes:
                val_raw = str(d.get(c, "0"))
                val_clean = re.sub(r"[^\d\.\,\-]", "", val_raw).replace(",", ".")
                try:
                    series[c].append(float(val_clean) if val_clean else 0.0)
                except ValueError:
                    series[c].append(0.0)
        return labels, series

    return ["Élément 1", "Élément 2"], {"Série": [10.0, 20.0]}


@outil(
    nom="generer_graphique",
    mcp_expose=True,
    description="Génère un graphique de données professionnel haute résolution (PNG 300 DPI). "
                "Types supportés : 'barres' (comparaison), 'courbe' (évolution temporelle / trading / finance), "
                "'donut' ou 'camembert' (répartition), 'aire' (volume cumulé). "
                "Accepte un tableau Markdown, du JSON ou une liste de données, et retourne une image directement affichable.",
    parametres={
        "type": "object",
        "properties": {
            "type_graphique": {
                "type": "string",
                "enum": ["barres", "courbe", "donut", "camembert", "aire", "barres_horizontales"],
                "description": "Type de visualisation souhaité (défaut: barres).",
            },
            "titre": {
                "type": "string",
                "description": "Titre principal du graphique.",
            },
            "donnees": {
                "type": "string",
                "description": "Données à visualiser : tableau Markdown (| Libellé | Série 1 | ...), JSON ou dictionnaires.",
            },
            "sous_titre": {
                "type": "string",
                "description": "Sous-titre optionnel avec unité ou source (ex: 'Montants en k€ - Q1 2026').",
            },
            "axe_y": {
                "type": "string",
                "description": "Libellé de l'axe vertical (ex: 'Volume ($)', 'Latence (ms)', '%').",
            },
            "nom_fichier": {
                "type": "string",
                "description": "Nom du fichier image (ex: 'pnl_mensuel.png'). Généré automatiquement si omis.",
            },
            "theme": {
                "type": "string",
                "enum": ["sombre", "moderne", "corporate"],
                "description": "Thème graphique et palette de couleurs (défaut: sombre).",
            },
        },
        "required": ["titre", "donnees"],
    },
)
def generer_graphique(
    titre: str,
    donnees: Any,
    type_graphique: str = "barres",
    sous_titre: str = "",
    axe_y: str = "",
    nom_fichier: str = "",
    theme: str = "sombre",
) -> str:
    """Crée un graphique stylisé et l'enregistre en PNG haute résolution."""
    th = THEMES_DATAVIZ.get(theme.lower().strip(), THEMES_DATAVIZ["sombre"])
    palette = th["palette"]
    labels, series_dict = _extraire_donnees_graphique(donnees)

    if not labels:
        return "❌ Aucune donnée exploitable trouvée pour générer le graphique."

    if not nom_fichier:
        slug = re.sub(r"[^\w\-_]", "_", titre.lower().strip())[:28]
        horo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nom_fichier = f"{slug}_{horo}.png"
    if not nom_fichier.lower().endswith(".png"):
        nom_fichier += ".png"

    projet_actif = _SESSION_CTX.get("projet_actif")
    dossier_cible = projet_actif if (projet_actif and projet_actif.exists()) else _DOSSIER_DOCS
    chemin_complet = (dossier_cible / nom_fichier).resolve()

    # Création de la figure Matplotlib
    plt.close("all")
    fig, ax = plt.subplots(figsize=(10, 5.8), dpi=200)

    # Application des couleurs du thème
    fig.patch.set_facecolor(th["bg_fig"])
    ax.set_facecolor(th["bg_ax"])

    # Grille et axes
    ax.grid(True, linestyle="--", linewidth=0.6, color=th["grid"], alpha=0.7, zorder=0)
    for spine in ax.spines.values():
        spine.set_color(th["grid"])
        spine.set_linewidth(0.8)

    type_g = type_graphique.lower().strip()

    # -----------------------------------------------------------------------
    # 1. TYPE : DONUT / CAMEMBERT
    # -----------------------------------------------------------------------
    if type_g in ("donut", "camembert", "pie"):
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)

        premiere_serie = list(series_dict.values())[0] if series_dict else [1]
        couleurs = [palette[i % len(palette)] for i in range(len(labels))]

        wedgeprops = {"width": 0.45, "edgecolor": th["bg_fig"], "linewidth": 2} if type_g == "donut" else {"edgecolor": th["bg_fig"], "linewidth": 1.5}

        wedges, texts, autotexts = ax.pie(
            premiere_serie,
            labels=labels,
            autopct="%1.1f%%",
            startangle=140,
            colors=couleurs,
            wedgeprops=wedgeprops,
            pctdistance=0.75 if type_g == "donut" else 0.6,
            textprops={"color": th["text"], "fontsize": 10, "weight": "bold"},
        )
        for autotext in autotexts:
            autotext.set_color("#ffffff")
            autotext.set_fontsize(9.5)
            autotext.set_weight("bold")

    # -----------------------------------------------------------------------
    # 2. TYPE : COURBE / LINE / SÉRIE TEMPORELLE
    # -----------------------------------------------------------------------
    elif type_g in ("courbe", "line"):
        for s_idx, (nom_serie, valeurs) in enumerate(series_dict.items()):
            color = palette[s_idx % len(palette)]
            ax.plot(
                labels, valeurs,
                marker="o", markersize=6, linewidth=2.5,
                color=color, label=nom_serie if len(series_dict) > 1 else None,
                zorder=3
            )
            # Remplissage dégradé sous la courbe
            ax.fill_between(labels, valeurs, alpha=0.18, color=color, zorder=2)

        ax.tick_params(colors=th["text_muted"], labelsize=10)

    # -----------------------------------------------------------------------
    # 3. TYPE : AIRE / AREA
    # -----------------------------------------------------------------------
    elif type_g in ("aire", "area"):
        for s_idx, (nom_serie, valeurs) in enumerate(series_dict.items()):
            color = palette[s_idx % len(palette)]
            ax.fill_between(labels, valeurs, alpha=0.45, color=color, label=nom_serie, zorder=2)
            ax.plot(labels, valeurs, color=color, linewidth=2.0, zorder=3)
        ax.tick_params(colors=th["text_muted"], labelsize=10)

    # -----------------------------------------------------------------------
    # 4. TYPE : BARRES HORIZONTALES
    # -----------------------------------------------------------------------
    elif type_g == "barres_horizontales":
        premiere_serie = list(series_dict.values())[0] if series_dict else []
        y_pos = range(len(labels))
        couleurs = [palette[i % len(palette)] for i in range(len(labels))]

        bars = ax.barh(y_pos, premiere_serie, align="center", color=couleurs, height=0.6, zorder=3)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, color=th["text"], fontsize=10, weight="bold")
        ax.invert_yaxis()
        ax.tick_params(colors=th["text_muted"], labelsize=10)

        # Étiquettes de valeur à droite
        for bar in bars:
            w = bar.get_width()
            ax.text(w + (max(premiere_serie) * 0.015), bar.get_y() + bar.get_height() / 2, f"{w:g}",
                    ha="left", va="center", color=th["text"], fontsize=9.5, weight="bold")

    # -----------------------------------------------------------------------
    # 5. TYPE : BARRES VERTICALES (DÉFAUT / MULTI-SÉRIES)
    # -----------------------------------------------------------------------
    else:
        import numpy as np
        x = np.arange(len(labels))
        nb_series = len(series_dict)
        bar_width = 0.75 / max(1, nb_series)

        for s_idx, (nom_serie, valeurs) in enumerate(series_dict.items()):
            pos = x - (0.75 / 2) + (s_idx * bar_width) + (bar_width / 2) if nb_series > 1 else x
            color = palette[s_idx % len(palette)]
            bars = ax.bar(pos, valeurs, width=bar_width, color=color, label=nom_serie if nb_series > 1 else None, zorder=3, edgecolor=th["bg_fig"], linewidth=0.5)

            # Étiquettes de valeurs au-dessus des barres
            for bar in bars:
                h = bar.get_height()
                if h != 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, h + (max(valeurs) * 0.015), f"{h:g}",
                            ha="center", va="bottom", color=th["text"], fontsize=9, weight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(labels, color=th["text"], fontsize=10, weight="bold")
        ax.tick_params(colors=th["text_muted"], labelsize=10)

    # Titres et En-têtes
    plt.title(titre, fontsize=14, weight="bold", color=th["text"], pad=20, loc="left")
    if sous_titre:
        fig.text(0.125, 0.91, sous_titre, fontsize=9.5, color=th["text_muted"], style="italic")

    if axe_y and type_g not in ("donut", "camembert", "pie"):
        ax.set_ylabel(axe_y, color=th["text_muted"], fontsize=10, weight="bold")

    # Légende si multi-séries
    if len(series_dict) > 1 and type_g not in ("donut", "camembert", "pie"):
        legend = ax.legend(facecolor=th["bg_ax"], edgecolor=th["grid"], labelcolor=th["text"], fontsize=9)
        legend.get_frame().set_alpha(0.85)

    plt.tight_layout()

    try:
        fig.savefig(str(chemin_complet), format="png", bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

        taille_ko = round(chemin_complet.stat().st_size / 1024, 1)
        url_web = f"/api/studio/document/telecharger?chemin={chemin_complet.name}"

        return (
            f"✅ Graphique généré avec succès ({taille_ko} Ko, 300 DPI) !\n\n"
            f"- **Aperçu visuel immédiat** :\n\n"
            f"![{titre}]({url_web})\n\n"
            f"- **Fichier local** : `{chemin_complet}`\n"
            f"- **Téléchargement Web** : [📥 Télécharger {nom_fichier}]({url_web})\n"
            f"- **Type** : {type_graphique} | Thème : {theme}"
        )
    except Exception as e:
        plt.close("all")
        LOG.exception("Erreur lors de la sauvegarde du graphique")
        return f"❌ Erreur lors de la création du graphique : {e}"
