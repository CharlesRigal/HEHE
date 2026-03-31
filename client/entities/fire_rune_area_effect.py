from __future__ import annotations

import math
import os
import random
from itertools import chain
from typing import Iterator

import pygame

from client.core.game_object import GameObject
from client.entities.base_player import BasePlayer
from client.entities.damagable import Damagable


class FireRuneAreaEffect(GameObject):
    """
    Effet de zone de la rune feu:
    - texture circulaire générée procéduralement (noise type Perlin/value-noise)
    - hitbox légèrement plus petite que la texture
    - applique des dégâts périodiques
    """

    _TEXTURE_CACHE_MAX = 64
    _SEED_VARIANTS = 4
    _PULSE_LEVELS = 5
    _PULSE_MIN_SCALE = 0.90
    _MAX_VISUAL_RADIUS = 96.0
    _RADIUS_QUANTUM = 6
    _SPELL_SOUND_PATHS = (
        "sound/fire_blast.flac",
        "songs/fire_blast.flac",
        "client/assets/sounds/fire_blast.flac",
        "client/assets/sounds/fire_blast.ogg",
        "client/assets/sounds/fire_blast.wav",
    )
    _TEXTURE_CACHE: dict[tuple[int, int], pygame.Surface] = {}
    _PULSE_CACHE: dict[tuple[int, int], tuple[pygame.Surface, ...]] = {}
    _SPELL_SOUND: pygame.mixer.Sound | None = None
    _SPELL_SOUND_LOADED = False

    def __init__(
        self,
        *,
        center: tuple[float, float],
        texture_radius: float,
        hitbox_radius: float | None = None,
        hitbox_radius_x: float | None = None,
        hitbox_radius_y: float | None = None,
        ellipse_angle: float = 0.0,
        velocity: tuple[float, float] = (0.0, 0.0),
        damage_per_tick: float = 12.0,
        tick_interval: float = 0.20,
        duration: float = 2.4,
        owner_player_id: str | None = None,
    ) -> None:
        super().__init__()
        self.center = pygame.Vector2(float(center[0]), float(center[1]))
        self.texture_radius = max(8.0, float(texture_radius))
        self._visual_radius = min(self.texture_radius, self._MAX_VISUAL_RADIUS)
        if hitbox_radius is None:
            hitbox_radius = self.texture_radius - 4.0
        base_hitbox_radius = max(1.0, float(hitbox_radius))
        if hitbox_radius_x is None:
            hitbox_radius_x = base_hitbox_radius
        if hitbox_radius_y is None:
            hitbox_radius_y = base_hitbox_radius
        self.hitbox_radius_x = max(1.0, float(hitbox_radius_x))
        self.hitbox_radius_y = max(1.0, float(hitbox_radius_y))
        self.hitbox_radius = max(self.hitbox_radius_x, self.hitbox_radius_y)
        self.ellipse_angle = float(ellipse_angle)
        self._cos_angle = math.cos(self.ellipse_angle)
        self._sin_angle = math.sin(self.ellipse_angle)
        self.velocity = pygame.Vector2(float(velocity[0]), float(velocity[1]))

        max_hitbox = max(self.hitbox_radius_x, self.hitbox_radius_y, 1.0)
        scale_x = self.hitbox_radius_x / max_hitbox
        scale_y = self.hitbox_radius_y / max_hitbox
        self._visual_radius_x = max(6.0, self._visual_radius * scale_x)
        self._visual_radius_y = max(6.0, self._visual_radius * scale_y)

        self.damage_per_tick = max(0.0, float(damage_per_tick))
        self.tick_interval = max(0.05, float(tick_interval))
        self.remaining_duration = max(0.05, float(duration))
        self._duration_total = self.remaining_duration
        self.owner_player_id = owner_player_id

        self._tick_accumulator = 0.0
        self._seed = int(
            (int(self.center.x * 31.0) ^ int(self.center.y * 17.0) ^ int(self.texture_radius * 13.0))
            & 0x7FFFFFFF
        )
        self._spell_sound_channel = None
        self._sound_phase = (self._seed & 0x7F) * 0.11

        self._texture_key = self._texture_cache_key(self._visual_radius, self._seed)
        self._texture = self._get_cached_texture(self._texture_key, self._seed)
        self._pulse_frames = self._get_cached_pulse_frames(self._texture_key, self._texture)
        self._pulse_phase = (self._seed & 0xFF) * 0.07

        self.rect = pygame.Rect(0, 0, 1, 1)
        self._update_rect_from_hitbox()
        self._start_spell_audio()

    def update(self, dt, *args, **kwargs):
        if not self.active:
            return

        self.remaining_duration -= dt
        if self.remaining_duration <= 0.0:
            self.mark_for_removal()
            return

        if self.velocity.length_squared() > 1e-8:
            self.center += self.velocity * float(dt)

        self._update_spell_audio()

        self._tick_accumulator += dt
        due_ticks = int(self._tick_accumulator / self.tick_interval)
        if due_ticks > 0:
            max_ticks_per_update = 3
            ticks_to_apply = min(due_ticks, max_ticks_per_update)
            self._tick_accumulator -= self.tick_interval * ticks_to_apply
            if due_ticks > max_ticks_per_update:
                # Évite la spirale de rattrapage après un pic de frame.
                self._tick_accumulator = min(self._tick_accumulator, self.tick_interval)
            for _ in range(ticks_to_apply):
                self._apply_damage_tick()

        self._update_rect_from_hitbox()

    def mark_for_removal(self):
        self._stop_spell_audio(clean=True)
        super().mark_for_removal()

    def draw(self, screen, camera=None):
        if not self.active:
            return

        screen_pos = camera.apply(self.center) if camera else self.center

        pulse = 0.94 + 0.06 * math.sin(pygame.time.get_ticks() * 0.006 + self._pulse_phase)
        draw_surface = self._build_draw_surface(pulse)
        rect = draw_surface.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))
        screen.blit(draw_surface, rect)

    def infliger_degats(self, target: Damagable, amount: float | None = None):
        if amount is None:
            amount = self.damage_per_tick
        if amount <= 0.0:
            return None
        return target.take_damage(amount)

    def _apply_damage_tick(self) -> None:
        center_x = float(self.center.x)
        center_y = float(self.center.y)
        hitbox_radius = float(max(self.hitbox_radius_x, self.hitbox_radius_y))

        for target in self._iter_damage_targets():
            target_x, target_y, target_radius = self._target_center_and_radius(target)
            if target_x is None or target_y is None:
                continue

            max_dist = hitbox_radius + target_radius
            dx = target_x - center_x
            if dx > max_dist or dx < -max_dist:
                continue
            dy = target_y - center_y
            if dy > max_dist or dy < -max_dist:
                continue
            if not self._point_in_hitbox(dx=dx, dy=dy, target_radius=target_radius):
                continue

            self.infliger_degats(target)

    def _iter_damage_targets(self) -> Iterator[Damagable]:
        manager = self.game_manager
        if manager is None:
            return

        active_objects = getattr(manager, "game_objects", ())
        pending_objects = getattr(manager, "objects_to_add", ())
        for obj in chain(active_objects, pending_objects):
            if obj is self:
                continue
            if not getattr(obj, "active", False):
                continue
            if not isinstance(obj, Damagable):
                continue
            # Par défaut, cet effet offensif ne touche pas les joueurs.
            if isinstance(obj, BasePlayer):
                continue
            if hasattr(obj, "alive") and not getattr(obj, "alive"):
                continue
            yield obj

    @staticmethod
    def _target_center_and_radius(target: Damagable) -> tuple[float | None, float | None, float]:
        if hasattr(target, "rect") and getattr(target, "rect") is not None:
            rect = getattr(target, "rect")
            radius = max(2.0, min(float(rect.width), float(rect.height)) * 0.45)
            return float(rect.centerx), float(rect.centery), radius
        if hasattr(target, "get_position"):
            try:
                x, y = target.get_position()
                return float(x), float(y), 8.0
            except Exception:
                return None, None, 0.0
        return None, None, 0.0

    def _build_draw_surface(self, pulse: float) -> pygame.Surface:
        base = self._select_pulse_surface(pulse)
        target_width = max(4, int(round(self._visual_radius_x * 2.0)))
        target_height = max(4, int(round(self._visual_radius_y * 2.0)))

        if base.get_width() != target_width or base.get_height() != target_height:
            base = pygame.transform.smoothscale(base, (target_width, target_height))
        if abs(self.ellipse_angle) > 1e-4:
            angle_deg = -math.degrees(self.ellipse_angle)
            base = pygame.transform.rotate(base, angle_deg)
        return base

    def _update_rect_from_hitbox(self) -> None:
        vx = self._visual_radius_x
        vy = self._visual_radius_y
        cos_a = self._cos_angle
        sin_a = self._sin_angle
        extent_x = math.sqrt((vx * cos_a) ** 2 + (vy * sin_a) ** 2)
        extent_y = math.sqrt((vx * sin_a) ** 2 + (vy * cos_a) ** 2)
        width = max(1, int(extent_x * 2.0))
        height = max(1, int(extent_y * 2.0))
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (int(self.center.x), int(self.center.y))

    def _point_in_hitbox(self, *, dx: float, dy: float, target_radius: float) -> bool:
        rx = self.hitbox_radius_x + target_radius
        ry = self.hitbox_radius_y + target_radius
        if rx <= 1e-6 or ry <= 1e-6:
            return False

        if abs(self.hitbox_radius_x - self.hitbox_radius_y) <= 1e-6:
            return dx * dx + dy * dy <= rx * rx

        local_x = dx * self._cos_angle + dy * self._sin_angle
        local_y = -dx * self._sin_angle + dy * self._cos_angle
        nx = local_x / rx
        ny = local_y / ry
        return nx * nx + ny * ny <= 1.0

    def _select_pulse_surface(self, pulse: float) -> pygame.Surface:
        if pulse >= 0.995:
            return self._texture

        frame_count = len(self._pulse_frames)
        if frame_count <= 1:
            return self._texture

        clamped = max(self._PULSE_MIN_SCALE, min(1.0, pulse))
        span = 1.0 - self._PULSE_MIN_SCALE
        if span <= 1e-9:
            return self._texture
        ratio = (clamped - self._PULSE_MIN_SCALE) / span
        index = int(round(ratio * (frame_count - 1)))
        index = max(0, min(frame_count - 1, index))
        return self._pulse_frames[index]

    @classmethod
    def _get_spell_sound(cls) -> pygame.mixer.Sound | None:
        if cls._SPELL_SOUND_LOADED:
            return cls._SPELL_SOUND

        cls._SPELL_SOUND_LOADED = True
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception:
            cls._SPELL_SOUND = None
            return None

        for path in cls._SPELL_SOUND_PATHS:
            if not os.path.exists(path):
                continue
            try:
                cls._SPELL_SOUND = pygame.mixer.Sound(path)
                return cls._SPELL_SOUND
            except Exception:
                continue

        cls._SPELL_SOUND = None
        return None

    def _start_spell_audio(self) -> None:
        sound = self._get_spell_sound()
        if sound is None:
            return
        try:
            self._spell_sound_channel = sound.play(loops=-1, fade_ms=80)
        except Exception:
            self._spell_sound_channel = None
            return
        self._update_spell_audio()

    def _update_spell_audio(self) -> None:
        channel = self._spell_sound_channel
        if channel is None or not channel.get_busy():
            return

        total = max(0.05, float(self._duration_total))
        remaining = max(0.0, float(self.remaining_duration))
        elapsed = total - remaining
        life_ratio = max(0.0, min(1.0, remaining / total))

        attack_time = max(0.08, min(0.35, total * 0.25))
        attack = max(0.0, min(1.0, elapsed / attack_time))
        release_window = max(0.12, min(0.35, total * 0.22))
        release = max(0.0, min(1.0, remaining / release_window))
        duration_factor = max(0.25, min(1.0, total / 3.0))

        lfo_speed = 3.5 + 3.5 / max(0.4, total)
        lfo = 0.82 + 0.18 * math.sin(pygame.time.get_ticks() * 0.001 * lfo_speed + self._sound_phase)
        dynamic = 0.65 + 0.35 * life_ratio
        volume = (0.22 + 0.36 * duration_factor) * attack * release * lfo * dynamic
        channel.set_volume(max(0.0, min(0.85, volume)))

    def _stop_spell_audio(self, *, clean: bool) -> None:
        channel = self._spell_sound_channel
        if channel is None:
            return
        try:
            if clean:
                channel.stop()
            else:
                channel.fadeout(80)
        except Exception:
            pass
        self._spell_sound_channel = None

    @classmethod
    def _texture_cache_key(cls, radius: float, seed: int) -> tuple[int, int]:
        radius_px = max(4, int(round(radius)))
        quantum = max(1, int(cls._RADIUS_QUANTUM))
        radius_px = max(4, int(round(radius_px / float(quantum))) * quantum)
        radius_px = min(radius_px, int(round(cls._MAX_VISUAL_RADIUS)))
        seed_variant = abs(int(seed)) % cls._SEED_VARIANTS
        return (radius_px, seed_variant)

    @classmethod
    def _get_cached_texture(cls, key: tuple[int, int], seed: int) -> pygame.Surface:
        cached = cls._TEXTURE_CACHE.pop(key, None)
        if cached is not None:
            cls._TEXTURE_CACHE[key] = cached
            return cached

        radius_px, seed_variant = key
        build_seed = (seed_variant + 1) * 193 + (seed % 97)
        texture = cls._build_procedural_texture(radius_px, build_seed)
        if pygame.display.get_surface() is not None:
            texture = texture.convert_alpha()
        cls._TEXTURE_CACHE[key] = texture
        cls._trim_caches()
        return texture

    @classmethod
    def _get_cached_pulse_frames(
        cls,
        key: tuple[int, int],
        texture: pygame.Surface,
    ) -> tuple[pygame.Surface, ...]:
        cached = cls._PULSE_CACHE.pop(key, None)
        if cached is not None:
            cls._PULSE_CACHE[key] = cached
            return cached

        frames = cls._build_pulse_frames(texture)
        cls._PULSE_CACHE[key] = frames
        cls._trim_caches()
        return frames

    @classmethod
    def _trim_caches(cls) -> None:
        while len(cls._TEXTURE_CACHE) > cls._TEXTURE_CACHE_MAX:
            oldest_key = next(iter(cls._TEXTURE_CACHE))
            cls._TEXTURE_CACHE.pop(oldest_key, None)
            cls._PULSE_CACHE.pop(oldest_key, None)

        while len(cls._PULSE_CACHE) > cls._TEXTURE_CACHE_MAX:
            oldest_key = next(iter(cls._PULSE_CACHE))
            cls._PULSE_CACHE.pop(oldest_key, None)

    @classmethod
    def _build_pulse_frames(cls, texture: pygame.Surface) -> tuple[pygame.Surface, ...]:
        levels = max(2, int(cls._PULSE_LEVELS))
        base_width = texture.get_width()
        base_height = texture.get_height()
        has_display = pygame.display.get_surface() is not None
        frames: list[pygame.Surface] = []

        for index in range(levels):
            ratio = index / float(levels - 1)
            scale = cls._PULSE_MIN_SCALE + (1.0 - cls._PULSE_MIN_SCALE) * ratio
            if scale >= 0.999:
                frames.append(texture)
                continue

            width = max(4, int(base_width * scale))
            height = max(4, int(base_height * scale))
            frame = pygame.transform.smoothscale(texture, (width, height))
            if has_display:
                frame = frame.convert_alpha()
            frames.append(frame)

        return tuple(frames)

    @classmethod
    def _build_procedural_texture(cls, radius_px: int, seed: int) -> pygame.Surface:
        diameter = radius_px * 2
        surface = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        center = (radius_px, radius_px)

        layers = max(6, min(18, radius_px // 3))
        for layer in range(layers, 0, -1):
            t = layer / float(layers)
            radius = max(1, int(radius_px * t))
            core = t * t
            red = int(195 + 55 * core)
            green = int(35 + 150 * core)
            blue = int(10 + 35 * (1.0 - t))
            alpha = int(16 + 165 * core)
            pygame.draw.circle(surface, (red, green, blue, alpha), center, radius)

        ring_width = max(1, radius_px // 14)
        for i in range(3):
            ring_radius = max(2, int(radius_px * (0.35 + 0.18 * i)))
            ring_alpha = max(10, 35 - i * 9)
            pygame.draw.circle(
                surface,
                (255, 190 - i * 28, 80, ring_alpha),
                center,
                ring_radius,
                ring_width,
            )

        randomizer = random.Random((int(seed) << 9) ^ radius_px ^ 0x45D9F3)
        embers = max(8, min(30, radius_px // 3))
        for _ in range(embers):
            angle = randomizer.random() * math.tau
            distance = (randomizer.random() ** 0.65) * radius_px * 0.84
            ex = int(center[0] + math.cos(angle) * distance)
            ey = int(center[1] + math.sin(angle) * distance)
            ember_radius = max(1, int(1 + radius_px * (0.015 + 0.04 * randomizer.random())))
            ember_color = (
                int(220 + 35 * randomizer.random()),
                int(70 + 120 * randomizer.random()),
                int(20 + 35 * randomizer.random()),
                int(55 + 155 * randomizer.random()),
            )
            pygame.draw.circle(surface, ember_color, (ex, ey), ember_radius)

        pygame.draw.circle(
            surface,
            (255, 230, 135, 60),
            center,
            max(1, int(radius_px * 0.45)),
        )

        return surface
