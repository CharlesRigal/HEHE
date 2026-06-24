"""Binding : un effet peut se lier a une cible ou a un point d'ancrage.

Phase 5 : un Effect peut porter des champs optionnels de binding qui font
que le runtime repositionne la shape chaque tick en fonction d'une entite
ou d'une paire d'entites (link).

Mode A : follow target
  bind_target_id = "torch_01"  -> la shape suit la position de l'entite
                                  (utile pour une lévitation, un bouclier)

Mode B : link between two targets
  bind_source_id = "crystal_a"
  bind_target_id = "crystal_b" -> la shape se positionne au milieu des deux
                                  (transfert d'energie, batterie magique)

Le runtime applique `update_binding()` avant le tick de dispatch. Si la
cible est absente ou morte, le binding est rompu : on vide les champs et
l'effet continue sa vie normalement a sa derniere position.
"""
from __future__ import annotations

from typing import Any

from server.effects.effect_types import Effect


def has_binding(effect: Effect) -> bool:
    return bool(
        getattr(effect, "bind_target_id", None)
        or getattr(effect, "bind_source_id", None)
    )


def _find_entity_position(instance: Any, entity_id: str) -> tuple[float, float] | None:
    """Cherche l'entite parmi entities (post-ECS) + players.

    Fallback `interactive` et `enemies` pour compat retro des tests.
    """
    for ent in getattr(instance, "entities", []) or []:
        if ent.id == entity_id:
            if ent.combat is not None and not ent.combat.alive:
                return None
            return ent.body.x, ent.body.y

    for ent in getattr(instance, "interactive", []) or []:
        if ent.id == entity_id:
            return ent.body.x, ent.body.y

    players = getattr(instance, "players", {})
    player = players.get(entity_id)
    if player is not None and getattr(player, "is_alive", lambda: True)():
        return player.x, player.y

    enemies = getattr(instance, "enemies", {})
    enemy = enemies.get(entity_id)
    if enemy is not None and enemy.get("alive", True):
        return float(enemy["x"]), float(enemy["y"])

    return None


def update_binding(instance: Any, effect: Effect) -> None:
    """Reajuste la position de la shape selon le binding. No-op sinon."""
    target_id = getattr(effect, "bind_target_id", None)
    source_id = getattr(effect, "bind_source_id", None)

    if not target_id and not source_id:
        return

    target_pos = _find_entity_position(instance, target_id) if target_id else None
    source_pos = _find_entity_position(instance, source_id) if source_id else None

    if target_id and target_pos is None:
        # cible disparue -> rupture du lien
        effect.bind_target_id = None  # type: ignore[attr-defined]
        return
    if source_id and source_pos is None:
        effect.bind_source_id = None  # type: ignore[attr-defined]
        return

    if target_pos and source_pos:
        effect.shape.x = (target_pos[0] + source_pos[0]) * 0.5
        effect.shape.y = (target_pos[1] + source_pos[1]) * 0.5
    elif target_pos:
        effect.shape.x, effect.shape.y = target_pos


if __name__ == "__main__":
    from server.effects.effect_types import DamageEffect, EffectShape, ShapeKind

    class _Body:
        def __init__(self, x, y): self.x, self.y = x, y

    class _Ent:
        def __init__(self, eid, x, y):
            self.id = eid
            self.body = _Body(x, y)

    class _Inst:
        def __init__(self):
            self.interactive = [_Ent("a", 100.0, 200.0), _Ent("b", 300.0, 400.0)]
            self.players = {}
            self.enemies = {}

    inst = _Inst()

    # Follow A
    eff = DamageEffect(
        owner_id="p1", element="fire",
        shape=EffectShape(kind=ShapeKind.CIRCLE, x=0.0, y=0.0, radius=10.0),
        duration=1.0,
    )
    eff.bind_target_id = "a"  # type: ignore[attr-defined]
    update_binding(inst, eff)
    assert eff.shape.x == 100.0 and eff.shape.y == 200.0

    # Link A-B : midpoint
    eff.bind_source_id = "b"  # type: ignore[attr-defined]
    update_binding(inst, eff)
    assert eff.shape.x == 200.0 and eff.shape.y == 300.0

    # Target disparue -> rupture
    eff.bind_source_id = None  # type: ignore[attr-defined]
    eff.bind_target_id = "ghost"  # type: ignore[attr-defined]
    update_binding(inst, eff)
    assert getattr(eff, "bind_target_id") is None

    print("binding: OK")
