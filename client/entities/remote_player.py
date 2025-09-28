# remote_player.py
import pygame

from client.game_object import GameObject


class RemotePlayer(GameObject):
    """Représente un joueur distant (contrôlé par un autre client)"""

    def __init__(self, player_id, x=100, y=100, health=100):
        super().__init__()
        self.player_id = player_id
        self.x = x
        self.y = y
        self.health = health
        self.max_health = 100
        self.alive = True
        self.active = True

        # Position précédente pour l'interpolation
        self.prev_x = x
        self.prev_y = y
        self.target_x = x
        self.target_y = y

        self.interpolation_time = 0.0
        self.interpolation_duration = 0.1

        # Graphismes
        self.load_sprite()
        self.rect = pygame.Rect(x - 16, y - 16, 32, 32)  # Taille du joueur

    def load_sprite(self):
        """Charge le sprite du joueur distant"""
        self.image = pygame.image.load("client/assets/images/remote_player.png").convert_alpha()


    def set_target_position(self, new_x, new_y):
        """Définit une nouvelle position cible pour l'interpolation"""
        self.prev_x = self.x
        self.prev_y = self.y
        self.target_x = new_x
        self.target_y = new_y
        self.interpolation_time = 0.0

    def update(self, dt, *args, **kwargs):
        """Met à jour le joueur distant (principalement l'interpolation)"""
        if not self.alive:
            return

        # Interpolation de position pour des mouvements fluides
        if self.interpolation_time < self.interpolation_duration:
            self.interpolation_time += dt
            t = min(1.0, self.interpolation_time / self.interpolation_duration)

            # Interpolation linéaire simple
            self.x = self.prev_x + (self.target_x - self.prev_x) * t
            self.y = self.prev_y + (self.target_y - self.prev_y) * t

        else:
            # Interpolation terminée, utiliser la position cible
            self.x = self.target_x
            self.y = self.target_y

        # Mettre à jour le rectangle de collision
        self.rect.center = (self.x, self.y)

    def draw(self, screen):
        """Dessine le joueur distant"""
        if not self.alive:
            return

        # Dessiner le sprite
        sprite_rect = self.image.get_rect(center=(self.x, self.y))
        screen.blit(self.image, sprite_rect)

    def update_from_server(self, player_remote_new_status:dict):
        self.alive = player_remote_new_status['alive']
        self.health = player_remote_new_status['health']
        self.set_target_position(player_remote_new_status['x'], player_remote_new_status['y'])
