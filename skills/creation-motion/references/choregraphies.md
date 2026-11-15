# Chorégraphies : recettes prêtes à adapter

Chaque recette donne l'intention, puis le code. Adapte les variables de
`principes-timing.md` (`--ease-sortie`, `--dur-long`…) à la personnalité du projet.

## Sommaire
1. Entrée de hero par masques de texte
2. Tracé SVG qui se dessine
3. Révélation d'un bloc par `clip-path`
4. Compteur de chiffres
5. Liste qui apparaît en cascade
6. Menu / panneau qui s'ouvre
7. Bouton : retour au survol et au clic
8. Loader
9. Transition de page
10. Défilement horizontal de texte (marquee)

---

## 1. Entrée de hero par masques de texte

Intention : le titre se révèle comme s'il sortait d'une fente. Plus précis et
plus distinctif qu'un fondu + glissement.

```html
<h1 class="titre">
  <span class="ligne"><span>Traverser</span></span>
  <span class="ligne"><span>sans bruit</span></span>
</h1>
```
```css
.ligne { display: block; overflow: hidden; padding-bottom: .08em; } /* le masque */
.ligne > span {
  display: block;
  transform: translateY(110%);
  animation: leve var(--dur-intro) var(--ease-sortie) forwards;
  animation-delay: calc(var(--base, 0.15s) + var(--i, 0) * 90ms);
}
.ligne:nth-child(2) > span { --i: 1; }
@keyframes leve { to { transform: none; } }
```
Piège : `overflow: hidden` coupe les jambages et les accents. Ajoute un
`padding` vertical sur le masque, et compense avec une marge négative si besoin.

## 2. Tracé SVG qui se dessine

```html
<svg viewBox="0 0 800 200">
  <path class="route" d="M20 150 C 220 20, 420 220, 780 60" pathLength="1"/>
</svg>
```
```css
.route { fill: none; stroke: currentColor; stroke-width: 2;
         stroke-dasharray: 1; stroke-dashoffset: 1;
         animation: trace 1.6s var(--ease-trajet) .2s forwards; }
@keyframes trace { to { stroke-dashoffset: 0; } }
```
Variante : un point qui suit le tracé avec `offset-path: path('…')` et
`offset-distance: 0% → 100%`.

## 3. Révélation d'un bloc par `clip-path`

```css
.revele { clip-path: inset(0 0 100% 0); animation: ouvre var(--dur-long) var(--ease-trajet) forwards; }
@keyframes ouvre { to { clip-path: inset(0 0 0 0); } }
```
Directions : `inset(0 100% 0 0)` (depuis la gauche), `inset(50% 50% 50% 50%)`
(depuis le centre). Évite de combiner avec un fondu : la forme révélée suffit.

## 4. Compteur de chiffres

```js
function compter(el, vers, duree = 1400) {
  const debut = performance.now();
  const facile = t => 1 - Math.pow(1 - t, 4);            // ease-out quart
  const fmt = new Intl.NumberFormat('fr-FR');
  function pas(maintenant) {
    const t = Math.min((maintenant - debut) / duree, 1);
    el.textContent = fmt.format(Math.round(vers * facile(t)));
    if (t < 1) requestAnimationFrame(pas);
  }
  requestAnimationFrame(pas);
}
```
- Ajoute `font-variant-numeric: tabular-nums` : les chiffres ne « dansent » pas.
- Réserve la largeur finale pour éviter les sauts de mise en page.
- Valeur finale écrite dans le HTML (`data-vers`) ; sans JS, elle reste lisible.

## 5. Liste qui apparaît en cascade

```css
.liste > li { opacity: 0; transform: translateY(14px);
  animation: monte var(--dur-moyen) var(--ease-sortie) forwards;
  animation-delay: calc(var(--i) * 60ms); }
@keyframes monte { to { opacity: 1; transform: none; } }
```
Plafonne : au-delà de 8 à 10 éléments, réduis l'écart ou anime par groupes.
À réserver à l'entrée d'une vue, jamais à chaque défilement.

## 6. Menu / panneau qui s'ouvre

```css
.panneau { display: grid; grid-template-rows: 0fr;
  transition: grid-template-rows var(--dur-moyen) var(--ease-trajet); }
.panneau > div { overflow: hidden; }
.panneau[data-ouvert="true"] { grid-template-rows: 1fr; }
```
Pour une modale : fond qui s'assombrit (`opacity`, 200 ms) + panneau qui
arrive (`translateY(16px) scale(.98)` → `none`, 300 ms). Fermeture : 60-70 % du temps.
Rends le focus au bouton d'origine et ferme avec `Échap`.

## 7. Bouton : retour au survol et au clic

```css
.bouton { transition: transform var(--dur-micro) var(--ease-sec),
                      background-color var(--dur-court) var(--ease-sec); }
.bouton:hover  { transform: translateY(-1px); }
.bouton:active { transform: translateY(0) scale(.98); }   /* l'appui se sent */
.bouton:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
```
Un retour de bouton est discret. Si l'utilisateur remarque l'animation,
elle est trop forte.

## 8. Loader

Choisis selon la durée d'attente :
- < 1 s : aucun loader, ou un simple changement d'état du bouton.
- 1 à 4 s : indicateur discret (barre fine, point qui respire), `linear` autorisé.
- > 4 s : indicateur de progression réel ou squelette de contenu (`skeleton`).

```css
.barre { height: 2px; background: currentColor; transform-origin: left;
  animation: charge 1.2s var(--ease-trajet) infinite; }
@keyframes charge { 0% { transform: scaleX(0); } 70% { transform: scaleX(1); opacity: 1; } 100% { transform: scaleX(1); opacity: 0; } }
```

## 9. Transition de page

Voir `techniques.md` § View Transitions. Principe : l'ancienne vue sort vite
(`--ease-depart`, ~200 ms), la nouvelle arrive un peu plus lentement
(`--ease-sortie`, ~380 ms), avec un léger chevauchement. Un élément partagé
(vignette → image de détail) peut « voyager » grâce à `view-transition-name`.

## 10. Marquee (défilement continu)

```css
.marquee { overflow: hidden; }
.marquee__piste { display: flex; width: max-content;
  animation: defile 30s linear infinite; }       /* ici, linear est correct */
@keyframes defile { to { transform: translateX(-50%); } }
@media (prefers-reduced-motion: reduce) { .marquee__piste { animation: none; } }
```
Duplique le contenu une fois dans la piste pour une boucle sans saut. Ne
l'utilise pas pour du texte important : il est difficile à lire en mouvement.
