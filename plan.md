# Plan — Système magique émergent pour puzzles

## Cible

Passer d'un moteur qui **fait du dégât** à un moteur qui **applique des effets physiques** sur un monde réactif. Les sorts deviennent des outils pour résoudre des énigmes, pas des boutons à dégât.

Règle fondamentale (rappel) :

```
pattern → propriétés → effet émergent
```

Jamais `pattern → effet`.

## Jalon MVP (puzzle visé)

**« Allumer une torche avec un sort de feu dirigé. »**

Conditions pour réussir :
- élément dominant = feu
- direction explicite (flèche)
- trajectoire touche la torche
- intensité suffisante

Ce jalon valide les fondations. Tout le reste s'y greffe.

---

## 6 manques critiques

1. **Forces continues** — le serveur ne sait faire que dégât + durée
2. **Entités interactives** — pas de torches, leviers, plateformes, objets mobiles
3. **Composants d'entité** — pas d'état (allumé, gelé), pas d'affinité élémentaire, pas de masse
4. **Réactions élémentaires** — `feu + glace → eau` etc. n'existe nulle part
5. **Binding** — un sort ne peut pas « tenir », « lier », « suivre »
6. **Feedback en cours de dessin** — le joueur dessine à l'aveugle

---

## Phase 1 — Moteur d'effets composables (serveur)

**Objectif** : remplacer `parametric_spell.cast_parametric_spell` (monolithe de 180 lignes produisant `{damage, radius, duration}`) par un générateur d'**effets** typés et composables.

**Décisions structurantes** :
- **Option A** (choisie) : refonte propre avec classes `Effect` typées, pas de dicts
- **`force` inclus dès Phase 1** avec runtime stub (le type existe, la simulation attend Phase 2)
- **Pas de tests de non-régression** : la reconstruction est prioritaire, les régressions de gameplay sont acceptées

**État jouable après Phase 1** : probablement cassé ou dégradé. Normal. Phase 2+3 restaurent puis étendent.

---

### Phase 1.1 — Types d'effets

**Fichier** : `server/effects/effect_types.py`

Dataclasses typées, hiérarchie simple :

```python
@dataclass
class Effect:
    owner_id: str
    element: str
    shape: EffectShape           # circle | ellipse | cone + position
    duration: float              # 0 = instant, >0 = persistant
    tick_interval: float         # 0 = non ticking

@dataclass
class DamageEffect(Effect):
    amount: float
    pierce: bool = False

@dataclass
class StateChangeEffect(Effect):
    state_name: str              # "lit", "frozen", "on_fire", ...
    value: Any
    target_filter: dict          # {"affinity": "fire", "min_threshold": 0.2}

@dataclass
class ForceEffect(Effect):
    dir_x: float
    dir_y: float
    magnitude: float             # N (newtons approximatifs)
```

**EffectShape** : dataclass dédiée (circle, ellipse_angle, cone_half_angle, position).

Les effets primitifs additionnels (`terrain_spawn`, `binding`, `elemental_reaction`) arrivent en Phase 4-5. Pas Phase 1.

---

### Phase 1.2 — Producteurs d'effets

**Fichier** : `server/effects/producers.py`

Chaque **producer** inspecte `ServerSpellSpec` + caster et retourne une liste d'`Effect` (éventuellement vide).

```python
def produce_damage(spec, caster) -> list[Effect]:
    # seuils existants : is_wall / is_pool / has_movement / has_area
    # dérive DamageEffect impact + DamageEffect tick
    ...

def produce_state_change(spec, caster) -> list[Effect]:
    # émet StateChangeEffect("lit", True) si element=fire + intensité suffisante
    ...

def produce_force(spec, caster) -> list[Effect]:
    # ex: compression élevée + vitesse élevée → ForceEffect (poussée)
    # gravity-like : compression basse + duration élevée + axe vertical → ForceEffect (lévitation)
    ...
```

Ajouter un producer = ajouter une fonction dans un registre. Aucun switch central.

---

### Phase 1.3 — Pipeline `spec → effects`

**Fichier** : `server/effects/spell_to_effects.py`

```python
REGISTERED_PRODUCERS = [produce_damage, produce_state_change, produce_force]

def spec_to_effects(spec: ServerSpellSpec, caster) -> list[Effect]:
    out = []
    for p in REGISTERED_PRODUCERS:
        out.extend(p(spec, caster))
    return out
```

Seuils documentés dans chaque producer, **pas de table centrale**.

---

### Phase 1.4 — Runtime des effets

**Fichier** : `server/effects/runtime.py`

- `ActiveEffect` : wrapper avec `remaining`, `next_tick_at`, `hit_targets`, état courant
- Dispatcher de tick par type d'effet :
  - `DamageEffect` → collision + apply_damage (reprend la logique actuelle de `tick_parametric_spell`)
  - `StateChangeEffect` → collision + apply_state (stub Phase 1, utilisé Phase 3)
  - `ForceEffect` → collision + apply_force (stub Phase 1, exécute Phase 2)

`game_instance.active_spells` devient `active_effects: list[ActiveEffect]`.

---

### Phase 1.5 — Migration de `parametric_spell` + `game_instance`

**Fichiers touchés** :
- `server/spells/parametric_spell.py` → devient adaptateur mince qui appelle `spec_to_effects` puis pousse des `ActiveEffect`
- `server/game_instance.py` → loop `_update_active_spells` consomme `ActiveEffect` via le dispatcher
- `server/spells/default_spells.py` → nettoyage des anciens spell_id (fire_projectile, fire_rune, lightning_rune)

Split + AOI : ré-exprimés comme des producers (`produce_split`, `produce_aoi`) qui émettent de nouveaux `DamageEffect` à l'impact/expiration. Pas de champ ad-hoc dans le dict.

---

### Livrables Phase 1

| Fichier | Contenu |
|---|---|
| `server/effects/effect_types.py` | Dataclasses `Effect`, `DamageEffect`, `StateChangeEffect`, `ForceEffect`, `EffectShape` |
| `server/effects/producers.py` | `produce_damage`, `produce_state_change`, `produce_force` (+ split, aoi ré-exprimés) |
| `server/effects/spell_to_effects.py` | Registry + `spec_to_effects()` |
| `server/effects/runtime.py` | `ActiveEffect` + dispatcher de tick |
| `server/spells/parametric_spell.py` | Adaptateur mince |
| `server/game_instance.py` | Consomme `active_effects` |

### Pièges identifiés

1. **Fuite de logique** : ne pas laisser de if/else dans `parametric_spell`. Tout doit être dans un producer.
2. **Sur-abstraction** : ne pas créer de classes pour chaque petite chose. `Effect` hiérarchie simple suffit.
3. **Couplage réseau** : l'architecture d'effets est **interne serveur**. Le format `"s"` ne change pas.
4. **Force sans physique** : `ForceEffect` est défini mais n'agit sur rien tant que Phase 2 n'a pas posé `EntityBody`. Accepté.

---

## Phase 2 — Composants d'entité (serveur)

**Objectif** : toute entité (joueur, objet, terrain, mécanisme) partage le même système de composants.

### Composants communs

```python
@dataclass
class EntityBody:
    mass: float           # kg, influence les forces
    velocity: Vec2
    position: Vec2

@dataclass
class EntityAffinities:
    weights: dict[str, float]   # {"fire": -0.5, "ice": 1.0}  (négatif = vulnérable)

@dataclass
class EntityStates:
    flags: dict[str, Any]       # {"lit": False, "frozen": False, "mass_factor": 1.0}

@dataclass
class EntityReactive:
    on_state_change: list[Callable]   # règles déclenchées par changement d'état
```

Les entités actuelles (joueurs, sorts) gagnent ces composants progressivement.

### Livrable Phase 2

- `server/entities/components.py`
- Migration des joueurs pour utiliser `EntityBody` + `EntityStates`
- Moteur de simulation continue (force → velocity → position, chaque tick)

---

## Phase 3 — Entités interactives (YAML + serveur)

**Objectif** : enrichir le format YAML des maps pour décrire des entités réactives.

### Extension du format map

```yaml
interactive:
  - id: torch_01
    type: torch
    position: [800, 400]
    state:
      lit: false
    affinities:
      fire: -1.0      # s'allume au feu
      water: 1.0      # résiste à l'eau
    reactions:
      - trigger: { element: fire, min_intensity: 0.2 }
        effect: { state: lit, value: true }

  - id: brazier_lit
    type: brazier
    position: [400, 400]
    state: { lit: true }
    emits: { element: fire, radius: 60 }  # allume ce qui entre dedans
```

### Types cibles pour MVP

- `torch` (allumable)
- `brazier` (émet un élément)
- `pressure_plate` (active si masse > seuil)
- `door` (ouvre sur condition)
- `ice_patch` / `water_pool` (terrain réactif)

### Livrable Phase 3

- Schéma YAML étendu
- `server/entities/interactive.py` : chargement + simulation
- Une map `torch_puzzle.yaml` : 3 torches, un brazier, une porte qui s'ouvre quand les 3 sont allumées

→ **MVP jouable** : le joueur dessine un sort de feu dirigé, touche une torche, la porte s'ouvre.

---

## Phase 4 — Réactions élémentaires

**Objectif** : deux éléments qui se rencontrent produisent un effet émergent.

### Table symétrique (lois physiques, pas recettes de sort)

| A | B | Résultat |
|---|---|---|
| fire | ice | water + steam_aoe |
| fire | water | steam_aoe (évaporation) |
| water | lightning | chain_shock sur tout contact eau |
| water | ice | terrain glace |
| fire | wind | flame_spread (propagation) |
| ice | fire | water |

Cette table décrit la **physique du monde**, pas une collection de sorts. Un sort ne lit jamais cette table. Elle se déclenche à la collision des effets.

### Livrable Phase 4

- `server/effects/elemental_reactions.py`
- Détection collision effet-effet / effet-terrain
- Émission de nouveaux effets en sortie

---

## Phase 5 — Binding

**Objectif** : permettre à un sort de **tenir**, **lier**, **suivre**.

### Sémantique dérivée

- `focus` élevé + `duration` élevée → le sort persiste sur sa cible
- `role_zone` + deux cibles à portée → binding croisé
- Flèche + zone de fin → trajectoire liée à un point d'ancrage

### Cas d'usage

- Lévitation : force verticale persistante liée à un objet
- Batterie magique : binding sort → mécanisme, énergie continue
- Lien énergétique : deux cristaux liés transfèrent des états

### Livrable Phase 5

- `Effect.binding` implémenté dans le moteur
- Simulation des liens à chaque tick
- Une map `levitation_puzzle.yaml`

---

## Phase 6 — Feedback temps réel (client)

**Objectif** : le joueur voit ce qu'il est en train de dessiner.

### Affichage pendant le dessin

- Propriétés dominantes du `PropertyBag` partiel (feu ↑, chaos ↑, vitesse ↓)
- Relations spatiales actives (cercle englobe X, flèche vers Y)
- Effets prédits (icônes, pas de noms de sorts)
- Archétype visuel reconnaissable (compression haute = apparence projectile)

### Livrable Phase 6

- Resolver incrémental (peut tourner sur un AST partiel)
- Overlay client qui affiche les dominantes en live
- **Pas** de nom de sort, pas de texte pseudo-grammatical

---

## Phase 7 — Grimoire

Sauver `ResolvedSpell.params` dans un slot, rejouer depuis le slot. Trivial une fois le reste en place.

---

## Pièges à éviter

1. **Table de réactions ≠ table de recettes.** La table Phase 4 modélise une physique, pas un sort. Différence essentielle mais subtile. À garder sous contrôle.
2. **L'illisibilité du continu.** Il faut des **archétypes reconnaissables** dans l'espace des paramètres. Pas des recettes, mais des attracteurs visuels stables.
3. **Équilibrage PvP.** Meta impossible à fixer. Accepter le flou, ou capper des combinaisons extrêmes.
4. **Ambition.** 7 phases = plusieurs mois. Un jalon jouable à chaque phase, sinon motivation qui chute.
5. **Ne pas ressusciter la grammaire.** Tentation forte quand on voudra « un peu de prédictibilité ». Refuser : c'est le continu qui fait l'émergence.

---

## Ordre strict

1. **Phase 1** (effets composables) — fondation, non négociable
2. **Phase 2** (composants entités) — prérequis physique continu
3. **Phase 3 partielle** (torche + porte) — **MVP jouable**
4. Phase 4, 5 — extensions
5. Phase 6 — confort joueur
6. Phase 7 — feature

À chaque phase, une map démo doit être jouable.
