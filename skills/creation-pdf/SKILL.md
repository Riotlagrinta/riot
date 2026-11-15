---
name: creation-pdf
description: |
  Compétence de génération, conception et manipulation de documents PDF professionnels pour Kéranos RIOT.
license: Apache-2.0
metadata:
  version: v1
  publisher: keranos-riot
---

# Compétence Kéranos : Création & Manipulation de PDF

Permet à l'assistant Kéranos RIOT de générer des PDF soignés (mise en page A4, en-têtes et pieds de page numérotés Page X/Y, tableaux stylisés, blocs de code, citations et thèmes graphiques).

## Outils Intégrés

1. `generer_pdf(titre, contenu_markdown, sous_titre="", nom_fichier="", theme="moderne", ouvrir_apres=False)`
2. `extraire_texte_pdf(chemin, max_pages=15)`
3. `fusionner_pdfs(fichiers, nom_fichier_sortie="")`

Les fichiers générés sont placés par défaut dans le dossier `output_pdf/` ou dans le dossier du projet actif, avec un lien de téléchargement direct pour l'interface Web Claude Studio :
`/api/claude/pdf/telecharger?chemin=<nom_fichier.pdf>`.
