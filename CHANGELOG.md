# Changelog

Toutes les évolutions notables de RIOT. Format inspiré de
[Keep a Changelog](https://keepachangelog.com/fr/) ; versionnage
[SemVer](https://semver.org/lang/fr/).

## [0.3.12] — 2026-11-22

### Ajouté
- **Récupération & Validation Admin vers Mémoire Globale (`/admin/lessons` & `/v1/playbook/global`)** : les leçons apprises chez les utilisateurs (via Mentor ou auto-extraction, anonymisées et dédupliquées avec compteur d'occurrences) remontent en file `pending` sur le portail `/admin` ; l'administrateur peut les éditer, approuver (`Intégrer à la Mémoire Globale`), rejeter ou supprimer. Chaque client RIOT synchronise automatiquement les leçons approuvées (`source: "global_curated"`).

### Corrigé
- **`agy CLI --json-schema` sur `VerdictMentor`** : aplatissement récursif des références `$defs`/`$ref`, lecture prioritaire de `structured_output`, repli résilient sans erreur Pydantic `EOF` si la réponse CLI est textuelle/vide, et suppression du faux avertissement `No module named 'google'` lorsque `agy` est utilisé sans SDK optionnel.

## [0.3.11] — 2026-11-22

### Ajouté
- **Télémétrie anonymisée du Mode Mentor (`POST /v1/telemetry/mentor`)** : les directives, verdicts (`APPROUVE` / `CORRIGE` / `ERREURS`), latences, tokens et leçons distillées issus d'Antigravity (`agy` CLI / SDK) sont désormais remontés de manière asynchrone et anonymisée (chemins et secrets masqués) vers le proxy/portail `/admin` (`source: "mentor"`), désactivable via `mentor.telemetrie: false`.

## [0.3.10] — 2026-11-22

### Ajouté
- **Mode Mentor Antigravity ouvert à tous les utilisateurs** : support prioritaire du CLI officiel `agy` (utilise directement la session Antigravity IDE / Google AI Pro de l'utilisateur sans `GEMINI_API_KEY` séparée), avec repli automatique sur `google-antigravity` SDK + `GEMINI_API_KEY`.
- **Gouvernance de Mémoire & Playbook Public** : table `recettes_code` enrichie (`scope`, `interdits`, `verification`, `confiance`, auto-archivage sous 30 %, anonymisation des chemins), onglet IDE `🧠 Playbook` + `🎓 Mentor AGY`, et auto-import au démarrage de `data/riot_playbook_public.json`.

## [0.3.9] — 2026-11-22

### Ajouté
- **Application Desktop Windows (`desktop/`)** : Coque Electron unifiée (`IDE`, `Studio`, `Mobile`, `Réglages`), System Tray, raccourci global `Ctrl+Alt+R`, sélecteur de dossiers OS natif, mode serveur headless `riot --server`, mise à jour moteur 1-clic et génération d'installeurs NSIS & Portable Windows.
- **Application Mobile Native (`mobile-app/`)** : Projet Expo Router / React Native TypeScript (`Agent`, `Cockpit`, `Terminal biométrique`, `Réglages`), appairage QR à usage unique généré localement (`segno`, `/api/mobile/pair/*`), stockage chiffré `expo-secure-store` et **Notifications Push Expo** (déclenchées sur fin `/swarm` & patches IDE).
- **QR Code intégré** : Affichage direct dans RIOT Desktop (`📱 Mobile`) et dans `/panneau`.
- **Benchmark RIOT (`scripts/benchmark_riot.py`)** : Mesures reproductibles locales & LLM live.

### Sécurité & Qualité
- Garde tunnel distant sur RIOT Studio (`core/studio_app.py`) bloquant tout accès non authentifié via proxy/Cloudflare.
- Suppression du contournement `confirme=True` sur le terminal mobile (`core/mobile.py`).
- Autorisation sécurisée du projet actif dans `tools/rendu_visuel.py`, continuité inter-modèles dans `core/ide.py`, timeout terminal étendu à 120s et refonte du sélecteur de dossiers IDE (récents persistants, fil d'Ariane, filtre, badge `.git`).
- Suppression complète du branding hérité tiers au profit de **RIOT**.

## [0.3.8] — 2026-11-22

### Ajouté
- Accès utilisateur 24h illimité (protection anti-rafale RPM conservée).
- Routage dédié par sous-agent (`RIOT-Architect`, `RIOT-Engineer`, `RIOT-Tester`, `RIOT-Reviewer`, `RIOT-Trader`) et `JournalContinuite` inter-modèles.
- Compatibilité native FreeLLMAPI Desktop (`127.0.0.1:31415/v1`) et `max_tokens` étendu jusqu'à 8 192 tokens en code.

## [1.0.0] — 2026-08-07

Première version publique. Assistant vocal local en français, architecture
modulaire, deux modes (cloud / local hors ligne).

### Cœur
- Chaîne vocale : openWakeWord (« Hey Jarvis ») → faster-whisper (STT local) →
  LLM → synthèse vocale, avec fenêtre de suivi pour enchaîner sans redire le mot-clé.
- Architecture modulaire : chaque outil est un fichier de `tools/` auto-découvert
  (décorateur `@outil`), registre central, `config.yaml` unique non versionné.
- Confirmation vocale des actions irréversibles ; interruption « attends/stop »
  (barge-in anti-écho) ; accusé de réception immédiat pour les outils lents.
- Abstraction des providers (mode `cloud` | `local`) :
  - LLM : **Anthropic** (Anthropic) ou **Ollama** (`qwen3.5:4b`…), même interface.
  - TTS : **ElevenLabs** ou, en local, **Piper** / **Kokoro** (repli voix Windows).
  - STT : faster-whisper (local dans les deux modes, GPU si dispo).

### Outils
- Domotique : Philips Hue (allumer, luminosité, couleur), ambiances/scènes.
- PC & streaming : OBS (direct, enregistrement, scènes, replay), stats système,
  lancement d'apps, média/volume, capture d'écran (vision).
- Productivité : Google Agenda (tous les agendas, y compris iCal abonnés),
  Gmail, brief du matin, mémoire long terme, minuteurs, météo, personnalités.
- Présence : détection par ping du téléphone, modes automatiques.
- Web : recherche, réservation pilotée par LLM (Playwright), assistance sur le
  vrai Chrome (CDP) avec domaines protégés en lecture seule.
- Communication : Discord (mentions + messages du jour), Instagram (abonnés &
  vues vs la veille, multi-comptes, refresh auto des tokens), appels Twilio
  (message simple V1, conversation temps réel V2).
- Serveur MCP : expose les outils domotique/PC à tout client MCP (Client MCP Desktop,
  Hermes), liste blanche par outil.

### Confidentialité & sécurité
- Secrets et données perso jamais versionnés (config, mémoire, logs, transcriptions
  d'appels, tokens OAuth, profils navigateur).
- Appels téléphoniques : présentation honnête comme assistant automatisé ; jamais
  de données bancaires ni de mots de passe ; blocage des numéros surtaxés.

### Installation
- Installateur interactif `scripts/setup.py` et diagnostic `scripts/doctor.py`.
- `INSTALL_WITH_AI.md` (FR/EN) : guide agnostique pour installer via n'importe
  quelle IA gratuite.
- Documentation par intégration dans `docs/`, README FR (défaut) + EN.

[1.0.0]: https://github.com/sosoj92/jarvis-assistant-vocal/releases/tag/v1.0.0
