import pygame

from game_object import GameObject
from settings import HEIGHT


class Projectile(GameObject):
    def __init__(self, damage, source_rect, speed, lifetime):
        super().__init__()
        self.damage = damage
        self.rect = pygame.Rect(source_rect.centerx, source_rect.centery, 5, 10)
        self.speed = speed
        self.lifetime = lifetime
        self.timer = 0

    def update(self, dt, *args):
        """Mise à jour du projectile"""
        self.rect.y -= self.speed * dt
        self.timer += dt

        # Se supprimer si hors écran ou temps écoulé
        if (self.rect.bottom < 0 or
                self.rect.top > HEIGHT or
                self.timer > self.lifetime):
            self.mark_for_removal()

    def draw(self, screen):
        pygame.draw.rect(screen, (255, 255, 0), self.rect)