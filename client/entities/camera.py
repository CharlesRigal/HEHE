import pygame


class Camera:
    def __init__(self, screen):
        self.screen = screen
        self.offset = pygame.Vector2(0, 0)

    def update(self, target_pos):
        screen_w, screen_h = self.screen.get_size()

        self.offset.x = target_pos.x - screen_w / 2
        self.offset.y = target_pos.y - screen_h / 2

    def apply(self, pos):
        return pos - self.offset