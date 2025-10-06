import pygame
from client.core.game_object import GameObject

class BaseEntity(GameObject):
    def __init__(self, x, y, image_path, max_health=100):
        super().__init__()
        self.pos = pygame.Vector2(x, y)
        self.image = pygame.image.load(image_path).convert_alpha()
        self.rect = self.image.get_rect(center=(x, y))
        self.health = max_health
        self.alive = True

    def draw(self, screen: pygame.Surface):
        if self.alive:
            screen.blit(self.image, self.rect)

    def update(self, dt: float, **kwargs):
        self.rect.center = (int(self.pos.x), int(self.pos.y))
