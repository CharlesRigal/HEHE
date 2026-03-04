import pygame
from pygame.surface import SurfaceType

from client.magic.graph_geo import GraphGeo


class MagicalDraw:
    def get_strokes(self):
        return list(self._point_list)

    def __init__(self, screen):
        self._point_list: list[list[(int, int)]] = []
        self._points: list[(int, int)] = []
        self._magical_graph: GraphGeo = GraphGeo()
        self.surface = pygame.Surface(screen.get_size(), pygame.SRCALPHA).convert_alpha()

    def add_node(self, primitive):
        self._magical_graph.add_node(primitive)

    def add_point(self, point, current_time):
        if not self._points:
            self._points.append((point, current_time))
            return

        last = self._points[-1]
        dx = point[0] - last[0][0]
        dy = point[1] - last[0][1]

        if dx * dx + dy * dy > 9:  # distance > 3px
            self._points.append((point, current_time))

    def validate_points_to_board(self):
        if self._points:
            self._point_list.append(self._points)
            to_return = self._point_list
            self._points = []
            return to_return
        return None

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
                    p1,
                    p2,
                    4
                )

        return self.surface


