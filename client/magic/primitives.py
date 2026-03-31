from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[float, float]
CutSegment = tuple[Point, Point]

@dataclass(slots=True)
class Segment:
    start: Point
    end: Point
    confidence: float = 1.0
    source: str = "heuristic"
    meta: dict[str, float | int | str | bool] = field(default_factory=dict)
    kind: str = "segment"


@dataclass(slots=True)
class ZigZag:
    _points: list[Point]
    vertices: list[Point]
    confidence: float = 1.0
    source: str = "heuristic"
    meta: dict[str, float | int | str | bool] = field(default_factory=dict)
    kind: str = "zigzag"


@dataclass(slots=True)
class Circle:
    _points: list[Point]
    center: Point | None = None
    radius: float | None = None
    confidence: float = 1.0
    source: str = "heuristic"
    meta: dict[str, float | int | str | bool] = field(default_factory=dict)
    kind: str = "circle"


@dataclass(slots=True)
class Triangle:
    _points: list[Point]
    vertices: list[Point]
    confidence: float = 1.0
    source: str = "heuristic"
    meta: dict[str, float | int | str | bool] = field(default_factory=dict)
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
    meta: dict[str, float | int | str | bool] = field(default_factory=dict)
    kind: str = "arrow"


@dataclass(slots=True)
class ArrowWithBase:
    _points: list[Point]
    tail: Point
    tip: Point
    left_head: Point
    right_head: Point
    base_start: Point
    base_end: Point
    confidence: float = 1.0
    source: str = "complex"
    meta: dict[str, float | int | str | bool] = field(default_factory=dict)
    kind: str = "arrow_with_base"


@dataclass(slots=True)
class RuneFire:
    _points: list[Point]
    vertices: list[Point]
    cuts: list[CutSegment]
    confidence: float = 1.0
    source: str = "complex"
    meta: dict[str, float | int | str | bool] = field(default_factory=dict)
    kind: str = "rune_fire"
