"""Outil `seo-audit` : audit technique SEO complet (Google Search, Mobile-First, Schema.org, robots/sitemap).

Analyse soit une URL publique en ligne (protegee anti-SSRF), soit un fichier HTML/Next.js local,
et genere un score /100, les blocages critiques et des extraits corriges prets a copier.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from core.registre import outil
from tools.web import _USER_AGENT, _nettoyer_html_texte, _valider_url_publique


def _resoudre_fichier_local(chemin: str) -> Path:
    p = Path((chemin or "").strip().strip('"').strip("'"))
    if p.is_absolute():
        return p
    try:
        from core.cli import _SESSION_CTX
        proj = _SESSION_CTX.get("projet_actif")
        if isinstance(proj, Path) and proj.exists():
            return proj / p
    except Exception:
        pass
    return Path.cwd() / p


def _verifier_ressource_site(url_racine: str, chemin: str) -> Tuple[bool, str]:
    try:
        r = requests.get(f"{url_racine.rstrip('/')}{chemin}", headers={"User-Agent": _USER_AGENT}, timeout=5)
        return (r.status_code == 200), (r.text[:600] if r.status_code == 200 else f"HTTP {r.status_code}")
    except Exception as e:
        return False, str(e)


def _extraire_meta_attr(brut: str, attr_name: str, attr_val: str) -> str:
    p1 = re.compile(
        rf'<meta\s+[^>]*{attr_name}=["\']{re.escape(attr_val)}["\'][^>]*content=["\'](.*?)["\']',
        re.IGNORECASE | re.DOTALL,
    )
    p2 = re.compile(
        rf'<meta\s+[^>]*content=["\'](.*?)["\'][^>]*{attr_name}=["\']{re.escape(attr_val)}["\']',
        re.IGNORECASE | re.DOTALL,
    )
    m = p1.search(brut) or p2.search(brut)
    return html.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else ""


def auditer_html_seo(
    brut: str,
    url: str = "",
    mot_cle_cible: str = "",
    est_nextjs: bool = False,
) -> Dict[str, Any]:
    """Calcule un audit SEO structure sur du HTML ou un composant Next.js."""
    critiques: List[str] = []
    importants: List[str] = []
    optimisations: List[str] = []
    reussis: List[str] = []
    score = 100

    # 1. Title
    m_title = re.search(r"<title[^>]*>(.*?)</title>", brut, re.IGNORECASE | re.DOTALL)
    title = html.unescape(re.sub(r"\s+", " ", m_title.group(1)).strip()) if m_title else ""
    if not title and est_nextjs:
        m_nxt_t = re.search(r"title\s*:\s*['\"`]([^'\"`]+)['\"`]", brut)
        if m_nxt_t:
            title = m_nxt_t.group(1).strip()

    if not title:
        score -= 18
        critiques.append("Balise `<title>` absente (indispensable pour le classement et le clic sur Google).")
    elif len(title) < 25 or len(title) > 65:
        score -= 6
        importants.append(f"`<title>` hors plage optimale ({len(title)} car., idéal : 30–60) : « {title[:65]} ».")
    else:
        reussis.append(f"`<title>` conforme ({len(title)} car.) : « {title} ».")

    # 2. Meta description
    desc = _extraire_meta_attr(brut, "name", "description")
    if not desc and est_nextjs:
        m_nxt_d = re.search(r"description\s*:\s*['\"`]([^'\"`]+)['\"`]", brut)
        if m_nxt_d:
            desc = m_nxt_d.group(1).strip()
    if not desc:
        score -= 14
        critiques.append("`<meta name=\"description\">` absente (Google générera un extrait aléatoire).")
    elif len(desc) < 90 or len(desc) > 165:
        score -= 5
        importants.append(f"`meta description` à ajuster ({len(desc)} car., idéal : 110–160).")
    else:
        reussis.append(f"`meta description` conforme ({len(desc)} car.).")

    # 3. Robots noindex / Canonical / Viewport / Lang
    robots_meta = _extraire_meta_attr(brut, "name", "robots")
    if "noindex" in robots_meta.lower():
        score -= 30
        critiques.append("BLOQUANT : `<meta name=\"robots\" content=\"noindex\">` empêche Google d'indexer cette page !")

    has_canonical = bool(re.search(r'<link[^>]+rel=["\']canonical["\']', brut, re.IGNORECASE)) or (
        est_nextjs and "canonical" in brut
    )
    if not has_canonical:
        score -= 7
        importants.append("Balise `<link rel=\"canonical\">` manquante (risque de contenu dupliqué).")
    else:
        reussis.append("Lien canonique présent.")

    has_viewport = bool(re.search(r'<meta[^>]+name=["\']viewport["\']', brut, re.IGNORECASE))
    if not has_viewport and not est_nextjs:
        score -= 10
        critiques.append("`<meta name=\"viewport\">` absent (pénalisé par l'indexation Mobile-First de Google).")

    has_lang = bool(re.search(r'<html[^>]+lang=["\'][a-z]{2}', brut, re.IGNORECASE))
    if not has_lang and not est_nextjs:
        score -= 5
        optimisations.append("Attribut `lang=\"fr\"` (ou langue cible) manquant sur `<html>`.")

    # 4. H1 / H2 / Images alt / Contenu texte
    h1_list = re.findall(r"<h1[^>]*>(.*?)</h1>", brut, re.IGNORECASE | re.DOTALL)
    h2_list = re.findall(r"<h2[^>]*>(.*?)</h2>", brut, re.IGNORECASE | re.DOTALL)
    if len(h1_list) == 0:
        score -= 12
        critiques.append("Aucune balise `<h1>` détectée sur la page.")
    elif len(h1_list) > 1:
        score -= 6
        importants.append(f"{len(h1_list)} balises `<h1>` détectées (n'en garder qu'un seul principal par page).")
    else:
        reussis.append("Un unique `<h1>` bien défini.")

    if not h2_list:
        score -= 5
        optimisations.append("Aucune balise `<h2>` pour structurer les sous-parties thématiques.")

    imgs = re.findall(r"<img\b[^>]*>", brut, re.IGNORECASE)
    imgs_sans_alt = [im for im in imgs if not re.search(r'\balt=["\'][^"\']+["\']', im, re.IGNORECASE)]
    if imgs_sans_alt:
        score -= min(10, len(imgs_sans_alt) * 3)
        importants.append(f"{len(imgs_sans_alt)} image(s) `<img>` sans attribut `alt` descriptif.")

    texte_propre = _nettoyer_html_texte(brut)
    nb_mots = len(texte_propre.split())
    if not est_nextjs and nb_mots < 250:
        score -= 8
        importants.append(f"Contenu textuel faible ({nb_mots} mots ; viser >= 300 mots utiles pour bien se positionner).")

    # 5. Open Graph & Schema.org JSON-LD
    og_ok = bool(_extraire_meta_attr(brut, "property", "og:title")) and bool(_extraire_meta_attr(brut, "property", "og:image"))
    if not og_ok and not (est_nextjs and "openGraph" in brut):
        score -= 6
        optimisations.append("Balises Open Graph (`og:title`, `og:description`, `og:image`) incomplètes pour les partages sociaux.")
    else:
        reussis.append("Métadonnées Open Graph configurées.")

    has_jsonld = bool(re.search(r'type=["\']application/ld\+json["\']', brut, re.IGNORECASE))
    if not has_jsonld:
        score -= 7
        optimisations.append("Données structurées JSON-LD (`Schema.org`) absentes (utiles pour les résultats enrichis Google).")
    else:
        reussis.append("Schema.org JSON-LD détecté.")

    # 6. Mot-clé cible
    kw = (mot_cle_cible or "").strip().lower()
    if kw:
        dans_title = kw in title.lower()
        dans_h1 = any(kw in re.sub(r"<[^>]+>", "", h).lower() for h in h1_list)
        if not dans_title or not dans_h1:
            score -= 6
            importants.append(f"Mot-clé cible « {mot_cle_cible} » absent du `<title>` ou du `<h1>`.")
        else:
            reussis.append(f"Mot-clé cible « {mot_cle_cible} » présent dans `<title>` et `<h1>`.")

    # 7. Checks site en ligne (HTTPS, robots.txt, sitemap.xml)
    if url:
        parsed = urllib.parse.urlparse(url)
        racine = f"{parsed.scheme}://{parsed.netloc}"
        if parsed.scheme != "https":
            score -= 12
            critiques.append("Site servi en HTTP non sécurisé : passer en HTTPS obligatoire pour Google.")
        ok_rob, txt_rob = _verifier_ressource_site(racine, "/robots.txt")
        if not ok_rob:
            score -= 6
            importants.append(f"`/robots.txt` absent ou inaccessible ({txt_rob}).")
        elif re.search(r"(?im)^Disallow:\s*/\s*$", txt_rob):
            score -= 25
            critiques.append("BLOQUANT : `/robots.txt` contient `Disallow: /`, bloquant tout le site sur Google !")
        else:
            reussis.append("`/robots.txt` présent et autorise le crawl.")

        ok_map, txt_map = _verifier_ressource_site(racine, "/sitemap.xml")
        if not ok_map:
            score -= 6
            importants.append(f"`/sitemap.xml` absent ({txt_map}) — essentiel pour accélérer l'indexation Google.")
        else:
            reussis.append("`/sitemap.xml` accessible.")

    return {
        "score": max(0, min(100, score)),
        "title": title,
        "description": desc,
        "nb_mots": nb_mots,
        "critiques": critiques,
        "importants": importants,
        "optimisations": optimisations,
        "reussis": reussis,
    }


@outil(
    nom="seo-audit",
    mcp_expose=True,
    description="Audite le referencement Google d'un site web (URL publique ou fichier HTML/Next.js local) : "
                "score /100, title, meta description, H1/H2, canonical, robots.txt, sitemap.xml, Open Graph, "
                "Schema.org JSON-LD et extrait correctif pret a integrer.",
    parametres={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL publique https:// du site ou de la page a auditer", "default": ""},
            "fichier": {"type": "string", "description": "Chemin local HTML ou Next.js (page.tsx/layout.tsx) si audit local", "default": ""},
            "contenu": {"type": "string", "description": "Code HTML brut optionnel a auditer directement", "default": ""},
            "mot_cle_cible": {"type": "string", "description": "Mot-cle principal vise sur Google (optionnel)", "default": ""},
        },
    },
    lent=True,
    phrase_attente="J'effectue l'audit SEO complet.",
    affichage="toujours",
)
def seo_audit(
    url: str = "",
    fichier: str = "",
    contenu: str = "",
    mot_cle_cible: str = "",
) -> str:
    """Realise un audit SEO technique + semantique complet et propose des correctifs concrets."""
    brut = contenu or ""
    url_cible = ""
    est_nextjs = False

    if (url or "").strip():
        ok, val = _valider_url_publique(url)
        if not ok:
            return f"[ERREUR SECURITE] URL refusée : {val}"
        try:
            rep = requests.get(val, headers={"User-Agent": _USER_AGENT}, timeout=10, allow_redirects=True)
            rep.raise_for_status()
            ok_fin, url_cible = _valider_url_publique(rep.url or val)
            if not ok_fin:
                return f"[ERREUR SECURITE] Redirection refusée : {url_cible}"
            brut = rep.text or ""
        except Exception as e:
            return f"[ERREUR] Impossible de charger {val} : {e}"
    elif (fichier or "").strip():
        p = _resoudre_fichier_local(fichier)
        if not p.exists() or not p.is_file():
            return f"[ERREUR] Fichier introuvable : {fichier}"
        brut = p.read_text(encoding="utf-8", errors="replace")
        est_nextjs = p.suffix.lower() in (".tsx", ".jsx", ".ts", ".js")

    if not brut.strip():
        return "[ERREUR] Fournis une `url`, un `fichier` ou du `contenu` HTML à auditer."

    res = auditer_html_seo(brut, url=url_cible, mot_cle_cible=mot_cle_cible, est_nextjs=est_nextjs)
    cible_nom = url_cible or fichier or "extrait HTML"
    lignes = [
        f"### Audit SEO Google — `{cible_nom}` · Score : **{res['score']}/100**",
        f"- **Title détecté :** {res['title'] or '*(absent)*'}",
        f"- **Meta description :** {res['description'] or '*(absente)*'}",
    ]
    if res["critiques"]:
        lignes.append("\n**🔴 Problèmes critiques (impact fort sur l'indexation) :**")
        lignes.extend(f"- {x}" for x in res["critiques"])
    if res["importants"]:
        lignes.append("\n**🟠 Améliorations importantes :**")
        lignes.extend(f"- {x}" for x in res["importants"])
    if res["optimisations"]:
        lignes.append("\n**🟡 Optimisations recommandées :**")
        lignes.extend(f"- {x}" for x in res["optimisations"])
    if res["reussis"]:
        lignes.append("\n**🟢 Points déjà conformes :**")
        lignes.extend(f"- {x}" for x in res["reussis"])

    kw_txt = mot_cle_cible.strip() or res["title"] or "Votre Service"
    url_can = url_cible or "https://votre-domaine.com/"
    lignes.extend([
        "\n**Snippet correctif prêt à intégrer (`<head>` + Schema.org JSON-LD) :**",
        "```html",
        f'<title>{kw_txt[:58]}</title>',
        f'<meta name="description" content="Découvrez {kw_txt} : solution claire, rapide et accessible dès maintenant." />',
        f'<link rel="canonical" href="{url_can}" />',
        '<meta property="og:type" content="website" />',
        f'<meta property="og:title" content="{kw_txt[:58]}" />',
        f'<meta property="og:url" content="{url_can}" />',
        '<script type="application/ld+json">',
        f'{{"@context":"https://schema.org","@type":"WebSite","name":"{kw_txt}","url":"{url_can}"}}',
        "</script>",
        "```",
    ])
    return "\n".join(lignes)
