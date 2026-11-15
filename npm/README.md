# @kelvix/riot

Wrapper CLI multiplateforme permettant d'installer et d'exécuter **RIOT** via `npm` sur Windows, macOS et Linux.

## Installation globale (sur n'importe quelle machine)

1. Publier d'abord le dépôt Python sur GitHub (ou PyPI), puis publier ce package :
   ```bash
   cd npm
   npm login
   npm publish --access public
   ```

2. Installer sur n'importe quelle autre machine :
   ```bash
   npm install -g @kelvix/riot
   riot
   ```

## Test local avant publication

```bash
cd npm
npm link
riot /pc
```

## Variables d'environnement utiles

- `RIOT_SOURCE` : URL Git ou chemin local du package Python RIOT.
- `RIOT_EXTRAS` : Extras optionnels à installer (`voice`, `browser`, `office`, `media`, `integrations`, `cuda`, `all`).
- `RIOT_CONFIG` : Chemin personnalisé vers `config.yaml` (par défaut `~/.riot/config.yaml`).
- `RIOT_PROJECTS_DIR` : Dossier racine des projets par défaut.

## Mise à jour du CLI

```bash
riot --update-cli
```

