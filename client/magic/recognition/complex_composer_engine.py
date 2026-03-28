from __future__ import annotations

from client.magic.recognition.complex_composer_types import (
    ComplexShapeComposer,
    CompositionResult,
    PrimitiveEntry,
)
from client.magic.recognition.shape_registry import ShapeRegistry
from client.magic.recognition.types import NormalizedStroke, RecognitionConfig


class ComplexCompositionEngine:
    """
    Moteur générique de composition multi-strokes.
    - délègue la génération de candidats aux composeurs spécialisés
    - filtre via seuils configurés/registry
    - résout les conflits (greedy non-overlap)
    """

    def __init__(
        self,
        *,
        shape_registry: ShapeRegistry,
        config: RecognitionConfig,
    ) -> None:
        self.shape_registry = shape_registry
        self.config = config
        self._composers: list[tuple[str, ComplexShapeComposer]] = []

    def register_composer(self, label: str, composer: ComplexShapeComposer) -> None:
        canonical = self.shape_registry.canonical_label(label) or label.strip().lower()
        if not canonical:
            raise ValueError("Complex composer label must not be empty")
        self._composers = [
            (existing_label, existing_composer)
            for existing_label, existing_composer in self._composers
            if existing_label != canonical
        ]
        self._composers.append((canonical, composer))

    def compose(
        self,
        primitive_entries: list[PrimitiveEntry],
        normalized_strokes: dict[int, NormalizedStroke],
    ) -> list[PrimitiveEntry]:
        if not primitive_entries or not self._composers:
            return sorted(primitive_entries, key=lambda entry: entry.stroke_index)

        candidates: list[CompositionResult] = []
        for label, composer in self._composers:
            shape = self.shape_registry.get(label)
            if shape is None:
                continue
            for candidate in composer.compose(primitive_entries, normalized_strokes):
                canonical = self.shape_registry.canonical_label(candidate.label) or label
                canonical_shape = self.shape_registry.get(canonical)
                if canonical_shape is None:
                    continue
                threshold = self.config.get_shape_threshold(canonical, canonical_shape.threshold)
                if candidate.priority < threshold:
                    continue
                candidates.append(
                    CompositionResult(
                        label=canonical,
                        primitive=candidate.primitive,
                        consumed_stroke_indices=candidate.consumed_stroke_indices,
                        priority=candidate.priority,
                    )
                )

        if not candidates:
            return sorted(primitive_entries, key=lambda entry: entry.stroke_index)

        candidates.sort(
            key=lambda item: (
                -item.priority,
                -len(item.consumed_stroke_indices),
                min(item.consumed_stroke_indices),
            )
        )
        consumed_strokes: set[int] = set()
        selected: list[CompositionResult] = []
        for candidate in candidates:
            if not candidate.consumed_stroke_indices:
                continue
            if any(index in consumed_strokes for index in candidate.consumed_stroke_indices):
                continue
            selected.append(candidate)
            consumed_strokes.update(candidate.consumed_stroke_indices)

        if not selected:
            return sorted(primitive_entries, key=lambda entry: entry.stroke_index)

        remaining_entries = [
            entry for entry in primitive_entries if entry.stroke_index not in consumed_strokes
        ]
        for composition in selected:
            remaining_entries.append(
                PrimitiveEntry(
                    primitive=composition.primitive,
                    stroke_index=min(composition.consumed_stroke_indices),
                )
            )
        return sorted(remaining_entries, key=lambda entry: entry.stroke_index)
