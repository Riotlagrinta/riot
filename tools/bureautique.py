"""Outils Bureautiques avancés pour Kéranos / RIOT : Génération et lecture Excel (.xlsx) et PowerPoint (.pptx).

Fournit un moteur complet basé sur openpyxl et python-pptx :
- Génération de classeurs Excel professionnels (en-têtes stylisés, volet figé, zebra striping, auto-largeur, formules).
- Génération de présentations PowerPoint 16:9 haute fidélité (couvertures, cartes KPI, tableaux, listes à puces).
- Lecture et extraction de données tabulaires et diapositives existantes.
- Enregistrement dans output_documents/ ou dans le projet actif, avec lien de téléchargement direct.
"""
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from core.cli import _SESSION_CTX
from core.registre import outil

LOG = logging.getLogger("riot.bureautique")
_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER_DOCS = _RACINE / "output_documents"
_DOSSIER_DOCS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# PALETTES DE THÈMES (EXCEL ET POWERPOINT)
# ---------------------------------------------------------------------------
THEMES_EXCEL = {
    "moderne": {
        "header_fill": "1E293B",      # Slate foncé
        "header_font": "FFFFFF",
        "zebra_fill": "F8FAFC",       # Gris très clair
        "border": "CBD5E1",
        "highlight": "D97757",        # Claude Coral
        "font_name": "Calibri",
    },
    "corporate": {
        "header_fill": "1E3A8A",      # Bleu Marine
        "header_font": "FFFFFF",
        "zebra_fill": "F1F5F9",
        "border": "CBD5E1",
        "highlight": "2563EB",
        "font_name": "Calibri",
    },
    "finance": {
        "header_fill": "065F46",      # Vert Émeraude
        "header_font": "FFFFFF",
        "zebra_fill": "F0FDF4",
        "border": "A7F3D0",
        "highlight": "10B981",
        "font_name": "Calibri",
    },
}

THEMES_PPT = {
    "moderne": {
        "bg_cover": RGBColor(15, 23, 42),       # Dark Slate #0f172a
        "bg_slide": RGBColor(248, 250, 252),    # Blanc cassé #f8fafc
        "title_cover": RGBColor(255, 255, 255),
        "title_slide": RGBColor(15, 23, 42),
        "accent": RGBColor(217, 119, 87),       # Claude Coral #d97757
        "accent2": RGBColor(59, 130, 246),      # Blue
        "text": RGBColor(51, 65, 85),
        "muted": RGBColor(148, 163, 184),
        "card_bg": RGBColor(255, 255, 255),
        "card_border": RGBColor(226, 232, 240),
    },
    "corporate": {
        "bg_cover": RGBColor(30, 58, 138),      # Navy #1e3a8a
        "bg_slide": RGBColor(255, 255, 255),
        "title_cover": RGBColor(255, 255, 255),
        "title_slide": RGBColor(30, 58, 138),
        "accent": RGBColor(37, 99, 235),        # Royal Blue
        "accent2": RGBColor(13, 148, 136),
        "text": RGBColor(31, 41, 55),
        "muted": RGBColor(107, 114, 128),
        "card_bg": RGBColor(248, 250, 252),
        "card_border": RGBColor(209, 213, 219),
    },
    "sombre": {
        "bg_cover": RGBColor(15, 23, 42),
        "bg_slide": RGBColor(15, 23, 42),
        "title_cover": RGBColor(255, 255, 255),
        "title_slide": RGBColor(255, 255, 255),
        "accent": RGBColor(217, 119, 87),
        "accent2": RGBColor(16, 185, 129),
        "text": RGBColor(226, 232, 240),
        "muted": RGBColor(148, 163, 184),
        "card_bg": RGBColor(30, 41, 59),
        "card_border": RGBColor(51, 65, 85),
    },
}


# ===========================================================================
# MODULE 1 : MOTEUR EXCEL (.XLSX)
# ===========================================================================
def _parser_donnees_tabulaires(donnees_brutes: Any) -> Dict[str, List[List[Any]]]:
    """Normalise divers formats d'entrée (Markdown table, liste de dicts, matrice, json) en dictionnaire de feuilles."""
    if isinstance(donnees_brutes, str):
        texte = donnees_brutes.strip()
        # Essai JSON
        if (texte.startswith("{") or texte.startswith("[")) and ("}" in texte or "]" in texte):
            try:
                obj = json.loads(texte)
                return _parser_donnees_tabulaires(obj)
            except Exception:
                pass

        # Parser tableau Markdown (| col1 | col2 |)
        lignes = [l.strip() for l in texte.splitlines() if l.strip()]
        matrice = []
        for l in lignes:
            if l.startswith("|") and "|" in l[1:]:
                # Ignorer les lignes de séparateur |---|---|
                if re.match(r"^\|(\s*[-:]+[-|\s:]*)\|$", l):
                    continue
                colonnes = [c.strip() for c in l.strip("|").split("|")]
                matrice.append(colonnes)
            elif "\t" in l:
                matrice.append([c.strip() for c in l.split("\t")])
            elif ";" in l:
                matrice.append([c.strip() for c in l.split(";")])

        if matrice:
            return {"Données": matrice}

        # Fallback texte simple
        return {"Feuille1": [[l] for l in lignes]}

    if isinstance(donnees_brutes, dict):
        feuilles = {}
        for nom_f, contenu in donnees_brutes.items():
            if isinstance(contenu, list):
                if contenu and isinstance(contenu[0], dict):
                    # Liste de dictionnaires -> Extraire les clés en ligne d'en-tête
                    headers = list(contenu[0].keys())
                    rows = [headers]
                    for d in contenu:
                        rows.append([d.get(h, "") for h in headers])
                    feuilles[nom_f] = rows
                elif contenu and isinstance(contenu[0], list):
                    feuilles[nom_f] = contenu
                else:
                    feuilles[nom_f] = [[item] for item in contenu]
            else:
                feuilles[nom_f] = [[str(contenu)]]
        return feuilles or {"Données": [["Information"], ["Aucune donnée"]]}

    if isinstance(donnees_brutes, list):
        if not donnees_brutes:
            return {"Données": [["Information"], ["Tableau vide"]]}
        if isinstance(donnees_brutes[0], dict):
            headers = list(donnees_brutes[0].keys())
            rows = [headers]
            for d in donnees_brutes:
                rows.append([d.get(h, "") for h in headers])
            return {"Données": rows}
        if isinstance(donnees_brutes[0], list):
            return {"Données": donnees_brutes}
        return {"Données": [["Élément"]] + [[item] for item in donnees_brutes]}

    return {"Données": [["Valeur"], [str(donnees_brutes)]]}


def _convertir_valeur_typée(val: Any) -> Any:
    """Tente de typer intelligemment les nombres, pourcentages et dates."""
    if not isinstance(val, str):
        return val
    s = val.strip()
    if not s:
        return ""
    # Entier
    if re.match(r"^-?\d+$", s):
        try:
            return int(s)
        except ValueError:
            pass
    # Flottant
    if re.match(r"^-?\d+[\.,]\d+$", s):
        try:
            return float(s.replace(",", "."))
        except ValueError:
            pass
    return s


@outil(
    nom="generer_excel",
    mcp_expose=True,
    description="Génère un classeur Microsoft Excel (.xlsx) professionnel avec en-têtes stylisés, "
                "lignes zébrées, volets figés et largeurs de colonnes ajustées automatiquement. "
                "Accepte un tableau Markdown, une liste de dictionnaires, du JSON ou une matrice de données multi-feuilles.",
    parametres={
        "type": "object",
        "properties": {
            "titre": {
                "type": "string",
                "description": "Titre du classeur ou sujet des données.",
            },
            "donnees": {
                "type": "string",
                "description": "Données tabulaires : tableau Markdown (| Col1 | Col2 |), JSON ou dictionnaire de feuilles.",
            },
            "nom_fichier": {
                "type": "string",
                "description": "Nom du fichier Excel (ex: 'analyse_financiere.xlsx'). Généré automatiquement si omis.",
            },
            "theme": {
                "type": "string",
                "enum": ["moderne", "corporate", "finance"],
                "description": "Palette graphique appliquée aux tableaux (défaut: moderne).",
            },
            "ouvrir_apres": {
                "type": "boolean",
                "description": "Ouvrir automatiquement le fichier dans Excel sur Windows après création.",
            },
        },
        "required": ["titre", "donnees"],
    },
)
def generer_excel(
    titre: str,
    donnees: Any,
    nom_fichier: str = "",
    theme: str = "moderne",
    ouvrir_apres: bool = False,
) -> str:
    """Génère un classeur Excel propre et stylisé."""
    th = THEMES_EXCEL.get(theme.lower().strip(), THEMES_EXCEL["moderne"])
    feuilles_dict = _parser_donnees_tabulaires(donnees)

    if not nom_fichier:
        slug = re.sub(r"[^\w\-_]", "_", titre.lower().strip())[:28]
        horo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nom_fichier = f"{slug}_{horo}.xlsx"
    if not nom_fichier.lower().endswith(".xlsx"):
        nom_fichier += ".xlsx"

    projet_actif = _SESSION_CTX.get("projet_actif")
    dossier_cible = projet_actif if (projet_actif and projet_actif.exists()) else _DOSSIER_DOCS
    chemin_complet = (dossier_cible / nom_fichier).resolve()

    wb = openpyxl.Workbook()
    # Supprimer la feuille par défaut si on va en créer d'autres
    premiere_feuille = True

    font_header = Font(name=th["font_name"], size=11, bold=True, color=th["header_font"])
    fill_header = PatternFill(start_color=th["header_fill"], end_color=th["header_fill"], fill_type="solid")
    fill_zebra = PatternFill(start_color=th["zebra_fill"], end_color=th["zebra_fill"], fill_type="solid")
    font_body = Font(name=th["font_name"], size=10)
    font_total = Font(name=th["font_name"], size=10, bold=True)

    border_side = Side(style="thin", color=th["border"])
    border_cell = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
    border_total = Border(
        left=border_side,
        right=border_side,
        top=Side(style="thin", color=th["border"]),
        bottom=Side(style="double", color=th["header_fill"])
    )

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    for nom_f, lignes in feuilles_dict.items():
        # Limiter le nom d'onglet à 31 caractères max (contrainte Excel)
        nom_onglet = re.sub(r"[\\/*?:\[\]]", "_", nom_f)[:31]
        if premiere_feuille:
            ws = wb.active
            ws.title = nom_onglet
            premiere_feuille = False
        else:
            ws = wb.create_sheet(title=nom_onglet)

        ws.views.sheetView[0].showGridLines = True
        ws.freeze_panes = "A2"  # Fige la ligne d'en-tête

        for r_idx, ligne in enumerate(lignes, start=1):
            is_header = (r_idx == 1)
            is_total = any(str(cell).strip().lower().startswith(("total", "moyenne", "somme")) for cell in ligne)

            for c_idx, cell_value in enumerate(ligne, start=1):
                val_typee = cell_value if is_header else _convertir_valeur_typée(cell_value)
                c = ws.cell(row=r_idx, column=c_idx, value=val_typee)

                if is_header:
                    c.font = font_header
                    c.fill = fill_header
                    c.alignment = align_center
                    c.border = border_cell
                else:
                    if is_total:
                        c.font = font_total
                        c.border = border_total
                    else:
                        c.font = font_body
                        c.border = border_cell
                        if r_idx % 2 == 0:
                            c.fill = fill_zebra

                    if isinstance(val_typee, (int, float)):
                        c.alignment = align_right
                        if isinstance(val_typee, float):
                            c.number_format = "#,##0.00"
                    else:
                        c.alignment = align_left

        # Auto-ajustement des largeurs de colonnes
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    try:
        wb.save(str(chemin_complet))
        taille_ko = round(chemin_complet.stat().st_size / 1024, 1)
        url_web = f"/api/claude/document/telecharger?chemin={chemin_complet.name}"

        if ouvrir_apres:
            try:
                os.startfile(str(chemin_complet))
            except Exception:
                pass

        nb_f = len(feuilles_dict)
        return (
            f"✅ Classeur Excel généré avec succès ({taille_ko} Ko, {nb_f} onglet{'s' if nb_f > 1 else ''}) !\n\n"
            f"- **Fichier local** : `{chemin_complet}`\n"
            f"- **Téléchargement Web** : [📥 Télécharger {nom_fichier}]({url_web})\n"
            f"- **Style appliqué** : Thème {theme} avec volet d'en-tête figé et largeurs automatiques."
        )
    except Exception as e:
        LOG.exception("Erreur lors de la sauvegarde du fichier Excel")
        return f"❌ Erreur lors de la création du classeur Excel : {e}"


@outil(
    nom="lire_excel",
    mcp_expose=True,
    description="Lit et extrait le contenu d'un classeur Excel (.xlsx). "
                "Permet d'analyser des feuilles de calcul, d'auditer des chiffres ou de résumer des tableaux.",
    parametres={
        "type": "object",
        "properties": {
            "chemin": {
                "type": "string",
                "description": "Chemin du fichier Excel (.xlsx).",
            },
            "feuille": {
                "type": "string",
                "description": "Nom de la feuille à lire (première feuille par défaut si omis).",
            },
            "max_lignes": {
                "type": "integer",
                "description": "Nombre maximum de lignes à lire (défaut: 50).",
            },
        },
        "required": ["chemin"],
    },
)
def lire_excel(chemin: str, feuille: str = "", max_lignes: int = 50) -> str:
    """Lit un fichier Excel et retourne un tableau Markdown lisible par le LLM."""
    p = Path(chemin)
    if not p.is_absolute():
        projet_actif = _SESSION_CTX.get("projet_actif")
        if projet_actif and (projet_actif / chemin).exists():
            p = projet_actif / chemin
        elif (_DOSSIER_DOCS / chemin).exists():
            p = _DOSSIER_DOCS / chemin

    if not p.exists() or not p.is_file():
        return f"❌ Fichier Excel introuvable : {chemin}"

    try:
        wb = openpyxl.load_workbook(str(p), data_only=True)
        nom_f = feuille if (feuille and feuille in wb.sheetnames) else wb.sheetnames[0]
        ws = wb[nom_f]

        lignes = []
        for row in ws.iter_rows(max_row=max_lignes, values_only=True):
            if any(cell is not None for cell in row):
                ligne_str = [str(c) if c is not None else "" for c in row]
                lignes.append(ligne_str)

        if not lignes:
            return f"La feuille '{nom_f}' est vide."

        # Rendu en tableau Markdown
        nb_cols = max(len(r) for r in lignes)
        lignes_pad = [r + [""] * (nb_cols - len(r)) for r in lignes]

        md_lignes = []
        md_lignes.append("| " + " | ".join(lignes_pad[0]) + " |")
        md_lignes.append("| " + " | ".join(["---"] * nb_cols) + " |")
        for r in lignes_pad[1:]:
            md_lignes.append("| " + " | ".join(r) + " |")

        resume = f"### 📊 Données de la feuille '{nom_f}' ({len(lignes_pad)} lignes affichées) :\n\n"
        resume += "\n".join(md_lignes)
        if ws.max_row and ws.max_row > max_lignes:
            resume += f"\n\n*(Note : {ws.max_row - max_lignes} lignes supplémentaires non affichées)*"
        return resume
    except Exception as e:
        return f"❌ Erreur lors de la lecture du fichier Excel : {e}"


# ===========================================================================
# MODULE 2 : MOTEUR POWERPOINT (.PPTX)
# ===========================================================================
def _parser_diapositives(contenu_brut: Any) -> List[Dict[str, Any]]:
    """Normalise une description de diapositives (Markdown structuré, JSON ou liste) en objets slides."""
    if isinstance(contenu_brut, list):
        slides = []
        for item in contenu_brut:
            if isinstance(item, dict):
                slides.append(item)
            elif isinstance(item, str):
                slides.append({"titre": "Diapositive", "points": [item]})
        return slides

    if isinstance(contenu_brut, str):
        texte = contenu_brut.strip()
        # Essai JSON
        if texte.startswith("[") and texte.endswith("]"):
            try:
                obj = json.loads(texte)
                if isinstance(obj, list):
                    return _parser_diapositives(obj)
            except Exception:
                pass

        # Découpage Markdown par séparateurs `---` ou par titres `## ` / `# `
        if re.search(r"\n\s*(?:---+|\*\*\*+)\s*\n", texte):
            parties = re.split(r"\n\s*(?:---+|\*\*\*+)\s*\n", texte)
        elif re.search(r"\n(?=#{1,3}\s+)", texte):
            parties = re.split(r"\n(?=#{1,3}\s+)", texte)
        else:
            parties = [texte]

        slides = []
        for part in parties:
            lignes = [l.strip() for l in part.splitlines() if l.strip()]
            if not lignes:
                continue
            titre_slide = "Diapositive"
            points = []
            cartes = []

            for l in lignes:
                if l.startswith("## ") or l.startswith("# "):
                    titre_slide = l.lstrip("#").strip()
                elif l.startswith(("- ", "* ")):
                    points.append(re.sub(r"^[-*]\s+", "", l))
                elif re.match(r"^\d+\.\s+", l):
                    points.append(re.sub(r"^\d+\.\s+", "", l))
                elif ":" in l and len(l) < 60:
                    # Possible carte KPI
                    k, v = l.split(":", 1)
                    cartes.append({"label": k.strip(), "valeur": v.strip()})
                else:
                    points.append(l)

            slide_dict = {"titre": titre_slide}
            if cartes and len(cartes) >= 2:
                slide_dict["cartes"] = cartes
            if points:
                slide_dict["points"] = points
            slides.append(slide_dict)

        return slides or [{"titre": "Présentation", "points": [texte]}]

    return [{"titre": "Présentation", "points": [str(contenu_brut)]}]


@outil(
    nom="generer_powerpoint",
    mcp_expose=True,
    description="Génère une présentation Microsoft PowerPoint (.pptx) moderne au format 16:9 écran large. "
                "Crée une diapositive de couverture percutante, des slides de contenu avec cartes KPI chiffrées, "
                "des listes de points clés aérées et des tableaux de données.",
    parametres={
        "type": "object",
        "properties": {
            "titre": {
                "type": "string",
                "description": "Titre principal de la présentation (affiché sur la slide de couverture).",
            },
            "sous_titre": {
                "type": "string",
                "description": "Sous-titre, nom de l'équipe ou contexte de la présentation.",
            },
            "diapositives": {
                "type": "string",
                "description": "Contenu des diapositives en Markdown (séparées par --- et ## Titre), JSON ou liste d'objets.",
            },
            "nom_fichier": {
                "type": "string",
                "description": "Nom du fichier PowerPoint (ex: 'pitch_projet.pptx'). Généré automatiquement si omis.",
            },
            "theme": {
                "type": "string",
                "enum": ["moderne", "corporate", "sombre"],
                "description": "Thème visuel de la présentation (défaut: moderne).",
            },
            "ouvrir_apres": {
                "type": "boolean",
                "description": "Ouvrir automatiquement la présentation dans PowerPoint sur Windows.",
            },
        },
        "required": ["titre", "diapositives"],
    },
)
def generer_powerpoint(
    titre: str,
    diapositives: Any,
    sous_titre: str = "",
    nom_fichier: str = "",
    theme: str = "moderne",
    ouvrir_apres: bool = False,
) -> str:
    """Génère une présentation PowerPoint 16:9 élégante et structurée."""
    th = THEMES_PPT.get(theme.lower().strip(), THEMES_PPT["moderne"])
    slides_data = _parser_diapositives(diapositives)

    if not nom_fichier:
        slug = re.sub(r"[^\w\-_]", "_", titre.lower().strip())[:28]
        horo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nom_fichier = f"{slug}_{horo}.pptx"
    if not nom_fichier.lower().endswith(".pptx"):
        nom_fichier += ".pptx"

    projet_actif = _SESSION_CTX.get("projet_actif")
    dossier_cible = projet_actif if (projet_actif and projet_actif.exists()) else _DOSSIER_DOCS
    chemin_complet = (dossier_cible / nom_fichier).resolve()

    prs = Presentation()
    # Format 16:9 HD standard (13.33 x 7.5 pouces)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # -----------------------------------------------------------------------
    # SLIDE 1 : COUVERTURE IMPACTANTE
    # -----------------------------------------------------------------------
    slide_couv = prs.slides.add_slide(blank_layout)

    # Fond de couverture
    bg_shape = slide_couv.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg_shape.fill.solid()
    bg_shape.fill.fore_color.rgb = th["bg_cover"]
    bg_shape.line.fill.background()

    # Barre d'accentuation verticale
    accent_bar = slide_couv.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(1.8), Inches(0.18), Inches(3.8))
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = th["accent"]
    accent_bar.line.fill.background()

    # Badge Claude RIOT
    badge_box = slide_couv.shapes.add_textbox(Inches(1.4), Inches(1.8), Inches(8.0), Inches(0.5))
    p_badge = badge_box.text_frame.paragraphs[0]
    p_badge.text = "CLAUDE RIOT — PRÉSENTATION STRATÉGIQUE"
    p_badge.font.size = Pt(11)
    p_badge.font.bold = True
    p_badge.font.color.rgb = th["accent"]

    # Titre de couverture
    title_box = slide_couv.shapes.add_textbox(Inches(1.4), Inches(2.3), Inches(10.5), Inches(2.2))
    title_box.text_frame.word_wrap = True
    p_title = title_box.text_frame.paragraphs[0]
    p_title.text = titre
    p_title.font.size = Pt(36)
    p_title.font.bold = True
    p_title.font.color.rgb = th["title_cover"]

    # Sous-titre
    sub_text = sous_titre or "Document de référence généré par Claude RIOT Studio"
    sub_box = slide_couv.shapes.add_textbox(Inches(1.4), Inches(4.5), Inches(10.5), Inches(1.2))
    sub_box.text_frame.word_wrap = True
    p_sub = sub_box.text_frame.paragraphs[0]
    p_sub.text = sub_text
    p_sub.font.size = Pt(16)
    p_sub.font.color.rgb = th["muted"]

    # Date en bas
    date_box = slide_couv.shapes.add_textbox(Inches(1.4), Inches(6.5), Inches(6.0), Inches(0.5))
    p_date = date_box.text_frame.paragraphs[0]
    p_date.text = datetime.now().strftime("%d %B %Y").upper()
    p_date.font.size = Pt(10)
    p_date.font.color.rgb = th["muted"]

    # -----------------------------------------------------------------------
    # SLIDES DE CONTENU
    # -----------------------------------------------------------------------
    for idx_slide, s_data in enumerate(slides_data, start=2):
        slide = prs.slides.add_slide(blank_layout)

        # Fond slide
        bg_s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
        bg_s.fill.solid()
        bg_s.fill.fore_color.rgb = th["bg_slide"]
        bg_s.line.fill.background()

        # En-tête de diapositive
        titre_slide = s_data.get("titre", f"Section {idx_slide - 1}")
        hdr_box = slide.shapes.add_textbox(Inches(0.9), Inches(0.6), Inches(11.5), Inches(1.0))
        hdr_p = hdr_box.text_frame.paragraphs[0]
        hdr_p.text = titre_slide
        hdr_p.font.size = Pt(24)
        hdr_p.font.bold = True
        hdr_p.font.color.rgb = th["title_slide"]

        # Filet sous le titre
        line_hdr = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.9), Inches(1.45), Inches(11.5), Inches(0.04))
        line_hdr.fill.solid()
        line_hdr.fill.fore_color.rgb = th["accent"]
        line_hdr.line.fill.background()

        cartes = s_data.get("cartes", [])
        points = s_data.get("points", [])

        top_content = 1.8

        # 1. Cartes KPI (si présentes)
        if cartes:
            nb_cartes = min(len(cartes), 4)
            card_width = (11.5 - (nb_cartes - 1) * 0.35) / nb_cartes
            for c_idx, c_info in enumerate(cartes[:nb_cartes]):
                c_left = 0.9 + c_idx * (card_width + 0.35)
                # Forme carte
                card_shape = slide.shapes.add_shape(
                    MSO_SHAPE.ROUNDED_RECTANGLE,
                    Inches(c_left), Inches(top_content), Inches(card_width), Inches(1.5)
                )
                card_shape.fill.solid()
                card_shape.fill.fore_color.rgb = th["card_bg"]
                card_shape.line.color.rgb = th["card_border"]
                card_shape.line.width = Pt(1)

                tf = card_shape.text_frame
                tf.word_wrap = True
                p_val = tf.paragraphs[0]
                p_val.text = str(c_info.get("valeur", ""))
                p_val.font.size = Pt(24)
                p_val.font.bold = True
                p_val.font.color.rgb = th["accent"]
                p_val.alignment = PP_ALIGN.CENTER

                p_lbl = tf.add_paragraph()
                p_lbl.text = str(c_info.get("label", ""))
                p_lbl.font.size = Pt(11)
                p_lbl.font.color.rgb = th["muted"]
                p_lbl.alignment = PP_ALIGN.CENTER

            top_content += 1.8

        # 2. Points clés / Paragraphes
        if points:
            txt_box = slide.shapes.add_textbox(Inches(0.9), Inches(top_content), Inches(11.5), Inches(4.5))
            tf_pts = txt_box.text_frame
            tf_pts.word_wrap = True

            for p_idx, pt_text in enumerate(points):
                p_item = tf_pts.paragraphs[0] if p_idx == 0 else tf_pts.add_paragraph()
                p_item.text = f"•  {pt_text}"
                p_item.font.size = Pt(14)
                p_item.font.color.rgb = th["text"]
                p_item.space_after = Pt(12)

        # Pied de slide (Numérotation & Titre)
        ftr_box = slide.shapes.add_textbox(Inches(0.9), Inches(6.9), Inches(11.5), Inches(0.4))
        p_ftr = ftr_box.text_frame.paragraphs[0]
        p_ftr.text = f"{titre}  |  Slide {idx_slide} sur {len(slides_data) + 1}"
        p_ftr.font.size = Pt(9)
        p_ftr.font.color.rgb = th["muted"]

    try:
        prs.save(str(chemin_complet))
        taille_ko = round(chemin_complet.stat().st_size / 1024, 1)
        url_web = f"/api/claude/document/telecharger?chemin={chemin_complet.name}"

        if ouvrir_apres:
            try:
                os.startfile(str(chemin_complet))
            except Exception:
                pass

        total_slides = len(slides_data) + 1
        return (
            f"✅ Présentation PowerPoint générée avec succès ({taille_ko} Ko, {total_slides} diapositives) !\n\n"
            f"- **Fichier local** : `{chemin_complet}`\n"
            f"- **Téléchargement Web** : [📥 Télécharger {nom_fichier}]({url_web})\n"
            f"- **Format** : 16:9 Écran large HD | Thème graphique : {theme}."
        )
    except Exception as e:
        LOG.exception("Erreur lors de la sauvegarde PowerPoint")
        return f"❌ Erreur lors de la création de la présentation PowerPoint : {e}"


@outil(
    nom="lire_powerpoint",
    mcp_expose=True,
    description="Lit et extrait le contenu textuel d'une présentation PowerPoint (.pptx) existante.",
    parametres={
        "type": "object",
        "properties": {
            "chemin": {
                "type": "string",
                "description": "Chemin vers le fichier PowerPoint (.pptx).",
            },
            "max_slides": {
                "type": "integer",
                "description": "Nombre maximum de diapositives à extraire (défaut: 20).",
            },
        },
        "required": ["chemin"],
    },
)
def lire_powerpoint(chemin: str, max_slides: int = 20) -> str:
    """Extrait le texte de chaque diapositive d'un fichier .pptx."""
    p = Path(chemin)
    if not p.is_absolute():
        projet_actif = _SESSION_CTX.get("projet_actif")
        if projet_actif and (projet_actif / chemin).exists():
            p = projet_actif / chemin
        elif (_DOSSIER_DOCS / chemin).exists():
            p = _DOSSIER_DOCS / chemin

    if not p.exists() or not p.is_file():
        return f"❌ Fichier PowerPoint introuvable : {chemin}"

    try:
        prs = Presentation(str(p))
        textes_slides = []
        for idx, slide in enumerate(prs.slides, start=1):
            if idx > max_slides:
                break
            textes_formes = []
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text_frame.text.strip():
                    textes_formes.append(shape.text_frame.text.strip())
            contenu_slide = "\n".join(textes_formes)
            textes_slides.append(f"--- [DIAPOSITIVE {idx}] ---\n{contenu_slide}")

        return "\n\n".join(textes_slides) or "La présentation ne contient aucun texte extractible."
    except Exception as e:
        return f"❌ Erreur lors de la lecture du fichier PowerPoint : {e}"
