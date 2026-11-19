# @riotlagrinta/riot

**RIOT** — IDE agentique, Studio Web/Mobile et copilote développeur multiplateforme (Windows, macOS, Linux).

## Installation & Démarrage

```bash
npm install -g @riotlagrinta/riot
riot
```

## Modes & Commandes principales

- `riot` : Terminal interactif multi-agents (`/swarm`, `/architect`, `/engineer`, `/test`, `/review`, `/trade`).
- `riot --ide` *(ou `/ide`)* : **RIOT IDE** multi-panneaux (explorateur Git, CodeMirror, revue de diff Accepter/Rejeter avant écriture, panneau `🔌 MCP`, mode `grill-me`, terminal intégré, palette `Ctrl+P`).
- `riot --app` *(ou `/studio`)* : **RIOT Studio** (interface web & application bureau + génération de maquettes/images).
- `/memory [sync|forget <sujet>]` : **Mémoire persistante hybride** (`~/.riot/riot_memory.db` SQLite FTS5 + synchronisation Cloud Neon multi-postes + auto-extraction silencieuse).
- `/mcp [catalog|add <slug> [cle]|reload]` : **Catalogue de 15 connecteurs MCP** prêts en 1 ligne (`context7`, `playwright`, `firecrawl`, `github`, `supabase`, `neon`, `postgres`, `notion`, `slack`, `stripe`...).
- `/grill-me [on|off|<sujet>]` : **Cadrage actif** — pose 1 à 4 questions ciblées avec recommandations avant d'agir.
- **Outil `content-strategy` (activé par défaut)** : génère une stratégie éditoriale complète (piliers, matrice canaux, calendrier 4 semaines, hooks & KPIs) exportée en Markdown.
- **Outil `anti-ai-slop` (activé par défaut)** : détecte et supprime les hooks génériques IA, badges emojis, halos flous et dégradés SaaS clichés de vos designs UI.
- **Accès Internet anti-hallucination (activé par défaut)** : `chercher_web`, `lire_page_web` (citations URLs vérifiables, Firecrawl / Perplexity / DuckDuckGo) + outils natifs Git (`git_status`, `git_diff`, `git_log`), GitHub & HTTP REST.
- `riot /theme [obsidian|paper|tactical]` : Bascule entre les 3 thèmes visuels (`Obsidian & Ambre`, `Encre & Émeraude`, `Tactical Ops`) sur CLI, IDE, Studio et Mobile.
- `/model custom` : Branche n'importe quelle passerelle compatible OpenAI (FreeLLMAPI, LiteLLM, LM Studio, DeepSeek) en plus de Groq, Mistral, Gemini, OpenRouter, Claude et Ollama.

## Mises à jour

RIOT vérifie automatiquement les nouvelles versions et vous prévient au démarrage (`/update` en CLI ou via le badge de mise à jour Web) :

```bash
riot --update-cli
# ou pour mettre à jour le lanceur npm :
npm install -g @riotlagrinta/riot@latest
```

## Variables d'environnement utiles

- `RIOT_SOURCE` : URL Git ou chemin local du package Python RIOT.
- `RIOT_EXTRAS` : Extras optionnels (`voice`, `browser`, `office`, `media`, `integrations`, `cuda`, `all`).
- `RIOT_CONFIG` : Chemin personnalisé vers `config.yaml` (par défaut `~/.riot/config.yaml`).
- `RIOT_PROJECTS_DIR` : Dossier racine des projets par défaut.
