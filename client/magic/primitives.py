from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float]

@dataclass(slots=True)
class Segment:
    start: Point
    end: Point
    confidence: float = 1.0
    source: str = "heuristic"
    kind: str = "segment"


@dataclass(slots=True)
class Circle:
    _points: list[Point]
    center: Point | None = None
    radius: float | None = None
    confidence: float = 1.0
    source: str = "heuristic"
    kind: str = "circle"


@dataclass(slots=True)
class Triangle:
    _points: list[Point]
    vertices: list[Point]
    confidence: float = 1.0
    source: str = "heuristic"
    kind: str = "triangle"

