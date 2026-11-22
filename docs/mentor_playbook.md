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

## 3. Activer le Mode Mentor Antigravity *(Usage créateur / entraînement local)*

Le Mode Mentor branche RIOT au SDK officiel `google-antigravity` en 2 passes bornées :
1. **Avant que RIOT code** : Antigravity inspecte le dossier en lecture seule et produit un cadrage strict (`Plan`, `À faire`, `À éviter`, `Critères de validation`).
2. **Après le travail de RIOT** : Antigravity vérifie les modifications, corrige si autorisé, et distille des leçons atomiques dans `~/.riot/riot_memory.db`.

### Prérequis
- Installer l'extra optionnel : `pip install -e ".[mentor]"` (ou `google-antigravity>=0.1.24`).
- Avoir `GEMINI_API_KEY` (ou `gemini.cle` dans `config.yaml`) configurée.

### Activation / Désactivation
- **Dans RIOT IDE** : cochez la case **`🎓 Mentor AGY`** dans le panneau Agent (visible en mode créateur uniquement), puis lancez une requête en mode `Code` ou `Swarm`.
- **En CLI** :
  - `/mentor on` : activer l'audit Mentor Antigravity ;
  - `/mentor off` : désactiver (recommandé en usage courant pour garder la latence minimale) ;
  - `/mentor status` : voir l'état du SDK et les statistiques du Playbook ;
  - `/mentor prune` : archiver automatiquement les leçons sous 30 % de confiance ;
  - `/mentor export` : générer `data/riot_playbook_public.json` pour publication.
