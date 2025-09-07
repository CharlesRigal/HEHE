import pygame

from settings import WIDTH, HEIGHT


class Enemy:
    def __init__(self, image_path, pos):
        self.image = pygame.image.load(image_path).convert_alpha()
        self.rect = self.image.get_rect(center=pos)
        self.speed = 200


class EnemyEye(Enemy):
    def __init__(self):
        super().__init__("assets/images/enemy.png", (WIDTH/2, HEIGHT/2))

    def draw(self, screen):
        screen.blit(self.image, self.rect)
