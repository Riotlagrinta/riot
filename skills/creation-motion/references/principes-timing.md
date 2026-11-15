# Principes de timing et d'easing

## Sommaire
1. Durées de référence
2. Courbes d'easing
3. Personnalités de mouvement
4. Stagger (décalage)
5. Distances et amplitudes
6. Hiérarchie et ordre d'apparition
7. Accessibilité

---

## 1. Durées de référence

| Type de mouvement | Durée |
|---|---|
| Retour au survol / focus / clic (feedback) | 100 – 180 ms |
| Petit changement d'état (toggle, onglet, tooltip) | 150 – 250 ms |
| Ouverture d'un panneau, menu, modale | 220 – 350 ms |
| Transition entre deux vues | 300 – 500 ms |
| Entrée d'un élément dans une page | 450 – 800 ms |
| Séquence d'introduction complète (hero) | 1,2 – 2 s au total |

Règles :
- **La sortie est plus rapide que l'entrée** (environ 60 à 70 % de la durée).
  Ce qui part ne doit pas retenir l'utilisateur.
- Plus la distance parcourue est grande, plus la durée augmente, mais pas
  de façon linéaire : un doublement de distance ≈ +30 % de durée.
- Sur mobile, réduis les durées d'environ 15 à 20 %.
- Au-delà de 400 ms pour une réponse à une action, l'interface paraît lente.

## 2. Courbes d'easing

Définis-les une fois comme variables CSS :

```css
:root {
  /* Arrivée : démarre vite, freine doucement. C'est ton easing par défaut. */
  --ease-sortie:   cubic-bezier(0.16, 1, 0.3, 1);    /* expo out, très doux */
  --ease-entree:   cubic-bezier(0.22, 1, 0.36, 1);   /* quint out */

  /* Départ : accélère, quitte l'écran. */
  --ease-depart:   cubic-bezier(0.7, 0, 0.84, 0);    /* expo in */

  /* Déplacement d'un point A à un point B visible à l'écran. */
  --ease-trajet:   cubic-bezier(0.65, 0, 0.35, 1);   /* in-out cubic */

  /* Mouvement net, mécanique, sans douceur excessive. */
  --ease-sec:      cubic-bezier(0.4, 0, 0.2, 1);

  /* Léger dépassement, personnalité joueuse. À doser. */
  --ease-elan:     cubic-bezier(0.34, 1.4, 0.64, 1);

  --dur-micro:   140ms;
  --dur-court:   220ms;
  --dur-moyen:   380ms;
  --dur-long:    650ms;
  --dur-intro:   900ms;
}
```

Règle simple :
- un élément **apparaît** → ease-out (`--ease-sortie`)
- un élément **disparaît** → ease-in (`--ease-depart`)
- un élément **se déplace** d'un endroit visible à un autre → ease-in-out (`--ease-trajet`)
- `linear` seulement pour : rotation continue, défilement continu (marquee), barre de progression.

Pour GSAP, équivalents : `expo.out`, `power4.out`, `expo.in`, `power3.inOut`,
ou `CustomEase` pour une courbe sur mesure. Pour des ressorts, préfère la
bibliothèque Motion (`type: "spring"`) avec `stiffness` 300-500 et
`damping` 30-40 : réactif, sans rebond mou.

## 3. Personnalités de mouvement

Choisis **une** personnalité par projet et applique-la partout.

| Personnalité | Easing | Durées | Caractère |
|---|---|---|---|
| Précis / technique | `--ease-sec`, `expo.out` | courtes | net, rapide, aucune fioriture |
| Éditorial / luxe | `--ease-sortie` | longues, 700-1000 ms | lent, posé, beaucoup d'air |
| Organique / doux | `--ease-trajet` | moyennes | fluide, arrondi, léger flottement |
| Joueur / vif | `--ease-elan`, ressorts | courtes à moyennes | énergique, légers dépassements |
| Cinématique | `power4.inOut` | longues | grandes masses, révélations par masque |

## 4. Stagger (décalage entre éléments)

- Écart entre éléments voisins : **40 à 90 ms**.
- Plafonne le décalage total à environ **600 ms** : avec beaucoup d'éléments,
  réduis l'écart (`total / nombre`) plutôt que de laisser la séquence traîner.
- Le décalage suit l'ordre de lecture (haut→bas, gauche→droite) ou un ordre
  de sens (du centre vers l'extérieur, de l'élément le plus important vers
  le moins important).
- N'utilise pas de stagger sur plus d'une dizaine d'éléments : regroupe-les.

En CSS, passe l'index en variable :

```css
.item { animation-delay: calc(var(--i) * 70ms); }
```
```html
<li class="item" style="--i:0">…</li>
<li class="item" style="--i:1">…</li>
```

## 5. Distances et amplitudes

- Déplacement d'entrée : **12 à 40 px** suffit. Plus, ça devient théâtral.
  Exception : une révélation par masque, où le texte monte de 100 % de sa hauteur.
- Échelle : de `0.94` à `1` pour une entrée, `1.02` à `1.04` maximum
  pour un survol. Jamais de zoom à 1.2 sur un bouton.
- Rotation : quelques degrés (2 à 6°). Au-delà, c'est un effet, pas un détail.
- Opacité : démarre de 0, mais ne t'appuie pas sur le fondu seul : combine-le
  avec un léger déplacement ou un masque pour donner de la direction.

## 6. Hiérarchie et ordre d'apparition

L'ordre raconte l'importance. Séquence type d'une intro de page :

1. Le fond / la structure (0 ms) : la scène se pose
2. Le titre principal (≈ 100-200 ms) : le sujet
3. Le sous-titre ou l'élément de preuve (≈ 350 ms)
4. L'appel à l'action (≈ 550 ms)
5. Les éléments secondaires, navigation, décor (≈ 700 ms et plus)

La navigation et ce dont l'utilisateur a besoin pour agir ne doivent pas
attendre la fin de la séquence : elle reste utilisable dès les premiers
instants.

## 7. Accessibilité

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Cette règle de sécurité est un minimum. Mieux : prévois un repli pensé
(fondu simple au lieu de déplacement, pas de parallaxe, pas de boucle).

- Rien ne clignote plus de 3 fois par seconde.
- Un contenu important ne disparaît pas tout seul avant d'avoir pu être lu.
- Les animations déclenchées au survol ont un équivalent au focus clavier.
