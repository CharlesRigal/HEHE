"""Reconnaisseur $P (Vatavu, Anthony, Wobbrock, ICMI 2012), vectorise.

$P compare des nuages de points : il ignore l'ordre et le sens des traits,
donc accepte les glyphes multi-traits. Il normalise position et echelle,
pas la rotation.

Pour les signes, un balayage de rotation teste le candidat a plusieurs
angles : le meilleur angle donne l'orientation du signe (README L6). Chaque
template annote sa base et sa tete ; l'axe base -> tete, tourne du meilleur
angle, donne le sens. F0 : si le score a l'angle oppose est presque aussi
bon, base et tete sont indistinguables et le signe meurt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from client.magic.geometry import Stroke, path_length, resample

N_POINTS = 32
# Distance moyenne ponderee (unites de boite normalisee) qui donne un score nul.
SCORE_ZERO_DISTANCE = 0.3
COARSE_STEP = math.radians(10.0)
FINE_STEP = math.radians(2.0)


def cloud(strokes: Sequence[Stroke], n: int = N_POINTS) -> np.ndarray:
    """Nuage de `n` points repartis sur les traits en proportion de leur longueur."""
    lengths = [max(path_length(s), 1e-6) for s in strokes]
    total = sum(lengths)
    counts = [max(1, round(n * length / total)) for length in lengths]
    while sum(counts) > n:
        counts[counts.index(max(counts))] -= 1
    while sum(counts) < n:
        counts[counts.index(max(counts))] += 1
    return np.concatenate([resample(s, c) for s, c in zip(strokes, counts)])


def _normalize(points: np.ndarray) -> np.ndarray:
    """Centre au centroide, echelle unitaire (plus grand cote de la boite)."""
    centered = points - points.mean(axis=-2, keepdims=True)
    extent = (centered.max(axis=-2) - centered.min(axis=-2)).max(axis=-1)
    return centered / np.maximum(extent, 1e-9)[..., None, None]


def _rotate(points: np.ndarray, angles: np.ndarray) -> np.ndarray:
    """(n, 2) tourne de chaque angle -> (A, n, 2). Repere ecran (y en bas)."""
    c, s = np.cos(angles)[:, None], np.sin(angles)[:, None]
    x, y = points[None, :, 0], points[None, :, 1]
    return np.stack([x * c - y * s, x * s + y * c], axis=-1)


def _greedy(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance $P de a vers b, minimisee sur les points de depart. a, b : (B, n, 2)."""
    batch, n, _ = a.shape
    dist = np.sqrt(((a[:, :, None, :] - b[:, None, :, :]) ** 2).sum(-1))   # (B, n, n)
    step = max(1, int(math.floor(n ** 0.5)))
    starts = np.arange(0, n, step)
    best = np.full(batch, np.inf)
    rows = np.arange(batch)
    for start in starts:
        matched = np.zeros((batch, n), dtype=bool)
        total = np.zeros(batch)
        for k in range(n):
            i = (start + k) % n
            row = np.where(matched, np.inf, dist[:, i, :])
            j = row.argmin(axis=1)
            total += (1.0 - k / n) * row[rows, j]
            matched[rows, j] = True
        best = np.minimum(best, total)
    return best


def _distance(candidate: np.ndarray, template: np.ndarray) -> np.ndarray:
    """Distance symetrique moyenne ; candidate (B, n, 2), template (n, 2)."""
    t = np.broadcast_to(template, candidate.shape)
    weight_sum = sum(1.0 - k / candidate.shape[1] for k in range(candidate.shape[1]))
    return np.minimum(_greedy(candidate, t), _greedy(t, candidate)) / weight_sum


def score_of(distance: float) -> float:
    return max(0.0, 1.0 - distance / SCORE_ZERO_DISTANCE)


@dataclass
class Template:
    label: str
    points: np.ndarray                     # nuage normalise
    head: np.ndarray | None = None         # tete et base, dans le repere du glyphe brut
    base: np.ndarray | None = None

    @classmethod
    def from_strokes(cls, label: str, strokes: Sequence[Stroke],
                     head: tuple[float, float] | None = None,
                     base: tuple[float, float] | None = None) -> "Template":
        return cls(
            label=label,
            points=_normalize(cloud(strokes)),
            head=None if head is None else np.asarray(head, dtype=float),
            base=None if base is None else np.asarray(base, dtype=float),
        )

    @property
    def axis_angle(self) -> float:
        """Angle de l'axe base -> tete dans le repere du template."""
        if self.head is None or self.base is None:
            return 0.0
        dx, dy = self.head - self.base
        return math.atan2(dy, dx)


@dataclass
class Match:
    label: str
    score: float
    orientation: float = 0.0       # angle base -> tete du candidat (repere ecran)
    flip_score: float = 0.0        # score au meme template tourne de 180°


def recognize(strokes: Sequence[Stroke], templates: Sequence[Template]) -> Match | None:
    """Sans rotation : pour les emblèmes, dessines droits (la page est une carte)."""
    candidate = _normalize(cloud(strokes))[None]
    best: Match | None = None
    for template in templates:
        score = score_of(float(_distance(candidate, template.points)[0]))
        if best is None or score > best.score:
            best = Match(template.label, score)
    return best


def recognize_oriented(strokes: Sequence[Stroke], templates: Sequence[Template]) -> Match | None:
    """Avec balayage de rotation : pour les signes. Renvoie l'orientation trouvee."""
    raw = cloud(strokes)
    raw = raw - raw.mean(axis=0)
    best: Match | None = None
    for template in templates:
        coarse = np.arange(0.0, 2 * math.pi, COARSE_STEP)
        dist = _distance(_normalize(_rotate(raw, coarse)), template.points)
        phi0 = float(coarse[int(dist.argmin())])
        fine = phi0 + np.arange(-COARSE_STEP, COARSE_STEP + 1e-9, FINE_STEP)
        fine_dist = _distance(_normalize(_rotate(raw, fine)), template.points)
        phi = float(fine[int(fine_dist.argmin())])
        score = score_of(float(fine_dist.min()))
        flip = score_of(float(_distance(_normalize(_rotate(raw, np.array([phi + math.pi]))), template.points)[0]))
        if best is None or score > best.score:
            # Le candidat tourne de phi ressemble au template : son axe est
            # celui du template, tourne de -phi.
            orientation = math.atan2(math.sin(template.axis_angle - phi), math.cos(template.axis_angle - phi))
            best = Match(template.label, score, orientation, flip)
    return best
