from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from client.magic.recognition.preprocessing import (
    clamp,
    centroid,
    euclidean_distance,
    simplify_to_vertices,
)
from client.magic.recognition.types import HeuristicDetector, NormalizedStroke, Point, RecognizerResult


@dataclass(slots=True)
class HeuristicRule:
    label: str
    detector: HeuristicDetector
    requires_closed: bool | None = None


class HeuristicPrimitiveRecognizer:
    """
    Détection géométrique analytique avec règles enregistrables.
    """

    def __init__(self, rules: Sequence[HeuristicRule] | None = None):
        self._rules: list[HeuristicRule] = []
        if rules is None:
            self._register_default_rules()
        else:
            for rule in rules:
                self.register_rule(rule.label, rule.detector, requires_closed=rule.requires_closed)

    def register_rule(self, label: str, detector: HeuristicDetector, requires_closed: bool | None = None) -> None:
        normalized = (label or "").strip().lower()
        if not normalized:
            raise ValueError("Heuristic rule label must not be empty")
        self._rules = [rule for rule in self._rules if rule.label != normalized]
        self._rules.append(HeuristicRule(label=normalized, detector=detector, requires_closed=requires_closed))

    def clear_rules(self) -> None:
        self._rules.clear()

    def recognize(self, stroke: NormalizedStroke) -> list[RecognizerResult]:
        candidates: list[RecognizerResult] = []

        for rule in self._rules:
            if rule.requires_closed is True and not stroke.is_closed:
                continue
            if rule.requires_closed is False and stroke.is_closed:
                continue

            candidate = rule.detector(stroke)
            if candidate is None:
                continue
            if candidate.label != rule.label:
                candidate = RecognizerResult(
                    label=rule.label,
                    score=candidate.score,
                    source=candidate.source,
                    payload=dict(candidate.payload),
                )
            candidates.append(candidate)

        return candidates

    def _register_default_rules(self) -> None:
        self.register_rule("segment", self._recognize_segment)
        self.register_rule("circle", self._recognize_circle, requires_closed=True)
        self.register_rule("triangle", self._recognize_triangle, requires_closed=True)

    def _recognize_segment(self, stroke: NormalizedStroke) -> RecognizerResult | None:
        points = stroke.points
        if len(points) < 2:
            return None

        start, end = points[0], points[-1]
        direct = euclidean_distance(start, end)
        straightness = direct / max(stroke.path_length, 1e-9)

        if straightness < 0.78:
            return None

        max_dev = self._max_distance_to_line(points, start, end)
        deviation_ratio = max_dev / max(stroke.diagonal, 1.0)
        deviation_score = clamp(1.0 - deviation_ratio * 3.5)

        closure_penalty = 0.2 if stroke.is_closed else 1.0
        score = clamp((straightness ** 1.4) * deviation_score * closure_penalty)

        if score < 0.55:
            return None

        return RecognizerResult(
            label="segment",
            score=score,
            source="heuristic",
            payload={"start": start, "end": end, "deviation_ratio": deviation_ratio},
        )

    def _recognize_circle(self, stroke: NormalizedStroke) -> RecognizerResult | None:
        points = stroke.points
        if len(points) < 8:
            return None

        center = centroid(points)
        radii = [euclidean_distance(point, center) for point in points]
        mean_radius = sum(radii) / len(radii)
        if mean_radius <= 2.0:
            return None

        variance = sum((radius - mean_radius) ** 2 for radius in radii) / len(radii)
        radial_error = math.sqrt(variance) / mean_radius
        radial_score = clamp(1.0 - radial_error / 0.22)

        min_x, min_y, max_x, max_y = stroke.bbox
        width = max_x - min_x
        height = max_y - min_y
        if width <= 1e-6 or height <= 1e-6:
            return None
        aspect = width / height
        aspect_score = clamp(1.0 - abs(1.0 - aspect) / 0.55)

        coverage_score = self._circle_coverage_score(points, center)
        closure_score = clamp(1.0 - stroke.closure_distance / max(4.0, stroke.diagonal * 0.2))

        score = clamp(
            radial_score * 0.45
            + aspect_score * 0.20
            + coverage_score * 0.20
            + closure_score * 0.15
        )

        if score < 0.58:
            return None

        return RecognizerResult(
            label="circle",
            score=score,
            source="heuristic",
            payload={"center": center, "radius": mean_radius},
        )

    def _recognize_triangle(self, stroke: NormalizedStroke) -> RecognizerResult | None:
        points = stroke.points
        if len(points) < 6:
            return None

        vertices = simplify_to_vertices(points, target_vertices=3)
        if vertices is None:
            return None

        area = abs(self._triangle_cross_area(vertices[0], vertices[1], vertices[2])) * 0.5
        if area <= (stroke.diagonal * stroke.diagonal * 0.01):
            return None

        edges = [
            euclidean_distance(vertices[0], vertices[1]),
            euclidean_distance(vertices[1], vertices[2]),
            euclidean_distance(vertices[2], vertices[0]),
        ]
        perimeter = sum(edges)
        if perimeter <= 1e-6:
            return None

        max_edge = max(edges)
        min_edge = min(edges)
        side_ratio = min_edge / max(max_edge, 1e-6)

        balance_score = clamp((side_ratio - 0.18) / 0.55)
        compactness = (4.0 * math.sqrt(3.0) * area) / (perimeter * perimeter)
        compactness_score = clamp(compactness / 0.60)
        area_score = clamp(area / max(1.0, stroke.diagonal * stroke.diagonal * 0.18))
        closure_score = clamp(1.0 - stroke.closure_distance / max(4.0, stroke.diagonal * 0.2))

        score = clamp(
            balance_score * 0.35
            + compactness_score * 0.30
            + area_score * 0.20
            + closure_score * 0.15
        )

        if score < 0.52:
            return None

        return RecognizerResult(
            label="triangle",
            score=score,
            source="heuristic",
            payload={"vertices": vertices},
        )

    @staticmethod
    def _triangle_cross_area(a: Point, b: Point, c: Point) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    @staticmethod
    def _max_distance_to_line(points: list[Point], start: Point, end: Point) -> float:
        if start == end:
            return 0.0

        x1, y1 = start
        x2, y2 = end
        denominator = math.hypot(y2 - y1, x2 - x1)
        if denominator <= 1e-9:
            return 0.0

        max_distance = 0.0
        for x0, y0 in points[1:-1]:
            numerator = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
            max_distance = max(max_distance, numerator / denominator)
        return max_distance

    @staticmethod
    def _circle_coverage_score(points: list[Point], center: Point) -> float:
        if len(points) < 3:
            return 0.0

        angles = sorted((math.atan2(y - center[1], x - center[0]) % (2 * math.pi)) for x, y in points)
        wrapped = angles + [angles[0] + 2 * math.pi]
        max_gap = max(wrapped[idx + 1] - wrapped[idx] for idx in range(len(angles)))
        coverage = 2 * math.pi - max_gap
        return clamp((coverage - math.pi) / math.pi)

