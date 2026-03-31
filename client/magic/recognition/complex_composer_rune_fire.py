from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from client.magic.primitives import RuneFire, Segment, Triangle
from client.magic.recognition.complex_composer_types import CompositionResult, PrimitiveEntry
from client.magic.recognition.preprocessing import clamp, euclidean_distance, point_to_segment_distance
from client.magic.recognition.types import NormalizedStroke

Point = tuple[float, float]


@dataclass(slots=True)
class _SideCutMatch:
    side_index: int
    segment_entry: PrimitiveEntry
    score: float
    anchor_t: float
    anchor_point: Point


class FireRuneComplexComposer:
    """
    Composeur multi-strokes pour la rune de feu:
    - un triangle
    - trois segments qui coupent perpendiculairement chaque cote.
    """

    _MAX_MATCHES_PER_SIDE = 6

    def compose(
        self,
        primitive_entries: Sequence[PrimitiveEntry],
        normalized_strokes: Mapping[int, NormalizedStroke],
    ) -> list[CompositionResult]:
        _ = normalized_strokes
        triangles = [entry for entry in primitive_entries if isinstance(entry.primitive, Triangle)]
        segments = [entry for entry in primitive_entries if isinstance(entry.primitive, Segment)]
        existing_rune_strokes = {entry.stroke_index for entry in primitive_entries if isinstance(entry.primitive, RuneFire)}

        candidates: list[CompositionResult] = []
        for triangle_entry in triangles:
            if triangle_entry.stroke_index in existing_rune_strokes:
                continue

            vertices = [tuple(vertex) for vertex in triangle_entry.primitive.vertices[:3]]
            if len(vertices) < 3:
                continue

            side_matches = self._collect_side_matches(
                triangle_vertices=vertices,
                triangle_entry=triangle_entry,
                segment_entries=segments,
                existing_rune_strokes=existing_rune_strokes,
            )
            if not side_matches or any(not matches for matches in side_matches):
                continue

            for grouped in itertools.product(*side_matches):
                score = self._score_grouped_matches(grouped)
                if score < 0.58:
                    continue

                rune = self._build_rune_fire(vertices, grouped, score)
                consumed = {triangle_entry.stroke_index}
                consumed.update(match.segment_entry.stroke_index for match in grouped)
                candidates.append(
                    CompositionResult(
                        label="rune_fire",
                        primitive=rune,
                        consumed_stroke_indices=frozenset(consumed),
                        priority=score,
                    )
                )

        return self._dedupe_candidates(candidates)

    def _collect_side_matches(
        self,
        *,
        triangle_vertices: list[Point],
        triangle_entry: PrimitiveEntry,
        segment_entries: list[PrimitiveEntry],
        existing_rune_strokes: set[int],
    ) -> list[list[_SideCutMatch]]:
        side_matches: list[list[_SideCutMatch]] = [[], [], []]
        sides = self._triangle_sides(triangle_vertices)
        perimeter = sum(side[2] for side in sides)
        scale = max(18.0, perimeter / 3.0)

        for segment_entry in segment_entries:
            if segment_entry.stroke_index == triangle_entry.stroke_index:
                continue
            if segment_entry.stroke_index in existing_rune_strokes:
                continue

            segment = segment_entry.primitive
            for side_index, (side_start, side_end, side_length) in enumerate(sides):
                match = self._score_side_cut(
                    segment=segment,
                    side_start=side_start,
                    side_end=side_end,
                    side_length=side_length,
                    scale=scale,
                )
                if match is None:
                    continue

                side_matches[side_index].append(
                    _SideCutMatch(
                        side_index=side_index,
                        segment_entry=segment_entry,
                        score=match[0],
                        anchor_t=match[1],
                        anchor_point=match[2],
                    )
                )

        for side_index in range(3):
            matches = side_matches[side_index]
            matches.sort(key=lambda item: item.score, reverse=True)
            side_matches[side_index] = matches[: self._MAX_MATCHES_PER_SIDE]
        return side_matches

    def _score_side_cut(
        self,
        *,
        segment: Segment,
        side_start: Point,
        side_end: Point,
        side_length: float,
        scale: float,
    ) -> tuple[float, float, Point] | None:
        seg_start = tuple(segment.start)
        seg_end = tuple(segment.end)
        seg_length = euclidean_distance(seg_start, seg_end)

        min_length = max(8.0, scale * 0.10)
        max_length = max(16.0, side_length * 0.78)
        if seg_length < min_length or seg_length > max_length:
            return None

        side_dir = self._normalize((side_end[0] - side_start[0], side_end[1] - side_start[1]))
        seg_dir = self._normalize((seg_end[0] - seg_start[0], seg_end[1] - seg_start[1]))
        abs_dot = abs(self._dot(side_dir, seg_dir))
        if abs_dot > 0.38:
            return None
        perpendicular_score = clamp(1.0 - abs_dot)

        seg_mid = ((seg_start[0] + seg_end[0]) * 0.5, (seg_start[1] + seg_end[1]) * 0.5)
        mid_distance = point_to_segment_distance(seg_mid, side_start, side_end)
        max_mid_distance = max(7.0, scale * 0.11)
        if mid_distance > max_mid_distance:
            return None
        distance_score = clamp(1.0 - mid_distance / max_mid_distance)

        normal = (-side_dir[1], side_dir[0])
        rel_start = (seg_start[0] - side_start[0], seg_start[1] - side_start[1])
        rel_end = (seg_end[0] - side_start[0], seg_end[1] - side_start[1])
        d_start = self._dot(rel_start, normal)
        d_end = self._dot(rel_end, normal)

        signed_product = d_start * d_end
        cross_score = 1.0
        if signed_product > 0.0:
            cross_gap = min(abs(d_start), abs(d_end))
            max_cross_gap = max(6.0, scale * 0.09)
            if cross_gap > max_cross_gap:
                return None
            cross_score = clamp(1.0 - cross_gap / max_cross_gap)

        anchor_t, anchor = self._side_anchor(seg_start, seg_end, side_start, side_end)
        if anchor_t < 0.18 or anchor_t > 0.82:
            return None
        anchor_score = clamp(1.0 - abs(anchor_t - 0.5) / 0.34)

        length_ratio = seg_length / max(side_length, 1e-6)
        if length_ratio < 0.12 or length_ratio > 0.72:
            return None
        length_score = clamp(1.0 - abs(length_ratio - 0.30) / 0.30)

        score = clamp(
            perpendicular_score * 0.45
            + distance_score * 0.20
            + cross_score * 0.15
            + anchor_score * 0.12
            + length_score * 0.08
        )
        if score < 0.56:
            return None
        return score, anchor_t, anchor

    def _score_grouped_matches(self, grouped: Sequence[_SideCutMatch]) -> float:
        if len(grouped) != 3:
            return 0.0

        segment_strokes = [match.segment_entry.stroke_index for match in grouped]
        if len(set(segment_strokes)) < 2:
            return 0.0

        unique_entries = {
            (match.segment_entry.stroke_index, id(match.segment_entry.primitive))
            for match in grouped
        }
        if len(unique_entries) != 3:
            return 0.0

        scores = [match.score for match in grouped]
        avg = sum(scores) / 3.0
        spread = max(scores) - min(scores)
        balance = clamp(1.0 - spread / max(avg, 1e-6))

        anchors = [match.anchor_t for match in grouped]
        anchor_spread = max(anchors) - min(anchors)
        anchor_balance = clamp(1.0 - anchor_spread / 0.75)

        unique_stroke_score = 1.0 if len(set(segment_strokes)) == 3 else 0.78
        return clamp(avg * 0.72 + balance * 0.14 + anchor_balance * 0.06 + unique_stroke_score * 0.08)

    @staticmethod
    def _build_rune_fire(
        triangle_vertices: Sequence[Point],
        grouped: Sequence[_SideCutMatch],
        score: float,
    ) -> RuneFire:
        ordered = sorted(grouped, key=lambda match: match.side_index)
        cuts = [
            (tuple(match.segment_entry.primitive.start), tuple(match.segment_entry.primitive.end))
            for match in ordered
        ]
        points = [
            tuple(triangle_vertices[0]),
            tuple(triangle_vertices[1]),
            tuple(triangle_vertices[2]),
            tuple(triangle_vertices[0]),
        ]
        for start, end in cuts:
            points.extend([start, end])
        return RuneFire(
            _points=points,
            vertices=[tuple(vertex) for vertex in triangle_vertices[:3]],
            cuts=cuts,
            confidence=score,
            source="complex",
            meta={
                "recognition_score": float(score),
                "recognition_source": "complex",
            },
        )

    @staticmethod
    def _triangle_sides(vertices: Sequence[Point]) -> list[tuple[Point, Point, float]]:
        sides: list[tuple[Point, Point, float]] = []
        for idx in range(3):
            start = tuple(vertices[idx])
            end = tuple(vertices[(idx + 1) % 3])
            sides.append((start, end, euclidean_distance(start, end)))
        return sides

    @staticmethod
    def _side_anchor(
        seg_start: Point,
        seg_end: Point,
        side_start: Point,
        side_end: Point,
    ) -> tuple[float, Point]:
        intersection = FireRuneComplexComposer._segment_intersection(seg_start, seg_end, side_start, side_end)
        if intersection is not None:
            return FireRuneComplexComposer._project_t(intersection, side_start, side_end), intersection
        midpoint = ((seg_start[0] + seg_end[0]) * 0.5, (seg_start[1] + seg_end[1]) * 0.5)
        projected = FireRuneComplexComposer._project_point(midpoint, side_start, side_end)
        return FireRuneComplexComposer._project_t(projected, side_start, side_end), projected

    @staticmethod
    def _project_t(point: Point, line_start: Point, line_end: Point) -> float:
        vx = line_end[0] - line_start[0]
        vy = line_end[1] - line_start[1]
        denom = vx * vx + vy * vy
        if denom <= 1e-9:
            return 0.0
        t = ((point[0] - line_start[0]) * vx + (point[1] - line_start[1]) * vy) / denom
        return clamp(t)

    @staticmethod
    def _project_point(point: Point, line_start: Point, line_end: Point) -> Point:
        t = FireRuneComplexComposer._project_t(point, line_start, line_end)
        return (
            line_start[0] + (line_end[0] - line_start[0]) * t,
            line_start[1] + (line_end[1] - line_start[1]) * t,
        )

    @staticmethod
    def _segment_intersection(a1: Point, a2: Point, b1: Point, b2: Point) -> Point | None:
        ax = a2[0] - a1[0]
        ay = a2[1] - a1[1]
        bx = b2[0] - b1[0]
        by = b2[1] - b1[1]
        denom = ax * by - ay * bx
        if abs(denom) <= 1e-9:
            return None

        cx = b1[0] - a1[0]
        cy = b1[1] - a1[1]
        t = (cx * by - cy * bx) / denom
        u = (cx * ay - cy * ax) / denom
        if t < -1e-6 or t > 1.0 + 1e-6 or u < -1e-6 or u > 1.0 + 1e-6:
            return None
        return (a1[0] + ax * t, a1[1] + ay * t)

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
    def _dedupe_candidates(candidates: list[CompositionResult]) -> list[CompositionResult]:
        best_by_consumed: dict[frozenset[int], CompositionResult] = {}
        for candidate in candidates:
            current = best_by_consumed.get(candidate.consumed_stroke_indices)
            if current is None or candidate.priority > current.priority:
                best_by_consumed[candidate.consumed_stroke_indices] = candidate
        return sorted(best_by_consumed.values(), key=lambda item: item.priority, reverse=True)
