from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from client.magic.primitives import Arrow, ArrowWithBase, Segment
from client.magic.recognition.complex_composer_arrow import ArrowComplexComposer
from client.magic.recognition.complex_composer_types import CompositionResult, PrimitiveEntry
from client.magic.recognition.preprocessing import clamp, euclidean_distance, point_to_segment_distance
from client.magic.recognition.types import NormalizedStroke

Point = tuple[float, float]


@dataclass(slots=True)
class _ArrowCandidate:
    primitive: Arrow
    consumed_strokes: frozenset[int]
    priority: float


@dataclass(slots=True)
class _BaseMatch:
    segment_entry: PrimitiveEntry
    start: Point
    end: Point
    score: float
    length: float


class ArrowWithBaseComplexComposer:
    """
    Composeur multi-strokes pour la forme ArrowWithBase.
    Cas gérés:
    - Arrow (mono ou multi-strokes) + Segment de base proche du tail.
    """

    def __init__(self, arrow_composer: ArrowComplexComposer | None = None) -> None:
        self._arrow_composer = arrow_composer or ArrowComplexComposer()

    def compose(
        self,
        primitive_entries: Sequence[PrimitiveEntry],
        normalized_strokes: Mapping[int, NormalizedStroke],
    ) -> list[CompositionResult]:
        segments = [entry for entry in primitive_entries if isinstance(entry.primitive, Segment)]
        existing_arrow_with_base_strokes = {
            entry.stroke_index
            for entry in primitive_entries
            if isinstance(entry.primitive, ArrowWithBase)
        }

        arrow_candidates = self._collect_arrow_candidates(primitive_entries, normalized_strokes)
        if not arrow_candidates or not segments:
            return []

        candidates: list[CompositionResult] = []
        for arrow_candidate in arrow_candidates:
            if any(
                stroke_index in existing_arrow_with_base_strokes
                for stroke_index in arrow_candidate.consumed_strokes
            ):
                continue

            base_match = self._best_base_match(
                arrow_candidate=arrow_candidate,
                segments=segments,
            )
            if base_match is None:
                continue

            score = clamp(arrow_candidate.priority * 0.58 + base_match.score * 0.42 + 0.04)
            if score < 0.60:
                continue

            arrow = arrow_candidate.primitive
            primitive = ArrowWithBase(
                _points=[
                    tuple(arrow.tail),
                    tuple(arrow.tip),
                    tuple(arrow.left_head),
                    tuple(arrow.tip),
                    tuple(arrow.right_head),
                    tuple(arrow.tail),
                    tuple(base_match.start),
                    tuple(base_match.end),
                ],
                tail=tuple(arrow.tail),
                tip=tuple(arrow.tip),
                left_head=tuple(arrow.left_head),
                right_head=tuple(arrow.right_head),
                base_start=tuple(base_match.start),
                base_end=tuple(base_match.end),
                confidence=score,
                source="complex",
                meta={
                    "recognition_score": float(score),
                    "recognition_source": "complex",
                    "base_score": float(base_match.score),
                    "base_length": float(base_match.length),
                    "arrow_score": float(arrow_candidate.priority),
                },
            )

            consumed = set(arrow_candidate.consumed_strokes)
            consumed.add(base_match.segment_entry.stroke_index)
            candidates.append(
                CompositionResult(
                    label="arrow_with_base",
                    primitive=primitive,
                    consumed_stroke_indices=frozenset(consumed),
                    priority=score,
                )
            )

        return self._dedupe_candidates(candidates)

    def _collect_arrow_candidates(
        self,
        primitive_entries: Sequence[PrimitiveEntry],
        normalized_strokes: Mapping[int, NormalizedStroke],
    ) -> list[_ArrowCandidate]:
        best_by_consumed: dict[frozenset[int], _ArrowCandidate] = {}

        for entry in primitive_entries:
            if not isinstance(entry.primitive, Arrow):
                continue
            consumed = frozenset({entry.stroke_index})
            candidate = _ArrowCandidate(
                primitive=entry.primitive,
                consumed_strokes=consumed,
                priority=self._coerce_priority(getattr(entry.primitive, "confidence", 0.62), fallback=0.62),
            )
            current = best_by_consumed.get(consumed)
            if current is None or candidate.priority > current.priority:
                best_by_consumed[consumed] = candidate

        for composed in self._arrow_composer.compose(primitive_entries, normalized_strokes):
            if not isinstance(composed.primitive, Arrow):
                continue
            consumed = frozenset(composed.consumed_stroke_indices)
            if not consumed:
                continue
            candidate = _ArrowCandidate(
                primitive=composed.primitive,
                consumed_strokes=consumed,
                priority=self._coerce_priority(composed.priority, fallback=0.62),
            )
            current = best_by_consumed.get(consumed)
            if current is None or candidate.priority > current.priority:
                best_by_consumed[consumed] = candidate

        return sorted(best_by_consumed.values(), key=lambda item: item.priority, reverse=True)

    def _best_base_match(
        self,
        *,
        arrow_candidate: _ArrowCandidate,
        segments: Sequence[PrimitiveEntry],
    ) -> _BaseMatch | None:
        best: _BaseMatch | None = None
        for segment_entry in segments:
            if segment_entry.stroke_index in arrow_candidate.consumed_strokes:
                continue

            scored = self._score_segment_as_base(
                arrow=arrow_candidate.primitive,
                segment=segment_entry.primitive,
            )
            if scored is None:
                continue
            start, end, score, length = scored
            candidate = _BaseMatch(
                segment_entry=segment_entry,
                start=start,
                end=end,
                score=score,
                length=length,
            )
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    def _score_segment_as_base(
        self,
        *,
        arrow: Arrow,
        segment: Segment,
    ) -> tuple[Point, Point, float, float] | None:
        tail = (float(arrow.tail[0]), float(arrow.tail[1]))
        tip = (float(arrow.tip[0]), float(arrow.tip[1]))
        shaft_length = euclidean_distance(tail, tip)
        if shaft_length <= 8.0:
            return None

        shaft_dir = self._normalize((tip[0] - tail[0], tip[1] - tail[1]))
        seg_start = (float(segment.start[0]), float(segment.start[1]))
        seg_end = (float(segment.end[0]), float(segment.end[1]))
        seg_vec = (seg_end[0] - seg_start[0], seg_end[1] - seg_start[1])
        seg_length = math.hypot(seg_vec[0], seg_vec[1])

        min_length = max(8.0, shaft_length * 0.08)
        max_length = max(18.0, shaft_length * 0.78)
        if seg_length < min_length or seg_length > max_length:
            return None

        seg_dir = self._normalize(seg_vec)
        abs_dot = abs(self._dot(seg_dir, shaft_dir))
        if abs_dot > 0.52:
            return None
        perpendicular_score = clamp(1.0 - abs_dot)

        midpoint = ((seg_start[0] + seg_end[0]) * 0.5, (seg_start[1] + seg_end[1]) * 0.5)
        tail_distance = euclidean_distance(midpoint, tail)
        max_tail_distance = max(18.0, shaft_length * 0.34)
        if tail_distance > max_tail_distance:
            return None
        tail_score = clamp(1.0 - tail_distance / max_tail_distance)

        line_distance = point_to_segment_distance(tail, seg_start, seg_end)
        max_line_distance = max(10.0, shaft_length * 0.12)
        if line_distance > max_line_distance:
            return None
        line_score = clamp(1.0 - line_distance / max_line_distance)

        projection = (midpoint[0] - tail[0]) * shaft_dir[0] + (midpoint[1] - tail[1]) * shaft_dir[1]
        if projection < -shaft_length * 0.30 or projection > shaft_length * 0.45:
            return None
        projection_score = clamp(1.0 - abs(projection) / max(shaft_length * 0.45, 1e-6))

        ratio = seg_length / max(shaft_length, 1e-6)
        if ratio < 0.10 or ratio > 0.82:
            return None
        ratio_score = clamp(1.0 - abs(ratio - 0.26) / 0.26)

        score = clamp(
            perpendicular_score * 0.34
            + tail_score * 0.22
            + line_score * 0.18
            + projection_score * 0.14
            + ratio_score * 0.12
        )
        if score < 0.56:
            return None

        base_start, base_end = self._orient_base_points(seg_start, seg_end, tail, shaft_dir)
        return base_start, base_end, score, seg_length

    @staticmethod
    def _orient_base_points(
        start: Point,
        end: Point,
        tail: Point,
        shaft_dir: Point,
    ) -> tuple[Point, Point]:
        rel_start = (start[0] - tail[0], start[1] - tail[1])
        rel_end = (end[0] - tail[0], end[1] - tail[1])
        cross_start = ArrowWithBaseComplexComposer._cross(shaft_dir, rel_start)
        cross_end = ArrowWithBaseComplexComposer._cross(shaft_dir, rel_end)
        if cross_start >= cross_end:
            return start, end
        return end, start

    @staticmethod
    def _coerce_priority(value: object, fallback: float) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = fallback
        return clamp(numeric)

    @staticmethod
    def _dot(a: Point, b: Point) -> float:
        return a[0] * b[0] + a[1] * b[1]

    @staticmethod
    def _cross(a: Point, b: Point) -> float:
        return a[0] * b[1] - a[1] * b[0]

    @staticmethod
    def _normalize(vector: Point) -> Point:
        length = math.hypot(vector[0], vector[1])
        if length <= 1e-9:
            return (0.0, 0.0)
        return (vector[0] / length, vector[1] / length)

    @staticmethod
    def _dedupe_candidates(candidates: list[CompositionResult]) -> list[CompositionResult]:
        best_by_consumed: dict[frozenset[int], CompositionResult] = {}
        for candidate in candidates:
            current = best_by_consumed.get(candidate.consumed_stroke_indices)
            if current is None or candidate.priority > current.priority:
                best_by_consumed[candidate.consumed_stroke_indices] = candidate
        return sorted(best_by_consumed.values(), key=lambda item: item.priority, reverse=True)
