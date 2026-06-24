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
- Refroidir une forge chaude pour désactiver un piège
- Vaporiser de l'eau en lançant du feu dessus
- Électriser de l'eau pour créer une chaîne de choc
- Amplifier un son pour briser une vitre

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
