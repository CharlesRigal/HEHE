import pygame
from client.entities.base_player import BasePlayer
from client.core.settings import WIDTH, HEIGHT

# Constantes d’input
IN_UP = 1
IN_DOWN = 2
IN_LEFT = 4
IN_RIGHT = 8
IN_FIRE = 32


class Player(BasePlayer):
    def __init__(self, player_id, x, y, image_path="client/assets/images/player.png", max_health=100, speed=200):
        super().__init__(player_id, x, y, image_path, max_health)
        self.speed = speed

        # Cache pour limites d’écran
        self._screen_bounds = pygame.Rect(0, 0, WIDTH, HEIGHT)

    @staticmethod
    def read_local_input():
        """Lit les inputs clavier"""
        keys = pygame.key.get_pressed()
        mask = 0
        if keys[pygame.K_z] or keys[pygame.K_UP]:
            mask |= IN_UP
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            mask |= IN_DOWN
        if keys[pygame.K_q] or keys[pygame.K_LEFT]:
            mask |= IN_LEFT
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            mask |= IN_RIGHT
        if keys[pygame.K_SPACE]:
            mask |= IN_FIRE
        return {"k": mask}

    def apply_input(self, inp, dt):
        """Déplacement local en fonction des inputs"""
        k = inp.get("k", 0)
        vx = vy = 0.0

        if k & IN_UP: vy -= self.speed
        if k & IN_DOWN: vy += self.speed
        if k & IN_LEFT: vx -= self.speed
        if k & IN_RIGHT: vx += self.speed

        # Normalisation diagonale
        if vx != 0 and vy != 0:
            factor = 0.70710678
            vx *= factor
            vy *= factor

        # Mise à jour de la position
        self.pos.x = max(0, min(self.pos.x + vx * dt, WIDTH - self.rect.width))
        self.pos.y = max(0, min(self.pos.y + vy * dt, HEIGHT - self.rect.height))

        # Sync rect
        self.rect.center = self.pos

    def take_damage(self, damage):
        remaining_health = self.life.lose_health(damage)
        if self.life.is_dead():
            self.on_death()
        return remaining_health

    def heal(self, amount):
        return self.life.heal(amount)

    def on_death(self):
        print(f"Player {self.player_id} is dead at {self.get_position()}")

    def update(self, dt):
        """Peut gérer animations futures"""
        super().update(dt)  # garde rect en phase

    def draw(self, screen):
        super().draw(screen)  # sprite
        self._draw_health_bar(screen)

    def _draw_health_bar(self, screen, bar_width=50, bar_height=5):
        """Barre de vie au-dessus du joueur"""
        if self.life.get_health() < self.life.get_max_health():
            bar_x = self.rect.centerx - bar_width // 2
            bar_y = self.rect.top - 10

            # fond rouge
            pygame.draw.rect(screen, (255, 0, 0), (bar_x, bar_y, bar_width, bar_height))
            # barre verte
            health_width = int(bar_width * (self.life.get_health() / self.life.get_max_health()))
            if health_width > 0:
                pygame.draw.rect(screen, (0, 255, 0), (bar_x, bar_y, health_width, bar_height))
