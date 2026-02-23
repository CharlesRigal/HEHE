import pygame

from client.core.game_object import GameObject
from client.core.settings import HEIGHT


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

    def draw(self, screen, camera=None):
        if camera:
            screen_x = self.rect.x - camera.offset.x
            screen_y = self.rect.y - camera.offset.y
            pygame.draw.rect(screen, (255, 255, 0),
                             (screen_x, screen_y, self.rect.width, self.rect.height))
        else:
            pygame.draw.rect(screen, (255, 255, 0), self.rect)