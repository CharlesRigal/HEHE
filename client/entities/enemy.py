from abc import ABC
import math

import pygame

from client.core.game_object import GameObject
from client.entities.damagable import Damagable
from client.entities.entity import Life


class Enemy(GameObject, Damagable, ABC):
    def __init__(self, image_path, pos, max_health=50):
        super().__init__()
        self.life = Life(max_health)
        self.image = pygame.image.load(image_path).convert_alpha()
        self.pos = pygame.Vector2(pos[0], pos[1])
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))
        self.speed = 100

    def on_death(self):
        self.active = False
        self.to_remove = True
        print("Enemy defeated!")

    def travel_to_player(self, player_entity, dt):
        """Version précise : mouvement vectoriel lisse."""
        player_x, player_y = player_entity.get_position()
        dx = player_x - self.pos.x
        dy = player_y - self.pos.y
        distance = math.hypot(dx, dy)

        # Evite les oscillations quand l'ennemi est quasiment au contact.
        if distance > 2:
            nx = dx / distance
            ny = dy / distance
            self.pos.x += nx * self.speed * dt
            self.pos.y += ny * self.speed * dt

        self.rect.center = (int(self.pos.x), int(self.pos.y))


class EnemyEye(Enemy):
    def __init__(self, image_path="client/assets/images/enemy.png", pos=(0, 0), targeted_player=None):
        self.targeted_player = targeted_player
        super().__init__(image_path=image_path, pos=pos, max_health=100)

    def set_targeted_player(self, player):
        self.targeted_player = player

    def update(self, dt, *args, **kwargs):
        if self.targeted_player is not None:
            self.travel_to_player(self.targeted_player, dt)

    def draw(self, screen, camera=None):
        if camera:
            screen_pos = camera.apply(self.pos)
            rect = self.image.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))
            screen.blit(self.image, rect)
            return
        screen.blit(self.image, self.rect)
