# HEHE

Jeu de mage multijoueur où les sorts sont **dessinés à la main** et résolus par un système émergent continu. Les sorts sont des **outils** pour résoudre des énigmes et interagir avec le monde, pas des boutons à dégât.

Voir [plan.md](plan.md) pour la feuille de route d'implémentation.

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

### Le cercle

- **C1 — Fermeture.** Tant que le cercle n'est pas fermé, le pentacle est inerte. Fermer le cercle lance le sort. Le cercle se trace donc en dernier.
- **C2 — Bloc autonome.** Tout ce qui est dans le cercle appartient au sort. Ce qui est dehors n'existe pas pour lui. Un trait qui traverse le cercle le brise.
- **C3 — Taille.** Le rayon du cercle donne le rayon de la zone d'effet.
- **C4 — Rondeur.** Plus le cercle est rond, moins le sort perd d'énergie.
- **C5 — Rupture.** Couper ou effacer le cercle d'un sort actif l'arrête net.
- **C6 — Voisinage.** Deux cercles séparés sont deux sorts indépendants. Deux cercles qui se chevauchent sont tous deux brisés.

### L'emblème

- **E1 — Un seul, au centre.** L'emblème fixe la nature de l'énergie. Deux emblèmes dans un cercle : sort invalide.
- **E2 — Proportion.** La taille de l'emblème rapportée à celle du cercle donne l'**intensité** élémentaire. C'est elle qui est comparée aux seuils de réaction du monde (une torche s'allume à partir d'une certaine intensité de feu).
- **E3 — Sans emblème.** Un cercle sans emblème est un sort de **force pure** : il pousse, tire ou retient, sans élément.

| Emblème | Grandeur physique portée | Clé d'affinité |
|---|---|---|
| Feu | chaleur (+) | `fire` |
| Glace | chaleur (−) | `ice` |
| Eau | matière fluide | `water` |
| Vent | poussée sur les corps légers | `wind` |
| Terre | masse, solidité | `earth` |
| Foudre | charge | `lightning` |
| Lumière | signal, visibilité | `light` |

Le glyphe de chaque emblème reste à dessiner.

### Les flèches

Les flèches se placent entre l'emblème et le cercle, sans toucher ni l'un ni l'autre, ni se toucher entre elles.

Mesures communes à toutes les flèches :

- **F1 — Orientation.** La page est une carte : le haut de la page est le haut du monde. Une flèche pointe dans le monde là où elle pointe sur la page.
- **F2 — Longueur.** Plus la flèche est longue, plus sa contribution est forte.
- **F3 — Somme.** Les flèches de même type s'additionnent en vecteurs. Vers l'extérieur tout autour : l'effet émane. Vers le centre : l'effet se ramasse. En biais : l'effet tourne en spirale.
- **F4 — Symétrie.** Des flèches régulièrement réparties donnent un sort stable. Un déséquilibre fait dériver le sort du côté le plus chargé. Ce n'est pas une erreur, c'est un outil.

Types de flèches (v1) :

| Flèche | Ce qu'elle règle | Grandeur physique |
|---|---|---|
| Direction | où va l'effet | direction du vecteur |
| Traction | tire les corps vers sa pointe ; retournée, elle pousse | force appliquée (N) |
| Convergence | resserre l'effet vers sa pointe | zone plus étroite, portée plus longue |
| Dispersion | étale l'effet | zone plus large, intensité plus faible |
| Suspension | tient l'effet ou l'objet en place | maintien contre l'amortissement |
| Répétition | fait durer le sort | durée (une flèche de plus = plus longtemps) |

Le glyphe de chaque flèche reste à dessiner. Chaque type doit se distinguer par sa pointe, pas par sa hampe.

### Le support

- **S1 — Papier (défaut).** Le pentacle agit autour du mage, à l'endroit où il se tient au moment de fermer le cercle.
- **S2 — Surface du monde.** Dessiné sur un objet ou sur le sol, le pentacle agit sur ce support et y reste accroché. Dessiner sur une caisse, c'est viser la caisse.
- **S3 — Encre.** Chaque trait consomme de l'encre selon sa longueur. Plus d'encre, plus de traits. Un trait mort consomme quand même.

### Qualité du tracé

Chaque trait reçoit une note de qualité entre 0 et 1. Sous le seuil, le trait est **mort** : il reste visible mais ne compte pas. Au-dessus, la note multiplie le rendement du sort.

| Trait | Critère mesuré | Seuil de départ (à régler) |
|---|---|---|
| Cercle | écart entre début et fin du trait | ≤ 5 % du périmètre |
| Cercle | variation du rayon | ≤ 8 % du rayon moyen |
| Flèche | rectitude de la hampe (corde / longueur) | ≥ 0,95 |
| Flèche | symétrie de la pointe | écart d'angle ≤ 15° |
| Emblème | centrage dans le cercle | ≤ 10 % du rayon |
| Tous | aucun contact entre deux traits | marge ≥ 3 % du rayon |

Un cercle mort ne lance rien. Un emblème mort donne un sort de force pure (E3). Une flèche morte est simplement absente de la somme.

### Du dessin à la physique

| Mesure du dessin | Grandeur | Bride moteur | État |
|---|---|---|---|
| Somme des flèches de traction | force `(fx, fy)` | `GameInstance.apply_force` | existe (borne 2400) |
| Rayon du cercle | rayon de zone | `apply_force_in_radius` | existe |
| Flèches de répétition | durée | paramètre `duration` | existe (borne 10 s) |
| Support = objet | cible | `target_id` | existe |
| Masse de la cible | accélération `F / m` | `EntityBody.apply_force` | existe |
| Emblème + proportion | élément + intensité | `apply_state_change_to_entity` | existe, jamais appelé |
| Flèches vers le centre / spirale | force radiale ou tangentielle | — | manque (force uniforme seulement) |
| Rupture du cercle | arrêt d'une force active | — | manque |
| Suspension | maintien d'un corps | — | manque |
| Terre + flèches | changement de masse | — | manque |

### Exemples

- **Pousser une balle vers une fosse.** Pas d'emblème, une flèche de traction retournée pointant vers la fosse, cercle. Balle trop lourde : flèche plus longue, donc cercle plus grand, donc plus d'encre.
- **Allumer trois torches alignées.** Emblème du feu, une flèche de direction vers les torches, une flèche de convergence pour allonger la portée, cercle.
- **Soulever un cristal jusqu'à l'autel.** Dessiné sur le cristal : flèche de traction vers l'autel, flèches de répétition pour tenir la distance, cercle. Le cristal lourd demande plus de flèches que le léger.

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

### Cast de sort (format unique émergent)
```json
client → {"t": "s", "e": "fire", "bh": "projectile", "spd": 0.5, "pwr": 0.8, ...}
```

Le format `"s"` porte les paramètres continus dérivés du `ResolvedSpell`. Le serveur traduit ces paramètres en **effets** (damage, force, state_change, terrain_spawn, binding, reaction élémentaire) selon des seuils — pas une lookup table.

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
