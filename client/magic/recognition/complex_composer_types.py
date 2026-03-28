from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from client.magic.recognition.types import NormalizedStroke


@dataclass(slots=True)
class PrimitiveEntry:
    primitive: Any
    stroke_index: int


@dataclass(slots=True)
class CompositionResult:
    label: str
    primitive: Any
    consumed_stroke_indices: frozenset[int]
    priority: float


class ComplexShapeComposer(Protocol):
    def compose(
        self,
        primitive_entries: Sequence[PrimitiveEntry],
        normalized_strokes: Mapping[int, NormalizedStroke],
    ) -> list[CompositionResult]:
        ...
