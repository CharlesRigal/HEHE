"""Entites interactives : cristaux, autels, plaques, portes.

Chargement depuis YAML :

  interactive:
    - id: crystal_small
      type: crystal
      position: [500, 600]
      radius: 16
      mass: 1.0
      state: { lifted: false }

Aucune entite ne reagit a un element nomme (README, M0). Les entites
subissent le monde par les forces de la grille (server/world) et les
regles de proximite (ProximitySystem).

Types fournis :
  crystal        : mobile, deplace par les courants d'element
  altar          : statique, 'powered' si un cristal est dans son rayon
  pressure_plate : etat 'pressed'
  door           : etat 'open'
"""
from __future__ import annotations

from typing import Any

from server.entities.components import Entity, EntityBody, EntityStates


def build_entity(config: dict) -> Entity:
    """Construit une Entity depuis un dict YAML."""
    entity_id = str(config.get("id", "entity"))
    entity_type = str(config.get("type", "prop"))
    pos = config.get("position", [0.0, 0.0])
    radius = float(config.get("radius", 20.0))
    mass = float(config.get("mass", 1.0))
    _static_types = ("door", "altar")
    static = bool(config.get("static", entity_type in _static_types))

    body = EntityBody(
        x=float(pos[0]), y=float(pos[1]),
        mass=mass, static=static, radius=radius,
    )
    states = EntityStates(flags=dict(config.get("state", {}) or {}))
    entity = Entity(id=entity_id, type=entity_type, body=body, states=states)
    _apply_type_defaults(entity)
    return entity


def _apply_type_defaults(entity: Entity) -> None:
    """Applique les defauts implicites par type."""
    if entity.type == "pressure_plate":
        entity.states.flags.setdefault("pressed", False)
    elif entity.type == "door":
        entity.states.flags.setdefault("open", False)
    elif entity.type == "crystal":
        entity.states.flags.setdefault("lifted", False)
    elif entity.type == "altar":
        entity.states.flags.setdefault("powered", False)
        entity.body.static = True
        # Regle de proximite : un cristal pose dessus = altar powered
        entity.states.flags.setdefault("_proximity", [{
            "source_type": "crystal",
            "within": entity.body.radius + 4.0,
            "state_name": "powered", "value": True,
            "clear_state_name": "powered", "clear_value": False,
        }])


def entity_public_state(entity: Entity) -> dict[str, Any]:
    """Projection reseau (sans les flags internes prefixes par '_')."""
    visible = {k: v for k, v in entity.states.flags.items() if not k.startswith("_")}
    return {
        "id": entity.id,
        "type": entity.type,
        "x": round(entity.body.x, 1),
        "y": round(entity.body.y, 1),
        "r": round(entity.body.radius, 1),
        "state": visible,
    }


if __name__ == "__main__":
    crystal = build_entity({"id": "c1", "type": "crystal", "position": [10.0, 10.0]})
    assert crystal.states.get("lifted") is False
    assert not crystal.body.static

    altar = build_entity({"id": "a1", "type": "altar", "position": [0.0, 0.0]})
    assert altar.body.static
    assert entity_public_state(altar)["state"] == {"powered": False}

    print("interactive: OK")
