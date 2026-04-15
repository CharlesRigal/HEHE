"""
symbol_rules.py — Système émergent à base géométrique.

Une seule règle universelle : rule_geometric.
Aucun symbole n'a de sémantique hardcodée.
Toutes les propriétés émergent de la géométrie brute du tracé.

PropertyTag.axis  : axe de la propriété
PropertyTag.scope : portée ("self" | "parent" | "children")

Domains / axes disponibles :
  energy : compression, spread, element
  motion : velocity, direction
  space  : axis, elongation
  time   : duration, chaos
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode


# ---------------------------------------------------------------------------
# Types de base
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PropertyTag:
    domain: str   # "energy" | "motion" | "space" | "time"
    axis: str     # "compression" | "spread" | "velocity" | "direction" | ...
    scope: str    # "self" | "parent" | "children"


@dataclass
class PropertyEntry:
    tag: PropertyTag
    value: float
    weight: float
    source_node_id: str


class PropertyBag:
    def __init__(self) -> None:
        self.entries: list[PropertyEntry] = []

    def add(self, tag: PropertyTag, value: float, weight: float, source_node_id: str) -> None:
        self.entries.append(PropertyEntry(tag=tag, value=value, weight=weight, source_node_id=source_node_id))

    def query(self, domain: str, axis: str = "*") -> list[PropertyEntry]:
        return [
            e for e in self.entries
            if e.tag.domain == domain and (axis == "*" or e.tag.axis == axis)
        ]

    def net(self, domain: str, axis: str) -> float:
        return sum(
            e.value * e.weight
            for e in self.entries
            if e.tag.domain == domain and e.tag.axis == axis
        )

    def merge(self, other: "PropertyBag") -> "PropertyBag":
        merged = PropertyBag()
        merged.entries = list(self.entries) + list(other.entries)
        return merged

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        return f"PropertyBag({len(self.entries)} entries)"


@dataclass
class ResolutionContext:
    node: Any
    depth: int
    child_bags: list[PropertyBag]

    @staticmethod
    def empty(node: Any, tree: Any = None) -> "ResolutionContext":
        return ResolutionContext(
            node=node,
            depth=getattr(node, "depth", 0),
            child_bags=[],
        )


class SymbolRule(Protocol):
    def __call__(self, node: "ASTNode", ctx: ResolutionContext) -> PropertyBag: ...


# ---------------------------------------------------------------------------
# Règle géométrique universelle
# ---------------------------------------------------------------------------

def rule_geometric(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    Règle émergente unique. Toutes les propriétés viennent de la géométrie.

    Features attendues dans node.drawing_features (extraites par ast_builder) :
        compactness   [0,1]  — rondeur  (4π·A / P²)
        elongation    [1,∞]  — étirement (ratio PCA major/minor)
        closure       [0,1]  — fermeture (1=cycle fermé)
        linearity     [0,1]  — droiture  (dist_endpoints / périmètre)
        angularity    [0,1]  — densité de coins aigus
        area_n        [0,1]  — aire normalisée
        scale_n       [0,1]  — échelle (max(area_n, perimeter_n × 0.5))
        direction_n   [0,1]  — angle principal / 360°
        convexity     [0,1]  — fraction de virages cohérents
        is_directional [0,1] — 1 si la forme a une tête directionnelle (flèche)
        confidence    [0,1]  — confiance de la reconnaissance
    """
    bag = PropertyBag()
    nid = node.node_id
    f = node.drawing_features

    compactness    = float(f.get("compactness",    0.5))
    elongation     = max(1.0, float(f.get("elongation",    1.0)))
    closure        = float(f.get("closure",        0.0))
    linearity      = float(f.get("linearity",      0.0))
    angularity     = float(f.get("angularity",     0.3))
    area_n         = float(f.get("area_n",         0.2))
    scale_n        = float(f.get("scale_n",        area_n))
    direction_n    = float(f.get("direction_n",    0.0))
    convexity      = float(f.get("convexity",      0.8))
    is_directional = float(f.get("is_directional", 0.0))
    conf           = float(f.get("confidence",     1.0))

    # scope : "self" si nœud racine (cercle exécuteur), "parent" sinon
    scope = "self" if ctx.depth == 0 else "parent"

    # facteur d'étirement normalisé [0, 1)
    elonga_n = (elongation - 1.0) / elongation

    # poids de base : taille × confiance
    w = scale_n * conf + 0.05

    # ── Compression (énergie focalisée) ────────────────────────────────────
    # Anguleux × non-rond × allongé → focalisation static
    angular_cmp = angularity * (1.0 - compactness) * (1.0 + elonga_n)
    # Linéaire × allongé × NON directionnel → énergie statique comprimée (mur)
    static_cmp = linearity * elonga_n * (1.0 - is_directional) * 2.0
    compression = angular_cmp + static_cmp
    bag.add(PropertyTag("energy", "compression", scope), compression, w, nid)

    # ── Spread (diffusion spatiale) ────────────────────────────────────────
    # Rond × fermé × grand → énergie étalée
    spread = compactness * closure * area_n
    if spread > 0.01:
        bag.add(PropertyTag("energy", "spread", scope), spread, conf, nid)

    # ── Vélocité + direction ───────────────────────────────────────────────
    # Linéaire × allongé × directionnel → mouvement
    velocity = linearity * elonga_n * is_directional
    if velocity > 0.02:
        bag.add(PropertyTag("motion", "velocity", scope), velocity, w, nid)
        bag.add(PropertyTag("motion", "direction", scope), direction_n, conf, nid)

    # ── Durée (persistance) ────────────────────────────────────────────────
    # Fermé × grand → sort persistant
    if closure > 0.4:
        bag.add(PropertyTag("time", "duration", scope), closure * area_n, conf, nid)

    # ── Chaos (instabilité) ────────────────────────────────────────────────
    # Non-convexe × anguleux → sort instable
    chaos = (1.0 - convexity) * angularity
    if chaos > 0.05:
        bag.add(PropertyTag("time", "chaos", scope), chaos, conf, nid)

    # ── Axe spatial (orientation dominante) ───────────────────────────────
    if elongation > 1.3:
        bag.add(PropertyTag("space", "axis",       scope), direction_n, elonga_n * conf, nid)
        bag.add(PropertyTag("space", "elongation", scope), elongation,  conf,            nid)

    # ── Signature élémentaire (émergente) ─────────────────────────────────
    element_val = _element_from_geometry(angularity, linearity, compactness, closure, is_directional)
    bag.add(PropertyTag("energy", "element", scope), element_val, scale_n * 0.5 + 0.15, nid)

    return bag


def _element_from_geometry(
    angularity: float,
    linearity: float,
    compactness: float,
    closure: float,
    is_directional: float,
) -> float:
    """
    Projection géométrique → valeur élémentaire continue [0, 1].

    Géométrie  →  élément attendu
    ─────────────────────────────────────────────────────────────────────
    anguleux + ouvert          → feu      (1.0) : flamme, chaotique
    linéaire + directionnel    → foudre   (0.75): arc, précis, rapide
    linéaire + non-directionnel→ arcane   (0.55): neutre stable
    compact + fermé + lisse    → glace    (0.1) : cristal, contenu
    """
    # chaleur : anguleux + ouvert = instable = feu
    heat = angularity * (1.0 - closure)
    # précision : linéaire + directionnel = foudre
    precision = linearity * is_directional * (1.0 - angularity * 0.4)
    # axe neutre : linéaire + non-directionnel = arcane
    arcane = linearity * (1.0 - is_directional) * (1.0 - angularity)
    # froid : compact + fermé + lisse = glace
    cold = compactness * closure * (1.0 - angularity)

    val = 0.5 + heat * 0.5 + precision * 0.25 + arcane * 0.05 - cold * 0.4
    return max(0.0, min(1.0, val))