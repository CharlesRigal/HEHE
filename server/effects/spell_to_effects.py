"""Pipeline ServerSpellSpec -> list[Effect].

Point d'entree unique cote serveur. Aucun switch/case ici : l'ordre et la
composition des effets sont definis par REGISTERED_PRODUCERS.

Pour ajouter un nouveau type d'effet emergent :
  1. definir un Effect (effect_types.py)
  2. ecrire un producer (producers.py)
  3. l'enregistrer ci-dessous

Le runtime (Phase 1.4) consomme la liste retournee.
"""
from __future__ import annotations

from typing import Any, Callable

from server.effects.effect_types import Effect
from server.effects.producers import (
    produce_binding,
    produce_damage,
    produce_force,
    produce_state_change,
)
from server.magic.spell_spec import ServerSpellSpec


Producer = Callable[[ServerSpellSpec, Any], list[Effect]]


REGISTERED_PRODUCERS: list[Producer] = [
    produce_damage,
    produce_state_change,
    produce_force,
    produce_binding,
]


def spec_to_effects(spec: ServerSpellSpec, caster: Any) -> list[Effect]:
    """Applique tous les producers enregistres et concatene les effets emis."""
    out: list[Effect] = []
    for producer in REGISTERED_PRODUCERS:
        out.extend(producer(spec, caster))
    return out


if __name__ == "__main__":
    class _FakeCaster:
        id = "p1"
        def position(self): return (100.0, 100.0)
        def facing(self): return (1.0, 0.0)

    caster = _FakeCaster()

    # Projectile feu : damage (1) + state_change (1) + force (1) = 3 effets
    spec = ServerSpellSpec(element="fire", power=0.6, speed=0.5, compression=0.3)
    effects = spec_to_effects(spec, caster)
    types = [type(e).__name__ for e in effects]
    assert "DamageEffect" in types
    assert "StateChangeEffect" in types
    assert "ForceEffect" in types
    assert len(effects) == 3

    # Pool feu : damage (1) + state_change (1) = 2 effets (pas de force : stationnaire)
    spec_pool = ServerSpellSpec(
        element="fire", power=0.5, spread=0.5, fade_rate=0.5, compression=0.2,
    )
    effects_pool = spec_to_effects(spec_pool, caster)
    types_pool = [type(e).__name__ for e in effects_pool]
    assert "ForceEffect" not in types_pool
    assert len(effects_pool) == 2

    # Sort neutre faible : uniquement damage
    spec_weak = ServerSpellSpec(element=None, power=0.05, compression=0.1)
    effects_weak = spec_to_effects(spec_weak, caster)
    assert all(type(e).__name__ == "DamageEffect" for e in effects_weak)

    print("spell_to_effects: OK")
