from __future__ import annotations

from server.spells import (
    FIRE_RUNE_SERVER_DEFINITION,
    FIRE_PROJECTILE_SERVER_DEFINITION,
    LIGHTNING_RUNE_SERVER_DEFINITION,
    PARAMETRIC_SPELL_DEFINITION,
)
from server.spells.types import ServerSpellRegistry


def register_default_spells(registry: ServerSpellRegistry) -> ServerSpellRegistry:
    registry.register(FIRE_RUNE_SERVER_DEFINITION)
    registry.register(FIRE_PROJECTILE_SERVER_DEFINITION)
    registry.register(LIGHTNING_RUNE_SERVER_DEFINITION)
    registry.register(PARAMETRIC_SPELL_DEFINITION)
    return registry


def build_default_spell_registry() -> ServerSpellRegistry:
    return register_default_spells(ServerSpellRegistry())
