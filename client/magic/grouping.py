"""Groupement des traits en symboles (README L2, L3, L4).

Deux traits se touchent si et seulement s'ils se touchent a l'ecran : la
distance entre leurs lignes centrales est <= l'epaisseur de trait rendue.
Des traits qui se touchent forment un seul symbole.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from client.magic.geometry import Stroke, bbox, densify, min_distance


@dataclass
class Symbol:
    strokes: list[Stroke]
    points: np.ndarray                      # points densifies de tous les traits
    stroke_indices: list[int] = field(default_factory=list)

    @property
    def centroid(self) -> tuple[float, float]:
        cx, cy = self.points.mean(axis=0)
        return float(cx), float(cy)

    @property
    def extent(self) -> float:
        x1, y1, x2, y2 = bbox(self.points)
        return max(x2 - x1, y2 - y1)


def group_strokes(strokes: Sequence[Stroke], thickness: float) -> list[Symbol]:
    """Union-find des traits en contact. L'ordre des symboles suit le premier trait."""
    clouds = [densify(stroke, max(0.5, thickness / 4.0)) for stroke in strokes]
    boxes = [bbox(cloud) for cloud in clouds]
    parent = list(range(len(strokes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(strokes)):
        for j in range(i + 1, len(strokes)):
            a, b = boxes[i], boxes[j]
            if (a[0] - thickness > b[2] or b[0] - thickness > a[2]
                    or a[1] - thickness > b[3] or b[1] - thickness > a[3]):
                continue
            if min_distance(clouds[i], clouds[j]) <= thickness:
                parent[find(j)] = find(i)

    groups: dict[int, list[int]] = {}
    for i in range(len(strokes)):
        groups.setdefault(find(i), []).append(i)
    return [
        Symbol(
            strokes=[list(strokes[i]) for i in members],
            points=np.concatenate([clouds[i] for i in members]),
            stroke_indices=members,
        )
        for members in groups.values()
    ]
