# 🧠 Mémoire Gouvernée, Playbook & Mode Mentor Antigravity

Ce guide explique **où est stockée la mémoire apprise de RIOT**, **comment la gérer**, et **comment activer le Mode Mentor Antigravity**.

---

## 1. Où est stocké tout ce que RIOT apprend ?

Toute l'expérience accumulée par RIOT au fil des sessions est persistée **localement sur la machine** dans une base SQLite haute performance (mode WAL + recherche plein texte **FTS5**) :

- **Fichier principal :** `~/.riot/riot_memory.db` *(soit `C:\Users\<VOTRE_NOM>\.riot\riot_memory.db` sous Windows, surchargeable via `RIOT_MEMORY_DB`)*
  - **Table `memoire_entites`** : faits utilisateur, préférences, contexte projets et règles de développement (`regles_dev`).
  - **Table `recettes_code`** : leçons apprises par RIOT et le Mentor Antigravity avec métadonnées de gouvernance :
    - `scope` : `global`, `stack:<techno>` ou `project:<nom>` (une leçon d'un projet privé A n'est jamais injectée dans un projet B) ;
    - `interdits` : ce qu'il faut éviter ;
    - `verification` : commande ou test qui valide la règle ;
    - `confiance` (`0.0` à `1.0`) : augmente sur succès (`+0.12`), baisse sur erreur (`-0.25`) et auto-archive (`archived`) sous `0.30` ou après 3 échecs.
  - **Table `chat_sessions` / `chat_messages`** : historique des discussions RIOT Studio.
- **Synchronisation Cloud optionnelle (Neon PostgreSQL)** : les entités et recettes peuvent être synchronisées entre plusieurs postes via `/memory sync` (avec anonymisation des secrets et chemins personnels `<HOME>`, `<PROJET>`).
- **Playbook Public Partageable :** `data/riot_playbook_public.json`
  - Contient uniquement les leçons `active` globales/stack avec `confiance >= 0.70`, anonymisées.
  - Importé **automatiquement** au premier démarrage de RIOT chez tout nouvel utilisateur.

---

## 2. Gérer le Playbook & la Mémoire (Pour tous les utilisateurs)

### Dans RIOT IDE (`/ide` ou RIOT Desktop)
1. Cliquez sur le bouton **`🧠 Playbook`** dans la barre supérieure droite de l'IDE.
2. Vous pouvez :
   - **Filtrer** par statut (`Actives` / `Archivées` / `Toutes`) ou mot-clé ;
   - **Promouvoir en Global** (`🌐 Global`), augmenter la confiance (`+ Confiance`), **Archiver / Réactiver** (`📦` / `♻️`) ou **Supprimer** (`🗑️`) une leçon ;
   - **Purger** en 1 clic les règles peu fiables (`🧹 Purger`) ;
   - **Exporter** le Playbook public anonymisé vers `data/riot_playbook_public.json` (`📤 Exporter Public`).

### En ligne de commande (`riot` CLI)
- `/memory` : afficher l'état de la mémoire locale et cloud.
- `/memory sync` : synchroniser avec Neon Cloud.
- `/memory forget <sujet>` : supprimer des souvenirs par mot-clé.

---

## 3. Activer le Mode Mentor Antigravity *(Pour tout utilisateur ayant Antigravity)*

Le Mode Mentor branche RIOT à Antigravity en 2 passes bornées :
1. **Avant que RIOT code** : Antigravity inspecte le dossier en lecture seule et produit un cadrage strict (`Plan`, `À faire`, `À éviter`, `Critères de validation`).
2. **Après le travail de RIOT** : Antigravity vérifie les modifications, corrige si autorisé, et distille des leçons atomiques dans `~/.riot/riot_memory.db`.

### Option A — Via Antigravity IDE / CLI (`agy`) *(Recommandé : fonctionne directement avec votre abonnement Google AI Pro)*

**Démarrage Express (3 étapes)** — dans le terminal intégré d'**Antigravity IDE** (ou tout terminal connecté à votre session Google AI Pro) :

```bash
# 1. Installer ou mettre à jour RIOT (v0.3.11+)
npm install -g @riotlagrinta/riot@latest

# 2. Connecter votre compte RIOT (indispensable pour la passerelle & le suivi)
riot login

# 3. Lancer RIOT et activer le Mode Mentor Antigravity
riot
# Puis dans RIOT :
/mentor status
/mentor on
```

- **Aucune `GEMINI_API_KEY` supplémentaire n'est requise** : RIOT détecte automatiquement `agy` en priorité.
- En interface web (`riot --ide`), cochez simplement **`🎓 Mentor AGY`** dans le panneau Agent.
- **Télémétrie anonymisée (opt-out)** : les résumés des directives, verdicts (`APPROUVE` / `CORRIGE` / `ERREURS`) et leçons distillées sont remontés de façon asynchrone et anonymisée (chemins locaux et secrets masqués) vers la passerelle. Pour désactiver cette remontée, ajoutez `mentor: { telemetrie: false }` dans `~/.riot/config.yaml`.

### Option B — Via le SDK Python (`[mentor]`) + `GEMINI_API_KEY`
- Installez l'extra optionnel `pip install "riot[mentor]"` (ou `RIOT_EXTRAS=mentor`) et renseignez `GEMINI_API_KEY` (ou `gemini.cle` dans `config.yaml`).

### Activation / Désactivation
- **Dans RIOT IDE** : cochez **`🎓 Mentor AGY`** dans le panneau Agent, puis lancez une requête en mode `Code` ou `Swarm`.
- **En CLI** :
  - `/mentor on` : activer l'audit Mentor Antigravity ;
  - `/mentor off` : désactiver (recommandé en usage courant pour garder la latence minimale) ;
  - `/mentor status` : voir l'état du SDK et les statistiques du Playbook ;
  - `/mentor prune` : archiver automatiquement les leçons sous 30 % de confiance ;
  - `/mentor export` : générer `data/riot_playbook_public.json` pour publication.
