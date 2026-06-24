"""Rendu des entites interactives recues du serveur (Phase 3).

Le serveur diffuse a chaque changement la liste des entites au format :

  {"id": "torch_west", "type": "torch", "x": 320, "y": 360, "r": 18,
   "state": {"lit": true}}

Ce module fait un rendu 2D simple de chaque type d'entite en fonction de
son etat (torch: flamme visible si lit, door: couleur differente si open,
pressure_plate: halo quand pressed...). Pas de sprite : purement pygame.draw.

Types couverts :
  torch, brazier, door, pressure_plate, ice_patch, water_pool
Le fallback est un cercle gris.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

import pygame


_COLORS = {
    "stone":       ( 90,  85,  78),
    "stone_dark":  ( 56,  52,  48),
    "wood":        (112,  72,  40),
    "flame_core":  (255, 230, 120),
    "flame_mid":   (255, 160,  40),
    "flame_glow":  (255,  90,  10),
    "metal":       (160, 160, 170),
    "metal_hot":   (255, 140,  40),
    "ice":         (180, 230, 255),
    "ice_dark":    (110, 170, 220),
    "water":       ( 60, 130, 220),
    "water_bright":(120, 190, 255),
    "door_closed": (100,  70,  40),
    "door_open":   ( 50, 140,  70),
    "plate_idle":  (110, 110, 120),
    "plate_active":(255, 200,  80),
    "crystal":     (180, 200, 255),
    "crystal_lit": (220, 230, 255),
    "altar":       (170, 160, 180),
    "altar_lit":   (255, 220, 150),
}


class InteractiveEntityRenderer:
    """Rend chaque entite d'apres son type et son dict `state`."""

    def draw(
        self,
        screen: pygame.Surface,
        entities: Iterable[dict[str, Any]],
        camera: Any,
    ) -> None:
        for ent in entities:
            try:
                self._draw_one(screen, ent, camera)
            except Exception:
                # Best-effort : si un champ manque, on saute l'entite sans crasher.
                continue

    def _draw_one(self, screen: pygame.Surface, ent: dict, camera: Any) -> None:
        etype = ent.get("type", "prop")
        wx = float(ent.get("x", 0.0))
        wy = float(ent.get("y", 0.0))
        r = max(4.0, float(ent.get("r", 20.0)))
        state = ent.get("state", {}) or {}

        if camera is not None:
            p = camera.apply(pygame.Vector2(wx, wy))
            sx, sy = int(p.x), int(p.y)
        else:
            sx, sy = int(wx), int(wy)

        draw = _TYPE_DISPATCH.get(etype, _draw_default)
        draw(screen, sx, sy, r, state)


# ─── Handlers par type ──────────────────────────────────────────

def _draw_torch(screen, sx, sy, r, state) -> None:
    lit = bool(state.get("lit"))
    base_w = int(r * 0.8)
    base_h = int(r * 1.6)
    # Socle : pierre
    pygame.draw.rect(
        screen, _COLORS["stone"],
        (sx - base_w // 2, sy - base_h // 4, base_w, base_h),
    )
    pygame.draw.rect(
        screen, _COLORS["stone_dark"],
        (sx - base_w // 2, sy - base_h // 4, base_w, base_h), width=1,
    )
    # Bras de torche (bois)
    head_cx = sx
    head_cy = sy - int(r * 0.8)
    pygame.draw.line(
        screen, _COLORS["wood"],
        (sx, sy - base_h // 4), (head_cx, head_cy),
        width=3,
    )
    if lit:
        _draw_flame(screen, head_cx, head_cy, size=int(r * 0.9))
    else:
        pygame.draw.circle(screen, _COLORS["metal"], (head_cx, head_cy), max(2, int(r * 0.25)))


def _draw_brazier(screen, sx, sy, r, state) -> None:
    lit = bool(state.get("lit", True))
    bowl_w = int(r * 2.0)
    bowl_h = int(r * 0.7)
    pygame.draw.ellipse(
        screen, _COLORS["metal"],
        (sx - bowl_w // 2, sy - bowl_h // 2, bowl_w, bowl_h),
    )
    pygame.draw.ellipse(
        screen, _COLORS["stone_dark"],
        (sx - bowl_w // 2, sy - bowl_h // 2, bowl_w, bowl_h), width=2,
    )
    if lit:
        _draw_flame(screen, sx, sy - int(r * 0.3), size=int(r * 1.3))


def _draw_door(screen, sx, sy, r, state) -> None:
    is_open = bool(state.get("open"))
    w = int(r * 1.6)
    h = int(r * 2.4)
    col = _COLORS["door_open"] if is_open else _COLORS["door_closed"]
    rect = pygame.Rect(sx - w // 2, sy - h // 2, w, h)
    if is_open:
        # Porte entrouverte : trait fin + halo
        pygame.draw.rect(screen, col, rect, width=2)
    else:
        pygame.draw.rect(screen, col, rect)
        pygame.draw.rect(screen, _COLORS["stone_dark"], rect, width=2)
        # Poignee
        pygame.draw.circle(screen, _COLORS["metal"], (sx + w // 4, sy), 2)


def _draw_pressure_plate(screen, sx, sy, r, state) -> None:
    pressed = bool(state.get("pressed"))
    w = int(r * 2.0)
    h = int(r * 0.6)
    col = _COLORS["plate_active"] if pressed else _COLORS["plate_idle"]
    rect = pygame.Rect(sx - w // 2, sy - h // 2, w, h)
    pygame.draw.rect(screen, col, rect)
    pygame.draw.rect(screen, _COLORS["stone_dark"], rect, width=1)
    if pressed:
        halo = pygame.Surface((w + 10, h + 10), pygame.SRCALPHA)
        pygame.draw.ellipse(halo, (*col, 80), halo.get_rect())
        screen.blit(halo, (sx - (w + 10) // 2, sy - (h + 10) // 2))


def _draw_ice_patch(screen, sx, sy, r, state) -> None:
    _ = state
    radius = int(r)
    base = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
    pygame.draw.circle(base, (*_COLORS["ice"], 180), (radius + 2, radius + 2), radius)
    pygame.draw.circle(base, (*_COLORS["ice_dark"], 220), (radius + 2, radius + 2), radius, width=2)
    screen.blit(base, (sx - radius - 2, sy - radius - 2))


def _draw_water_pool(screen, sx, sy, r, state) -> None:
    _ = state
    radius = int(r)
    surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
    pygame.draw.circle(surf, (*_COLORS["water"], 170), (radius + 2, radius + 2), radius)
    pygame.draw.circle(surf, (*_COLORS["water_bright"], 90), (radius + 2, radius + 2), int(radius * 0.7))
    screen.blit(surf, (sx - radius - 2, sy - radius - 2))


def _draw_crystal(screen, sx, sy, r, state) -> None:
    """Cristal facette : losange avec gradient clair/sombre. `lifted` ajoute une lueur."""
    _ = state
    rr = int(r)
    diag_v = rr + 4
    diag_h = int(rr * 0.75) + 2
    points = [
        (sx, sy - diag_v),
        (sx + diag_h, sy),
        (sx, sy + diag_v),
        (sx - diag_h, sy),
    ]
    pygame.draw.polygon(screen, _COLORS["crystal"], points)
    pygame.draw.polygon(screen, _COLORS["ice_dark"], points, width=2)
    # Reflet interne
    highlight = [(sx, sy - diag_v + 4), (sx + 3, sy - 2), (sx, sy + 4), (sx - 3, sy - 2)]
    pygame.draw.polygon(screen, _COLORS["crystal_lit"], highlight)


def _draw_altar(screen, sx, sy, r, state) -> None:
    powered = bool(state.get("powered"))
    w = int(r * 2.2)
    h = int(r * 1.4)
    col = _COLORS["altar_lit"] if powered else _COLORS["altar"]
    rect = pygame.Rect(sx - w // 2, sy - h // 2, w, h)
    pygame.draw.rect(screen, col, rect)
    pygame.draw.rect(screen, _COLORS["stone_dark"], rect, width=2)
    # Rune gravee
    inner = pygame.Rect(rect.left + 6, rect.top + 6, rect.width - 12, rect.height - 12)
    pygame.draw.rect(screen, _COLORS["stone_dark"], inner, width=1)
    if powered:
        halo = pygame.Surface((w + 30, h + 30), pygame.SRCALPHA)
        pygame.draw.ellipse(halo, (*_COLORS["altar_lit"], 90), halo.get_rect())
        screen.blit(halo, (sx - (w + 30) // 2, sy - (h + 30) // 2))


def _draw_default(screen, sx, sy, r, state) -> None:
    _ = state
    pygame.draw.circle(screen, (160, 160, 160), (sx, sy), int(r), width=2)


_TYPE_DISPATCH = {
    "torch": _draw_torch,
    "brazier": _draw_brazier,
    "door": _draw_door,
    "pressure_plate": _draw_pressure_plate,
    "ice_patch": _draw_ice_patch,
    "water_pool": _draw_water_pool,
    "crystal": _draw_crystal,
    "altar": _draw_altar,
}


# ─── Helpers visuels ─────────────────────────────────────────────

def _draw_flame(screen: pygame.Surface, cx: int, cy: int, size: int) -> None:
    """Flamme a trois couches : lueur, moyenne, coeur."""
    size = max(4, size)
    glow = pygame.Surface((size * 3, size * 3), pygame.SRCALPHA)
    g_cx = size * 3 // 2
    g_cy = size * 3 // 2
    pygame.draw.circle(glow, (*_COLORS["flame_glow"], 110), (g_cx, g_cy), size)
    pygame.draw.circle(glow, (*_COLORS["flame_mid"], 180), (g_cx, g_cy), int(size * 0.7))
    pygame.draw.circle(glow, (*_COLORS["flame_core"], 230), (g_cx, g_cy), max(2, int(size * 0.35)))
    screen.blit(glow, (cx - g_cx, cy - g_cy))


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((1, 1))
    surface = pygame.Surface((400, 400))
    renderer = InteractiveEntityRenderer()
    renderer.draw(surface, [
        {"id": "t1", "type": "torch", "x": 50, "y": 100, "r": 18, "state": {"lit": True}},
        {"id": "t2", "type": "torch", "x": 100, "y": 100, "r": 18, "state": {"lit": False}},
        {"id": "b1", "type": "brazier", "x": 200, "y": 150, "r": 24, "state": {"lit": True}},
        {"id": "d1", "type": "door", "x": 300, "y": 200, "r": 20, "state": {"open": False}},
        {"id": "d2", "type": "door", "x": 340, "y": 200, "r": 20, "state": {"open": True}},
        {"id": "p1", "type": "pressure_plate", "x": 200, "y": 300, "r": 24, "state": {"pressed": True}},
        {"id": "c1", "type": "crystal", "x": 50, "y": 300, "r": 16, "state": {"lifted": False}},
        {"id": "a1", "type": "altar", "x": 120, "y": 350, "r": 28, "state": {"powered": True}},
        {"id": "x1", "type": "unknown", "x": 350, "y": 50, "r": 12, "state": {}},
    ], camera=None)
    print("interactive_entity_renderer: OK")
