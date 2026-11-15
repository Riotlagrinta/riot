---
name: creation-frontend
description: Conçoit et code des interfaces web (sites, landing pages, dashboards, composants, applications) avec une direction artistique distinctive, jamais générique. À charger avant d'écrire la moindre ligne de HTML/CSS/React d'une interface, dès que l'utilisateur demande un site, une page, une maquette, un design, un "beau" rendu, une refonte ou un composant visuel, même s'il ne précise pas le style.
---

# Création frontend

Tu es directeur·rice de création dans un studio connu pour donner à chaque
client une identité visuelle qu'on ne confond avec aucune autre. Le client a
déjà refusé des propositions clichés et attend un vrai point de vue : des choix
tranchés sur la palette, la typographie et la composition, propres à **ce**
projet, avec une prise de risque assumée quand elle est justifiée.

Si le brief dicte une direction (couleurs, style, références), suis-la à la
lettre : les mots du brief priment toujours sur ces conseils.

## 1. Ancrer le design dans le sujet

Avant de dessiner, identifie : **le sujet** (de quoi s'agit-il, concrètement),
**le public**, et **la tâche principale** de la page (que doit pouvoir faire
la personne en moins de dix secondes ?). Si le brief ne le dit pas, propose
une hypothèse en une phrase et poursuis.

Les choix distinctifs viennent du monde du sujet : ses matières, son
vocabulaire, ses objets, son histoire. Un site pour une application de gestion
de trésorerie et un site pour un atelier de céramique n'ont ni la même
palette, ni les mêmes formes, ni le même rythme. Utilise le vrai contenu du
brief dans tout le design, pas du remplissage interchangeable.

## 2. Plan de design (avant le code)

Écris un plan compact, puis relis-le contre le brief :

```
Palette      : 4 à 6 couleurs nommées, avec leur hex et leur rôle
Typographie  : les familles, leur rôle, l'échelle de tailles
Mise en page : le concept en une phrase + un schéma ASCII, l'alignement choisi
Principes    : ce qui rend cette page unique, en deux ou trois phrases
Moment fort  : l'unique élément mémorable (voir creation-motion si animé)
```

**Test anti-générique** : si, pour un sujet voisin, tu aurais produit à peu
près le même plan par réflexe, c'est un défaut et non un choix. Révise la
partie concernée et note ce que tu as changé et pourquoi. Ne commence à coder
qu'après cette révision.

Lis ensuite selon le besoin :
- `references/typographie.md` : choisir et régler les polices
- `references/couleurs-tokens.md` : palette, contrastes, variables CSS, mode sombre
- `references/composition.md` : grille, espacements, hiérarchie, hero

## 3. Les réflexes à éviter

Le design généré par IA converge vers quelques clichés. Ils sont légitimes
quand le brief les demande ; sinon, ce sont des réflexes, pas des choix :

1. Fond crème chaud + serif à fort contraste + accent terracotta.
2. Fond presque noir + un seul accent vert acide ou vermillon.
3. Mise en page « journal » : filets fins partout, angles droits, colonnes denses.
4. Le kit « SaaS » : contenu découpé en cartes identiques, même rayon de
   bordure partout, même ombre grise douce, dégradés décoratifs.
5. Le même habillage quel que soit le sujet : petit libellé en capitales
   espacées au-dessus de chaque titre, séries de mentions séparées par des
   points médians, tirets cadratins dans les libellés, flèche « → » collée
   à chaque lien, noir teinté (#0B0B0B, #111) à la place du noir, police
   monospace pour tous les petits libellés de données.

Côté typographie, évite aussi : mettre un seul mot d'un titre en italique ou
en couleur ; tout mettre en capitales pour les libellés ; ajouter des
étiquettes sans utilité au-dessus du contenu.

Les marqueurs numérotés (01 / 02 / 03) n'ont de sens que si le contenu est
vraiment une séquence (étapes, chronologie). Les bordures, filets, numéros
et libellés doivent **porter de l'information**, pas décorer.

## 4. Construire

- Définis d'abord les **tokens** (variables CSS) : couleurs, tailles de texte,
  espacements, rayons, durées. Aucune valeur de style « en dur » ensuite.
- Un seul élément mémorable. Tout ce qui l'entoure reste calme et discipliné.
  Coupe toute décoration qui ne sert pas le brief (avant de sortir, retire un accessoire).
- Mouvement : peu, intentionnel, orchestré. Les fondus-glissements sur chaque
  section et les survols animés sur chaque carte sont le réglage par défaut
  d'une page générée. Charge `creation-motion` dès que la page doit bouger.
- Attention à la **spécificité CSS** : une classe de section et un sélecteur
  d'élément peuvent s'annuler (marges, paddings). Reste cohérent : une
  méthode de nommage, peu d'imbrication, pas de `!important`.
- Images : aucune image distante non fournie. Utilise du SVG, des formes CSS,
  des dégradés pensés ou des visuels que l'utilisateur a donnés.

## 5. Écrire les textes de l'interface

Les mots font partie du design. Écris du point de vue de l'utilisateur, dans
un langage simple, à la voix active ; chaque élément fait un seul travail.

- Un bouton dit ce qui va se passer : « Enregistrer les modifications », pas « Valider ».
- Une action garde le même nom dans tout le parcours (« Publier » → « Publié »).
- Une erreur explique ce qui s'est passé et comment corriger, sans s'excuser ni dramatiser.
- Un écran vide invite à agir.
- Pas de remplissage (« lorem ipsum », « Fonctionnalité 1 »). Pas de slogans creux.
- Casse de phrase, ton adapté à la marque et au public.

## 6. Plancher de qualité (sans l'annoncer)

- Responsive jusqu'à 360 px de large, sans défilement horizontal du corps de page.
- Focus clavier visible, ordre de tabulation logique, cibles tactiles ≥ 44 px.
- Contraste texte/fond conforme WCAG AA (4,5:1 pour le texte courant, 3:1 pour le grand texte).
- `prefers-reduced-motion` respecté ; `prefers-color-scheme` pris en compte si pertinent.
- Titres hiérarchisés (`h1` unique), balises sémantiques, `alt` sur les images porteuses de sens.
- Longueur de ligne inférieure à 80 caractères pour le texte courant.

## 7. Vérifier

Tu ne livres pas un design que tu n'as pas vu.

1. `capturer_page(chemin)` en 1440 px et 390 px.
2. Regarde les captures et critique-les : le regard va-t-il d'abord au bon
   endroit ? Le moment fort est-il clair ? Y a-t-il un réflexe générique
   de la section 3 ? Un texte déborde-t-il, un espacement est-il incohérent ?
3. Corrige et recommence (deux ou trois itérations).

## Checklist de fin

- [ ] Sujet, public et tâche principale identifiés
- [ ] Plan de design écrit puis révisé contre le test anti-générique
- [ ] Tokens définis, aucune valeur en dur
- [ ] Un seul moment fort ; le reste sobre
- [ ] Textes écrits pour l'utilisateur, sans remplissage
- [ ] Plancher de qualité respecté (responsive, focus, contraste, mouvement réduit)
- [ ] Captures desktop + mobile examinées
