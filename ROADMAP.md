# ⚡ ROADMAP & ÉTAT D'AVANCEMENT — RIOT

Ce document est le tableau de bord officiel de **RIOT** (anciennement Kéranos). Il récapitule l'ensemble des fonctionnalités implémentées, l'architecture logicielle, les tests de validation Zéro Erreur et les guides de lancement.

---

## 🎯 Vision Réalisée de RIOT

**RIOT** est votre copilote personnel de nouvelle génération, sans censure, configuré comme un expert technique polyvalent :
1. **Copilote d'élite** : Ultra-précis, factuel, sans avertissements moralisateurs ni leçons de conformité, alimenté par Groq (`openai/gpt-oss-120b`).
2. **0 % CPU au repos sur PC** : Écoute micro PC désactivée par défaut ; la dictée vocale se fait directement depuis votre smartphone via Web Speech API.
3. **Cockpit Mobile Cyberpunk PWA** : Interface tactile sombre Obsidian & Néon Cyan, ultra-fluide avec retour haptique, adaptée à une utilisation à une main.
4. **WebSocket Temps Réel (`/ws/riot`)** : Streaming mot à mot, retour immédiat des outils en cours d'exécution, et télémétrie push continue (CPU, RAM, Disque, Débit réseau KB/s).
5. **Terminal Universel Sécurisé** : Exécution de commandes PowerShell et CMD sans blocage artificiel, avec protection des processus Windows vitaux et confirmation pour les actions destructrices.
6. **Mémoire SQLite FTS5** : Base de données relationnelle persistante avec recherche plein texte BM25 instantanée pour retenir vos faits, règles de code et résolutions de bugs.
7. **Tuteur de Cours RAG (`etude/`)** : Déposez vos supports de cours (PDF, Markdown, texte, code) dans le dossier `etude/`. RIOT les indexe et répond précisément à vos révisions d'examens.
8. **Accès Distant 4G/5G Mondial** : Tunnel chiffré Cloudflare Quick Tunnel (`*.trycloudflare.com`) activable en 1 tap sans ouverture de ports sur votre box.
9. **Sécurité Militaire** : Accès protégé par code PIN haché en scrypt, jetons de session révocables, verrouillage anti-brute force et journal d'audit (`logs/audit.log`).

---

## 📊 Tableau de Bord d'Avancement Global

| Étape | Module / Fonctionnalité | Statut | Tests & Diagnostic |
| :--- | :--- | :---: | :---: |
| **Étape 1** | **Sécurité d'accès & PIN scrypt** | **100% TERMINÉ** | Validé (Fail-closed, 5 échecs = 15m lockout) |
| **Étape 2** | **Terminal universel & Gestion des processus** | **100% TERMINÉ** | Validé (PowerShell, CMD, inspection ports, kill PID) |
| **Étape 3** | **Mémoire SQLite FTS5 (Faits & Contexte)** | **100% TERMINÉ** | Validé (WAL mode, BM25, triggers FTS5) |
| **Étape 4** | **Carnet d'apprentissage & Recettes de dev** | **100% TERMINÉ** | Validé (API `/recettes` et `/regles`, injection LLM) |
| **Étape 5** | **Dossier `etude/` & Tuteur de cours RAG** | **100% TERMINÉ** | Validé (Extracteur PDF `pypdf`, chunking, sync FTS5) |
| **Étape 6** | **Tunnel Cloudflare 4G/5G Chiffré** | **100% TERMINÉ** | Validé (`bin/cloudflared.exe`, Quick Tunnel HTTPS) |
| **Étape 7** | **Moteur WebSocket Temps Réel (`/ws/riot`)** | **100% TERMINÉ** | Validé (Streaming tokens, telemetry push, ping/pong) |
| **Étape 8** | **Refonte Design Tactile Mobile (Cyberpunk Linear)** | **100% TERMINÉ** | Validé (PWA `web/mobile.html`, 4 onglets, haptique) |
| **Étape 9** | **Swarm Multi-Agents Autonome (Dev Pipeline)** | **100% TERMINÉ** | Validé (`RIOT-Architect` ➔ `Engineer` ➔ `Tester` ➔ `Reviewer`) |
| **Étape 10** | **Claude Desktop & Web Studio (`/claude`)** | **100% TERMINÉ** | Validé (3 panneaux, 28 projets auto, Artifacts viewer, PWA) |
| **Étape 11** | **Client & Serveur MCP Universel** | **100% TERMINÉ** | Validé (`core/mcp_client.py`, stdio & sse, 27 outils exportés) |
| **Étape 12** | **RIOT-Trader (Quant & Risk 1%)** | **100% TERMINÉ** | Validé (Binance Klines live, RSI, Carnet, Sizing 1%) |
| **Étape 13** | **RIOT-Raw (Agent Dé-Censuré Ultime)** | **100% TERMINÉ** | Validé (Ollama Dolphin local, 100% gratuit & privé, 0 filtre) |
| **Étape 14** | **Persistance SQLite Chats & Fichiers Joints** | **100% TERMINÉ** | Validé (Tables SQLite WAL, survie reboot, upload/drag&drop/paste) |
| **Étape 15** | **Suite Bureautique Exécutive (PDF, Excel, PPTX)** | **100% TERMINÉ** | Validé (ReportLab Platypus, OpenPyXL, Python-PPTX, 1-clic download) |
| **Étape 16** | **Skill DataViz & Graphiques 300 DPI** | **100% TERMINÉ** | Validé (Matplotlib Agg, courbes dégradées, barres, donuts, inline web) |
| **Étape 17** | **Skill Architecte Visuel (Mermaid & SVG)** | **100% TERMINÉ** | Validé (Mermaid v10, viewer HTML pan/zoom, export vectoriel SVG) |
| **Étape 18** | **Digital Product Factory (eBooks & Infoproduits)** | **100% TERMINÉ** | Validé (EBook PDF, Simulateur Excel, Landing Page HTML, Kit Copywriting, ZIP, Zéro Erreur) |
| **Étape 19** | **Inspecteur & Optimiseur SQL / PostGIS / Supabase RLS** | **100% TERMINÉ** | Validé (Audit DDL, Remédiation auto, GIST spatial, Supabase RLS, Zéro Erreur) |
| **Étape 20** | **Scaffolding & Composants Mobile (React Native / Expo)** | **100% TERMINÉ** | Validé (React Native 0.74, Expo Router v3, Carte Géo-spatiale, Modal Mobile Money Togo, Starter ZIP, Zéro Erreur) |
| **Étape 21** | **Veille & Scraping Sécurisé (Web & Crypto)** | **100% TERMINÉ** | Validé (Binance live direct, assainissement HTML anti-injections, Bulletins d'intelligence, Zéro Erreur) |
| **Étape 22** | **Studio Motion Design & Feedback Visuel (Playwright & Timing)** | **100% TERMINÉ** | Validé (Playwright Chromium, Contact Sheets PNG, Divulgation progressive, 10 recettes, Zéro Erreur) |

---

## 🤖 Guide des Sous-Agents Spécialisés de RIOT

RIOT orchestre un écosystème modulaire de sous-agents experts :

### 1. ⚡ Swarm Multi-Agents de Développement (`/swarm <tâche>`)
Pipeline d'ingénierie logicielle autonome inspiré des standards Anthropic / DeepMind :
1. **`RIOT-Architect`** : Analyse la base de code, explore l'arborescence et produit un plan d'action chirurgical.
2. **`RIOT-Engineer`** : Implémente le code via `patcher_code` et `ecrire_code`.
3. **`RIOT-Tester`** : Exécute les suites de tests unitaires avec boucle d'auto-guérison en cas d'échec.
4. **`RIOT-Reviewer`** : Audit de qualité de code, détection de régressions et validation finale.

### 2. 📈 RIOT-Trader (`/trade <actif>`)
Trader quantitatif institutionnel dédié au trading algorithmique et à la protection du capital :
* **Règle absolue du 1%** : Le risque financier par opération est rigoureusement limité à 1.0% du capital.
* **Calcul automatique de position** : $\text{Sizing} = (\text{Capital} \times 1\%) / (\text{Entrée} - \text{StopLoss})$.
* **Outils connectés** : `trading_analyse_technique` (RSI, SMA20/50, EMA20), `trading_carnet_ordres_express` (Profondeur Top 10 Bids/Asks), `trade_app_prix_crypto`.

### 3. 🔥 RIOT-Raw (`/raw <sujet>`)
Sous-agent souverain sans filtre moral, motorisé par un LLM non censuré en local :
* **Moteur d'inférence** : Ollama en local (`dolphin-phi:latest` à 1.6 Go ou `dolphin-llama3:latest` à 4.7 Go).
* **Détection dynamique** : Bascule automatique sur le meilleur modèle non censuré présent dans la machine.
* **Doctrine** : 0 prêche moral, 0 refus, analyse brute pour la cybersécurité offensive (pentest, reverse engineering), philosophie noire, scénarios de crise et débats sans tabou.
* **Accès** : En CLI (`/raw`), commande externe (`riot /raw`) ou interface Web (mode `🔥 RIOT Raw`).

---

## 🖥️ Applications & Interfaces Utilisateur

1. **Terminal Cyberpunk Interactif** :
   * Lancement : `python riot.py` ou `riot`
   * Commandes disponibles : `/swarm`, `/architect`, `/engineer`, `/test`, `/review`, `/trade`, `/raw`, `/mcp`, `/app`, `/pc`, `/tokens`.
2. **Claude Web & Desktop Studio** :
   * Lancement : `riot-app` ou `http://localhost:8790/claude`
   * Ergonomie façon Claude Code : Panneau gauche (sélection de projet, historique, modes d'action), Panneau central (chat streaming, tool cards animées), Panneau droit (Artifacts syntaxés et explorateur de fichiers).
3. **Application Tactile Mobile (PWA)** :
   * Accès : `http://<IP_LOCAL>:8790/mobile`
   * 4 espaces : Cockpit, Copilote vocal, Terminal shell, Tuteur RAG Étude.

---

## 🧪 Tests & Diagnostics Zéro Erreur

Pour valider l'intégrité complète de la plateforme :
```powershell
.\.venv\Scripts\python scripts/tester_mobile.py
.\.venv\Scripts\python scripts/tester_claude_web.py
.\.venv\Scripts\python scripts/tester_raw_agent.py
.\.venv\Scripts\python scripts/doctor.py
```
Résultat garanti : **100% des tests validés, 0 erreur.**
