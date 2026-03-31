from abc import abstractmethod, ABC

import pygame

from client.core.game_object import GameObject
from client.core.interpolator import Interpolator
from client.entities.damagable import Damagable
from client.entities.entity import Life
from client.network.server_updatable import ServerUpdatable


class BasePlayer(ServerUpdatable, GameObject, Damagable, ABC):
    def __init__(self, player_id: str, x: float, y: float, image_path: str, max_health=100):
        super().__init__()
        self.player_id = player_id

        self.pos = pygame.Vector2(x, y)
        self.direction = 0
        self.facing = pygame.Vector2(1.0, 0.0)


        self.image_right = pygame.image.load(image_path).convert_alpha()
        self.image_left = pygame.transform.flip(self.image_right, True, False)
        self.previous_image = self.image_right  # for the player direction and initialized to right
        self.current_image = self.image_right
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

    def get_draw_position(self):
        return self.pos

    def get_draw_image(self):
        return self.current_image or self.image_right

    def get_facing_vector(self) -> pygame.Vector2:
        if self.facing.length_squared() <= 1e-9:
            return pygame.Vector2(1.0, 0.0)
        return self.facing.normalize()

    def draw_sprite(self, screen: pygame.Surface, camera=None, pos=None, image=None):
        draw_pos = pos if pos is not None else self.get_draw_position()
        sprite = image if image is not None else self.get_draw_image()
        screen_pos = camera.apply(draw_pos) if camera else draw_pos
        rect = sprite.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))
        screen.blit(sprite, rect)
        return screen_pos, rect

    def update_direction_from_velocity(self, vx: float):
        if vx < 0:
            self.direction = -1
            self.current_image = self.image_left
        elif vx > 0:
            self.direction = 1
            self.current_image = self.image_right

    def draw(self, screen: pygame.Surface, camera=None):
        self.draw_sprite(screen, camera)

    def on_death(self):
        self.alive = False
