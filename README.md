# ⚡ RIOT Studio (ex-Kéranos)

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

Initialement conçu sous le nom de **Kéranos** comme assistant vocal local souverain (Jarvis + Hermes), le projet a évolué pour devenir **RIOT Studio** : un environnement d'ingénierie logicielle autonome, d'analyse quantitative et de production documentaire d'élite.

L'écosystème réunit sous une même interface web réactive (PWA) des capacités avancées :
1. **Pipeline Swarm Multi-Agents** de développement autonome (Planification, Codage chirurgical, Tests unitaires auto-guérisseurs, Audit sécurité).
2. **RIOT-Trader** : Analyse quantitative, flux crypto en direct (Binance), carnet d'ordres et doctrine stricte de risk management (1% du capital max).
3. **RIOT-Raw** : Agent local 0 censure (Ollama Dolphin), 100% privé, sans filtres moraux pour l'audit de cybersécurité offensive et les scénarios de crise.
4. **Suite Exécutive & DataViz Intégrée** : Génération instantanée de livrables professionnels (PDF, classeurs Excel dynamiques, présentations PowerPoint 16:9, graphiques 300 DPI et schémas d'architecture Mermaid).

---

## 🚀 Les 4 Piliers Fondamentaux

### 1. 🤖 Pipeline Multi-Agents Autonome (Swarm) & Routage Adaptatif
Chaque sous-agent est piloté par un profil de modèle adapté à son rôle, tout en partageant un **Journal de Continuité Inter-Modèles** (`JournalContinuite`) pour ne jamais perdre le contexte lors d'une rotation d'IA :
- **📐 RIOT-Architect** (`deep` — *Sonnet 4.5 / Nemotron 3 Ultra 800k / DeepSeek*) : Explore l'arborescence, détecte la stack (`package.json`, `pyproject.toml`, Remotion) et conçoit le plan d'action chirurgical.
- **💻 RIOT-Engineer** (`code` — *Codestral Latest / Sonnet 4.5 / DeepSeek*, sortie jusqu'à **8 192 tokens**) : Applique les modifications via `patcher_code` tolérant et `ecrire_code` dans une boucle étendue à **10 tours** avec synthèse finale garantie.
- **🧪 RIOT-Tester** (`agent` — *GPT-OSS 120B / Qwen 3.6 27B / Llama 3.3 70B*) : Exécute les tests unitaires et vérifie le code sans gaspiller les modèles codeurs.
- **🛡️ RIOT-Reviewer** (`deep`) : Audit de conformité, détection de secrets (`vcp_`, `freellmapi-`, `sk-`, `gsk_`, `ghp_`), vérification du typage et verdict final `[APPROUVÉ]`.

**Moteur Adaptatif & Modèles supportés (`RIOT Engine` + `FreeLLMAPI`) :**
- **Code & Architecture (`code` / `deep`)** : `codestral-latest`, `Sonnet 4.5`, `deepseek-chat` / `deepseek-reasoner`, `nemotron-3-ultra-550b` (`800k` ctx), `nemotron-3.5-lightning` (`838 860` ctx).
- **Agent & Rapide (`agent` / `fast`)** : `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-3.3-70b-versatile`, `qwen3.6-27b`, `gemini-flash-lite-latest`, `Haiku 4.5`.
- **Pool Multi-Clés & Zéro Plafond Journalier** : Rotation Round-Robin sur pools de clés (`GROQ_API_KEY="cle1,cle2"`), failover automatique HTTP `413`/`429`, compaction des schémas d'outils (-45 %) et accès utilisateur 24h **illimité**.
- **Compatible FreeLLMAPI Desktop** : Détection native sur `http://127.0.0.1:31415/v1` via `/model freellmapi` (avec bascule adaptative automatique selon la tâche).

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

### 1. Studio Web RIOT (`http://localhost:8790/`)
- **Tri-panneau moderne** :
  - *Gauche* : Sélecteur de projets réels (28+ projets indexés automatiquement), historique persistant des discussions SQLite, modes rapides (`/swarm`, `/trade`, `/raw`, `/architect`, `/review`).
  - *Centre* : Chat fluide en Server-Sent Events (SSE), téléversement direct de fichiers (bouton trombone, drag & drop, collage presse-papier), cartes d'outils animées.
  - *Droite* : Explorateur de fichiers interactif et visionneuse d'Artifacts syntaxés.
- **Persistance intégrale** : Base de données `riot_memory.db` en mode WAL avec recherche plein texte BM25 (FTS5). Les discussions et fichiers joints survivent à tous les redémarrages.

### 2. Application Bureau Windows (`desktop/` — `RIOT Desktop`)
- **Coque Windows Electron dédiée** (`RIOT-Setup` NSIS & `RIOT-Portable` x64) réunissant **IDE**, **Studio**, **Cockpit Mobile** et **Réglages** dans une seule fenêtre sombre.
- **Intégration Windows native** : System Tray (réduction sans couper les tâches en cours), raccourci global **`Ctrl+Alt+R`**, sélecteur de dossiers natif relié à l'IDE, mise à jour moteur en 1 clic (`↻ Màj`) et modale **`📱 Mobile`** générant un QR Code localement (via `segno`).

### 3. Application Mobile Native (`mobile-app/` — Android & iOS) & Cockpit PWA (`http://localhost:8790/mobile`)
- **App Native Expo / React Native** ([mobile-app/](mobile-app)) avec stockage chiffré (`expo-secure-store`), bascule automatique **LAN → Tunnel Cloudflare HTTPS**, streaming WebSocket temps réel, terminal protégé par **confirmation biométrique** (`expo-local-authentication`) et **Notifications Push natives** (`expo-notifications`) à la fin des pipelines Swarm et revues IDE.
- **Appairage QR à usage unique** : `/api/mobile/pair/generer` (valable 5 min, SVG local) et `/api/mobile/pair/echanger`.
- **Cockpit PWA** (`http://localhost:8790/mobile`) : télémétrie CPU/RAM/Disque, terminal, tunnel et tuteur RAG (`etude/`).

### 4. Terminal Cyberpunk CLI & RIOT IDE (`riot --ide`)
- Lancement CLI : `riot` ou `python riot.py` — Lancement IDE : `riot --ide` ou `/ide` — Serveur headless : `riot --server`.
- **Sélection de dossiers fluide** : projets récents persistants (`~/.riot/ide_recent_projects.json`), fil d'Ariane cliquable, filtre instantané, création de dossier et badge `.git`.
- **Sécurité renforcée** : garde d'accès tunnel sur RIOT Studio (`/` & `/api/studio/*`) et confirmation obligatoire (`confirme=False` par défaut) sur le terminal mobile.
- **Mémoire Hybride, Gouvernance & Playbook (`~/.riot/riot_memory.db`)** : SQLite FTS5 persistante synchronisée sur Neon PostgreSQL (`/memory`, `/memory sync`, `/memory forget <sujet>`). Chaque leçon apprise dispose d'un `scope` (`global`, `stack:*`, `project:*`), d'un score de `confiance` (auto-archivage sous 30 %) et peut être gérée dans l'IDE via **`🧠 Playbook`** (`Purger`, `Promouvoir`, `Exporter Public` -> `data/riot_playbook_public.json` chargé automatiquement chez les utilisateurs).
- **Mode Mentor Antigravity (`🎓 Mentor AGY` / `/mentor on`)** *(usage créateur local via extra `[mentor]` `google-antigravity`)* : boucle optionnelle Pré-cadrage (`À faire` / `À éviter`) -> Exécution RIOT -> Post-audit & distillation vers le Playbook. Guide complet : [docs/mentor_playbook.md](docs/mentor_playbook.md).
- **Accès Internet Anti-Hallucination** : `chercher_web` + `lire_page_web` avec sources vérifiées (Perplexity, Tavily, Firecrawl, Brave, DuckDuckGo, Wikipedia).
- **15 Connecteurs MCP & Outils natifs** : `/mcp catalog`, `/mcp add <slug>` (`firecrawl`, `playwright`, `context7`, `github`, `neon`, `supabase`, `notion`, `stripe`...) + bouton `🔌 MCP` dans l'IDE + outils Git (`git_status`, `git_diff`, `git_log`), GitHub & API HTTP sécurisée.
- **Mode Cadrage `grill-me`, `content-strategy`, `anti-ai-slop` & `seo-audit` (activés par défaut)** : `/grill-me on|off|<sujet>` ou case `Clarifier avant d'agir (grill-me)` dans l'IDE, `content-strategy` pour vos plans éditoriaux, `anti-ai-slop` pour éliminer les clichés IA de vos designs, et `seo-audit` pour optimiser le référencement Google de vos sites.
- Guide détaillé : [docs/connecteurs_et_outils.md](docs/connecteurs_et_outils.md).

---

## 🛠️ Démarrage Rapide

### Prérequis
- Windows 11
- Python 3.11+ (recommandé : environnement virtuel `.venv`)
- Node.js 18+ *(pour le lanceur npm, RIOT Desktop ou `mobile-app`)*
- *(Optionnel pour mode Raw)* : [Ollama](https://ollama.com/) avec modèle Dolphin installé.

### Lancement
```powershell
# 0. Installation globale recommandée (npm + uv)
npm install -g @riotlagrinta/riot@latest
riot login

# 1. Lancer la console interactive CLI / IDE / Studio / Serveur
riot            # CLI interactif
riot --ide      # RIOT IDE Web (diff review, terminal 120s, MCP)
riot --app      # RIOT Studio Web (Port 8790)
riot --server   # Serveur backend headless (utilise par RIOT Desktop)

# 2. Builder l'app Windows Desktop ou lancer l'app Mobile Expo
cd desktop && npm install && npm run build:win
cd mobile-app && npm install && npx expo start
```

---

## 🧪 Diagnostic Zéro Erreur & Benchmark

La plateforme applique une politique stricte de **Zéro Erreur**. Une suite de **25 tests automatisés** valide la totalité des composants avant chaque déploiement, complétée par un benchmark reproductible :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_riot_core.py -v
.\.venv\Scripts\python.exe scripts/benchmark_riot.py --live
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
