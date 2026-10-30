"""Rendu de la grille du monde recue du serveur (README, « Le monde »).

Le serveur envoie les cellules non vides :
  [index, eau, terre, air, chaleur, charge, lumiere]
Chaque grandeur est une couche de couleur ; l'etat de la matiere (glace,
vapeur, lave) suit les memes seuils de chaleur que le serveur.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pygame

# Doivent rester identiques a server/world/grid.py.
FREEZE_BELOW = -0.5
BOIL_ABOVE = 1.0
MELT_ABOVE = 1.5

_FIELDS = ("water", "earth", "air", "heat", "charge", "light")

_ELEMENT_COLORS = {
    "fire": (255, 110, 40),
    "ice": (150, 225, 255),
    "water": (60, 130, 230),
    "wind": (210, 230, 245),
    "earth": (140, 100, 60),
    "lightning": (255, 235, 90),
    "light": (255, 250, 210),
}


def _over(rgb: np.ndarray, alpha: np.ndarray, color: tuple[int, int, int], layer_alpha: np.ndarray) -> None:
    """Compose une couche de couleur unie sur (rgb, alpha), en place (couleurs non premultipliees)."""
    a = np.clip(layer_alpha, 0.0, 1.0)
    out_alpha = a + alpha * (1.0 - a)
    weight_new = np.divide(a, out_alpha, out=np.zeros_like(a), where=out_alpha > 0)[..., None]
    rgb[:] = rgb * (1.0 - weight_new) + np.asarray(color, dtype=float) * weight_new
    alpha[:] = out_alpha


class WorldRenderer:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.cell_size = 16.0
        self.cols = 0
        self.rows = 0
        self.fields: dict[str, np.ndarray] = {}
        self.spells: list[dict] = []
        self._surface: pygame.Surface | None = None

    def load(self, world: dict | None) -> None:
        """Etat complet recu a l'arrivee dans l'instance."""
        if not world:
            self.reset()
            return
        self.cell_size = float(world.get("cs", 16.0))
        self.cols = int(world.get("cols", 0))
        self.rows = int(world.get("rows", 0))
        self.set_cells(world.get("cells", []))

    def set_cells(self, cells: Iterable[list[float]]) -> None:
        if self.cols <= 0 or self.rows <= 0:
            return
        values = np.zeros((len(_FIELDS), self.rows * self.cols))
        for cell in cells:
            index = int(cell[0])
            if 0 <= index < self.rows * self.cols:
                values[:, index] = cell[1:1 + len(_FIELDS)]
        self.fields = {
            name: values[k].reshape(self.rows, self.cols) for k, name in enumerate(_FIELDS)
        }
        self._surface = None

    def set_spells(self, spells: list[dict] | None) -> None:
        self.spells = list(spells or [])

    def _build_surface(self) -> pygame.Surface | None:
        if not self.fields:
            return None
        f = self.fields
        rgb = np.zeros((self.rows, self.cols, 3))
        alpha = np.zeros((self.rows, self.cols))
        water, earth, heat = f["water"], f["earth"], f["heat"]
        ice = heat < FREEZE_BELOW
        vapor = heat > BOIL_ABOVE
        lava = heat > MELT_ABOVE

        _over(rgb, alpha, (140, 100, 60), np.where(lava, 0.0, earth * 0.7))
        _over(rgb, alpha, (255, 110, 30), np.where(lava, earth * 0.9, 0.0))
        _over(rgb, alpha, (40, 110, 230), np.where(ice | vapor, 0.0, water * 0.45))
        _over(rgb, alpha, (200, 235, 255), np.where(ice, water * 0.8, 0.0))
        _over(rgb, alpha, (235, 235, 245), np.where(vapor & ~ice, water * 0.35, 0.0))
        _over(rgb, alpha, (255, 80, 20), np.clip(heat, 0.0, None) * 0.25)
        _over(rgb, alpha, (120, 220, 255), np.clip(-heat, 0.0, None) * 0.25)
        _over(rgb, alpha, (210, 230, 245), f["air"] * 0.25)
        _over(rgb, alpha, (255, 240, 90), f["charge"] * 0.5)
        _over(rgb, alpha, (255, 255, 220), f["light"] * 0.5)

        pixels = np.dstack([rgb, alpha[..., None] * 255.0]).clip(0, 255).astype(np.uint8)
        small = pygame.image.frombuffer(pixels.tobytes(), (self.cols, self.rows), "RGBA")
        size = (int(self.cols * self.cell_size), int(self.rows * self.cell_size))
        return pygame.transform.smoothscale(small, size)

    def draw(self, screen: pygame.Surface, camera: Any) -> None:
        if self._surface is None:
            self._surface = self._build_surface()
        if self._surface is not None:
            screen.blit(self._surface, (-camera.offset.x, -camera.offset.y))
        self._draw_spells(screen, camera)

    def _draw_spells(self, screen: pygame.Surface, camera: Any) -> None:
        for spell in self.spells:
            try:
                center = camera.apply(pygame.Vector2(float(spell["x"]), float(spell["y"])))
                radius = float(spell["R"])
            except (KeyError, TypeError, ValueError):
                continue
            color = _ELEMENT_COLORS.get(spell.get("e"), (200, 200, 200))
            fade = max(0.25, min(1.0, float(spell.get("left", 1.0))))
            size = int(radius * 2 + 8)
            ring = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(ring, (*color, int(160 * fade)), (size // 2, size // 2), int(radius), 2)
            # Repere de duree : un arc qui raccourcit avec le temps restant.
            rect = pygame.Rect(4, 4, int(radius * 2), int(radius * 2))
            pygame.draw.arc(ring, (*color, int(220 * fade)), rect, math.pi / 2,
                            math.pi / 2 + 2 * math.pi * min(1.0, fade), 3)
            screen.blit(ring, (center.x - size // 2, center.y - size // 2))
