# Techniques et choix d'outil

## Sommaire
1. CSS
2. Web Animations API
3. GSAP
4. Motion (React)
5. View Transitions API
6. Animations liées au scroll
7. SVG
8. Lottie / Rive / Remotion
9. Performance et pièges

---

## 1. CSS : le choix par défaut

Idéal pour : états (hover, focus, ouvert/fermé), entrées simples, boucles légères.

```css
.carte {
  transition: transform var(--dur-court) var(--ease-sortie),
              box-shadow var(--dur-court) var(--ease-sortie);
}
.carte:hover { transform: translateY(-3px); }

@keyframes monte {
  from { transform: translateY(24px); opacity: 0; }
  to   { transform: none;             opacity: 1; }
}
.titre { animation: monte var(--dur-long) var(--ease-sortie) both; }
```

- `animation-fill-mode: both` (ou `backwards`) : l'élément reste dans l'état
  de départ pendant son `animation-delay`. Sans cela : flash de contenu.
- Un élément qui doit réagir à un clic : bascule une classe ou un attribut
  `data-etat`, et anime en CSS plutôt qu'en JavaScript.
- Pour animer `height: auto`, utilise `grid-template-rows: 0fr → 1fr`
  avec `overflow: hidden` sur l'enfant : animable sans mesurer la hauteur.

## 2. Web Animations API (sans dépendance)

```js
const anim = element.animate(
  [{ transform: 'translateY(24px)', opacity: 0 },
   { transform: 'none',             opacity: 1 }],
  { duration: 650, easing: 'cubic-bezier(0.16,1,0.3,1)', fill: 'both', delay: 100 }
);
anim.finished.then(() => { /* suite */ });
```

Contrôle : `anim.pause()`, `anim.reverse()`, `anim.currentTime = 300`.
Pratique pour enchaîner et pour capturer des frames (voir `capturer_frames`).

## 3. GSAP : timelines et scroll

Idéal pour : séquences à plusieurs étapes, synchronisation fine, scroll, SVG.

CDN (versions épinglées) :
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js"></script>
```

Timeline de base :

```js
gsap.registerPlugin(ScrollTrigger);

const tl = gsap.timeline({ defaults: { ease: 'expo.out', duration: 0.9 } });
tl.from('.hero__titre', { yPercent: 110, stagger: 0.08 })
  .from('.hero__sous',  { opacity: 0, y: 16 }, '-=0.5')   // chevauche l'étape précédente
  .from('.hero__cta',   { opacity: 0, y: 12 }, '-=0.4');
```

Points clés :
- Position en 3ᵉ argument : `'-=0.4'` (avant la fin), `'<'` (même début que le précédent), `'label'`.
- Préfère `yPercent`/`xPercent` aux pixels quand l'élément a une taille variable.
- `gsap.set()` pour l'état initial ; mais le **vrai** état caché doit venir du
  CSS (sinon flash). Ajoute une classe `js` sur `<html>` et cache avec `.js .x { opacity:0 }`.
- Respecte la réduction de mouvement avec `gsap.matchMedia()` :

```js
const mm = gsap.matchMedia();
mm.add('(prefers-reduced-motion: no-preference)', () => {
  // animations complètes
});
mm.add('(prefers-reduced-motion: reduce)', () => {
  gsap.set('.x', { opacity: 1, y: 0 });   // contenu visible, sans mouvement
});
```

ScrollTrigger :
```js
gsap.from('.bloc', {
  opacity: 0, y: 32, duration: 0.8, ease: 'expo.out',
  scrollTrigger: { trigger: '.bloc', start: 'top 80%', once: true }
});

// liée au défilement (scrub)
gsap.to('.panneau', {
  clipPath: 'inset(0% 0% 0% 0%)', ease: 'none',
  scrollTrigger: { trigger: '.section', start: 'top bottom', end: 'top 20%', scrub: true }
});
```
- `scrub: true` : l'animation suit le scroll, avec `ease: 'none'`
  (l'easing vient du geste de l'utilisateur).
- `once: true` pour les révélations : ça ne rejoue pas à chaque passage.
- Appelle `ScrollTrigger.refresh()` après le chargement des images/polices.

## 4. Motion (React)

```jsx
import { motion } from "motion/react";

<motion.h1
  initial={{ y: 24, opacity: 0 }}
  animate={{ y: 0, opacity: 1 }}
  transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
/>
```
- Animations de layout : prop `layout` (réarrangement fluide d'une liste).
- Éléments qui quittent le DOM : `<AnimatePresence>` + prop `exit`.
- Stagger : `variants` parent/enfant avec `staggerChildren`.
- Gestes : `whileHover`, `whileTap`, `drag`.
- Réduction de mouvement : `useReducedMotion()` ou `<MotionConfig reducedMotion="user">`.

## 5. View Transitions API (transitions de page)

```js
function allerVers(maj) {
  if (!document.startViewTransition) return maj();  // repli
  document.startViewTransition(maj);
}
```
```css
::view-transition-old(root) { animation: sortie var(--dur-moyen) var(--ease-depart) both; }
::view-transition-new(root) { animation: entree var(--dur-moyen) var(--ease-sortie) both; }
.vignette { view-transition-name: produit-12; }  /* morphing entre deux vues */
```
Toujours prévoir un repli (le support n'est pas universel).

## 6. Animations liées au scroll

- Révélation simple et robuste : `IntersectionObserver` qui ajoute une classe
  `.visible` ; l'animation reste en CSS.
- Scroll-driven CSS (`animation-timeline: view()` / `scroll()`) existe mais le
  support est partiel : n'en fais pas la seule voie, prévois un repli.
- Défilement « fluide » personnalisé (Lenis, etc.) : seulement si le projet
  le justifie ; ça peut nuire à l'accessibilité et au ressenti natif.

## 7. SVG

Tracé qui se dessine :
```css
.trait {
  stroke-dasharray: var(--long);       /* mesure : path.getTotalLength() */
  stroke-dashoffset: var(--long);
  animation: trace 1.4s var(--ease-trajet) forwards;
}
@keyframes trace { to { stroke-dashoffset: 0; } }
```
Alternative sans mesure : `pathLength="1"` sur le `<path>`, puis
`stroke-dasharray: 1; stroke-dashoffset: 1;` → `0`.

Morphing de formes : GSAP (MorphSVG) ou interpolation entre chemins ayant le
même nombre de points. Pour des icônes animées complexes, passe par Lottie.

## 8. Lottie / Rive / Remotion

- **Lottie** (`lottie-web` ou `@lottiefiles/dotlottie-web`) : animations vectorielles
  exportées depuis After Effects. Léger, mais tu ne les « codes » pas : tu les intègres.
- **Rive** : animations interactives à états (machines d'état). Très bon pour les
  personnages et les icônes réactives.
- **Remotion** : vidéos en React. Une composition = un composant dont l'état
  dépend de `useCurrentFrame()`. Rendu en mp4 via CLI. Utile pour les contenus
  réseaux sociaux, intros, démos produit. Calcule tout à partir de `frame`
  et de `fps`, n'utilise jamais de `setTimeout` ni de transitions CSS.

```jsx
import { useCurrentFrame, interpolate, Easing } from "remotion";

export const Titre = () => {
  const frame = useCurrentFrame();
  const y = interpolate(frame, [0, 24], [60, 0], {
    easing: Easing.out(Easing.exp), extrapolateRight: "clamp",
  });
  const o = interpolate(frame, [0, 16], [0, 1], { extrapolateRight: "clamp" });
  return <h1 style={{ transform: `translateY(${y}px)`, opacity: o }}>Titre</h1>;
};
```

## 9. Performance et pièges

- Seuls `transform` et `opacity` sont animés sur le compositeur (GPU) sans
  recalcul de mise en page. `clip-path` et `filter` : corrects, mais teste-les.
- `filter: blur()` animé est coûteux sur grandes surfaces : limite le rayon
  et la zone.
- Pas de `transition: all`. Liste les propriétés.
- `will-change: transform` uniquement sur ce qui s'anime, pour une courte durée.
- Les polices web qui chargent tard décalent le texte : attends
  `document.fonts.ready` avant de mesurer ou de découper du texte.
- Découpage de texte par lignes : refais-le au redimensionnement ou
  utilise des masques par bloc (ligne unique) pour éviter les coupes erronées.
- Un élément `position: fixed` à l'intérieur d'un parent avec `transform`
  se comporte comme `absolute` : piège classique.
- Teste toujours sur petit écran et avec réduction de mouvement activée.
