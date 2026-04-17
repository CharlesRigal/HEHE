from __future__ import annotations

import math
import time
from typing import Any


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalize_direction(
    x: float,
    y: float,
    *,
    fallback: tuple[float, float] = (1.0, 0.0),
) -> tuple[float, float]:
    norm = math.hypot(x, y)
    if norm <= 1e-6:
        return fallback
    return x / norm, y / norm


def facing_direction(player: Any) -> tuple[float, float]:
    facing_x, facing_y = player.facing()
    return normalize_direction(float(facing_x), float(facing_y))


def resolve_player_direction(player: Any, payload: dict[str, Any]) -> tuple[float, float]:
    facing_x, facing_y = player.facing()
    dir_x = _safe_float(payload.get("direction_x", facing_x), float(facing_x))
    dir_y = _safe_float(payload.get("direction_y", facing_y), float(facing_y))
    return normalize_direction(dir_x, dir_y)


def apply_enemy_damage(enemy: dict[str, Any], damage: float, *, now: float | None = None) -> None:
    if damage <= 0.0 or not enemy.get("alive", True):
        return

    enemy["health"] = max(0.0, float(enemy.get("health", 0.0)) - float(damage))
    if enemy["health"] <= 0.0:
        enemy["alive"] = False
        enemy["vx"] = 0.0
        enemy["vy"] = 0.0

    enemy["last_update"] = time.time() if now is None else now
