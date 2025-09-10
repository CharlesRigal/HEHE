import time

import pygame

from entity import Life
from settings import WIDTH, HEIGHT


IN_UP = 1
IN_DOWN = 2
IN_LEFT = 3
IN_RIGHT = 4

IN_FIRE = 32


class Player:
    def __init__(self, image_path, pos, max_health=100):
        self.image = pygame.image.load(image_path).convert_alpha()
        self.pos = self.image.get_rect(center=pos)
        self.speed = 300
        self.life = Life(max_health)

    def read_local_input(self):
        keys = pygame.key.get_pressed()
        # mx, my = pygame.mouse.get_pos() TODO pour l'ajout de la souris sur l'écran
        # mb = pygame.mouse.get_pressed(3)

        mask = 0
        if keys[pygame.K_z]:
            mask |= IN_UP
        if keys[pygame.K_s]:
            mask |= IN_DOWN
        if keys[pygame.K_q]:
            mask |= IN_RIGHT
        if keys[pygame.K_d]:
            mask |= IN_LEFT

        return {"k": mask}


    def apply_input(self, inp, dt):
        k = inp.get("k", 0)
        speed = 200
        vx = vy = 0.0
        if k & IN_UP: vy -= speed
        if k & IN_DOWN: vy += speed
        if k & IN_LEFT: vx -= speed
        if k & IN_RIGHT: vx += speed

        self.pos.x += vx * dt
        self.pos.y += vy * dt

    def take_damage(self, damage):
        remaining_health = self.life.lose_health(damage)
        if self.life.is_dead():
            print("Player is dead!")
        return remaining_health

    def heal(self, amount):
        return self.life.heal(amount)

    def get_position(self) -> tuple:
        return self.pos.x, self.pos.y

    def update(self, dt):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_z]:
            self.pos.y -= self.speed * dt
        if keys[pygame.K_s]:
            self.pos.y += self.speed * dt
        if keys[pygame.K_q]:
            self.pos.x -= self.speed * dt
        if keys[pygame.K_d]:
            self.pos.x += self.speed * dt


        # collisions écran
        if self.pos.left < 0: self.pos.left = 0
        if self.pos.right > WIDTH: self.pos.right = WIDTH
        if self.pos.top < 0: self.pos.top = 0
        if self.pos.bottom > HEIGHT: self.pos.bottom = HEIGHT

    def draw(self, screen):
        screen.blit(self.image, self.pos)
