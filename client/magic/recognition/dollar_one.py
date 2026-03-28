from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from client.magic.recognition.preprocessing import (
    bounding_box,
    distance_at_best_angle,
    euclidean_distance,
    indicative_angle,
    path_length,
    point_to_segment_distance,
    resample,
    rotate_by,
    scale_to_square,
    translate_to_origin,
)
from client.magic.recognition.types import Point, RecognizerResult


@dataclass(slots=True)
class DollarOneTemplate:
    label: str
    points: list[Point]
    is_closed: bool


class DollarOneRecognizer:
    """
    Implementation du $1 Unistroke Recognizer.
    Référence: Wobbrock et al. (UIST 2007).
    """

    def __init__(
        self,
        num_points: int = 64,
        square_size: float = 250.0,
        angle_range_deg: float = 45.0,
        angle_precision_deg: float = 2.0,
        closed_angle_range_deg: float = 180.0,
        closed_shift_steps: int = 24,
    ):
        self.num_points = num_points
        self.square_size = square_size
        self.angle_range = math.radians(angle_range_deg)
        self.angle_precision = math.radians(angle_precision_deg)
        self.closed_angle_range = math.radians(closed_angle_range_deg)
        self.closed_shift_steps = max(4, closed_shift_steps)
        self.templates: list[DollarOneTemplate] = []
        self._register_default_templates()

    def add_template(self, label: str, points: Sequence[Point]) -> None:
        is_closed = self._is_closed_path(points)
        normalized = self._normalize(points, is_closed=is_closed)
        if normalized:
            self.templates.append(DollarOneTemplate(label=label, points=normalized, is_closed=is_closed))

    def recognize(self, points: Sequence[Point], is_closed: bool | None = None) -> RecognizerResult | None:
        if len(points) < 2 or not self.templates:
            return None

        closed = self._is_closed_path(points) if is_closed is None else is_closed
        candidate = self._normalize(points, is_closed=closed)
        if not candidate:
            return None

        best_label = ""
        best_distance = float("inf")

        for template in self.templates:
            if template.is_closed != closed:
                continue

            if closed:
                distance = self._best_closed_distance(candidate, template.points)
            else:
                distance = distance_at_best_angle(
                    candidate,
                    template.points,
                    angle_range=self.angle_range,
                    angle_precision=self.angle_precision,
                )
            if distance < best_distance:
                best_distance = distance
                best_label = template.label

        if not best_label:
            return None

        half_diagonal = 0.5 * math.sqrt(2 * (self.square_size ** 2))
        score = max(0.0, 1.0 - (best_distance / half_diagonal))

        return RecognizerResult(
            label=best_label,
            score=score,
            source="$1",
            payload={"distance": best_distance},
        )

    def _normalize(self, points: Sequence[Point], is_closed: bool = False) -> list[Point]:
        if len(points) < 2:
            return []
        normalized = resample(points, self.num_points)
        if is_closed:
            normalized = self._canonicalize_closed_path(normalized)
        else:
            angle = indicative_angle(normalized)
            normalized = rotate_by(normalized, -angle)
        normalized = scale_to_square(normalized, self.square_size)
        normalized = translate_to_origin(normalized)
        return normalized

    def _best_closed_distance(self, candidate: list[Point], template: list[Point]) -> float:
        if not candidate or not template:
            return float("inf")

        count = min(len(candidate), len(template))
        if count < 3:
            return float("inf")

        cand = list(candidate[:count])
        templ = list(template[:count])
        shift_step = max(1, count // self.closed_shift_steps)
        best = float("inf")

        for variant in (cand, list(reversed(cand))):
            for shift in range(0, count, shift_step):
                shifted = variant[shift:] + variant[:shift]
                distance = distance_at_best_angle(
                    shifted,
                    templ,
                    angle_range=self.closed_angle_range,
                    angle_precision=self.angle_precision,
                )
                if distance < best:
                    best = distance

        return best

    @staticmethod
    def _canonicalize_closed_path(points: Sequence[Point]) -> list[Point]:
        contour = list(points)
        if not contour:
            return []
        if len(contour) > 1 and euclidean_distance(contour[0], contour[-1]) <= 1e-6:
            contour = contour[:-1]
        if not contour:
            return []

        anchor = min(range(len(contour)), key=lambda idx: (contour[idx][1], contour[idx][0]))
        return contour[anchor:] + contour[:anchor]

    @staticmethod
    def _is_closed_path(points: Sequence[Point], closed_ratio: float = 0.08) -> bool:
        if len(points) < 4:
            return False

        bbox = bounding_box(points)
        diagonal = max(1e-6, math.hypot(bbox[2] - bbox[0], bbox[3] - bbox[1]))
        threshold = max(8.0, diagonal * closed_ratio)
        total_path = path_length(points)
        if total_path <= 1e-6:
            return False

        end = points[-1]
        best = euclidean_distance(points[0], end)
        for point in points[:-2]:
            best = min(best, euclidean_distance(point, end))
        for idx in range(len(points) - 2):
            best = min(best, point_to_segment_distance(end, points[idx], points[idx + 1]))

        start_end_ratio = euclidean_distance(points[0], end) / total_path
        return best <= threshold and start_end_ratio <= 0.45

    def _register_default_templates(self) -> None:
        self.add_template("line", self._line_template())
        self.add_template("triangle", self._triangle_template())
        self.add_template("circle", self._circle_template())

    @staticmethod
    def _line_template() -> list[Point]:
        return [(-120.0, 0.0), (120.0, 0.0)]

    @staticmethod
    def _triangle_template() -> list[Point]:
        return [
            (0.0, -120.0),
            (104.0, 60.0),
            (-104.0, 60.0),
            (0.0, -120.0),
        ]

    @staticmethod
    def _circle_template(samples: int = 96) -> list[Point]:
        points: list[Point] = []
        for idx in range(samples):
            angle = (2.0 * math.pi * idx) / samples
            points.append((math.cos(angle) * 120.0, math.sin(angle) * 120.0))
        points.append(points[0])
        return points
