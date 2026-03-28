from __future__ import annotations

from typing import Iterable

from client.magic.recognition.types import ShapeDefinition


class ShapeRegistry:
    """
    Registre central des formes reconnues.
    Permet d'ajouter/surcharger des formes sans modifier la pipeline.
    """

    def __init__(self, shapes: Iterable[ShapeDefinition] | None = None):
        self._shapes: dict[str, ShapeDefinition] = {}
        self._aliases: dict[str, str] = {}
        if shapes is not None:
            for shape in shapes:
                self.register(shape)

    @staticmethod
    def _normalize(label: str) -> str:
        return (label or "").strip().lower()

    def register(self, shape: ShapeDefinition) -> None:
        canonical = self._normalize(shape.label)
        aliases = tuple(self._normalize(alias) for alias in shape.aliases if self._normalize(alias))
        normalized = ShapeDefinition(
            label=canonical,
            builder=shape.builder,
            threshold=shape.threshold,
            aliases=aliases,
            requires_closed=shape.requires_closed,
            open_penalty=shape.open_penalty,
            multi_source_bonus=shape.multi_source_bonus,
        )
        self._shapes[canonical] = normalized
        self._aliases[canonical] = canonical
        for alias in aliases:
            self._aliases[alias] = canonical

    def get(self, label: str) -> ShapeDefinition | None:
        canonical = self.canonical_label(label)
        if canonical is None:
            return None
        return self._shapes.get(canonical)

    def canonical_label(self, label: str | None) -> str | None:
        if label is None:
            return None
        key = self._normalize(label)
        if not key:
            return None
        return self._aliases.get(key, key if key in self._shapes else None)

    def labels(self) -> list[str]:
        return list(self._shapes.keys())

