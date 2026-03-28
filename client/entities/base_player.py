from abc import abstractmethod, ABC

import pygame

from client.core.game_object import GameObject
from client.core.interpolator import Interpolator
from client.entities.entity import Life
from client.network.server_updatable import ServerUpdatable


class BasePlayer(ServerUpdatable, GameObject, ABC):
    def __init__(self, player_id: str, x: float, y: float, image_path: str, max_health=100):
        super().__init__()
        self.player_id = player_id

        self.pos = pygame.Vector2(x, y)
        self.direction = 0


        self.image_right = pygame.image.load(image_path).convert_alpha()
        self.image_left = pygame.transform.flip(self.image_right, True, False)
        self.previous_image = self.image_right # for the player direction and initialized to right
        self.rect = self.image_right.get_rect(center=(x, y))

        self.life = Life(max_health)

        self.alive = True

        self.interpolator = Interpolator(self.pos)

    def is_alive(self) -> bool:
        return not self.life.is_dead()

    def get_position(self) -> tuple:
        return self.pos.x, self.pos.y

    @abstractmethod
    def update_from_server(self, server_update: dict):
        """Mise à jour générique depuis le serveur"""
        pass

    @abstractmethod
    def update(self,dt, *args, **kwargs):
        pass

    def update_direction_from_velocity(self, vx: float):
        if vx < 0:
            self.direction = -1
        elif vx > 0:
            self.direction = 1

    def draw(self, screen: pygame.Surface, camera=None):
        if camera:
            screen_pos = camera.apply(self.pos)
            rect = self.image.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))
            screen.blit(self.image, rect)
        else:
            screen.blit(self.image, self.rect)
