"""Entites interactives Phase 3 : torches, brasiers, plaques, portes.

Chargement depuis YAML :

  interactive:
    - id: torch_01
      type: torch
      position: [800, 400]
      radius: 18
      state: { lit: false }
      affinities: { fire: -1.0, water: 0.5 }
      reactions:
        - trigger: { element: fire, min_intensity: 0.2 }
          effect: { state: lit, value: true }

Les reactions sont declenchees par les StateChangeEffect du runtime d'effets
(voir `server/effects/runtime.py::tick_state_change_effect`). Le runtime
emet l'empreinte elementaire `touched_by_<element>` : ce module la convertit
en mutation d'etat via la regle `reactions[*].trigger`.

Types fournis :
  torch          : s'allume si feu (ou selon reactions[])
  brazier        : statique, lit=true par defaut
  pressure_plate : change 'pressed' selon masse au dessus (Phase 2+)
  door           : 'open' commute la collidability
"""
from __future__ import annotations

import logging
from typing import Any

from server.entities.components import (
    Entity,
    EntityAffinities,
    EntityBody,
    EntityStates,
)


def _as_reaction(raw: dict) -> dict:
    """Normalise une entree 'reactions' YAML."""
    trigger = raw.get("trigger", {}) or {}
    effect = raw.get("effect", {}) or {}
    return {
        "element": trigger.get("element"),
        "min_intensity": float(trigger.get("min_intensity", 0.0)),
        "state_name": str(effect.get("state", "")),
        "value": effect.get("value"),
    }


def build_entity(config: dict) -> Entity:
    """Construit une Entity depuis un dict YAML."""
    entity_id = str(config.get("id", "entity"))
    entity_type = str(config.get("type", "prop"))
    pos = config.get("position", [0.0, 0.0])
    radius = float(config.get("radius", 20.0))
    mass = float(config.get("mass", 1.0))
    # Types static par defaut (lockable si la config ne precise pas)
    _static_types = ("torch", "brazier", "door", "altar")
    static = bool(config.get("static", entity_type in _static_types))

    body = EntityBody(
        x=float(pos[0]), y=float(pos[1]),
        mass=mass, static=static, radius=radius,
    )

    affinities = EntityAffinities(
        weights=dict(config.get("affinities", {}) or {})
    )

    initial_state = dict(config.get("state", {}) or {})
    states = EntityStates(flags=initial_state)

    entity = Entity(
        id=entity_id, type=entity_type,
        body=body, affinities=affinities, states=states,
    )

    # Reactions
    reactions = [_as_reaction(r) for r in (config.get("reactions") or [])]
    entity.states.flags.setdefault("_reactions", reactions)

    # Defauts par type (utiles si YAML minimal)
    _apply_type_defaults(entity)

    return entity


def _apply_type_defaults(entity: Entity) -> None:
    """Applique les defauts implicites par type."""
    if entity.type == "torch":
        entity.states.flags.setdefault("lit", False)
        entity.affinities.weights.setdefault("fire", -1.0)
        reactions = entity.states.flags["_reactions"]
        if not reactions:
            reactions.append({
                "element": "fire", "min_intensity": 0.1,
                "state_name": "lit", "value": True,
            })
    elif entity.type == "brazier":
        entity.states.flags.setdefault("lit", True)
        entity.body.static = True
    elif entity.type == "pressure_plate":
        entity.states.flags.setdefault("pressed", False)
    elif entity.type == "door":
        entity.states.flags.setdefault("open", False)
    elif entity.type == "crystal":
        # Liftable par defaut. Si config.yaml surcharge avec static=True,
        # on respecte. Sinon mobile pour levitation.
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


def apply_state_change_to_entity(
    entity: Entity,
    element: str,
    intensity: float,
) -> bool:
    """Applique les reactions matchantes d'une entite. True si au moins une change."""
    reactions = entity.states.flags.get("_reactions", [])
    changed = False
    for reaction in reactions:
        if reaction["element"] and reaction["element"] != element:
            continue
        if intensity < reaction["min_intensity"]:
            continue
        if not reaction["state_name"]:
            continue
        if entity.set_state(reaction["state_name"], reaction["value"]):
            changed = True
            logging.debug(
                f"[{entity.id}] reaction fired: {reaction['state_name']}={reaction['value']} "
                f"(element={element}, intensity={intensity:.2f})"
            )
    return changed


def entity_public_state(entity: Entity) -> dict[str, Any]:
    """Projection reseau (sans _reactions internes)."""
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
    torch_cfg = {
        "id": "t1",
        "type": "torch",
        "position": [500.0, 500.0],
        "radius": 18.0,
    }
    torch = build_entity(torch_cfg)
    assert torch.states.get("lit") is False
    assert torch.affinities.weight_for("fire") == -1.0
    assert apply_state_change_to_entity(torch, "fire", 0.5)
    assert torch.states.get("lit") is True
    # Meme stimulus : rien a changer
    assert not apply_state_change_to_entity(torch, "fire", 0.5)

    # Water ne l'allume pas
    torch2 = build_entity(torch_cfg)
    assert not apply_state_change_to_entity(torch2, "water", 0.9)
    assert torch2.states.get("lit") is False

    # Intensite insuffisante
    torch3 = build_entity(torch_cfg)
    assert not apply_state_change_to_entity(torch3, "fire", 0.05)

    # Reactions YAML explicites
    brazier = build_entity({
        "id": "b1", "type": "brazier",
        "position": [0.0, 0.0],
    })
    assert brazier.states.get("lit") is True
    assert brazier.body.static

    door = build_entity({
        "id": "d1", "type": "door",
        "position": [100.0, 100.0],
        "state": {"open": False},
        "reactions": [
            {"trigger": {"element": "lightning", "min_intensity": 0.3},
             "effect": {"state": "open", "value": True}},
        ],
    })
    assert apply_state_change_to_entity(door, "lightning", 0.5)
    assert door.states.get("open") is True

    pub = entity_public_state(torch)
    assert pub["state"] == {"lit": True}
    assert "_reactions" not in pub["state"]

    print("interactive: OK")
