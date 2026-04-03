"""Sort parametrique unique.

Au lieu de N implementations discretes (fire_rune, fire_projectile, ...),
ce module gere TOUS les sorts via des proprietes continues derivees de la
SpellSpec.  Chaque dessin produit un point unique dans un espace continu
de sorts.

Comportement determine par les proprietes :
- speed > 0        → le sort se deplace (projectile)
- tick_damage > 0   → degats en zone par tick (rune/area)
- impact_damage > 0 → degats d'impact au premier contact
- cone_half_angle>0 → degats en cone et non en cercle
- axis              → hitbox elliptique (mur)
"""

from __future__ import annotations

import math
import time
from typing import Any

from server.magic.spell_spec import ServerSpellSpec
from server.spells.types import ServerSpellDefinition


# ─── Element modifiers ─────────────────────────────────────────────
# Chaque element a un "profil" qui teinte le sort de maniere unique.
# damage : multiplicateur de degats
# duration : multiplicateur de duree
# tick_rate : multiplicateur de tick_interval (< 1 = plus rapide)
# radius : multiplicateur de rayon
_ELEMENT_MODS: dict[str, dict[str, float]] = {
    "fire":      {"damage": 1.0,  "duration": 1.0,  "tick_rate": 1.0,  "radius": 1.0},
    "lightning": {"damage": 1.15, "duration": 0.75, "tick_rate": 0.6,  "radius": 0.9},
    "plasma":    {"damage": 1.3,  "duration": 0.6,  "tick_rate": 0.5,  "radius": 0.85},
    "inferno":   {"damage": 1.1,  "duration": 1.4,  "tick_rate": 0.9,  "radius": 1.3},
    "storm":     {"damage": 1.0,  "duration": 0.85, "tick_rate": 0.45, "radius": 1.2},
}

_DEFAULT_MOD: dict[str, float] = {"damage": 1.0, "duration": 1.0, "tick_rate": 1.0, "radius": 1.0}

# ─── Constantes de base ────────────────────────────────────────────
_BASE_DAMAGE = 12.0
_BASE_TICK_INTERVAL = 0.20
_MAX_SPEED = 500.0
_MIN_RADIUS = 8.0
_MAX_RADIUS = 300.0


def cast_parametric_spell(
    instance: Any,
    client_id: str,
    spec: ServerSpellSpec,
) -> None:
    """Lance un sort parametrique derive directement de la spec."""
    player = instance.players.get(client_id)
    if player is None or not player.get("alive", True):
        return

    element = spec.element or "fire"
    emod = _ELEMENT_MODS.get(element, _DEFAULT_MOD)

    power = spec.power if spec.power is not None else 0.5
    intensity = max(1.0, spec.intensity)
    has_movement = spec.speed > 0.05
    has_area = spec.spread > 0.05 or spec.shape == "cone"
    has_wall = spec.axis is not None

    # ─── Degats de base (scales avec power et intensite/complexite) ──
    complexity_bonus = 1.0 + 0.12 * max(0.0, intensity - 1.0)
    base_damage = _BASE_DAMAGE * (0.5 + power) * complexity_bonus * emod["damage"]

    # ─── Rayon ───────────────────────────────────────────────────────
    if has_movement:
        radius = (10.0 + power * 22.0) * emod["radius"]
    else:
        radius = (20.0 + power * 140.0) * emod["radius"]

    # ─── Degats d'impact et de zone ──────────────────────────────────
    # Le blend se fait naturellement : si le sort bouge ET a du rayon,
    # il fait les deux types de degats.
    if has_movement and not has_area:
        # Projectile pur : gros impact, pas de tick
        impact_damage = base_damage * 2.5
        tick_damage = 0.0
    elif has_movement and has_area:
        # Projectile + zone : impact moyen + tick moyen (boule mobile)
        impact_damage = base_damage * 1.5
        tick_damage = base_damage * 0.7
        radius *= 1.6  # un peu plus large car c'est une boule
    elif not has_movement and has_area:
        # Zone conique stationnaire
        impact_damage = 0.0
        tick_damage = base_damage * 1.0
    else:
        # Rune stationnaire classique
        impact_damage = 0.0
        tick_damage = base_damage * 1.0

    radius = _clamp(radius, _MIN_RADIUS, _MAX_RADIUS)

    # ─── Vitesse ─────────────────────────────────────────────────────
    speed = spec.speed * _MAX_SPEED if has_movement else 0.0

    # ─── Duree ───────────────────────────────────────────────────────
    base_duration = 2.0 if has_movement else 2.5
    duration = base_duration * (0.5 + spec.duration_bonus) * emod["duration"]
    duration = _clamp(duration, 0.3, 10.0)

    # ─── Tick interval ───────────────────────────────────────────────
    tick_interval = _BASE_TICK_INTERVAL * emod["tick_rate"]
    tick_interval = _clamp(tick_interval, 0.04, 1.0)

    # ─── Modifieurs focused / unstable ───────────────────────────────
    if spec.focused:
        radius *= 0.6
        impact_damage *= 1.4
        tick_damage *= 1.3
    if spec.unstable:
        speed *= 1.35
        tick_damage *= 1.2
        duration *= 0.7

    # ─── Direction ───────────────────────────────────────────────────
    if spec.direction is not None:
        dir_x, dir_y = spec.direction
    else:
        dir_x = float(player.get("facing_x", 1.0))
        dir_y = float(player.get("facing_y", 0.0))
    norm = math.hypot(dir_x, dir_y)
    if norm > 1e-6:
        dir_x /= norm
        dir_y /= norm
    else:
        dir_x, dir_y = 1.0, 0.0

    # ─── Cone ────────────────────────────────────────────────────────
    cone_half_angle = 0.0
    if spec.spread > 0.05:
        # spread 0.1 → 18deg, spread 1.0 → 90deg demi-angle
        cone_half_angle = spec.spread * (math.pi / 2.0)

    # ─── Hitbox elliptique (mur) ─────────────────────────────────────
    radius_x = radius
    radius_y = radius
    ellipse_angle = 0.0
    if has_wall and spec.axis is not None:
        ax, ay = spec.axis
        axis_len = math.hypot(ax, ay)
        if axis_len > 1e-6:
            elongation = _clamp(1.0 + axis_len * 0.008, 1.2, 3.0)
            radius_x = radius * elongation
            radius_y = radius / elongation
            ellipse_angle = math.atan2(ay, ax)

    # ─── Position de spawn ───────────────────────────────────────────
    cast_dist = max(24.0, max(radius_x, radius_y) + 10.0)
    raw_x = float(player["x"]) + dir_x * cast_dist
    raw_y = float(player["y"]) + dir_y * cast_dist

    map_w, map_h = instance.map_data.get("size", [1280, 720])
    x = _clamp(raw_x, radius_x, max(radius_x, map_w - radius_x))
    y = _clamp(raw_y, radius_y, max(radius_y, map_h - radius_y))

    # ─── Pierce : le sort continue apres impact si c'est un blend ───
    pierce = has_movement and tick_damage > 0.1

    instance.active_spells.append({
        "spell_id":         "parametric",
        "owner_id":         client_id,
        "element":          element,
        "x":                x,
        "y":                y,
        "velocity_x":       dir_x * speed,
        "velocity_y":       dir_y * speed,
        "hitbox_radius":    radius,
        "hitbox_radius_x":  radius_x,
        "hitbox_radius_y":  radius_y,
        "ellipse_angle":    ellipse_angle,
        "remaining":        duration,
        "tick_interval":    tick_interval,
        "tick_damage":      tick_damage,
        "impact_damage":    impact_damage,
        "next_tick_at":     time.time(),
        "cone_half_angle":  cone_half_angle,
        "spell_dir_x":      dir_x,
        "spell_dir_y":      dir_y,
        "pierce":           pierce,
        "hit_targets":      [],
    })


def tick_parametric_spell(instance: Any, spell: dict[str, Any]) -> None:
    """Tick handler unifie pour tous les sorts parametriques."""
    cx = float(spell["x"])
    cy = float(spell["y"])
    radius = max(1.0, float(spell.get("hitbox_radius", _MIN_RADIUS)))
    radius_x = max(1.0, float(spell.get("hitbox_radius_x", radius)))
    radius_y = max(1.0, float(spell.get("hitbox_radius_y", radius)))
    ellipse_angle = float(spell.get("ellipse_angle", 0.0))
    tick_damage = max(0.0, float(spell.get("tick_damage", 0.0)))
    impact_damage = max(0.0, float(spell.get("impact_damage", 0.0)))
    cone_half_angle = float(spell.get("cone_half_angle", 0.0))
    spell_dir_x = float(spell.get("spell_dir_x", 1.0))
    spell_dir_y = float(spell.get("spell_dir_y", 0.0))
    pierce = spell.get("pierce", False)
    hit_targets: list[str] = spell.get("hit_targets", [])

    if tick_damage <= 0.0 and impact_damage <= 0.0:
        return

    cos_angle = math.cos(ellipse_angle)
    sin_angle = math.sin(ellipse_angle)
    enemy_hr = instance.enemy_collision_size * 0.5
    broad_phase = max(radius_x, radius_y)

    for enemy_id, enemy in instance.enemies.items():
        if not enemy.get("alive", True):
            continue

        dx = enemy["x"] - cx
        dy = enemy["y"] - cy
        dist = math.hypot(dx, dy)

        if dist > broad_phase + enemy_hr:
            continue

        # ── Hitbox elliptique ──
        if abs(radius_x - radius_y) > 1e-6:
            local_x = dx * cos_angle + dy * sin_angle
            local_y = -dx * sin_angle + dy * cos_angle
            rx = radius_x + enemy_hr
            ry = radius_y + enemy_hr
            if rx <= 1e-6 or ry <= 1e-6:
                continue
            if (local_x / rx) ** 2 + (local_y / ry) ** 2 > 1.0:
                continue
        else:
            if dist > radius_x + enemy_hr:
                continue

        # ── Cone check ──
        if cone_half_angle > 0.01 and dist > 1e-6:
            dot = dx * spell_dir_x + dy * spell_dir_y
            cos_to_enemy = dot / dist
            if cos_to_enemy < math.cos(cone_half_angle):
                continue

        # ── Determiner les degats ──
        damage = 0.0

        # Impact (une seule fois par cible)
        if impact_damage > 0.0 and enemy_id not in hit_targets:
            damage += impact_damage
            hit_targets.append(enemy_id)
            if not pierce:
                spell["remaining"] = 0.0

        # Tick damage (zone continue)
        if tick_damage > 0.0:
            damage += tick_damage

        if damage <= 0.0:
            continue

        enemy["health"] = max(0.0, enemy["health"] - damage)
        if enemy["health"] <= 0.0:
            enemy["alive"] = False
            enemy["vx"] = 0.0
            enemy["vy"] = 0.0
        enemy["last_update"] = time.time()

        # Sort non-pierce : s'arrete au premier impact
        if spell["remaining"] <= 0.0:
            return


PARAMETRIC_SPELL_DEFINITION = ServerSpellDefinition(
    spell_id="parametric",
    cast_handler=lambda inst, cid, payload, mods: None,  # pas utilise directement
    tick_handler=tick_parametric_spell,
)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
