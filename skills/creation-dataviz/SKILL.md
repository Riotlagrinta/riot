---
name: creation-dataviz
description: |
  Compétence Kéranos : Visualisation de données et graphiques haute résolution (300 DPI) en PNG.
license: Apache-2.0
metadata:
  version: v1
  publisher: keranos-riot
---

# Compétence Kéranos : DataViz & Graphiques Haute Définition

Permet à tous les agents Kéranos RIOT de transformer des tableaux de données, métriques et résultats en graphiques professionnels (courbes, diagrammes en barres, donuts, camemberts, aires).

## Outil Intégré

`generer_graphique(titre, donnees, type_graphique="barres", sous_titre="", axe_y="", nom_fichier="", theme="sombre")`

- **Types supportés** : `barres`, `courbe`, `donut`, `camembert`, `aire`, `barres_horizontales`.
- **Thèmes supportés** : `sombre` (défaut RIOT), `moderne`, `corporate`.
- **Format d'entrée** : Tableaux Markdown (`| Catégorie | Valeur |`) ou JSON.
- **Résolution** : 300 DPI avec anti-aliasing et palettes coordonnées.

Téléchargement et intégration directe dans l'interface web :
`/api/claude/document/telecharger?chemin=<nom_fichier>`
