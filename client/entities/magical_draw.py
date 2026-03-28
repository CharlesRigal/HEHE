import pygame
import math
import os
from pygame.surface import SurfaceType
from typing import TypeAlias

from client.entities.recognition_effect_renderer import RecognitionEffectRenderer
from client.magic.circle_symbol_executor import CircleSubSymbolExecutor
from client.magic.graph_geo import GraphGeo, MagicalNode
from client.magic.primitives import Arrow, RuneFire, Segment, Circle, Triangle, ZigZag

ScreenPoint: TypeAlias = tuple[int, int]
TimedPoint: TypeAlias = tuple[ScreenPoint, float]
Stroke: TypeAlias = list[TimedPoint]


class MagicalDraw:
    MAGIC_SOUND_PATHS = [
        "sound/magic.flac",
        "songs/magic.flac",
        "client/assets/sounds/magic.flac",
        "client/assets/sounds/magic.ogg",
        "client/assets/sounds/magic.wav",
    ]

    def get_strokes(self) -> list[Stroke]:
        return list(self._point_list)

    def __init__(self, screen, clear_delay_seconds: float = 0.75):
        self._point_list: list[Stroke] = []
        self._points: Stroke = []
        self._magical_graph: GraphGeo = GraphGeo()
        self._circle_symbol_executor = CircleSubSymbolExecutor()
        self._recognition_effect_renderer = RecognitionEffectRenderer()
        self._primitive_drawers = {
            Segment: self._draw_segment_primitive,
            ZigZag: self._draw_zigzag_primitive,
            Circle: self._draw_circle_primitive,
            Triangle: self._draw_triangle_primitive,
            RuneFire: self._draw_rune_fire_primitive,
            Arrow: self._draw_arrow_primitive,
        }
        self.surface = pygame.Surface(screen.get_size(), pygame.SRCALPHA).convert_alpha()
        self._clear_delay_seconds = clear_delay_seconds
        self._clear_at: float | None = None
        self._magic_sound = self._load_magic_sound()
        self._magic_channel = None
        self._stroke_length = 0.0
        self._last_segment_speed = 0.0

    def resize_surface(self, size: tuple[int, int]) -> None:
        width = max(1, int(size[0]))
        height = max(1, int(size[1]))
        if self.surface.get_size() == (width, height):
            return

        previous = self.surface
        resized = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
        resized.blit(previous, (0, 0))
        self.surface = resized

    def add_node(self, primitive):
        self._magical_graph.add_node(primitive)
        self._try_execute_circle_subsymbols(primitive)
        now = pygame.time.get_ticks() / 1000.0
        self._recognition_effect_renderer.spawn(primitive, now)

    def _try_execute_circle_subsymbols(self, primitive) -> None:
        if not isinstance(primitive, Circle):
            return

        circle_index = len(self._magical_graph.iter_primitives()) - 1
        plan = self._magical_graph.build_circle_reading_plan(circle_index=circle_index)
        if plan is None or not plan.ordered_subsymbol_indices:
            return

        self._circle_symbol_executor.execute_reading_plan(
            plan=plan,
            primitives=self._magical_graph.iter_primitives(),
        )

    def _load_magic_sound(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception:
            return None

        for path in self.MAGIC_SOUND_PATHS:
            if not os.path.exists(path):
                continue
            try:
                return pygame.mixer.Sound(path)
            except Exception:
                continue
        return None

    def _ensure_magic_channel(self):
        if not self._magic_sound:
            return None
        if self._magic_channel and self._magic_channel.get_busy():
            return self._magic_channel
        try:
            self._magic_channel = self._magic_sound.play(loops=-1, fade_ms=80)
        except Exception:
            self._magic_channel = None
        return self._magic_channel

    def _stop_magic_audio(self):
        if self._magic_channel:
            try:
                self._magic_channel.fadeout(120)
            except Exception:
                pass
        self._magic_channel = None
        self._stroke_length = 0.0
        self._last_segment_speed = 0.0

    def _update_magic_audio(self, point: ScreenPoint, current_time: float, segment_length: float, dt: float):
        channel = self._ensure_magic_channel()
        if not channel:
            return

        self._stroke_length += max(0.0, segment_length)
        if segment_length > 0.0 and dt > 0.0:
            speed = segment_length / max(0.001, dt)
            self._last_segment_speed = self._last_segment_speed * 0.72 + speed * 0.28

        speed_norm = min(1.0, self._last_segment_speed / 900.0)
        length_norm = min(1.0, self._stroke_length / 420.0)
        pulse = 0.85 + 0.15 * math.sin(current_time * 7.0 + self._stroke_length * 0.02)
        volume = (0.13 + 0.45 * speed_norm + 0.28 * length_norm) * pulse
        volume = max(0.03, min(1.0, volume))

        width = max(1, self.surface.get_width())
        x_ratio = max(0.0, min(1.0, point[0] / width))
        pan = (x_ratio - 0.5) * 0.7
        if pan >= 0:
            left = volume * (1.0 - pan)
            right = volume
        else:
            left = volume
            right = volume * (1.0 + pan)
        channel.set_volume(max(0.0, left), max(0.0, right))

    def add_point(self, point: ScreenPoint, current_time: float) -> None:
        if not self._points:
            self._points.append((point, current_time))
            self._stroke_length = 0.0
            self._last_segment_speed = 0.0
            self._update_magic_audio(point, current_time, 0.0, 0.016)
            return

        last = self._points[-1]
        dx = point[0] - last[0][0]
        dy = point[1] - last[0][1]

        if dx * dx + dy * dy > 9:  # distance > 3px
            self._points.append((point, current_time))
            segment_length = math.hypot(dx, dy)
            dt = current_time - last[1]
            self._update_magic_audio(point, current_time, segment_length, dt)

    def validate_points_to_board(self) -> None:
        if self._points:
            self._point_list.append(self._points)
            self._points = []
        self._stop_magic_audio()

    def clear_board(self) -> None:
        self._point_list = []
        self._points = []
        self._stop_magic_audio()

    def has_primitives(self) -> bool:
        return self._magical_graph.get_head() is not None

    def get_spatial_relations(self):
        return self._magical_graph.build_spatial_relations()

    def get_priority_primitives(self):
        return self._magical_graph.resolve_priority_primitives()

    def schedule_clear(self, current_time: float) -> None:
        self._clear_at = current_time + self._clear_delay_seconds

    def cancel_clear(self) -> None:
        self._clear_at = None

    def should_render(self, current_time: float, board_pressed: bool) -> bool:
        if board_pressed:
            self.cancel_clear()
            return True

        if self._clear_at is None:
            return bool(self._point_list or self._points or self.has_primitives())

        if current_time < self._clear_at:
            return True

        self.clear_board()
        self._clear_at = None
        return False

    @staticmethod
    def _clamp_alpha(value: float) -> int:
        return max(0, min(255, int(value)))

    def _draw_magic_segment(
        self,
        start: ScreenPoint,
        end: ScreenPoint,
        now: float,
        segment_time: float,
        stroke_index: int,
        segment_index: int,
    ) -> None:
        age = max(0.0, now - segment_time)
        fade = max(0.35, 1.0 - age * 0.22)
        phase = now * 7.5 + stroke_index * 0.8 + segment_index * 0.35
        pulse = 0.5 + 0.5 * math.sin(phase)

        outer_width = max(2, int(10 + pulse * 4))
        mid_width = max(2, int(6 + pulse * 2))
        core_width = max(1, int(3 + pulse))

        outer = (90, 0, 170, self._clamp_alpha((55 + 45 * pulse) * fade))
        mid = (170, 60, 255, self._clamp_alpha((110 + 80 * pulse) * fade))
        core = (230, 235, 255, self._clamp_alpha((165 + 90 * pulse) * fade))

        pygame.draw.line(self.surface, outer, start, end, outer_width)
        pygame.draw.line(self.surface, mid, start, end, mid_width)
        pygame.draw.line(self.surface, core, start, end, core_width)

        spark_offset = 1.8 + pulse * 1.8
        spark_x = int(end[0] + math.sin(phase * 1.2) * spark_offset)
        spark_y = int(end[1] + math.cos(phase * 1.7) * spark_offset)
        spark_r = max(1, int(2 + pulse * 2))
        spark_color = (245, 245, 255, self._clamp_alpha((130 + 100 * pulse) * fade))
        pygame.draw.circle(self.surface, spark_color, (spark_x, spark_y), spark_r)

    def _draw_segment_primitive(self, primitive: Segment) -> None:
        pygame.draw.line(self.surface, (170, 70, 255, 95), primitive.start, primitive.end, 6)
        pygame.draw.line(self.surface, (245, 235, 255, 170), primitive.start, primitive.end, 2)

    def _draw_zigzag_primitive(self, primitive: ZigZag) -> None:
        if len(primitive.vertices) < 2:
            return
        pts = [(int(x), int(y)) for x, y in primitive.vertices]
        pygame.draw.lines(self.surface, (170, 70, 255, 95), False, pts, 6)
        pygame.draw.lines(self.surface, (245, 235, 255, 170), False, pts, 2)

    def _draw_circle_primitive(self, primitive: Circle) -> None:
        if primitive.center is None or primitive.radius is None:
            return
        center = (int(primitive.center[0]), int(primitive.center[1]))
        radius = max(1, int(primitive.radius))
        pygame.draw.circle(self.surface, (170, 70, 255, 95), center, radius + 2, 6)
        pygame.draw.circle(self.surface, (245, 235, 255, 170), center, radius, 2)

    def _draw_triangle_primitive(self, primitive: Triangle) -> None:
        if len(primitive.vertices) < 3:
            return
        pts = [(int(x), int(y)) for x, y in primitive.vertices[:3]]
        pygame.draw.polygon(self.surface, (170, 70, 255, 95), pts, 6)
        pygame.draw.polygon(self.surface, (245, 235, 255, 170), pts, 2)

    def _draw_rune_fire_primitive(self, primitive: RuneFire) -> None:
        if len(primitive.vertices) < 3:
            return
        pts = [(int(x), int(y)) for x, y in primitive.vertices[:3]]
        pygame.draw.polygon(self.surface, (235, 90, 40, 125), pts, 6)
        pygame.draw.polygon(self.surface, (255, 230, 210, 180), pts, 2)
        for cut_start, cut_end in primitive.cuts[:3]:
            start = (int(cut_start[0]), int(cut_start[1]))
            end = (int(cut_end[0]), int(cut_end[1]))
            pygame.draw.line(self.surface, (235, 90, 40, 125), start, end, 6)
            pygame.draw.line(self.surface, (255, 230, 210, 180), start, end, 2)

    def _draw_arrow_primitive(self, primitive: Arrow) -> None:
        tip = (int(primitive.tip[0]), int(primitive.tip[1]))
        tail = (int(primitive.tail[0]), int(primitive.tail[1]))
        left = (int(primitive.left_head[0]), int(primitive.left_head[1]))
        right = (int(primitive.right_head[0]), int(primitive.right_head[1]))
        pygame.draw.line(self.surface, (170, 70, 255, 95), tail, tip, 6)
        pygame.draw.line(self.surface, (170, 70, 255, 95), tip, left, 6)
        pygame.draw.line(self.surface, (170, 70, 255, 95), tip, right, 6)
        pygame.draw.line(self.surface, (245, 235, 255, 170), tail, tip, 2)
        pygame.draw.line(self.surface, (245, 235, 255, 170), tip, left, 2)
        pygame.draw.line(self.surface, (245, 235, 255, 170), tip, right, 2)

    def draw(self) -> SurfaceType:
        self.surface.fill((0, 0, 0, 0))
        now = pygame.time.get_ticks() / 1000.0

        to_draw = list(self._point_list)
        if len(self._points) > 1:
            to_draw.append(self._points)

        for stroke_index, stroke in enumerate(to_draw):
            for segment_index, (p1, p2) in enumerate(zip(stroke, stroke[1:])):
                self._draw_magic_segment(
                    p1[0],
                    p2[0],
                    now,
                    p2[1],
                    stroke_index,
                    segment_index,
                )

        simplified_stroke: MagicalNode | None = self._magical_graph.get_head()
        while simplified_stroke is not None:
            primitive = simplified_stroke.primitive
            drawer = self._primitive_drawers.get(type(primitive))
            if drawer is not None:
                drawer(primitive)
            simplified_stroke = simplified_stroke.child

        self._recognition_effect_renderer.draw(self.surface, now)
        return self.surface


