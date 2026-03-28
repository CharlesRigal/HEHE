from __future__ import annotations

from typing import Any, Sequence

from client.magic.recognition.default_shapes import build_default_shape_registry
from client.magic.recognition.dollar_one import DollarOneRecognizer
from client.magic.recognition.heuristic import HeuristicPrimitiveRecognizer
from client.magic.recognition.preprocessing import normalize_stroke
from client.magic.recognition.shape_registry import ShapeRegistry
from client.magic.recognition.types import (
    HeuristicDetector,
    NormalizedStroke,
    Point,
    RecognitionConfig,
    RecognizerResult,
    ShapeDefinition,
)


class PrimitiveRecognitionEngine:
    """
    Pipeline modulaire de reconnaissance:
    - normalisation des strokes
    - agrégation de candidats (heuristique + $1)
    - fusion/scoring via registre de formes
    - construction de primitive via builder dédié
    """

    def __init__(
        self,
        config: RecognitionConfig | None = None,
        heuristic: HeuristicPrimitiveRecognizer | None = None,
        dollar_one: DollarOneRecognizer | None = None,
        shape_registry: ShapeRegistry | None = None,
    ):
        self.config = config or RecognitionConfig()
        self.heuristic = heuristic or HeuristicPrimitiveRecognizer()
        self.dollar_one = dollar_one or DollarOneRecognizer()
        self.shape_registry = shape_registry or build_default_shape_registry(self.config)

    def register_shape(
        self,
        shape: ShapeDefinition,
        *,
        heuristic_detector: HeuristicDetector | None = None,
        dollar_templates: Sequence[Sequence[Point]] | None = None,
    ) -> None:
        self.shape_registry.register(shape)
        if heuristic_detector is not None:
            self.heuristic.register_rule(
                label=shape.label,
                detector=heuristic_detector,
                requires_closed=shape.requires_closed,
            )
        if dollar_templates:
            for template in dollar_templates:
                self.dollar_one.add_template(shape.label, template)

    def register_heuristic_rule(
        self,
        label: str,
        detector: HeuristicDetector,
        *,
        requires_closed: bool | None = None,
    ) -> None:
        self.heuristic.register_rule(label=label, detector=detector, requires_closed=requires_closed)

    def register_dollar_template(self, label: str, points: Sequence[Point]) -> None:
        canonical = self.shape_registry.canonical_label(label) or label.strip().lower()
        self.dollar_one.add_template(canonical, points)

    def recognize_strokes(self, strokes: Sequence[Sequence[Any]]) -> list[Any]:
        primitives: list[Any] = []
        for stroke in strokes:
            primitive = self.recognize_stroke(stroke)
            if primitive is not None:
                primitives.append(primitive)
        return primitives

    def recognize_stroke(self, raw_stroke: Sequence[Any]) -> Any | None:
        stroke = normalize_stroke(
            raw_stroke,
            min_sample_distance=self.config.min_sample_distance,
            closed_ratio=self.config.closed_ratio,
        )
        if stroke is None:
            return None

        heuristic_candidates = self.heuristic.recognize(stroke)
        dollar_candidate = self.dollar_one.recognize(stroke.points, is_closed=stroke.is_closed)
        merged = self._merge_candidates(stroke, heuristic_candidates, dollar_candidate)
        if merged is None:
            return None

        return self._build_primitive(stroke, merged)

    def _merge_candidates(
        self,
        stroke: NormalizedStroke,
        heuristic_candidates: list[RecognizerResult],
        dollar_candidate: RecognizerResult | None,
    ) -> RecognizerResult | None:
        by_label: dict[str, dict[str, Any]] = {}
        heuristic_labels: set[str] = set()

        for candidate in heuristic_candidates:
            canonical = self.shape_registry.canonical_label(candidate.label)
            if canonical is None:
                continue
            heuristic_labels.add(canonical)
            weight = self.config.get_source_weight(candidate.source, default=self.config.heuristic_weight)
            self._accumulate_candidate(by_label, canonical, candidate, weight)

        if dollar_candidate is not None:
            canonical = self.shape_registry.canonical_label(dollar_candidate.label)
            if canonical is not None:
                has_heuristic_for_label = canonical in heuristic_labels
                weight = self.config.get_source_weight("$1") if has_heuristic_for_label else self.config.fallback_source_weight
                dollar_payload = {"dollar": dollar_candidate.payload} if dollar_candidate.payload else {}
                self._accumulate_candidate(
                    by_label,
                    canonical,
                    RecognizerResult(
                        label=canonical,
                        score=dollar_candidate.score,
                        source="$1",
                        payload=dollar_payload,
                    ),
                    weight,
                )

        if not by_label:
            return None

        for label, slot in by_label.items():
            shape = self.shape_registry.get(label)
            if shape is None:
                continue
            if len(set(slot["sources"])) >= 2:
                slot["score"] = min(1.0, slot["score"] + shape.multi_source_bonus)
            if shape.requires_closed is True and not stroke.is_closed:
                slot["score"] *= shape.open_penalty

        best_label, best_slot = max(by_label.items(), key=lambda item: item[1]["score"])
        shape = self.shape_registry.get(best_label)
        if shape is None:
            return None
        threshold = self.config.get_shape_threshold(best_label, shape.threshold)
        best_score = best_slot["score"]

        if best_score < threshold:
            return None

        source = "+".join(sorted(set(best_slot["sources"]))) or "unknown"
        return RecognizerResult(
            label=best_label,
            score=best_score,
            source=source,
            payload=best_slot["payload"],
        )

    @staticmethod
    def _accumulate_candidate(
        by_label: dict[str, dict[str, Any]],
        label: str,
        candidate: RecognizerResult,
        weight: float,
    ) -> None:
        if weight <= 0.0:
            return
        slot = by_label.setdefault(label, {"score": 0.0, "payload": {}, "sources": []})
        slot["score"] += candidate.score * weight
        if candidate.payload:
            slot["payload"].update(candidate.payload)
        slot["sources"].append(candidate.source)

    def _build_primitive(self, stroke: NormalizedStroke, winner: RecognizerResult) -> Any | None:
        shape = self.shape_registry.get(winner.label)
        if shape is None:
            return None
        return shape.builder(stroke, winner)
