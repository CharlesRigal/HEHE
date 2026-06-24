"""Runtime d'effets : LiveEffect + dispatcher de tick.

Phase 1.4. Consomme les Effect emis par les producers (Phase 1.2) via
`spawn_effect`. La boucle de jeu appelle `tick_all()` chaque frame et
recupere la liste des survivants.

Un LiveEffect encapsule un Effect (config immuable) + etat runtime mutable :
  - remaining : temps restant avant expiration
  - next_tick_at : prochain tick periodique (pour tick_interval > 0)
  - hit_targets : cibles deja touchees (anti-doublon pour impact)
  - expired : flag de fin (collecte par tick_all)

Dispatch par type :
  DamageEffect       -> tick_damage_effect  (actif)
  StateChangeEffect  -> tick_state_change_effect  (stub, Phase 3)
  ForceEffect        -> tick_force_effect  (stub, Phase 2)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from server.config import TICK_INTERVAL
from server.effects.effect_types import (
    DamageEffect,
    Effect,
    EffectShape,
    ForceEffect,
    ShapeKind,
    StateChangeEffect,
)
from server.entities.components import Entity
from server.spells.runtime import apply_enemy_damage


def apply_combat_damage(entity: Entity, amount: float, now: float | None = None) -> None:
    """Applique des degats a une Entity dotee d'EntityCombat (post-migration ECS)."""
    if entity.combat is None or amount <= 0.0 or not entity.combat.alive:
        return
    entity.combat.health = max(0.0, entity.combat.health - float(amount))
    if entity.combat.health <= 0.0:
        entity.combat.alive = False
        entity.body.velocity_x = 0.0
        entity.body.velocity_y = 0.0
    entity.combat.last_update = time.time() if now is None else now


@dataclass
class LiveEffect:
    effect: Effect
    remaining: float
    next_tick_at: float
    initial_duration: float
    hit_targets: list[str] = field(default_factory=list)
    expired: bool = False


def spawn_effect(effect: Effect, now: float | None = None) -> LiveEffect:
    """Wrap un Effect dans un LiveEffect pret pour le runtime."""
    t = time.time() if now is None else now
    remaining = max(0.0, effect.duration)
    return LiveEffect(
        effect=effect,
        remaining=remaining,
        next_tick_at=t,
        initial_duration=remaining,
    )


# ─── Collision ─────────────────────────────────────────────────

def update_shape_motion(
    shape: EffectShape, dt: float, bounds: tuple[float, float]
) -> None:
    """Deplace la shape selon sa velocite et clampe aux limites de la map."""
    if shape.velocity_x == 0.0 and shape.velocity_y == 0.0:
        return
    w, h = bounds
    r = max(shape.radius, shape.radius_x, shape.radius_y, 1.0)
    shape.x = max(r, min(w - r, shape.x + shape.velocity_x * dt))
    shape.y = max(r, min(h - r, shape.y + shape.velocity_y * dt))


def point_in_shape(
    shape: EffectShape, tx: float, ty: float, extra_radius: float = 0.0
) -> bool:
    """Test inclusion (tx, ty) dans shape, elargi de extra_radius."""
    dx = tx - shape.x
    dy = ty - shape.y

    if shape.kind is ShapeKind.CIRCLE:
        r = shape.radius + extra_radius
        return dx * dx + dy * dy <= r * r

    if shape.kind is ShapeKind.ELLIPSE:
        rx = shape.radius_x + extra_radius
        ry = shape.radius_y + extra_radius
        if rx <= 1e-6 or ry <= 1e-6:
            return False
        cos_a = math.cos(shape.angle)
        sin_a = math.sin(shape.angle)
        local_x = dx * cos_a + dy * sin_a
        local_y = -dx * sin_a + dy * cos_a
        return (local_x / rx) ** 2 + (local_y / ry) ** 2 <= 1.0

    if shape.kind is ShapeKind.CONE:
        r = shape.radius + extra_radius
        dist_sq = dx * dx + dy * dy
        if dist_sq > r * r:
            return False
        if dist_sq < 1e-6:
            return True
        dist = math.sqrt(dist_sq)
        dir_x = math.cos(shape.angle)
        dir_y = math.sin(shape.angle)
        dot = (dx * dir_x + dy * dir_y) / dist
        return dot >= math.cos(shape.cone_half_angle)

    return False


# ─── Handlers par type ─────────────────────────────────────────

def tick_damage_effect(instance: Any, live: LiveEffect) -> None:
    """Applique des degats aux entites combat chevauchees.

    tick_interval == 0 : dommage d'impact, une seule fois par cible
                         sauf si `pierce`, sort meurt au premier contact.
    tick_interval  > 0 : dommage de zone periodique, tous les overlaps
                         prennent des degats chaque tick.

    Post-ECS : itere `instance.entities` filtrees par presence d'EntityCombat.
    Fallback `instance.enemies` (dict legacy) pour compat retro des tests.
    """
    effect = live.effect
    assert isinstance(effect, DamageEffect)

    shape = effect.shape
    impact_mode = effect.tick_interval == 0.0

    entities = getattr(instance, "entities", None)
    if entities is not None:
        for entity in entities:
            if entity.combat is None or not entity.combat.alive:
                continue
            body = entity.body
            if not point_in_shape(shape, body.x, body.y, extra_radius=body.radius):
                continue
            if impact_mode:
                if entity.id in live.hit_targets:
                    continue
                live.hit_targets.append(entity.id)
                apply_combat_damage(entity, effect.amount)
                if not effect.pierce:
                    live.expired = True
                    return
            else:
                apply_combat_damage(entity, effect.amount)
        return

    # Legacy : dict d'ennemis (pour tests __main__ a l'ancienne)
    enemy_hr = getattr(instance, "enemy_collision_size", 32.0) * 0.5
    for enemy_id, enemy in instance.enemies.items():
        if not enemy.get("alive", True):
            continue
        if not point_in_shape(shape, enemy["x"], enemy["y"], extra_radius=enemy_hr):
            continue
        if impact_mode:
            if enemy_id in live.hit_targets:
                continue
            live.hit_targets.append(enemy_id)
            apply_enemy_damage(enemy, effect.amount)
            if not effect.pierce:
                live.expired = True
                return
        else:
            apply_enemy_damage(enemy, effect.amount)


def tick_state_change_effect(instance: Any, live: LiveEffect) -> None:
    """Applique un StateChangeEffect a toute Entity dans la shape.

    Post-ECS : cible `instance.entities` (torches + ennemis + cristaux...).
    Fallback `instance.interactive` pour compat.

    hit_targets evite les re-declenchements pendant toute la vie de l'effet.
    """
    from server.effects.effect_types import StateChangeEffect
    from server.entities.interactive import apply_state_change_to_entity

    effect = live.effect
    assert isinstance(effect, StateChangeEffect)

    entities = getattr(instance, "entities", None) or getattr(instance, "interactive", None)
    if not entities:
        return

    intensity = float(effect.value) if isinstance(effect.value, (int, float)) else 1.0

    for entity in entities:
        if entity.id in live.hit_targets:
            continue
        body = entity.body
        if not point_in_shape(effect.shape, body.x, body.y, extra_radius=body.radius):
            continue
        if apply_state_change_to_entity(entity, effect.element, intensity):
            live.hit_targets.append(entity.id)
            if hasattr(instance, "_on_entity_state_changed"):
                instance._on_entity_state_changed(entity)


def tick_force_effect(instance: Any, live: LiveEffect) -> None:
    """Applique F = m*a aux entites avec EntityBody non static dans la shape.

    Modes :
      - impulsion (par defaut) : applique une fois par cible via hit_targets
      - continuous=True        : reapplique a chaque tick (levitation)
      - auto_bind_on_hit=True  : premier contact pose effect.bind_target_id
                                 et bascule en mode bind (shape recollee
                                 sur la cible par binding.update_binding)

    Post-ECS : cible `instance.entities` (ennemis + caisses + interactives).
    Fallback `instance.interactive` pour compat.
    """
    from server.effects.effect_types import ForceEffect

    effect = live.effect
    assert isinstance(effect, ForceEffect)
    if effect.magnitude <= 0.0:
        return

    entities = getattr(instance, "entities", None) or getattr(instance, "interactive", None)
    if not entities:
        return

    fx = effect.dir_x * effect.magnitude
    fy = effect.dir_y * effect.magnitude
    # Pour un impulse, on integre sur effect.duration (ou 1 frame si instant).
    # Pour un continuous, on integre sur le tick reel.
    if effect.continuous:
        dt = max(TICK_INTERVAL, 1.0 / 60.0)
    else:
        dt = max(effect.duration, 1.0 / 60.0) if effect.duration > 0.0 else 1.0 / 60.0

    # Si deja bound : on n'applique qu'a la cible bindee
    if effect.bind_target_id:
        for entity in entities:
            if entity.id != effect.bind_target_id:
                continue
            body = entity.body
            if body.static:
                return
            body.apply_force(fx, fy, dt)
            return
        # Cible disparue : laisser binding.update_binding rompre le lien
        return

    for entity in entities:
        body = entity.body
        if body.static:
            continue
        if not effect.continuous and entity.id in live.hit_targets:
            continue
        if not point_in_shape(effect.shape, body.x, body.y, extra_radius=body.radius):
            continue
        body.apply_force(fx, fy, dt)
        if effect.auto_bind_on_hit:
            effect.bind_target_id = entity.id
            return
        if not effect.continuous:
            live.hit_targets.append(entity.id)


_TICK_DISPATCH: dict[type, Callable[[Any, LiveEffect], None]] = {
    DamageEffect: tick_damage_effect,
    StateChangeEffect: tick_state_change_effect,
    ForceEffect: tick_force_effect,
}


# ─── Boucle principale ─────────────────────────────────────────

def tick_live_effect(
    instance: Any,
    live: LiveEffect,
    dt: float,
    now: float,
    bounds: tuple[float, float],
) -> None:
    """Avance le temps, deplace la shape, dispatche le tick de type."""
    effect = live.effect
    handler = _TICK_DISPATCH.get(type(effect))

    # Duration == 0 : effet instantane applique une fois puis expire.
    if effect.duration <= 0.0:
        if handler is not None:
            handler(instance, live)
        live.expired = True
        return

    live.remaining -= dt

    from server.effects.binding import update_binding
    update_binding(instance, effect)
    update_shape_motion(effect.shape, dt, bounds)

    if handler is not None and not live.expired:
        if effect.tick_interval == 0.0:
            handler(instance, live)
        else:
            while now >= live.next_tick_at and not live.expired:
                handler(instance, live)
                live.next_tick_at += effect.tick_interval

    if live.remaining <= 0.0:
        live.expired = True


def tick_all(
    instance: Any,
    live_effects: list[LiveEffect],
    dt: float,
    now: float,
    bounds: tuple[float, float],
) -> list[LiveEffect]:
    """Tick tous les effets, retourne les survivants."""
    survivors: list[LiveEffect] = []
    for live in live_effects:
        tick_live_effect(instance, live, dt, now, bounds)
        if not live.expired:
            survivors.append(live)
    return survivors


if __name__ == "__main__":
    # ── Collision ────────────────────────────────────────
    c = EffectShape(kind=ShapeKind.CIRCLE, x=0.0, y=0.0, radius=10.0)
    assert point_in_shape(c, 5.0, 0.0)
    assert not point_in_shape(c, 15.0, 0.0)

    e = EffectShape(
        kind=ShapeKind.ELLIPSE, x=0.0, y=0.0,
        radius_x=20.0, radius_y=5.0, angle=0.0,
    )
    assert point_in_shape(e, 18.0, 0.0)
    assert not point_in_shape(e, 0.0, 6.0)

    cone = EffectShape(
        kind=ShapeKind.CONE, x=0.0, y=0.0,
        radius=100.0, angle=0.0, cone_half_angle=math.pi / 6,
    )
    assert point_in_shape(cone, 50.0, 0.0)            # dans l'axe
    assert not point_in_shape(cone, 0.0, 50.0)         # perpendiculaire
    assert not point_in_shape(cone, 150.0, 0.0)        # trop loin

    # ── Motion ───────────────────────────────────────────
    moving = EffectShape(
        kind=ShapeKind.CIRCLE, x=100.0, y=100.0, radius=10.0,
        velocity_x=200.0, velocity_y=0.0,
    )
    update_shape_motion(moving, 0.5, (1600.0, 900.0))
    assert abs(moving.x - 200.0) < 1e-6
    assert abs(moving.y - 100.0) < 1e-6

    # ── Dispatch damage ──────────────────────────────────
    class _FakeInstance:
        enemy_collision_size = 20.0
        def __init__(self):
            self.enemies = {
                "e1": {"x": 105.0, "y": 100.0, "alive": True, "health": 50.0},
                "e2": {"x": 500.0, "y": 500.0, "alive": True, "health": 50.0},
            }

    inst = _FakeInstance()
    dmg = DamageEffect(
        owner_id="p1", element="fire",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=100.0, y=100.0, radius=30.0),
        duration=1.0, tick_interval=0.0,
        amount=20.0, pierce=False,
    )
    live = spawn_effect(dmg, now=0.0)
    tick_live_effect(inst, live, dt=0.016, now=0.016, bounds=(1600.0, 900.0))
    assert inst.enemies["e1"]["health"] == 30.0
    assert inst.enemies["e2"]["health"] == 50.0
    assert live.expired  # impact + not pierce -> meurt au contact

    # ── Dispatch tick (zone periodique) ──────────────────
    inst2 = _FakeInstance()
    tick_dmg = DamageEffect(
        owner_id="p1", element="fire",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=100.0, y=100.0, radius=30.0),
        duration=2.0, tick_interval=0.2,
        amount=5.0, pierce=True,
    )
    live2 = spawn_effect(tick_dmg, now=0.0)
    # Avance de 0.5s : devrait faire 2 ou 3 ticks
    tick_live_effect(inst2, live2, dt=0.5, now=0.5, bounds=(1600.0, 900.0))
    assert inst2.enemies["e1"]["health"] < 50.0
    assert not live2.expired

    # ── Duration 0 : instant ─────────────────────────────
    state_fx = StateChangeEffect(
        owner_id="p1", element="fire",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=0.0, y=0.0, radius=10.0),
        duration=0.0, tick_interval=0.0,
        state_name="lit", value=True,
    )
    live3 = spawn_effect(state_fx, now=0.0)
    tick_live_effect(_FakeInstance(), live3, dt=0.016, now=0.016, bounds=(1600.0, 900.0))
    assert live3.expired

    print("runtime: OK")
