from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from client.magic.recognition.preprocessing import (
    clamp,
    centroid,
    dedupe_consecutive,
    euclidean_distance,
    point_to_segment_distance,
    rdp,
    simplify_to_vertices,
    turn_angle,
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
        self.register_rule("zigzag", self._recognize_zigzag, requires_closed=False)

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

        zigzag_signature = self._extract_zigzag_signature(stroke)
        if zigzag_signature is not None:
            turn_count = int(zigzag_signature["turn_count"])
            alternation = float(zigzag_signature["alternation_ratio"])
            amplitude = float(zigzag_signature["amplitude_ratio"])
            path_ratio = float(zigzag_signature["path_ratio"])
            if turn_count >= 2 and alternation >= 0.50 and amplitude >= 0.04 and path_ratio >= 1.08:
                return None
            if turn_count >= 2 and amplitude >= 0.03:
                deviation_score *= 0.10

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

        # Rejette les "faux triangles" de type zigzag fermé:
        # le tracé est trop long vs le périmètre théorique du triangle.
        path_to_perimeter = stroke.path_length / max(perimeter, 1e-6)
        if path_to_perimeter > 1.45 or path_to_perimeter < 0.72:
            return None

        max_edge = max(edges)
        min_edge = min(edges)
        side_ratio = min_edge / max(max_edge, 1e-6)
        if min_edge < max(8.0, stroke.diagonal * 0.06):
            return None

        angles = self._triangle_angles(vertices[0], vertices[1], vertices[2])
        if any(angle < 0.26 or angle > 2.62 for angle in angles):
            return None

        edge_fit_error = self._triangle_edge_fit_error(points, vertices[0], vertices[1], vertices[2])
        if edge_fit_error > 0.11:
            return None

        simplified = self._simplify_polyline_points(points, stroke.path_length)
        turn_count = self._count_significant_turns(
            simplified,
            min_leg=max(6.0, stroke.diagonal * 0.04),
            min_angle=0.28,
        )
        if turn_count > 5:
            return None

        balance_score = clamp((side_ratio - 0.18) / 0.55)
        compactness = (4.0 * math.sqrt(3.0) * area) / (perimeter * perimeter)
        compactness_score = clamp(compactness / 0.60)
        area_score = clamp(area / max(1.0, stroke.diagonal * stroke.diagonal * 0.18))
        closure_score = clamp(1.0 - stroke.closure_distance / max(4.0, stroke.diagonal * 0.2))
        path_score = clamp(1.0 - abs(path_to_perimeter - 1.05) / 0.70)
        fit_score = clamp(1.0 - edge_fit_error / 0.11)
        turn_score = clamp(1.0 - abs(turn_count - 3.0) / 3.0)

        score = clamp(
            balance_score * 0.22
            + compactness_score * 0.20
            + area_score * 0.14
            + closure_score * 0.12
            + path_score * 0.12
            + fit_score * 0.12
            + turn_score * 0.08
        )

        if score < 0.60:
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

    def _triangle_angles(self, a: Point, b: Point, c: Point) -> tuple[float, float, float]:
        return (
            self._angle_at(a, b, c),
            self._angle_at(b, a, c),
            self._angle_at(c, a, b),
        )

    @staticmethod
    def _angle_at(vertex: Point, left: Point, right: Point) -> float:
        v1 = (left[0] - vertex[0], left[1] - vertex[1])
        v2 = (right[0] - vertex[0], right[1] - vertex[1])
        n1 = math.hypot(v1[0], v1[1])
        n2 = math.hypot(v2[0], v2[1])
        if n1 <= 1e-9 or n2 <= 1e-9:
            return 0.0
        dot_value = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        dot_value = max(-1.0, min(1.0, dot_value))
        return math.acos(dot_value)

    def _triangle_edge_fit_error(self, points: list[Point], a: Point, b: Point, c: Point) -> float:
        if not points:
            return 1.0
        sample_step = max(1, len(points) // 64)
        sampled = points[::sample_step]
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])

        total = 0.0
        for point in sampled:
            total += min(
                point_to_segment_distance(point, a, b),
                point_to_segment_distance(point, b, c),
                point_to_segment_distance(point, c, a),
            )
        mean_distance = total / max(1, len(sampled))
        diagonal = max(1e-6, math.hypot(max(p[0] for p in points) - min(p[0] for p in points), max(p[1] for p in points) - min(p[1] for p in points)))
        return mean_distance / diagonal

    def _recognize_zigzag(self, stroke: NormalizedStroke) -> RecognizerResult | None:
        """Detecte un zigzag a partir de la signature geometrique.

        Un zigzag est un trace ouvert qui :
          - alterne des deviations perpendiculaires (>= 2 retournements)
          - progresse le long d'un axe principal (monotonic_ratio eleve)
          - a un path_length > distance axe (redondance)
        """
        if stroke.is_closed:
            return None

        signature = self._extract_zigzag_signature(stroke)
        if signature is None:
            return None

        turn_count = int(signature["turn_count"])
        alternation = float(signature["alternation_ratio"])
        amplitude = float(signature["amplitude_ratio"])
        path_ratio = float(signature["path_ratio"])
        axis_progress = float(signature["axis_progress"])
        monotonic_ratio = float(signature["monotonic_ratio"])
        raw_vertices = signature["vertices"]
        vertices: list[Point] = []
        if isinstance(raw_vertices, list):
            for v in raw_vertices:
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    vertices.append((float(v[0]), float(v[1])))

        # Seuils d'exclusion : rejeter les traces qui sont plus proches d'un
        # segment bruite ou d'un triangle que d'un vrai zigzag.
        if turn_count < 2:
            return None
        if alternation < 0.50:
            return None
        if amplitude < 0.04:
            return None
        if path_ratio < 1.10:
            return None
        if axis_progress < 0.55:
            return None
        if monotonic_ratio < 0.55:
            return None
        if len(vertices) < 4:
            return None

        # Scoring : chaque critere contribue, normalise dans [0, 1].
        turn_score = clamp((turn_count - 1) / 5.0)          # 2 -> 0.2, 6+ -> 1.0
        alternation_score = clamp((alternation - 0.45) / 0.55)
        amplitude_score = clamp((amplitude - 0.03) / 0.18)  # 0.03 -> 0, 0.21 -> 1
        path_score = clamp((path_ratio - 1.05) / 0.95)      # 1.05 -> 0, 2.0 -> 1
        progress_score = clamp((axis_progress - 0.5) / 0.5)
        monotonic_score = clamp((monotonic_ratio - 0.5) / 0.5)

        score = clamp(
            turn_score * 0.25
            + alternation_score * 0.22
            + amplitude_score * 0.18
            + path_score * 0.15
            + progress_score * 0.10
            + monotonic_score * 0.10
        )

        if score < 0.55:
            return None

        return RecognizerResult(
            label="zigzag",
            score=score,
            source="heuristic",
            payload={
                "vertices": vertices,
                "turn_count": turn_count,
                "amplitude_ratio": amplitude,
                "path_ratio": path_ratio,
                "alternation_ratio": alternation,
                "monotonic_ratio": monotonic_ratio,
            },
        )

    def _extract_zigzag_signature(self, stroke: NormalizedStroke) -> dict[str, float | list[Point]] | None:
        points = stroke.points
        if len(points) < 5:
            return None

        simplified = self._simplify_polyline_points(points, stroke.path_length)
        if len(simplified) < 4:
            return None

        start = simplified[0]
        end = simplified[-1]
        axis = (end[0] - start[0], end[1] - start[1])
        axis_length = math.hypot(axis[0], axis[1])
        min_axis = max(24.0, stroke.diagonal * 0.16)
        if axis_length < min_axis:
            return None

        axis_len_sq = max(1e-6, axis_length * axis_length)
        perp_offsets: list[float] = []
        projections: list[float] = []
        for point in simplified[1:-1]:
            rel = (point[0] - start[0], point[1] - start[1])
            projection = (rel[0] * axis[0] + rel[1] * axis[1]) / axis_len_sq
            offset = (rel[0] * axis[1] - rel[1] * axis[0]) / max(axis_length, 1e-6)
            projections.append(projection)
            perp_offsets.append(offset)

        if not perp_offsets:
            return None

        min_offset = max(3.0, stroke.diagonal * 0.03)
        signed_peaks: list[tuple[Point, int]] = []
        for idx, offset in enumerate(perp_offsets):
            if abs(offset) < min_offset:
                continue
            sign = 1 if offset > 0.0 else -1
            signed_peaks.append((simplified[idx + 1], sign))

        if len(signed_peaks) < 3:
            return None

        signs = [item[1] for item in signed_peaks]
        turn_count = 0
        for left, right in zip(signs, signs[1:]):
            if left != right:
                turn_count += 1
        if turn_count < 2:
            return None

        alternation_ratio = turn_count / max(1, len(signs) - 1)
        amplitude_ratio = (sum(abs(offset) for offset in perp_offsets) / len(perp_offsets)) / max(axis_length, 1e-6)
        path_ratio = stroke.path_length / max(axis_length, 1e-6)

        projected_full = [0.0] + projections + [1.0]
        monotonic_steps = 0
        for prev, curr in zip(projected_full, projected_full[1:]):
            if curr >= prev - 0.03:
                monotonic_steps += 1
        monotonic_ratio = monotonic_steps / max(1, len(projected_full) - 1)
        axis_progress = max(projected_full) - min(projected_full)

        vertices = self._collect_zigzag_vertices(simplified, perp_offsets, min_offset)
        if len(vertices) < 4:
            return None

        return {
            "turn_count": float(turn_count),
            "alternation_ratio": alternation_ratio,
            "amplitude_ratio": amplitude_ratio,
            "path_ratio": path_ratio,
            "axis_progress": axis_progress,
            "monotonic_ratio": monotonic_ratio,
            "vertices": vertices,
        }

    def _simplify_polyline_points(self, points: list[Point], total_path: float) -> list[Point]:
        epsilon = max(2.0, total_path * 0.03)
        simplified = rdp(points, epsilon=epsilon)
        simplified = dedupe_consecutive(simplified, tolerance=1.2)
        if simplified and simplified[0] != points[0]:
            simplified.insert(0, points[0])
        if simplified and simplified[-1] != points[-1]:
            simplified.append(points[-1])
        return simplified

    def _collect_zigzag_vertices(
        self,
        simplified: list[Point],
        perp_offsets: list[float],
        min_offset: float,
    ) -> list[Point]:
        vertices: list[Point] = [simplified[0]]
        for idx, offset in enumerate(perp_offsets):
            if abs(offset) >= min_offset * 0.75:
                vertices.append(simplified[idx + 1])
        vertices.append(simplified[-1])
        return dedupe_consecutive(vertices, tolerance=2.0)

    def _count_significant_turns(
        self,
        points: list[Point],
        *,
        min_leg: float,
        min_angle: float,
    ) -> int:
        if len(points) < 3:
            return 0

        contour = list(points)
        if len(contour) > 2 and euclidean_distance(contour[0], contour[-1]) <= 1.5:
            contour = contour[:-1]
        if len(contour) < 3:
            return 0

        total = len(contour)
        turns = 0
        for idx in range(total):
            prev = contour[(idx - 1) % total]
            curr = contour[idx]
            nxt = contour[(idx + 1) % total]
            if euclidean_distance(prev, curr) < min_leg or euclidean_distance(curr, nxt) < min_leg:
                continue
            angle = turn_angle(prev, curr, nxt)
            if angle >= min_angle:
                turns += 1
        return turns

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
