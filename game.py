import pygame

from enemy import EnemyEye
from settings import WIDTH, HEIGHT, FPS, BLACK
from player import Player
from utils import get_random_location_away_from_screen_circle


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Mon Jeu 2D")
        self.clock = pygame.time.Clock()
        self.running = True
        self.start_time = None

        # états du jeu
        self.state = "menu"  # menu, playing, game_over

        # entités
        self.player = Player("assets/images/player.png", (WIDTH/2, HEIGHT/2))
        self.enemies = []

    def run(self):
        """Boucle principale"""
        while self.running:
            dt = self.clock.tick(FPS) / 1000
            self.handle_events()
            self.update(dt)
            self.draw()
        pygame.quit()

    def handle_events(self):
        """Gestion des entrées"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            if self.state == "menu":
                if event.type == pygame.KEYDOWN:
                    self.state = "playing"

            elif self.state == "game_over":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    self.state = "menu"


    def update(self, dt):
        """Logique du jeu selon l'état"""
        if self.state == "menu":

            # futur menu
            pass
        elif self.state == "playing":
            if self.start_time is None:
                self.start_time = pygame.time.get_ticks()

            elapsed = (pygame.time.get_ticks() - self.start_time) / 1000

            if elapsed > 2.5 and len(self.enemies) == 0:
                self.enemies.append(EnemyEye(location=(get_random_location_away_from_screen_circle())))

            self.player.update(dt)
        elif self.state == "game_over":
            pass

    def draw(self):
        """Rendu graphique"""
        self.screen.fill(BLACK)
        if self.state == "menu":
            self.draw_text("Appuie sur une touche pour jouer", 40, (255,255,255), WIDTH/2, HEIGHT/2)
        elif self.state == "playing":
            self.player.draw(self.screen)
            for enemie in self.enemies:
                enemie.draw(self.screen)
        elif self.state == "game_over":
            self.draw_text("Game Over - Appuie sur R pour recommencer", 40, (255,0,0), WIDTH/2, HEIGHT/2)
        pygame.display.flip()

    def draw_text(self, text, size, color, x, y):
        """Utilitaire pour dessiner du texte centré"""
        font = pygame.font.Font(None, size)
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(x, y))
        self.screen.blit(surf, rect)
