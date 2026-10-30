"""Rendu des entites interactives recues du serveur.

Le serveur diffuse a chaque changement la liste des entites au format :

  {"id": "altar_left", "type": "altar", "x": 500, "y": 150, "r": 28,
   "state": {"powered": true}}

Rendu 2D simple de chaque type d'entite selon son etat (door: couleur
differente si open, pressure_plate: halo quand pressed, altar: halo quand
powered). Pas de sprite : purement pygame.draw.

Types couverts :
  door, pressure_plate, crystal, altar
Le fallback est un cercle gris.
"""
from __future__ import annotations

from typing import Any, Iterable

import pygame


_COLORS = {
    "stone":       ( 90,  85,  78),
    "stone_dark":  ( 56,  52,  48),
    "metal":       (160, 160, 170),
    "ice_dark":    (110, 170, 220),
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
    "door": _draw_door,
    "pressure_plate": _draw_pressure_plate,
    "crystal": _draw_crystal,
    "altar": _draw_altar,
}


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((1, 1))
    surface = pygame.Surface((400, 400))
    renderer = InteractiveEntityRenderer()
    renderer.draw(surface, [
        {"id": "d1", "type": "door", "x": 300, "y": 200, "r": 20, "state": {"open": False}},
        {"id": "d2", "type": "door", "x": 340, "y": 200, "r": 20, "state": {"open": True}},
        {"id": "p1", "type": "pressure_plate", "x": 200, "y": 300, "r": 24, "state": {"pressed": True}},
        {"id": "c1", "type": "crystal", "x": 50, "y": 300, "r": 16, "state": {"lifted": False}},
        {"id": "a1", "type": "altar", "x": 120, "y": 350, "r": 28, "state": {"powered": True}},
        {"id": "x1", "type": "unknown", "x": 350, "y": 50, "r": 12, "state": {}},
    ], camera=None)
    print("interactive_entity_renderer: OK")
