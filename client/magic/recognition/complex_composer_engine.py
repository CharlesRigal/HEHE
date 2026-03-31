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
            consumed_entries = [
                entry for entry in primitive_entries if entry.stroke_index in composition.consumed_stroke_indices
            ]
            self._enrich_composed_primitive_meta(
                composition.primitive,
                label=composition.label,
                priority=composition.priority,
                consumed_strokes=composition.consumed_stroke_indices,
                consumed_entries=consumed_entries,
                normalized_strokes=normalized_strokes,
            )
            remaining_entries.append(
                PrimitiveEntry(
                    primitive=composition.primitive,
                    stroke_index=min(composition.consumed_stroke_indices),
                )
            )
        return sorted(remaining_entries, key=lambda entry: entry.stroke_index)

    @staticmethod
    def _enrich_composed_primitive_meta(
        primitive: object,
        *,
        label: str,
        priority: float,
        consumed_strokes: frozenset[int],
        consumed_entries: list[PrimitiveEntry],
        normalized_strokes: dict[int, NormalizedStroke],
    ) -> None:
        if not hasattr(primitive, "meta"):
            return

        existing_meta = getattr(primitive, "meta", None)
        if not isinstance(existing_meta, dict):
            existing_meta = {}

        sums: dict[str, float] = {}
        counts: dict[str, int] = {}

        def add_numeric(key: str, value: object) -> None:
            if not isinstance(value, (int, float)):
                return
            numeric = float(value)
            sums[key] = sums.get(key, 0.0) + numeric
            counts[key] = counts.get(key, 0) + 1

        for entry in consumed_entries:
            entry_meta = getattr(entry.primitive, "meta", None)
            if isinstance(entry_meta, dict):
                for key, value in entry_meta.items():
                    add_numeric(key, value)

        for stroke_index in consumed_strokes:
            stroke = normalized_strokes.get(stroke_index)
            if stroke is None:
                continue
            for key, value in (stroke.features or {}).items():
                add_numeric(f"drawing_{key}", value)
            add_numeric("stroke_path_length", stroke.path_length)
            add_numeric("stroke_diagonal", stroke.diagonal)

        for key, total in sums.items():
            count = max(1, counts.get(key, 1))
            existing_meta.setdefault(key, total / count)

        existing_meta.setdefault("composition_label", label)
        existing_meta.setdefault("composition_priority", float(priority))
        existing_meta.setdefault("composition_strokes", float(len(consumed_strokes)))
        primitive.meta = existing_meta
