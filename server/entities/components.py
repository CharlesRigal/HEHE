"""Composants d'entite partages (Phase 2).

Toute entite simulee (joueur, ennemi, torche, levier, projectile, terrain
reactif) peut porter un sous-ensemble de ces composants. Les systemes
consomment les composants sans connaitre le type d'entite.

Contrat minimal pose en Phase 2 :
  - EntityBody       : physique (position, velocite, masse) pour ForceEffect
  - EntityAffinities : ponderation par element (vulnerabilite, resistance)
  - EntityStates    : sac d'etats nommes (lit, frozen, powered, ...)
  - EntityReactive  : regles declenchees sur changement d'etat (Phase 3)

La composition est volontaire : un joueur peut avoir Body + States ; une
torche aura Body (statique) + Affinities + States + Reactive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class EntityBody:
    """Corps physique. Consomme par ForceEffect (Phase 2+)."""
    x: float = 0.0
    y: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    mass: float = 1.0
    static: bool = False     # immuable (mur, torche scellee)
    radius: float = 16.0     # hitbox simple pour collision d'effet

    def apply_force(self, fx: float, fy: float, dt: float) -> None:
        """F = m*a : integre l'acceleration sur dt."""
        if self.static or self.mass <= 0.0:
            return
        self.velocity_x += (fx / self.mass) * dt
        self.velocity_y += (fy / self.mass) * dt

    def integrate(self, dt: float, bounds: tuple[float, float] | None = None) -> None:
        """Avance la position selon la velocite. Clamp optionnel."""
        if self.static:
            return
        self.x += self.velocity_x * dt
        self.y += self.velocity_y * dt
        if bounds is not None:
            w, h = bounds
            self.x = max(self.radius, min(w - self.radius, self.x))
            self.y = max(self.radius, min(h - self.radius, self.y))


@dataclass
class EntityAffinities:
    """Ponderation par element. Negatif = vulnerable, positif = resistant.

    weights[e] = -1.0  -> s'enflamme / fond / reagit fort a e
    weights[e] = +1.0  -> resiste
    weights absent    -> neutre (0.0)
    """
    weights: dict[str, float] = field(default_factory=dict)

    def weight_for(self, element: str | None) -> float:
        if element is None:
            return 0.0
        return self.weights.get(element, 0.0)

    def reacts_to(self, element: str | None, min_intensity: float = 0.0) -> bool:
        """True si l'affinite est suffisamment negative (vulnerable)."""
        if element is None:
            return False
        return self.weights.get(element, 0.0) <= -min_intensity


@dataclass
class EntityStates:
    """Sac d'etats nommes. Les ecritures notifient EntityReactive si present."""
    flags: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> Any:
        return self.flags.get(name, default)

    def set(self, name: str, value: Any) -> bool:
        """Retourne True si la valeur a change."""
        prev = self.flags.get(name)
        if prev == value:
            return False
        self.flags[name] = value
        return True


# Signature : (entity, state_name, old_value, new_value, context) -> None
ReactionCallback = Callable[[Any, str, Any, Any, dict], None]


@dataclass
class EntityReactive:
    """Regles de reaction a un changement d'etat (Phase 3).

    on_state_change est une liste de tuples (state_name, callback). La
    simulation appelle fire() apres toute mutation via EntityStates.
    """
    on_state_change: list[tuple[str, ReactionCallback]] = field(default_factory=list)

    def fire(
        self,
        entity: Any,
        state_name: str,
        old: Any,
        new: Any,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        for name, callback in self.on_state_change:
            if name == "*" or name == state_name:
                callback(entity, state_name, old, new, ctx)


@dataclass
class EntityCombat:
    """Composant HP : porte par tout ce qui peut subir un DamageEffect.

    Absent sur torches / portes / mares d'eau : le sort les traverse sans degat
    (seul StateChangeEffect agit). Present sur ennemis et potentiellement
    joueurs, cristaux destructibles, miroirs fragiles, etc.
    """
    health: float = 100.0
    max_health: float = 100.0
    alive: bool = True
    last_update: float = 0.0


@dataclass
class EnemyAI:
    """Composant IA minimal : cible le joueur le plus proche, frappe au contact.

    Porte par les Entity de type 'enemy'. Traite par EnemyAISystem.
    """
    speed: float = 180.0
    stop_distance: float = 2.0
    attack_hitbox_w: float = 22.0
    attack_hitbox_h: float = 22.0
    attack_damage: float = 12.0
    attack_cooldown: float = 1.1
    last_attack_at: float = 0.0
    attack_seq: int = 0
    direction: int = 1


@dataclass
class Entity:
    """Agregat a composition variable.

    Un ennemi a body + combat + ai + states (frozen, speed_multiplier).
    Une torche a body (static) + affinities + states + reactive.
    Une mare d'eau a body (static) + affinities + states.
    Les systemes filtrent par presence de composant (combat, ai).
    """
    id: str
    type: str                                   # "torch" | "enemy" | "brazier" | ...
    body: EntityBody = field(default_factory=EntityBody)
    affinities: EntityAffinities = field(default_factory=EntityAffinities)
    states: EntityStates = field(default_factory=EntityStates)
    reactive: EntityReactive = field(default_factory=EntityReactive)
    combat: EntityCombat | None = None
    ai: EnemyAI | None = None

    def set_state(self, name: str, value: Any, context: dict | None = None) -> bool:
        old = self.states.get(name)
        if self.states.set(name, value):
            self.reactive.fire(self, name, old, value, context)
            return True
        return False


if __name__ == "__main__":
    body = EntityBody(x=100.0, y=100.0, mass=2.0)
    body.apply_force(40.0, 0.0, dt=0.5)
    assert abs(body.velocity_x - 10.0) < 1e-6
    body.integrate(0.5)
    assert abs(body.x - 105.0) < 1e-6

    # Static : n'encaisse pas la force
    wall = EntityBody(static=True, mass=1.0)
    wall.apply_force(100.0, 100.0, dt=1.0)
    assert wall.velocity_x == 0.0 and wall.velocity_y == 0.0

    # Affinities
    aff = EntityAffinities(weights={"fire": -1.0, "water": 0.5})
    assert aff.reacts_to("fire", min_intensity=0.5)
    assert not aff.reacts_to("water")
    assert aff.weight_for("ice") == 0.0

    # States + Reactive
    fired = []
    def on_lit(entity, name, old, new, ctx):
        fired.append((name, old, new))

    ent = Entity(id="torch_01", type="torch")
    ent.reactive.on_state_change.append(("lit", on_lit))
    assert ent.set_state("lit", True)
    assert not ent.set_state("lit", True)        # pas de change -> pas de fire
    assert fired == [("lit", None, True)]

    # EntityCombat + EnemyAI optionnels
    goblin = Entity(
        id="e1", type="enemy",
        body=EntityBody(x=50.0, y=50.0, radius=12.0),
        combat=EntityCombat(health=100.0, max_health=100.0),
        ai=EnemyAI(speed=220.0),
    )
    assert goblin.combat is not None and goblin.ai is not None
    assert goblin.combat.alive and goblin.combat.health == 100.0
    torch2 = Entity(id="t2", type="torch")
    assert torch2.combat is None and torch2.ai is None

    print("components: OK")
