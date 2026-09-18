# Plan de test — limites de la simulation

## Objectif

Vérifier que la simulation serveur reste prévisible aux frontières du monde,
lors d'entrées réseau imparfaites et au voisinage des seuils des mécanismes.
Les tests ciblent la logique serveur, sans fenêtre pygame ni websocket, afin
d'être reproductibles dans l'intégration continue.

## Périmètre et limites identifiées

| Domaine | Limite à couvrir | Risque | Critère d'acceptation |
| --- | --- | --- | --- |
| Carte | Bords gauche, droit, haut et bas | Sortie de carte ou position invalide | Le centre du joueur reste dans les bornes autorisées par sa hitbox. |
| Objets | Contact et tentative de traversée d'un obstacle | Passage à travers un mur | La position est inchangée et la vitesse devient nulle. |
| Mouvement | Plusieurs ticks continus et changement de direction | Saut de position ou accélération | Chaque pas vaut `PLAYER_SPEED × TICK_INTERVAL`; aucun déplacement anormal entre deux ticks. |
| Diagonale | Deux directions simultanées | Vitesse supérieure à celle en ligne droite | La norme du déplacement diagonal est égale à celle d'un déplacement horizontal. |
| Réseau | `seq` manquant, invalide, identique ou inférieur au dernier reçu | Retour en arrière après paquets désordonnés | L'entrée est ignorée; la position et l'état ne régressent pas. |
| IA ennemie | Collision, bord de carte et un tick IA + mouvement | Double déplacement, sortie de carte ou traversée d'objet | Un ennemi avance au plus de `speed × dt`, ou reste immobile si bloqué. |
| Combat | Santé proche de zéro, zéro et dégâts négatifs | Mort prématurée ou joueur actif après sa mort | La santé est bornée à zéro; le joueur mort ne reçoit plus d'entrée. |
| Interactions | Intensité juste sous / égale / au-dessus du seuil | Puzzle déclenché trop tôt ou jamais | La mutation n'arrive qu'à partir du seuil configuré. |
| Proximité | Rayon juste hors / à la frontière / dedans | Autel instable ou activation incorrecte | L'état s'active dans le rayon effectif et se réinitialise à la sortie. |

## Cas de test prioritaires

### P0 — à exécuter à chaque modification

1. Déplacement répété à droite sur 10 ticks : chaque delta de position est identique.
2. Déplacement diagonal : la distance totale d'un tick égale celle d'un tick horizontal.
3. Déplacement contre un obstacle : le joueur ne le traverse pas.
4. Paquet réseau ancien : il ne remplace pas le dernier mouvement accepté.
5. Ennemi libre : un passage IA suivi du système de mouvement produit un seul déplacement.
6. Ennemi devant un obstacle : il ne se déplace pas.
7. Dégât létal : santé à `0`, état `alive=False`, entrées refusées.
8. Torche : feu sous le seuil sans effet; feu au seuil déclenche `lit=True`.
9. Cristal : autel hors rayon éteint, dans le rayon allumé, à nouveau hors rayon éteint.

Les cas P0 et P1 de logique serveur sont automatisés dans `tests/test_gameplay.py` et doivent réussir
avec :

```bash
python -m unittest discover -s tests -v
```

### P1 — automatisés avant d'étendre les systèmes concernés

1. Joueur placé exactement contre chacun des quatre bords, avec une entrée sortante.
2. Objet collidable dont le joueur atteint exactement le coin.
3. Série de 60 entrées dans un tick : seule la limite prévue par la boucle est traitée et le reste demeure en file.
4. Séquences réseau `None`, texte non numérique, négative et très grande.
5. IA avec `frozen=True` et `speed_multiplier` à `0`, `0.01` et supérieur à `1`.
6. Cooldown d'attaque exactement avant, à, et après son expiration.
7. Rayon de proximité à une distance égale à `within + radius_source`.

### P2 — tests de stabilité et d'intégration

1. ✅ Simuler 10 minutes de ticks avec des entrées déterministes et vérifier que toutes les positions restent finies et dans la carte.
2. ✅ Simuler plusieurs joueurs et des paquets volontairement réordonnés.
3. ✅ Mesurer le coût p95 des systèmes serveur sur 300 ticks; le test échoue s'il dépasse le budget de `TICK_INTERVAL` (16,67 ms à 60 Hz).
4. ✅ Vérifier l'interpolation client avec des snapshots successifs : pas régulier, vitesse bornée et absence de dépassement de cible.
5. ✅ Rendre une scène pygame headless (torche, autel et cristal) et comparer ses pixels à une empreinte SHA-256 de référence. Les changements d'état allumé/alimenté doivent modifier plus de 100 pixels.

## Données de test

- Carte vide de `500 × 500` pour isoler le mouvement.
- Carte avec mur vertical et coins pour les collisions.
- Joueurs aux coordonnées proches des quatre limites.
- Ennemi à vitesse connue (`180`) et rayon connu (`12`).
- Torche de seuil `0.1`, cristal de rayon `16`, autel de rayon `20`.

Les valeurs sont délibérément petites et fixes : un échec doit être facile à
reproduire et à diagnostiquer.

## Règles de sortie

Une modification est prête à être intégrée lorsque tous les tests P0 passent,
qu'aucune nouvelle limite métier ne reste sans cas de test documenté, et que
les cas P1 touchés par la modification ont été automatisés ou justifiés.
