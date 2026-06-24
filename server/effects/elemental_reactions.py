"""Reactions elementaires (Phase 4).

Modele : deux effets d'elements incompatibles qui se chevauchent declenchent
une reaction physique (pas une recette de sort). Detection tous les ticks :
une paire qui overlap + une entree dans REACTIONS produit un effet emergent
(steam, water, chain_shock, ...) et consomme/neutralise les deux parents.

Le module n'a aucune connaissance des sorts ; il ne regarde que l'element
des effets et leurs shapes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from server.effects.effect_types import (
    DamageEffect,
    Effect,
    EffectShape,
    ShapeKind,
    StateChangeEffect,
)
from server.effects.runtime import LiveEffect


def _midpoint(a: EffectShape, b: EffectShape) -> tuple[float, float]:
    return (a.x + b.x) * 0.5, (a.y + b.y) * 0.5


def _max_radius(shape: EffectShape) -> float:
    return max(shape.radius, shape.radius_x, shape.radius_y, 1.0)


def _shapes_overlap(a: EffectShape, b: EffectShape) -> bool:
    """Approximation cercle-cercle (ellipse/cone traites comme leur rayon max)."""
    dx = a.x - b.x
    dy = a.y - b.y
    return math.hypot(dx, dy) <= _max_radius(a) + _max_radius(b)


# Type d'un constructeur de reaction : prend les 2 parents, retourne une
# liste d'Effect a spawner pour remplacer (ou prolonger) la rencontre.
ReactionBuilder = Callable[[LiveEffect, LiveEffect], list[Effect]]


def _build_steam(a: LiveEffect, b: LiveEffect) -> list[Effect]:
    """Feu + eau (ou glace) -> nuage de vapeur local (zone chaude brievement)."""
    x, y = _midpoint(a.effect.shape, b.effect.shape)
    radius = max(_max_radius(a.effect.shape), _max_radius(b.effect.shape)) * 1.2
    owner = a.effect.owner_id
    return [
        DamageEffect(
            owner_id=owner, element="steam",
            shape=EffectShape(kind=ShapeKind.CIRCLE, x=x, y=y, radius=radius),
            duration=1.2, tick_interval=0.2,
            amount=4.0, pierce=True,
        ),
        StateChangeEffect(
            owner_id=owner, element="steam",
            shape=EffectShape(kind=ShapeKind.CIRCLE, x=x, y=y, radius=radius),
            duration=1.2, tick_interval=0.0,
            state_name="fogged", value=True,
            target_filter={"reacts_to": "steam", "min_intensity": 0.0},
        ),
    ]


def _build_water(a: LiveEffect, b: LiveEffect) -> list[Effect]:
    """Glace + feu -> eau locale (mare)."""
    x, y = _midpoint(a.effect.shape, b.effect.shape)
    radius = max(_max_radius(a.effect.shape), _max_radius(b.effect.shape))
    owner = a.effect.owner_id
    return [
        DamageEffect(
            owner_id=owner, element="water",
            shape=EffectShape(kind=ShapeKind.CIRCLE, x=x, y=y, radius=radius),
            duration=3.0, tick_interval=0.25,
            amount=2.0, pierce=True,
        )
    ]


def _build_chain_shock(a: LiveEffect, b: LiveEffect) -> list[Effect]:
    """Eau + foudre -> choc de zone, forte intensite courte duree."""
    x, y = _midpoint(a.effect.shape, b.effect.shape)
    radius = max(_max_radius(a.effect.shape), _max_radius(b.effect.shape)) * 1.6
    owner = a.effect.owner_id
    return [
        DamageEffect(
            owner_id=owner, element="lightning",
            shape=EffectShape(kind=ShapeKind.CIRCLE, x=x, y=y, radius=radius),
            duration=0.4, tick_interval=0.0,
            amount=35.0, pierce=True,
        )
    ]


def _build_flame_spread(a: LiveEffect, b: LiveEffect) -> list[Effect]:
    """Feu + vent -> zone de feu plus large, duree plus longue."""
    x, y = _midpoint(a.effect.shape, b.effect.shape)
    radius = max(_max_radius(a.effect.shape), _max_radius(b.effect.shape)) * 2.0
    owner = a.effect.owner_id
    return [
        DamageEffect(
            owner_id=owner, element="fire",
            shape=EffectShape(kind=ShapeKind.CIRCLE, x=x, y=y, radius=radius),
            duration=2.5, tick_interval=0.2,
            amount=6.0, pierce=True,
        )
    ]


# Table symetrique des reactions. Cle = frozenset des 2 elements.
REACTIONS: dict[frozenset[str], ReactionBuilder] = {
    frozenset({"fire", "ice"}): _build_water,
    frozenset({"fire", "water"}): _build_steam,
    frozenset({"ice", "water"}): _build_water,
    frozenset({"water", "lightning"}): _build_chain_shock,
    frozenset({"fire", "wind"}): _build_flame_spread,
}


@dataclass
class ReactionResult:
    """Sortie d'une passe de detection : effets a spawner + parents consommes."""
    new_effects: list[Effect]
    consumed_ids: set[int]   # id() des LiveEffect a retirer


def detect_reactions(live_effects: list[LiveEffect]) -> ReactionResult:
    """Scanne les paires d'effets et declenche les reactions possibles.

    Chaque paire n'est consideree qu'une fois. Un effet deja consomme n'est
    pas reutilise dans la meme passe. La consommation est signalee via l'id
    Python de l'objet, pour eviter de depenser des champs supplementaires.
    """
    new_effects: list[Effect] = []
    consumed: set[int] = set()

    for i in range(len(live_effects)):
        li = live_effects[i]
        if id(li) in consumed or li.expired:
            continue
        for j in range(i + 1, len(live_effects)):
            lj = live_effects[j]
            if id(lj) in consumed or lj.expired:
                continue
            key = frozenset({li.effect.element, lj.effect.element})
            if len(key) != 2:
                continue
            builder = REACTIONS.get(key)
            if builder is None:
                continue
            if not _shapes_overlap(li.effect.shape, lj.effect.shape):
                continue
            new_effects.extend(builder(li, lj))
            consumed.add(id(li))
            consumed.add(id(lj))
            break

    return ReactionResult(new_effects=new_effects, consumed_ids=consumed)


if __name__ == "__main__":
    from server.effects.runtime import spawn_effect

    fire = DamageEffect(
        owner_id="p1", element="fire",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=100.0, y=100.0, radius=30.0),
        duration=1.0, tick_interval=0.0, amount=10.0,
    )
    water = DamageEffect(
        owner_id="p2", element="water",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=110.0, y=100.0, radius=30.0),
        duration=1.0, tick_interval=0.0, amount=0.0,
    )
    neutral = DamageEffect(
        owner_id="p3", element="neutral",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=500.0, y=500.0, radius=30.0),
        duration=1.0, tick_interval=0.0, amount=10.0,
    )

    live = [spawn_effect(fire), spawn_effect(water), spawn_effect(neutral)]
    result = detect_reactions(live)

    assert len(result.new_effects) == 2  # steam + state_change
    assert result.new_effects[0].element == "steam"
    assert len(result.consumed_ids) == 2

    # Neutre non consomme
    assert id(live[2]) not in result.consumed_ids

    # Aucun overlap -> rien
    far_fire = DamageEffect(
        owner_id="p1", element="fire",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=0.0, y=0.0, radius=10.0),
        duration=1.0, tick_interval=0.0, amount=5.0,
    )
    far_ice = DamageEffect(
        owner_id="p2", element="ice",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=1000.0, y=1000.0, radius=10.0),
        duration=1.0, tick_interval=0.0, amount=0.0,
    )
    result = detect_reactions([spawn_effect(far_fire), spawn_effect(far_ice)])
    assert result.new_effects == []
    assert result.consumed_ids == set()

    # Fire + ice -> water
    ice = DamageEffect(
        owner_id="p2", element="ice",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=100.0, y=100.0, radius=30.0),
        duration=1.0, tick_interval=0.0, amount=0.0,
    )
    result = detect_reactions([spawn_effect(fire), spawn_effect(ice)])
    assert len(result.new_effects) == 1
    assert result.new_effects[0].element == "water"

    print("elemental_reactions: OK")
