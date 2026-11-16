# @riotlagrinta/riot

**RIOT** — IDE agentique, Studio Web/Mobile et copilote développeur multiplateforme (Windows, macOS, Linux).

## Installation & Démarrage

```bash
npm install -g @riotlagrinta/riot
riot
```

## Modes principaux

- `riot` : Terminal interactif multi-agents (`/swarm`, `/architect`, `/engineer`, `/test`, `/review`, `/trade`).
- `riot --ide` *(ou `/ide`)* : **RIOT IDE** multi-panneaux (explorateur Git, CodeMirror, revue de diff Accepter/Rejeter avant écriture, terminal intégré, palette `Ctrl+P`, agent copilote).
- `riot --app` *(ou `/studio`)* : **RIOT Studio** (interface web & application bureau + génération de maquettes/images).
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
