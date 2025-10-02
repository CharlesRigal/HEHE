# remote_player.py
import pygame
from client.entities.base_player import BasePlayer
from client.core.interpolator import Interpolator


class RemotePlayer(BasePlayer):
    def __init__(self, player_id, x, y, image_path="client/assets/images/remote_player.png"):
        super().__init__(player_id, x, y, image_path)
        self.interpolator = Interpolator(self.pos)

    def update_from_server(self, server_update: dict):
        """Mise à jour depuis serveur (snapshots espacés)"""
        new_target = pygame.Vector2(
            server_update.get("x", self.pos.x),
            server_update.get("y", self.pos.y)
        )
        self.interpolator.set_target(new_target)
        self.life.life_current = server_update.get("health", self.life.life_current)
        self.alive = server_update.get("alive", self.alive)

    def update(self, dt: float, *args, **kwargs):
        self.pos = self.interpolator.update(dt)
        super().update(dt, *args, **kwargs)
