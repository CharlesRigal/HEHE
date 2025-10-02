import pygame

from client.core.game_object import GameObject
from client.core.interpolator import Interpolator
from client.entities.entity import Life
from client.network.server_updatable import ServerUpdatable


class BasePlayer(ServerUpdatable, GameObject):
    def __init__(self, player_id: str, x: float, y: float, image_path: str, max_health=100):
        super().__init__()
        self.player_id = player_id

        # Position logique
        self.pos = pygame.Vector2(x, y)

        # Sprite + rect
        self.image = pygame.image.load(image_path).convert_alpha()
        self.rect = self.image.get_rect(center=(x, y))

        # Vie
        self.life = Life(max_health)

        # Flags état
        self.alive = True

        self.interpolator = Interpolator(self.pos)

    def is_alive(self) -> bool:
        return not self.life.is_dead()

    def get_position(self) -> tuple:
        return self.pos.x, self.pos.y

    def update_from_server(self, server_update: dict):
        """Mise à jour générique depuis le serveur"""
        new_target = pygame.Vector2(
            server_update.get("x", self.pos.x),
            server_update.get("y", self.pos.y)
        )

        # snap si trop loin
        if (new_target - self.pos).length() > 20:
            self.pos = new_target.copy()
            self.interpolator.set_target(new_target)
        else:
            self.interpolator.set_target(new_target)

    def update(self, dt: float, *args, **kwargs):
        """Par défaut, juste maintenir rect en phase avec pos"""
        self.pos = self.interpolator.update(dt)
        self.rect.center = (int(self.pos.x), int(self.pos.y))


    def draw(self, screen: pygame.Surface):
        if self.is_alive():
            screen.blit(self.image, self.rect)
