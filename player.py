import pygame

from entity import Life
from settings import WIDTH, HEIGHT

class Player:
    def __init__(self, image_path, pos, max_health=100):
        self.image = pygame.image.load(image_path).convert_alpha()
        self.rect = self.image.get_rect(center=pos)
        self.speed = 300
        self.life = Life(max_health)

    def take_damage(self, damage):
        remaining_health = self.life.lose_health(damage)
        if self.life.is_dead():
            print("Player is dead!")
        return remaining_health

    def heal(self, amount):
        return self.life.heal(amount)

    def get_position(self):
        return (self.rect.x, self.rect.y)

    def update(self, dt):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_z]:
            self.rect.y -= self.speed * dt
        if keys[pygame.K_s]:
            self.rect.y += self.speed * dt
        if keys[pygame.K_q]:
            self.rect.x -= self.speed * dt
        if keys[pygame.K_d]:
            self.rect.x += self.speed * dt

        # collisions écran
        if self.rect.left < 0: self.rect.left = 0
        if self.rect.right > WIDTH: self.rect.right = WIDTH
        if self.rect.top < 0: self.rect.top = 0
        if self.rect.bottom > HEIGHT: self.rect.bottom = HEIGHT

    def draw(self, screen):
        screen.blit(self.image, self.rect)
