"""Types d'effets emis par les sorts.

Un sort produit une liste d'Effect via les producers (voir producers.py).
Chaque Effect est une donnee typee consommee par le runtime (voir runtime.py
en Phase 1.4) qui applique les effets aux entites via collision de shape.

Hierarchie minimale :
    Effect (base)
      |- DamageEffect        degats ponctuels ou periodiques
      |- StateChangeEffect   change un etat d'entite (lit, frozen, ...)
      |- ForceEffect         applique une force (lecture Phase 2)

Les types additionnels (TerrainSpawnEffect, BindingEffect,
ElementalReactionEffect) arrivent en Phase 4-5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ShapeKind(Enum):
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    CONE = "cone"


@dataclass
class EffectShape:
    """Zone de collision d'un Effect dans le monde.

    - CIRCLE : utilise `radius`
    - ELLIPSE : utilise `radius_x`, `radius_y`, `angle` (rotation en rad)
    - CONE : utilise `radius` (portee), `angle` (direction), `cone_half_angle`

    La shape peut se deplacer via `velocity_x/y` (projectile). Position (x, y)
    mise a jour par le runtime chaque tick.
    """
    kind: ShapeKind
    x: float
    y: float
    radius: float = 0.0
    radius_x: float = 0.0
    radius_y: float = 0.0
    angle: float = 0.0
    cone_half_angle: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0


@dataclass
class Effect:
    """Effet emis par un sort. Base des sous-types.

    - duration=0.0 : effet instantane applique une fois a la creation
    - duration>0.0 : effet persistant, tick selon tick_interval
    - tick_interval=0.0 : pas de tick (soit instantane, soit permanent sans tick)

    Binding (Phase 5) : si `bind_target_id` est pose, le runtime recolle
    la shape sur l'entite chaque tick (follow). Si en plus `bind_source_id`
    est pose, la shape se place au milieu des deux (link). Voir binding.py.
    """
    owner_id: str
    element: str
    shape: EffectShape
    duration: float = 0.0
    tick_interval: float = 0.0
    bind_target_id: str | None = None
    bind_source_id: str | None = None


@dataclass
class DamageEffect(Effect):
    amount: float = 0.0
    pierce: bool = False


@dataclass
class StateChangeEffect(Effect):
    """Change un etat sur les entites touchees (ex: torche -> lit=True).

    `target_filter` permet de restreindre l'application :
        {"affinity": "fire", "min_intensity": 0.2}
    signifie : n'applique qu'aux cibles avec affinite "fire" et si l'intensite
    du sort depasse 0.2. Interprete par le runtime Phase 3.
    """
    state_name: str = ""
    value: Any = None
    target_filter: dict = field(default_factory=dict)


@dataclass
class ForceEffect(Effect):
    """Force vectorielle appliquee aux entites ayant un EntityBody (Phase 2).

    Phase 1 : le type existe, le runtime l'ignore (stub).
    Phase 2 : le runtime l'applique via F = ma sur les corps physiques.
    Phase 5 : si `continuous=True`, la force est reappliquee chaque tick
              (levitation). Si `auto_bind_on_hit=True`, la premiere
              collision pose `bind_target_id` et colle l'effet a la cible.
    """
    dir_x: float = 1.0
    dir_y: float = 0.0
    magnitude: float = 0.0
    continuous: bool = False
    auto_bind_on_hit: bool = False


if __name__ == "__main__":
    import math

    shape = EffectShape(kind=ShapeKind.CIRCLE, x=100.0, y=200.0, radius=50.0)
    dmg = DamageEffect(owner_id="p1", element="fire", shape=shape, amount=12.0)
    assert dmg.amount == 12.0
    assert dmg.shape.kind == ShapeKind.CIRCLE

    ellipse = EffectShape(
        kind=ShapeKind.ELLIPSE,
        x=0.0, y=0.0,
        radius_x=60.0, radius_y=20.0,
        angle=math.pi / 4,
    )
    state = StateChangeEffect(
        owner_id="p1", element="fire", shape=ellipse,
        duration=0.0,
        state_name="lit", value=True,
        target_filter={"affinity": "fire", "min_intensity": 0.2},
    )
    assert state.state_name == "lit"
    assert state.target_filter["affinity"] == "fire"

    cone = EffectShape(
        kind=ShapeKind.CONE,
        x=0.0, y=0.0,
        radius=120.0,
        angle=0.0,
        cone_half_angle=math.pi / 6,
    )
    force = ForceEffect(
        owner_id="p1", element="fire", shape=cone,
        duration=0.5,
        dir_x=1.0, dir_y=0.0, magnitude=800.0,
    )
    assert force.magnitude == 800.0
    assert force.shape.cone_half_angle > 0.0

    print("effect_types: OK")
