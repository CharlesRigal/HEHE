# remote_player.py
import pygame
from client.entities.base_player import BasePlayer


class RemotePlayer(BasePlayer):
    def __init__(self, player_id, x, y, image_path="client/assets/images/remote_player.png"):
        super().__init__(player_id, x, y, image_path)

        # Vitesse d'interpolation augmentée pour suivre les joueurs à 200px/s
        # On met 400px/s pour être sûr de rattraper rapidement
        self.interpolator.speed = 700.0

    def update_from_server(self, server_update: dict):
        """Mise à jour depuis serveur (snapshots espacés)"""
        new_target = pygame.Vector2(
            server_update.get("x", self.pos.x),
            server_update.get("y", self.pos.y)
        )

        # Calculer la distance
        distance = (new_target - self.pos).length()

        # Si trop loin (téléportation, spawn, etc.), snap instantané
        SNAP_THRESHOLD = 100  # pixels
        if distance > SNAP_THRESHOLD:
            self.pos = new_target.copy()
            self.interpolator.current = new_target.copy()
            self.interpolator.target = new_target.copy()
        else:
            # Sinon, interpolation douce
            self.interpolator.set_target(new_target)

        # Mettre à jour les autres propriétés (autoritaires depuis le serveur)
        self.life.life_current = server_update.get("health", self.life.life_current)
        self.alive = server_update.get("alive", self.alive)

    def update(self, dt: float, *args, **kwargs):
        """Update avec interpolation pour les joueurs distants"""
        self.pos = self.interpolator.update(dt)
        self.rect.center = (int(self.pos.x), int(self.pos.y))