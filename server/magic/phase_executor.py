"""
phase_executor.py -- Execute les sorts multi-phases (protocole s2).

Recoit un SpellIntent deserialise et :
  1. Lance la phase 0 comme spell actif
  2. Gere les triggers (on_impact, after_delay, on_expire) pour spawner les phases suivantes
  3. Applique les effets non-degat via l'EffectRegistry
"""
from __future__ import annotations

import math
import time
import logging
from typing import Any

from server.effects.effect_registry import EFFECT_REGISTRY, ActiveEffect


# --- Constantes ---
_BASE_DAMAGE = 12.0
_BASE_TICK_INTERVAL = 0.20
_MAX_SPEED = 500.0
_MIN_RADIUS = 8.0
_MAX_RADIUS = 300.0

_ELEMENT_MODS: dict[str, dict[str, float]] = {
    "fire":      {"damage": 1.0,  "duration": 1.0,  "tick_rate": 1.0,  "radius": 1.0},
    "lightning": {"damage": 1.15, "duration": 0.75, "tick_rate": 0.6,  "radius": 0.9},
    "arcane":    {"damage": 0.9,  "duration": 1.2,  "tick_rate": 0.8,  "radius": 1.1},
    "ice":       {"damage": 0.8,  "duration": 1.5,  "tick_rate": 1.2,  "radius": 1.0},
}
_DEFAULT_MOD = {"damage": 1.0, "duration": 1.0, "tick_rate": 1.0, "radius": 1.0}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def execute_spell_intent(instance: Any, client_id: str, intent_data: dict) -> None:
    """Point d'entree : execute un sort s2 multi-phases."""
    player = instance.players.get(client_id)
    if player is None or not player.get("alive", True):
        return

    phases = intent_data.get("phases", [])
    if not phases:
        return

    global_power = float(intent_data.get("pwr", 0.5))

    # Lancer la phase 0
    _execute_phase(instance, client_id, phases, 0, global_power,
                   float(player["x"]), float(player["y"]),
                   float(player.get("facing_x", 1.0)),
                   float(player.get("facing_y", 0.0)))


def _execute_phase(
    instance: Any,
    client_id: str,
    phases: list[dict],
    phase_idx: int,
    global_power: float,
    spawn_x: float,
    spawn_y: float,
    default_dir_x: float,
    default_dir_y: float,
) -> None:
    """Execute une phase specifique du sort."""
    if phase_idx < 0 or phase_idx >= len(phases):
        return

    phase = phases[phase_idx]
    form_type = phase.get("form", "aoe")
    sub_type = phase.get("sub", "damage")
    element = phase.get("e", "neutral")
    power = float(phase.get("pwr", global_power))
    emod = _ELEMENT_MODS.get(element, _DEFAULT_MOD)

    # Direction
    dir_raw = phase.get("dir")
    if isinstance(dir_raw, (list, tuple)) and len(dir_raw) == 2:
        dir_x, dir_y = float(dir_raw[0]), float(dir_raw[1])
    else:
        dir_x, dir_y = default_dir_x, default_dir_y
    norm = math.hypot(dir_x, dir_y)
    if norm > 1e-6:
        dir_x /= norm
        dir_y /= norm
    else:
        dir_x, dir_y = 1.0, 0.0

    # Vitesse
    speed_raw = float(phase.get("spd", 0.0))
    speed = speed_raw * _MAX_SPEED if speed_raw > 0.01 else 0.0

    # Rayon
    radius_raw = float(phase.get("rad", 0.3))
    radius = _clamp((20.0 + radius_raw * 200.0) * emod["radius"], _MIN_RADIUS, _MAX_RADIUS)

    # Duree
    dur_bonus = float(phase.get("dur", 0.0))
    base_dur = 2.0 if speed > 0 else 3.0
    duration = _clamp(base_dur * (0.5 + dur_bonus * 2.0), 0.5, 15.0) * emod["duration"]

    # Spread
    spread = float(phase.get("spr", 0.0))
    cone_half_angle = spread * (math.pi / 2.0) if spread > 0.05 else 0.0

    # Position de spawn
    if speed > 0:
        cast_dist = max(24.0, radius + 10.0)
    else:
        cast_dist = max(10.0, radius * 0.3)
    x = spawn_x + dir_x * cast_dist
    y = spawn_y + dir_y * cast_dist

    map_w, map_h = instance.map_data.get("size", [1280, 720])
    x = _clamp(x, radius, max(radius, map_w - radius))
    y = _clamp(y, radius, max(radius, map_h - radius))

    # --- Effets non-degat ---
    if sub_type != "damage":
        _apply_substance_effect(instance, client_id, phase, sub_type, element,
                                power, duration, x, y, radius, dir_x, dir_y)

    # --- Degats (toujours, sauf pour create/transmute purs) ---
    if sub_type in ("damage", "push", "freeze"):
        base_damage = _BASE_DAMAGE * (0.5 + power) * emod["damage"]
        if speed > 0:
            impact_damage = base_damage * 2.5
            tick_damage = 0.0
        else:
            impact_damage = 0.0
            tick_damage = base_damage

        # Freeze fait moins de degat mais plus longtemps
        if sub_type == "freeze":
            tick_damage *= 0.3
            duration *= 1.5

        tick_interval = _BASE_TICK_INTERVAL * emod["tick_rate"]

        spell_entry = {
            "spell_id":         "parametric",
            "owner_id":         client_id,
            "element":          element,
            "x":                x,
            "y":                y,
            "velocity_x":       dir_x * speed,
            "velocity_y":       dir_y * speed,
            "hitbox_radius":    radius,
            "hitbox_radius_x":  radius,
            "hitbox_radius_y":  radius,
            "ellipse_angle":    0.0,
            "remaining":        duration,
            "initial_duration": duration,
            "tick_interval":    tick_interval,
            "tick_damage":      tick_damage,
            "impact_damage":    impact_damage,
            "next_tick_at":     time.time(),
            "cone_half_angle":  cone_half_angle,
            "spell_dir_x":     dir_x,
            "spell_dir_y":     dir_y,
            "pierce":           speed > 0 and tick_damage > 0.1,
            "hit_targets":      [],
            "compression":      0.0,
            "fade_rate":        0.0,
            # Metadata pour triggers
            "_s2_phases":       phases,
            "_s2_phase_idx":    phase_idx,
            "_s2_global_power": global_power,
        }

        # Wall form : hitbox elliptique
        if form_type == "wall":
            ax_raw = phase.get("ax")
            if isinstance(ax_raw, (list, tuple)) and len(ax_raw) == 2:
                ax, ay = float(ax_raw[0]), float(ax_raw[1])
                axis_len = math.hypot(ax, ay)
                if axis_len > 1e-6:
                    elongation = _clamp(axis_len * 0.6, 1.2, 5.0)
                    spell_entry["hitbox_radius_x"] = radius * elongation
                    spell_entry["hitbox_radius_y"] = radius / max(elongation, 1.0)
                    spell_entry["ellipse_angle"] = math.atan2(ay, ax)

        instance.active_spells.append(spell_entry)

    # Trigger handler info
    trigger = phase.get("trigger")
    if trigger and sub_type in ("damage", "push"):
        trigger_type = trigger.get("type", "on_expire")
        # after_delay : creer un evenement temporel
        if trigger_type == "after_delay":
            delay = float(trigger.get("delay", 3.0))
            _schedule_trigger(instance, client_id, phases, trigger,
                              global_power, x, y, dir_x, dir_y, delay)
        # on_expire et on_impact sont geres dans le tick du spell (voir handle_spell_trigger)


def _apply_substance_effect(
    instance: Any,
    client_id: str,
    phase: dict,
    sub_type: str,
    element: str,
    power: float,
    duration: float,
    x: float, y: float,
    radius: float,
    dir_x: float, dir_y: float,
) -> None:
    """Applique un effet non-degat via l'EffectRegistry."""
    extra = phase.get("extra", {})

    if sub_type == "freeze":
        # Geler les ennemis dans le rayon
        for enemy_id, enemy in instance.enemies.items():
            if not enemy.get("alive", True):
                continue
            dist = math.hypot(enemy["x"] - x, enemy["y"] - y)
            if dist < radius:
                freeze_dur = float(extra.get("freeze_duration", 3.0 + power * 4.0))
                effect = ActiveEffect(
                    effect_id="freeze",
                    target_type="entity",
                    target_id=enemy_id,
                    owner_id=client_id,
                    remaining=freeze_dur,
                    tick_interval=0.0,
                    next_tick_at=time.time() + freeze_dur,
                    params={"element": element},
                )
                EFFECT_REGISTRY.apply_effect(instance, effect)
                instance.active_effects.append(effect)

    elif sub_type == "create":
        create_dur = duration * 2.0
        effect = ActiveEffect(
            effect_id="create_terrain",
            target_type="area",
            target_id=f"terrain_{x:.0f}_{y:.0f}",
            owner_id=client_id,
            remaining=create_dur,
            tick_interval=1.0,
            next_tick_at=time.time() + 1.0,
            params={
                "x": x, "y": y,
                "terrain_type": extra.get("terrain_type", "wall"),
                "traversable": extra.get("traversable", False),
                "width": float(extra.get("width", 40.0)),
                "length": float(extra.get("length", 80.0)),
            },
        )
        EFFECT_REGISTRY.apply_effect(instance, effect)
        instance.active_effects.append(effect)

    elif sub_type == "transmute":
        effect = ActiveEffect(
            effect_id="transmute",
            target_type="area",
            target_id=f"transmute_{x:.0f}_{y:.0f}",
            owner_id=client_id,
            remaining=0.1,  # instantane
            tick_interval=0.0,
            next_tick_at=time.time() + 1.0,
            params={
                "x": x, "y": y,
                "radius": radius,
                "to_material": extra.get("to_material", "dust"),
            },
        )
        EFFECT_REGISTRY.apply_effect(instance, effect)
        instance.active_effects.append(effect)

    elif sub_type == "push":
        effect = ActiveEffect(
            effect_id="push",
            target_type="area",
            target_id=f"push_{x:.0f}_{y:.0f}",
            owner_id=client_id,
            remaining=0.1,  # instantane
            tick_interval=0.0,
            next_tick_at=time.time() + 1.0,
            params={
                "x": x, "y": y,
                "radius": radius,
                "push_x": float(extra.get("push_x", dir_x)),
                "push_y": float(extra.get("push_y", dir_y)),
                "push_force": float(extra.get("push_force", 200.0)),
            },
        )
        EFFECT_REGISTRY.apply_effect(instance, effect)
        instance.active_effects.append(effect)


def _schedule_trigger(
    instance: Any,
    client_id: str,
    phases: list[dict],
    trigger: dict,
    global_power: float,
    x: float, y: float,
    dir_x: float, dir_y: float,
    delay: float,
) -> None:
    """Programme un trigger temporel (after_delay)."""
    scheduled = {
        "type": "spell_trigger",
        "fire_at": time.time() + delay,
        "client_id": client_id,
        "phases": phases,
        "trigger": trigger,
        "global_power": global_power,
        "x": x, "y": y,
        "dir_x": dir_x, "dir_y": dir_y,
    }
    instance.pending_triggers.append(scheduled)


def handle_spell_trigger_on_expire(
    instance: Any,
    spell: dict,
) -> None:
    """Appele quand un spell s2 expire. Verifie les triggers on_expire."""
    phases = spell.get("_s2_phases")
    if phases is None:
        return

    phase_idx = spell.get("_s2_phase_idx", 0)
    if phase_idx >= len(phases):
        return

    phase = phases[phase_idx]
    trigger = phase.get("trigger")
    if trigger is None or trigger.get("type") != "on_expire":
        return

    _fire_trigger(instance, spell, phases, trigger)


def handle_spell_trigger_on_impact(
    instance: Any,
    spell: dict,
) -> None:
    """Appele quand un spell s2 touche une cible. Verifie les triggers on_impact."""
    phases = spell.get("_s2_phases")
    if phases is None:
        return

    phase_idx = spell.get("_s2_phase_idx", 0)
    if phase_idx >= len(phases):
        return

    phase = phases[phase_idx]
    trigger = phase.get("trigger")
    if trigger is None or trigger.get("type") != "on_impact":
        return

    _fire_trigger(instance, spell, phases, trigger)


def _fire_trigger(
    instance: Any,
    spell: dict,
    phases: list[dict],
    trigger: dict,
) -> None:
    """Execute un trigger : spawn les phases suivantes."""
    next_idx = trigger.get("next", -1)
    if next_idx < 0 or next_idx >= len(phases):
        return

    count = max(1, int(trigger.get("count", 1)))
    global_power = spell.get("_s2_global_power", 0.5)

    for i in range(count):
        # Direction avec spread pour les splits
        dir_x = float(spell.get("spell_dir_x", 1.0))
        dir_y = float(spell.get("spell_dir_y", 0.0))
        if count > 1:
            angle_offset = (i - (count - 1) / 2.0) * (math.pi / 6.0)
            cos_a = math.cos(angle_offset)
            sin_a = math.sin(angle_offset)
            new_dx = dir_x * cos_a - dir_y * sin_a
            new_dy = dir_x * sin_a + dir_y * cos_a
            dir_x, dir_y = new_dx, new_dy

        _execute_phase(
            instance,
            spell.get("owner_id", ""),
            phases,
            next_idx,
            global_power,
            float(spell["x"]),
            float(spell["y"]),
            dir_x,
            dir_y,
        )


def tick_pending_triggers(instance: Any, now: float) -> None:
    """Tick les triggers temporels (after_delay)."""
    remaining = []
    for trigger_data in instance.pending_triggers:
        if now >= trigger_data["fire_at"]:
            trigger = trigger_data["trigger"]
            next_idx = trigger.get("next", -1)
            count = max(1, int(trigger.get("count", 1)))
            phases = trigger_data["phases"]

            for i in range(count):
                dir_x = trigger_data["dir_x"]
                dir_y = trigger_data["dir_y"]
                if count > 1:
                    angle_offset = (i - (count - 1) / 2.0) * (math.pi / 6.0)
                    cos_a = math.cos(angle_offset)
                    sin_a = math.sin(angle_offset)
                    new_dx = dir_x * cos_a - dir_y * sin_a
                    new_dy = dir_x * sin_a + dir_y * cos_a
                    dir_x, dir_y = new_dx, new_dy

                _execute_phase(
                    instance,
                    trigger_data["client_id"],
                    phases,
                    next_idx,
                    trigger_data["global_power"],
                    trigger_data["x"],
                    trigger_data["y"],
                    dir_x,
                    dir_y,
                )
        else:
            remaining.append(trigger_data)
    instance.pending_triggers = remaining
