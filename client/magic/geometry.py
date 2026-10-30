"""Outils geometriques sur les traits (listes de points)."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

Point = tuple[float, float]
Stroke = list[Point]


def path_length(points: Sequence[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def densify(points: Sequence[Point], spacing: float) -> np.ndarray:
    """Points le long du trait, espaces d'au plus `spacing` (un point isole reste un point)."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) < 2:
        return pts
    out = [pts[:1]]
    for a, b in zip(pts[:-1], pts[1:]):
        length = float(np.hypot(*(b - a)))
        steps = max(1, int(math.ceil(length / spacing)))
        t = np.arange(1, steps + 1)[:, None] / steps
        out.append(a + (b - a) * t)
    return np.concatenate(out)


def resample(points: Sequence[Point], count: int) -> np.ndarray:
    """`count` points equidistants le long du trait."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(pts) == 1 or count <= 1:
        return np.repeat(pts[:1], max(1, count), axis=0)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if cum[-1] <= 0.0:
        return np.repeat(pts[:1], count, axis=0)
    targets = np.linspace(0.0, cum[-1], count)
    xs = np.interp(targets, cum, pts[:, 0])
    ys = np.interp(targets, cum, pts[:, 1])
    return np.stack([xs, ys], axis=1)


def min_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Plus petite distance entre deux nuages de points."""
    diff = a[:, None, :] - b[None, :, :]
    return float(np.sqrt((diff ** 2).sum(axis=2)).min())


def bbox(points: np.ndarray) -> tuple[float, float, float, float]:
    return (
        float(points[:, 0].min()), float(points[:, 1].min()),
        float(points[:, 0].max()), float(points[:, 1].max()),
    )
