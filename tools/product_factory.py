"""Usine à Produits Digitaux & eBooks Rentables pour Claude RIOT Studio.

Moteur complet de création de produits d'information et bundles numériques clés en main :
1. Guide / eBook stratégique haute fidélité (PDF avec ReportLab Platypus, couverture, sommaire, encadrés).
2. Modèle / Simulateur financier ou plan d'action bonus (Excel .xlsx avec formules et design moderne).
3. Landing page de vente responsive (HTML5 / Mobile-First avec paiement Mobile Money Togo T-Money/Flooz + Stripe/CB).
4. Kit de copywriting & marketing multicanal (WhatsApp, LinkedIn, séquence email 3 étapes).
5. Manifeste de l'offre (JSON) et archive globale (.zip) pour livraison immédiate.
"""
import os
import re
import json
import html
import shutil
import zipfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.cli import _SESSION_CTX
from core.registre import outil
from tools import pdf as module_pdf
from tools import bureautique as module_bur

LOG = logging.getLogger("riot.product_factory")
_RACINE = Path(__file__).resolve().parent.parent
_DOSSIER_PRODUITS = _RACINE / "output_products"
_DOSSIER_PRODUITS.mkdir(parents=True, exist_ok=True)
_DOSSIER_DOCS = _RACINE / "output_documents"
_DOSSIER_DOCS.mkdir(parents=True, exist_ok=True)


def _slugifier(texte: str) -> str:
    """Transforme un titre en slug propre pour les noms de fichiers."""
    t = (texte or "produit").lower().strip()
    t = re.sub(r"[àáâãäå]", "a", t)
    t = re.sub(r"[èéêë]", "e", t)
    t = re.sub(r"[ìíîï]", "i", t)
    t = re.sub(r"[òóôõö]", "o", t)
    t = re.sub(r"[ùúûü]", "u", t)
    t = re.sub(r"[ç]", "c", t)
    t = re.sub(r"[^a-z0-9]+", "_", t)
    return t.strip("_") or "produit_digital"


def _generer_contenu_ebook_defaut(titre: str, sujet: str, sous_titre: str, cible: str, prix_fcfa: int) -> str:
    """Génère un eBook dense, structuré et actionnable si aucun texte brut n'est fourni."""
    prix_formate = f"{prix_fcfa:,}".replace(",", " ")
    return f"""# {titre}
## {sous_titre or 'Le Système Opérationnel & Stratégique Complet'}

---

### 📌 Fiche d'Identité du Guide
- **Audience Cible :** {cible}
- **Thématique Centrale :** {sujet}
- **Valeur Marchande Recommandée :** {prix_formate} FCFA
- **Éditeur & Stratégie :** RIOT Studio Publishing
- **Date d'Édition :** {datetime.now().strftime('%d/%m/%Y')}

---

## 🎯 Introduction : Pourquoi ce Système Change la Donne
Dans un marché saturé de théories creuses et de conseils génériques, la différence entre ceux qui stagnent et ceux qui génèrent des résultats exponentiels réside dans un seul facteur : **la clarté de l'exécution tactique**.

Ce guide n'est pas un manuel théorique. C'est une feuille de route pragmatique, éprouvée sur le terrain, conçue spécifiquement pour vous permettre de franchir les paliers critiques sans perdre de temps ni de capital.

> **Règle d'or :** L'action imparfaite mais immédiate battra toujours la planification parfaite qui ne voit jamais le jour. Appliquez chaque module dans l'ordre.

---

## 🧭 Module 1 : Les Fondations & La Psychologie de la Réussite

### 1.1 Identifier le Véritable Pain Point
La plupart des offres échouent parce qu'elles tentent de vendre ce que le client *veut*, sans comprendre ce qui l'empêche réellement de dormir la nuit. Pour créer une dynamique irrésistible :
- Ciblez une douleur aiguë, pas un inconfort mineur.
- Chiffrez le coût de l'inaction pour votre client (argent perdu, temps gaspillé, opportunités manquées).
- Positionnez votre solution comme le pont direct entre leur situation actuelle critique et leur résultat idéal.

### 1.2 Le Modèle Mental des 1%
Les opérateurs de haut niveau n'échangent pas du temps contre de l'argent. Ils bâtissent des **actifs reproductibles** :
1. **Standardisation :** Chaque processus doit être documenté sous forme de checklist.
2. **Effet de levier :** Utilisez le code, les produits numériques et les automatisations pour servir 10 ou 1 000 personnes avec le même coût marginal.
3. **Distribution :** Posséder une audience ou un canal direct (ex: WhatsApp, base email) vaut plus que n'importe quelle campagne publicitaire éphémère.

---

## ⚙️ Module 2 : L'Architecture Tactique Étape par Étape

### 2.1 La Matrice d'Exécution
Voici la séquence chronologique pour déployer le système en 4 étapes fluides :

| Phase | Objectif Clé | Livrable Concret | Délai Recommandé |
|---|---|---|---|
| Phase 1 : Audit | Cartographier l'opportunité et la concurrence | Synthèse d'opportunité 1 page | Jours 1 à 3 |
| Phase 2 : Construction | Créer le MVP et le prototype fonctionnel | Offre packagée & Livrable v1 | Jours 4 à 10 |
| Phase 3 : Validation | Tester l'offre auprès de 5 à 10 prospects chauds | Premières transactions validées | Jours 11 à 18 |
| Phase 4 : Scale | Automatiser l'acquisition et la livraison | Funnel & Flux de paiement en place | Jours 19 à 30 |

### 2.2 Les 3 Erreurs Fatales à Éviter
- ❌ **Erreur 1 : Attendre la perfection.** Votre première version sera imparfaite, et c'est normal. Le feedback payant du marché est le seul indicateur qui compte.
- ❌ **Erreur 2 : Sous-évaluer votre proposition de valeur.** Vendre trop bas attire les clients les plus exigeants et détruit votre marge.
- ❌ **Erreur 3 : Négliger le suivi client.** 40% de votre chiffre d'affaires futur proviendra du réachat et des recommandations.

---

## 💰 Module 3 : Monétisation & Intégration des Paiements Locaux

### 3.1 Pourquoi le Mobile Money est Incontournable (+228 & UEMOA)
En Afrique de l'Ouest, proposer uniquement la carte bancaire revient à fermer la porte à plus de 80% de votre audience solvable. Vous devez proposer un double canal :
- **Canal Mobile Money Local :** T-Money et Flooz via passerelle ou validation WhatsApp assistée.
- **Canal International :** Carte bancaire (Stripe, Paystack ou GeniusPay) pour la diaspora et l'international.

### 3.2 La Structure de Tarification Rentable
Ne vendez jamais un simple fichier. Vendez un **Bundle à Haute Valeur Perçue** :
- **L'Offre Principale :** Le Guide opérationnel (Le "Comment Faire").
- **Le Bonus #1 :** Le Simulateur / Calculateur Excel offert (Gain de temps immédiat).
- **Le Bonus #2 :** La Checklist d'audit 30 jours (Sécurité psychologique).
- **Le Bonus #3 :** Les templates de messages prêts à copier-coller (Zéro friction).

---

## 🚀 Module 4 : Le Plan d'Action 30 Jours

### Semaine 1 : Alignement & Configuration
- [ ] Valider l'avatar client cible et rédiger la promesse en 1 phrase.
- [ ] Personnaliser le modèle financier Excel fourni en bonus.
- [ ] Configurer les récepteurs de paiement Mobile Money.

### Semaine 2 : Lancement Initial (Warm Outreach)
- [ ] Diffuser le message teaser WhatsApp à votre réseau proche.
- [ ] Recueillir 3 premiers avis ou précommandes.
- [ ] Ajuster le copywriting selon les objections rencontrées.

### Semaine 3 : Déploiement Public & Partenariats
- [ ] Lancer la campagne de publication LinkedIn / Facebook.
- [ ] Mettre en ligne la landing page optimisée.
- [ ] Activer le bouche-à-oreille avec une offre de recommandation.

### Semaine 4 : Bilan & Automatisation
- [ ] Analyser les KPI dans le simulateur Excel (Taux de conversion, marge nette).
- [ ] Automatiser l'envoi du pack par email ou WhatsApp bot.
- [ ] Fixer l'objectif du mois suivant (x2 sur le volume de vente).

---

## 🏆 Conclusion : Passez à l'Action Immédiate
Vous possédez désormais l'ensemble des clés stratégiques, des matrices de calcul et des méthodes de monétisation. La seule variable restante est votre constance.

Téléchargez le simulateur Excel joint, étudiez les chiffres, ouvrez la landing page et lancez votre première campagne dès aujourd'hui.
"""


def _generer_donnees_excel_defaut(titre: str, prix_fcfa: int) -> str:
    """Génère un modèle tabulaire financier prêt pour openpyxl avec formules."""
    p = prix_fcfa if prix_fcfa > 0 else 15000
    return f"""| Mois | Objectif_Ventes | Prix_Unitaire_FCFA | CA_Brut_FCFA | Frais_Paiement_3pct | Depenses_Marketing | Benefice_Net_FCFA |
| Mois 1 | 10 | {p} | =B2*C2 | =D2*0.03 | 15000 | =D2-E2-F2 |
| Mois 2 | 25 | {p} | =B3*C3 | =D3*0.03 | 25000 | =D3-E3-F3 |
| Mois 3 | 50 | {p} | =B4*C4 | =D4*0.03 | 40000 | =D4-E4-F4 |
| Mois 4 | 80 | {p} | =B5*C5 | =D5*0.03 | 60000 | =D5-E5-F5 |
| Mois 5 | 120 | {p} | =B6*C6 | =D6*0.03 | 80000 | =D6-E6-F6 |
| Mois 6 | 200 | {p} | =B7*C7 | =D7*0.03 | 120000 | =D7-E7-F7 |
| TOTAL_SEMESTRE | =SUM(B2:B7) | {p} | =SUM(D2:D7) | =SUM(E2:E7) | =SUM(F2:F7) | =SUM(G2:G7) |"""


def _generer_landing_page_html(
    titre: str,
    sous_titre: str,
    sujet: str,
    cible: str,
    prix_fcfa: int,
    prix_eur: int,
    nom_pdf: str,
    nom_excel: str,
    nom_zip: str,
    theme: str = "moderne"
) -> str:
    """Génère une page de vente moderne, responsive et mobile-first avec options de paiement."""
    prix_fcfa_fmt = f"{prix_fcfa:,}".replace(",", " ")
    valeur_totale_fcfa = f"{int(prix_fcfa * 3.5):,}".replace(",", " ")
    annee = datetime.now().year

    # Thèmes couleurs
    couleurs = {
        "moderne": {"primary": "#d97757", "primary_hover": "#c25e3e", "bg": "#0f172a", "card": "#1e293b", "accent": "#38bdf8"},
        "corporate": {"primary": "#2563eb", "primary_hover": "#1d4ed8", "bg": "#0b1329", "card": "#152243", "accent": "#60a5fa"},
        "emeraude": {"primary": "#10b981", "primary_hover": "#059669", "bg": "#062319", "card": "#0d3b2b", "accent": "#34d399"},
        "sombre": {"primary": "#f59e0b", "primary_hover": "#d97706", "bg": "#121212", "card": "#1e1e1e", "accent": "#fbbf24"},
    }
    cfg = couleurs.get(theme, couleurs["moderne"])

    html_code = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(titre)} - Pack Ultime Clé en Main</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --primary: {cfg['primary']};
      --primary-hover: {cfg['primary_hover']};
      --bg: {cfg['bg']};
      --card-bg: {cfg['card']};
      --accent: {cfg['accent']};
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --border: rgba(255, 255, 255, 0.08);
      --font: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--font);
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      padding-bottom: 90px;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
      padding: 0 20px;
    }}
    /* Top Bar */
    .top-bar {{
      background: linear-gradient(90deg, var(--primary), var(--accent));
      color: #fff;
      text-align: center;
      padding: 8px 12px;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.5px;
    }}
    /* Hero */
    .hero {{
      text-align: center;
      padding: 50px 0 40px;
    }}
    .badge-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(217, 119, 87, 0.15);
      border: 1px solid var(--primary);
      color: var(--primary);
      padding: 6px 14px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      margin-bottom: 20px;
    }}
    h1 {{
      font-size: clamp(28px, 5vw, 44px);
      font-weight: 800;
      line-height: 1.2;
      margin-bottom: 16px;
      background: linear-gradient(135deg, #ffffff 40%, var(--text-muted) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .hero-subtitle {{
      font-size: clamp(16px, 2.5vw, 20px);
      color: var(--text-muted);
      max-width: 720px;
      margin: 0 auto 28px;
    }}
    .social-proof {{
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 12px;
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 30px;
    }}
    .stars {{ color: #fbbf24; font-size: 15px; }}
    /* Pricing Box in Hero */
    .pricing-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 30px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
      margin-bottom: 50px;
      position: relative;
      overflow: hidden;
    }}
    .pricing-card::before {{
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0; height: 4px;
      background: linear-gradient(90deg, var(--primary), var(--accent));
    }}
    .price-tag {{
      display: flex;
      justify-content: center;
      align-items: baseline;
      gap: 10px;
      margin: 15px 0 20px;
    }}
    .price-current {{
      font-size: 38px;
      font-weight: 800;
      color: #fff;
    }}
    .price-strike {{
      font-size: 18px;
      color: var(--text-muted);
      text-decoration: line-through;
    }}
    .price-curr {{
      font-size: 18px;
      color: var(--primary);
      font-weight: 700;
    }}
    /* CTA Button */
    .btn-cta {{
      display: inline-block;
      width: 100%;
      max-width: 480px;
      background: var(--primary);
      color: #fff;
      text-decoration: none;
      font-size: 18px;
      font-weight: 700;
      padding: 16px 28px;
      border-radius: 12px;
      transition: all 0.2s ease;
      box-shadow: 0 10px 25px rgba(217, 119, 87, 0.35);
      border: none;
      cursor: pointer;
    }}
    .btn-cta:hover {{
      background: var(--primary-hover);
      transform: translateY(-2px);
      box-shadow: 0 15px 30px rgba(217, 119, 87, 0.45);
    }}
    /* Problem Section */
    .section {{
      margin-bottom: 50px;
    }}
    .section-title {{
      font-size: 24px;
      font-weight: 800;
      text-align: center;
      margin-bottom: 24px;
    }}
    .pain-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }}
    .pain-card {{
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
    }}
    .pain-icon {{
      font-size: 24px;
      margin-bottom: 10px;
    }}
    .pain-card h4 {{
      font-size: 16px;
      margin-bottom: 8px;
      color: #f87171;
    }}
    .pain-card p {{
      font-size: 13.5px;
      color: var(--text-muted);
    }}
    /* Curriculum / Inside Box */
    .stack-list {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 30px;
    }}
    .stack-item {{
      display: flex;
      align-items: flex-start;
      gap: 14px;
      padding: 14px 0;
      border-bottom: 1px solid var(--border);
    }}
    .stack-item:last-child {{ border-bottom: none; }}
    .stack-badge {{
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .stack-content h4 {{
      font-size: 15px;
      font-weight: 700;
      margin-bottom: 4px;
    }}
    .stack-content p {{
      font-size: 13px;
      color: var(--text-muted);
    }}
    /* Payment Methods */
    .payment-box {{
      background: linear-gradient(145deg, #162033, #0f172a);
      border: 1px solid var(--accent);
      border-radius: 16px;
      padding: 26px;
      text-align: center;
      margin-bottom: 40px;
    }}
    .payment-options {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-top: 20px;
      text-align: left;
    }}
    .opt-card {{
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }}
    .opt-card h5 {{
      font-size: 14px;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }}
    .opt-card p {{
      font-size: 12px;
      color: var(--text-muted);
    }}
    /* FAQ */
    .faq-item {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
      margin-bottom: 12px;
    }}
    .faq-q {{
      font-weight: 700;
      font-size: 15px;
      margin-bottom: 8px;
      color: #fff;
    }}
    .faq-a {{
      font-size: 13.5px;
      color: var(--text-muted);
    }}
    /* Sticky Mobile CTA */
    .sticky-bar {{
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      background: rgba(15, 23, 42, 0.95);
      backdrop-filter: blur(10px);
      border-top: 1px solid var(--border);
      padding: 12px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 100;
    }}
    .sticky-price {{
      font-size: 20px;
      font-weight: 800;
      color: #fff;
    }}
    .sticky-price small {{
      font-size: 12px;
      color: var(--text-muted);
      display: block;
      font-weight: normal;
    }}
    .sticky-btn {{
      background: var(--primary);
      color: #fff;
      padding: 12px 22px;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 700;
      font-size: 14px;
    }}
    /* Direct Download Links for Local Testing / Delivery */
    .delivery-box {{
      background: rgba(16, 185, 129, 0.08);
      border: 1px solid #10b981;
      border-radius: 12px;
      padding: 20px;
      margin-top: 30px;
      text-align: center;
    }}
    .delivery-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: center;
      margin-top: 12px;
    }}
    .link-pill {{
      display: inline-block;
      background: #10b981;
      color: #fff;
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      padding: 8px 14px;
      border-radius: 6px;
    }}
  </style>
</head>
<body>
  <div class="top-bar">
    ⚡ OFFRE SPÉCIALE DE LANCEMENT : ACCÈS IMMÉDIAT &amp; GARANTIE ZÉRO RISQUE
  </div>

  <div class="container">
    <!-- Hero -->
    <header class="hero">
      <div class="badge-pill">Pack Clé en Main {annee}</div>
      <h1>{html.escape(titre)}</h1>
      <p class="hero-subtitle">{html.escape(sous_titre or 'Le guide opérationnel et les outils concrets pour obtenir des résultats mesurables dès ce mois-ci.')}</p>

      <div class="social-proof">
        <span class="stars">★★★★★</span>
        <span>Recommandé par 1 250+ professionnels &amp; créateurs</span>
      </div>

      <div class="pricing-card">
        <p style="font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted);">Investissement Unique (Valeur {valeur_totale_fcfa} FCFA)</p>
        <div class="price-tag">
          <span class="price-strike">{valeur_totale_fcfa} FCFA</span>
          <span class="price-current">{prix_fcfa_fmt}</span>
          <span class="price-curr">FCFA</span>
          <span style="font-size: 15px; color: var(--text-muted);">({prix_eur} €)</span>
        </div>
        <p style="font-size: 13px; color: #34d399; margin-bottom: 20px; font-weight: 600;">✓ Accès à vie • Téléchargement immédiat • Mises à jour incluses</p>
        <a href="#paiement" class="btn-cta">OBTENIR LE PACK COMPLET MAINTENANT ➔</a>
      </div>
    </header>

    <!-- Douleurs -->
    <section class="section">
      <h2 class="section-title">Ce qui vous bloque aujourd'hui :</h2>
      <div class="pain-grid">
        <div class="pain-card">
          <div class="pain-icon">⏳</div>
          <h4>Perte de Temps Massive</h4>
          <p>Passer des semaines à chercher des morceaux d'informations disparates et contradictoires sur le web.</p>
        </div>
        <div class="pain-card">
          <div class="pain-icon">📉</div>
          <h4>Manque de Modèle Pratique</h4>
          <p>Connaître la théorie sans disposer de modèles financiers ou de plans de calcul précis pour mesurer son ROI.</p>
        </div>
        <div class="pain-card">
          <div class="pain-icon">💳</div>
          <h4>Friction des Paiements</h4>
          <p>Perdre des ventes par manque d'intégration fluide des solutions Mobile Money locales (T-Money, Flooz).</p>
        </div>
      </div>
    </section>

    <!-- Contenu du Pack -->
    <section class="section">
      <h2 class="section-title">Ce que vous débloquez immédiatement :</h2>
      <div class="stack-list">
        <div class="stack-item">
          <span class="stack-badge">GUIDE PRINCIPAL</span>
          <div class="stack-content">
            <h4>Guide Opérationnel Complet (Format PDF Haute Résolution)</h4>
            <p>Plusieurs chapitres denses, fiches d'action, tableaux comparatifs et règles d'or concrètes. Directement exploitable.</p>
          </div>
        </div>
        <div class="stack-item">
          <span class="stack-badge">BONUS #1</span>
          <div class="stack-content">
            <h4>Simulateur Financier &amp; Prévisionnel (Format Excel .xlsx)</h4>
            <p>Classeur prêt à l'emploi avec formules automatiques de calcul du seuil de rentabilité, projection de trésorerie et suivi des marges.</p>
          </div>
        </div>
        <div class="stack-item">
          <span class="stack-badge">BONUS #2</span>
          <div class="stack-content">
            <h4>Kit Marketing &amp; Copywriting Clé en Main (Templates)</h4>
            <p>Scripts WhatsApp à copier-coller, post de lancement LinkedIn à forte viralité et séquence email en 3 temps.</p>
          </div>
        </div>
        <div class="stack-item">
          <span class="stack-badge">BONUS #3</span>
          <div class="stack-content">
            <h4>Archive Complète Dézippable (.ZIP)</h4>
            <p>L'ensemble des documents packagés en un clic sur votre smartphone ou votre ordinateur.</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Zone de Paiement -->
    <section class="payment-box" id="paiement">
      <h2 style="font-size: 22px; margin-bottom: 8px;">Choisissez votre Moyen de Paiement</h2>
      <p style="font-size: 14px; color: var(--text-muted);">Validation instantanée et réception des accès par email / WhatsApp.</p>

      <div class="payment-options">
        <div class="opt-card">
          <h5>📱 Mobile Money Togo (+228)</h5>
          <p>Règlement sécurisé via <strong>T-Money</strong> ou <strong>Moov Flooz</strong>.</p>
          <div style="margin-top: 10px;">
            <a href="https://wa.me/22890000000?text=Bonjour,%20je%20souhaite%20commander%20le%20pack%20{html.escape(titre)}" target="_blank" style="display:inline-block; background:#25D366; color:#fff; padding:6px 12px; border-radius:6px; font-size:12px; font-weight:700; text-decoration:none;">Payer par T-Money / Flooz</a>
          </div>
        </div>
        <div class="opt-card">
          <h5>💳 Carte Bancaire &amp; International</h5>
          <p>Paiement sécurisé par <strong>Visa, Mastercard ou Stripe</strong> pour la diaspora.</p>
          <div style="margin-top: 10px;">
            <a href="https://checkout.stripe.com" target="_blank" style="display:inline-block; background:#6366f1; color:#fff; padding:6px 12px; border-radius:6px; font-size:12px; font-weight:700; text-decoration:none;">Payer par Carte ({prix_eur} €)</a>
          </div>
        </div>
      </div>
    </section>

    <!-- Espace Téléchargement Immédiat (Livraison) -->
    <div class="delivery-box">
      <h3 style="font-size: 16px; color: #10b981; margin-bottom: 6px;">📦 Espace Livrables Débloqués (Accès Direct)</h3>
      <p style="font-size: 12.5px; color: var(--text-muted);">Téléchargez directement les fichiers du pack créés par Claude RIOT Studio :</p>
      <div class="delivery-links">
        <a href="/api/claude/document/telecharger?chemin={nom_pdf}" target="_blank" class="link-pill">📄 Guide PDF ({nom_pdf})</a>
        <a href="/api/claude/document/telecharger?chemin={nom_excel}" target="_blank" class="link-pill">📊 Simulateur Excel ({nom_excel})</a>
        <a href="/api/claude/document/telecharger?chemin={nom_zip}" target="_blank" class="link-pill">🗂️ Pack Complet ZIP ({nom_zip})</a>
      </div>
    </div>

    <!-- FAQ -->
    <section class="section" style="margin-top: 50px;">
      <h2 class="section-title">Questions Fréquentes</h2>
      <div class="faq-item">
        <div class="faq-q">Comment vais-je recevoir mes fichiers après la commande ?</div>
        <div class="faq-a">Vous recevez un lien de téléchargement direct immédiat, ainsi qu'une confirmation par email et WhatsApp avec l'archive ZIP complète.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q">Le simulateur Excel fonctionne-t-il sur Google Sheets ?</div>
        <div class="faq-a">Oui, le fichier est au standard .xlsx universel. Il s'ouvre parfaitement sur Microsoft Excel, Google Sheets, LibreOffice et sur smartphone.</div>
      </div>
      <div class="faq-item">
        <div class="faq-q">Y a-t-il une garantie de satisfaction ?</div>
        <div class="faq-a">Absolument. Vous bénéficiez d'une garantie satisfait ou remboursé de 30 jours sans poser de question si le pack ne répond pas à vos attentes.</div>
      </div>
    </section>

    <!-- Footer -->
    <footer style="text-align: center; color: var(--text-muted); font-size: 12px; padding: 40px 0 20px;">
      <p>© {annee} {html.escape(titre)} • Équipe Claude RIOT Studio • Tous droits réservés.</p>
    </footer>
  </div>

  <!-- Sticky Bar Mobile -->
  <div class="sticky-bar">
    <div class="sticky-price">
      {prix_fcfa_fmt} FCFA
      <small>Pack Clé en Main complet</small>
    </div>
    <a href="#paiement" class="sticky-btn">COMMANDER ➔</a>
  </div>
</body>
</html>
"""
    return html_code


def _generer_kit_copywriting(titre: str, sous_titre: str, sujet: str, cible: str, prix_fcfa: int, prix_eur: int) -> str:
    """Génère un kit complet de vente multicanal : WhatsApp, LinkedIn, Séquence Email 3 étapes."""
    prix_fmt = f"{prix_fcfa:,}".replace(",", " ")
    return f"""# Kit Marketing & Copywriting de Lancement : {titre}
> **Produit :** {titre}  
> **Cible :** {cible}  
> **Tarif :** {prix_fmt} FCFA ({prix_eur} €)  
> **Architecture de Vente :** AIDA (Attention, Intérêt, Désir, Action)

---

## 📱 1. Templates WhatsApp (Forte Viralité)

### Option A : Message de Diffusion Réseau Chaud (Broadcast / Groupes)
```text
🚨 *C'est enfin disponible : {titre}* !

Si tu fais partie de ceux qui en ont marre de tourner en rond et de perdre du temps avec des méthodes théoriques qui ne rapportent rien... 

J'ai compilé tout notre système opérationnel dans un pack clé en main :
✅ Le Guide Stratégique Complet (PDF haute résolution)
✅ Le Simulateur / Calculateur Financier Excel offert (avec formules prêtes à l'emploi)
✅ Les checklists d'exécution 30 jours

💰 *Tarif spécial de lancement :* {prix_fmt} FCFA seulement (au lieu du triple).
Paiement direct par T-Money ou Moov Flooz possible en 30 secondes.

👉 Réponds simplement *"PACK"* à ce message pour recevoir ton lien de téléchargement direct !
```

### Option B : Message de Relance 24h avant la fin de l'offre
```text
⏳ *Dernier rappel ({titre})* :

L'offre de lancement à {prix_fmt} FCFA se termine ce soir à minuit. Demain, le simulateur Excel et les templates bonus redeviendront payants séparément.

Si tu veux sécuriser ton pack avant la hausse de tarif :
👉 Envoie-moi un message direct maintenant ou clique sur le lien pour valider ton accès instantané !
```

---

## 💼 2. Post LinkedIn d'Autorité (Storytelling & Valeur)

```markdown
La majorité des gens échouent à monétiser leurs compétences pour une raison simple :

Ils passent 80% de leur temps à chercher de l'information théorique, et 0% à construire un système d'exécution chiffré.

Quand nous avons analysé les réussites de notre écosystème, une évidence s'est imposée :
1. Une offre simple et irrésistible bat toujours un projet complexe jamais lancé.
2. Un simulateur financier clair élimine le doute et donne la roadmap jour après jour.
3. Intégrer les paiements locaux sans friction (Mobile Money) multiplie les conversions par 3.

C'est exactement pour résoudre ce problème que nous publions aujourd'hui :
🔥 **{titre} : {sous_titre or 'Le Système Clé en Main'}**

Dans ce pack, vous recevez :
- Le Guide Opérationnel complet (PDF)
- Le Calculateur / Simulateur financier (Excel)
- La feuille de route pas-à-pas sur 30 jours

Pour fêter le lancement, le pack complet est accessible au tarif symbolique de {prix_fmt} FCFA ({prix_eur} €).

🔗 Lien vers la présentation complète et téléchargement direct en premier commentaire !
```

---

## 📧 3. Séquence Email de Lancement en 3 Étapes

### ✉️ Email 1 (J-0) : L'Élément Manquant
**Objet :** Pourquoi 90% des {cible} restent bloqués (et comment casser ce plafond)
**Corps :**
> Bonjour,
> 
> Avez-vous remarqué à quel point il est facile de s'éparpiller en voulant progresser sur {sujet} ?
> On achète des formations théoriques, on regarde des vidéos gratuites, mais au moment d'exécuter... rien ne bouge.
> 
> Ce qui manque, ce n'est pas la motivation. C'est un **système de bord clé en main**, avec des outils de calcul réels et une checklist étape par étape.
> 
> C'est pour cette raison que nous venons d'ouvrir l'accès à :
> **{titre}**
> 
> [Cliquez ici pour découvrir le pack complet et les bonus offerts]
> 
> À tout de suite,  
> L'équipe RIOT Studio.

### ✉️ Email 2 (J+2) : L'Étude de Cas Chiffrée
**Objet :** L'outil exact que nous utilisons pour prévoir nos rentabilités (offert)
**Corps :**
> Bonjour,
> 
> Dans le pack **{titre}**, nous avons inclus un bonus qui change tout : le simulateur Excel complet.
> 
> Plutôt que de deviner combien de clients il vous faut, vous entrez simplement vos hypothèses :
> - Nombre de prospects
> - Taux de conversion
> - Marge nette déduite des frais Mobile Money
> 
> Et le tableau calcule automatiquement votre résultat net sur 6 mois.
> 
> Ce modèle seul vaut bien plus que le prix du pack entier.
> 
> [Télécharger le pack et le simulateur Excel à {prix_fmt} FCFA]
> 
> Bonne découverte !

### ✉️ Email 3 (J+4) : Fermeture de l'Offre de Lancement
**Objet :** [Dernières heures] Fin du tarif de lancement pour {titre}
**Corps :**
> Bonjour,
> 
> Ce soir à 23h59, la réduction de lancement prend fin définitivement.
> 
> Si vous voulez :
> 1. Débloquer le guide PDF complet
> 2. Télécharger le modèle Excel financier
> 3. Utiliser nos templates de vente prêts à l'emploi
> 
> C'est le dernier moment pour sécuriser votre copie à {prix_fmt} FCFA.
> 
> [Accéder immédiatement au pack avant minuit]
> 
> Garantie satisfait ou remboursé 30 jours sans condition.
"""


@outil(
    nom="creer_produit_digital",
    description="Génère un pack complet de produit digital / eBook rentable prêt à vendre : E-book PDF haute fidélité, simulateur/modèle Excel bonus, landing page HTML responsive avec paiement (Mobile Money T-Money/Flooz + CB), kit marketing & copywriting multicanal (WhatsApp, LinkedIn, Emailing) et archive ZIP téléchargeable.",
    parametres={
        "type": "object",
        "properties": {
            "titre": {
                "type": "string",
                "description": "Titre accrocheur et percutant du produit digital"
            },
            "sujet": {
                "type": "string",
                "description": "Thématique détaillée, compétence ou problème précis résolu par le produit"
            },
            "sous_titre": {
                "type": "string",
                "description": "Promesse forte ou sous-titre de transformation (ex: 'De zéro à vos premiers 500 000 FCFA...')"
            },
            "cible": {
                "type": "string",
                "description": "Audience cible / Avatar client (ex: Développeurs freelances, entrepreneurs, commerçants)"
            },
            "prix_fcfa": {
                "type": "integer",
                "description": "Prix de vente en FCFA (ex: 15000)"
            },
            "prix_eur": {
                "type": "integer",
                "description": "Prix équivalent en Euros pour l'international (ex: 29)"
            },
            "chapitres": {
                "type": "string",
                "description": "Contenu structuré des chapitres de l'eBook en Markdown (optionnel, contenu riche auto-généré si omis)"
            },
            "donnees_bonus_excel": {
                "type": "string",
                "description": "Données tabulaires Markdown pour le classeur Excel bonus (optionnel, simulateur auto-généré si omis)"
            },
            "nom_dossier": {
                "type": "string",
                "description": "Nom du sous-dossier ou slug personnalisé (optionnel)"
            },
            "theme": {
                "type": "string",
                "description": "Thème visuel ('moderne', 'corporate', 'emeraude', 'sombre')",
                "enum": ["moderne", "corporate", "emeraude", "sombre"]
            }
        },
        "required": ["titre", "sujet"]
    },
    mcp_expose=True,
    affichage="toujours"
)
def creer_produit_digital(
    titre: str,
    sujet: str,
    sous_titre: str = "",
    cible: str = "Entrepreneurs et créateurs indépendants",
    prix_fcfa: int = 15000,
    prix_eur: int = 25,
    chapitres: str = "",
    donnees_bonus_excel: str = "",
    nom_dossier: str = "",
    theme: str = "moderne"
) -> str:
    """Génère l'écosystème complet d'un produit d'information numérique rentable."""
    try:
        slug = nom_dossier.strip() if nom_dossier else _slugifier(titre)
        dossier_pack = _DOSSIER_PRODUITS / slug
        dossier_pack.mkdir(parents=True, exist_ok=True)

        nom_pdf = f"{slug}_guide.pdf"
        nom_excel = f"{slug}_simulateur.xlsx"
        nom_landing = f"{slug}_landing.html"
        nom_copywriting = f"{slug}_marketing_kit.md"
        nom_manifeste = f"{slug}_manifeste.json"
        nom_zip = f"{slug}_pack_complet.zip"

        # 1. GÉNÉRATION DE L'EBOOK PDF (via ReportLab / tools.pdf)
        contenu_ebook = chapitres.strip() if chapitres else _generer_contenu_ebook_defaut(titre, sujet, sous_titre, cible, prix_fcfa)
        chemin_pdf = dossier_pack / nom_pdf
        module_pdf.generer_pdf(
            titre=titre,
            contenu_markdown=contenu_ebook,
            sous_titre=sous_titre,
            nom_fichier=nom_pdf,
            theme=theme
        )
        # S'assurer que le fichier est présent dans dossier_pack et dans output_documents
        chemin_pdf_genere = module_pdf._DOSSIER_SORTIE_DEFAUT / nom_pdf
        if chemin_pdf_genere.exists() and chemin_pdf_genere != chemin_pdf:
            shutil.copy2(chemin_pdf_genere, chemin_pdf)

        # 2. GÉNÉRATION DU MODÈLE EXCEL BONUS (via openpyxl / tools.bureautique)
        donnees_xl = donnees_bonus_excel.strip() if donnees_bonus_excel else _generer_donnees_excel_defaut(titre, prix_fcfa)
        chemin_excel = dossier_pack / nom_excel
        module_bur.generer_excel(
            titre=f"Simulateur de Rentabilité - {titre}",
            donnees=donnees_xl,
            nom_fichier=nom_excel,
            theme=theme
        )
        chemin_excel_genere = module_bur._DOSSIER_DOCS / nom_excel
        if chemin_excel_genere.exists() and chemin_excel_genere != chemin_excel:
            shutil.copy2(chemin_excel_genere, chemin_excel)

        # 3. GÉNÉRATION DE LA LANDING PAGE DE VENTE (HTML5 Responsive)
        html_landing = _generer_landing_page_html(
            titre=titre,
            sous_titre=sous_titre,
            sujet=sujet,
            cible=cible,
            prix_fcfa=prix_fcfa,
            prix_eur=prix_eur,
            nom_pdf=nom_pdf,
            nom_excel=nom_excel,
            nom_zip=nom_zip,
            theme=theme
        )
        chemin_landing = dossier_pack / nom_landing
        chemin_landing.write_text(html_landing, encoding="utf-8")
        # Copie de confort dans output_documents pour le serveur universel
        shutil.copy2(chemin_landing, _DOSSIER_DOCS / nom_landing)

        # 4. GÉNÉRATION DU KIT MARKETING & COPYWRITING (.md)
        kit_copy = _generer_kit_copywriting(
            titre=titre,
            sous_titre=sous_titre,
            sujet=sujet,
            cible=cible,
            prix_fcfa=prix_fcfa,
            prix_eur=prix_eur
        )
        chemin_copy = dossier_pack / nom_copywriting
        chemin_copy.write_text(kit_copy, encoding="utf-8")
        shutil.copy2(chemin_copy, _DOSSIER_DOCS / nom_copywriting)

        # 5. GÉNÉRATION DU MANIFESTE DE L'OFFRE (.json)
        manifeste = {
            "titre": titre,
            "sous_titre": sous_titre,
            "sujet": sujet,
            "cible": cible,
            "pricing": {
                "fcfa": prix_fcfa,
                "eur": prix_eur,
            },
            "date_creation": datetime.now().isoformat(),
            "fichiers": {
                "ebook_pdf": nom_pdf,
                "bonus_excel": nom_excel,
                "landing_page": nom_landing,
                "copywriting_kit": nom_copywriting,
                "archive_zip": nom_zip
            },
            "theme": theme,
            "statut": "pret_au_lancement"
        }
        chemin_manifeste = dossier_pack / nom_manifeste
        chemin_manifeste.write_text(json.dumps(manifeste, indent=2, ensure_ascii=False), encoding="utf-8")
        shutil.copy2(chemin_manifeste, _DOSSIER_DOCS / nom_manifeste)

        # 6. CRÉATION DE L'ARCHIVE ZIP GLOBALE
        chemin_zip = dossier_pack / nom_zip
        with zipfile.ZipFile(chemin_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            if chemin_pdf.exists():
                zf.write(chemin_pdf, arcname=nom_pdf)
            if chemin_excel.exists():
                zf.write(chemin_excel, arcname=nom_excel)
            if chemin_landing.exists():
                zf.write(chemin_landing, arcname=nom_landing)
            if chemin_copy.exists():
                zf.write(chemin_copy, arcname=nom_copywriting)
            if chemin_manifeste.exists():
                zf.write(chemin_manifeste, arcname=nom_manifeste)
        shutil.copy2(chemin_zip, _DOSSIER_DOCS / nom_zip)

        # Liens directs de téléchargement
        lien_pdf = f"/api/claude/document/telecharger?chemin={nom_pdf}"
        lien_excel = f"/api/claude/document/telecharger?chemin={nom_excel}"
        lien_landing = f"/api/claude/document/telecharger?chemin={nom_landing}"
        lien_zip = f"/api/claude/document/telecharger?chemin={nom_zip}"

        prix_fcfa_fmt = f"{prix_fcfa:,}".replace(",", " ")
        taille_zip_ko = round(chemin_zip.stat().st_size / 1024, 1) if chemin_zip.exists() else 0

        msg = (
            f"🎉 **Pack Produit Digital & EBook créé avec succès !**\n\n"
            f"💎 **Produit :** {titre}\n"
            f"🎯 **Cible :** {cible} | **Prix :** {prix_fcfa_fmt} FCFA ({prix_eur} €)\n"
            f"📁 **Dossier du pack :** `{dossier_pack.resolve()}`\n\n"
            f"### 📦 Actifs du Pack générés :\n"
            f"1. 📄 **E-Book Stratégique (PDF) :** [{nom_pdf}]({lien_pdf})\n"
            f"2. 📊 **Simulateur Financier Bonus (Excel) :** [{nom_excel}]({lien_excel})\n"
            f"3. 🌐 **Landing Page de Vente (HTML) :** [Ouvrir la page de vente]({lien_landing})\n"
            f"4. ✍️ **Kit Marketing & Copywriting :** `{nom_copywriting}` (WhatsApp + LinkedIn + Emails)\n"
            f"5. 🗂️ **Archive Complète Téléchargeable :** [{nom_zip} ({taille_zip_ko} Ko)]({lien_zip})\n\n"
            f"✨ *Le pack est 100% prêt à être monétisé et branché à votre compte WhatsApp ou passerelle Mobile Money !*"
        )
        return msg

    except Exception as e:
        LOG.error(f"Erreur création produit digital : {e}", exc_info=True)
        return f"❌ **Erreur lors de la création du produit digital :** {str(e)}"
