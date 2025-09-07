import pygame
from settings import WIDTH, HEIGHT

class Player:
    def __init__(self, image_path, pos):
        self.image = pygame.image.load(image_path).convert_alpha()
        self.rect = self.image.get_rect(center=pos)
        self.speed = 300

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
