from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeAlias

import pygame
from pygame.surface import SurfaceType

from client.magic.primitives import Arrow, ArrowWithBase, Circle, RuneFire, Segment, Triangle, ZigZag

Point: TypeAlias = tuple[float, float]
ScreenPoint: TypeAlias = tuple[int, int]
Color3: TypeAlias = tuple[int, int, int]


@dataclass(slots=True)
class RecognitionEffect:
    kind: str
    primitive: object
    start_time: float
    duration: float
    color: Color3


class RecognitionEffectRenderer:
    _KIND_BY_TYPE: tuple[tuple[type, str], ...] = (
        (Segment, "segment"),
        (ZigZag, "zigzag"),
        (Circle, "circle"),
        (Triangle, "triangle"),
        (ArrowWithBase, "arrow_with_base"),
        (Arrow, "arrow"),
        (RuneFire, "rune_fire"),
    )

    DEFAULT_CONFIG: dict[str, tuple[float, Color3]] = {
        "segment": (0.36, (255, 240, 70)),
        "zigzag": (0.52, (255, 95, 30)),
        "circle": (0.58, (50, 240, 255)),
        "triangle": (0.50, (110, 255, 90)),
        "arrow": (0.46, (238, 90, 255)),
        "arrow_with_base": (0.56, (255, 175, 30)),
        "rune_fire": (0.64, (255, 55, 20)),
    }
    def __init__(
        self,
        config: dict[str, tuple[float, Color3]] | None = None,
        max_effects: int = 48,
    ) -> None:
        self._config: dict[str, tuple[float, Color3]] = dict(self.DEFAULT_CONFIG)
        if config:
            self._config.update(config)
        self._max_effects = max(1, int(max_effects))
        self._effects: list[RecognitionEffect] = []
        self._effect_drawers = {
            "segment": self._draw_segment_effect,
            "zigzag": self._draw_zigzag_effect,
            "circle": self._draw_circle_effect,
            "triangle": self._draw_triangle_effect,
            "arrow": self._draw_arrow_effect,
            "arrow_with_base": self._draw_arrow_with_base_effect,
            "rune_fire": self._draw_rune_fire_effect,
        }

    def spawn(self, primitive: object, now: float) -> None:
        kind = self._primitive_kind(primitive)
        config = self._config.get(kind)
        if config is None:
            return

        duration, color = config
        self._effects.append(
            RecognitionEffect(
                kind=kind,
                primitive=primitive,
                start_time=now,
                duration=duration,
                color=color,
            )
        )
        if len(self._effects) > self._max_effects:
            self._effects = self._effects[-self._max_effects :]

    def draw(self, surface: SurfaceType, now: float) -> None:
        if not self._effects:
            return

        active: list[RecognitionEffect] = []
        for effect in self._effects:
            age = now - effect.start_time
            if age < 0.0 or age > effect.duration:
                continue

            progress = age / max(effect.duration, 1e-6)
            drawer = self._effect_drawers.get(effect.kind)
            if drawer is not None:
                drawer(surface, effect, progress)

            active.append(effect)

        self._effects = active

    def clear(self) -> None:
        self._effects.clear()

    @staticmethod
    def _primitive_kind(primitive: object) -> str:
        for primitive_type, kind in RecognitionEffectRenderer._KIND_BY_TYPE:
            if isinstance(primitive, primitive_type):
                return kind
        return ""

    @staticmethod
    def _lerp_point(a: Point, b: Point, t: float) -> Point:
        ratio = max(0.0, min(1.0, t))
        return (
            a[0] + (b[0] - a[0]) * ratio,
            a[1] + (b[1] - a[1]) * ratio,
        )

    @staticmethod
    def _point_to_screen(point: Point) -> ScreenPoint:
        return (int(point[0]), int(point[1]))

    @staticmethod
    def _clamp_alpha(value: float) -> int:
        return max(0, min(255, int(value)))

    def _color_with_alpha(self, color: Color3, alpha: float) -> tuple[int, int, int, int]:
        return (color[0], color[1], color[2], self._clamp_alpha(alpha))

    def _draw_segment_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, Segment):
            return

        fade = max(0.0, 1.0 - progress)
        pulse = 0.5 + 0.5 * math.sin(effect.start_time * 23.0 + progress * 13.0)

        start = self._point_to_screen(primitive.start)
        end = self._point_to_screen(primitive.end)
        outer_width = max(3, int(5 + 10 * fade))
        core_width = max(2, int(2 + 4 * fade))

        pygame.draw.line(
            surface,
            self._color_with_alpha(effect.color, (140 + 80 * pulse) * fade),
            start,
            end,
            outer_width,
        )
        pygame.draw.line(
            surface,
            (255, 160, 40, self._clamp_alpha(130 * fade)),
            start,
            end,
            max(2, outer_width - 2),
        )
        pygame.draw.line(
            surface,
            (255, 252, 210, self._clamp_alpha(245 * fade)),
            start,
            end,
            core_width,
        )

        spark_t = min(1.0, progress * 1.45)
        spark = self._point_to_screen(self._lerp_point(primitive.start, primitive.end, spark_t))
        spark_radius = max(3, int(6 + 10 * fade))
        pygame.draw.circle(
            surface,
            self._color_with_alpha(effect.color, 200 * fade),
            spark,
            spark_radius,
        )
        midpoint = self._point_to_screen(self._lerp_point(primitive.start, primitive.end, 0.5))
        mid_radius = max(1, int(2 + 5 * pulse * fade))
        pygame.draw.circle(surface, (255, 245, 170, self._clamp_alpha(170 * fade)), midpoint, mid_radius)
        cap_radius = max(2, int(3 + 5 * fade))
        pygame.draw.circle(surface, (255, 235, 155, self._clamp_alpha(150 * fade)), start, cap_radius)
        pygame.draw.circle(surface, (255, 235, 155, self._clamp_alpha(150 * fade)), end, cap_radius)

    def _draw_circle_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, Circle) or primitive.center is None or primitive.radius is None:
            return

        fade = max(0.0, 1.0 - progress)
        outer_radius = max(1, int(primitive.radius * (1.0 + 0.32 * progress)))
        inner_radius = max(1, int(primitive.radius * (0.78 + 0.20 * (1.0 - progress))))
        center = self._point_to_screen(primitive.center)
        width = max(2, int(3 + 10 * fade))
        phase = effect.start_time * 10.0 + progress * 12.0

        pygame.draw.circle(
            surface,
            self._color_with_alpha(effect.color, 200 * fade),
            center,
            outer_radius,
            width,
        )
        pygame.draw.circle(
            surface,
            (165, 245, 255, self._clamp_alpha(165 * fade)),
            center,
            inner_radius,
            max(1, int(1 + 6 * fade)),
        )
        orbit_radius = max(2, int(primitive.radius * (0.95 + 0.10 * progress)))
        orbit_x = int(primitive.center[0] + math.cos(phase) * orbit_radius)
        orbit_y = int(primitive.center[1] + math.sin(phase) * orbit_radius)
        pygame.draw.circle(
            surface,
            (220, 250, 255, self._clamp_alpha(220 * fade)),
            (orbit_x, orbit_y),
            max(3, int(4 + 6 * fade)),
        )
        orbit_x_b = int(primitive.center[0] + math.cos(phase + math.pi) * orbit_radius)
        orbit_y_b = int(primitive.center[1] + math.sin(phase + math.pi) * orbit_radius)
        pygame.draw.circle(
            surface,
            (120, 245, 255, self._clamp_alpha(190 * fade)),
            (orbit_x_b, orbit_y_b),
            max(2, int(3 + 4 * fade)),
        )
        spark_r = max(1, int(2 + 3 * fade))
        for axis in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
            px = int(primitive.center[0] + math.cos(axis + phase * 0.35) * inner_radius)
            py = int(primitive.center[1] + math.sin(axis + phase * 0.35) * inner_radius)
            pygame.draw.circle(surface, (210, 255, 255, self._clamp_alpha(165 * fade)), (px, py), spark_r)

    def _draw_zigzag_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, ZigZag) or len(primitive.vertices) < 2:
            return

        fade = max(0.0, 1.0 - progress)
        vertices = [tuple(point) for point in primitive.vertices]
        visible_segments = max(1, int((len(vertices) - 1) * min(1.0, progress * 1.6)))
        path_points = vertices[: visible_segments + 1]
        points = [self._point_to_screen(point) for point in path_points]
        pulse = 0.5 + 0.5 * math.sin(effect.start_time * 21.0 + progress * 18.0)

        pygame.draw.lines(
            surface,
            self._color_with_alpha(effect.color, 190 * fade),
            False,
            points,
            max(3, int(3 + 9 * fade)),
        )
        ghost = [(point[0] + 2, point[1] + 2) for point in points]
        pygame.draw.lines(
            surface,
            (255, 70, 35, self._clamp_alpha(95 * fade)),
            False,
            ghost,
            max(2, int(2 + 7 * fade)),
        )
        pygame.draw.lines(
            surface,
            (255, 236, 210, self._clamp_alpha(175 * fade)),
            False,
            points,
            max(2, int(2 + 3 * fade)),
        )

        tip = points[-1]
        pygame.draw.circle(
            surface,
            self._color_with_alpha(effect.color, 220 * fade),
            tip,
            max(3, int(5 + 9 * fade)),
        )
        for index, point in enumerate(points[:-1]):
            if index % 2 != 0:
                continue
            node_radius = max(1, int(2 + 3 * pulse * fade))
            pygame.draw.circle(
                surface,
                (255, 205, 150, self._clamp_alpha(130 * fade)),
                point,
                node_radius,
            )

    def _draw_triangle_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, Triangle) or len(primitive.vertices) < 3:
            return

        fade = max(0.0, 1.0 - progress)
        pulse = 0.5 + 0.5 * math.sin(effect.start_time * 24.0 + progress * 16.0)
        vertices = [tuple(point) for point in primitive.vertices[:3]]
        center_x = sum(point[0] for point in vertices) / 3.0
        center_y = sum(point[1] for point in vertices) / 3.0
        center = (center_x, center_y)
        scale = 0.84 + 0.28 * progress

        scaled: list[Point] = []
        for vx, vy in vertices:
            sx = center[0] + (vx - center[0]) * scale
            sy = center[1] + (vy - center[1]) * scale
            scaled.append((sx, sy))
        polygon = [self._point_to_screen(point) for point in scaled]

        edges = [(scaled[0], scaled[1]), (scaled[1], scaled[2]), (scaled[2], scaled[0])]
        for edge_index, (start, end) in enumerate(edges):
            edge_progress = max(0.0, min(1.0, (progress - edge_index * 0.20) / 0.55))
            if edge_progress <= 0.0:
                continue
            edge_end = self._lerp_point(start, end, edge_progress)
            pygame.draw.line(
                surface,
                self._color_with_alpha(effect.color, 190 * fade),
                self._point_to_screen(start),
                self._point_to_screen(edge_end),
                max(2, int(3 + 7 * fade)),
            )

        pygame.draw.polygon(
            surface,
            (120, 255, 120, self._clamp_alpha((70 + 40 * pulse) * fade)),
            polygon,
            0,
        )
        for point in polygon:
            pygame.draw.circle(
                surface,
                (230, 255, 225, self._clamp_alpha(150 * fade)),
                point,
                max(1, int(2 + 4 * fade)),
            )
        center_point = (int(center_x), int(center_y))
        pygame.draw.circle(
            surface,
            (220, 255, 200, self._clamp_alpha(190 * fade)),
            center_point,
            max(2, int(3 + 4 * pulse * fade)),
        )

    def _draw_arrow_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, (Arrow, ArrowWithBase)):
            return

        fade = max(0.0, 1.0 - progress)
        beam_progress = min(1.0, progress * 1.6)
        tail = tuple(primitive.tail)
        tip = tuple(primitive.tip)
        left_head = tuple(primitive.left_head)
        right_head = tuple(primitive.right_head)
        beam_end = self._lerp_point(tail, tip, beam_progress)
        pulse = 0.5 + 0.5 * math.sin(effect.start_time * 25.0 + progress * 14.0)

        pygame.draw.line(
            surface,
            self._color_with_alpha(effect.color, 200 * fade),
            self._point_to_screen(tail),
            self._point_to_screen(beam_end),
            max(3, int(4 + 10 * fade)),
        )
        pygame.draw.line(
            surface,
            (255, 205, 255, self._clamp_alpha(235 * fade)),
            self._point_to_screen(tail),
            self._point_to_screen(beam_end),
            max(2, int(2 + 4 * fade)),
        )

        wing_progress = max(0.0, min(1.0, (progress - 0.20) / 0.80))
        if wing_progress > 0.0:
            wing_left = self._lerp_point(tip, left_head, wing_progress)
            wing_right = self._lerp_point(tip, right_head, wing_progress)
            wing_width = max(2, int(3 + 8 * fade))
            pygame.draw.line(
                surface,
                self._color_with_alpha(effect.color, 185 * fade),
                self._point_to_screen(tip),
                self._point_to_screen(wing_left),
                wing_width,
            )
            pygame.draw.line(
                surface,
                self._color_with_alpha(effect.color, 185 * fade),
                self._point_to_screen(tip),
                self._point_to_screen(wing_right),
                wing_width,
            )

        trail_1 = self._lerp_point(tail, tip, max(0.0, beam_progress - 0.18))
        trail_2 = self._lerp_point(tail, tip, max(0.0, beam_progress - 0.35))
        pygame.draw.circle(
            surface,
            (255, 195, 255, self._clamp_alpha(130 * fade)),
            self._point_to_screen(trail_1),
            max(1, int(2 + 4 * pulse * fade)),
        )
        pygame.draw.circle(
            surface,
            (255, 185, 250, self._clamp_alpha(90 * fade)),
            self._point_to_screen(trail_2),
            max(1, int(1 + 3 * fade)),
        )

        tip_radius = max(2, int(5 + 10 * fade))
        pygame.draw.circle(
            surface,
            (255, 255, 255, self._clamp_alpha(220 * fade)),
            self._point_to_screen(tip),
            max(3, tip_radius),
        )

    def _draw_arrow_with_base_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, ArrowWithBase):
            return

        self._draw_arrow_effect(surface, effect, progress)
        fade = max(0.0, 1.0 - progress)
        base_progress = max(0.0, min(1.0, (progress - 0.16) / 0.84))
        start = tuple(primitive.base_start)
        end = tuple(primitive.base_end)
        draw_end = self._lerp_point(start, end, base_progress)
        pulse = 0.5 + 0.5 * math.sin(effect.start_time * 28.0 + progress * 12.0)

        pygame.draw.line(
            surface,
            self._color_with_alpha(effect.color, 210 * fade),
            self._point_to_screen(start),
            self._point_to_screen(draw_end),
            max(3, int(4 + 8 * fade)),
        )
        pygame.draw.line(
            surface,
            (255, 255, 245, self._clamp_alpha(150 * fade)),
            self._point_to_screen(start),
            self._point_to_screen(draw_end),
            max(2, int(2 + 3 * fade)),
        )
        tail = self._point_to_screen(tuple(primitive.tail))
        pygame.draw.circle(
            surface,
            (255, 230, 155, self._clamp_alpha(180 * fade)),
            tail,
            max(2, int(3 + 5 * pulse * fade)),
        )
        pygame.draw.circle(
            surface,
            (255, 230, 120, self._clamp_alpha(170 * fade)),
            self._point_to_screen(start),
            max(2, int(2 + 4 * fade)),
        )
        pygame.draw.circle(
            surface,
            (255, 230, 120, self._clamp_alpha(170 * fade)),
            self._point_to_screen(end),
            max(2, int(2 + 4 * fade)),
        )

    def _draw_rune_fire_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, RuneFire) or len(primitive.vertices) < 3:
            return

        fade = max(0.0, 1.0 - progress)
        flicker = 0.82 + 0.18 * math.sin(effect.start_time * 19.0 + progress * 17.0)
        pulse = 0.88 + 0.12 * math.sin(effect.start_time * 13.0 + progress * 9.5)

        vertices = [tuple(point) for point in primitive.vertices[:3]]
        center_x = sum(point[0] for point in vertices) / 3.0
        center_y = sum(point[1] for point in vertices) / 3.0
        scale = 0.80 + 0.26 * progress

        scaled_vertices: list[ScreenPoint] = []
        for vx, vy in vertices:
            sx = center_x + (vx - center_x) * scale
            sy = center_y + (vy - center_y) * scale
            scaled_vertices.append((int(sx), int(sy)))

        pygame.draw.polygon(
            surface,
            (255, 145, 90, self._clamp_alpha(65 * fade)),
            scaled_vertices,
            0,
        )
        pygame.draw.polygon(
            surface,
            self._color_with_alpha(effect.color, (185 * fade) * flicker),
            scaled_vertices,
            max(3, int(4 + 10 * fade)),
        )

        for cut_start, cut_end in primitive.cuts[:3]:
            start = self._point_to_screen(cut_start)
            end = self._point_to_screen(cut_end)
            pygame.draw.line(
                surface,
                self._color_with_alpha(effect.color, (210 * fade) * pulse),
                start,
                end,
                max(3, int(3 + 7 * fade)),
            )
            pygame.draw.line(
                surface,
                (255, 245, 235, self._clamp_alpha(130 * fade)),
                start,
                end,
                max(1, int(1 + 2 * fade)),
            )
        for spark_idx in range(3):
            angle = effect.start_time * 6.0 + progress * 11.0 + spark_idx * (2.0 * math.pi / 3.0)
            orbit = 6.0 + progress * 14.0 + spark_idx * 2.0
            spark_x = int(center_x + math.cos(angle) * orbit)
            spark_y = int(center_y + math.sin(angle) * orbit)
            pygame.draw.circle(
                surface,
                (255, 225, 160, self._clamp_alpha(165 * fade)),
                (spark_x, spark_y),
                max(1, int(2 + 3 * fade)),
            )
        shock_radius = max(3, int((8.0 + progress * 42.0)))
        pygame.draw.circle(
            surface,
            (255, 120, 80, self._clamp_alpha(135 * fade)),
            (int(center_x), int(center_y)),
            shock_radius,
            max(1, int(2 + 4 * fade)),
        )
