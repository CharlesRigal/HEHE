import pygame

from settings import WIDTH, HEIGHT


class Enemy:
    def __init__(self, image_path, pos):
        self.image = pygame.image.load(image_path).convert_alpha()
        self.rect = self.image.get_rect(center=pos)
        self.speed = 200


class EnemyEye(Enemy):
    def __init__(self, image_path="assets/images/enemy.png", pos=(WIDTH/2, HEIGHT/2)):
        super().__init__(image_path=image_path, pos=pos)

    def draw(self, screen):
        screen.blit(self.image, self.rect)
