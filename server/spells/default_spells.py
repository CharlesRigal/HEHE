from __future__ import annotations

from server.spells import FIRE_RUNE_SERVER_DEFINITION
from server.spells.types import ServerSpellRegistry


def register_default_spells(registry: ServerSpellRegistry) -> ServerSpellRegistry:
    registry.register(FIRE_RUNE_SERVER_DEFINITION)
    return registry


def build_default_spell_registry() -> ServerSpellRegistry:
    return register_default_spells(ServerSpellRegistry())
