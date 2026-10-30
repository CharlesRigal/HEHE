# HEHE

Jeu de mage multijoueur où les sorts sont **dessinés à la main** et résolus par un système émergent continu. Les sorts sont des **outils** pour résoudre des énigmes et interagir avec le monde, pas des boutons à dégât.

[plan.md](plan.md) est un brouillon de travail, non normatif. Ce README fait foi.

---

## Principe fondamental

```
dessin → primitives → AST → propriétés continues → effets émergents
```

**Jamais** `pattern → effet`. Pas de table de recettes, pas de lookup `(élément, forme) → sort_id`.

---

## Règle d'orthographe

Inspiré à 100 % de *L'Atelier des sorciers* ([fonctionnement des sorts](https://latelier-des-sorciers.fandom.com/fr/wiki/Sorts:_Fonctionnement)), adapté pour rester crédible et implémentable en jeu vidéo.

Un sort est un **pentacle** fait de trois choses :

- l'**emblème**, au centre, fixe l'élément du sort ;
- les **flèches**, autour de l'emblème, fixent la forme, la taille et l'orientation du sort ;
- le **cercle**, autour du tout, achève et active le sort.

### Principes

1. **Le dessin se mesure, il ne se lit pas.** Chaque trait donne des grandeurs continues (longueur, angle, rayon, position). Ces grandeurs deviennent des grandeurs physiques (force, rayon, durée, intensité). Aucune règle ne dit « ce dessin = ce sort ».
2. **Exigence de tracé.** Le joueur doit bien dessiner. Un trait raté n'est jamais deviné ni corrigé : il est mort (voir *Qualité du tracé*).
3. **Tout s'additionne.** Les flèches sont des vecteurs. Deux flèches opposées s'annulent, deux flèches en biais donnent une diagonale. Les comportements viennent de la somme, pas d'une liste de cas.
4. **Rien n'est gratuit.** L'encre consommée borne l'énergie du sort. Grand dessin = sort ample = beaucoup d'encre.
5. **Un sort n'agit que sur son élément.** Un sort ne pousse, ne tire et ne tient jamais un objet directement. Il crée, déplace, compresse ou maintient **son élément**. C'est l'élément qui agit ensuite sur le monde : un sort de vent qui aspire l'air entraîne les objets légers, un sort d'eau qui pousse l'eau emporte ce qui flotte.

### Le cercle

- **C1 — Fermeture.** Tant que le cercle n'est pas fermé, le pentacle est inerte. Fermer le cercle lance le sort. Le cercle peut compter plusieurs traits : n'importe quelle boucle fermée compte. Le joueur peut tracer un cercle presque fermé pour fixer la dimension, dessiner l'intérieur, puis le fermer d'un dernier trait.
- **C2 — Bloc autonome.** Tout ce qui est dans le cercle appartient au sort. Ce qui est dehors n'existe pas pour lui. Un trait qui traverse le cercle le brise.
- **C3 — Taille.** La surface du cercle donne la **puissance** du sort. Son rayon donne le rayon de la zone d'effet.
- **C4 — Rondeur.** Plus le cercle est rond, moins le sort perd d'énergie.
- **C5 — Rupture.** Couper ou effacer le cercle d'un sort actif l'arrête net.
- **C7 — Relâchement.** Quand le sort s'arrête (rupture ou fin de durée), l'élément accumulé est **relâché** dans le monde : l'eau compressée éclate et mouille, la chaleur concentrée se diffuse. Ces effets secondaires sont voulus.
- **C6 — Voisinage.** Deux cercles séparés sont deux sorts indépendants. Deux cercles qui se chevauchent sont tous deux brisés.

### L'emblème

- **E1 — Un seul, au centre.** L'emblème fixe l'élément du sort. L'emblème est le symbole le plus proche du centre du cercle. Les autres emblèmes éventuels sont ignorés (v1).
- **E2 — Taille sans effet.** La taille de l'emblème ne compte pas. La puissance vient de la surface du cercle (C3). L'**intensité** monte avec les signes de convergence. C'est elle qui est comparée aux seuils de réaction du monde (une torche s'allume à partir d'une certaine intensité de feu).
- **E3 — Sans emblème, rien.** Un cercle sans emblème valide ne produit aucun effet. Il n'existe pas de sort de force pure.
- **E4 — Source.** L'emblème **crée** son élément au centre, en quantité proportionnelle à la taille du cercle. Il n'y a pas de mode « désignation » : la traction attire en plus l'élément déjà présent dans le monde. Avec de l'eau autour, une traction donne une grosse bulle ; sans eau, il ne reste que l'eau créée.
- **E5 — Coût.** Le seul coût est l'encre : chaque trait compte (S3). Les énergies (chaleur, froid, charge, lumière) se créent librement, même si le monde n'en contient pas. Le vent est partout.

| Emblème | Nature | Grandeur physique portée | Clé d'affinité |
|---|---|---|---|
| Feu | énergie | chaleur (+) | `fire` |
| Glace | énergie | chaleur (−) : codée comme température négative, même grandeur que le feu | `ice` |
| Eau | matière | matière fluide | `water` |
| Vent | matière (partout) | poussée sur les corps légers | `wind` |
| Terre | matière | masse, solidité | `earth` |
| Foudre | énergie | charge | `lightning` |
| Lumière | énergie | signal, visibilité | `light` |

Le glyphe de chaque emblème reste à dessiner. Un emblème peut compter plusieurs traits, mais il doit être **d'un seul tenant** : tous ses traits se touchent (voir *Lecture du dessin*).

### Les flèches (signes)

Les flèches se placent entre l'emblème et le cercle, sans toucher ni l'un ni l'autre, ni se toucher entre elles. Chaque type a son propre glyphe (triangle, T, flèche ouverte…), inspiré des [signes de L'Atelier des sorciers](https://witch-hat-atelier.fandom.com/wiki/Signs_Explained).

- **F0 — Base et tête.** Tout signe a une **base** et une **tête** distinguables (comme `|--▷`). L'axe base → tête donne son orientation, et un signe retourné inverse son effet. Un signe dont on ne peut pas distinguer la base de la tête est mort : son score à l'angle θ et son score à θ + 180° sont trop proches (voir L6).

Mesures communes à toutes les flèches :

- **F1 — Repère du cercle.** Tout se mesure par rapport au **centre du cercle** : distance du signe au centre, angle de sa position, et angle de son axe par rapport au rayon qui passe par lui. Sa composante **radiale** dit s'il va vers le centre ou vers l'extérieur, sa composante **tangentielle** dit s'il tourne. La zone d'effet est centrée sur le centre du cercle, et le haut de la page reste le haut du monde. Le monde est en **2D** : il n'y a pas de hauteur simulée.
- **F2 — Longueur.** La longueur d'un signe ne donne pas de force : la force vient de la puissance du cercle (C3). La taille d'un signe donne sa **couverture**, c'est-à-dire la largeur de la zone qu'il influence.
- **F3 — Somme.** Les flèches de même type s'additionnent en vecteurs. Vers l'extérieur tout autour : l'effet émane. Vers le centre : l'effet se ramasse. En biais : l'effet tourne en spirale.
- **F4 — Symétrie.** Des flèches régulièrement réparties donnent un sort stable. Un déséquilibre fait dériver le sort du côté le plus chargé. Ce n'est pas une erreur, c'est un outil.
- **F5 — Dehors agit dehors.** Il n'y a pas d'anneaux explicites. Chaque signe agit dans la bande de la zone qui correspond à sa distance au centre : un signe à 80 % du rayon du cercle agit à 80 % du rayon de la zone. La largeur de la bande est l'étendue radiale du signe. Quand des bandes se recouvrent, leurs signes **fusionnent** : les signes de même type s'additionnent en vecteurs (F3), les signes de types différents agissent ensemble (une traction et une convergence au même rayon attirent et compressent à la fois).
- **F6 — Carte de champ.** Le pentacle est une carte de champ posée sur la zone d'effet. Chaque signe en est un échantillon, et entre deux signes le champ s'**interpole** : l'influence d'un signe décroît avec la distance, sur une largeur proportionnelle à sa taille. Il y a trois familles :
  - **vectoriels** (Direction, Traction) : un sens d'écoulement local ;
  - **scalaires** (Convergence/Dispersion, Suspension) : une valeur locale. Convergence et dispersion forment **une seule échelle signée** : positif = compresser, négatif = étaler ;
  - **locaux dans le temps** (Répétition) : une durée pour la bande où ils sont placés.

  Dans une même cellule, les vecteurs s'additionnent et les scalaires de même échelle s'additionnent. F3, F4 et F5 ne sont donc pas des règles à coder : ce sont des propriétés du champ.

Types de flèches (v1) :

| Flèche | Glyphe | Ce qu'elle règle | Grandeur physique |
|---|---|---|---|
| Direction | à dessiner | où va l'élément | direction du vecteur |
| Traction | flèche ouverte, triangle superposé à la hampe (les traits se croisent) | attire l'élément vers sa tête ; retournée, elle le repousse | flux de l'élément |
| Convergence | triangle | resserre et compresse l'élément vers sa tête | zone plus étroite, intensité plus haute |
| Dispersion | triangle retourné (convergence retournée, F0) | étale l'élément | zone plus large, intensité plus faible |
| Suspension | flèche ouverte avec base | tient l'élément du sort en place sur le dessin : il ne s'écoule plus | maintien contre l'amortissement |
| Colonne | T | fait jaillir l'élément en jet, dans l'axe du signe | à préciser |
| Répétition | à dessiner | fait durer la bande où il est placé (locale, F5) | durée locale (un signe de plus = plus longtemps) |

Les glyphes restants sont à dessiner. Chaque type doit se distinguer par sa tête et sa base, pas par sa hampe.

Une flèche peut compter plusieurs traits, à condition d'être d'un seul tenant. Chaque glyphe doit avoir **un seul axe** : pas de symétrie qui le rendrait identique une fois tourné (triangle isocèle plutôt qu'équilatéral, T à barre plus courte qu'un des bras, etc.).

### Le support

- **S1 — Papier (défaut).** Le pentacle agit autour du mage, à l'endroit où il se tient au moment de fermer le cercle.
- **S2 — Surface du monde.** Dessiné sur un objet ou sur le sol, le pentacle y reste accroché et suit le support. Le sort agit toujours sur son élément, depuis ce support (principe 5).
- **S3 — Encre.** Chaque trait consomme de l'encre selon sa longueur. Plus d'encre, plus de traits. Un trait mort consomme quand même.

### Lecture du dessin

Le dessin est **mesuré**, pas reconnu. La reconnaissance par modèle est limitée au strict nécessaire : l'identité de l'emblème et le type de chaque signe. Tout le reste (position, orientation, taille, cercle) est mesuré.

- **L1 — Lecture à la fermeture.** Rien n'est analysé tant que le cercle n'est pas fermé (C1). Pas de retour en temps réel pendant le tracé.
- **L2 — Contact = rendu.** Deux traits se touchent si et seulement s'ils se touchent à l'écran. Le seuil se calcule à partir de l'épaisseur de trait rendue : contact quand la distance entre les lignes centrales est ≤ l'épaisseur. Il n'y a pas de zone ambiguë.
- **L3 — Symbole = traits connectés.** Des traits qui se touchent forment un seul symbole. Des traits séparés forment des symboles distincts.
- **L4 — Aucune superposition.** Deux symboles ne se touchent jamais. S'ils se touchent, ils fusionnent en un seul symbole incohérent, qui meurt.
- **L5 — Rôle par position.** La boucle fermée englobante est le cercle, le symbole le plus proche du centre est l'emblème, les autres symboles sont des flèches. La forme ne décide jamais du rôle.
- **L6 — Outil par rôle.**

| Rôle | Outil | Sortie |
|---|---|---|
| Cercle | mesure géométrique | rayon, rondeur, fermeture |
| Signe | reconnaisseur $P avec balayage de rotation ; chaque template annote sa tête et sa base | type, orientation (meilleur angle), sens (tête annotée), score |
| Signe | mesure géométrique dans le repère du cercle (F1) | distance au centre, angle, longueur projetée sur l'axe, étendue radiale |
| Emblème | reconnaisseur $P (multi-trait, insensible à l'ordre des traits), avec rejet sous le seuil | élément + score |

$P n'est pas invariant en rotation. Chaque template de signe est donc testé à plusieurs angles, et le meilleur angle donne l'orientation du signe. Le template stocke la position de sa tête et de sa base. Une fois tournées de ce meilleur angle, elles donnent le sens.

- **L7 — Lecture locale.** La lecture se fait sur le client. Le client envoie les paramètres au serveur. Aucune protection contre la triche n'est prévue.

### Qualité du tracé

Chaque symbole reçoit une note de qualité entre 0 et 1. Sous le seuil, le symbole est **mort** : il reste visible mais ne compte pas. Au-dessus, la note multiplie le rendement du sort.

La note d'un symbole est le **minimum** des notes de ses critères et de ses traits. Un seul défaut suffit : un dessin trop brouillon échoue.

| Symbole | Critère mesuré | Seuil de départ (à régler) |
|---|---|---|
| Cercle | boucle fermée (contact au sens L2) | obligatoire |
| Cercle | variation du rayon | ≤ 8 % du rayon moyen |
| Flèche | score $P au meilleur angle | à régler, très haut |
| Flèche | base et tête distinguables (F0) : écart entre le score à θ et le score à θ + 180° | à régler |
| Emblème | score $P (seul critère) | à régler, haut |

Un cercle mort ne lance rien. Un emblème mort rend le sort inerte (E3). Une flèche morte est simplement absente de la somme.

### Du dessin à la physique

| Mesure du dessin | Grandeur |
|---|---|
| Emblème | élément du sort |
| Surface du cercle | puissance |
| Rayon du cercle | rayon de zone |
| Somme des flèches de traction | flux de l'élément vers le sort (ou depuis, si retournées) |
| Flèches de convergence | compression de l'élément, intensité |
| Flèches de suspension | maintien de l'élément sur place |
| Flèches de répétition | durée de leur bande |
| Flèches vers le centre / en biais | flux radial / en spirale |
| Support = objet | point d'ancrage |
| Rupture du cercle | arrêt du sort |

Côté moteur, les forces sur les objets (`GameInstance.apply_force`, `apply_force_in_radius`, `EntityBody.apply_force`) doivent venir de l'élément simulé, jamais directement du sort (principe 5). Le branchement actuel est à revoir.

### Le monde

Le monde est une grille de cellules en 2D. Chaque cellule contient quelques grandeurs seulement :

| Grandeur | Valeur | Emblème |
|---|---|---|
| eau | ≥ 0 | Eau |
| terre | ≥ 0 | Terre |
| air (courant) | vecteur | Vent |
| température | signée | Feu (+), Glace (−) |
| charge | ≥ 0 | Foudre |
| lumière | ≥ 0 | Lumière |

- **M0 — Garde-fou.** Toute règle du monde s'écrit comme un seuil sur une ou plusieurs grandeurs de cellule. Une règle qui nomme des éléments ou des entités (« A + B → C », « la torche s'allume au feu ») est refusée.
- **M1 — États par seuils.** L'état de la matière dépend de la température : eau froide → glace, eau chaude → vapeur, terre très chaude → lave. Il n'y a pas de table de réactions.
- **M2 — Règles croisées.** Les règles qui lient deux grandeurs (par exemple la charge conduite par l'eau) viendront plus tard.

### Exemples

- **Bulle d'eau suspendue.** Emblème de l'eau, trois flèches de traction, trois de convergence, trois de suspension. Chaque type forme un triangle équilatéral, dans l'ordre indiqué. Le dessin est symétrique. Effet : le sort attire l'eau autour de lui, la compresse et la maintient de manière stable sur le dessin. À la fin du sort, la bulle éclate (C7).
- **Pousser une balle vers une fosse.** Emblème du vent, flèches de traction retournées vers la fosse : le vent souffle et emporte la balle. Balle trop lourde : cercle plus grand, donc plus de puissance, donc plus d'encre.
- **Allumer trois torches alignées.** Emblème du feu, une flèche de direction vers les torches, une flèche de convergence pour allonger la portée, cercle.

### Hors v1

- Cercles imbriqués (un sort qui en nourrit un autre).
- Lien tracé entre deux cercles (binding à distance).
- Flèches de taille, de collecte, de pluie.

## Exemples de puzzles visés

Le joueur doit **penser** comment composer un sort pour résoudre un défi, pas mémoriser des recettes.

### Traversée
- Traverser un grand trou : pont de glace, plateforme lévitée, courant d'air porteur
- Geler une rivière pour marcher dessus
- Créer une bulle d'eau pour sauter plus haut

### Combat / environnement
- Vaincre un ennemi résistant au feu → passer à la glace ou à la foudre
- Mur de glace pour bloquer un projectile ennemi
- Miroir magique pour renvoyer un projectile
- Retirer un obstacle avec l'élément opposé (glace sur feu, eau sur rocher chaud)

### Mécanismes
- Allumer 3 torches d'un seul sort dirigé
- Mettre une balle dans une fosse (poussée horizontale)
- Rendre un objet léger / lourd pour activer des plaques de pression
- Batterie magique : tonnerre continu pour alimenter un mécanisme
- Transférer l'énergie d'un feu existant vers un mécanisme distant
- Lien énergétique entre deux cristaux (binding à distance)

### Plateforme / navigation
- Lever une plateforme pour en atteindre une autre
- Téléportation courte (vecteur auto-appliqué)
- Courant d'air pour déplacer un objet léger

### Interaction élémentaire
- Refroidir de la lave pour la transformer en roche
- Vaporiser de l'eau en lançant du feu dessus pour quelle se trensforme en vapeur
- Électriser de l'eau pour créer une chaîne de choc

---

## À ajouter plus tard

### Grimoire
Un livre dans lequel le joueur enregistre un sort réussi et peut le rejouer plus tard. Complément au dessin écran pour les joueurs sans mémorisation ni redraw.

---

## Protocole réseau

### Connexion
```json
server → {"t": "welcome", "your_id": <int>}
```

### Keepalive
```json
client → {"t": "ping"}
server → {"t": "pong"}
```

### Cast de sort
```json
client → {"t": "s", "R": 120.0, "q": 0.93, "e": "water", "eq": 0.88, "ink": 1450.0,
          "signs": [{"k": "traction", "r": 0.8, "a": 1.57, "o": -1.57, "s": 0.25, "q": 0.9}]}
```

Le message porte la lecture du pentacle (L7) :
- `R` : rayon du cercle ;
- `q` : qualité du cercle ;
- `e`, `eq` : élément de l'emblème et son score ;
- `ink` : encre consommée ;
- `signs` : pour chaque signe vivant, son type `k`, sa distance au centre `r` (en fraction de R), l'angle de sa position `a`, son orientation base → tête `o`, sa taille `s` et son score `q`. Les angles sont en radians, dans le repère de la page.

Le centre n'est pas envoyé : le serveur prend la position du mage (S1). Il pose le champ sur la grille du monde.

### Monde
```json
server → {"t": "game_update", "world": [[index, eau, terre, air, chaleur, charge, lumière], ...],
          "spells": [{"x": 640, "y": 360, "R": 120, "e": "water", "left": 2.9}]}
```

`world` liste les cellules non vides de la grille, à 10 Hz au plus. L'état complet (`cs`, `cols`, `rows`, `cells`) arrive dans `game_state`.

### Commandes de dessin
- Clic droit : ouvrir ou fermer le tableau.
- Clic gauche maintenu : tracer.
- Le sort part quand le cercle se ferme.

### Input joueur
```json
client → {"t": "in", "k": <bitmask>, "seq": <int>}
```

### Rejoindre une instance
```json
client → {"t": "join", "map": "<map_id>"}
```

---

## Architecture

Voir [CLAUDE.md](CLAUDE.md) pour les détails de la pipeline client (strokes → primitives → AST → resolver → réseau) et la structure serveur.

---

## Tests automatisés

La simulation serveur est testée sans ouvrir de fenêtre ni démarrer le réseau.
La suite couvre notamment le mouvement, les collisions, l'ordre des entrées
réseau, l'IA ennemie et les interactions de puzzle.
Elle comprend aussi une régression visuelle pygame sans fenêtre : une scène
d'objets interactifs est rendue puis comparée à sa capture de référence.

```bash
python -m unittest discover -s tests -v
```

Le même scénario est exécuté automatiquement par GitHub Actions à chaque push
et pull request (`.github/workflows/tests.yml`).
