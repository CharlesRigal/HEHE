from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pygame


class MergeStrategy(Enum):
    OVERRIDE = "override"      # le dernier gagne
    FIRST = "first"           # le premier gagne  
    ACCUMULATE = "accumulate" # s'additionnent
    MAX = "max"              # le plus grand gagne
    COMBINE = "combine"      # fusion sémantique (ex: éléments)


@dataclass
class TypedProperty:
    value: Any
    source: str        # quelle primitive a émis ça, pour debuggabilité
    strategy: MergeStrategy


@dataclass
class SpellSpec:
    element: TypedProperty | None = None    # fire, lightning, plasma...
    behavior: TypedProperty | None = None   # projectile, wall, area, stationary
    direction: TypedProperty | None = None  # Vector2 normalisé
    power: TypedProperty | None = None      # float 0..1
    shape: TypedProperty | None = None      # sphere, line, cone
    focused: TypedProperty | None = None    # bool
    unstable: TypedProperty | None = None   # bool
    axis: TypedProperty | None = None       # Vector2 pour les sorts linéaires
    intensity: TypedProperty | None = None  # float, ACCUMULATE - complexité du dessin
    speed: TypedProperty | None = None      # float 0..1, MAX - vitesse de déplacement
    duration_bonus: TypedProperty | None = None  # float, ACCUMULATE - bonus de durée
    spread: TypedProperty | None = None     # float 0..1, MAX - angle de cône / zone


# Table de fusion des éléments
ELEMENT_COMBINE = {
    ("fire", "lightning"): "plasma",
    ("fire", "fire"): "inferno",
    ("lightning", "lightning"): "storm",
}


def merge_spec_into(base: SpellSpec, incoming: SpellSpec) -> SpellSpec:
    """Fusionne une SpellSpec incoming dans base selon les stratégies de chaque propriété."""
    result = SpellSpec()
    
    properties = [
        'element', 'behavior', 'direction', 'power', 'shape',
        'focused', 'unstable', 'axis', 'intensity', 'speed',
        'duration_bonus', 'spread',
    ]

    for prop_name in properties:
        base_prop = getattr(base, prop_name)
        incoming_prop = getattr(incoming, prop_name)
        
        if base_prop is None:
            setattr(result, prop_name, incoming_prop)
        elif incoming_prop is None:
            setattr(result, prop_name, base_prop)
        else:
            # Les deux propriétés existent, appliquer la stratégie
            merged_prop = _merge_property(base_prop, incoming_prop, prop_name)
            setattr(result, prop_name, merged_prop)
    
    return result


def _merge_property(base_prop: TypedProperty, incoming_prop: TypedProperty, prop_name: str) -> TypedProperty:
    """Fusionne deux TypedProperty selon leur stratégie."""
    # Utiliser la stratégie de incoming par défaut
    strategy = incoming_prop.strategy
    
    if strategy == MergeStrategy.OVERRIDE:
        return incoming_prop
    elif strategy == MergeStrategy.FIRST:
        return base_prop
    elif strategy == MergeStrategy.ACCUMULATE:
        if isinstance(base_prop.value, (int, float)) and isinstance(incoming_prop.value, (int, float)):
            new_value = float(base_prop.value or 0) + float(incoming_prop.value or 0)
            if prop_name == 'power':
                new_value = min(1.0, new_value)
            return TypedProperty(
                value=new_value,
                source=f"{base_prop.source}+{incoming_prop.source}",
                strategy=strategy,
            )
        else:
            return TypedProperty(
                value=incoming_prop.value,
                source=f"{base_prop.source}+{incoming_prop.source}",
                strategy=strategy,
            )
    elif strategy == MergeStrategy.MAX:
        if prop_name == 'power':
            new_value = max(float(base_prop.value or 0), float(incoming_prop.value or 0))
            winner = incoming_prop if new_value == float(incoming_prop.value or 0) else base_prop
            return TypedProperty(
                value=new_value,
                source=winner.source,
                strategy=strategy
            )
        else:
            return incoming_prop  # Par défaut, prendre le nouveau
    elif strategy == MergeStrategy.COMBINE:
        if prop_name == 'element':
            return _combine_elements(base_prop, incoming_prop)
        elif prop_name == 'unstable':
            # Si l'un des deux est instable, le résultat l'est
            new_value = bool(base_prop.value) or bool(incoming_prop.value)
            return TypedProperty(
                value=new_value,
                source=f"{base_prop.source}+{incoming_prop.source}",
                strategy=strategy
            )
        else:
            return incoming_prop
    else:
        # Fallback: OVERRIDE
        return incoming_prop


def _combine_elements(base_prop: TypedProperty, incoming_prop: TypedProperty) -> TypedProperty:
    """Combine deux éléments selon la table de fusion."""
    base_element = base_prop.value
    incoming_element = incoming_prop.value
    
    # Essayer la combinaison dans les deux sens
    combo_key = (base_element, incoming_element)
    reverse_key = (incoming_element, base_element)
    
    if combo_key in ELEMENT_COMBINE:
        result_element = ELEMENT_COMBINE[combo_key]
    elif reverse_key in ELEMENT_COMBINE:
        result_element = ELEMENT_COMBINE[reverse_key]
    else:
        # Pas de combinaison spécifique, garder l'élément entrant
        result_element = incoming_element
    
    return TypedProperty(
        value=result_element,
        source=f"{base_prop.source}+{incoming_prop.source}",
        strategy=MergeStrategy.COMBINE
    )


def spec_to_dict(spec: SpellSpec) -> dict:
    """Convertit une SpellSpec en dictionnaire pour la sérialisation réseau."""
    result = {}
    properties = [
        'element', 'behavior', 'direction', 'power', 'shape',
        'focused', 'unstable', 'axis', 'intensity', 'speed',
        'duration_bonus', 'spread',
    ]

    for prop_name in properties:
        prop = getattr(spec, prop_name)
        if prop is not None:
            value = prop.value
            # Convertir pygame.Vector2 en tuple pour la sérialisation
            if isinstance(value, pygame.Vector2):
                value = (value.x, value.y)

            result[prop_name] = {
                'value': value,
                'source': prop.source,
                'strategy': prop.strategy.value
            }

    return result


def spec_to_network(spec: SpellSpec) -> dict:
    """Sérialisation réseau compacte : clés courtes, sans source/strategy, booléens omis si False."""
    result: dict = {}

    if spec.element is not None:
        result["e"] = spec.element.value
    if spec.behavior is not None:
        result["bh"] = spec.behavior.value
    if spec.direction is not None:
        v = spec.direction.value
        if isinstance(v, pygame.Vector2):
            result["dir"] = [round(v.x, 3), round(v.y, 3)]
        elif isinstance(v, (list, tuple)) and len(v) == 2:
            result["dir"] = [round(float(v[0]), 3), round(float(v[1]), 3)]
    if spec.power is not None:
        result["pwr"] = round(float(spec.power.value), 3)
    if spec.shape is not None:
        result["shp"] = spec.shape.value
    if spec.focused is not None and spec.focused.value:
        result["foc"] = 1
    if spec.unstable is not None and spec.unstable.value:
        result["uns"] = 1
    if spec.axis is not None:
        v = spec.axis.value
        if isinstance(v, pygame.Vector2):
            result["ax"] = [round(v.x, 3), round(v.y, 3)]
        elif isinstance(v, (list, tuple)) and len(v) == 2:
            result["ax"] = [round(float(v[0]), 3), round(float(v[1]), 3)]

    if spec.intensity is not None:
        result["intn"] = round(float(spec.intensity.value), 3)
    if spec.speed is not None:
        result["spd"] = round(float(spec.speed.value), 3)
    if spec.duration_bonus is not None:
        result["dur"] = round(float(spec.duration_bonus.value), 3)
    if spec.spread is not None:
        result["spr"] = round(float(spec.spread.value), 3)

    return result


def dict_to_spec(data: dict) -> SpellSpec:
    """Reconstruit une SpellSpec depuis un dictionnaire."""
    spec = SpellSpec()
    
    for prop_name, prop_data in data.items():
        if not isinstance(prop_data, dict):
            continue
            
        value = prop_data.get('value')
        source = prop_data.get('source', 'unknown')
        strategy_str = prop_data.get('strategy', 'override')
        
        # Convertir tuple en Vector2 si nécessaire
        if prop_name in ['direction', 'axis'] and isinstance(value, (list, tuple)) and len(value) == 2:
            value = pygame.Vector2(value[0], value[1])
        
        try:
            strategy = MergeStrategy(strategy_str)
        except ValueError:
            strategy = MergeStrategy.OVERRIDE
        
        typed_prop = TypedProperty(value=value, source=source, strategy=strategy)
        setattr(spec, prop_name, typed_prop)
    
    return spec