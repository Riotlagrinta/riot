# ⚡ Claude RIOT Studio (ex-Kéranos)

> **Plateforme d'Ingénierie Logicielle Multi-Agents, Trading Quantitatif, IA 100% Souveraine & Suite Exécutive Autonome.**

![Python](https://img.shields.io/badge/python-3.13-blue?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square)
![SQLite WAL](https://img.shields.io/badge/SQLite-FTS5%20WAL-003B57?style=flat-square)
![Multi-Agents](https://img.shields.io/badge/Swarm-4%20Specialists-d97757?style=flat-square)
![ReportLab](https://img.shields.io/badge/Engine-ReportLab%20Platypus-red?style=flat-square)
![Office](https://img.shields.io/badge/Suite-Excel%20%7C%20PowerPoint-green?style=flat-square)
![DataViz](https://img.shields.io/badge/DataViz-300%20DPI-purple?style=flat-square)
![Mermaid](https://img.shields.io/badge/Diagrammes-Mermaid%20v10-ff69b4?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%2011-lightgrey?style=flat-square)

---

## 🏛️ Genèse & Vision du Projet

Initialement conçu sous le nom de **Kéranos** comme assistant vocal local souverain (Jarvis + Hermes), le projet a évolué pour devenir **Claude RIOT Studio** : un environnement d'ingénierie logicielle autonome, d'analyse quantitative et de production documentaire d'élite.

L'écosystème réunit sous une même interface web réactive (PWA) des capacités avancées :
1. **Pipeline Swarm Multi-Agents** de développement autonome (Planification, Codage chirurgical, Tests unitaires auto-guérisseurs, Audit sécurité).
2. **RIOT-Trader** : Analyse quantitative, flux crypto en direct (Binance), carnet d'ordres et doctrine stricte de risk management (1% du capital max).
3. **RIOT-Raw** : Agent local 0 censure (Ollama Dolphin), 100% privé, sans filtres moraux pour l'audit de cybersécurité offensive et les scénarios de crise.
4. **Suite Exécutive & DataViz Intégrée** : Génération instantanée de livrables professionnels (PDF, classeurs Excel dynamiques, présentations PowerPoint 16:9, graphiques 300 DPI et schémas d'architecture Mermaid).

---

## 🚀 Les 4 Piliers Fondamentaux

### 1. 🤖 Pipeline Multi-Agents Autonome (Swarm)
Inspiré des standards d'ingénierie d'Anthropic et DeepMind, le coordinateur orchestre 4 sous-agents spécialisés avec **synthèse unique consolidée** :
- **📐 RIOT-Architect** : Explore l'arborescence du projet, cartographie les dépendances et conçoit un plan d'action chirurgical structuré.
- **💻 RIOT-Engineer** : Applique les modifications de code avec une précision millimétrique via `patcher_code` et `ecrire_code`.
- **🧪 RIOT-Tester** : Exécute les suites de tests unitaires avec boucle de rétroaction et d'auto-guérison en cas d'erreur.
- **🛡️ RIOT-Reviewer** : Audit de conformité, détection de secrets en clair, vérification du typage et validation finale `[APPROUVÉ]`.

### 2. 📈 RIOT-Trader (Quant & Risk Management)
- **Doctrine des 1%** : Le risque par position ne dépasse jamais 1.0% du capital total.
- **Outils connectés** : Klines Binance temps réel, indicateurs techniques (RSI, SMA20/50, EMA20), carnet d'ordres Top 10 et dimensionnement de position automatique.

### 3. 🔥 RIOT-Raw (IA Locale & Privée)
- Motorisé par des modèles dé-censurés locaux via Ollama (`dolphin-llama3`, `dolphin-phi`).
- Fonctionne hors-ligne, sans dépendance cloud, sans coût d'API et avec une latence ultra-faible.

### 4. 💼 Suite Exécutive & Compétences Avancées

| Compétence | Outils Clés | Description & Fonctionnalités |
| :--- | :--- | :--- |
| **`creation-pdf`** | `generer_pdf`, `extraire_texte_pdf`, `fusionner_pdfs` | Moteur ReportLab Platypus. Génération de rapports PDF exécutifs avec couverture, sommaire cliquable, pagination dynamique et bouton 1-clic "Exporter en PDF". |
| **`creation-office`** | `generer_excel`, `lire_excel`, `generer_powerpoint`, `lire_powerpoint` | Tableaux financiers Excel `.xlsx` (OpenPyXL) avec formules, formatage monétaire et freeze-panes. Présentations PowerPoint `.pptx` 16:9 HD avec slides KPI et grilles. |
| **`creation-dataviz`** | `generer_graphique` | Graphiques haute résolution (300 DPI) en PNG (Matplotlib Agg) : courbes avec aire dégradée, barres simples/groupées, donuts et barres horizontales. Intégration en direct dans le chat. |
| **`creation-diagrammes`** | `generer_diagramme` | Architectures Mermaid.js v10 (Flowchart, Sequence, ERD, State). Rendu immédiat dans le chat et visionneuse HTML interactive plein écran (Pan, Zoom 30-300%, export vectoriel SVG). |
| **`digital-product-factory`** | *(En cours)* | Usine à infoproduits & eBooks rentables : cadrage commercial, packaging multi-assets, templates et sales copywriting de conversion. |

---

## 🖥️ Interfaces Utilisateur & Accès

### 1. Studio Web Claude RIOT (`http://localhost:8790/`)
- **Tri-panneau moderne** :
  - *Gauche* : Sélecteur de projets réels (28+ projets indexés automatiquement), historique persistant des discussions SQLite, modes rapides (`/swarm`, `/trade`, `/raw`, `/architect`, `/review`).
  - *Centre* : Chat fluide en Server-Sent Events (SSE), téléversement direct de fichiers (bouton trombone, drag & drop, collage presse-papier), cartes d'outils animées.
  - *Droite* : Explorateur de fichiers interactif et visionneuse d'Artifacts syntaxés.
- **Persistance intégrale** : Base de données `riot_memory.db` en mode WAL avec recherche plein texte BM25 (FTS5). Les discussions et fichiers joints survivent à tous les redémarrages.

### 2. Cockpit Tactile Mobile PWA (`http://localhost:8790/mobile`)
- Interface Obsidian & Néon Cyan pour smartphone.
- Télémétrie push continue (CPU, RAM, Disque, Réseau), reconnaissance vocale Web Speech API, terminal interactif et tuteur RAG de cours (`etude/`).

### 3. Terminal Cyberpunk CLI
- Lancement : `riot` ou `python riot.py`
- Raccourcis directs : `riot /trade BTCUSDT`, `riot /raw`, `riot /swarm`.

---

## 🛠️ Démarrage Rapide

### Prérequis
- Windows 11
- Python 3.11+ (recommandé : environnement virtuel `.venv`)
- *(Optionnel pour mode Raw)* : [Ollama](https://ollama.com/) avec modèle Dolphin installé.

### Lancement
```powershell
# 1. Lancer l'environnement Web Studio (Port 8790)
.\riot-app.bat
# ou en ligne de commande :
.\.venv\Scripts\python -c "import uvicorn; from core import serveur; uvicorn.run(serveur.app(), host='0.0.0.0', port=8790)"

# 2. Lancer la console interactive CLI
.\riot.bat
```

---

## 🧪 Diagnostic Zéro Erreur

La plateforme applique une politique stricte de **Zéro Erreur**. Une suite de tests automatisés valide la totalité des composants avant chaque déploiement :

```powershell
.\.venv\Scripts\python scripts/tester_claude_web.py
```

Résultats validés :
- ✅ Page d'accueil & Manifest PWA
- ✅ Routage Swarm multi-agents & intention classifier
- ✅ Persistance SQLite des sessions et messages
- ✅ Fichiers joints (Drag & Drop, upload, injection de contexte)
- ✅ Moteur PDF ReportLab (Génération, téléchargement inline, anti-traversal)
- ✅ Suite Bureautique Excel & PowerPoint
- ✅ Moteur DataViz 300 DPI (Multi-thèmes, inline web)
- ✅ Architecte Visuel Mermaid (Rendu chat, viewer HTML pan/zoom & export SVG)

---

## 📄 Licence & Crédits

- Développé et maintenu par **Kelvix / RIOT Team**.
- Licence : MIT.
