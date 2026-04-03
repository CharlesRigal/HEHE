from __future__ import annotations

import math
from typing import Any

import pygame

from client.magic.primitives import Arrow, Circle, RuneFire, Segment, Triangle, ZigZag
from client.magic.spell_spec import MergeStrategy, SpellSpec, TypedProperty


def emit_spell_spec(primitive: Any) -> SpellSpec | None:
    """Émet une SpellSpec pour une primitive donnée."""
    if isinstance(primitive, RuneFire):
        return _emit_rune_fire_spec(primitive)
    elif isinstance(primitive, Arrow):
        return _emit_arrow_spec(primitive)
    elif isinstance(primitive, Circle):
        return _emit_circle_spec(primitive)
    elif isinstance(primitive, Triangle):
        return _emit_triangle_spec(primitive)
    elif isinstance(primitive, Segment):
        return _emit_segment_spec(primitive)
    elif isinstance(primitive, ZigZag):
        return _emit_zigzag_spec(primitive)
    else:
        return None


def _emit_rune_fire_spec(primitive: RuneFire) -> SpellSpec:
    """RuneFire → element=fire/COMBINE, unstable=True/OVERRIDE, intensity+=1"""
    spec = SpellSpec()
    spec.element = TypedProperty(
        value="fire",
        source="rune_fire",
        strategy=MergeStrategy.COMBINE
    )
    spec.unstable = TypedProperty(
        value=True,
        source="rune_fire",
        strategy=MergeStrategy.OVERRIDE
    )
    spec.intensity = TypedProperty(
        value=1.0,
        source="rune_fire",
        strategy=MergeStrategy.ACCUMULATE
    )
    return spec


def _emit_arrow_spec(primitive: Arrow) -> SpellSpec:
    """Arrow → behavior=projectile/FIRST, direction, speed∝length, intensity+=1"""
    spec = SpellSpec()

    spec.behavior = TypedProperty(
        value="projectile",
        source="arrow",
        strategy=MergeStrategy.FIRST
    )

    dx = primitive.tip[0] - primitive.tail[0]
    dy = primitive.tip[1] - primitive.tail[1]
    length = math.hypot(dx, dy)

    if length > 1e-6:
        direction = pygame.Vector2(dx / length, dy / length)
    else:
        direction = pygame.Vector2(1.0, 0.0)

    spec.direction = TypedProperty(
        value=direction,
        source="arrow",
        strategy=MergeStrategy.FIRST
    )

    # Vitesse proportionnelle à la longueur de la flèche
    speed_value = min(1.0, max(0.15, length / 200.0))
    spec.speed = TypedProperty(
        value=speed_value,
        source="arrow",
        strategy=MergeStrategy.MAX
    )

    spec.intensity = TypedProperty(
        value=1.0,
        source="arrow",
        strategy=MergeStrategy.ACCUMULATE
    )

    return spec


def _emit_circle_spec(primitive: Circle) -> SpellSpec:
    """Circle → power∝radius/MAX, focused, shape=sphere, duration+=0.3, intensity+=1"""
    spec = SpellSpec()

    if primitive.radius is not None:
        power_value = min(1.0, max(0.1, primitive.radius / 100.0))
    else:
        power_value = 0.5

    spec.power = TypedProperty(
        value=power_value,
        source="circle",
        strategy=MergeStrategy.MAX
    )

    spec.focused = TypedProperty(
        value=True,
        source="circle",
        strategy=MergeStrategy.OVERRIDE
    )

    spec.shape = TypedProperty(
        value="sphere",
        source="circle",
        strategy=MergeStrategy.FIRST
    )

    # Chaque cercle ajoute de la durée
    spec.duration_bonus = TypedProperty(
        value=0.3,
        source="circle",
        strategy=MergeStrategy.ACCUMULATE
    )

    spec.intensity = TypedProperty(
        value=1.0,
        source="circle",
        strategy=MergeStrategy.ACCUMULATE
    )

    return spec


def _emit_triangle_spec(primitive: Triangle) -> SpellSpec:
    """Triangle → shape=cone, behavior=area, direction, spread∝area, intensity+=1"""
    spec = SpellSpec()

    spec.shape = TypedProperty(
        value="cone",
        source="triangle",
        strategy=MergeStrategy.FIRST
    )

    spec.behavior = TypedProperty(
        value="area",
        source="triangle",
        strategy=MergeStrategy.FIRST
    )

    if len(primitive.vertices) >= 3:
        cx = sum(v[0] for v in primitive.vertices[:3]) / 3
        cy = sum(v[1] for v in primitive.vertices[:3]) / 3

        max_dist = 0
        tip_vertex = primitive.vertices[0]
        for vertex in primitive.vertices[:3]:
            dist = math.hypot(vertex[0] - cx, vertex[1] - cy)
            if dist > max_dist:
                max_dist = dist
                tip_vertex = vertex

        dx = tip_vertex[0] - cx
        dy = tip_vertex[1] - cy
        length = math.hypot(dx, dy)

        if length > 1e-6:
            direction = pygame.Vector2(dx / length, dy / length)
        else:
            direction = pygame.Vector2(0.0, -1.0)

        # Spread proportionnel à l'aire du triangle
        v = primitive.vertices[:3]
        area = 0.5 * abs(
            (v[1][0] - v[0][0]) * (v[2][1] - v[0][1])
            - (v[2][0] - v[0][0]) * (v[1][1] - v[0][1])
        )
        spread_value = min(1.0, max(0.1, area / 10000.0))
    else:
        direction = pygame.Vector2(0.0, -1.0)
        spread_value = 0.3

    spec.direction = TypedProperty(
        value=direction,
        source="triangle",
        strategy=MergeStrategy.FIRST
    )

    spec.spread = TypedProperty(
        value=spread_value,
        source="triangle",
        strategy=MergeStrategy.MAX
    )

    spec.intensity = TypedProperty(
        value=1.0,
        source="triangle",
        strategy=MergeStrategy.ACCUMULATE
    )

    return spec


def _emit_segment_spec(primitive: Segment) -> SpellSpec:
    """Segment → shape=line, behavior=wall, axis, intensity+=1"""
    spec = SpellSpec()

    spec.shape = TypedProperty(
        value="line",
        source="segment",
        strategy=MergeStrategy.FIRST
    )

    spec.behavior = TypedProperty(
        value="wall",
        source="segment",
        strategy=MergeStrategy.FIRST
    )

    dx = primitive.end[0] - primitive.start[0]
    dy = primitive.end[1] - primitive.start[1]
    axis = pygame.Vector2(dx, dy)

    spec.axis = TypedProperty(
        value=axis,
        source="segment",
        strategy=MergeStrategy.FIRST
    )

    spec.intensity = TypedProperty(
        value=1.0,
        source="segment",
        strategy=MergeStrategy.ACCUMULATE
    )

    return spec


def _emit_zigzag_spec(primitive: ZigZag) -> SpellSpec:
    """ZigZag → element=lightning, unstable, behavior=area, intensity+=1"""
    spec = SpellSpec()

    spec.element = TypedProperty(
        value="lightning",
        source="zigzag",
        strategy=MergeStrategy.COMBINE
    )

    spec.unstable = TypedProperty(
        value=True,
        source="zigzag",
        strategy=MergeStrategy.OVERRIDE
    )

    spec.behavior = TypedProperty(
        value="area",
        source="zigzag",
        strategy=MergeStrategy.FIRST
    )

    spec.intensity = TypedProperty(
        value=1.0,
        source="zigzag",
        strategy=MergeStrategy.ACCUMULATE
    )

    return spec