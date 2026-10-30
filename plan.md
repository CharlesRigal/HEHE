# Plan — Système de sorts par champ

Brouillon de travail. Le [README](README.md) fait foi. Ce plan traduit ses règles en code, dans la branche `feature/spell-field-system`. L'ancien plan reste dans l'historique git.

## Vue d'ensemble

```
CLIENT                                         SERVEUR
traits ─► groupement (L2-L4) ─► rôles (L5)     {"t":"s"} ─► ActiveSpell
       ─► cercle mesuré, $P emblème/signes ──►            ─► champ échantillonné sur la grille
       ─► qualité (min) ─► message "s"                    ─► WorldGrid : transport, seuils, forces
                                                          ─► {"t":"world"} ─► rendu client
```

## Phase 0 — Nettoyage

- Supprimer le système des torches : types `torch` et `brazier`, `EntityAffinities`, réactions par élément nommé (`_reactions`, `apply_state_change_to_entity`), carte `torch_puzzle`, rendu des torches, braseros, flaques et plaques de glace.
- Supprimer `EffectTickSystem` (vide) et les restes de l'ancienne pipeline (`cast_ast_spell`, `send_ast_spell`).
- Ajouter la règle M0 (garde-fou) au README.
- Garder `crystal`, `altar`, `door` et `pressure_plate` : ils ne réagissent pas à un élément nommé.

## Phase 1 — Le monde (serveur, `server/world/`)

`grid.py` — `WorldGrid` : grille numpy, cellules de 16 px.

| Champ | Valeur | Comportement naturel |
|---|---|---|
| `water` | ≥ 0 | diffuse si liquide ; immobile si gelée (M1) ; diffuse vite si vapeur |
| `earth` | ≥ 0 | immobile ; diffuse lentement si lave (M1) |
| `air` | ≥ 0 | surplus d'air sur un fond ambiant constant ; diffuse vite et se dissipe |
| `heat` | signée | diffuse et revient vers 0 |
| `charge` | ≥ 0 | diffuse et se dissipe |
| `light` | ≥ 0 | se dissipe vite |

- **Transport conservatif** (schéma upwind par flux) : un flux convergent accumule la matière, ce qu'exige la compression.
- **Murs** : les cellules des objets de la carte bloquent tout flux.
- **États M1**, par seuils sur `heat` uniquement : glace (eau, `heat` < 0), vapeur (eau, `heat` > seuil), lave (terre, `heat` > seuil). Un état change seulement la mobilité de la cellule.
- **Forces** : un corps reçoit `Σ matière × vitesse de son élément` dans sa cellule. L'air ambiant compte toujours, donc le vent pousse sans rien créer.
- **Contenu initial** optionnel dans le YAML de carte (`world:` liste de rectangles).

`spell.py` — `ActiveSpell` construit depuis le message `s` :
- **Puissance** = (R / R_ref)², d'après C3. Elle multiplie les vitesses du champ et la quantité créée.
- **E4** : création de l'élément au centre, quantité ∝ surface du cercle.
- **F1/F5/F6** : chaque signe pose un noyau gaussien centré sur sa position relative transposée dans la zone (r/R → même fraction du rayon de zone), de largeur ∝ taille du signe.
  - Les signes vectoriels (Direction, Traction, Colonne) ajoutent une vitesse dans leur orientation.
  - Convergence/Dispersion ajoutent une vitesse radiale signée vers le centre.
  - Suspension bloque la sortie de matière de la cellule et sa diffusion.
  - Répétition prolonge la durée locale de la cellule.
- **Principe 5** : le champ ne déplace que la grandeur de l'élément du sort.
- **C7** : à la fin, le champ disparaît et la physique naturelle relâche l'élément.

`GameInstance` : tick du monde, application des sorts, forces, diffusion `world` à 10 Hz (cellules non nulles seulement) et liste des sorts actifs.

## Phase 2 — Lecture du dessin (client, `client/magic/`)

| Module | Rôle | Règles |
|---|---|---|
| `geometry.py` | rééchantillonnage, distances point/segment, centroïdes | — |
| `grouping.py` | union-find des traits en contact (distance ≤ épaisseur) | L2, L3, L4 |
| `circle.py` | boucle fermée : écart angulaire max × R ≤ épaisseur ; rondeur | C1, C4, qualité |
| `dollar_p.py` | reconnaisseur $P, balayage de rotation optionnel | L6 |
| `templates.py` | glyphes provisoires (emblèmes et signes), tête/base annotées | — |
| `reader.py` | rôles par position, mesures relatives au centre, qualité min, encre | L1, L5, F0, F1, S3 |
| `spell_message.py` | lecture → message réseau `s` | L7 |

- **Signe :** son orientation est le meilleur angle du balayage. Il est mort si le score à θ + 180° est trop proche du meilleur (F0).
- **Signe radial signé :** Convergence et Dispersion sont **un seul glyphe**. Le signe vient de la composante radiale : tête vers le centre = compresser, vers l'extérieur = étaler.
- **Glyphes :** ceux des emblèmes, de Direction et de Répétition sont des **provisoires**, à remplacer par les vrais.

## Phase 3 — Jeu

- **Tableau de dessin** (`client/magic/drawing_board.py`) : clic droit pour l'ouvrir ou le fermer, clic gauche pour tracer. Il teste seulement la fermeture du cercle après chaque trait (C1/L1). À la fermeture : lecture, envoi, effacement.
- **S1 :** le sort est centré sur le mage au moment de la fermeture. Le rayon de la zone est le rayon du cercle, en pixels.
- **Rendu du monde** (`client/graphics/world_renderer.py`) : couleurs par grandeur et par état, et cercle des sorts actifs.
- **Nouvelle carte `elements_lab`** : bassin d'eau, terre chaude, cristaux légers.

## Phase 4 — Tests

- `tests/test_world.py` :
  - conservation de l'eau ;
  - création ∝ surface ;
  - la traction rassemble ;
  - la suspension tient ;
  - relâchement à la fin ;
  - eau + froid → glace immobile ;
  - un sort d'eau ne bouge pas la chaleur ;
  - le vent pousse un corps léger plus qu'un lourd.
- `tests/test_reading.py` :
  - contact selon l'épaisseur ;
  - cercle fermé ou ouvert, mono ou multi-trait ;
  - un trait qui touche le cercle le tue ;
  - emblème le plus proche du centre ;
  - $P reconnaît chaque glyphe bruité et tourné ;
  - orientation ;
  - convergence contre dispersion ;
  - ambiguïté F0 ;
  - qualité min ;
  - pentacle complet → message.
- Mise à jour de la référence visuelle, après le retrait des torches.

## Décisions prises dans ce plan (à valider)

- **Direction et Traction** ont le même effet de champ (une vitesse). La traction porte aussi au-delà du cercle (bassin de captation à 2 R) : elle va chercher l'élément existant (E4).
- **Colonne** : vecteur comme Direction, mais plus rapide et plus étroit. Pas de hauteur (monde 2D).
- **Durée de base d'un sort** : constante, prolongée localement par la Répétition.
- **Rupture C5** (couper un cercle actif) : pas dans cette itération.

## Hors de cette itération

- Les vrais glyphes.
- La rupture C5.
- Les règles croisées (M2).
- Le support S2 (dessin sur un objet).
- Le grimoire.
