import pygame
from client.entities.base_player import BasePlayer


class RemotePlayer(BasePlayer):
    def __init__(self, player_id, x, y, image_path="client/assets/images/remote_player.png"):
        super().__init__(player_id, x, y, image_path)

        # Interpolation
        self.prev = pygame.Vector2(x, y)
        self.target = pygame.Vector2(x, y)
        self.interpolation_time = 0.0
        self.interpolation_duration = 0.1

    def set_target_position(self, new_x: float, new_y: float):
        """Fixe une nouvelle position cible envoyée par le serveur"""
        self.prev.update(self.pos)   # garde la position actuelle comme "départ"
        self.target.update(new_x, new_y)
        self.interpolation_time = 0.0

    def update(self, dt: float, *args, **kwargs):
        """Interpolation fluide entre pos actuelle et target"""
        if self.interpolation_time < self.interpolation_duration:
            self.interpolation_time += dt
            t = min(1.0, self.interpolation_time / self.interpolation_duration)
            self.pos = self.prev.lerp(self.target, t)
        else:
            self.pos.update(self.target)

        # Met à jour le rect
        self.rect.center = self.pos

    def draw(self, screen: pygame.Surface):
        """Affiche le joueur si vivant"""
        if self.is_alive():
            screen.blit(self.image, self.rect)

    def update_from_server(self, server_update: dict):
        """Applique les updates envoyées par le serveur"""
        super().update_from_server(server_update)
        self.set_target_position(server_update["x"], server_update["y"])
