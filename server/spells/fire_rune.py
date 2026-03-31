from __future__ import annotations

import math
import time
from typing import Any

from server.spells.types import ServerSpellDefinition


def cast_fire_rune(instance: Any, client_id: str, payload: dict[str, Any], modifiers: list[dict[str, Any]]) -> None:
    player = instance.players.get(client_id)
    if player is None or not player.get("alive", True):
        return

    try:
        raw_radius = float(payload.get("hitbox_radius", payload.get("texture_radius", instance.fire_rune_min_radius)))
    except (TypeError, ValueError):
        raw_radius = instance.fire_rune_min_radius
    radius = instance._clamp(raw_radius, instance.fire_rune_min_radius, instance.fire_rune_max_radius)

    params = instance._apply_server_spell_modifiers(
        spell_id="fire_rune",
        base_params={
            "damage_per_tick": instance.fire_rune_tick_damage,
            "tick_interval": instance.fire_rune_tick_interval,
            "duration": instance.fire_rune_duration,
            "cast_distance_bonus": 0.0,
        },
        modifiers=modifiers,
    )

    damage_per_tick = instance._clamp(float(params.get("damage_per_tick", instance.fire_rune_tick_damage)), 0.0, 80.0)
    tick_interval = instance._clamp(float(params.get("tick_interval", instance.fire_rune_tick_interval)), 0.05, 1.5)
    duration = instance._clamp(float(params.get("duration", instance.fire_rune_duration)), 0.15, 8.0)
    cast_distance_bonus = instance._clamp(float(params.get("cast_distance_bonus", 0.0)), 0.0, 220.0)
    radius_x, radius_y, ellipse_angle, velocity_x, velocity_y = _resolve_fire_geometry_from_params(
        base_radius=radius,
        params=params,
    )

    facing_x = float(player.get("facing_x", 1.0))
    facing_y = float(player.get("facing_y", 0.0))
    facing_norm = math.hypot(facing_x, facing_y)
    if facing_norm <= 1e-9:
        facing_x, facing_y = 1.0, 0.0
    else:
        facing_x /= facing_norm
        facing_y /= facing_norm

    cast_distance = max(24.0, max(radius_x, radius_y) + 10.0 + cast_distance_bonus)
    raw_x = float(player["x"]) + facing_x * cast_distance
    raw_y = float(player["y"]) + facing_y * cast_distance

    map_width, map_height = instance.map_data.get("size", [1280, 720])
    x = instance._clamp(raw_x, radius_x, max(radius_x, map_width - radius_x))
    y = instance._clamp(raw_y, radius_y, max(radius_y, map_height - radius_y))

    instance.active_spells.append(
        {
            "spell_id": "fire_rune",
            "owner_id": client_id,
            "x": x,
            "y": y,
            "hitbox_radius": radius,
            "hitbox_radius_x": radius_x,
            "hitbox_radius_y": radius_y,
            "ellipse_angle": ellipse_angle,
            "velocity_x": velocity_x,
            "velocity_y": velocity_y,
            "remaining": duration,
            "tick_interval": tick_interval,
            "damage_per_tick": damage_per_tick,
            "next_tick_at": time.time(),
            "modifiers": modifiers,
        }
    )


def tick_fire_rune(instance: Any, spell: dict[str, Any]) -> None:
    cx = float(spell["x"])
    cy = float(spell["y"])
    radius = float(spell.get("hitbox_radius", instance.fire_rune_min_radius))
    radius_x = max(1.0, float(spell.get("hitbox_radius_x", radius)))
    radius_y = max(1.0, float(spell.get("hitbox_radius_y", radius)))
    ellipse_angle = float(spell.get("ellipse_angle", 0.0))
    cos_angle = math.cos(ellipse_angle)
    sin_angle = math.sin(ellipse_angle)
    damage = max(0.0, float(spell.get("damage_per_tick", instance.fire_rune_tick_damage)))
    if damage <= 0.0:
        return

    enemy_hit_radius = instance.enemy_collision_size * 0.5
    broad_phase = max(radius_x, radius_y)
    for enemy in instance.enemies.values():
        if not enemy.get("alive", True):
            continue
        dx = enemy["x"] - cx
        dy = enemy["y"] - cy
        if math.hypot(dx, dy) > broad_phase + enemy_hit_radius:
            continue

        if abs(radius_x - radius_y) <= 1e-6:
            if dx * dx + dy * dy > (radius_x + enemy_hit_radius) ** 2:
                continue
        else:
            local_x = dx * cos_angle + dy * sin_angle
            local_y = -dx * sin_angle + dy * cos_angle
            rx = radius_x + enemy_hit_radius
            ry = radius_y + enemy_hit_radius
            if rx <= 1e-6 or ry <= 1e-6:
                continue
            norm = (local_x / rx) ** 2 + (local_y / ry) ** 2
            if norm > 1.0:
                continue

        enemy["health"] = max(0.0, enemy["health"] - damage)
        if enemy["health"] <= 0.0:
            enemy["alive"] = False
            enemy["vx"] = 0.0
            enemy["vy"] = 0.0
        enemy["last_update"] = time.time()


def _resolve_fire_geometry_from_params(
    *,
    base_radius: float,
    params: dict[str, float],
) -> tuple[float, float, float, float, float]:
    motion_x = float(params.get("motion_vector_x", 0.0))
    motion_y = float(params.get("motion_vector_y", 0.0))
    shape_pressure = max(0.0, float(params.get("shape_pressure", 0.0)))
    move_speed_bonus = max(0.0, float(params.get("move_speed_bonus", 0.0)))

    motion_magnitude = math.hypot(motion_x, motion_y)
    if motion_magnitude <= 1e-6:
        return base_radius, base_radius, 0.0, 0.0, 0.0

    direction_x = motion_x / motion_magnitude
    direction_y = motion_y / motion_magnitude
    elongation = _clamp(1.0 + 0.28 * shape_pressure + 0.22 * motion_magnitude, 1.0, 2.5)
    compression = _clamp(1.0 / max(1.0, 0.22 * shape_pressure + 0.30 * motion_magnitude), 0.45, 1.0)
    radius_x = max(1.0, base_radius * elongation)
    radius_y = max(1.0, base_radius * compression)
    speed = _clamp(move_speed_bonus + 90.0 * motion_magnitude, 0.0, 620.0)
    return (
        radius_x,
        radius_y,
        math.atan2(direction_y, direction_x),
        direction_x * speed,
        direction_y * speed,
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


FIRE_RUNE_SERVER_DEFINITION = ServerSpellDefinition(
    spell_id="fire_rune",
    cast_handler=cast_fire_rune,
    tick_handler=tick_fire_rune,
)
