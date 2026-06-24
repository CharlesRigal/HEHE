"""Producteurs d'effets.

Chaque producer inspecte une ServerSpellSpec + le caster et decide s'il emet
un ou plusieurs Effect. Aucun switch/case central : pour ajouter un effet, on
ajoute un producer dans REGISTERED_PRODUCERS (voir spell_to_effects.py).

Les seuils continus ici REMPLACENT la logique monolithique de l'ancien
parametric_spell.cast_parametric_spell.

Phase 1 :
  - produce_damage  : actif, remplace le DPS actuel
  - produce_state_change : minimal (empreinte elementaire), consomme Phase 3
  - produce_force : impulsion sur projectile, consomme Phase 2
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from server.effects.effect_types import (
    DamageEffect,
    Effect,
    EffectShape,
    ForceEffect,
    ShapeKind,
    StateChangeEffect,
)
from server.magic.spell_spec import ServerSpellSpec
from server.spells.runtime import facing_direction, normalize_direction


_ELEMENT_MODS: dict[str, dict[str, float]] = {
    "fire":      {"damage": 1.0,  "duration": 1.0,  "tick_rate": 1.0,  "radius": 1.0},
    "lightning": {"damage": 1.15, "duration": 0.75, "tick_rate": 0.6,  "radius": 0.9},
    "plasma":    {"damage": 1.3,  "duration": 0.6,  "tick_rate": 0.5,  "radius": 0.85},
    "inferno":   {"damage": 1.1,  "duration": 1.4,  "tick_rate": 0.9,  "radius": 1.3},
    "storm":     {"damage": 1.0,  "duration": 0.85, "tick_rate": 0.45, "radius": 1.2},
}
_DEFAULT_MOD = {"damage": 1.0, "duration": 1.0, "tick_rate": 1.0, "radius": 1.0}

_BASE_DAMAGE = 12.0
_BASE_TICK_INTERVAL = 0.20
_MAX_SPEED = 500.0
_MIN_RADIUS = 8.0
_MAX_RADIUS = 300.0

_REACTIVE_ELEMENTS = {"fire", "ice", "lightning", "water", "plasma", "inferno", "storm"}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class SpellContext:
    """Contexte derive partage entre producers. Calcule une seule fois.

    Regroupe tous les seuils emergents et les dimensions resolues pour
    eviter que chaque producer recalcule. Les producers lisent ce contexte
    et decident quoi emettre.
    """
    spec: ServerSpellSpec
    caster: Any
    element: str
    emod: dict[str, float]
    power: float
    intensity: float
    dir_x: float
    dir_y: float
    has_movement: bool
    is_wall: bool
    is_pool: bool
    has_area: bool
    radius_x: float
    radius_y: float
    ellipse_angle: float
    cone_half_angle: float
    speed: float
    spawn_x: float
    spawn_y: float
    duration: float
    tick_interval: float
    base_damage: float


def build_context(spec: ServerSpellSpec, caster: Any) -> SpellContext:
    """Calcule le contexte derive a partir de la spec et du caster."""
    element = spec.element or "neutral"
    emod = _ELEMENT_MODS.get(element, _DEFAULT_MOD)

    power = spec.power if spec.power is not None else 0.5
    intensity = max(1.0, spec.intensity)

    if spec.direction is not None:
        dir_x, dir_y = normalize_direction(
            float(spec.direction[0]), float(spec.direction[1])
        )
    else:
        dir_x, dir_y = facing_direction(caster)

    has_movement = spec.speed > 0.05
    is_wall = spec.compression > 1.5 and spec.axis is not None
    is_pool = (
        spec.spread > 0.3
        and spec.fade_rate > 0.0
        and not has_movement
        and spec.compression < 1.0
    )
    has_area = spec.spread > 0.05 or spec.shape == "cone"

    complexity_bonus = 1.0 + 0.12 * max(0.0, intensity - 1.0)
    base_damage = _BASE_DAMAGE * (0.5 + power) * complexity_bonus * emod["damage"]

    if has_movement:
        radius = (10.0 + power * 22.0) * emod["radius"]
    elif is_wall:
        radius = (15.0 + power * 60.0) * emod["radius"]
    else:
        radius = (20.0 + power * 140.0) * emod["radius"]
    radius = _clamp(radius, _MIN_RADIUS, _MAX_RADIUS)

    radius_x = radius
    radius_y = radius
    ellipse_angle = 0.0
    if is_wall and spec.axis is not None:
        ax, ay = spec.axis
        axis_len = math.hypot(ax, ay)
        if axis_len > 1e-6:
            elongation = _clamp(axis_len * 0.6, 1.2, 5.0)
            elongation *= _clamp(1.0 + (spec.compression - 1.5) * 0.2, 1.0, 2.0)
            radius_x = radius * elongation
            radius_y = radius / max(elongation, 1.0)
            ellipse_angle = math.atan2(ay, ax)

    cone_half_angle = 0.0
    if spec.spread > 0.05 and not is_pool:
        cone_half_angle = spec.spread * (math.pi / 2.0)

    speed = spec.speed * _MAX_SPEED if has_movement else 0.0

    base_dur = 2.0 if has_movement else 2.5
    dur_bonus = spec.duration_bonus
    if is_wall:
        duration = _clamp(base_dur * (1.0 + dur_bonus * 4.0), 3.0, 30.0)
    elif is_pool:
        duration = _clamp(base_dur * (0.5 + dur_bonus), 2.0, 15.0)
    else:
        duration = _clamp(base_dur * (0.5 + dur_bonus), 0.3, 10.0)
    duration *= emod["duration"]

    tick_interval = _clamp(_BASE_TICK_INTERVAL * emod["tick_rate"], 0.04, 1.0)

    caster_x, caster_y = caster.position()
    if is_pool:
        cast_dist = 0.0
    elif is_wall:
        cast_dist = max(20.0, radius * 0.3)
    elif not has_movement and cone_half_angle > 0.05:
        cast_dist = max(10.0, radius * 0.5)
    else:
        cast_dist = max(24.0, max(radius_x, radius_y) + 10.0)

    spawn_x = caster_x + dir_x * cast_dist
    spawn_y = caster_y + dir_y * cast_dist

    if spec.focused:
        radius_x *= 0.6
        radius_y *= 0.6
        base_damage *= 1.4
    if spec.unstable:
        speed *= 1.35
        base_damage *= 1.1
        duration *= 0.7

    return SpellContext(
        spec=spec,
        caster=caster,
        element=element,
        emod=emod,
        power=power,
        intensity=intensity,
        dir_x=dir_x,
        dir_y=dir_y,
        has_movement=has_movement,
        is_wall=is_wall,
        is_pool=is_pool,
        has_area=has_area,
        radius_x=radius_x,
        radius_y=radius_y,
        ellipse_angle=ellipse_angle,
        cone_half_angle=cone_half_angle,
        speed=speed,
        spawn_x=spawn_x,
        spawn_y=spawn_y,
        duration=duration,
        tick_interval=tick_interval,
        base_damage=base_damage,
    )


def _build_shape(ctx: SpellContext) -> EffectShape:
    """Construit la shape principale d'un effet selon le contexte.

    - is_wall            -> ELLIPSE
    - has_area et cone   -> CONE (si direction explicite)
    - sinon              -> CIRCLE (peut se deplacer si has_movement)
    """
    if ctx.is_wall and abs(ctx.radius_x - ctx.radius_y) > 1e-6:
        return EffectShape(
            kind=ShapeKind.ELLIPSE,
            x=ctx.spawn_x, y=ctx.spawn_y,
            radius_x=ctx.radius_x, radius_y=ctx.radius_y,
            angle=ctx.ellipse_angle,
        )

    if ctx.cone_half_angle > 0.05 and not ctx.has_movement:
        return EffectShape(
            kind=ShapeKind.CONE,
            x=ctx.spawn_x, y=ctx.spawn_y,
            radius=max(ctx.radius_x, ctx.radius_y),
            angle=math.atan2(ctx.dir_y, ctx.dir_x),
            cone_half_angle=ctx.cone_half_angle,
        )

    return EffectShape(
        kind=ShapeKind.CIRCLE,
        x=ctx.spawn_x, y=ctx.spawn_y,
        radius=max(ctx.radius_x, ctx.radius_y),
        velocity_x=ctx.dir_x * ctx.speed,
        velocity_y=ctx.dir_y * ctx.speed,
    )


# ─── Producers ────────────────────────────────────────────────────────────

def produce_damage(spec: ServerSpellSpec, caster: Any) -> list[Effect]:
    """Emet les DamageEffect (impact et/ou tick) selon le profil emergent.

    Profils :
      projectile seul         -> 1 DamageEffect impact (duration=travel, pierce possible)
      projectile + zone       -> 1 impact + 1 tick
      pool                    -> 1 tick, fade
      wall                    -> 1 tick persistant elliptique
      stationary + area       -> 1 tick conique
      stationary sans area    -> 1 tick circulaire local
    """
    ctx = build_context(spec, caster)
    out: list[Effect] = []

    if ctx.has_movement and not ctx.has_area:
        out.append(DamageEffect(
            owner_id=caster.id if hasattr(caster, "id") else str(caster),
            element=ctx.element,
            shape=_build_shape(ctx),
            duration=ctx.duration,
            tick_interval=0.0,
            amount=ctx.base_damage * 2.5,
            pierce=False,
        ))
        return out

    if ctx.has_movement and ctx.has_area:
        shape = _build_shape(ctx)
        shape.radius *= 1.6
        out.append(DamageEffect(
            owner_id=_owner(caster), element=ctx.element, shape=shape,
            duration=ctx.duration, tick_interval=0.0,
            amount=ctx.base_damage * 1.5, pierce=True,
        ))
        out.append(DamageEffect(
            owner_id=_owner(caster), element=ctx.element, shape=shape,
            duration=ctx.duration, tick_interval=ctx.tick_interval,
            amount=ctx.base_damage * 0.7, pierce=True,
        ))
        return out

    if ctx.is_pool:
        out.append(DamageEffect(
            owner_id=_owner(caster), element=ctx.element,
            shape=_build_shape(ctx),
            duration=ctx.duration, tick_interval=ctx.tick_interval,
            amount=ctx.base_damage * 0.6, pierce=True,
        ))
        return out

    out.append(DamageEffect(
        owner_id=_owner(caster), element=ctx.element,
        shape=_build_shape(ctx),
        duration=ctx.duration, tick_interval=ctx.tick_interval,
        amount=ctx.base_damage, pierce=True,
    ))
    return out


def produce_state_change(spec: ServerSpellSpec, caster: Any) -> list[Effect]:
    """Emet une empreinte elementaire consommee par les entites reactives.

    Phase 1 : forme minimale. Phase 3 (entites interactives) consomme
    cet effet pour declencher des reactions (torche -> lit, glace -> fondu).

    Rien d'emis si element neutre ou intensite trop faible.
    """
    element = spec.element or "neutral"
    if element not in _REACTIVE_ELEMENTS:
        return []

    power = spec.power if spec.power is not None else 0.0
    if power < 0.1:
        return []

    ctx = build_context(spec, caster)
    shape = _build_shape(ctx)

    return [StateChangeEffect(
        owner_id=_owner(caster),
        element=element,
        shape=shape,
        duration=ctx.duration,
        tick_interval=0.0,
        state_name=f"touched_by_{element}",
        value=power,
        target_filter={"reacts_to": element, "min_intensity": 0.2},
    )]


def produce_force(spec: ServerSpellSpec, caster: Any) -> list[Effect]:
    """Emet un ForceEffect d'impulsion pour les projectiles porteurs.

    Phase 1 : calcule et emet. Runtime Phase 2 applique via EntityBody.

    Regle emergente :
      - has_movement + power > 0.2 -> impulsion dans la direction du sort
      - magnitude augmente avec compression et power
    """
    ctx = build_context(spec, caster)
    if not ctx.has_movement or ctx.power < 0.2:
        return []

    compression_boost = 1.0 + max(0.0, spec.compression) * 0.5
    magnitude = 250.0 * ctx.power * compression_boost

    return [ForceEffect(
        owner_id=_owner(caster),
        element=ctx.element,
        shape=_build_shape(ctx),
        duration=0.0,
        tick_interval=0.0,
        dir_x=ctx.dir_x,
        dir_y=ctx.dir_y,
        magnitude=magnitude,
    )]


def produce_binding(spec: ServerSpellSpec, caster: Any) -> list[Effect]:
    """Emet une ForceEffect persistante bindee quand le dessin suggere un lien.

    Phase 5 regles emergentes :
      - focused=True + duration_bonus >= 0.5 + power >= 0.3
        -> force continue bindee a la premiere cible touchee
      - element + direction donnent l'orientation de la force
      - wind | lightning | plasma : levitation verticale (bias -y)
      - autres : direction du sort

    Le runtime applique :
      - tick_force_effect met a jour la velocite de la cible chaque tick
      - binding.update_binding recolle la shape sur la cible
    Rupture naturelle : si la cible meurt ou sort de la map, `update_binding`
    efface bind_target_id et l'effet finit sa vie a la derniere position.
    """
    if not spec.focused:
        return []
    if spec.duration_bonus < 0.5:
        return []

    ctx = build_context(spec, caster)
    if ctx.power < 0.3:
        return []

    # Levitation : direction upward si vent ou tempete, sinon dir du sort
    dir_x, dir_y = ctx.dir_x, ctx.dir_y
    if ctx.element in ("wind", "storm", "lightning", "plasma"):
        dir_x, dir_y = 0.0, -1.0

    # Duree longue pour qu'on sente le binding
    duration = _clamp(
        3.0 * (1.0 + spec.duration_bonus * 2.0),
        3.0,
        15.0,
    )

    # Magnitude : assez forte pour lutter contre une gravite simulee (~ 400 px/s²)
    magnitude = 450.0 * ctx.power * (1.0 + max(0.0, spec.compression) * 0.3)

    # Pour capturer une cible, on pose un champ large autour du caster,
    # etendu dans la direction du sort. Une fois bindee, la shape suit la cible.
    caster_x, caster_y = caster.position()
    reach = 180.0 + ctx.power * 140.0
    shape = EffectShape(
        kind=ShapeKind.CIRCLE,
        x=caster_x + ctx.dir_x * reach * 0.5,
        y=caster_y + ctx.dir_y * reach * 0.5,
        radius=reach,
    )

    return [ForceEffect(
        owner_id=_owner(caster),
        element=ctx.element,
        shape=shape,
        duration=duration,
        tick_interval=0.0,
        dir_x=dir_x,
        dir_y=dir_y,
        magnitude=magnitude,
        continuous=True,
        auto_bind_on_hit=True,
    )]


def _owner(caster: Any) -> str:
    return caster.id if hasattr(caster, "id") else str(caster)


if __name__ == "__main__":
    class _FakeCaster:
        id = "p1"
        def position(self): return (100.0, 100.0)
        def facing(self): return (1.0, 0.0)

    caster = _FakeCaster()

    # Cas 1 : projectile feu simple
    spec1 = ServerSpellSpec(
        element="fire", power=0.6, speed=0.5, compression=0.3,
    )
    effects = produce_damage(spec1, caster)
    assert len(effects) == 1
    assert isinstance(effects[0], DamageEffect)
    assert effects[0].shape.velocity_x > 0.0
    assert effects[0].amount > 0.0

    # Cas 2 : projectile + zone
    spec2 = ServerSpellSpec(
        element="fire", power=0.7, speed=0.4, spread=0.3, compression=0.2,
    )
    effects = produce_damage(spec2, caster)
    assert len(effects) == 2  # impact + tick

    # Cas 3 : pool (spread + fade + pas de mouvement + compression basse)
    spec3 = ServerSpellSpec(
        element="fire", power=0.5, spread=0.5, fade_rate=0.5, compression=0.2,
    )
    effects = produce_damage(spec3, caster)
    assert len(effects) == 1
    assert effects[0].tick_interval > 0.0
    assert effects[0].shape.kind == ShapeKind.CIRCLE

    # Cas 4 : wall (compression haute + axis)
    spec4 = ServerSpellSpec(
        element="fire", power=0.6, compression=2.0, axis=(50.0, 0.0),
    )
    effects = produce_damage(spec4, caster)
    assert len(effects) == 1
    assert effects[0].shape.kind == ShapeKind.ELLIPSE

    # State change : element reactif + power suffisant
    state_fx = produce_state_change(spec1, caster)
    assert len(state_fx) == 1
    assert state_fx[0].state_name == "touched_by_fire"
    assert state_fx[0].target_filter["reacts_to"] == "fire"

    # State change : element neutre -> rien
    spec_neutral = ServerSpellSpec(element=None, power=0.5)
    assert produce_state_change(spec_neutral, caster) == []

    # Force : projectile fort -> emis
    force_fx = produce_force(spec1, caster)
    assert len(force_fx) == 1
    assert force_fx[0].magnitude > 0.0

    # Force : stationnaire -> rien
    force_static = produce_force(spec3, caster)
    assert force_static == []

    print("producers: OK")
