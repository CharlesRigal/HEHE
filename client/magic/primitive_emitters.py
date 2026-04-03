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
    """RuneFire → element=fire/COMBINE, unstable=True/OVERRIDE"""
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
    return spec


def _emit_arrow_spec(primitive: Arrow) -> SpellSpec:
    """Arrow → behavior=projectile/FIRST, direction=tip-tail normalisé/FIRST"""
    spec = SpellSpec()
    
    spec.behavior = TypedProperty(
        value="projectile",
        source="arrow",
        strategy=MergeStrategy.FIRST
    )
    
    # Calculer la direction normalisée du tail vers le tip
    dx = primitive.tip[0] - primitive.tail[0]
    dy = primitive.tip[1] - primitive.tail[1]
    length = math.hypot(dx, dy)
    
    if length > 1e-6:  # Éviter la division par zéro
        direction = pygame.Vector2(dx / length, dy / length)
    else:
        direction = pygame.Vector2(1.0, 0.0)  # Direction par défaut vers la droite
    
    spec.direction = TypedProperty(
        value=direction,
        source="arrow",
        strategy=MergeStrategy.FIRST
    )
    
    return spec


def _emit_circle_spec(primitive: Circle) -> SpellSpec:
    """Circle → power∝radius/MAX, focused=True/OVERRIDE, shape=sphere/FIRST"""
    spec = SpellSpec()
    
    # Power proportionnel au rayon (normalisé entre 0 et 1)
    if primitive.radius is not None:
        # Normaliser le rayon : petit cercle (10px) = 0.1, grand cercle (100px+) = 1.0
        power_value = min(1.0, max(0.1, primitive.radius / 100.0))
    else:
        power_value = 0.5  # Valeur par défaut
    
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
    
    return spec


def _emit_triangle_spec(primitive: Triangle) -> SpellSpec:
    """Triangle → shape=cone/FIRST, behavior=area/FIRST, direction=pointe/FIRST"""
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
    
    # Calculer la direction de la pointe (sommet le plus éloigné du centroïde)
    if len(primitive.vertices) >= 3:
        # Calculer le centroïde
        cx = sum(v[0] for v in primitive.vertices[:3]) / 3
        cy = sum(v[1] for v in primitive.vertices[:3]) / 3
        centroid = (cx, cy)
        
        # Trouver le sommet le plus éloigné du centroïde (la pointe)
        max_dist = 0
        tip_vertex = primitive.vertices[0]
        
        for vertex in primitive.vertices[:3]:
            dist = math.hypot(vertex[0] - cx, vertex[1] - cy)
            if dist > max_dist:
                max_dist = dist
                tip_vertex = vertex
        
        # Direction du centroïde vers la pointe
        dx = tip_vertex[0] - cx
        dy = tip_vertex[1] - cy
        length = math.hypot(dx, dy)
        
        if length > 1e-6:
            direction = pygame.Vector2(dx / length, dy / length)
        else:
            direction = pygame.Vector2(0.0, -1.0)  # Vers le haut par défaut
    else:
        direction = pygame.Vector2(0.0, -1.0)
    
    spec.direction = TypedProperty(
        value=direction,
        source="triangle",
        strategy=MergeStrategy.FIRST
    )
    
    return spec


def _emit_segment_spec(primitive: Segment) -> SpellSpec:
    """Segment → shape=line/FIRST, behavior=wall/FIRST, axis=vecteur segment/FIRST"""
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
    
    # Calculer l'axe du segment (vecteur non normalisé pour conserver la longueur)
    dx = primitive.end[0] - primitive.start[0]
    dy = primitive.end[1] - primitive.start[1]
    axis = pygame.Vector2(dx, dy)
    
    spec.axis = TypedProperty(
        value=axis,
        source="segment",
        strategy=MergeStrategy.FIRST
    )
    
    return spec


def _emit_zigzag_spec(primitive: ZigZag) -> SpellSpec:
    """ZigZag → element=lightning/COMBINE, unstable=True/OVERRIDE, behavior=area/FIRST"""
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
    
    return spec