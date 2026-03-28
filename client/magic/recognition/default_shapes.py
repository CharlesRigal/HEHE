from __future__ import annotations

from client.magic.primitives import Circle, Segment, Triangle
from client.magic.recognition.preprocessing import centroid, euclidean_distance, simplify_to_vertices
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


def _mean_radius(points: list[tuple[float, float]], center: tuple[float, float]) -> float:
    if not points:
        return 0.0
    return sum(euclidean_distance(point, center) for point in points) / len(points)

