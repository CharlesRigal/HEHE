"""Cercle du pentacle (README C1, C3, C4).

N'importe quelle boucle fermee compte, en un ou plusieurs traits. La boucle
est fermee si aucun trou entre ses points ne depasse l'epaisseur du trait :
le plus grand ecart angulaire autour du centre, ramene en longueur d'arc,
reste <= epaisseur (meme regle que le contact, L2). Seuls les points proches
du rayon moyen comptent : une spirale couvre tous les angles sans etre une
boucle.

Seule une boucle ronde (variation de rayon <= MAX_RADIUS_VARIATION) est un
cercle : un triangle ferme reste un signe. Un cercle trop irregulier n'est
donc jamais ferme, et le pentacle reste inerte (C1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from client.magic.grouping import Symbol

# Variation de rayon admise (ecart-type / rayon moyen) avant que le cercle meure.
MAX_RADIUS_VARIATION = 0.08
# Bande autour du rayon moyen ou les points comptent pour la fermeture.
RING_BAND = 0.3


@dataclass
class LoopMeasure:
    center: tuple[float, float]
    radius: float
    closed: bool
    radius_variation: float

    @property
    def quality(self) -> float:
        """1 pour un cercle parfait, 0.5 a la limite, 0 au-dela (mort)."""
        if not self.closed or self.radius_variation > MAX_RADIUS_VARIATION:
            return 0.0
        return 1.0 - 0.5 * self.radius_variation / MAX_RADIUS_VARIATION


def measure_loop(symbol: Symbol, thickness: float) -> LoopMeasure:
    pts = symbol.points
    cx, cy = pts.mean(axis=0)
    dx, dy = pts[:, 0] - cx, pts[:, 1] - cy
    radii = np.hypot(dx, dy)
    radius = float(radii.mean())
    if radius <= thickness:
        return LoopMeasure((float(cx), float(cy)), radius, False, 1.0)
    on_ring = np.abs(radii - radius) <= RING_BAND * radius
    if int(on_ring.sum()) < 3:
        return LoopMeasure((float(cx), float(cy)), radius, False, float(radii.std() / radius))
    angles = np.sort(np.arctan2(dy[on_ring], dx[on_ring]))
    gaps = np.diff(np.concatenate([angles, angles[:1] + 2 * math.pi]))
    closed = float(gaps.max()) * radius <= thickness
    return LoopMeasure((float(cx), float(cy)), radius, closed, float(radii.std() / radius))


def find_circle(symbols: list[Symbol], thickness: float) -> tuple[Symbol, LoopMeasure] | None:
    """La plus grande boucle fermee et ronde : c'est le cercle (L5)."""
    best: tuple[Symbol, LoopMeasure] | None = None
    for symbol in symbols:
        loop = measure_loop(symbol, thickness)
        if loop.quality > 0.0 and (best is None or loop.radius > best[1].radius):
            best = (symbol, loop)
    return best
