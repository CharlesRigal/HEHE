"""
effect_registry.py -- Systeme d'effets non-degat pour le serveur.

Les effets s'appliquent aux entites (ennemis, joueurs) ou aux zones (terrain).
Chaque effet a 3 callbacks : apply (debut), tick (par intervalle), remove (fin).
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ActiveEffect:
    effect_id: str           # "freeze" | "create_terrain" | "transmute" | "push"
    target_type: str         # "entity" | "area"
    target_id: str           # enemy/player ID ou "terrain_<x>_<y>"
    owner_id: str            # caster
    remaining: float         # secondes restantes
    tick_interval: float     # secondes entre ticks (0 = pas de tick)
    next_tick_at: float      # timestamp du prochain tick
    params: dict[str, Any] = field(default_factory=dict)


# Type pour les callbacks d'effet
EffectCallback = Callable[[Any, ActiveEffect], None]  # (instance, effect) -> None


class EffectRegistry:
    def __init__(self):
        self._apply: dict[str, EffectCallback] = {}
        self._tick: dict[str, EffectCallback] = {}
        self._remove: dict[str, EffectCallback] = {}

    def register(
        self,
        effect_id: str,
        apply_fn: EffectCallback,
        tick_fn: Optional[EffectCallback] = None,
        remove_fn: Optional[EffectCallback] = None,
    ) -> None:
        self._apply[effect_id] = apply_fn
        if tick_fn:
            self._tick[effect_id] = tick_fn
        if remove_fn:
            self._remove[effect_id] = remove_fn

    def apply_effect(self, instance: Any, effect: ActiveEffect) -> None:
        fn = self._apply.get(effect.effect_id)
        if fn:
            fn(instance, effect)

    def tick_effect(self, instance: Any, effect: ActiveEffect) -> None:
        fn = self._tick.get(effect.effect_id)
        if fn:
            fn(instance, effect)

    def remove_effect(self, instance: Any, effect: ActiveEffect) -> None:
        fn = self._remove.get(effect.effect_id)
        if fn:
            fn(instance, effect)


# ---------------------------------------------------------------------------
# Effets built-in
# ---------------------------------------------------------------------------

def _apply_freeze(instance: Any, effect: ActiveEffect) -> None:
    """Gele une entite : speed_multiplier = 0."""
    target = instance.enemies.get(effect.target_id) or instance.players.get(effect.target_id)
    if target and target.get("alive", True):
        target["frozen"] = True
        target["_original_speed_mult"] = target.get("speed_multiplier", 1.0)
        target["speed_multiplier"] = 0.0
        logging.debug(f"Freeze applied to {effect.target_id}")


def _remove_freeze(instance: Any, effect: ActiveEffect) -> None:
    """Degele une entite."""
    target = instance.enemies.get(effect.target_id) or instance.players.get(effect.target_id)
    if target:
        target["frozen"] = False
        target["speed_multiplier"] = target.pop("_original_speed_mult", 1.0)
        logging.debug(f"Freeze removed from {effect.target_id}")


def _apply_create_terrain(instance: Any, effect: ActiveEffect) -> None:
    """Cree un objet de terrain temporaire."""
    terrain = {
        "id": f"terrain_{effect.owner_id}_{int(time.time()*1000)}",
        "type": effect.params.get("terrain_type", "wall"),
        "x": effect.params.get("x", 0.0),
        "y": effect.params.get("y", 0.0),
        "w": effect.params.get("width", 40.0),
        "h": effect.params.get("length", 80.0),
        "traversable": effect.params.get("traversable", False),
        "remaining": effect.remaining,
        "owner_id": effect.owner_id,
    }
    instance.active_terrain.append(terrain)
    logging.debug(f"Terrain created: {terrain['type']} at ({terrain['x']:.0f}, {terrain['y']:.0f})")


def _tick_create_terrain(instance: Any, effect: ActiveEffect) -> None:
    """Decremente la duree du terrain."""
    terrain_id_prefix = f"terrain_{effect.owner_id}_"
    for terrain in instance.active_terrain:
        if terrain["id"].startswith(terrain_id_prefix):
            terrain["remaining"] = effect.remaining


def _remove_create_terrain(instance: Any, effect: ActiveEffect) -> None:
    """Supprime le terrain temporaire."""
    terrain_id_prefix = f"terrain_{effect.owner_id}_"
    instance.active_terrain = [
        t for t in instance.active_terrain
        if not t["id"].startswith(terrain_id_prefix)
    ]
    logging.debug(f"Terrain removed for {effect.owner_id}")


def _apply_transmute(instance: Any, effect: ActiveEffect) -> None:
    """Transmute un objet map : change son materiau."""
    target_x = effect.params.get("x", 0.0)
    target_y = effect.params.get("y", 0.0)
    radius = effect.params.get("radius", 50.0)
    to_material = effect.params.get("to_material", "dust")

    objects = instance.map_data.get("objects", [])
    for obj in objects:
        points = obj.get("points", [])
        if len(points) < 2:
            continue
        # Centre de l'objet
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        dist = ((cx - target_x) ** 2 + (cy - target_y) ** 2) ** 0.5
        if dist < radius:
            obj["material"] = to_material
            if to_material == "dust":
                obj["_original_points"] = list(obj["points"])
                obj["points"] = []  # rend l'objet non-collidable
            logging.debug(f"Transmuted object at ({cx:.0f}, {cy:.0f}) to {to_material}")


def _apply_push(instance: Any, effect: ActiveEffect) -> None:
    """Pousse les entites dans la zone."""
    cx = effect.params.get("x", 0.0)
    cy = effect.params.get("y", 0.0)
    radius = effect.params.get("radius", 60.0)
    push_x = effect.params.get("push_x", 0.0)
    push_y = effect.params.get("push_y", 0.0)
    push_force = effect.params.get("push_force", 200.0)

    for enemy in instance.enemies.values():
        if not enemy.get("alive", True):
            continue
        dx = enemy["x"] - cx
        dy = enemy["y"] - cy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < radius:
            enemy["x"] += push_x * push_force * 0.05
            enemy["y"] += push_y * push_force * 0.05


# ---------------------------------------------------------------------------
# Registre global
# ---------------------------------------------------------------------------

EFFECT_REGISTRY = EffectRegistry()
EFFECT_REGISTRY.register("freeze", _apply_freeze, remove_fn=_remove_freeze)
EFFECT_REGISTRY.register("create_terrain", _apply_create_terrain, _tick_create_terrain, _remove_create_terrain)
EFFECT_REGISTRY.register("transmute", _apply_transmute)
EFFECT_REGISTRY.register("push", _apply_push)
