from __future__ import annotations

from typing import Any, Sequence

from client.magic.primitives import Segment
from client.magic.recognition.candidate_fusion import CandidateFusionPolicy
from client.magic.recognition.complex_composer_arrow import ArrowComplexComposer
from client.magic.recognition.complex_composer_arrow_with_base import ArrowWithBaseComplexComposer
from client.magic.recognition.complex_composer_rune_fire import FireRuneComplexComposer
from client.magic.recognition.complex_composer_engine import ComplexCompositionEngine
from client.magic.recognition.complex_composer_types import ComplexShapeComposer, PrimitiveEntry
from client.magic.recognition.default_shapes import build_default_shape_registry
from client.magic.recognition.dollar_one import DollarOneRecognizer
from client.magic.recognition.heuristic import HeuristicPrimitiveRecognizer
from client.magic.recognition.preprocessing import (
    clamp,
    dedupe_consecutive,
    euclidean_distance,
    normalize_stroke,
    rdp,
    turn_angle,
)
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
        complex_composers: Sequence[tuple[str, ComplexShapeComposer]] | None = None,
    ):
        self.config = config or RecognitionConfig()
        self.heuristic = heuristic or HeuristicPrimitiveRecognizer()
        self.dollar_one = dollar_one or DollarOneRecognizer()
        self.shape_registry = shape_registry or build_default_shape_registry(self.config)
        self._fusion_policy = CandidateFusionPolicy(
            shape_registry=self.shape_registry,
            config=self.config,
        )
        self._complex_engine = ComplexCompositionEngine(
            shape_registry=self.shape_registry,
            config=self.config,
        )

        default_composers = complex_composers or (
            ("rune_fire", FireRuneComplexComposer()),
            ("arrow_with_base", ArrowWithBaseComplexComposer()),
            ("arrow", ArrowComplexComposer()),
        )
        for label, composer in default_composers:
            self.register_complex_composer(label, composer)

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

    def register_complex_composer(self, label: str, composer: ComplexShapeComposer) -> None:
        self._complex_engine.register_composer(label, composer)

    def recognize_strokes(self, strokes: Sequence[Sequence[Any]]) -> list[Any]:
        normalized_strokes: dict[int, NormalizedStroke] = {}
        primitive_entries: list[PrimitiveEntry] = []

        for stroke_index, raw_stroke in enumerate(strokes):
            stroke = normalize_stroke(
                raw_stroke,
                min_sample_distance=self.config.min_sample_distance,
                closed_ratio=self.config.closed_ratio,
            )
            if stroke is None:
                continue
            normalized_strokes[stroke_index] = stroke
            primitive = self._recognize_normalized_stroke(stroke)
            if self._should_split_stroke_into_segments(stroke, primitive):
                split_segments = self._decompose_stroke_into_segments(stroke)
                if split_segments:
                    for segment in split_segments:
                        primitive_entries.append(PrimitiveEntry(primitive=segment, stroke_index=stroke_index))
                    continue
            if primitive is not None:
                primitive_entries.append(PrimitiveEntry(primitive=primitive, stroke_index=stroke_index))

        merged_entries = self._complex_engine.compose(primitive_entries, normalized_strokes)
        return [entry.primitive for entry in merged_entries]

    def recognize_stroke(self, raw_stroke: Sequence[Any]) -> Any | None:
        stroke = normalize_stroke(
            raw_stroke,
            min_sample_distance=self.config.min_sample_distance,
            closed_ratio=self.config.closed_ratio,
        )
        if stroke is None:
            return None
        return self._recognize_normalized_stroke(stroke)

    def _recognize_normalized_stroke(self, stroke: NormalizedStroke) -> Any | None:
        heuristic_candidates = self.heuristic.recognize(stroke)
        dollar_candidate = self.dollar_one.recognize(stroke.points, is_closed=stroke.is_closed)
        merged = self._fusion_policy.merge(stroke, heuristic_candidates, dollar_candidate)
        if merged is None:
            return None

        return self._build_primitive(stroke, merged)

    def _should_split_stroke_into_segments(
        self,
        stroke: NormalizedStroke,
        primitive: Any | None,
    ) -> bool:
        if stroke.is_closed:
            return False
        if primitive is None:
            return True
        return isinstance(primitive, Segment)

    def _decompose_stroke_into_segments(self, stroke: NormalizedStroke) -> list[Segment]:
        vertices = self._extract_polyline_vertices(stroke)
        if len(vertices) < 3:
            return []

        direct = euclidean_distance(vertices[0], vertices[-1])
        if direct <= 1e-6:
            return []
        polyline_path = sum(euclidean_distance(a, b) for a, b in zip(vertices, vertices[1:]))
        path_ratio = polyline_path / max(direct, 1e-6)
        if path_ratio < 1.08:
            return []

        turn_count = 0
        for idx in range(1, len(vertices) - 1):
            angle = turn_angle(vertices[idx - 1], vertices[idx], vertices[idx + 1])
            if angle >= 0.30:
                turn_count += 1
        if turn_count < 1:
            return []

        turn_score = clamp(turn_count / 4.0)
        path_score = clamp((path_ratio - 1.05) / 0.75)
        confidence = clamp(0.55 + turn_score * 0.25 + path_score * 0.20)

        min_segment_length = max(8.0, stroke.diagonal * 0.045)
        segments: list[Segment] = []
        for start, end in zip(vertices, vertices[1:]):
            if euclidean_distance(start, end) < min_segment_length:
                continue
            segments.append(
                Segment(
                    start=tuple(start),
                    end=tuple(end),
                    confidence=confidence,
                    source="polyline",
                    meta=self._build_stroke_meta(stroke, confidence=confidence, source="polyline"),
                )
            )
        if len(segments) < 2:
            return []
        return segments

    def _extract_polyline_vertices(self, stroke: NormalizedStroke) -> list[Point]:
        points = list(stroke.points)
        if len(points) < 4:
            return []

        epsilon = max(2.0, stroke.path_length * 0.03)
        simplified = rdp(points, epsilon=epsilon)
        simplified = dedupe_consecutive(simplified, tolerance=1.2)
        if simplified and simplified[0] != points[0]:
            simplified.insert(0, points[0])
        if simplified and simplified[-1] != points[-1]:
            simplified.append(points[-1])
        if len(simplified) < 3:
            return []

        min_leg = max(10.0, stroke.diagonal * 0.06)
        kept: list[Point] = [simplified[0]]
        for idx in range(1, len(simplified) - 1):
            a = kept[-1]
            b = simplified[idx]
            c = simplified[idx + 1]
            len_ab = euclidean_distance(a, b)
            len_bc = euclidean_distance(b, c)
            if len_ab < min_leg * 0.4 or len_bc < min_leg * 0.4:
                continue
            angle = turn_angle(a, b, c)
            if angle >= 0.26:
                kept.append(b)
        kept.append(simplified[-1])
        kept = dedupe_consecutive(kept, tolerance=2.0)
        return kept

    def _build_primitive(self, stroke: NormalizedStroke, winner: RecognizerResult) -> Any | None:
        shape = self.shape_registry.get(winner.label)
        if shape is None:
            return None
        primitive = shape.builder(stroke, winner)
        if primitive is None:
            return None

        if hasattr(primitive, "meta"):
            current_meta = getattr(primitive, "meta", None)
            if not isinstance(current_meta, dict):
                current_meta = {}
            fallback = self._build_stroke_meta(stroke, confidence=winner.score, source=winner.source)
            for key, value in fallback.items():
                current_meta.setdefault(key, value)
            primitive.meta = current_meta
        return primitive

    @staticmethod
    def _build_stroke_meta(
        stroke: NormalizedStroke,
        *,
        confidence: float,
        source: str,
    ) -> dict[str, float | int | str | bool]:
        meta: dict[str, float | int | str | bool] = {
            "recognition_score": float(confidence),
            "recognition_source": source,
            "stroke_closed": bool(stroke.is_closed),
            "stroke_path_length": float(stroke.path_length),
            "stroke_diagonal": float(stroke.diagonal),
        }
        for key, value in (stroke.features or {}).items():
            if isinstance(value, (int, float)):
                meta[f"drawing_{key}"] = float(value)
        return meta
