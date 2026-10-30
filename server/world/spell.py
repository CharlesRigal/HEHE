"""Sort actif : un pentacle lu par le client, pose comme champ sur la grille.

Message reseau (README, L7) :

  {"t": "s", "R": 120.0, "q": 0.93, "e": "water", "eq": 0.88,
   "signs": [{"k": "traction", "r": 0.8, "a": 1.57, "o": -1.57, "s": 0.25, "q": 0.9}, ...]}

  R  : rayon du cercle (px) = rayon de la zone (C3)
  q  : qualite du cercle ; eq : score de l'emblème
  e  : element de l'emblème (E1)
  signs[*] : k type, r distance au centre / R, a angle de position,
             o orientation base -> tete, s taille / R, q qualite
             (angles en radians, repere de la page : x a droite, y en bas)

Le centre est la position du mage a la fermeture du cercle (S1) ; le serveur
la prend sur le joueur, pas dans le message.

Champ (F1, F5, F6) : chaque signe pose un noyau sur la zone, a la meme
distance relative du centre. Les composantes sont exprimees dans le repere
du centre (radiale, tangentielle) puis remises dans le repere de chaque
cellule : trois tractions vers le centre aspirent tout l'anneau.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from server.world.grid import ELEMENT_FIELD, Flow, WorldGrid


SIGN_KINDS = ("direction", "traction", "convergence", "suspension", "column", "repetition")

R_REF = 100.0                 # rayon de reference : puissance 1
CREATE_PER_AREA = 0.0008      # quantite creee par px² de cercle (E4)
CREATE_RADIUS = 0.3           # disque de creation, en fraction de R
FLOW_SPEED = 120.0            # px/s pour un signe plein a puissance 1
COLUMN_SPEED_FACTOR = 2.0
BASE_DURATION = 3.0           # s, prolongee localement par la repetition
TRACTION_CATCHMENT = 2.0      # la traction attire jusqu'a 2 R (E4)
MIN_RADIAL_SIGMA = 0.08
MIN_ANGULAR_SIGMA = 0.25


@dataclass
class SignSpec:
    kind: str
    r: float
    angle: float
    orientation: float
    size: float
    quality: float

    def radial_frame(self) -> tuple[float, float]:
        """Orientation decomposee au point du signe : (radiale, tangentielle)."""
        ox, oy = math.cos(self.orientation), math.sin(self.orientation)
        rx, ry = math.cos(self.angle), math.sin(self.angle)
        return ox * rx + oy * ry, -ox * ry + oy * rx


@dataclass
class SpellSpec:
    radius: float
    circle_quality: float
    element: str
    emblem_quality: float
    signs: list[SignSpec] = field(default_factory=list)

    @property
    def power(self) -> float:
        """C3 : la surface du cercle donne la puissance ; la qualite la multiplie."""
        return (self.radius / R_REF) ** 2 * self.circle_quality * self.emblem_quality


def _num(raw: dict, key: str, default: float | None = None) -> float:
    value = raw.get(key, default)
    if value is None:
        raise ValueError(f"missing {key}")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"bad {key}")
    return value


def parse_spell_message(msg: dict) -> SpellSpec:
    """Valide un message `s`. Leve ValueError si le sort est inerte ou malforme."""
    element = msg.get("e")
    if element not in ELEMENT_FIELD:
        raise ValueError("no valid emblem: spell is inert (E3)")
    radius = _num(msg, "R")
    if radius <= 0.0:
        raise ValueError("bad radius")
    signs = []
    for raw in msg.get("signs") or []:
        if not isinstance(raw, dict) or raw.get("k") not in SIGN_KINDS:
            continue
        signs.append(SignSpec(
            kind=raw["k"],
            r=max(0.0, _num(raw, "r")),
            angle=_num(raw, "a"),
            orientation=_num(raw, "o"),
            size=max(0.01, _num(raw, "s", 0.2)),
            quality=min(1.0, max(0.0, _num(raw, "q", 1.0))),
        ))
    return SpellSpec(
        radius=radius,
        circle_quality=min(1.0, max(0.0, _num(msg, "q", 1.0))),
        element=str(element),
        emblem_quality=min(1.0, max(0.0, _num(msg, "eq", 1.0))),
        signs=signs,
    )


class ActiveSpell:
    """Champ d'un sort pose sur la grille. Les poids sont calcules une fois."""

    def __init__(self, spec: SpellSpec, x: float, y: float, grid: WorldGrid, owner: str = "") -> None:
        self.spec = spec
        self.x = float(x)
        self.y = float(y)
        self.owner = owner
        self.age = 0.0
        self.field_name, self.element_sign = ELEMENT_FIELD[spec.element]
        self._build_field(grid)
        # E4 : l'emblème cree son element au centre, en proportion de la surface.
        created = CREATE_PER_AREA * math.pi * spec.radius ** 2 * spec.circle_quality * spec.emblem_quality
        grid.add_disc(self.field_name, self.x, self.y, CREATE_RADIUS * spec.radius, self.element_sign * created)

    @property
    def duration(self) -> float:
        return float(self.cell_duration.max(initial=BASE_DURATION))

    def is_over(self) -> bool:
        return self.age >= self.duration

    def _build_field(self, grid: WorldGrid) -> None:
        spec = self.spec
        R = spec.radius
        dx = (grid.center_x - self.x) / R
        dy = (grid.center_y - self.y) / R
        r = np.hypot(dx, dy)
        theta = np.arctan2(dy, dx)
        safe_r = np.where(r > 1e-9, r, 1.0)
        er_x, er_y = np.where(r > 1e-9, dx / safe_r, 0.0), np.where(r > 1e-9, dy / safe_r, 0.0)
        inside = r <= 1.0

        u_r = np.zeros(r.shape)        # vitesse radiale (+ vers l'exterieur)
        u_t = np.zeros(r.shape)        # vitesse tangentielle
        hold = np.zeros(r.shape)
        repetition = np.zeros(r.shape)

        for sign in spec.signs:
            radial, tangential = sign.radial_frame()
            sigma_r = max(MIN_RADIAL_SIGMA, sign.size * 0.5)
            sigma_t = max(MIN_ANGULAR_SIGMA, sign.size / max(sign.r, 0.2) * 1.5)
            if sign.kind == "column":
                sigma_t *= 0.5
            d_theta = np.angle(np.exp(1j * (theta - sign.angle)))
            angular = np.exp(-d_theta ** 2 / (2 * sigma_t ** 2))
            d_r = r - sign.r
            band = np.exp(-d_r ** 2 / (2 * sigma_r ** 2))
            if sign.kind == "traction":
                # Bassin de captation : tout l'exterieur jusqu'a 2 R est attire.
                band = np.where((d_r > 0) & (r <= TRACTION_CATCHMENT), 1.0, band)
                weight = band * angular * sign.quality
                weight = np.where(r <= TRACTION_CATCHMENT, weight, 0.0)
            elif sign.kind == "convergence":
                # La convergence agit de sa bande jusqu'au centre : elle resserre
                # tout l'interieur (et l'etale vers sa bande quand elle est retournee).
                band = np.where(d_r < 0, 1.0, band)
                weight = np.where(inside, band * angular * sign.quality, 0.0)
            else:
                weight = np.where(inside, band * angular * sign.quality, 0.0)

            if sign.kind in ("direction", "traction"):
                u_r += weight * radial
                u_t += weight * tangential
            elif sign.kind == "column":
                u_r += weight * radial * COLUMN_SPEED_FACTOR
                u_t += weight * tangential * COLUMN_SPEED_FACTOR
            elif sign.kind == "convergence":
                # Une seule echelle signee : tete vers le centre = compresser,
                # vers l'exterieur = etaler (README F6).
                u_r += weight * radial
            elif sign.kind == "suspension":
                hold = np.maximum(hold, weight)
            elif sign.kind == "repetition":
                repetition += weight

        speed = FLOW_SPEED * spec.power
        self.vx = speed * (u_r * er_x - u_t * er_y)
        self.vy = speed * (u_r * er_y + u_t * er_x)
        self.hold = np.clip(hold, 0.0, 1.0)
        self.cell_duration = BASE_DURATION * (1.0 + repetition)
        reach = TRACTION_CATCHMENT if any(s.kind == "traction" for s in spec.signs) else 1.0
        self.area = r <= reach

    def flow(self) -> Flow:
        """Champ actif a l'age courant : chaque cellule s'eteint a sa duree (Repetition)."""
        alive = (self.cell_duration > self.age) & self.area
        return Flow(
            vx=np.where(alive, self.vx, 0.0),
            vy=np.where(alive, self.vy, 0.0),
            hold=np.where(alive, self.hold, 0.0),
        )

    def advance(self, dt: float) -> None:
        self.age += dt

    def public_state(self) -> dict:
        return {
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "R": round(self.spec.radius, 1),
            "e": self.spec.element,
            "left": round(max(0.0, self.duration - self.age), 2),
        }


def combine_flows(grid: WorldGrid, spells: list[ActiveSpell]) -> dict[str, Flow]:
    """Somme des champs par grandeur. Un sort ne touche que son element (principe 5)."""
    flows: dict[str, Flow] = {}
    for spell in spells:
        flow = spell.flow()
        current = flows.get(spell.field_name)
        if current is None:
            flows[spell.field_name] = flow
        else:
            current.vx = current.vx + flow.vx
            current.vy = current.vy + flow.vy
            current.hold = np.maximum(current.hold, flow.hold)
    return flows
