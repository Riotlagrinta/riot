# RIOT Engine Gateway (Proxy Cloud Serveur)

Permet d'héberger **vos propres clés LLM côté serveur** (Render, Railway, Fly.io, VPS) afin que les utilisateurs finaux de RIOT :
- **n'entrent aucune clé API**,
- **ne voient aucun modèle tiers** (`model` est réécrit en `"riot-engine"`),
- restent protégés par votre rate-limit (`RIOT_PROXY_RPM`) et votre jeton optionnel (`RIOT_PROXY_TOKEN`).

## Déploiement rapide (Render / Railway)

- **Build command :** `pip install -r proxy/requirements.txt`
- **Start command :** `uvicorn proxy.server:app --host 0.0.0.0 --port $PORT`
- **Variables d'environnement secrètes :**
  - `MISTRAL_API_KEY=...`
  - `GROQ_API_KEY=...`
  - `GEMINI_API_KEY=...`
  - `OPENROUTER_API_KEY=...`
  - `RIOT_PROXY_TOKEN=riot_client_token_secret` *(optionnel)*
  - `RIOT_PROXY_RPM=30`

## Branchement côté clients RIOT

```bash
RIOT_GATEWAY_URL=https://votre-proxy.onrender.com/v1
RIOT_GATEWAY_TOKEN=riot_client_token_secret
```
*(En mode créateur sur votre PC de développement, gardez `RIOT_ADMIN=1` ou `admin_mode: true` dans `config.yaml` pour garder l'accès direct complet.)*
