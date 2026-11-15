# 📚 Centre d'Apprentissage & Tutorat Multimédia RIOT

Déposez ici vos ressources d'apprentissage, formations et cours :
- **Documents & Code** : `.pdf`, `.md`, `.txt`, `.py`, `.sql`, `.json`, etc.
- **Formations Vidéo Longues (jusqu'à 15h)** : `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`.

### 🚀 Fonctionnalités Automatisées de RIOT :
1. **Zéro Gaspillage de Quota** : Traitement local autonome via Python et FFmpeg. Aucun quota d'API externe n'est gaspillé.
2. **Découpage en segments (30-45 min)** pour un traitement fluide des formations géantes sans saturer la mémoire vive.
3. **Extraction de Keyframes HD** : RIOT capture automatiquement les diapositives, schémas d'architecture et fenêtres de code montrées par le formateur dans `etude/keyframes/`.
4. **Distillation dans le Livre de Recettes** : Les résolutions de bugs et patterns expliqués dans le cours sont automatiquement indexés dans `recettes_code`.
5. **Règles d'Ingénierie Dev** : Les bonnes pratiques fortes sont mémorisées dans `memoire_entites` (`regles_dev`).
6. **Recherche RAG SQLite FTS5** : Posez n'importe quelle question technique à RIOT depuis le terminal ou vocalement :
   - *« RIOT, qu'as-tu appris dans la formation Docker ? »*
   - *« Montre-moi les schémas d'architecture de Next.js »*
