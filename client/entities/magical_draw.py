import pygame
from pygame.surface import SurfaceType


class MagicalDraw:
    def __init__(self, screen):
        self._point_list: list[list[(int, int)]] = []
        self._points: list[(int, int)] = []
        self.surface = pygame.display.set_mode((screen.get_width(), screen.get_height()))

    def add_point(self, point: (int, int)):
        self._points.append(point)

    def validate_points_to_board(self):
        if self._points:
            self._point_list.append(self._points)
            self._points = []

    def draw(self, screen) -> SurfaceType:
        self.surface.set_alpha(10)

        to_draw = self._point_list
        if len(self._points) > 1:
            to_draw.append(self._points)

        for list_of_point in to_draw:
            previous_point = list_of_point[0]
            for point in list_of_point:
                pygame.draw.line(self.surface, (255, 255, 255), previous_point, point, 5)
                previous_point = point
        return self.surface


