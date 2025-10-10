import pygame
from client.entities.base_player import BasePlayer
from client.core.settings import WIDTH, HEIGHT

# Constantes d'input
IN_UP = 1
IN_DOWN = 2
IN_LEFT = 4
IN_RIGHT = 8
IN_FIRE = 32


class Player(BasePlayer):
    def __init__(self, player_id, x, y, image_path="client/assets/images/player.png", max_health=100, speed=200):
        super().__init__(player_id, x, y, image_path, max_health)
        self.speed = speed

        # Cache pour limites d'écran
        self._screen_bounds = pygame.Rect(0, 0, WIDTH, HEIGHT)

        # ===== CLIENT-SIDE PREDICTION =====
        # Historique des inputs envoyés mais pas encore confirmés par le serveur
        self.pending_inputs = []

        # Référence au MapRenderer pour les collisions (à setter depuis Game)
        self.map_renderer = None

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
        """Déplacement local en fonction des inputs avec vérification de collision"""
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

        # Calculer la nouvelle position
        new_x = self.pos.x + vx * dt
        new_y = self.pos.y + vy * dt

        # Vérifier les collisions si map_renderer est disponible
        collision_detected = False
        if self.map_renderer:
            collision_detected = self.map_renderer.check_collision(new_x, new_y, size=32)

        # Appliquer le mouvement seulement si pas de collision
        if not collision_detected:
            # Limites de l'écran
            self.pos.x = max(16, min(new_x, WIDTH - 16))
            self.pos.y = max(16, min(new_y, HEIGHT - 16))

        # Sync rect
        self.rect.center = self.pos

    def save_input_for_reconciliation(self, inp, dt):
        """Sauvegarde un input pour la réconciliation future"""
        self.pending_inputs.append({
            "seq": inp.get("seq", 0),
            "k": inp["k"],
            "dt": dt,
            "timestamp": pygame.time.get_ticks()
        })

        # Limite l'historique à 60 inputs max (1 seconde à 60 FPS)
        if len(self.pending_inputs) > 60:
            self.pending_inputs = self.pending_inputs[-60:]

    def reconcile_with_server(self, server_data):
        """
        Réconciliation avec l'état serveur.
        Compare la position prédite localement avec celle du serveur,
        et rejoue les inputs non confirmés si nécessaire.
        """
        server_pos = pygame.Vector2(server_data.get("x", self.pos.x), server_data.get("y", self.pos.y))
        last_processed_seq = server_data.get("last_input_seq", -1)

        # Supprimer les inputs confirmés par le serveur
        self.pending_inputs = [
            inp for inp in self.pending_inputs
            if inp["seq"] > last_processed_seq
        ]

        # Calculer l'erreur de prédiction
        prediction_error = (server_pos - self.pos).length()

        # Seuil de tolérance pour déclencher une correction
        ERROR_THRESHOLD = 5.0  # pixels

        if prediction_error > ERROR_THRESHOLD:
            print(f"[RECONCILE] Erreur de {prediction_error:.2f}px détectée")
            print(f"  Position serveur: ({server_pos.x:.2f}, {server_pos.y:.2f})")
            print(f"  Position prédite: ({self.pos.x:.2f}, {self.pos.y:.2f})")
            print(f"  Inputs à rejouer: {len(self.pending_inputs)}")

            # Repartir de la position autoritaire du serveur
            self.pos = server_pos.copy()

            # Rejouer tous les inputs non confirmés
            for inp in self.pending_inputs:
                self.apply_input(inp, inp["dt"])

            print(f"  Position après rejeu: ({self.pos.x:.2f}, {self.pos.y:.2f})")

        # Toujours mettre à jour la santé depuis le serveur (autoritaire)
        self.life.life_current = server_data.get("health", self.life.life_current)

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
        """
        Update pour le joueur local.
        NE PAS utiliser l'interpolateur, la position est gérée par apply_input.
        """
        # Juste synchroniser le rect avec la position
        self.rect.center = (int(self.pos.x), int(self.pos.y))

    def draw(self, screen):
        super().draw(screen)  # sprite
        self._draw_health_bar(screen)

        # Debug: afficher le nombre d'inputs en attente
        if self.pending_inputs:
            font = pygame.font.Font(None, 20)
            text = font.render(f"Pending: {len(self.pending_inputs)}", True, (255, 255, 0))
            screen.blit(text, (self.rect.centerx - 30, self.rect.top - 25))

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