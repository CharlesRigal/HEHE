from __future__ import annotations

from typing import Any, Callable

from client.magic.default_runes import build_default_rune_registry
from client.magic.rune_registry import RuneRegistry
from client.magic.spell_types import SpellModel


class ClientSpellExecutionPipeline:
    """
    Exécution gameplay côté client des sorts résolus par le pipeline magique.
    Le dispatch est piloté par `spell_id` via registre, pour rester extensible.
    """

    def __init__(self, rune_registry: RuneRegistry | None = None) -> None:
        self._handlers: dict[str, Callable[[Any, SpellModel], None]] = {}
        self.rune_registry = rune_registry or build_default_rune_registry()
        self._register_default_handlers()

    def register(self, spell_id: str, handler: Callable[[Any, SpellModel], None]) -> None:
        self._handlers[spell_id] = handler

    def execute(self, game: Any, spell: object) -> None:
        if not isinstance(spell, SpellModel):
            return
        handler = self._handlers.get(spell.spell_id)
        if handler is None:
            return
        handler(game, spell)

    def _register_default_handlers(self) -> None:
        for definition in self.rune_registry.iter_definitions():
            if definition.execute_client is None:
                continue
            self.register(definition.spell_id, definition.execute_client)
