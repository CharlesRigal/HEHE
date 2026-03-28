from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float]
CutSegment = tuple[Point, Point]

@dataclass(slots=True)
class Segment:
    start: Point
    end: Point
    confidence: float = 1.0
    source: str = "heuristic"
    kind: str = "segment"


@dataclass(slots=True)
class ZigZag:
    _points: list[Point]
    vertices: list[Point]
    confidence: float = 1.0
    source: str = "heuristic"
    kind: str = "zigzag"


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


@dataclass(slots=True)
class Arrow:
    _points: list[Point]
    tail: Point
    tip: Point
    left_head: Point
    right_head: Point
    confidence: float = 1.0
    source: str = "heuristic"
    kind: str = "arrow"


@dataclass(slots=True)
class RuneFire:
    _points: list[Point]
    vertices: list[Point]
    cuts: list[CutSegment]
    confidence: float = 1.0
    source: str = "complex"
    kind: str = "rune_fire"
