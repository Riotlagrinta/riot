---
name: digital-product-factory
description: |
  Création et industrialisation de produits digitaux, eBooks et bundles rentables clés en main.
  Utilisez cette compétence dès que l'utilisateur souhaite créer un eBook, packager une expertise sous forme de produit d'information numérique,
  générer une page de vente (landing page) optimisée avec intégration de paiement (Mobile Money Togo T-Money/Flooz + Carte/Stripe),
  concevoir un simulateur Excel de rentabilité offert en bonus ou rédiger un kit marketing & copywriting multicanal (WhatsApp, LinkedIn, Email).
license: Apache-2.0
metadata:
  version: v1
  publisher: riot-studio
---

# Compétence Usine à Produits Digitaux & eBooks Rentables (Digital Product Factory)

Cette compétence transforme Claude RIOT Studio en une usine d'édition et de monétisation numérique complète. Elle ne génère pas de simples fichiers texte génériques, mais un **écosystème de vente complet prêt à être commercialisé en 60 secondes**.

---

## 🎯 Les 5 Actifs Clés d'un Pack Produit Digital Rentable

Chaque exécution génère un bundle complet et packagé :

1. 📄 **L'E-Book / Guide Stratégique Opérationnel (Format PDF A4 HD)** :
   - Généré via le moteur ReportLab Platypus (`tools/pdf.py`).
   - Couverture prestige, typographie épurée, sommaire exécutif, fiches d'action, tableaux comparatifs et encadrés de conseils pratiques.
   
2. 📊 **Le Modèle / Simulateur Financier & ROI Bonus (Format Excel .xlsx)** :
   - Généré via openpyxl (`tools/bureautique.py`).
   - Classeur dynamique avec formules réelles (objectifs de ventes, calcul du chiffre d'affaires, déduction des frais de paiement Mobile Money à 3%, bénéfice net semestriel), volet supérieur figé et styles modernes.

3. 🌐 **La Landing Page de Vente Responsive & Mobile-First (Format HTML5 Standalone)** :
   - Design moderne (Dark mode / Dégradés modernes, Google Font Plus Jakarta Sans).
   - Structure de conversion haute performance : Accroche percutante, formulation des douleurs du prospect (Pain points), curriculum détaillé, cartes de tarification, modules de paiement local (T-Money / Moov Flooz via WhatsApp ou GeniusPay) et international (Carte Bancaire / Stripe).
   - Sticky bar d'achat pour mobile et FAQ avec objections levées.

4. ✍️ **Le Kit Marketing & Copywriting Multicanal (Format Markdown .md)** :
   - **Templates WhatsApp :** Messages de diffusion pour groupes et messages de relance d'urgence (J-24h).
   - **Post LinkedIn d'autorité :** Storytelling engageant, framework AIDA et appel à l'action.
   - **Séquence Email 3 Étapes :** Email 1 (Le problème caché), Email 2 (L'étude de cas et le simulateur offert), Email 3 (Urgence et clôture de l'offre de lancement).

5. 🗂️ **Le Manifeste d'Offre (.json) & L'Archive Dézippable (.zip)** :
   - Métadonnées structurées de l'offre.
   - Archive unique prête à être livrée immédiatement aux clients finaux.

---

## 🛠️ Utilisation Technique de l'Outil

L'outil Python associé est `creer_produit_digital` dans [`tools/product_factory.py`](file:///e:/PROJETS/Kéranos/keranos-assistant-vocal-main-1/tools/product_factory.py).

### Signature :
```python
creer_produit_digital(
    titre="L'Empire Digital 228",
    sujet="Monétiser ses compétences de développeur et créateur au Togo et en Afrique de l'Ouest",
    sous_titre="De zéro à vos premiers 500 000 FCFA par mois grâce aux produits digitaux",
    cible="Développeurs freelances, infographistes, créateurs de contenu et consultants",
    prix_fcfa=15000,
    prix_eur=25,
    chapitres="",              # Optionnel : Contenu Markdown spécifique ou auto-généré
    donnees_bonus_excel="",    # Optionnel : Données spécifiques ou simulateur auto-généré
    nom_dossier="empire_228",  # Optionnel : Nom du sous-dossier
    theme="moderne"            # 'moderne' | 'corporate' | 'emeraude' | 'sombre'
)
```
