from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator

from client.magic.rune_abstractions import RuneArchetype
from client.magic.spell_types import OrderedSymbol, SpellDraft, SpellModel

RuneBuildHandler = Callable[[OrderedSymbol, SpellDraft], SpellModel | None]
RuneExecuteHandler = Callable[[Any, SpellModel], None]


@dataclass(slots=True, frozen=True)
class RuneDefinition:
    spell_id: str
    primary_primitive_type: type[Any]
    build_spell: RuneBuildHandler
    execute_client: RuneExecuteHandler | None = None


class RuneRegistry:
    def __init__(self) -> None:
        self._ordered: list[RuneDefinition] = []
        self._by_spell_id: dict[str, RuneDefinition] = {}

    def register(self, definition: RuneDefinition | RuneArchetype) -> None:
        resolved = definition.to_definition() if isinstance(definition, RuneArchetype) else definition
        existing = self._by_spell_id.get(resolved.spell_id)
        if existing is not None:
            self._ordered = [item for item in self._ordered if item.spell_id != resolved.spell_id]
        self._ordered.append(resolved)
        self._by_spell_id[resolved.spell_id] = resolved

    def get_by_spell_id(self, spell_id: str) -> RuneDefinition | None:
        return self._by_spell_id.get(spell_id)

    def iter_definitions(self) -> Iterator[RuneDefinition]:
        yield from self._ordered

    def iter_primary_matches(self, primitive: Any) -> Iterator[RuneDefinition]:
        for definition in self._ordered:
            if isinstance(primitive, definition.primary_primitive_type):
                yield definition
