import pygame
from pygame.surface import SurfaceType
from typing import TypeAlias

from client.magic.graph_geo import GraphGeo, MagicalNode
from client.magic.primitives import Segment

ScreenPoint: TypeAlias = tuple[int, int]
TimedPoint: TypeAlias = tuple[ScreenPoint, float]
Stroke: TypeAlias = list[TimedPoint]


class MagicalDraw:
    def get_strokes(self) -> list[Stroke]:
        return list(self._point_list)

    def __init__(self, screen):
        self._point_list: list[Stroke] = []
        self._points: Stroke = []
        self._magical_graph: GraphGeo = GraphGeo()
        self.surface = pygame.Surface(screen.get_size(), pygame.SRCALPHA).convert_alpha()

    def add_node(self, primitive):
        self._magical_graph.add_node(primitive)

    def add_point(self, point: ScreenPoint, current_time: float) -> None:
        if not self._points:
            self._points.append((point, current_time))
            return

        last = self._points[-1]
        dx = point[0] - last[0][0]
        dy = point[1] - last[0][1]

        if dx * dx + dy * dy > 9:  # distance > 3px
            self._points.append((point, current_time))

    def validate_points_to_board(self) -> None:
        if self._points:
            self._point_list.append(self._points)
            self._points = []

    def clear_board(self) -> None:
        self._point_list = []

    def draw(self) -> SurfaceType:
        self.surface.fill((0, 0, 0, 0))

        to_draw = list(self._point_list)
        if len(self._points) > 1:
            to_draw.append(self._points)

        for stroke in to_draw:
            for p1, p2 in zip(stroke, stroke[1:]):
                pygame.draw.line(
                    self.surface,
                    (255, 255, 255, 180),
                    p1[0],
                    p2[0],
                    4
                )

        symplified_strock: MagicalNode|None = self._magical_graph.get_head()
        while symplified_strock is not None:
            if isinstance(symplified_strock, Segment):
                line:Segment = symplified_strock
                pygame.draw.line(self.surface, (255, 0, 255, 90), line.start, symplified_strock.end, 80)

        return self.surface


