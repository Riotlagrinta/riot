# Composition et mise en page

## Sommaire
1. Hiérarchie : où va le regard
2. Grille et espacements
3. Alignement
4. Le hero
5. Rythme d'une page
6. Responsive
7. Composants : cohérence

---

## 1. Hiérarchie : où va le regard

Avant de coder, décide l'ordre de lecture en trois niveaux :
1. Ce que la personne doit voir **en premier** (une seule chose)
2. Ce qu'elle doit voir **ensuite**
3. Ce qui reste disponible mais discret

Obtiens la hiérarchie par l'**échelle**, le **contraste** (valeur, couleur),
l'**espace** autour et la **position**, avant d'utiliser la graisse, les
bordures ou les cadres. Une page où tout est mis en avant n'a pas de hiérarchie.

## 2. Grille et espacements

- Base de **4 px** (ou 8 px) pour tous les espacements : valeurs tirées de l'échelle de tokens.
- Les espaces **entre** les groupes sont nettement plus grands que les espaces
  **à l'intérieur** des groupes. C'est ce qui crée la lecture en blocs
  (proximité). Rapport indicatif : ×2 à ×3.
- Marges de section généreuses (`--e-16` à `--e-24` en bureau). L'espace vide
  est un outil de composition, pas un oubli.
- Grille de 12 colonnes (CSS Grid) pour les pages riches ; pour une page
  éditoriale, une colonne de texte de 60-70ch avec des éléments qui débordent.
- Évite le centrage systématique d'un contenu à largeur unique pour toutes
  les sections : varie les largeurs et les points d'ancrage pour créer du rythme.

```css
.page { display: grid;
  grid-template-columns: [plein-debut] minmax(1rem, 1fr) [contenu-debut] minmax(0, 68rem) [contenu-fin] minmax(1rem, 1fr) [plein-fin]; }
.page > * { grid-column: contenu; }
.page > .plein { grid-column: plein; }   /* éléments qui sortent de la colonne */
```

## 3. Alignement

Choisis un parti pris et tiens-le :
- **Aligné à gauche** : lisible, sobre, le choix par défaut pour du texte.
- **Centré** : pour une phrase courte, un moment solennel, un hero. Pas pour du texte long.
- **Asymétrique** : un titre décalé, une colonne étroite à côté d'un grand
  visuel. Donne de la personnalité si l'axe reste lisible.

Aligne les éléments sur des axes communs (bord gauche du titre, du texte et du
bouton). Les petits décalages involontaires se voient.

## 4. Le hero

Le hero est la première chose vue. Ouvre avec **l'élément le plus caractéristique
du monde du sujet**, sous la forme qui lui convient : un titre fort, un
visuel, une animation, une démonstration vivante, un moment interactif.

Le traitement par défaut (un grand chiffre avec un petit libellé, des
statistiques de soutien et un accent en dégradé) est un réflexe courant : ne
le garde que s'il est vraiment le meilleur choix pour ce sujet.

Un bon hero :
- dit **ce que c'est** et **pour qui** dès la première lecture,
- propose **une** action principale claire,
- ne contient pas plus de trois niveaux de texte,
- laisse respirer (pas de bloc de texte dense au-dessus de la ligne de flottaison).

## 5. Rythme d'une page

Une page lisible alterne : dense / aéré, texte / visuel, large / étroit,
sombre / clair si la palette le permet. Trois sections au même gabarit
d'affilée donnent une impression de modèle. Casse le rythme à un endroit
choisi, qui devient le moment fort.

Chaque section a **un seul travail**. Si tu ne peux pas le dire en une
phrase, scinde-la.

## 6. Responsive

- Conçois **mobile d'abord** pour le contenu, puis enrichis.
- Rupture selon le contenu (quand une ligne devient trop longue ou trop
  serrée), pas selon des appareils : `@container` pour les composants autonomes.
- Aucun défilement horizontal du corps de page. Les tableaux et le code
  défilent dans leur propre conteneur (`overflow-x: auto`).
- Cibles tactiles ≥ 44 × 44 px, espacées.
- Les images et visuels gardent leur sens en recadrage : `aspect-ratio`, `object-fit`.
- Teste à 360, 390, 768, 1024, 1440 px.
- Utilise des unités relatives (`rem`, `ch`, `%`, `fr`, `clamp()`), pas des `px` rigides pour les tailles de texte.

## 7. Composants : cohérence

- Un composant = un rôle, un nom, un comportement identique partout.
- États complets pour tout élément interactif : repos, survol, focus visible,
  actif, désactivé, chargement, erreur.
- Pas de rayon, d'ombre ou d'espacement inventé à la volée : tout vient des tokens.
- Les icônes viennent d'un jeu unique et cohérent (trait, épaisseur, taille), en SVG.
  Pas d'émojis en guise d'icônes.
