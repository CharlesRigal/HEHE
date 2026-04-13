"""Sort parametrique unique.

Au lieu de N implementations discretes (fire_rune, fire_projectile, ...),
ce module gere TOUS les sorts via des proprietes continues derivees de la
SpellSpec.  Chaque dessin produit un point unique dans un espace continu.

Comportement derive des proprietes continues (pas de switch hardcode) :
  is_wall : compression > 1.5 ET axe present
  is_pool : spread > 0.3 ET fade_rate > 0 ET pas de movement ET compression < 1.0
  projectile : speed > 0.05
  aoe : spread > 0.05 (cone si direction explicite)
  stationary : fallback
"""

from __future__ import annotations

import math
import time
from typing import Any

from server.magic.spell_spec import ServerSpellSpec
from server.spells.types import ServerSpellDefinition


# ─── Element modifiers ─────────────────────────────────────────────
_ELEMENT_MODS: dict[str, dict[str, float]] = {
    "fire":      {"damage": 1.0,  "duration": 1.0,  "tick_rate": 1.0,  "radius": 1.0},
    "lightning": {"damage": 1.15, "duration": 0.75, "tick_rate": 0.6,  "radius": 0.9},
    "plasma":    {"damage": 1.3,  "duration": 0.6,  "tick_rate": 0.5,  "radius": 0.85},
    "inferno":   {"damage": 1.1,  "duration": 1.4,  "tick_rate": 0.9,  "radius": 1.3},
    "storm":     {"damage": 1.0,  "duration": 0.85, "tick_rate": 0.45, "radius": 1.2},
}
_DEFAULT_MOD: dict[str, float] = {"damage": 1.0, "duration": 1.0, "tick_rate": 1.0, "radius": 1.0}

# ─── Constantes ────────────────────────────────────────────────────
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

    element = spec.element or "neutral"
    emod = _ELEMENT_MODS.get(element, _DEFAULT_MOD)

    power = spec.power if spec.power is not None else 0.5
    intensity = max(1.0, spec.intensity)
    dur_bonus = spec.duration_bonus

    # ─── Behavior emerge des proprietes continues ──────────────────
    has_movement = spec.speed > 0.05
    is_wall = spec.compression > 1.5 and spec.axis is not None
    is_pool = (
        spec.spread > 0.3
        and spec.fade_rate > 0.0
        and not has_movement
        and spec.compression < 1.0
    )
    has_area = spec.spread > 0.05 or spec.shape == "cone"

    # ─── Complexite / degats de base ─────────────────────────────
    complexity_bonus = 1.0 + 0.12 * max(0.0, intensity - 1.0)
    base_damage = _BASE_DAMAGE * (0.5 + power) * complexity_bonus * emod["damage"]

    # ─── Rayon ───────────────────────────────────────────────────
    if has_movement:
        radius = (10.0 + power * 22.0) * emod["radius"]
    elif is_wall:
        radius = (15.0 + power * 60.0) * emod["radius"]
    else:
        radius = (20.0 + power * 140.0) * emod["radius"]

    # ─── Degats d'impact et de zone ──────────────────────────────
    if has_movement and not has_area:
        impact_damage = base_damage * 2.5
        tick_damage = 0.0
    elif has_movement and has_area:
        impact_damage = base_damage * 1.5
        tick_damage = base_damage * 0.7
        radius *= 1.6
    elif is_pool:
        impact_damage = 0.0
        tick_damage = base_damage * 0.6   # plus doux mais plus long
    elif not has_movement and has_area:
        impact_damage = 0.0
        tick_damage = base_damage * 1.0
    else:
        impact_damage = 0.0
        tick_damage = base_damage * 1.0

    radius = _clamp(radius, _MIN_RADIUS, _MAX_RADIUS)

    # ─── Vitesse ─────────────────────────────────────────────────
    speed = spec.speed * _MAX_SPEED if has_movement else 0.0

    # ─── Duree (par type emergent) ────────────────────────────────
    base_dur = 2.0 if has_movement else 2.5
    if is_wall:
        duration = _clamp(base_dur * (1.0 + dur_bonus * 4.0), 3.0, 30.0)
    elif is_pool:
        duration = _clamp(base_dur * (0.5 + dur_bonus), 2.0, 15.0)
    else:
        duration = _clamp(base_dur * (0.5 + dur_bonus), 0.3, 10.0)
    duration *= emod["duration"]

    # ─── Tick interval ───────────────────────────────────────────
    tick_interval = _BASE_TICK_INTERVAL * emod["tick_rate"]
    tick_interval = _clamp(tick_interval, 0.04, 1.0)

    # ─── Focused / unstable ───────────────────────────────────────
    if spec.focused:
        radius *= 0.6
        impact_damage *= 1.4
        tick_damage *= 1.3
    if spec.unstable:
        speed *= 1.35
        tick_damage *= 1.2
        duration *= 0.7

    # ─── Direction ───────────────────────────────────────────────
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

    # ─── Cone ────────────────────────────────────────────────────
    cone_half_angle = 0.0
    if spec.spread > 0.05:
        cone_half_angle = spec.spread * (math.pi / 2.0)

    # ─── Hitbox elliptique (mur) ─────────────────────────────────
    radius_x = radius
    radius_y = radius
    ellipse_angle = 0.0

    if is_wall and spec.axis is not None:
        ax, ay = spec.axis
        # La magnitude de l'axe encode l'elongation (envoye par resolved_spell.py)
        axis_len = math.hypot(ax, ay)
        if axis_len > 1e-6:
            # axis_len porte deja l'elongation encodee cote client
            elongation = _clamp(axis_len * 0.6, 1.2, 5.0)
            # La compression amplifie encore l'allongement
            elongation *= _clamp(1.0 + (spec.compression - 1.5) * 0.2, 1.0, 2.0)
            radius_x = radius * elongation
            radius_y = radius / max(elongation, 1.0)
            ellipse_angle = math.atan2(ay, ax)

    # ─── Position de spawn ───────────────────────────────────────
    if is_pool:
        cast_dist = 0.0
        cone_half_angle = 0.0   # mare = pas de cone
    elif is_wall:
        cast_dist = max(20.0, radius * 0.3)
    elif not has_movement and cone_half_angle > 0.05:
        cast_dist = max(10.0, radius * 0.5)
    else:
        cast_dist = max(24.0, max(radius_x, radius_y) + 10.0)

    raw_x = float(player["x"]) + dir_x * cast_dist
    raw_y = float(player["y"]) + dir_y * cast_dist

    map_w, map_h = instance.map_data.get("size", [1280, 720])
    x = _clamp(raw_x, radius_x, max(radius_x, map_w - radius_x))
    y = _clamp(raw_y, radius_y, max(radius_y, map_h - radius_y))

    # ─── Pierce ──────────────────────────────────────────────────
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
        "initial_duration": duration,
        "tick_interval":    tick_interval,
        "tick_damage":      tick_damage,
        "impact_damage":    impact_damage,
        "next_tick_at":     time.time(),
        "cone_half_angle":  cone_half_angle,
        "spell_dir_x":      dir_x,
        "spell_dir_y":      dir_y,
        "pierce":           pierce,
        "hit_targets":      [],
        "compression":      spec.compression,
        "fade_rate":        spec.fade_rate,
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
    fade_rate = float(spell.get("fade_rate", 0.0))

    if tick_damage <= 0.0 and impact_damage <= 0.0:
        return

    # Attenuation des degats de zone selon fade_rate (mare)
    effective_tick = tick_damage
    if fade_rate > 0.0 and tick_damage > 0.0:
        initial_dur = max(spell.get("initial_duration", 1.0), 0.01)
        elapsed_ratio = 1.0 - spell["remaining"] / initial_dur
        effective_tick = tick_damage * max(0.0, 1.0 - elapsed_ratio * fade_rate)

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

        if impact_damage > 0.0 and enemy_id not in hit_targets:
            damage += impact_damage
            hit_targets.append(enemy_id)
            if not pierce:
                spell["remaining"] = 0.0

        if effective_tick > 0.0:
            damage += effective_tick

        if damage <= 0.0:
            continue

        enemy["health"] = max(0.0, enemy["health"] - damage)
        if enemy["health"] <= 0.0:
            enemy["alive"] = False
            enemy["vx"] = 0.0
            enemy["vy"] = 0.0
        enemy["last_update"] = time.time()

        if spell["remaining"] <= 0.0:
            return


def resolve_spell_vs_spell(active: list[dict]) -> list[dict]:
    """
    Collision sort-vs-sort : le sort avec la compression la plus elevee
    absorbe l'autre en cas de chevauchement significatif.
    Les sorts du meme proprietaire ne se neutralisent pas.
    """
    to_remove: set[int] = set()
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            if i in to_remove or j in to_remove:
                continue
            si, sj = active[i], active[j]
            if si.get("owner_id") == sj.get("owner_id"):
                continue
            dist = math.hypot(si["x"] - sj["x"], si["y"] - sj["y"])
            ri = max(si.get("hitbox_radius_x", si["hitbox_radius"]),
                     si.get("hitbox_radius_y", si["hitbox_radius"]))
            rj = max(sj.get("hitbox_radius_x", sj["hitbox_radius"]),
                     sj.get("hitbox_radius_y", sj["hitbox_radius"]))
            if dist < (ri + rj) * 0.5:
                ci = si.get("compression", 0.0)
                cj = sj.get("compression", 0.0)
                if ci > cj:
                    to_remove.add(j)
                elif cj > ci:
                    to_remove.add(i)
                # egalite : les deux survivent
    return [s for k, s in enumerate(active) if k not in to_remove]


PARAMETRIC_SPELL_DEFINITION = ServerSpellDefinition(
    spell_id="parametric",
    cast_handler=lambda inst, cid, payload, mods: None,
    tick_handler=tick_parametric_spell,
)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
