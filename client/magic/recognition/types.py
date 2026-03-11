from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]


@dataclass(slots=True)
class StrokeSample:
    point: Point
    time: float | None = None


@dataclass(slots=True)
class NormalizedStroke:
    points: list[Point]
    times: list[float | None]
    path_length: float
    bbox: tuple[float, float, float, float]
    diagonal: float
    start_end_distance: float
    is_closed: bool


@dataclass(slots=True)
class RecognizerResult:
    label: str
    score: float
    source: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RecognitionConfig:
    min_sample_distance: float = 2.0
    closed_ratio: float = 0.08
    segment_threshold: float = 0.60
    circle_threshold: float = 0.64
    triangle_threshold: float = 0.60
    heuristic_weight: float = 0.70
    dollar_weight: float = 0.30

