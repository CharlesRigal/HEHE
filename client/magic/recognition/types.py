from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

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
    closure_distance: float
    is_closed: bool


@dataclass(slots=True)
class RecognizerResult:
    label: str
    score: float
    source: str
    payload: dict[str, Any] = field(default_factory=dict)


PrimitiveBuilder = Callable[["NormalizedStroke", RecognizerResult], Any | None]
HeuristicDetector = Callable[["NormalizedStroke"], RecognizerResult | None]


@dataclass(slots=True)
class ShapeDefinition:
    label: str
    builder: PrimitiveBuilder
    threshold: float = 0.65
    aliases: tuple[str, ...] = ()
    requires_closed: bool | None = None
    open_penalty: float = 0.65
    multi_source_bonus: float = 0.08


@dataclass(slots=True)
class RecognitionConfig:
    min_sample_distance: float = 2.0
    closed_ratio: float = 0.08
    segment_threshold: float = 0.60
    circle_threshold: float = 0.64
    triangle_threshold: float = 0.60
    heuristic_weight: float = 0.70
    dollar_weight: float = 0.30
    shape_thresholds: dict[str, float] = field(default_factory=dict)
    source_weights: dict[str, float] = field(default_factory=dict)
    fallback_source_weight: float = 0.90
    multi_source_bonus: float = 0.08
    closed_shape_open_penalty: float = 0.65

    def get_shape_threshold(self, label: str, default: float = 0.65) -> float:
        key = label.lower()
        if key in self.shape_thresholds:
            return self.shape_thresholds[key]
        legacy_thresholds = {
            "segment": self.segment_threshold,
            "circle": self.circle_threshold,
            "triangle": self.triangle_threshold,
        }
        return legacy_thresholds.get(key, default)

    def get_source_weight(self, source: str, default: float = 0.0) -> float:
        if source in self.source_weights:
            return self.source_weights[source]
        if source == "heuristic":
            return self.heuristic_weight
        if source == "$1":
            return self.dollar_weight
        return default
