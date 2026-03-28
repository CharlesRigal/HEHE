from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeAlias

import pygame
from pygame.surface import SurfaceType

from client.magic.primitives import Arrow, Circle, RuneFire, Segment, Triangle, ZigZag

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
        (Arrow, "arrow"),
        (RuneFire, "rune_fire"),
    )

    DEFAULT_CONFIG: dict[str, tuple[float, Color3]] = {
        "segment": (0.45, (255, 210, 120)),
        "zigzag": (0.58, (255, 180, 90)),
        "circle": (0.60, (120, 230, 255)),
        "triangle": (0.56, (190, 255, 145)),
        "arrow": (0.52, (255, 145, 220)),
        "rune_fire": (0.62, (255, 125, 90)),
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
        pulse = 0.5 + 0.5 * math.sin(effect.start_time * 23.0 + progress * 11.0)

        start = self._point_to_screen(primitive.start)
        end = self._point_to_screen(primitive.end)
        outer_width = max(2, int(3 + 9 * fade))
        core_width = max(1, int(1 + 3 * fade))

        pygame.draw.line(
            surface,
            self._color_with_alpha(effect.color, (140 + 80 * pulse) * fade),
            start,
            end,
            outer_width,
        )
        pygame.draw.line(
            surface,
            (255, 255, 255, self._clamp_alpha(210 * fade)),
            start,
            end,
            core_width,
        )

        spark_t = min(1.0, progress * 1.45)
        spark = self._point_to_screen(self._lerp_point(primitive.start, primitive.end, spark_t))
        spark_radius = max(2, int(4 + 9 * fade))
        pygame.draw.circle(
            surface,
            self._color_with_alpha(effect.color, 200 * fade),
            spark,
            spark_radius,
        )

    def _draw_circle_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, Circle) or primitive.center is None or primitive.radius is None:
            return

        fade = max(0.0, 1.0 - progress)
        ring_radius = max(1, int(primitive.radius * (1.0 + 0.28 * progress)))
        center = self._point_to_screen(primitive.center)
        width = max(1, int(2 + 10 * fade))

        pygame.draw.circle(
            surface,
            self._color_with_alpha(effect.color, 200 * fade),
            center,
            ring_radius,
            width,
        )
        pygame.draw.circle(
            surface,
            self._color_with_alpha(effect.color, 45 * fade),
            center,
            max(1, int(ring_radius * 0.8)),
            0,
        )

    def _draw_zigzag_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, ZigZag) or len(primitive.vertices) < 2:
            return

        fade = max(0.0, 1.0 - progress)
        vertices = [tuple(point) for point in primitive.vertices]
        visible_segments = max(1, int((len(vertices) - 1) * min(1.0, progress * 1.6)))
        path_points = vertices[: visible_segments + 1]
        points = [self._point_to_screen(point) for point in path_points]

        pygame.draw.lines(
            surface,
            self._color_with_alpha(effect.color, 190 * fade),
            False,
            points,
            max(2, int(2 + 8 * fade)),
        )
        pygame.draw.lines(
            surface,
            (255, 255, 255, self._clamp_alpha(150 * fade)),
            False,
            points,
            max(1, int(1 + 3 * fade)),
        )

        tip = points[-1]
        pygame.draw.circle(
            surface,
            self._color_with_alpha(effect.color, 220 * fade),
            tip,
            max(2, int(4 + 8 * fade)),
        )

    def _draw_triangle_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, Triangle) or len(primitive.vertices) < 3:
            return

        fade = max(0.0, 1.0 - progress)
        vertices = [tuple(point) for point in primitive.vertices[:3]]
        center_x = sum(point[0] for point in vertices) / 3.0
        center_y = sum(point[1] for point in vertices) / 3.0
        center = (center_x, center_y)
        scale = 0.82 + 0.30 * progress

        scaled_vertices: list[ScreenPoint] = []
        for vx, vy in vertices:
            sx = center[0] + (vx - center[0]) * scale
            sy = center[1] + (vy - center[1]) * scale
            scaled_vertices.append((int(sx), int(sy)))

        pygame.draw.polygon(
            surface,
            self._color_with_alpha(effect.color, 170 * fade),
            scaled_vertices,
            max(1, int(2 + 8 * fade)),
        )
        pygame.draw.polygon(
            surface,
            (255, 255, 255, self._clamp_alpha(65 * fade)),
            scaled_vertices,
            0,
        )

    def _draw_arrow_effect(self, surface: SurfaceType, effect: RecognitionEffect, progress: float) -> None:
        primitive = effect.primitive
        if not isinstance(primitive, Arrow):
            return

        fade = max(0.0, 1.0 - progress)
        beam_progress = min(1.0, progress * 1.6)
        tail = tuple(primitive.tail)
        tip = tuple(primitive.tip)
        left_head = tuple(primitive.left_head)
        right_head = tuple(primitive.right_head)
        beam_end = self._lerp_point(tail, tip, beam_progress)

        pygame.draw.line(
            surface,
            self._color_with_alpha(effect.color, 200 * fade),
            self._point_to_screen(tail),
            self._point_to_screen(beam_end),
            max(2, int(2 + 9 * fade)),
        )

        wing_progress = max(0.0, min(1.0, (progress - 0.20) / 0.80))
        if wing_progress > 0.0:
            wing_left = self._lerp_point(tip, left_head, wing_progress)
            wing_right = self._lerp_point(tip, right_head, wing_progress)
            wing_width = max(1, int(2 + 7 * fade))
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

        tip_radius = max(2, int(5 + 10 * fade))
        pygame.draw.circle(
            surface,
            (255, 255, 255, self._clamp_alpha(220 * fade)),
            self._point_to_screen(tip),
            tip_radius,
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
            self._color_with_alpha(effect.color, (185 * fade) * flicker),
            scaled_vertices,
            max(2, int(2 + 9 * fade)),
        )

        for cut_start, cut_end in primitive.cuts[:3]:
            start = self._point_to_screen(cut_start)
            end = self._point_to_screen(cut_end)
            pygame.draw.line(
                surface,
                self._color_with_alpha(effect.color, (210 * fade) * pulse),
                start,
                end,
                max(2, int(2 + 6 * fade)),
            )
            pygame.draw.line(
                surface,
                (255, 245, 235, self._clamp_alpha(130 * fade)),
                start,
                end,
                max(1, int(1 + 2 * fade)),
            )
