"""EffectTickSystem : wrapper fin autour du runtime d'effets.

Ne change pas la logique existante (dispatcher par type + detect_reactions),
mais expose une interface uniforme `tick(world, dt, now)` alignee sur les
autres systems. Cela prepare Phase 4 (ReactionSystem) et Phase 5
(BindingSystem) qui pourront s'inserer dans le meme pipeline.
"""
from __future__ import annotations

from typing import Any

from server.effects.elemental_reactions import detect_reactions
from server.effects.runtime import spawn_effect, tick_all


class EffectTickSystem:
    def tick(self, world: Any, dt: float, now: float) -> None:
        if not world.live_effects:
            return
        bounds = tuple(world.map_data.get("size", [1280, 720]))
        world.live_effects = tick_all(world, world.live_effects, dt, now, bounds)

        result = detect_reactions(world.live_effects)
        if result.consumed_ids or result.new_effects:
            world.live_effects = [
                le for le in world.live_effects if id(le) not in result.consumed_ids
            ]
            for effect in result.new_effects:
                world.live_effects.append(spawn_effect(effect, now=now))


if __name__ == "__main__":
    class _World:
        map_data = {"size": [100, 100]}
        live_effects = []

    # Vide : ne crash pas
    EffectTickSystem().tick(_World(), 0.016, 0.0)
    print("effect_tick_system: OK")
