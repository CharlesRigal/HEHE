import array
import math
import os

import pygame

from client.core.game_object import GameObject


class RemoteEnemy(GameObject):
    ATTACK_EFFECT_DURATION = 0.28
    ATTACK_SOUND_PATHS = [
        "sound/attack_sound.flac",
        "client/assets/sounds/attack_sound.flac",
        "client/assets/sounds/enemy_attack.wav",
        "client/assets/sounds/enemy_attack.ogg",
    ]

    def __init__(self, enemy_id, x, y, image_path="client/assets/images/enemy.png"):
        super().__init__()
        self.enemy_id = enemy_id
        self.pos = pygame.Vector2(x, y)
        self.target_pos = self.pos.copy()
        self.render_pos = self.pos.copy()
        self.direction = 1
        self.alive = True

        self.image_right = pygame.image.load(image_path).convert_alpha()
        self.image_left = pygame.transform.flip(self.image_right, True, False)
        self.inverted_right = self._build_inverted_image(self.image_right)
        self.inverted_left = self._build_inverted_image(self.image_left)
        self.current_image = self.image_right
        self.current_inverted_image = self.inverted_right
        self.rect = self.current_image.get_rect(center=(int(self.render_pos.x), int(self.render_pos.y)))

        self.attack_effect_timer = 0.0
        self.last_attack_seq = 0
        self.has_received_server_state = False
        self.attack_sound = self._load_attack_sound()

    def _build_inverted_image(self, source: pygame.Surface) -> pygame.Surface:
        try:
            inverted = source.copy()
            rgb = pygame.surfarray.pixels3d(inverted)
            rgb[:] = 255 - rgb
            del rgb
            alpha_src = pygame.surfarray.pixels_alpha(source)
            alpha_dst = pygame.surfarray.pixels_alpha(inverted)
            alpha_dst[:] = alpha_src[:]
            del alpha_src
            del alpha_dst
            return inverted
        except Exception:
            return source.copy()

    def _load_attack_sound(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception:
            return None

        for sound_path in self.ATTACK_SOUND_PATHS:
            if not os.path.exists(sound_path):
                continue
            try:
                return pygame.mixer.Sound(sound_path)
            except Exception:
                continue

        return self._build_fallback_tone()

    def _build_fallback_tone(self):
        try:
            mixer_init = pygame.mixer.get_init()
            if not mixer_init:
                return None
            sample_rate, _, channels = mixer_init
            duration = 0.14
            sample_count = max(1, int(sample_rate * duration))
            samples = array.array("h")
            for index in range(sample_count):
                t = index / sample_rate
                envelope = 1.0 - (index / sample_count)
                value = (
                    math.sin(2.0 * math.pi * 280.0 * t) * 0.55
                    + math.sin(2.0 * math.pi * 420.0 * t) * 0.35
                )
                sample = int(max(-1.0, min(1.0, value * envelope)) * 32767)
                if channels == 1:
                    samples.append(sample)
                else:
                    samples.append(sample)
                    samples.append(sample)
            return pygame.mixer.Sound(buffer=samples.tobytes())
        except Exception:
            return None

    def _set_direction(self, direction: int):
        if direction < 0:
            self.direction = -1
            self.current_image = self.image_left
            self.current_inverted_image = self.inverted_left
        elif direction > 0:
            self.direction = 1
            self.current_image = self.image_right
            self.current_inverted_image = self.inverted_right

    def _trigger_attack_feedback(self):
        self.attack_effect_timer = self.ATTACK_EFFECT_DURATION
        if self.attack_sound:
            try:
                self.attack_sound.play()
            except Exception:
                pass

    def _attack_scale_factor(self):
        if self.attack_effect_timer <= 0.0:
            return 1.0

        progress = 1.0 - (self.attack_effect_timer / self.ATTACK_EFFECT_DURATION)
        if progress < 0.4:
            return 1.0 - 0.12 * (progress / 0.4)
        if progress < 0.8:
            return 0.88 + 0.18 * ((progress - 0.4) / 0.4)
        return 1.06 - 0.06 * ((progress - 0.8) / 0.2)

    def update_from_server(self, enemy_update: dict):
        self.target_pos = pygame.Vector2(
            enemy_update.get("x", self.target_pos.x),
            enemy_update.get("y", self.target_pos.y),
        )
        self.alive = enemy_update.get("alive", self.alive)
        self._set_direction(enemy_update.get("direction", self.direction))

        attack_seq = enemy_update.get("attack_seq", self.last_attack_seq)
        if self.has_received_server_state:
            if attack_seq > self.last_attack_seq:
                self._trigger_attack_feedback()
        else:
            self.has_received_server_state = True
        self.last_attack_seq = attack_seq

        if not self.alive:
            self.mark_for_removal()

    def update(self, dt, *args, **kwargs):
        if not self.active:
            return
        self.pos = self.target_pos.copy()
        smoothing_rate = 18.0
        delta = self.target_pos - self.render_pos
        self.render_pos += delta * min(1.0, smoothing_rate * dt)
        self.attack_effect_timer = max(0.0, self.attack_effect_timer - dt)
        self.rect.center = (int(self.render_pos.x), int(self.render_pos.y))

    def draw(self, screen, camera=None):
        if not self.active:
            return

        source_image = self.current_image
        if self.attack_effect_timer > 0.0:
            source_image = self.current_inverted_image

        scale = self._attack_scale_factor()
        if abs(scale - 1.0) > 0.001:
            width = max(1, int(source_image.get_width() * scale))
            height = max(1, int(source_image.get_height() * scale))
            draw_image = pygame.transform.smoothscale(source_image, (width, height))
        else:
            draw_image = source_image

        screen_pos = camera.apply(self.render_pos) if camera else self.render_pos
        rect = draw_image.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))
        screen.blit(draw_image, rect)
