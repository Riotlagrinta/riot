"""Outils de création et manipulation de documents PDF professionnels pour Kéranos / RIOT.

Fournit un moteur complet basé sur ReportLab (Platypus) et PyPDF :
- Génération de PDF haute fidélité à partir de contenu Markdown ou structuré.
- En-têtes, pieds de page numérotés automatiques (Page X sur Y), tables zébrées et palettes modernes.
- Extraction de texte et fusion de plusieurs PDF.
- Enregistrement dans output_pdf/ ou dans le projet actif, avec lien de téléchargement immédiat.
"""
import os
import re
import html
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Preformatted,
    KeepTogether,
    HRFlowable,
)

from core.cli import _SESSION_CTX
from core.config import reglage
from core.registre import outil

LOG = logging.getLogger("riot.pdf")
_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER_SORTIE_DEFAUT = _RACINE / "output_pdf"
_DOSSIER_SORTIE_DEFAUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# PALETTES GRAPHIQUES DE STYLE
# ---------------------------------------------------------------------------
THEMES = {
    "moderne": {
        "primary": colors.HexColor("#d97757"),      # Claude Coral
        "secondary": colors.HexColor("#1e293b"),    # Slate Dark
        "accent": colors.HexColor("#3b82f6"),       # Blue
        "text": colors.HexColor("#0f172a"),         # Charcoal
        "text_muted": colors.HexColor("#64748b"),   # Slate Muted
        "bg_table_hdr": colors.HexColor("#1e293b"), # Slate Header
        "text_table_hdr": colors.white,
        "bg_table_alt": colors.HexColor("#f8fafc"), # Light Zebra
        "bg_code": colors.HexColor("#f1f5f9"),      # Code Gray
        "border_color": colors.HexColor("#cbd5e1"), # Border
    },
    "corporate": {
        "primary": colors.HexColor("#1e3a8a"),      # Royal Navy
        "secondary": colors.HexColor("#0284c7"),    # Sky Blue
        "accent": colors.HexColor("#0d9488"),       # Teal
        "text": colors.HexColor("#111827"),         # Dark Gray
        "text_muted": colors.HexColor("#4b5563"),   # Cool Gray
        "bg_table_hdr": colors.HexColor("#1e3a8a"), # Navy Header
        "text_table_hdr": colors.white,
        "bg_table_alt": colors.HexColor("#f8fafc"),
        "bg_code": colors.HexColor("#f3f4f6"),
        "border_color": colors.HexColor("#d1d5db"),
    },
    "minimaliste": {
        "primary": colors.HexColor("#18181b"),      # Deep Black
        "secondary": colors.HexColor("#52525b"),    # Zinc Gray
        "accent": colors.HexColor("#27272a"),
        "text": colors.HexColor("#09090b"),
        "text_muted": colors.HexColor("#71717a"),
        "bg_table_hdr": colors.HexColor("#27272a"),
        "text_table_hdr": colors.white,
        "bg_table_alt": colors.HexColor("#fafafa"),
        "bg_code": colors.HexColor("#f4f4f5"),
        "border_color": colors.HexColor("#e4e4e7"),
    },
}


# ---------------------------------------------------------------------------
# CANVAS PERSONNALISÉ AVEC NUMÉROTATION CONTINUE "PAGE X SUR Y"
# ---------------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    """Calcule en deux passes le nombre total de pages pour imprimer 'Page X sur Y'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.doc_titre = "Document Claude RIOT"
        self.doc_footer = "Généré par Claude RIOT"

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        nb_total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._dessiner_en_tete_et_pied(nb_total)
            super().showPage()
        super().save()

    def _dessiner_en_tete_et_pied(self, nb_total: int):
        self.saveState()
        largeur, hauteur = A4
        marge_x = 54  # ~19mm
        marge_top = hauteur - 36
        marge_bottom = 32

        # En-tête uniquement sur les pages suivantes (page 2+)
        if self._pageNumber > 1:
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748b"))
            self.drawString(marge_x, marge_top, str(self.doc_titre)[:65])
            self.drawRightString(largeur - marge_x, marge_top, datetime.now().strftime("%d/%m/%Y"))
            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.5)
            self.line(marge_x, marge_top - 6, largeur - marge_x, marge_top - 6)

        # Pied de page sur toutes les pages
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawString(marge_x, marge_bottom, str(self.doc_footer))
        texte_page = f"Page {self._pageNumber} sur {nb_total}"
        self.drawRightString(largeur - marge_x, marge_bottom, texte_page)
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(marge_x, marge_bottom + 12, largeur - marge_x, marge_bottom + 12)

        self.restoreState()


# ---------------------------------------------------------------------------
# PARSEUR MARKDOWN VERS ELEMENTS PLATYPUS
# ---------------------------------------------------------------------------
def _nettoyer_inline_markdown(texte: str, code_color: str = "#d97757") -> str:
    """Convertit le gras, l'italique et le code inline en balises XML acceptées par ReportLab."""
    if not texte:
        return ""
    # Échapper les caractères XML réservés
    t = html.escape(texte)

    # Remplacer le gras **texte** ou __texte__
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r"<b>\1</b>", t)

    # Remplacer l'italique *texte* ou _texte_
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", t)

    # Remplacer le code inline `code`
    t = re.sub(r"`(.+?)`", rf'<font face="Courier" color="{code_color}"><b>\1</b></font>', t)

    return t


def _construire_tableau_flowable(lignes_raw: List[str], styles: dict, palette: dict) -> Table:
    """Parse une table Markdown (| Col 1 | Col 2 |) en Flowable Table stylisée."""
    data = []
    for raw in lignes_raw:
        raw_nettoyee = raw.strip().strip("|")
        colonnes = [c.strip() for c in raw_nettoyee.split("|")]
        data.append(colonnes)

    if not data:
        return Spacer(1, 2)

    nb_cols = max(len(row) for row in data)
    # Égaliser les colonnes
    data_pad = []
    for row in data:
        row_pad = row + [""] * (nb_cols - len(row))
        data_pad.append(row_pad)

    # Transformer chaque cellule en Paragraph avec style adapté
    flowable_data = []
    for r_idx, row in enumerate(data_pad):
        row_flow = []
        is_header = (r_idx == 0)
        st = styles["TableHeader"] if is_header else styles["TableCell"]
        for cell_text in row:
            p = Paragraph(_nettoyer_inline_markdown(cell_text), st)
            row_flow.append(p)
        flowable_data.append(row_flow)

    largeur_totale = 487  # A4 largeur utile (~172mm)
    col_width = largeur_totale / max(1, nb_cols)

    t = Table(flowable_data, colWidths=[col_width] * nb_cols)
    t_style = [
        ("BACKGROUND", (0, 0), (-1, 0), palette["bg_table_hdr"]),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, palette["border_color"]),
    ]
    # Alternance de couleurs (zebra stripes)
    for i in range(1, len(data_pad)):
        if i % 2 == 0:
            t_style.append(("BACKGROUND", (0, i), (-1, i), palette["bg_table_alt"]))

    t.setStyle(TableStyle(t_style))
    return t


def _markdown_vers_flowables(texte_md: str, palette: dict, styles: dict) -> List[Any]:
    """Analyse un texte en Markdown et produit une liste de Flowables ReportLab."""
    story = []
    lignes = texte_md.strip().splitlines()
    i = 0
    total = len(lignes)

    while i < total:
        ligne = lignes[i].rstrip()
        ligne_strip = ligne.strip()

        # 1. Ligne vide
        if not ligne_strip:
            i += 1
            continue

        # 2. Séparateur horizontal (--- ou ***)
        if re.match(r"^(\-{3,}|\*{3,})$", ligne_strip):
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.8, color=palette["border_color"], spaceBefore=6, spaceAfter=8))
            i += 1
            continue

        # 3. Bloc de Code (```)
        if ligne_strip.startswith("```"):
            lang = ligne_strip.lstrip("`").strip()
            bloc_code = []
            i += 1
            while i < total and not lignes[i].strip().startswith("```"):
                bloc_code.append(lignes[i])
                i += 1
            i += 1  # Sauter le ``` de fin
            code_str = "\n".join(bloc_code)
            p_code = Preformatted(html.escape(code_str), styles["CodeBlock"])
            # Encadrer le code dans un tableau avec fond gris
            t_code = Table([[p_code]], colWidths=[487])
            t_code.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), palette["bg_code"]),
                ("BOX", (0, 0), (-1, -1), 0.8, palette["border_color"]),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(Spacer(1, 4))
            story.append(t_code)
            story.append(Spacer(1, 6))
            continue

        # 4. Tableaux Markdown (| col1 | col2 |)
        if ligne_strip.startswith("|") and "|" in ligne_strip[1:]:
            lignes_table = []
            while i < total and lignes[i].strip().startswith("|"):
                l_cur = lignes[i].strip()
                # Ignorer la ligne de séparation |---|---|
                if not re.match(r"^\|(\s*[-:]+[-|\s:]*)\|$", l_cur):
                    lignes_table.append(l_cur)
                i += 1
            if lignes_table:
                story.append(Spacer(1, 6))
                story.append(_construire_tableau_flowable(lignes_table, styles, palette))
                story.append(Spacer(1, 6))
            continue

        # 5. Titre H1 (# )
        if ligne_strip.startswith("# "):
            txt = ligne_strip[2:].strip()
            story.append(Spacer(1, 10))
            story.append(Paragraph(_nettoyer_inline_markdown(txt), styles["Heading1Custom"]))
            story.append(HRFlowable(width="100%", thickness=1.2, color=palette["primary"], spaceBefore=4, spaceAfter=8))
            i += 1
            continue

        # 6. Titre H2 (## )
        if ligne_strip.startswith("## "):
            txt = ligne_strip[3:].strip()
            story.append(Spacer(1, 8))
            story.append(Paragraph(_nettoyer_inline_markdown(txt), styles["Heading2Custom"]))
            i += 1
            continue

        # 7. Titre H3 (### )
        if ligne_strip.startswith("### "):
            txt = ligne_strip[4:].strip()
            story.append(Spacer(1, 6))
            story.append(Paragraph(_nettoyer_inline_markdown(txt), styles["Heading3Custom"]))
            i += 1
            continue

        # 8. Citation (> )
        if ligne_strip.startswith(">"):
            txt = ligne_strip.lstrip(">").strip()
            p_quote = Paragraph(_nettoyer_inline_markdown(txt), styles["QuoteCustom"])
            t_quote = Table([[p_quote]], colWidths=[487])
            t_quote.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), palette["bg_table_alt"]),
                ("LINEBEFORE", (0, 0), (0, -1), 3.0, palette["primary"]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(Spacer(1, 4))
            story.append(t_quote)
            story.append(Spacer(1, 4))
            i += 1
            continue

        # 9. Listes à puces (- ou * )
        if re.match(r"^[-*]\s+", ligne_strip):
            txt = re.sub(r"^[-*]\s+", "", ligne_strip)
            bullet_html = f"&bull; {_nettoyer_inline_markdown(txt)}"
            story.append(Paragraph(bullet_html, styles["BulletCustom"]))
            i += 1
            continue

        # 10. Listes numérotées (1. )
        m_num = re.match(r"^(\d+)\.\s+(.*)", ligne_strip)
        if m_num:
            num = m_num.group(1)
            txt = m_num.group(2)
            num_html = f"<b>{num}.</b> {_nettoyer_inline_markdown(txt)}"
            story.append(Paragraph(num_html, styles["NumberedCustom"]))
            i += 1
            continue

        # 11. Paragraphe standard
        story.append(Paragraph(_nettoyer_inline_markdown(ligne_strip), styles["BodyCustom"]))
        story.append(Spacer(1, 3))
        i += 1

    return story


# ---------------------------------------------------------------------------
# OUTILS ENREGISTRÉS DANS LE REGISTRE RIOT
# ---------------------------------------------------------------------------
@outil(
    nom="generer_pdf",
    mcp_expose=True,
    description="Génère un document PDF professionnel et élégant à partir de texte ou de contenu Markdown. "
                "Idéal pour rapports d'audit, plans d'action, fiches de récapitulation, factures ou documentations. "
                "Gère la mise en page, les titres H1/H2/H3, listes, blocs de code, tableaux zébrés et numérotation de pages.",
    parametres={
        "type": "object",
        "properties": {
            "titre": {
                "type": "string",
                "description": "Titre principal du document affiché en tête de page.",
            },
            "contenu_markdown": {
                "type": "string",
                "description": "Contenu du document formaté en Markdown (titres #, listes, tableaux, code, texte).",
            },
            "sous_titre": {
                "type": "string",
                "description": "Sous-titre optionnel ou résumé d'en-tête (ex: 'Rapport technique - v1.0').",
            },
            "nom_fichier": {
                "type": "string",
                "description": "Nom du fichier PDF (ex: 'rapport_audit.pdf'). Si omis, généré automatiquement.",
            },
            "theme": {
                "type": "string",
                "enum": ["moderne", "corporate", "minimaliste"],
                "description": "Thème graphique et palette de couleurs du document (défaut: moderne).",
            },
            "ouvrir_apres": {
                "type": "boolean",
                "description": "Ouvrir automatiquement le PDF avec l'application par défaut après création.",
            },
        },
        "required": ["titre", "contenu_markdown"],
    },
)
def generer_pdf(
    titre: str,
    contenu_markdown: str,
    sous_titre: str = "",
    nom_fichier: str = "",
    theme: str = "moderne",
    ouvrir_apres: bool = False,
) -> str:
    """Génère un fichier PDF complet et élégant à partir de contenu Markdown."""
    palette = THEMES.get(theme.lower().strip(), THEMES["moderne"])

    # 1. Détermination du chemin de sortie
    if not nom_fichier:
        slug = re.sub(r"[^\w\-_]", "_", titre.lower().strip())[:30]
        horo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nom_fichier = f"{slug}_{horo}.pdf"
    if not nom_fichier.lower().endswith(".pdf"):
        nom_fichier += ".pdf"

    # Vérifier si un projet actif est défini dans la session
    projet_actif = _SESSION_CTX.get("projet_actif")
    if projet_actif and isinstance(projet_actif, Path) and projet_actif.exists():
        dossier_cible = projet_actif
    else:
        dossier_cible = _DOSSIER_SORTIE_DEFAUT

    chemin_complet = (dossier_cible / nom_fichier).resolve()

    # 2. Configuration des styles ReportLab
    base_styles = getSampleStyleSheet()

    styles = {
        "DocTitle": ParagraphStyle(
            "DocTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=palette["primary"],
            alignment=0,
            spaceAfter=4,
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=11,
            leading=15,
            textColor=palette["text_muted"],
            spaceAfter=12,
        ),
        "Heading1Custom": ParagraphStyle(
            "Heading1Custom",
            parent=base_styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=palette["secondary"],
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "Heading2Custom": ParagraphStyle(
            "Heading2Custom",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=palette["primary"],
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "Heading3Custom": ParagraphStyle(
            "Heading3Custom",
            parent=base_styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=palette["text"],
            spaceBefore=6,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "BodyCustom": ParagraphStyle(
            "BodyCustom",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=palette["text"],
            spaceAfter=2,
        ),
        "BulletCustom": ParagraphStyle(
            "BulletCustom",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=palette["text"],
            leftIndent=14,
            spaceAfter=2,
        ),
        "NumberedCustom": ParagraphStyle(
            "NumberedCustom",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=palette["text"],
            leftIndent=14,
            spaceAfter=2,
        ),
        "QuoteCustom": ParagraphStyle(
            "QuoteCustom",
            parent=base_styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9.5,
            leading=13.5,
            textColor=palette["text_muted"],
        ),
        "CodeBlock": ParagraphStyle(
            "CodeBlock",
            parent=base_styles["Normal"],
            fontName="Courier",
            fontSize=8.5,
            leading=11.5,
            textColor=palette["secondary"],
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=palette["text_table_hdr"],
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=palette["text"],
        ),
    }

    # 3. Construction de la Story (contenu ordonné)
    story = []

    # En-tête Titre et date
    story.append(Paragraph(html.escape(titre), styles["DocTitle"]))
    if sous_titre:
        story.append(Paragraph(html.escape(sous_titre), styles["DocSubtitle"]))

    date_str = f"Date de génération : {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    story.append(Paragraph(f'<font size="8" color="#64748b">{date_str}</font>', styles["BodyCustom"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=palette["primary"], spaceBefore=6, spaceAfter=14))

    # Conversion du contenu Markdown
    flowables_corps = _markdown_vers_flowables(contenu_markdown, palette, styles)
    story.extend(flowables_corps)

    # 4. Compilation du PDF via SimpleDocTemplate avec NumberedCanvas
    try:
        doc = SimpleDocTemplate(
            str(chemin_complet),
            pagesize=A4,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        def on_first_page(canvas_obj, document):
            canvas_obj.doc_titre = titre
            canvas_obj.doc_footer = f"Document généré par Claude RIOT — {nom_fichier}"

        doc.build(story, canvasmaker=NumberedCanvas)
        taille_ko = round(chemin_complet.stat().st_size / 1024, 1)

        # Lien de téléchargement web pour Claude Studio
        url_web = f"/api/claude/pdf/telecharger?chemin={chemin_complet.name}"

        # Ouverture locale si demandée
        if ouvrir_apres:
            try:
                os.startfile(str(chemin_complet))
            except Exception:
                pass

        return (
            f"✅ Document PDF généré avec succès ({taille_ko} Ko) !\n\n"
            f"- **Fichier local** : `{chemin_complet}`\n"
            f"- **Téléchargement direct (Web)** : [📥 Télécharger {nom_fichier}]({url_web})\n"
            f"- **Thème appliqué** : {theme} | **Pages** : A4 avec numérotation automatique"
        )
    except Exception as e:
        LOG.exception("Erreur lors de la génération du PDF")
        return f"❌ Erreur lors de la création du PDF : {e}"


@outil(
    nom="extraire_texte_pdf",
    mcp_expose=True,
    description="Lit et extrait le contenu textuel d'un document PDF existant (pypdf). "
                "Permet d'analyser, de résumer ou de vérifier des documents PDF locaux.",
    parametres={
        "type": "object",
        "properties": {
            "chemin": {
                "type": "string",
                "description": "Chemin vers le fichier PDF (absolu ou relatif au projet actif ou output_pdf).",
            },
            "max_pages": {
                "type": "integer",
                "description": "Nombre maximum de pages à extraire (défaut: 15).",
            },
        },
        "required": ["chemin"],
    },
)
def extraire_texte_pdf(chemin: str, max_pages: int = 15) -> str:
    """Extrait le texte brut d'un fichier PDF page par page."""
    from pypdf import PdfReader

    p = Path(chemin)
    if not p.is_absolute():
        # Vérifier dans le projet actif puis dans output_pdf
        projet_actif = _SESSION_CTX.get("projet_actif")
        if projet_actif and (projet_actif / chemin).exists():
            p = projet_actif / chemin
        elif (_DOSSIER_SORTIE_DEFAUT / chemin).exists():
            p = _DOSSIER_SORTIE_DEFAUT / chemin

    if not p.exists() or not p.is_file():
        return f"❌ Fichier PDF introuvable : {chemin}"

    try:
        reader = PdfReader(str(p))
        nb_pages_totales = len(reader.pages)
        pages_a_lire = min(nb_pages_totales, max_pages)

        textes = []
        for idx in range(pages_a_lire):
            page = reader.pages[idx]
            txt = page.extract_text() or ""
            textes.append(f"--- [PAGE {idx + 1} / {nb_pages_totales}] ---\n{txt.strip()}")

        resultat = "\n\n".join(textes)
        if nb_pages_totales > max_pages:
            resultat += f"\n\n[... Note : {nb_pages_totales - max_pages} page(s) supplémentaires non affichées ...]"

        return resultat or "Le document ne contient aucun texte extractible (il s'agit peut-être d'un scan ou d'images)."
    except Exception as e:
        return f"❌ Erreur lors de la lecture du PDF : {e}"


@outil(
    nom="fusionner_pdfs",
    mcp_expose=True,
    description="Fusionne plusieurs fichiers PDF existants en un seul document consolidé.",
    parametres={
        "type": "object",
        "properties": {
            "fichiers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste ordonnée des chemins des fichiers PDF à fusionner.",
            },
            "nom_fichier_sortie": {
                "type": "string",
                "description": "Nom du fichier PDF fusionné de sortie (ex: 'fusion_complete.pdf').",
            },
        },
        "required": ["fichiers"],
    },
)
def fusionner_pdfs(fichiers: List[str], nom_fichier_sortie: str = "") -> str:
    """Assemble plusieurs fichiers PDF en un document final unique."""
    from pypdf import PdfWriter

    if not fichiers or len(fichiers) < 2:
        return "❌ Il faut au moins 2 fichiers PDF pour effectuer une fusion."

    if not nom_fichier_sortie:
        horo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nom_fichier_sortie = f"fusion_{horo}.pdf"
    if not nom_fichier_sortie.lower().endswith(".pdf"):
        nom_fichier_sortie += ".pdf"

    projet_actif = _SESSION_CTX.get("projet_actif")
    dossier_cible = projet_actif if (projet_actif and projet_actif.exists()) else _DOSSIER_SORTIE_DEFAUT
    chemin_sortie = (dossier_cible / nom_fichier_sortie).resolve()

    writer = PdfWriter()
    ajoutes = 0
    try:
        for f_nom in fichiers:
            p = Path(f_nom)
            if not p.is_absolute():
                if projet_actif and (projet_actif / f_nom).exists():
                    p = projet_actif / f_nom
                elif (_DOSSIER_SORTIE_DEFAUT / f_nom).exists():
                    p = _DOSSIER_SORTIE_DEFAUT / f_nom

            if p.exists() and p.is_file():
                writer.append(str(p))
                ajoutes += 1
            else:
                return f"❌ Fichier manquant pour la fusion : {f_nom}"

        with open(chemin_sortie, "wb") as f_out:
            writer.write(f_out)
        writer.close()

        taille_ko = round(chemin_sortie.stat().st_size / 1024, 1)
        url_web = f"/api/claude/pdf/telecharger?chemin={chemin_sortie.name}"
        return (
            f"✅ {ajoutes} fichiers PDF fusionnés avec succès dans `{chemin_sortie}` ({taille_ko} Ko) !\n"
            f"[📥 Télécharger le PDF fusionné]({url_web})"
        )
    except Exception as e:
        return f"❌ Échec de la fusion PDF : {e}"
