"""Rendu des sorts actifs reçus du serveur.

Le serveur envoie chaque tick (quand des sorts existent) :
  {"spells": [{"x","y","r","e","vx","vy"[,"rx","ry","ea","bh"]}, ...]}

Champs optionnels :
  rx / ry  — demi-axes de l'ellipse (présents si le sort est allongé)
  ea       — angle de l'ellipse en degrés
  bh       — spell_id  (utilisé pour teinter visuellement)

Rendu :
  cercle  → sphère lumineuse (projectile / aoe / stationary)
  ellipse → mur de force (rx >> ry)
  pool    → halo diffus centré sur le sol (fade_rate > 0)
"""

from __future__ import annotations

import math
from typing import Any

import pygame

# ---------------------------------------------------------------------------
# Palette par élément  (R, G, B)
# ---------------------------------------------------------------------------
_ELEMENT_COLOR: dict[str, tuple[int, int, int]] = {
    "fire":      (255, 100,  20),
    "lightning": ( 80, 210, 255),
    "arcane":    (170,  60, 255),
    "ice":       (140, 220, 255),
    "plasma":    (255, 200,  50),
    "inferno":   (255,  50,   0),
    "storm":     (160, 185, 255),
    "neutral":   (190, 190, 200),
}
_DEFAULT_COLOR = (190, 190, 200)

# Couches de rendu pour les sphères : (radius_factor, alpha)
_GLOW_LAYERS: list[tuple[float, int]] = [
    (2.4,  22),
    (1.7,  45),
    (1.15, 90),
    (0.7, 200),
]

# Couches pour les murs (halo plus allongé, plus vif)
_WALL_GLOW_LAYERS: list[tuple[float, int]] = [
    (1.4,  30),
    (1.15, 70),
    (0.9, 160),
    (0.65, 220),
]

# Couches pour les mares (large halo diffus sur le sol)
_POOL_GLOW_LAYERS: list[tuple[float, int]] = [
    (1.6,  18),
    (1.2,  40),
    (0.8,  80),
    (0.5, 130),
]


class ActiveSpellRenderer:
    """Dessine tous les sorts actifs reçus du serveur."""

    def draw(
        self,
        screen: pygame.Surface,
        spells: list[dict[str, Any]],
        camera: Any,
    ) -> None:
        if not spells:
            return

        screen_w = screen.get_width()
        screen_h = screen.get_height()

        for spell in spells:
            self._draw_spell(screen, spell, camera, screen_w, screen_h)

    # ------------------------------------------------------------------

    def _draw_spell(
        self,
        screen: pygame.Surface,
        spell: dict,
        camera: Any,
        screen_w: int,
        screen_h: int,
    ) -> None:
        world_x = float(spell.get("x", 0.0))
        world_y = float(spell.get("y", 0.0))
        element  = spell.get("e", "neutral")

        # Présence de rx/ry → mur elliptique
        rx_world = spell.get("rx")
        ry_world = spell.get("ry")
        is_wall = rx_world is not None and ry_world is not None
        ea_deg  = float(spell.get("ea", 0)) if is_wall else 0.0
        ea_rad  = math.radians(ea_deg)

        # Rayon de base (pour les sorts ronds)
        radius = max(4.0, float(spell.get("r", 12.0)))

        # Appliquer la caméra
        if camera is not None:
            screen_pos = camera.apply(pygame.Vector2(world_x, world_y))
            sx, sy = int(screen_pos.x), int(screen_pos.y)
        else:
            sx, sy = int(world_x), int(world_y)

        base_r, base_g, base_b = _ELEMENT_COLOR.get(element, _DEFAULT_COLOR)

        if is_wall:
            self._draw_wall(screen, sx, sy,
                            float(rx_world), float(ry_world), ea_rad,
                            base_r, base_g, base_b,
                            screen_w, screen_h)
        else:
            # Détecter une mare via vitesse nulle + grand rayon
            vx = float(spell.get("vx", 0.0))
            vy = float(spell.get("vy", 0.0))
            is_moving = math.hypot(vx, vy) > 5.0
            is_pool   = not is_moving and radius > 40.0

            if is_pool:
                self._draw_pool(screen, sx, sy, radius, base_r, base_g, base_b,
                                screen_w, screen_h)
            else:
                self._draw_sphere(screen, sx, sy, radius, base_r, base_g, base_b,
                                  vx, vy, screen_w, screen_h)

    # ------------------------------------------------------------------
    # Sphère lumineuse (projectile / aoe)
    # ------------------------------------------------------------------

    def _draw_sphere(
        self, screen, sx, sy, radius,
        base_r, base_g, base_b,
        vx, vy, screen_w, screen_h,
    ) -> None:
        max_halo = radius * _GLOW_LAYERS[0][0]
        if (sx + max_halo < 0 or sx - max_halo > screen_w or
                sy + max_halo < 0 or sy - max_halo > screen_h):
            return

        halo_size = int(max_halo * 2) + 2
        halo_surf = pygame.Surface((halo_size, halo_size), pygame.SRCALPHA)
        center = halo_size // 2

        for factor, alpha in _GLOW_LAYERS:
            layer_r = int(radius * factor)
            if layer_r < 1:
                continue
            pygame.draw.circle(halo_surf, (base_r, base_g, base_b, alpha),
                                (center, center), layer_r)

        # Reflet blanc
        core_r = max(2, int(radius * 0.3))
        pygame.draw.circle(halo_surf, (255, 255, 255, 160), (center, center), core_r)

        screen.blit(halo_surf, (sx - center, sy - center))

        # Traînée si en mouvement
        speed = math.hypot(vx, vy)
        if speed > 20.0:
            nx, ny = -vx / speed, -vy / speed
            trail_len = min(radius * 2.0, speed * 0.06)
            trail_alpha = min(180, int(speed * 0.25))
            for i in range(4):
                t = (i + 1) / 4
                tx = sx + int(nx * trail_len * t)
                ty = sy + int(ny * trail_len * t)
                tr = max(1, int(radius * (1.0 - t * 0.7)))
                ta = int(trail_alpha * (1.0 - t * 0.6))
                tsurf = pygame.Surface((tr * 2 + 2, tr * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(tsurf, (base_r, base_g, base_b, ta),
                                   (tr + 1, tr + 1), tr)
                screen.blit(tsurf, (tx - tr - 1, ty - tr - 1))

    # ------------------------------------------------------------------
    # Mur — ellipse orientée
    # ------------------------------------------------------------------

    def _draw_wall(
        self, screen, sx, sy,
        rx, ry, angle_rad,
        base_r, base_g, base_b,
        screen_w, screen_h,
    ) -> None:
        max_extent = max(rx, ry) * 1.5
        if (sx + max_extent < 0 or sx - max_extent > screen_w or
                sy + max_extent < 0 or sy - max_extent > screen_h):
            return

        surf_w = int(max_extent * 2) + 4
        surf_h = int(max_extent * 2) + 4
        wall_surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
        cx, cy = surf_w // 2, surf_h // 2

        for factor, alpha in _WALL_GLOW_LAYERS:
            erx = int(rx * factor)
            ery = int(ry * factor * 1.5 + 4)  # halo légèrement plus épais
            if erx < 1 or ery < 1:
                continue
            self._draw_ellipse_rotated(
                wall_surf, (base_r, base_g, base_b, alpha),
                cx, cy, erx, ery, angle_rad,
            )

        # Ligne centrale brillante
        self._draw_ellipse_rotated(
            wall_surf, (255, 255, 255, 120),
            cx, cy, max(1, int(rx * 0.5)), max(1, int(ry * 0.3)), angle_rad,
        )

        screen.blit(wall_surf, (sx - cx, sy - cy))

    @staticmethod
    def _draw_ellipse_rotated(
        surf: pygame.Surface,
        color: tuple,
        cx: int, cy: int,
        rx: int, ry: int,
        angle_rad: float,
    ) -> None:
        """Dessine une ellipse orientée via une surface temporaire."""
        if rx < 1 or ry < 1:
            return
        tmp = pygame.Surface((rx * 2 + 2, ry * 2 + 2), pygame.SRCALPHA)
        pygame.draw.ellipse(tmp, color, tmp.get_rect())
        rotated = pygame.transform.rotate(tmp, -math.degrees(angle_rad))
        rw, rh = rotated.get_size()
        surf.blit(rotated, (cx - rw // 2, cy - rh // 2))

    # ------------------------------------------------------------------
    # Mare — halo diffus au sol, pas de cœur lumineux
    # ------------------------------------------------------------------

    def _draw_pool(
        self, screen, sx, sy, radius,
        base_r, base_g, base_b,
        screen_w, screen_h,
    ) -> None:
        max_halo = radius * _POOL_GLOW_LAYERS[0][0]
        if (sx + max_halo < 0 or sx - max_halo > screen_w or
                sy + max_halo < 0 or sy - max_halo > screen_h):
            return

        # Aplatir légèrement en ellipse pour un effet "sol"
        rx_pool = int(radius * 1.1)
        ry_pool = int(radius * 0.6)

        halo_size = int(max_halo * 2) + 4
        pool_surf = pygame.Surface((halo_size, halo_size), pygame.SRCALPHA)
        cx, cy = halo_size // 2, halo_size // 2

        for factor, alpha in _POOL_GLOW_LAYERS:
            erx = int(rx_pool * factor)
            ery = int(ry_pool * factor)
            if erx < 1 or ery < 1:
                continue
            tmp = pygame.Surface((erx * 2 + 2, ery * 2 + 2), pygame.SRCALPHA)
            pygame.draw.ellipse(tmp, (base_r, base_g, base_b, alpha), tmp.get_rect())
            pool_surf.blit(tmp, (cx - erx - 1, cy - ery - 1))

        # Légère ondulation centrale (cercle semi-transparent)
        pygame.draw.circle(pool_surf, (base_r, base_g, base_b, 50),
                           (cx, cy), max(4, int(radius * 0.2)))

        screen.blit(pool_surf, (sx - cx, sy - cy))
