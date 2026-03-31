import pygame
import os
import logging
from client.entities.base_player import BasePlayer
from client.core.settings import TICK_INTERVAL
from client.entities.magical_draw import MagicalDraw
from client.ui.health_bar import PlayerHealthBar

IN_UP = 1
IN_DOWN = 2
IN_LEFT = 4
IN_RIGHT = 8
IN_BOARD = 32
IN_DRAWING = 64


class Player(BasePlayer):
    DAMAGE_SOUND_PATHS = [
        "sounds/damage_recived.flac",
        "sounds/damage_received.flac",
        "client/assets/sounds/damage_recived.flac",
        "client/assets/sounds/damage_received.flac",
        "client/assets/sounds/damage_recived.ogg",
        "client/assets/sounds/damage_received.ogg",
        "client/assets/sounds/damage_recived.wav",
        "client/assets/sounds/damage_received.wav",
    ]

    def update_from_server(self, server_update: dict):
        new_target = pygame.Vector2(
            server_update.get("x", self.pos.x),
            server_update.get("y", self.pos.y)
        )
        if (new_target - self.pos).length() > 20:
            logging.warning(f"Snap to position delta={new_target - self.pos}")
            self.pos = new_target.copy()
        self.interpolator.set_target(new_target)

    def __init__(self, player_id, x, y, image_path="client/assets/images/full_mage.png", max_health=100, speed=300,
                 magical_draw=None):
        super().__init__(player_id, x, y, image_path, max_health)
        self.mask = 0
        self.speed = speed
        self.target_pos = self.pos.copy()
        self.render_pos = self.pos.copy()
        self.pending_inputs = []
        self.last_processed_seq = -1
        self.map_renderer = None

        self.magical_draw: MagicalDraw = magical_draw

        self._correction = pygame.Vector2(0, 0)
        self.health_bar_ui = PlayerHealthBar()
        self._damage_sound = self._load_damage_sound()
        self._last_damage_sound_ms = -100000


    def read_local_input(self):
        keys = pygame.key.get_pressed()
        mask = 0
        if keys[pygame.K_z] or keys[pygame.K_UP]:    mask |= IN_UP
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  mask |= IN_DOWN
        if keys[pygame.K_q] or keys[pygame.K_LEFT]:  mask |= IN_LEFT
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: mask |= IN_RIGHT
        if pygame.mouse.get_pressed()[2]:            mask |= IN_BOARD
        if pygame.mouse.get_pressed()[0]:            mask |= IN_DRAWING
        self.mask = mask
        return {"k": mask}

    def apply_input(self, inp):
        """Applique un input sur self.pos"""
        vy, vx = self.compute_velocity(inp)
        if vx != 0.0 or vy != 0.0:
            self.facing = pygame.Vector2(vx, vy).normalize()
        self.update_direction_from_velocity(vx)

        new_x = self.pos.x + vx * TICK_INTERVAL
        new_y = self.pos.y + vy * TICK_INTERVAL

        collision_detected = False
        if self.map_renderer:
            collision_detected = self.map_renderer.check_collision(new_x, new_y, size=32)

        if not collision_detected:
            self.pos.x = max(16, min(new_x, self.map_renderer.map_surface.get_width() - 16))
            self.pos.y = max(16, min(new_y, self.map_renderer.map_surface.get_height() - 16))

        self.rect.center = self.pos


    def compute_velocity(self, inp) -> tuple:
        """Calcul pur des composantes de vitesse pour l'input donné."""
        k = inp.get("k", 0)
        vx = vy = 0.0
        if k & IN_UP:    vy -= self.speed
        if k & IN_DOWN:  vy += self.speed
        if k & IN_LEFT:  vx -= self.speed
        if k & IN_RIGHT: vx += self.speed

        if vx != 0 and vy != 0:
            vx *= 0.70710678
            vy *= 0.70710678
        return vy, vx

    def _simulate_input_on(self, pos: pygame.Vector2, inp: dict) -> pygame.Vector2:
        """
        Même physique que apply_input mais sur un vecteur externe.
        self.pos n'est JAMAIS touché.
        """
        vy, vx = self.compute_velocity(inp)
        # Simulation reste pure : on ne change pas la direction ici.
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
        previous_health = self.life.life_current
        server_health = server_state.get("health", previous_health)
        if server_health < previous_health:
            self._play_damage_received_sound()
        self.life.life_current = server_health
        server_alive = server_state.get("alive", self.alive)
        if self.alive and not server_alive:
            self.on_death()
        self.alive = server_alive

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

    def on_death(self):
        super().on_death()
        logging.info(f"Player {self.player_id} is dead at {self.get_position()}")

    def _load_damage_sound(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception:
            return None

        for path in self.DAMAGE_SOUND_PATHS:
            if not os.path.exists(path):
                continue
            try:
                return pygame.mixer.Sound(path)
            except Exception:
                continue
        return None

    def _play_damage_received_sound(self):
        if not self._damage_sound:
            return
        now_ms = pygame.time.get_ticks()
        if now_ms - self._last_damage_sound_ms < 120:
            return
        self._last_damage_sound_ms = now_ms
        try:
            self._damage_sound.play()
        except Exception:
            pass

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

    def draw(self, screen, camera=None):
        if self.direction > -1:
            image = self.image_right
            self.previous_image = image
        elif self.direction < 1:
            image = self.image_left
            self.previous_image = image
        else:
            image = self.previous_image

        self.current_image = image
        screen_pos, rect = self.draw_sprite(screen, camera, pos=self.render_pos, image=image)
        if camera and self.pending_inputs:
            font = pygame.font.Font(None, 20)
            text = font.render(f"Pending: {len(self.pending_inputs)}", True, (255, 255, 0))
            screen.blit(text, (screen_pos.x - 30, screen_pos.y - rect.height // 2 - 25))
        self.health_bar_ui.draw(
            screen,
            self.life.get_health(),
            self.life.get_max_health()
        )
