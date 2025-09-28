from abc import ABC

import pygame
import math

from entity import Life
from client.core.game_object import GameObject
from settings import WIDTH, HEIGHT


class Enemy(GameObject, ABC):
    def __init__(self, image_path, pos, max_health=50):
        self.life = Life(max_health)
        self.image = pygame.image.load(image_path).convert_alpha()
        self.rect = self.image.get_rect(center=pos)
        self.speed = 100
        super().__init__()

    def take_damage(self, damage):
        remaining_health = self.life.lose_health(damage)
        if self.life.is_dead():
            print("Enemy defeated!")
        return remaining_health

    def travel_to_player(self, player_entity, dt):
        """Version précise : mouvement vectoriel lisse"""
        player_pos = player_entity.get_position()

        # Calculer le vecteur direction
        dx = player_pos[0] - self.rect.centerx
        dy = player_pos[1] - self.rect.centery

        # Calculer la distance
        distance = math.sqrt(dx * dx + dy * dy)

        # Éviter la division par zéro et l'oscillation
        if distance > 2:  # Seuil minimal pour éviter l'oscillation
            # Normaliser le vecteur direction
            dx_normalized = dx / distance
            dy_normalized = dy / distance

            # Appliquer le mouvement
            self.rect.centerx += dx_normalized * self.speed * dt
            self.rect.centery += dy_normalized * self.speed * dt


class EnemyEye(Enemy):
    def __init__(self, image_path="client/assets/images/enemy.png", pos=(WIDTH / 2, HEIGHT / 2), targeted_player=None):
        self.life = Life(life_max=100)
        self.targeted_player = targeted_player
        super().__init__(image_path=image_path, pos=pos)

    def set_targeted_player(self, player):
        self.targeted_player = player

    def update(self, dt, *args, **kwargs):
        if self.targeted_player is not None:
            self.travel_to_player(self.targeted_player, dt)

    def draw(self, screen):
        screen.blit(self.image, self.rect)