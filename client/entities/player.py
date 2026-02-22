import pygame
from client.entities.base_player import BasePlayer
from client.core.settings import TICK_INTERVAL

IN_UP = 1
IN_DOWN = 2
IN_LEFT = 4
IN_RIGHT = 8
IN_FIRE = 32


class Player(BasePlayer):
    def update_from_server(self, server_update: dict):
        new_target = pygame.Vector2(
            server_update.get("x", self.pos.x),
            server_update.get("y", self.pos.y)
        )
        if (new_target - self.pos).length() > 20:
            print("WARNING snap to position:" + str(new_target - self.pos))
            self.pos = new_target.copy()
        self.interpolator.set_target(new_target)

    def __init__(self, player_id, x, y, image_path="client/assets/images/player.png", max_health=100, speed=300):
        super().__init__(player_id, x, y, image_path, max_health)
        self.speed = speed
        self.target_pos = self.pos.copy()
        self.render_pos = self.pos.copy()
        self.pending_inputs = []
        self.last_processed_seq = -1
        self.map_renderer = None

        # Correction accumulée à drainer progressivement dans update()
        self._correction = pygame.Vector2(0, 0)
        print(self._correction)

    @staticmethod
    def read_local_input():
        keys = pygame.key.get_pressed()
        mask = 0
        if keys[pygame.K_z] or keys[pygame.K_UP]:    mask |= IN_UP
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  mask |= IN_DOWN
        if keys[pygame.K_q] or keys[pygame.K_LEFT]:  mask |= IN_LEFT
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: mask |= IN_RIGHT
        if keys[pygame.K_SPACE]:                     mask |= IN_FIRE
        return {"k": mask}

    def apply_input(self, inp):
        """Applique un input sur self.pos"""
        k = inp.get("k", 0)
        vx = vy = 0.0
        if k & IN_UP:    vy -= self.speed
        if k & IN_DOWN:  vy += self.speed
        if k & IN_LEFT:  vx -= self.speed
        if k & IN_RIGHT: vx += self.speed

        if vx != 0 and vy != 0:
            vx *= 0.70710678
            vy *= 0.70710678

        new_x = self.pos.x + vx * TICK_INTERVAL
        new_y = self.pos.y + vy * TICK_INTERVAL

        collision_detected = False
        if self.map_renderer:
            collision_detected = self.map_renderer.check_collision(new_x, new_y, size=32)

        if not collision_detected:
            self.pos.x = max(16, min(new_x, self.map_renderer.map_surface.get_width() - 16))
            self.pos.y = max(16, min(new_y, self.map_renderer.map_surface.get_height() - 16))

        self.rect.center = self.pos

    def _simulate_input_on(self, pos: pygame.Vector2, inp: dict) -> pygame.Vector2:
        """
        Même physique que apply_input mais sur un vecteur externe.
        self.pos n'est JAMAIS touché.
        """
        k = inp.get("k", 0)
        vx = vy = 0.0
        if k & IN_UP:    vy -= self.speed
        if k & IN_DOWN:  vy += self.speed
        if k & IN_LEFT:  vx -= self.speed
        if k & IN_RIGHT: vx += self.speed

        if vx != 0 and vy != 0:
            vx *= 0.70710678
            vy *= 0.70710678

        new_x = pos.x + vx * TICK_INTERVAL
        new_y = pos.y + vy * TICK_INTERVAL

        collision_detected = False
        if self.map_renderer:
            collision_detected = self.map_renderer.check_collision(new_x, new_y, size=32)

        if not collision_detected:
            return pygame.Vector2(
                max(16, min(new_x, self.map_renderer.map_surface.get_width() - 16)),
                max(16, min(new_y, self.map_renderer.map_surface.get_height() - 16))
            )
        return pos.copy()

    def save_input_for_reconciliation(self, inp):
        self.pending_inputs.append({
            "seq": inp.get("seq", 0),
            "k": inp["k"],
        })
        if len(self.pending_inputs) > 120:
            self.pending_inputs = self.pending_inputs[-120:]

    def data_from_the_server(self, server_state):
        """
        Réconciliation sans jamais toucher self.pos ni render_pos.

        On simule dans une variable temporaire ce que le serveur a
        confirmé + les inputs non encorssssse confirmés. On calcule l'écart
        avec la prédiction locale et on accumule la correction dans
        self._correction. update() la drainera progressivement sur
        self.pos sans aucun saut visible.
        """
        server_x   = server_state.get("x", self.pos.x)
        server_y   = server_state.get("y", self.pos.y)
        server_seq = server_state.get("last_input_seq", -1)

        if server_seq <= self.last_processed_seq:
            return
        self.last_processed_seq = server_seq

        self.pending_inputs = [i for i in self.pending_inputs if i["seq"] > server_seq]

        sim = pygame.Vector2(server_x, server_y)
        for inp in self.pending_inputs:
            sim = self._simulate_input_on(sim, inp)

        # Delta entre ce que le serveur dit et ce qu'on a prédit localement
        # Si les simulations sont identiques → correction ≈ (0, 0)
        self._correction += sim - self.pos

    def take_damage(self, damage):
        remaining_health = self.life.lose_health(damage)
        if self.life.is_dead():
            self.on_death()
        return remaining_health

    def heal(self, amount):
        return self.life.heal(amount)

    def on_death(self):
        print(f"Player {self.player_id} is dead at {self.get_position()}")

    def update(self, dt, *args, **kwargs):
        """
        Draine la correction accumulée progressivement sur self.pos.
        Aucun saut : la correction influence les futures simulations
        sans jamais déplacer le joueur instantanément.
        render_pos suit self.pos avec lissage → aucune saccade visuelle.
        """
        CORRECTION_RATE = 20.0
        SMOOTHING_RATE  = 20.0

        # Drainer la correction sur self.pos progressivement
        if self._correction.length_squared() > 0.01:
            step = self._correction * min(1.0, CORRECTION_RATE * dt)
            self.pos      += step
            self._correction -= step

        # render_pos suit self.pos avec lissage
        delta = self.pos - self.render_pos
        self.render_pos += delta * min(1.0, SMOOTHING_RATE * dt)
        self.rect.center = (int(self.render_pos.x), int(self.render_pos.y))

    def draw(self, screen):
        super().draw(screen)
        self._draw_health_bar(screen)
        if self.pending_inputs:
            font = pygame.font.Font(None, 20)
            text = font.render(f"Pending: {len(self.pending_inputs)}", True, (255, 255, 0))
            screen.blit(text, (self.rect.centerx - 30, self.rect.top - 25))

    def _draw_health_bar(self, screen, bar_width=50, bar_height=5):
        if self.life.get_health() < self.life.get_max_health():
            bar_x = self.rect.centerx - bar_width // 2
            bar_y = self.rect.top - 10
            pygame.draw.rect(screen, (255, 0, 0), (bar_x, bar_y, bar_width, bar_height))
            health_width = int(bar_width * (self.life.get_health() / self.life.get_max_health()))
            if health_width > 0:
                pygame.draw.rect(screen, (0, 255, 0), (bar_x, bar_y, health_width, bar_height))