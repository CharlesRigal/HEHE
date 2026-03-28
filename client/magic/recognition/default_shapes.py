from __future__ import annotations

from client.magic.primitives import Arrow, Circle, RuneFire, Segment, Triangle
from client.magic.recognition.preprocessing import (
    centroid,
    euclidean_distance,
    simplify_to_vertices,
)
from client.magic.recognition.shape_registry import ShapeRegistry
from client.magic.recognition.types import NormalizedStroke, RecognitionConfig, RecognizerResult, ShapeDefinition


def build_default_shape_registry(config: RecognitionConfig) -> ShapeRegistry:
    registry = ShapeRegistry()
    registry.register(
        ShapeDefinition(
            label="segment",
            aliases=("line",),
            threshold=config.get_shape_threshold("segment"),
            builder=build_segment_primitive,
            requires_closed=None,
            open_penalty=1.0,
            multi_source_bonus=config.multi_source_bonus,
        )
    )
    registry.register(
        ShapeDefinition(
            label="circle",
            threshold=config.get_shape_threshold("circle"),
            builder=build_circle_primitive,
            requires_closed=True,
            open_penalty=config.closed_shape_open_penalty,
            multi_source_bonus=config.multi_source_bonus,
        )
    )
    registry.register(
        ShapeDefinition(
            label="triangle",
            threshold=config.get_shape_threshold("triangle"),
            builder=build_triangle_primitive,
            requires_closed=True,
            open_penalty=config.closed_shape_open_penalty,
            multi_source_bonus=config.multi_source_bonus,
        )
    )
    registry.register(
        ShapeDefinition(
            label="arrow",
            aliases=("fleche",),
            threshold=config.get_shape_threshold("arrow"),
            builder=build_arrow_primitive,
            requires_closed=False,
            open_penalty=1.0,
            multi_source_bonus=config.multi_source_bonus,
        )
    )
    registry.register(
        ShapeDefinition(
            label="rune_fire",
            aliases=("rune_feu", "fire_rune"),
            threshold=config.get_shape_threshold("rune_fire", 0.64),
            builder=build_rune_fire_primitive,
            requires_closed=None,
            open_penalty=1.0,
            multi_source_bonus=config.multi_source_bonus,
        )
    )
    return registry


def build_segment_primitive(stroke: NormalizedStroke, winner: RecognizerResult) -> Segment | None:
    points = stroke.points
    if len(points) < 2:
        return None
    payload = winner.payload or {}
    start = payload.get("start", points[0])
    end = payload.get("end", points[-1])
    return Segment(
        start=tuple(start),
        end=tuple(end),
        confidence=float(winner.score),
        source=winner.source,
    )


def build_circle_primitive(stroke: NormalizedStroke, winner: RecognizerResult) -> Circle | None:
    points = list(stroke.points)
    if len(points) < 3:
        return None
    payload = winner.payload or {}
    center = payload.get("center", centroid(points))
    radius = payload.get("radius")
    if radius is None:
        radius = _mean_radius(points, center)
    return Circle(
        _points=points,
        center=tuple(center),
        radius=float(radius),
        confidence=float(winner.score),
        source=winner.source,
    )


def build_triangle_primitive(stroke: NormalizedStroke, winner: RecognizerResult) -> Triangle | None:
    points = list(stroke.points)
    if len(points) < 3:
        return None
    payload = winner.payload or {}
    vertices = payload.get("vertices")
    if not vertices:
        vertices = simplify_to_vertices(points, target_vertices=3)
    if not vertices:
        return None
    return Triangle(
        _points=points,
        vertices=[tuple(v) for v in vertices],
        confidence=float(winner.score),
        source=winner.source,
    )


def build_arrow_primitive(stroke: NormalizedStroke, winner: RecognizerResult) -> Arrow | None:
    points = list(stroke.points)
    if len(points) < 4:
        return None

    payload = winner.payload or {}
    tail = payload.get("tail")
    tip = payload.get("tip")
    left_head = payload.get("left_head")
    right_head = payload.get("right_head")

    if tail is None:
        tail = points[0]
    if tip is None:
        tip = max(points, key=lambda point: _distance(point, tail))
    if left_head is None or right_head is None:
        left_head, right_head = _arrow_fallback_wings(points, tip)
        if left_head is None or right_head is None:
            return None

    return Arrow(
        _points=points,
        tail=tuple(tail),
        tip=tuple(tip),
        left_head=tuple(left_head),
        right_head=tuple(right_head),
        confidence=float(winner.score),
        source=winner.source,
    )


def build_rune_fire_primitive(stroke: NormalizedStroke, winner: RecognizerResult) -> RuneFire | None:
    payload = winner.payload or {}
    raw_vertices = payload.get("vertices")
    raw_cuts = payload.get("cuts")
    if not raw_vertices or not raw_cuts:
        return None

    vertices: list[tuple[float, float]] = []
    for item in raw_vertices:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        vertices.append((float(item[0]), float(item[1])))
    if len(vertices) < 3:
        return None

    cuts: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for item in raw_cuts:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        start = item[0]
        end = item[1]
        if not isinstance(start, (list, tuple)) or len(start) < 2:
            continue
        if not isinstance(end, (list, tuple)) or len(end) < 2:
            continue
        cuts.append(((float(start[0]), float(start[1])), (float(end[0]), float(end[1]))))
    if len(cuts) < 3:
        return None

    points: list[tuple[float, float]] = list(stroke.points)
    if not points:
        points = [vertices[0], vertices[1], vertices[2], vertices[0]]
        for start, end in cuts:
            points.extend([start, end])

    return RuneFire(
        _points=points,
        vertices=vertices[:3],
        cuts=cuts[:3],
        confidence=float(winner.score),
        source=winner.source,
    )


def _mean_radius(points: list[tuple[float, float]], center: tuple[float, float]) -> float:
    if not points:
        return 0.0
    return sum(euclidean_distance(point, center) for point in points) / len(points)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return euclidean_distance(a, b)


def _arrow_fallback_wings(
    points: list[tuple[float, float]],
    tip: tuple[float, float],
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    if len(points) < 4:
        return None, None

    candidates = [points[idx] for idx in range(len(points) - 1, max(-1, len(points) - 7), -1)]
    candidates = [point for point in candidates if _distance(point, tip) > 1.0]
    if len(candidates) < 2:
        return None, None
    return candidates[0], candidates[1]
