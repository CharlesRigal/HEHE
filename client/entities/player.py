import pygame

from client.entities.entity import Life
from client.core.settings import WIDTH, HEIGHT

# Constantes d'input
IN_UP = 1
IN_DOWN = 2
IN_LEFT = 4
IN_RIGHT = 8
IN_FIRE = 32


class Player:
    def __init__(self, image_path, pos, max_health=100, speed=200):
        self.image = pygame.image.load(image_path).convert_alpha()
        self.pos = self.image.get_rect(center=pos)
        self.speed = speed
        self.life = Life(max_health)

        # Cache pour éviter de recalculer les limites
        self._screen_bounds = pygame.Rect(0, 0, WIDTH, HEIGHT)

    @staticmethod
    def read_local_input():
        """Lit les inputs locaux du clavier"""
        keys = pygame.key.get_pressed()
        # mx, my = pygame.mouse.get_pos() # TODO pour l'ajout de la souris
        # mb = pygame.mouse.get_pressed(3)

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
        """Applique les inputs de mouvement au joueur"""
        k = inp.get("k", 0)
        vx = vy = 0.0

        # Calcul de la vélocité basée sur les inputs
        if k & IN_UP:
            vy -= self.speed
        if k & IN_DOWN:
            vy += self.speed
        if k & IN_LEFT:
            vx -= self.speed
        if k & IN_RIGHT:
            vx += self.speed

        # Normalisation diagonale (mouvement à vitesse constante)
        if vx != 0 and vy != 0:
            diagonal_factor = 0.7071067811865476  # 1/sqrt(2)
            vx *= diagonal_factor
            vy *= diagonal_factor

        # Application du mouvement
        new_x = self.pos.x + vx * dt
        new_y = self.pos.y + vy * dt

        # Contraintes des limites d'écran
        self.pos.x = max(0, min(new_x, WIDTH - self.pos.width))
        self.pos.y = max(0, min(new_y, HEIGHT - self.pos.height))

    def take_damage(self, damage):
        """Le joueur subit des dégâts"""
        remaining_health = self.life.lose_health(damage)
        if self.life.is_dead():
            self.on_death()
        return remaining_health

    def heal(self, amount):
        """Soigne le joueur"""
        return self.life.heal(amount)

    def on_death(self):
        """Appelé quand le joueur meurt"""
        print(f"Player is dead! Final position: {self.get_position()}")
        # Ici on peut ajouter des effets de mort, respawn, etc.

    def get_position(self) -> tuple:
        """Retourne la position du centre du joueur"""
        return self.pos.centerx, self.pos.centery

    def get_rect(self) -> pygame.Rect:
        """Retourne le rectangle de collision"""
        return self.pos

    def is_alive(self) -> bool:
        """Vérifie si le joueur est vivant"""
        return not self.life.is_dead()

    def get_health_percentage(self) -> float:
        """Retourne le pourcentage de vie restant"""
        return self.life.get_health() / self.life.get_max_health()

    def update(self, dt):
        """Mise à jour du joueur (pour animations futures, etc.)"""
        # Ici on peut ajouter des animations, des effets, etc.
        pass

    def draw(self, screen):
        """Dessine le joueur à l'écran"""
        if self.is_alive():
            screen.blit(self.image, self.pos)

            # Optionnel : dessiner la barre de vie
            self._draw_health_bar(screen)

    def _draw_health_bar(self, screen, bar_width=50, bar_height=5):
        """Dessine une barre de vie au-dessus du joueur"""
        if self.life.get_health() < self.life.get_max_health():
            # Position de la barre
            bar_x = self.pos.centerx - bar_width // 2
            bar_y = self.pos.top - 10

            # Fond rouge
            pygame.draw.rect(screen, (255, 0, 0),
                             (bar_x, bar_y, bar_width, bar_height))

            # Barre verte (vie restante)
            health_width = int(bar_width * self.get_health_percentage())
            if health_width > 0:
                pygame.draw.rect(screen, (0, 255, 0),
                                 (bar_x, bar_y, health_width, bar_height))

    def __repr__(self):
        return f"Player(pos={self.get_position()}, health={self.life.get_health()}/{self.life.get_max_health()})"