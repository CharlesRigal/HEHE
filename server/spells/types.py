from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator

ServerCastHandler = Callable[[Any, str, dict[str, Any], list[dict[str, Any]]], None]
ServerTickHandler = Callable[[Any, dict[str, Any]], None]


@dataclass(slots=True, frozen=True)
class ServerSpellDefinition:
    spell_id: str
    cast_handler: ServerCastHandler
    tick_handler: ServerTickHandler | None = None


class ServerSpellRegistry:
    def __init__(self) -> None:
        self._ordered: list[ServerSpellDefinition] = []
        self._by_spell_id: dict[str, ServerSpellDefinition] = {}

    def register(self, definition: ServerSpellDefinition) -> None:
        existing = self._by_spell_id.get(definition.spell_id)
        if existing is not None:
            self._ordered = [item for item in self._ordered if item.spell_id != definition.spell_id]
        self._ordered.append(definition)
        self._by_spell_id[definition.spell_id] = definition

    def iter_definitions(self) -> Iterator[ServerSpellDefinition]:
        yield from self._ordered

    def get_cast_handler(self, spell_id: str) -> ServerCastHandler | None:
        definition = self._by_spell_id.get(spell_id)
        if definition is None:
            return None
        return definition.cast_handler

    def get_tick_handler(self, spell_id: str) -> ServerTickHandler | None:
        definition = self._by_spell_id.get(spell_id)
        if definition is None:
            return None
        return definition.tick_handler
