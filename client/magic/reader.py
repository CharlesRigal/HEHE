"""Lecture d'un pentacle (README, « Lecture du dessin » et « Qualite du trace »).

  traits -> symboles par contact (L2-L4)
         -> cercle = plus grande boucle fermee et ronde (C1, L5)
         -> hors du cercle : ignore (C2)
         -> emblème = symbole le plus proche du centre ($P, sans rotation)
         -> signes = les autres ($P avec balayage de rotation, F0)
         -> mesures relatives au centre du cercle (F1)

La lecture ne se fait qu'une fois le cercle ferme (L1). Un symbole sous son
seuil est mort : il reste visible mais ne compte pas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from client.magic.circle import find_circle
from client.magic.dollar_p import Template, recognize, recognize_oriented
from client.magic.geometry import Stroke, path_length
from client.magic.grouping import Symbol, group_strokes
from client.magic.templates import emblem_templates, sign_templates

EMBLEM_MIN_SCORE = 0.6
SIGN_MIN_SCORE = 0.75          # seuil tres haut (README L6)
F0_MIN_MARGIN = 0.08           # ecart minimal entre l'angle trouve et l'angle oppose


@dataclass
class EmblemReading:
    element: str
    score: float
    alive: bool


@dataclass
class SignReading:
    kind: str
    r: float                   # distance au centre / R
    angle: float               # angle de position (repere ecran)
    orientation: float         # angle base -> tete (repere ecran)
    size: float                # etendue / R
    score: float
    alive: bool
    reason: str = ""


@dataclass
class PentacleReading:
    center: tuple[float, float]
    radius: float
    circle_quality: float
    emblem: EmblemReading | None
    signs: list[SignReading] = field(default_factory=list)
    ignored: int = 0           # symboles hors du cercle
    ink: float = 0.0           # longueur totale tracee (S3)

    @property
    def is_inert(self) -> bool:
        """E3 : sans emblème valide, rien."""
        return self.emblem is None or not self.emblem.alive


class PentacleReader:
    def __init__(
        self,
        emblems: Sequence[Template] | None = None,
        signs: Sequence[Template] | None = None,
    ) -> None:
        self.emblems = list(emblems) if emblems is not None else emblem_templates()
        self.signs = list(signs) if signs is not None else sign_templates()

    @staticmethod
    def circle_closed(strokes: Sequence[Stroke], thickness: float) -> bool:
        """Test leger appele apres chaque trait : le cercle vient-il de se fermer ?"""
        return find_circle(group_strokes(strokes, thickness), thickness) is not None

    def read(self, strokes: Sequence[Stroke], thickness: float) -> PentacleReading | None:
        """None tant qu'aucun cercle n'est ferme (C1)."""
        symbols = group_strokes(strokes, thickness)
        found = find_circle(symbols, thickness)
        if found is None:
            return None
        circle, loop = found
        cx, cy = loop.center
        radius = loop.radius
        inside: list[tuple[float, Symbol]] = []
        ignored = 0
        for symbol in symbols:
            if symbol is circle:
                continue
            sx, sy = symbol.centroid
            distance = math.hypot(sx - cx, sy - cy)
            if distance >= radius:
                ignored += 1
                continue
            inside.append((distance, symbol))

        reading = PentacleReading(
            center=(cx, cy),
            radius=radius,
            circle_quality=loop.quality,
            emblem=None,
            ignored=ignored,
            ink=sum(path_length(s) for s in strokes),
        )
        if not inside:
            return reading

        inside.sort(key=lambda item: item[0])
        _, emblem_symbol = inside[0]
        match = recognize(emblem_symbol.strokes, self.emblems)
        if match is not None:
            reading.emblem = EmblemReading(match.label, match.score, match.score >= EMBLEM_MIN_SCORE)

        for distance, symbol in inside[1:]:
            reading.signs.append(self._read_sign(symbol, distance, (cx, cy), radius))
        return reading

    def _read_sign(self, symbol: Symbol, distance: float, center: tuple[float, float], radius: float) -> SignReading:
        sx, sy = symbol.centroid
        match = recognize_oriented(symbol.strokes, self.signs)
        sign = SignReading(
            kind=match.label if match else "",
            r=distance / radius,
            angle=math.atan2(sy - center[1], sx - center[0]),
            orientation=match.orientation if match else 0.0,
            size=symbol.extent / radius,
            score=match.score if match else 0.0,
            alive=True,
        )
        if match is None or match.score < SIGN_MIN_SCORE:
            sign.alive, sign.reason = False, "score"
        elif match.score - match.flip_score < F0_MIN_MARGIN:
            sign.alive, sign.reason = False, "base/tete"
        return sign
