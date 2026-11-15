---
name: creation-diagrammes
description: |
  Compétence Kéranos : Conception et visualisation de diagrammes d'architecture, flux et modèles de données (Mermaid).
license: Apache-2.0
metadata:
  version: v1
  publisher: keranos-riot
---

# Compétence Kéranos : Architecte Visuel & Diagrammes Techniques

Permet à tous les agents Kéranos RIOT de concevoir, valider et visualiser des schémas d'architecture, flux de séquence, modèles relationnels et diagrammes d'états.

## Outil Intégré

`generer_diagramme(titre, type_diagramme, code_mermaid, sous_titre="", theme="sombre", nom_fichier="")`

- **Types supportés** : `flowchart`, `sequence`, `class`, `state`, `erd`, `gitgraph`, `gantt`, `mindmap`.
- **Rendu Web** : Bloc Mermaid avec coloration sombre instantanée dans le chat Claude.
- **Visionneuse Interactive** : Génère une page HTML autonome avec Pan, Zoom et export direct SVG dans `/output_documents/`.
- **Lien Web direct** : `/api/claude/document/telecharger?chemin=<nom_fichier>.html`
