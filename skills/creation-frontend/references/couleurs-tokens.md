# Couleurs et tokens

## Sommaire
1. Construire la palette
2. Contraste et accessibilité
3. Tokens CSS
4. Mode sombre
5. Ombres, bordures, rayons
6. À éviter

---

## 1. Construire la palette

Décris la palette en **4 à 6 couleurs nommées**, chacune avec son hex et son rôle.
Nomme-les par ce qu'elles évoquent, pas par leur teinte (`--ecume`, `--rouille-balise`).

Structure type :
- 1 couleur de **fond** (la scène)
- 1 couleur d'**encre** (le texte principal)
- 1 couleur **secondaire / atténuée** (texte secondaire, filets)
- 1 couleur **d'accent** (action, point d'attention) : une seule
- 0 à 2 couleurs de **soutien** (états, données)

Pars du sujet : matières, lumière, objets, lieux. Une marque de céramique
puise dans l'argile, l'émail et la cendre ; un outil de supervision, dans la
lumière d'un poste de contrôle. Une couleur dominante assumée, un accent
net, et le reste en retrait fonctionnent mieux qu'une palette « équilibrée »
où tout se vaut.

Le noir pur et le blanc pur sont rarement les meilleurs choix : teinte
légèrement tes neutres vers la couleur dominante (pas systématiquement vers
un ton chaud, qui est un réflexe courant).

## 2. Contraste et accessibilité

| Usage | Ratio minimum (WCAG AA) |
|---|---|
| Texte courant | 4,5:1 |
| Grand texte (≥ 24 px, ou ≥ 19 px en gras) | 3:1 |
| Éléments d'interface, icônes porteuses de sens | 3:1 |

- Calcule les ratios ; ne les devine pas. Fonction de luminance relative WCAG :

```python
def lum(hex):
    r, g, b = [int(hex.lstrip('#')[i:i+2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c/12.92 if c <= 0.03928 else ((c+0.055)/1.055) ** 2.4
    return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b)

def contraste(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
```

- L'information ne repose jamais sur la couleur seule (ajoute une icône, un texte, une forme).
- Teste l'accent sur le fond : un accent vif sur fond sombre n'a pas le même
  contraste que sur fond clair ; ajuste la luminosité par thème.

## 3. Tokens CSS

Toute valeur visuelle vit dans une variable. Deux niveaux : les valeurs
brutes, puis les rôles sémantiques qui s'y réfèrent.

```css
:root {
  /* Valeurs brutes (palette nommée) */
  --marine-900: #0f2a33;
  --ecume-50:   #e9efe6;
  --brume-400:  #8fb0ad;
  --balise-500: #e2673a;

  /* Rôles sémantiques : c'est ce que les composants utilisent */
  --fond:        var(--marine-900);
  --texte:       var(--ecume-50);
  --texte-doux:  var(--brume-400);
  --accent:      var(--balise-500);
  --sur-accent:  #1a0d07;          /* texte posé sur l'accent */
  --filet:       color-mix(in srgb, var(--texte) 18%, transparent);

  /* Espacements (base 4 px) */
  --e-1: .25rem; --e-2: .5rem; --e-3: .75rem; --e-4: 1rem;
  --e-6: 1.5rem; --e-8: 2rem;  --e-12: 3rem; --e-16: 4rem; --e-24: 6rem;

  /* Rayons : donne-leur une logique, pas un seul rayon partout */
  --r-petit: 2px; --r-moyen: 8px; --r-grand: 20px;

  /* Mouvement : voir creation-motion */
  --ease-sortie: cubic-bezier(0.16, 1, 0.3, 1);
  --dur-court: 220ms;
}
```

Les composants ne contiennent jamais `#e2673a` : ils contiennent `var(--accent)`.
Changer de thème, c'est redéfinir quelques variables.

## 4. Mode sombre

Ne te contente pas d'inverser. Redéfinis les rôles :

```css
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="clair"]) {
    --fond: #0f2a33; --texte: #e9efe6; --texte-doux: #8fb0ad;
  }
}
:root[data-theme="sombre"] { --fond: #0f2a33; --texte: #e9efe6; }
```
- Sur fond sombre, les surfaces « montent » en clarté (plus un élément est
  proche, plus il est clair) plutôt que de s'appuyer sur de grosses ombres.
- Réduis légèrement la saturation des accents vifs ; baisse l'éclat du blanc
  (`#e9efe6` plutôt que `#fff`) pour limiter l'éblouissement.
- Déclare `color-scheme: light dark;` pour que les contrôles natifs suivent.

## 5. Ombres, bordures, rayons

- Une hiérarchie : plus un élément est « au-dessus », plus son ombre est
  marquée, avec une direction de lumière cohérente. Pas la même ombre grise
  partout.
- Une bordure doit dire quelque chose (regroupement, état, séparation). Sinon,
  utilise l'espace.
- Le rayon exprime le caractère : 0-2 px (net, technique), 6-12 px (neutre),
  grand/pilule (amical). Choisis une logique et varie-la selon la hiérarchie
  (un bouton, une carte et une modale n'ont pas forcément le même rayon).

## 6. À éviter

- Dégradés décoratifs sans rapport avec le sujet (le « dégradé violet-bleu » générique).
- Plus d'un accent concurrent.
- Gris neutres purs sans aucune relation avec la palette.
- Couleurs vives sur toutes les surfaces : la couleur est un signal, elle doit rester rare.
