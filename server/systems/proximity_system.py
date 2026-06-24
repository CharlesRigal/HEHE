"""ProximitySystem : boucle de reactions entite-entite par proximite.

Phase 5 bis : les altars s'allument (`powered`) quand un cristal est dans
leur rayon. Generalisable a tout couple (emetteur, receveur) via un champ
`proximity_reactions` sur l'entite receveur :

  entity.states.flags["_proximity"] = [
      {"source_type": "crystal", "within": 40.0,
       "state_name": "powered", "value": True,
       "clear_state_name": "powered", "clear_value": False},
  ]

Par defaut, les altars recoivent cette regle sur crystal. Le system met a
True quand au moins un cristal est dans le rayon, False sinon.
"""
from __future__ import annotations

import math
from typing import Any

from server.entities.components import Entity


class ProximitySystem:
    def tick(self, world: Any, dt: float, now: float) -> None:
        _ = dt, now
        entities = getattr(world, "entities", None)
        if not entities:
            return

        for receiver in entities:
            rules = receiver.states.flags.get("_proximity")
            if not rules:
                continue
            for rule in rules:
                self._apply_rule(world, receiver, rule)

    def _apply_rule(self, world: Any, receiver: Entity, rule: dict) -> None:
        source_type = rule.get("source_type")
        within = float(rule.get("within", 40.0))
        state_name = rule.get("state_name")
        value = rule.get("value")
        clear_name = rule.get("clear_state_name", state_name)
        clear_value = rule.get("clear_value")

        if not state_name:
            return

        rx, ry = receiver.body.x, receiver.body.y
        hit = False
        for source in world.entities:
            if source.id == receiver.id:
                continue
            if source_type and source.type != source_type:
                continue
            dx = source.body.x - rx
            dy = source.body.y - ry
            if math.hypot(dx, dy) <= within + source.body.radius:
                hit = True
                break

        if hit:
            if receiver.set_state(state_name, value):
                if hasattr(world, "_on_entity_state_changed"):
                    world._on_entity_state_changed(receiver)
        elif clear_name:
            if receiver.set_state(clear_name, clear_value):
                if hasattr(world, "_on_entity_state_changed"):
                    world._on_entity_state_changed(receiver)


if __name__ == "__main__":
    from server.entities.components import EntityBody

    class _World:
        entities = []
        def _on_entity_state_changed(self, ent): pass

    w = _World()
    altar = Entity(id="a1", type="altar", body=EntityBody(x=100, y=100, radius=20, static=True))
    altar.states.flags["powered"] = False
    altar.states.flags["_proximity"] = [{
        "source_type": "crystal", "within": 40.0,
        "state_name": "powered", "value": True,
        "clear_state_name": "powered", "clear_value": False,
    }]
    crystal = Entity(id="c1", type="crystal", body=EntityBody(x=200, y=100, radius=16))

    w.entities = [altar, crystal]
    sys = ProximitySystem()
    sys.tick(w, 0.016, 0.0)
    assert altar.states.get("powered") is False, "crystal hors rayon -> pas powered"

    crystal.body.x = 130.0  # dist centre = 30 ; +crystal.radius=16 -> 46 > within=40 ? 30 <= 40+16 = 56 oui
    sys.tick(w, 0.016, 0.0)
    assert altar.states.get("powered") is True, "crystal dans rayon -> powered"

    crystal.body.x = 300.0
    sys.tick(w, 0.016, 0.0)
    assert altar.states.get("powered") is False, "crystal parti -> clear"

    print("proximity_system: OK")
