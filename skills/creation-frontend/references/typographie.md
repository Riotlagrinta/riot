# Typographie

La typographie porte la personnalité de la page. Choisis-la en premier, après
le sujet, avant la couleur.

## Sommaire
1. Choisir les familles
2. Associer deux familles
3. Échelle de tailles
4. Réglages fins
5. Chargement et repli
6. Le titre comme élément de design

---

## 1. Choisir les familles

- Une famille ou deux. Si deux, elles doivent être **nettement différentes**
  (par exemple : une grotesque large pour les titres, une humaniste sobre
  pour le texte), pas deux grotesques presque identiques.
- Ne choisis pas la police que tu choisirais pour n'importe quel projet.
  Évite par défaut Inter, Roboto, Arial et les polices système comme
  signature visuelle (elles restent valables pour une interface utilitaire
  où la neutralité est le but).
- Décide par **caractère**, depuis le sujet :

| Caractère cherché | Pistes de familles (Google Fonts) |
|---|---|
| Technique, précis | Space Grotesk, IBM Plex Sans, Sora, Manrope |
| Éditorial, posé | Newsreader, Source Serif 4, Literata, Libre Caslon |
| Géométrique, moderne | Outfit, Urbanist, Plus Jakarta Sans |
| Expressif, affiché | Anybody (largeur variable), Syne, Unbounded, Bricolage Grotesque |
| Chaleureux, humain | Hanken Grotesk, DM Sans, Figtree, Nunito Sans |
| Données, code | JetBrains Mono, IBM Plex Mono, Geist Mono |

Ces pistes sont un point de départ, pas une liste à épuiser : vérifie que la
police gère les accents français (é, è, ê, à, ç, œ, «  »), les chiffres
tabulaires si besoin, et le poids dont tu as réellement besoin.

## 2. Associer deux familles

- Contraste de structure : serif + sans-serif, ou large + étroite.
- Même hauteur d'x apparente, sinon le texte semble inégal.
- Un seul rôle par famille : l'une pour les titres et accents, l'autre pour
  le texte courant. Ne mélange pas les rôles.
- Les polices variables (axes de graisse et de largeur) donnent de la
  richesse avec un seul fichier : une même famille de 300 à 800 de graisse
  et plusieurs largeurs peut suffire pour toute une page.

## 3. Échelle de tailles

Choisis un rapport et tiens-le : 1,2 (sobre), 1,25 (équilibré), 1,333 (affirmé),
1,5 (très contrasté). Génère les tailles et nomme-les.

```css
:root {
  --t-1: clamp(0.82rem, 0.8rem + 0.1vw, 0.9rem);   /* légendes */
  --t0:  clamp(1rem, 0.96rem + 0.2vw, 1.125rem);   /* texte courant */
  --t1:  clamp(1.25rem, 1.15rem + 0.5vw, 1.5rem);
  --t2:  clamp(1.6rem, 1.4rem + 1vw, 2.2rem);
  --t3:  clamp(2.2rem, 1.7rem + 2.5vw, 3.6rem);
  --t4:  clamp(2.8rem, 1.8rem + 5vw, 6rem);        /* hero */
}
```

`clamp()` fait varier la taille avec la largeur sans points de rupture.

## 4. Réglages fins

- **Longueur de ligne** : 45 à 75 caractères (`max-width: 65ch`), moins de 80 au maximum.
- **Interligne** : texte courant 1,5 à 1,65 ; titres 0,95 à 1,15. Une police
  serif demande un peu plus d'interligne qu'une sans-serif.
- **Approche (letter-spacing)** : gros titres légèrement resserrés (`-0.01em` à `-0.03em`) ;
  petits textes en capitales (si vraiment utilisés) légèrement espacés (`0.04em`).
- **Graisses** : trois niveaux maximum par page (par exemple 400, 500, 700).
- **Chiffres** : `font-variant-numeric: tabular-nums` pour les tableaux et compteurs.
- **Césure et rendu** : `text-wrap: balance` pour les titres, `text-wrap: pretty`
  pour les paragraphes, `hyphens: auto` avec `lang="fr"`.
- **Typographie française** : espace insécable avant `: ; ! ?` et dans les
  guillemets « … » (utilise `&nbsp;` ou l'espace fine insécable `&#8239;`),
  apostrophe typographique ’, vraies capitales accentuées (É, À).
- Aligne le texte long à gauche. Le texte justifié demande une césure maîtrisée ;
  le texte centré reste réservé aux courtes phrases.

## 5. Chargement et repli

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=...&display=swap" rel="stylesheet">
```
```css
font-family: "Ma Police", ui-serif, Georgia, serif;   /* repli de même nature */
```
- `display=swap` pour afficher le texte tout de suite.
- Un repli de même nature (serif → serif, grotesque → `system-ui`).
- Charge uniquement les graisses utilisées.
- Si l'animation découpe du texte, attends `document.fonts.ready`.

## 6. Le titre comme élément de design

Quand un titre sert d'élément visuel, traite la typographie elle-même
comme le design : grande taille, largeur de caractère expressive, découpage
volontaire des lignes, contraste d'échelle avec le texte voisin. Un titre
bien composé peut remplacer une image.

Évite le réflexe d'accentuer un seul mot du titre (en italique, en couleur
ou en gras) : c'est l'un des signes les plus reconnaissables d'une page générée.
