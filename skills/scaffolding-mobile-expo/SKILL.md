---
name: scaffolding-mobile-expo
description: |
  Génération de gabarits et composants mobiles modernes pour React Native et Expo Router v3/v4.
  Utilisez cette compétence dès que l'utilisateur souhaite créer une application mobile, concevoir un écran de cartographie (Leaflet/Mapbox),
  intégrer un formulaire de paiement Mobile Money Togo (T-Money, Flooz) ou échafauder un projet Expo complet prêt à l'emploi.
license: Apache-2.0
metadata:
  version: v1
  publisher: riot-studio
---

# Compétence Scaffolding & Composants Mobile (React Native / Expo)

Cette compétence permet à Claude RIOT Studio de concevoir et générer des applications mobiles modernes basées sur **Expo Router v3+**, **React Native** et **TypeScript**.

Elle est optimisée pour les applications géolocalisées et transactionnelles au Togo et en Afrique de l'Ouest (ex: **MediGo Mobile**, **TogoDrive**, **Scan 'n Serve TG**).

---

## 🎯 Capacités Clés

1. **Écrans Géographiques & Proximité (`carte_geoloc`) :**
   - Écran de cartographie avec radar de proximité GPS, marqueurs de pharmacies / véhicules, indicateur de pharmacie de garde et bottom-sheet de détails.
2. **Paiement Mobile Money Togo (`paiement_togo`) :**
   - Modal de paiement avec détection automatique d'opérateur selon l'indicatif togolais (90/91/92/93 -> Togocom T-Money, 96/97/98/99/70 -> Moov Flooz).
   - Validation stricte du format à 8 chiffres et gestion du cycle de chargement.
3. **Architecture Complète Expo (`scaffolder_app_mobile_expo`) :**
   - Création de l'arborescence de fichiers Expo Router v3 (Tabs + Stack), `package.json`, `app.json` et packaging en archive `.zip` téléchargeable.
