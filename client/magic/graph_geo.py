from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from client.magic.primitives import Arrow, ArrowWithBase, Circle, RuneFire, Segment, Triangle, ZigZag

Point = tuple[float, float]
PriorityRule = Callable[["PriorityContext"], dict[int, float]]


class MagicalNode:
    def __init__(self, primitive: Any, parent: "MagicalNode | None" = None, index: int = -1):
        self.primitive = primitive
        self.parent = parent
        self.child: MagicalNode | None = None
        self.index = index

    def set_child(self, child: "MagicalNode") -> None:
        self.child = child


@dataclass(slots=True)
class SpatialRelation:
    source_index: int
    target_index: int
    relation: str
    weight: float = 1.0
    details: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class PriorityContext:
    nodes: list[MagicalNode]
    relations: list[SpatialRelation]
    anchor_circle_index: int | None
    centers: dict[int, Point]
    distances_to_anchor: dict[int, float]
    clockwise_angles: dict[int, float]


@dataclass(slots=True)
class CircleReadingPlan:
    anchor_circle_index: int
    ordered_subsymbol_indices: list[int]
    center: Point
    anchor_radius: float
    radial_step: float


class GraphGeo:
    def __init__(self):
        self._root_node: MagicalNode | None = None
        self._nodes: list[MagicalNode] = []
        self._priority_rules: list[tuple[str, PriorityRule]] = []

    def add_node(self, primitive: Any) -> None:
        node = MagicalNode(primitive, index=len(self._nodes))
        if self._root_node is None:
            self._root_node = node
        else:
            tail = self._nodes[-1]
            tail.set_child(node)
            node.parent = tail
        self._nodes.append(node)

    def get_head(self) -> MagicalNode | None:
        return self._root_node

    def iter_nodes(self) -> list[MagicalNode]:
        return list(self._nodes)

    def iter_primitives(self) -> list[Any]:
        return [node.primitive for node in self._nodes]

    def register_priority_rule(self, name: str, rule: PriorityRule) -> None:
        normalized = (name or "").strip().lower()
        if not normalized:
            raise ValueError("Priority rule name must not be empty")
        self._priority_rules = [(rule_name, fn) for rule_name, fn in self._priority_rules if rule_name != normalized]
        self._priority_rules.append((normalized, rule))

    def clear_priority_rules(self) -> None:
        self._priority_rules.clear()

    def get_anchor_circle_index(self) -> int | None:
        best_index: int | None = None
        best_radius = -1.0
        for idx, node in enumerate(self._nodes):
            primitive = node.primitive
            if isinstance(primitive, Circle) and primitive.center is not None and primitive.radius is not None:
                if primitive.radius > best_radius:
                    best_radius = primitive.radius
                    best_index = idx
        return best_index

    def build_spatial_relations(self, proximity_px: float | None = None) -> list[SpatialRelation]:
        if len(self._nodes) < 2:
            return []

        if proximity_px is None:
            proximity_px = max(24.0, self._scene_diagonal() * 0.12)

        relations: list[SpatialRelation] = []
        centers = [self._primitive_center(node.primitive) for node in self._nodes]

        for left in range(len(self._nodes)):
            for right in range(left + 1, len(self._nodes)):
                a = self._nodes[left].primitive
                b = self._nodes[right].primitive
                distance = self._distance(centers[left], centers[right])

                if self._intersects(a, b):
                    relations.append(
                        SpatialRelation(
                            source_index=left,
                            target_index=right,
                            relation="intersects",
                            details={"distance": distance},
                        )
                    )
                    relations.append(
                        SpatialRelation(
                            source_index=right,
                            target_index=left,
                            relation="intersects",
                            details={"distance": distance},
                        )
                    )

                if self._contains(a, b):
                    relations.append(
                        SpatialRelation(
                            source_index=left,
                            target_index=right,
                            relation="contains",
                            details={"distance": distance},
                        )
                    )
                    relations.append(
                        SpatialRelation(
                            source_index=right,
                            target_index=left,
                            relation="inside",
                            details={"distance": distance},
                        )
                    )

                if self._contains(b, a):
                    relations.append(
                        SpatialRelation(
                            source_index=right,
                            target_index=left,
                            relation="contains",
                            details={"distance": distance},
                        )
                    )
                    relations.append(
                        SpatialRelation(
                            source_index=left,
                            target_index=right,
                            relation="inside",
                            details={"distance": distance},
                        )
                    )

                if distance <= proximity_px:
                    proximity_weight = max(0.0, 1.0 - distance / max(proximity_px, 1e-6))
                    details = {"distance": distance, "threshold": proximity_px}
                    relations.append(
                        SpatialRelation(
                            source_index=left,
                            target_index=right,
                            relation="near",
                            weight=proximity_weight,
                            details=details,
                        )
                    )
                    relations.append(
                        SpatialRelation(
                            source_index=right,
                            target_index=left,
                            relation="near",
                            weight=proximity_weight,
                            details=details,
                        )
                    )

        return relations

    def get_contained_clockwise_indices(
        self,
        circle_index: int | None = None,
        radial_step_ratio: float = 0.2,
        sort_by: str = "ring",
    ) -> list[int]:
        anchor_index = self.get_anchor_circle_index() if circle_index is None else circle_index
        if anchor_index is None or anchor_index < 0 or anchor_index >= len(self._nodes):
            return []

        anchor = self._nodes[anchor_index].primitive
        if not isinstance(anchor, Circle) or anchor.center is None or anchor.radius is None:
            return []

        center = anchor.center
        radial_step = max(1.0, anchor.radius * max(0.05, radial_step_ratio))
        ranked: list[tuple[int, float, float]] = []

        for idx, node in enumerate(self._nodes):
            if idx == anchor_index:
                continue
            primitive = node.primitive
            if not self._contains(anchor, primitive):
                continue
            point = self._primitive_center(primitive)
            distance = self._distance(center, point)
            angle = self._clockwise_angle_from_up(center, point)
            ranked.append((idx, distance, angle))

        if sort_by == "ring":
            # Tri par anneaux de distance (comportement par défaut)
            ranked.sort(key=lambda item: (int(item[1] / radial_step), item[2], item[1]))
        elif sort_by == "distance":
            # Tri strict par distance au centre (nouveau mode pour SpellChain)
            ranked.sort(key=lambda item: (item[1], item[2], item[0]))
        else:
            # Fallback: tri par anneaux
            ranked.sort(key=lambda item: (int(item[1] / radial_step), item[2], item[1]))
            
        return [idx for idx, _, _ in ranked]

    def build_circle_reading_plan(
        self,
        circle_index: int | None = None,
        radial_step_ratio: float = 0.2,
    ) -> CircleReadingPlan | None:
        anchor_index = self.get_anchor_circle_index() if circle_index is None else circle_index
        if anchor_index is None or anchor_index < 0 or anchor_index >= len(self._nodes):
            return None

        anchor = self._nodes[anchor_index].primitive
        if not isinstance(anchor, Circle) or anchor.center is None or anchor.radius is None:
            return None

        radial_step = max(1.0, anchor.radius * max(0.05, radial_step_ratio))
        ordered = self.get_contained_clockwise_indices(
            circle_index=anchor_index,
            radial_step_ratio=radial_step_ratio,
        )
        return CircleReadingPlan(
            anchor_circle_index=anchor_index,
            ordered_subsymbol_indices=ordered,
            center=tuple(anchor.center),
            anchor_radius=float(anchor.radius),
            radial_step=radial_step,
        )

    def build_priority_context(self, circle_index: int | None = None) -> PriorityContext:
        centers = {idx: self._primitive_center(node.primitive) for idx, node in enumerate(self._nodes)}
        anchor_index = self.get_anchor_circle_index() if circle_index is None else circle_index
        distances_to_anchor: dict[int, float] = {}
        clockwise_angles: dict[int, float] = {}

        if anchor_index is not None and 0 <= anchor_index < len(self._nodes):
            anchor = self._nodes[anchor_index].primitive
            if isinstance(anchor, Circle) and anchor.center is not None:
                center = anchor.center
                for idx, point in centers.items():
                    if idx == anchor_index:
                        continue
                    distances_to_anchor[idx] = self._distance(center, point)
                    clockwise_angles[idx] = self._clockwise_angle_from_up(center, point)

        return PriorityContext(
            nodes=self.iter_nodes(),
            relations=self.build_spatial_relations(),
            anchor_circle_index=anchor_index,
            centers=centers,
            distances_to_anchor=distances_to_anchor,
            clockwise_angles=clockwise_angles,
        )

    def build_relation_index(self, relations: list[SpatialRelation] | None = None) -> dict[int, list[SpatialRelation]]:
        source_map: dict[int, list[SpatialRelation]] = {}
        active_relations = relations if relations is not None else self.build_spatial_relations()
        for relation in active_relations:
            source_map.setdefault(relation.source_index, []).append(relation)
        return source_map

    def find_relations(
        self,
        *,
        relation: str | None = None,
        source_index: int | None = None,
        target_index: int | None = None,
        relations: list[SpatialRelation] | None = None,
    ) -> list[SpatialRelation]:
        active_relations = relations if relations is not None else self.build_spatial_relations()
        expected = (relation or "").strip().lower() if relation is not None else None
        result: list[SpatialRelation] = []
        for item in active_relations:
            if expected is not None and item.relation != expected:
                continue
            if source_index is not None and item.source_index != source_index:
                continue
            if target_index is not None and item.target_index != target_index:
                continue
            result.append(item)
        return result

    def resolve_priority_indices(self, include_anchor_circle: bool = True) -> list[int]:
        if not self._nodes:
            return []

        context = self.build_priority_context()
        anchor_index = context.anchor_circle_index
        contained_order = set(self.get_contained_clockwise_indices(anchor_index))

        group: dict[int, int] = {}
        minor: dict[int, float] = {}
        for idx in range(len(self._nodes)):
            group[idx] = 0
            minor[idx] = float(idx)

        if anchor_index is not None and anchor_index in group and include_anchor_circle:
            group[anchor_index] = -2
            minor[anchor_index] = -1.0

        if contained_order:
            ordered = self.get_contained_clockwise_indices(anchor_index)
            for rank, idx in enumerate(ordered):
                group[idx] = -1
                minor[idx] = float(rank)

        adjustment = {idx: 0.0 for idx in range(len(self._nodes))}
        for _, rule in self._priority_rules:
            delta = rule(context) or {}
            for idx, value in delta.items():
                if idx in adjustment:
                    adjustment[idx] += float(value)

        sorted_indices = sorted(
            range(len(self._nodes)),
            key=lambda idx: (group[idx], minor[idx] + adjustment[idx], idx),
        )
        return sorted_indices

    def resolve_priority_nodes(self, include_anchor_circle: bool = True) -> list[MagicalNode]:
        return [self._nodes[idx] for idx in self.resolve_priority_indices(include_anchor_circle=include_anchor_circle)]

    def resolve_priority_primitives(self, include_anchor_circle: bool = True) -> list[Any]:
        return [node.primitive for node in self.resolve_priority_nodes(include_anchor_circle=include_anchor_circle)]

    @staticmethod
    def _distance(a: Point, b: Point) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    @staticmethod
    def _clockwise_angle_from_up(center: Point, point: Point) -> float:
        dx = point[0] - center[0]
        dy = point[1] - center[1]
        # Ecran pygame: axe Y vers le bas.
        # atan2(dx, -dy) donne 0 vers le haut et augmente en sens horaire.
        return math.atan2(dx, -dy) % (2.0 * math.pi)

    def _scene_diagonal(self) -> float:
        all_points: list[Point] = []
        for node in self._nodes:
            all_points.extend(self._primitive_points(node.primitive))
        if len(all_points) < 2:
            return 100.0
        min_x = min(point[0] for point in all_points)
        min_y = min(point[1] for point in all_points)
        max_x = max(point[0] for point in all_points)
        max_y = max(point[1] for point in all_points)
        return max(1.0, math.hypot(max_x - min_x, max_y - min_y))

    def _contains(self, container: Any, target: Any) -> bool:
        if isinstance(container, Circle):
            return self._circle_contains_primitive(container, target)
        if isinstance(container, Triangle):
            center = self._primitive_center(target)
            return self._point_in_triangle(center, container.vertices[0], container.vertices[1], container.vertices[2])
        if isinstance(container, RuneFire) and len(container.vertices) >= 3:
            center = self._primitive_center(target)
            return self._point_in_triangle(
                center,
                container.vertices[0],
                container.vertices[1],
                container.vertices[2],
            )
        return False

    def _intersects(self, left: Any, right: Any) -> bool:
        if isinstance(left, Circle) and isinstance(right, Circle):
            return self._circle_circle_intersection(left, right)
        if isinstance(left, Circle) and isinstance(right, Segment):
            return self._circle_segment_intersection(left, right)
        if isinstance(left, Segment) and isinstance(right, Circle):
            return self._circle_segment_intersection(right, left)

        left_edges = self._primitive_edges(left)
        right_edges = self._primitive_edges(right)
        if not left_edges or not right_edges:
            return False

        for edge_a in left_edges:
            for edge_b in right_edges:
                if self._segments_intersect(edge_a[0], edge_a[1], edge_b[0], edge_b[1]):
                    return True
        return False

    def _circle_contains_primitive(self, circle: Circle, primitive: Any) -> bool:
        if circle.center is None or circle.radius is None:
            return False

        if isinstance(primitive, Circle) and primitive.center is not None and primitive.radius is not None:
            center_distance = self._distance(circle.center, primitive.center)
            return center_distance + primitive.radius <= circle.radius + 1e-6

        key_points = self._primitive_key_points(primitive)
        if not key_points:
            return False
        for point in key_points:
            if self._distance(circle.center, point) > circle.radius + 1e-6:
                return False
        return True

    @staticmethod
    def _point_to_segment_distance(point: Point, seg_start: Point, seg_end: Point) -> float:
        px, py = point
        ax, ay = seg_start
        bx, by = seg_end
        abx = bx - ax
        aby = by - ay
        denom = abx * abx + aby * aby
        if denom <= 1e-9:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * abx + (py - ay) * aby) / denom
        t = max(0.0, min(1.0, t))
        proj_x = ax + abx * t
        proj_y = ay + aby * t
        return math.hypot(px - proj_x, py - proj_y)

    def _circle_segment_intersection(self, circle: Circle, segment: Segment) -> bool:
        if circle.center is None or circle.radius is None:
            return False
        distance = self._point_to_segment_distance(circle.center, segment.start, segment.end)
        return distance <= circle.radius + 1e-6

    def _circle_circle_intersection(self, left: Circle, right: Circle) -> bool:
        if left.center is None or left.radius is None or right.center is None or right.radius is None:
            return False
        distance = self._distance(left.center, right.center)
        return distance <= (left.radius + right.radius + 1e-6)

    def _primitive_center(self, primitive: Any) -> Point:
        if isinstance(primitive, Circle) and primitive.center is not None:
            return primitive.center
        if isinstance(primitive, Segment):
            return (
                (primitive.start[0] + primitive.end[0]) * 0.5,
                (primitive.start[1] + primitive.end[1]) * 0.5,
            )
        if isinstance(primitive, Triangle) and primitive.vertices:
            vx = sum(point[0] for point in primitive.vertices) / len(primitive.vertices)
            vy = sum(point[1] for point in primitive.vertices) / len(primitive.vertices)
            return (vx, vy)
        if isinstance(primitive, RuneFire) and primitive.vertices:
            vx = sum(point[0] for point in primitive.vertices) / len(primitive.vertices)
            vy = sum(point[1] for point in primitive.vertices) / len(primitive.vertices)
            return (vx, vy)
        if isinstance(primitive, ZigZag) and primitive.vertices:
            vx = sum(point[0] for point in primitive.vertices) / len(primitive.vertices)
            vy = sum(point[1] for point in primitive.vertices) / len(primitive.vertices)
            return (vx, vy)
        if isinstance(primitive, ArrowWithBase):
            return (
                (primitive.tail[0] + primitive.tip[0] + primitive.base_start[0] + primitive.base_end[0]) * 0.25,
                (primitive.tail[1] + primitive.tip[1] + primitive.base_start[1] + primitive.base_end[1]) * 0.25,
            )
        if isinstance(primitive, Arrow):
            return (
                (primitive.tail[0] + primitive.tip[0]) * 0.5,
                (primitive.tail[1] + primitive.tip[1]) * 0.5,
            )
        points = self._primitive_points(primitive)
        if not points:
            return (0.0, 0.0)
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )

    def _primitive_key_points(self, primitive: Any) -> list[Point]:
        if isinstance(primitive, Segment):
            middle = self._primitive_center(primitive)
            return [primitive.start, primitive.end, middle]
        if isinstance(primitive, Triangle):
            return list(primitive.vertices) + [self._primitive_center(primitive)]
        if isinstance(primitive, RuneFire):
            points = list(primitive.vertices) + [self._primitive_center(primitive)]
            for start, end in primitive.cuts[:3]:
                points.append(((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5))
            return points
        if isinstance(primitive, ZigZag):
            if not primitive.vertices:
                return []
            middle = primitive.vertices[len(primitive.vertices) // 2]
            return [primitive.vertices[0], middle, primitive.vertices[-1]]
        if isinstance(primitive, ArrowWithBase):
            return [
                primitive.tail,
                primitive.tip,
                primitive.left_head,
                primitive.right_head,
                primitive.base_start,
                primitive.base_end,
            ]
        if isinstance(primitive, Arrow):
            return [primitive.tail, primitive.tip, primitive.left_head, primitive.right_head]
        if isinstance(primitive, Circle) and primitive.center is not None and primitive.radius is not None:
            cx, cy = primitive.center
            r = primitive.radius
            return [
                primitive.center,
                (cx + r, cy),
                (cx - r, cy),
                (cx, cy + r),
                (cx, cy - r),
            ]
        points = self._primitive_points(primitive)
        if not points:
            return []
        if len(points) <= 3:
            return points
        middle = points[len(points) // 2]
        return [points[0], middle, points[-1]]

    def _primitive_points(self, primitive: Any) -> list[Point]:
        if isinstance(primitive, Segment):
            return [tuple(primitive.start), tuple(primitive.end)]
        if isinstance(primitive, Triangle):
            return [tuple(point) for point in primitive.vertices]
        if isinstance(primitive, RuneFire):
            points: list[Point] = [tuple(point) for point in primitive.vertices[:3]]
            for start, end in primitive.cuts:
                points.extend([tuple(start), tuple(end)])
            return points
        if isinstance(primitive, ZigZag):
            return [tuple(point) for point in primitive.vertices]
        if isinstance(primitive, ArrowWithBase):
            return [
                tuple(primitive.tail),
                tuple(primitive.tip),
                tuple(primitive.left_head),
                tuple(primitive.tip),
                tuple(primitive.right_head),
                tuple(primitive.base_start),
                tuple(primitive.base_end),
            ]
        if isinstance(primitive, Arrow):
            return [
                tuple(primitive.tail),
                tuple(primitive.tip),
                tuple(primitive.left_head),
                tuple(primitive.tip),
                tuple(primitive.right_head),
            ]
        if isinstance(primitive, Circle):
            if primitive._points:
                return [tuple(point) for point in primitive._points]
            if primitive.center is not None and primitive.radius is not None:
                points: list[Point] = []
                for idx in range(16):
                    angle = 2.0 * math.pi * idx / 16.0
                    points.append(
                        (
                            primitive.center[0] + math.cos(angle) * primitive.radius,
                            primitive.center[1] + math.sin(angle) * primitive.radius,
                        )
                    )
                return points
            return []
        points = getattr(primitive, "_points", None)
        if isinstance(points, list):
            return [tuple(point) for point in points]
        return []

    def _primitive_edges(self, primitive: Any) -> list[tuple[Point, Point]]:
        if isinstance(primitive, Segment):
            return [(tuple(primitive.start), tuple(primitive.end))]
        if isinstance(primitive, ArrowWithBase):
            return [
                (tuple(primitive.tail), tuple(primitive.tip)),
                (tuple(primitive.tip), tuple(primitive.left_head)),
                (tuple(primitive.tip), tuple(primitive.right_head)),
                (tuple(primitive.base_start), tuple(primitive.base_end)),
            ]
        if isinstance(primitive, RuneFire) and len(primitive.vertices) >= 3:
            vertices = [tuple(point) for point in primitive.vertices[:3]]
            edges: list[tuple[Point, Point]] = [
                (vertices[0], vertices[1]),
                (vertices[1], vertices[2]),
                (vertices[2], vertices[0]),
            ]
            for start, end in primitive.cuts[:3]:
                edges.append((tuple(start), tuple(end)))
            return edges
        points = self._primitive_points(primitive)
        if len(points) < 2:
            return []

        is_closed = isinstance(primitive, (Circle, Triangle))
        edges: list[tuple[Point, Point]] = []
        for idx in range(1, len(points)):
            edges.append((points[idx - 1], points[idx]))
        if is_closed and points[0] != points[-1]:
            edges.append((points[-1], points[0]))
        return edges

    @staticmethod
    def _segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
        def orientation(p: Point, q: Point, r: Point) -> float:
            return (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])

        def on_segment(p: Point, q: Point, r: Point) -> bool:
            return (
                min(p[0], r[0]) - 1e-9 <= q[0] <= max(p[0], r[0]) + 1e-9
                and min(p[1], r[1]) - 1e-9 <= q[1] <= max(p[1], r[1]) + 1e-9
            )

        o1 = orientation(a1, a2, b1)
        o2 = orientation(a1, a2, b2)
        o3 = orientation(b1, b2, a1)
        o4 = orientation(b1, b2, a2)

        if (o1 > 0 and o2 < 0 or o1 < 0 and o2 > 0) and (o3 > 0 and o4 < 0 or o3 < 0 and o4 > 0):
            return True
        if abs(o1) <= 1e-9 and on_segment(a1, b1, a2):
            return True
        if abs(o2) <= 1e-9 and on_segment(a1, b2, a2):
            return True
        if abs(o3) <= 1e-9 and on_segment(b1, a1, b2):
            return True
        if abs(o4) <= 1e-9 and on_segment(b1, a2, b2):
            return True
        return False

    @staticmethod
    def _point_in_triangle(point: Point, a: Point, b: Point, c: Point) -> bool:
        def sign(p1: Point, p2: Point, p3: Point) -> float:
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

        d1 = sign(point, a, b)
        d2 = sign(point, b, c)
        d3 = sign(point, c, a)

        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)
