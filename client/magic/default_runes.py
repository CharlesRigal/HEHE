from __future__ import annotations

from client.magic.rune_registry import RuneRegistry
from client.magic.runes import FIRE_RUNE


def register_default_runes(registry: RuneRegistry) -> RuneRegistry:
    registry.register(FIRE_RUNE)
    return registry


def build_default_rune_registry() -> RuneRegistry:
    return register_default_runes(RuneRegistry())
