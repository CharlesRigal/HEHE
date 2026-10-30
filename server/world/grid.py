"""Grille du monde : quantites d'element par cellule (README, section « Le monde »).

Chaque cellule porte six grandeurs : eau, terre, air, chaleur (signee),
charge, lumiere. Les sorts ne font que deplacer ou creer une grandeur ; le
reste vient de la physique naturelle de la grille :

- transport conservatif (flux upwind) : un flux convergent accumule ;
- diffusion selon la mobilite de la cellule ;
- dissipation (air, charge, lumiere) et retour de la chaleur vers 0.

Regle M0 : toute regle est un seuil sur une grandeur de cellule. Ici, le
seul seuil (M1) porte sur la chaleur et ne change que la mobilite :
glace (eau froide, immobile), vapeur (eau chaude, tres mobile), lave
(terre chaude, mobile).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


FIELDS = ("water", "earth", "air", "heat", "charge", "light")
MATTER_FIELDS = ("water", "earth", "air")

# Emblème -> (grandeur portee, signe). La glace est une chaleur negative.
ELEMENT_FIELD: dict[str, tuple[str, float]] = {
    "fire": ("heat", 1.0),
    "ice": ("heat", -1.0),
    "water": ("water", 1.0),
    "wind": ("air", 1.0),
    "earth": ("earth", 1.0),
    "lightning": ("charge", 1.0),
    "light": ("light", 1.0),
}

# Seuils M1, sur la chaleur uniquement.
FREEZE_BELOW = -0.5
BOIL_ABOVE = 1.0
MELT_ABOVE = 1.5

# Air ambiant : le vent est partout (E5), meme sans air cree.
AMBIENT_AIR = 1.0

# Diffusion naturelle (par seconde) et dissipation (fraction par seconde).
_DIFFUSION = {
    "water": 0.6,
    "earth": 0.0,
    "air": 3.0,
    "heat": 1.0,
    "charge": 2.0,
    "light": 1.5,
}
_WATER_ICE_DIFFUSION = 0.0
_WATER_VAPOR_DIFFUSION = 4.0
_EARTH_LAVA_DIFFUSION = 0.3
_DECAY = {
    "air": 1.0,
    "heat": 0.15,
    "charge": 0.8,
    "light": 2.0,
}

# Fraction max d'une cellule transportee par sous-pas (stabilite numerique).
_CFL = 0.25


@dataclass
class Flow:
    """Ecoulement impose a une grandeur pendant un tick.

    vx, vy : vitesse par cellule (px/s). hold : 0..1, part de la matiere
    d'une cellule retenue sur place (suspension).
    """
    vx: np.ndarray
    vy: np.ndarray
    hold: np.ndarray


class WorldGrid:
    def __init__(
        self,
        width: float,
        height: float,
        cell_size: float = 16.0,
        walls: list[tuple[float, float, float, float]] | None = None,
    ) -> None:
        self.cell_size = float(cell_size)
        self.cols = max(1, int(math.ceil(float(width) / self.cell_size)))
        self.rows = max(1, int(math.ceil(float(height) / self.cell_size)))
        shape = (self.rows, self.cols)
        self.fields: dict[str, np.ndarray] = {name: np.zeros(shape) for name in FIELDS}
        self.solid = np.zeros(shape, dtype=bool)
        for x1, y1, x2, y2 in walls or []:
            c1, r1 = self._clamp_cell(x1, y1)
            c2, r2 = self._clamp_cell(x2 - 1e-6, y2 - 1e-6)
            self.solid[r1:r2 + 1, c1:c2 + 1] = True
        ys = (np.arange(self.rows) + 0.5) * self.cell_size
        xs = (np.arange(self.cols) + 0.5) * self.cell_size
        self.center_x, self.center_y = np.meshgrid(xs, ys)
        # Faces ouvertes : aucune des deux cellules n'est solide.
        self._open_x = ~(self.solid[:, :-1] | self.solid[:, 1:])
        self._open_y = ~(self.solid[:-1, :] | self.solid[1:, :])

    # ── Acces ─────────────────────────────────────────────────────

    def _clamp_cell(self, x: float, y: float) -> tuple[int, int]:
        col = int(min(self.cols - 1, max(0, x // self.cell_size)))
        row = int(min(self.rows - 1, max(0, y // self.cell_size)))
        return col, row

    def cell_of(self, x: float, y: float) -> tuple[int, int] | None:
        """(row, col) de la cellule contenant (x, y), ou None hors grille."""
        col = int(x // self.cell_size)
        row = int(y // self.cell_size)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return row, col
        return None

    def total(self, field: str) -> float:
        return float(self.fields[field].sum())

    def add_rect(self, field: str, x: float, y: float, w: float, h: float, amount: float) -> None:
        """Ajoute `amount` par cellule dans un rectangle (contenu de carte)."""
        mask = (
            (self.center_x >= x) & (self.center_x < x + w)
            & (self.center_y >= y) & (self.center_y < y + h)
            & ~self.solid
        )
        self.fields[field][mask] += float(amount)

    def add_disc(self, field: str, x: float, y: float, radius: float, total: float) -> None:
        """Repartit `total` sur les cellules libres d'un disque (au moins une)."""
        dist_sq = (self.center_x - x) ** 2 + (self.center_y - y) ** 2
        mask = (dist_sq <= radius * radius) & ~self.solid
        count = int(mask.sum())
        if count == 0:
            cell = self.cell_of(x, y)
            if cell is None or self.solid[cell]:
                return
            self.fields[field][cell] += float(total)
            return
        self.fields[field][mask] += float(total) / count

    # ── Etats M1 ──────────────────────────────────────────────────

    def ice_mask(self) -> np.ndarray:
        return (self.fields["water"] > 1e-3) & (self.fields["heat"] < FREEZE_BELOW)

    def vapor_mask(self) -> np.ndarray:
        return (self.fields["water"] > 1e-3) & (self.fields["heat"] > BOIL_ABOVE)

    def lava_mask(self) -> np.ndarray:
        return (self.fields["earth"] > 1e-3) & (self.fields["heat"] > MELT_ABOVE)

    def _diffusion(self, field: str) -> np.ndarray:
        """Coefficient de diffusion par cellule (par seconde)."""
        heat = self.fields["heat"]
        if field == "water":
            coeff = np.full(self.solid.shape, _DIFFUSION["water"])
            coeff[heat < FREEZE_BELOW] = _WATER_ICE_DIFFUSION
            coeff[heat > BOIL_ABOVE] = _WATER_VAPOR_DIFFUSION
            return coeff
        if field == "earth":
            coeff = np.zeros(self.solid.shape)
            coeff[heat > MELT_ABOVE] = _EARTH_LAVA_DIFFUSION
            return coeff
        return np.full(self.solid.shape, _DIFFUSION[field])

    # ── Simulation ────────────────────────────────────────────────

    def step(self, dt: float, flows: dict[str, Flow] | None = None) -> None:
        flows = flows or {}
        for field in FIELDS:
            flow = flows.get(field)
            hold = flow.hold if flow is not None else None
            if flow is not None:
                self._advect(field, flow, dt)
            self._diffuse(field, dt, hold)
            decay = _DECAY.get(field)
            if decay:
                keep = math.exp(-decay * dt)
                if hold is not None:
                    keep = keep + (1.0 - keep) * hold
                self.fields[field] *= keep
            if field != "heat":
                np.maximum(self.fields[field], 0.0, out=self.fields[field])
            self.fields[field][self.solid] = 0.0

    def _advect(self, field: str, flow: Flow, dt: float) -> None:
        q = self.fields[field]
        ux = 0.5 * (flow.vx[:, :-1] + flow.vx[:, 1:]) * self._open_x
        uy = 0.5 * (flow.vy[:-1, :] + flow.vy[1:, :]) * self._open_y
        max_speed = max(float(np.abs(ux).max(initial=0.0)), float(np.abs(uy).max(initial=0.0)))
        if max_speed <= 0.0:
            return
        substeps = max(1, int(math.ceil(max_speed * dt / self.cell_size / _CFL)))
        h = dt / substeps / self.cell_size
        release = 1.0 - flow.hold
        for _ in range(substeps):
            out = q * release
            fx = np.where(ux > 0.0, out[:, :-1], out[:, 1:]) * ux * h
            fy = np.where(uy > 0.0, out[:-1, :], out[1:, :]) * uy * h
            q[:, :-1] -= fx
            q[:, 1:] += fx
            q[:-1, :] -= fy
            q[1:, :] += fy

    def _diffuse(self, field: str, dt: float, hold: np.ndarray | None) -> None:
        coeff = self._diffusion(field)
        if hold is not None:
            coeff = coeff * (1.0 - hold)
        if not coeff.any():
            return
        q = self.fields[field]
        # Face : la cellule la moins mobile decide (pas d'echange avec la glace).
        kx = np.minimum(coeff[:, :-1], coeff[:, 1:]) * self._open_x
        ky = np.minimum(coeff[:-1, :], coeff[1:, :]) * self._open_y
        max_k = max(float(kx.max(initial=0.0)), float(ky.max(initial=0.0)))
        substeps = max(1, int(math.ceil(max_k * dt / 0.2)))
        h = dt / substeps
        for _ in range(substeps):
            fx = kx * (q[:, :-1] - q[:, 1:]) * h
            fy = ky * (q[:-1, :] - q[1:, :]) * h
            q[:, :-1] -= fx
            q[:, 1:] += fx
            q[:-1, :] -= fy
            q[1:, :] += fy

    # ── Reseau ────────────────────────────────────────────────────

    def snapshot(self, eps: float = 0.02) -> list[list[float]]:
        """Cellules non vides : [index, eau, terre, air, chaleur, charge, lumiere]."""
        stack = np.stack([self.fields[name] for name in FIELDS])
        active = np.abs(stack).max(axis=0) > eps
        out: list[list[float]] = []
        for index in np.flatnonzero(active):
            row, col = divmod(int(index), self.cols)
            values = [round(float(stack[k, row, col]), 2) for k in range(len(FIELDS))]
            out.append([int(index), *values])
        return out


if __name__ == "__main__":
    grid = WorldGrid(160, 160, cell_size=16)
    grid.add_disc("water", 80, 80, 20, total=10.0)
    before = grid.total("water")
    for _ in range(120):
        grid.step(1 / 60)
    assert abs(grid.total("water") - before) < 1e-6, "diffusion conservative"

    grid.fields["heat"][:] = -2.0
    frozen = grid.fields["water"].copy()
    grid.step(1 / 60)
    assert np.allclose(frozen, grid.fields["water"]), "la glace ne bouge pas"
    print("grid: OK")
