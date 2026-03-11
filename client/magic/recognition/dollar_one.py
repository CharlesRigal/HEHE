from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from client.magic.recognition.preprocessing import (
    distance_at_best_angle,
    indicative_angle,
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
    ):
        self.num_points = num_points
        self.square_size = square_size
        self.angle_range = math.radians(angle_range_deg)
        self.angle_precision = math.radians(angle_precision_deg)
        self.templates: list[DollarOneTemplate] = []
        self._register_default_templates()

    def add_template(self, label: str, points: Sequence[Point]) -> None:
        normalized = self._normalize(points)
        if normalized:
            self.templates.append(DollarOneTemplate(label=label, points=normalized))

    def recognize(self, points: Sequence[Point]) -> RecognizerResult | None:
        if len(points) < 2 or not self.templates:
            return None

        candidate = self._normalize(points)
        if not candidate:
            return None

        best_label = ""
        best_distance = float("inf")

        for template in self.templates:
            distance = distance_at_best_angle(
                candidate,
                template.points,
                angle_range=self.angle_range,
                angle_precision=self.angle_precision,
            )
            if distance < best_distance:
                best_distance = distance
                best_label = template.label

        half_diagonal = 0.5 * math.sqrt(2 * (self.square_size ** 2))
        score = max(0.0, 1.0 - (best_distance / half_diagonal))

        return RecognizerResult(
            label=best_label,
            score=score,
            source="$1",
            payload={"distance": best_distance},
        )

    def _normalize(self, points: Sequence[Point]) -> list[Point]:
        if len(points) < 2:
            return []
        normalized = resample(points, self.num_points)
        angle = indicative_angle(normalized)
        normalized = rotate_by(normalized, -angle)
        normalized = scale_to_square(normalized, self.square_size)
        normalized = translate_to_origin(normalized)
        return normalized

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

