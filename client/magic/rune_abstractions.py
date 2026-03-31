from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from client.magic.spell_types import OrderedSymbol, SpellDraft, SpellModifier, SpellModel


class RuneArchetype(ABC):
    """
    Contrat abstrait d'une rune.
    Chaque rune sait:
    - quel type de primitive la déclenche,
    - construire son SpellModel,
    - (optionnellement) l'exécuter côté client.
    """

    @property
    @abstractmethod
    def spell_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def primary_primitive_type(self) -> type[Any]:
        raise NotImplementedError

    @abstractmethod
    def build_spell(self, symbol: OrderedSymbol, draft: SpellDraft) -> SpellModel | None:
        raise NotImplementedError

    def execute_client(self, game: Any, spell: SpellModel) -> None:
        _ = game
        _ = spell
        return None

    def has_client_executor(self) -> bool:
        return False

    def to_definition(self) -> "RuneDefinition":
        from client.magic.rune_registry import RuneDefinition

        execute = self.execute_client if self.has_client_executor() else None
        return RuneDefinition(
            spell_id=self.spell_id,
            primary_primitive_type=self.primary_primitive_type,
            build_spell=self.build_spell,
            execute_client=execute,
        )


class ModifierArchetype(ABC):
    """
    Contrat abstrait d'un modificateur de sort.
    """

    modifier_id: str

    @abstractmethod
    def supports(self, primitive: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    def build(self, symbol: OrderedSymbol) -> SpellModifier:
        raise NotImplementedError


@dataclass(slots=True, frozen=True)
class FunctionalModifierArchetype(ModifierArchetype):
    """
    Adaptateur pour conserver l'API factory existante tout en passant
    sur une architecture de modificateurs orientée classes.
    """

    modifier_id: str
    primitive_type: type[Any]
    factory: Callable[[OrderedSymbol], SpellModifier]

    def supports(self, primitive: Any) -> bool:
        return isinstance(primitive, self.primitive_type)

    def build(self, symbol: OrderedSymbol) -> SpellModifier:
        return self.factory(symbol)
