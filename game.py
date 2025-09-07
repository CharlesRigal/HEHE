import pygame

from enemy import EnemyEye
from settings import WIDTH, HEIGHT, FPS, BLACK
from player import Player
from utils import get_random_location_away_from_screen_circle


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Fala world")
        self.clock = pygame.time.Clock()
        self.running = True
        self.start_time = None

        # états du jeu
        self.state = "menu"  # menu, playing, game_over

        # Chargement du background
        self.load_background()

        # entités
        self.player = Player("assets/images/player.png", (WIDTH / 2, HEIGHT / 2))
        self.enemies = []

    def load_background(self):
        """Charge et prépare l'image de background"""
        try:
            # Essayer de charger l'image de background
            self.background = pygame.image.load("assets/images/dirt_and_grass.png").convert()
            self.has_background = True
        except pygame.error:
            # Si l'image n'existe pas, utiliser une couleur de fond
            print("Background image not found, using solid color")
            self.background = pygame.Surface((WIDTH, HEIGHT))
            self.background.fill(BLACK)  # ou une autre couleur comme (50, 50, 80)
            self.has_background = False

    def draw_background(self):
        """Dessine le background"""
        self.screen.blit(self.background, (0, 0))

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
                self.enemies.append(EnemyEye(pos=(get_random_location_away_from_screen_circle(min_radius=100))))

            self.player.update(dt)
            for enemie in self.enemies:
                enemie.update(self.player, dt)
        elif self.state == "game_over":
            pass

    def draw(self):
        """Rendu graphique"""
        # Dessiner le background en premier
        self.draw_background()

        if self.state == "menu":
            self.draw_text("Appuie sur une touche pour jouer", 40, (255, 255, 255), WIDTH / 2, HEIGHT / 2)
        elif self.state == "playing":
            self.player.draw(self.screen)
            for enemie in self.enemies:
                enemie.draw(self.screen)
        elif self.state == "game_over":
            self.draw_text("Game Over - Appuie sur R pour recommencer", 40, (255, 0, 0), WIDTH / 2, HEIGHT / 2)
        pygame.display.flip()

    def draw_text(self, text, size, color, x, y):
        """Utilitaire pour dessiner du texte centré"""
        font = pygame.font.Font(None, size)
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(x, y))
        self.screen.blit(surf, rect)