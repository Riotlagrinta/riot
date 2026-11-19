# Guide Utilisateur — Mémoire Hybride, Accès Web, Connecteurs MCP & `grill-me` (RIOT v0.3.3+)

Ce guide explique comment utiliser toutes les nouvelles capacités de **RIOT** dans la **CLI (`riot`)**, **RIOT IDE (`riot --ide`)** et **RIOT Studio (`riot --app`)**.

---

## 1. Mémoire Persistante Long Terme (Local + Cloud Neon)

RIOT mémorise durablement vos préférences, vos projets actifs, vos règles d'ingénierie et vos recettes de résolution de bugs.

- **Stockage local protégé** : `~/.riot/riot_memory.db` (SQLite WAL + recherche plein texte FTS5), conservé même après une mise à jour (`riot --update-cli`).
- **Synchro Cloud multi-postes** : dès que vous êtes connecté via `riot login`, votre mémoire est automatiquement synchronisée sur votre compte **Neon PostgreSQL** entre vos différents PC (y compris les suppressions).
- **Auto-extraction silencieuse** : après des échanges techniques importants ou quand vous exprimez une préférence durable, RIOT extrait et enregistre automatiquement les faits/recettes utiles en arrière-plan (avec masquage automatique de tout secret ou clé API).

### Commandes CLI
```text
/memory                   # Affiche l'état Cloud et tout ce que RIOT retient
/memory sync              # Force une synchronisation immédiate avec RIOT Cloud
/memory forget <sujet>    # Oublie et supprime un élément partout (local + Cloud)
```

### En langage naturel (CLI, IDE, Studio)
- *« Retiens que mes projets backend utilisent FastAPI et pytest »* (`remember`)
- *« Quelles règles as-tu retenues sur mon projet ? »* (`recall`, `lister_regles`)
- *« Enregistre comment on a résolu ce bug CORS »* (`enregistrer_recette_dev`)
- *« Oublie tout ce qui concerne le projet X »* (`forget`)

---

## 2. Recherche Internet Sourcée & Lecture Web (Anti-Hallucination)

Pour les versions récentes de librairies, l'actualité ou toute donnée incertaine, RIOT va vérifier sur Internet au lieu d'inventer et cite ses URLs sources.

- **`chercher_web`** : retourne titres, URLs exactes et extraits vérifiés (et lit automatiquement les 2 meilleures pages si `approfondir=True`).
- **`lire_page_web`** / **`recueillir_veille_web`** : ouvre une documentation officielle ou un article complet, nettoie le HTML/JS et protège contre les injections de prompt et attaques SSRF.
- **Passerelle & Moteurs supportés** : `Perplexity Sonar` → `Tavily` → `Firecrawl` → `Brave Search` → `DuckDuckGo` → `Wikipedia` (côté passerelle Cloud `/v1/web/search` & `/v1/web/scrape` ou via vos clés locales).

---

## 3. Connecteurs MCP & Outils Natifs (Firecrawl, Playwright, GitHub, Neon...)

Vos configurations MCP sont stockées dans **`~/.riot/mcp_servers.json`** (préservé lors des mises à jour) et supportent les transports `stdio`, `sse` et `http` (*Streamable HTTP*).

### Catalogue de 15 connecteurs prêts en 1 commande
| Catégorie | Connecteurs disponibles | Clé requise |
| :--- | :--- | :--- |
| **Web & Navigateur** | `fetch`, `playwright` | **Aucune (0 clé)** |
| **Web & Scraping avancé** | `firecrawl`, `brave_search`, `tavily`, `perplexity` | `FIRECRAWL_API_KEY`, `BRAVE_API_KEY`, etc. |
| **Dev & Bases de données** | `context7` *(docs à jour)* | **Aucune (0 clé)** |
| **Dev & Cloud DB** | `github`, `postgres`, `neon`, `supabase` | `GITHUB_PERSONAL_ACCESS_TOKEN`, `POSTGRES_URL`, `NEON_API_KEY`, `SUPABASE_ACCESS_TOKEN` |
| **SaaS & Productivité** | `notion`, `slack`, `stripe`, `google_workspace` | `NOTION_TOKEN`, `SLACK_BOT_TOKEN`, `STRIPE_SECRET_KEY`, OAuth Google |

### Utilisation dans la CLI
```text
/mcp catalog                        # Liste les 15 connecteurs et leurs prérequis
/mcp add context7                   # Installe et active Context7 (0 clé)
/mcp add playwright                 # Installe et active Playwright MCP (0 clé)
/mcp add firecrawl fc-votre-cle     # Installe Firecrawl avec votre clé API
/mcp enable <nom> | /mcp disable <nom>
/mcp reload                         # Recharge à chaud sans redémarrer RIOT
```

### Utilisation dans RIOT IDE (`riot --ide`)
Cliquez sur le bouton **`🔌 MCP`** en haut à droite de l'IDE pour voir l'état de vos serveurs, installer ou activer/désactiver chaque connecteur en un clic.

### Outils natifs intégrés (0 Node.js requis)
- **Git** : `git_status`, `git_diff`, `git_log` sur le projet actif.
- **GitHub REST** : `github_repo_info` (dépôts publics sans clé, privés via `GITHUB_PERSONAL_ACCESS_TOKEN`).
- **API HTTP sécurisée** : `requete_api_http` (GET/POST/PUT/PATCH/DELETE avec protection anti-SSRF).
- **Pilotage MCP en langage naturel** : demandez simplement *« Liste les connecteurs MCP »* ou *« Active context7 »*.

---

## 4. Mode Clarification `grill-me` (Cadrage avant d'agir)

L'outil **`grill-me`** permet à RIOT de vous poser **1 à 4 questions ciblées** (avec options et recommandation par défaut) avant de coder ou d'exécuter une modification importante.

- **Dans la CLI** :
  - `/grill-me on` : active la clarification systématique sur chaque nouveau prompt.
  - `/grill-me off` : revient au mode direct.
  - `/grill-me <sujet>` : lance un cadrage immédiat sur un sujet précis (ex: `/grill-me Créer une API de paiement T-Money`).
- **Dans RIOT IDE** : cochez **`Clarifier avant d'agir (grill-me)`** sous les modes `Code / Plan / Swarm / Ask`, ou préfixez votre message par `/grill-me`.
- **En chat libre / Studio** : l'agent appelle automatiquement `grill-me` dès qu'une demande présente de vraies ambiguïtés.
