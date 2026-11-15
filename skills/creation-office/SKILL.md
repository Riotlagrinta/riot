---
name: creation-office
description: |
  Compétence Kéranos : Génération et lecture de documents Excel (.xlsx) et présentations PowerPoint (.pptx).
license: Apache-2.0
metadata:
  version: v1
  publisher: keranos-riot
---

# Compétence Kéranos : Excel & PowerPoint

Permet à tous les agents Kéranos RIOT de générer et lire des classeurs Excel stylisés et des présentations PowerPoint 16:9 professionnelles.

## Outils Intégrés

1. `generer_excel(titre, donnees, nom_fichier="", theme="moderne", ouvrir_apres=False)`
2. `lire_excel(chemin, feuille="", max_lignes=50)`
3. `generer_powerpoint(titre, diapositives, sous_titre="", nom_fichier="", theme="moderne", ouvrir_apres=False)`
4. `lire_powerpoint(chemin, max_slides=20)`

Téléchargement direct dans l'interface web :
`/api/claude/document/telecharger?chemin=<nom_fichier>`
