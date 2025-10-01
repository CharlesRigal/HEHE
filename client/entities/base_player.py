import pygame

from client.core.game_object import GameObject
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

    def is_alive(self) -> bool:
        return not self.life.is_dead()

    def get_position(self) -> tuple:
        return self.pos.x, self.pos.y

    def update_from_server(self, server_update: dict):
        """Mise à jour générique depuis le serveur"""
        self.pos.update(server_update.get("x", self.pos.x),
                        server_update.get("y", self.pos.y))
        self.life.life_current = server_update.get("health", self.life.life_current)
        self.alive = server_update.get("alive", self.alive)

        # Sync rect avec pos
        self.rect.center = (int(self.pos.y), int(self.pos.x))

    def update(self, dt: float, *args, **kwargs):
        """Par défaut, juste maintenir rect en phase avec pos"""
        self.rect.center = (int(self.pos.y), int(self.pos.x))

    def draw(self, screen: pygame.Surface):
        if self.is_alive():
            screen.blit(self.image, self.rect)
