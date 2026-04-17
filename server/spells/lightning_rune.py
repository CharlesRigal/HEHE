from __future__ import annotations

import time
from typing import Any

from server.spells.runtime import apply_enemy_damage, resolve_player_direction
from server.spells.types import ServerSpellDefinition

_BASE_RADIUS = 90.0
_BASE_DAMAGE = 9.0
_BASE_TICK = 0.12
_BASE_DURATION = 1.4


def cast_lightning_rune(
    instance: Any,
    client_id: str,
    payload: dict[str, Any],
    modifiers: list[dict[str, Any]],
) -> None:
    player = instance.players.get(client_id)
    if player is None or not player.is_alive():
        return

    power = float(payload.get("power", 0.5))
    radius = instance._clamp(_BASE_RADIUS * (0.4 + power * 1.2), 20.0, 260.0)
    damage = _BASE_DAMAGE * (0.5 + power)
    tick_interval = _BASE_TICK
    duration = _BASE_DURATION

    if payload.get("unstable"):
        tick_interval *= 0.55
        duration *= 0.65
        damage *= 1.25
    if payload.get("focused"):
        radius *= 0.65
        damage *= 1.4

    # Direction : spec > facing joueur
    dir_x, dir_y = resolve_player_direction(player, payload)

    map_w, map_h = instance.map_data.get("size", [1280, 720])
    cast_dist = max(24.0, radius + 10.0)
    player_x, player_y = player.position()
    x = instance._clamp(player_x + dir_x * cast_dist, radius, map_w - radius)
    y = instance._clamp(player_y + dir_y * cast_dist, radius, map_h - radius)

    instance.active_spells.append({
        "spell_id":        "lightning_rune",
        "owner_id":        client_id,
        "x":               x,
        "y":               y,
        "hitbox_radius":   radius,
        "hitbox_radius_x": radius,
        "hitbox_radius_y": radius,
        "ellipse_angle":   0.0,
        "velocity_x":      0.0,
        "velocity_y":      0.0,
        "remaining":       duration,
        "tick_interval":   tick_interval,
        "damage_per_tick": damage,
        "next_tick_at":    time.time(),
    })


def tick_lightning_rune(instance: Any, spell: dict[str, Any]) -> None:
    cx = float(spell["x"])
    cy = float(spell["y"])
    radius = max(1.0, float(spell.get("hitbox_radius", _BASE_RADIUS)))
    damage = max(0.0, float(spell.get("damage_per_tick", _BASE_DAMAGE)))
    if damage <= 0.0:
        return

    enemy_hr = instance.enemy_collision_size * 0.5
    r2 = (radius + enemy_hr) ** 2
    for enemy in instance.enemies.values():
        if not enemy.get("alive", True):
            continue
        dx = enemy["x"] - cx
        dy = enemy["y"] - cy
        if dx * dx + dy * dy > r2:
            continue
        apply_enemy_damage(enemy, damage)


LIGHTNING_RUNE_SERVER_DEFINITION = ServerSpellDefinition(
    spell_id="lightning_rune",
    cast_handler=cast_lightning_rune,
    tick_handler=tick_lightning_rune,
)
