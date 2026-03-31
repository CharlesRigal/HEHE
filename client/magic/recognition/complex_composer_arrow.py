from __future__ import annotations

import math
from typing import Mapping, Sequence

from client.magic.primitives import Arrow, Segment, Triangle
from client.magic.recognition.complex_composer_types import CompositionResult, PrimitiveEntry
from client.magic.recognition.preprocessing import clamp, dedupe_consecutive, euclidean_distance, rdp
from client.magic.recognition.types import NormalizedStroke

Point = tuple[float, float]


class ArrowComplexComposer:
    """
    Composeur multi-strokes pour la forme Arrow.
    Cas gérés:
    - Segment + Triangle
    - Segment + stroke en V (head stroke)
    """

    def compose(
        self,
        primitive_entries: Sequence[PrimitiveEntry],
        normalized_strokes: Mapping[int, NormalizedStroke],
    ) -> list[CompositionResult]:
        segments = [entry for entry in primitive_entries if isinstance(entry.primitive, Segment)]
        triangles = [entry for entry in primitive_entries if isinstance(entry.primitive, Triangle)]
        existing_arrow_strokes = {entry.stroke_index for entry in primitive_entries if isinstance(entry.primitive, Arrow)}

        candidates: list[CompositionResult] = []

        for segment_entry in segments:
            if segment_entry.stroke_index in existing_arrow_strokes:
                continue

            for triangle_entry in triangles:
                if triangle_entry.stroke_index == segment_entry.stroke_index:
                    continue
                if triangle_entry.stroke_index in existing_arrow_strokes:
                    continue

                arrow, score = self._build_from_segment_triangle(
                    segment=segment_entry.primitive,
                    triangle=triangle_entry.primitive,
                )
                if arrow is None or score < 0.54:
                    continue
                candidates.append(
                    CompositionResult(
                        label="arrow",
                        primitive=arrow,
                        consumed_stroke_indices=frozenset({segment_entry.stroke_index, triangle_entry.stroke_index}),
                        priority=score,
                    )
                )

            for stroke_index, head_stroke in normalized_strokes.items():
                if stroke_index == segment_entry.stroke_index:
                    continue
                if stroke_index in existing_arrow_strokes:
                    continue

                arrow, score = self._build_from_segment_and_head_stroke(
                    segment=segment_entry.primitive,
                    head_stroke=head_stroke,
                )
                if arrow is None or score < 0.56:
                    continue
                candidates.append(
                    CompositionResult(
                        label="arrow",
                        primitive=arrow,
                        consumed_stroke_indices=frozenset({segment_entry.stroke_index, stroke_index}),
                        priority=score,
                    )
                )

        return self._dedupe_candidates(candidates)

    @staticmethod
    def _dedupe_candidates(candidates: list[CompositionResult]) -> list[CompositionResult]:
        best_by_pair: dict[frozenset[int], CompositionResult] = {}
        for candidate in candidates:
            current = best_by_pair.get(candidate.consumed_stroke_indices)
            if current is None or candidate.priority > current.priority:
                best_by_pair[candidate.consumed_stroke_indices] = candidate
        return sorted(best_by_pair.values(), key=lambda item: item.priority, reverse=True)

    def _build_from_segment_triangle(
        self,
        segment: Segment,
        triangle: Triangle,
    ) -> tuple[Arrow | None, float]:
        vertices = [tuple(vertex) for vertex in triangle.vertices[:3]]
        if len(vertices) < 3:
            return None, 0.0

        best_arrow: Arrow | None = None
        best_score = 0.0

        for tip_endpoint, tail_endpoint in ((segment.start, segment.end), (segment.end, segment.start)):
            tip_vertex_idx = min(range(3), key=lambda idx: euclidean_distance(vertices[idx], tip_endpoint))
            tip_vertex = vertices[tip_vertex_idx]
            distance_tip_to_head = euclidean_distance(tip_vertex, tip_endpoint)
            segment_length = euclidean_distance(segment.start, segment.end)
            if distance_tip_to_head > max(26.0, segment_length * 0.5):
                continue

            wings = [vertices[idx] for idx in range(3) if idx != tip_vertex_idx]
            if len(wings) != 2:
                continue

            geometry = self._arrow_geometry_score(
                tail=tuple(tail_endpoint),
                tip=tuple(tip_vertex),
                wing_a=tuple(wings[0]),
                wing_b=tuple(wings[1]),
            )
            if geometry is None:
                continue

            left_head, right_head, geometry_score = geometry
            distance_score = clamp(1.0 - distance_tip_to_head / max(1e-6, segment_length * 0.6))
            score = clamp(geometry_score * 0.8 + distance_score * 0.2)

            arrow = Arrow(
                _points=[
                    tuple(tail_endpoint),
                    tuple(tip_vertex),
                    tuple(wings[0]),
                    tuple(tip_vertex),
                    tuple(wings[1]),
                ],
                tail=tuple(tail_endpoint),
                tip=tuple(tip_vertex),
                left_head=left_head,
                right_head=right_head,
                confidence=score,
                source="complex",
                meta={
                    "recognition_score": float(score),
                    "recognition_source": "complex",
                },
            )
            if score > best_score:
                best_score = score
                best_arrow = arrow

        return best_arrow, best_score

    def _build_from_segment_and_head_stroke(
        self,
        segment: Segment,
        head_stroke: NormalizedStroke,
    ) -> tuple[Arrow | None, float]:
        if head_stroke.is_closed:
            return None, 0.0
        if len(head_stroke.points) < 3:
            return None, 0.0

        head_candidates = self._extract_head_candidates(head_stroke)
        if not head_candidates:
            return None, 0.0

        segment_length = euclidean_distance(segment.start, segment.end)
        best_arrow: Arrow | None = None
        best_score = 0.0

        for tip, wing_a, wing_b, head_score in head_candidates:
            dist_start = euclidean_distance(tip, segment.start)
            dist_end = euclidean_distance(tip, segment.end)

            if dist_start <= dist_end:
                tail = tuple(segment.end)
                tip_attachment_dist = dist_start
            else:
                tail = tuple(segment.start)
                tip_attachment_dist = dist_end

            if tip_attachment_dist > max(24.0, head_stroke.diagonal * 0.24, segment_length * 0.32):
                continue

            geometry = self._arrow_geometry_score(
                tail=tail,
                tip=tip,
                wing_a=wing_a,
                wing_b=wing_b,
            )
            if geometry is None:
                continue

            left_head, right_head, geometry_score = geometry
            attach_score = clamp(1.0 - tip_attachment_dist / max(1e-6, segment_length * 0.45))
            score = clamp(geometry_score * 0.55 + head_score * 0.25 + attach_score * 0.20)

            arrow = Arrow(
                _points=[tail, tip, wing_a, tip, wing_b],
                tail=tail,
                tip=tip,
                left_head=left_head,
                right_head=right_head,
                confidence=score,
                source="complex",
                meta={
                    "recognition_score": float(score),
                    "recognition_source": "complex",
                },
            )
            if score > best_score:
                best_score = score
                best_arrow = arrow

        return best_arrow, best_score

    def _extract_head_candidates(
        self,
        stroke: NormalizedStroke,
    ) -> list[tuple[Point, Point, Point, float]]:
        points = self._simplify_points(stroke.points, stroke.path_length)
        if len(points) < 3:
            return []

        left_anchor = tuple(points[0])
        right_anchor = tuple(points[-1])
        if euclidean_distance(left_anchor, right_anchor) <= 2.0:
            return []

        candidates: list[tuple[Point, Point, Point, float]] = []
        for tip_index in range(1, len(points) - 1):
            tip = tuple(points[tip_index])
            left_vec = self._normalize((left_anchor[0] - tip[0], left_anchor[1] - tip[1]))
            right_vec = self._normalize((right_anchor[0] - tip[0], right_anchor[1] - tip[1]))
            left_len = euclidean_distance(left_anchor, tip)
            right_len = euclidean_distance(right_anchor, tip)

            min_len = max(8.0, stroke.diagonal * 0.12)
            if left_len < min_len or right_len < min_len:
                continue

            angle = self._angle_between(left_vec, right_vec)
            if angle < 0.32 or angle > 2.70:
                continue

            symmetry = clamp(1.0 - abs(left_len - right_len) / max(left_len, right_len, 1e-6))
            angle_score = clamp(1.0 - abs(angle - 1.15) / 1.15)
            score = clamp(symmetry * 0.45 + angle_score * 0.55)
            candidates.append((tip, left_anchor, right_anchor, score))

        candidates.sort(key=lambda item: item[3], reverse=True)
        return candidates[:5]

    def _arrow_geometry_score(
        self,
        tail: Point,
        tip: Point,
        wing_a: Point,
        wing_b: Point,
    ) -> tuple[Point, Point, float] | None:
        shaft_length = euclidean_distance(tail, tip)
        if shaft_length <= 8.0:
            return None

        shaft_dir = self._normalize((tip[0] - tail[0], tip[1] - tail[1]))
        vec_a = self._normalize((wing_a[0] - tip[0], wing_a[1] - tip[1]))
        vec_b = self._normalize((wing_b[0] - tip[0], wing_b[1] - tip[1]))
        len_a = euclidean_distance(wing_a, tip)
        len_b = euclidean_distance(wing_b, tip)

        min_wing = max(6.0, shaft_length * 0.08)
        max_wing = max(18.0, shaft_length * 0.70)
        if len_a < min_wing or len_b < min_wing or len_a > max_wing or len_b > max_wing:
            return None

        back_a = -self._dot(vec_a, shaft_dir)
        back_b = -self._dot(vec_b, shaft_dir)
        if back_a < 0.12 or back_b < 0.12:
            return None

        side_a = self._cross(shaft_dir, vec_a)
        side_b = self._cross(shaft_dir, vec_b)
        if abs(side_a) < 0.10 or abs(side_b) < 0.10:
            return None
        if side_a * side_b >= 0.0:
            return None

        opening = self._angle_between(vec_a, vec_b)
        if opening < 0.35 or opening > 2.70:
            return None

        symmetry = clamp(1.0 - abs(len_a - len_b) / max(len_a, len_b, 1e-6))
        back_score = clamp((back_a + back_b) * 0.5)
        side_score = clamp((abs(side_a) + abs(side_b)) * 0.5)
        opening_score = clamp(1.0 - abs(opening - 1.20) / 1.20)
        score = clamp(back_score * 0.30 + side_score * 0.25 + opening_score * 0.20 + symmetry * 0.25)

        left_head = wing_a if side_a > 0.0 else wing_b
        right_head = wing_b if side_a > 0.0 else wing_a
        return left_head, right_head, score

    def _simplify_points(self, points: Sequence[Point], total_path: float) -> list[Point]:
        epsilon = max(2.0, total_path * 0.03)
        simplified = rdp(points, epsilon=epsilon)
        return dedupe_consecutive(simplified, tolerance=1.2)

    @staticmethod
    def _normalize(vector: tuple[float, float]) -> tuple[float, float]:
        length = math.hypot(vector[0], vector[1])
        if length <= 1e-9:
            return (0.0, 0.0)
        return (vector[0] / length, vector[1] / length)

    @staticmethod
    def _dot(a: tuple[float, float], b: tuple[float, float]) -> float:
        return a[0] * b[0] + a[1] * b[1]

    @staticmethod
    def _cross(a: tuple[float, float], b: tuple[float, float]) -> float:
        return a[0] * b[1] - a[1] * b[0]

    @staticmethod
    def _angle_between(a: tuple[float, float], b: tuple[float, float]) -> float:
        dot_value = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
        return math.acos(dot_value)
