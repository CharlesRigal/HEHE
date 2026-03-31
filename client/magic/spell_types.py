from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OrderedSymbol:
    symbol_index: int
    primitive: Any
    ordinal: int
    total: int
    drawing_features: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class SpellDraft:
    anchor_circle_index: int
    center: tuple[float, float]
    anchor_radius: float
    ordered_symbols: list[OrderedSymbol]
    drawing_features: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class SpellModifier:
    modifier_id: str
    source_symbol_index: int
    ordinal: int
    total: int
    payload: dict[str, float | int | str | bool]

    def to_network_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.modifier_id,
            "source_symbol_index": self.source_symbol_index,
            "ordinal": self.ordinal,
            "total": self.total,
        }
        if self.payload:
            data["payload"] = dict(self.payload)
        return data


@dataclass(slots=True)
class SpellModel:
    spell_id: str
    anchor_circle_index: int
    center: tuple[float, float]
    params: dict[str, float | int | str | bool]
    modifiers: list[SpellModifier]
    ordered_symbols: list[OrderedSymbol]
    drawing_features: dict[str, float] = field(default_factory=dict)

    def get_float(self, key: str, default: float) -> float:
        value = self.params.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def to_cast_message(self) -> dict[str, Any]:
        return {
            "t": "cast_spell",
            "spell_id": self.spell_id,
            "payload": dict(self.params),
            "modifiers": [modifier.to_network_dict() for modifier in self.modifiers],
        }
