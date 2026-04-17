from __future__ import annotations

import math
import time
from typing import Any

from server.spells.runtime import apply_enemy_damage, resolve_player_direction
from server.spells.types import ServerSpellDefinition

_BASE_SPEED = 400.0
_BASE_RADIUS = 10.0
_BASE_DURATION = 1.8
_BASE_DAMAGE = 40.0


def cast_fire_projectile(
    instance: Any,
    client_id: str,
    payload: dict[str, Any],
    modifiers: list[dict[str, Any]],
) -> None:
    player = instance.players.get(client_id)
    if player is None or not player.is_alive():
        return

    # Direction : spec > facing joueur
    dir_x, dir_y = resolve_player_direction(player, payload)

    power = float(payload.get("power", 0.5))
    radius = _BASE_RADIUS + power * 18.0
    damage = _BASE_DAMAGE * (0.5 + power)
    speed = _BASE_SPEED
    duration = _BASE_DURATION

    if payload.get("focused"):
        radius *= 0.65
        damage *= 1.5
    if payload.get("unstable"):
        speed *= 1.35
        duration *= 0.65
        damage *= 0.9

    player_x, player_y = player.position()
    x = player_x + dir_x * (radius + 20.0)
    y = player_y + dir_y * (radius + 20.0)

    instance.active_spells.append({
        "spell_id":       "fire_projectile",
        "owner_id":       client_id,
        "x":              x,
        "y":              y,
        "velocity_x":     dir_x * speed,
        "velocity_y":     dir_y * speed,
        "hitbox_radius":  radius,
        "hitbox_radius_x": radius,
        "hitbox_radius_y": radius,
        "ellipse_angle":  0.0,
        "remaining":      duration,
        "tick_interval":  0.05,
        "damage_per_tick": 0.0,
        "impact_damage":  damage,
        "next_tick_at":   time.time(),
        "hit_once":       False,
    })


def tick_fire_projectile(instance: Any, spell: dict[str, Any]) -> None:
    if spell.get("hit_once"):
        spell["remaining"] = 0.0
        return

    cx = float(spell["x"])
    cy = float(spell["y"])
    radius = max(1.0, float(spell.get("hitbox_radius", _BASE_RADIUS)))
    damage = max(0.0, float(spell.get("impact_damage", _BASE_DAMAGE)))

    enemy_hr = instance.enemy_collision_size * 0.5
    for enemy in instance.enemies.values():
        if not enemy.get("alive", True):
            continue
        dx = enemy["x"] - cx
        dy = enemy["y"] - cy
        if math.hypot(dx, dy) > radius + enemy_hr:
            continue

        apply_enemy_damage(enemy, damage)
        spell["hit_once"] = True
        spell["remaining"] = 0.0
        return


FIRE_PROJECTILE_SERVER_DEFINITION = ServerSpellDefinition(
    spell_id="fire_projectile",
    cast_handler=cast_fire_projectile,
    tick_handler=tick_fire_projectile,
)
