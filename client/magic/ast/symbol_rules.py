from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode, SpellAST


# ---------------------------------------------------------------------------
# Types de base
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PropertyTag:
    domain: str   # "energy" | "space" | "time" | "motion" | "polarity"
    name:   str   # "compression" | "spread" | "axis" | "velocity" | "direction" | etc.
    target: str   # "self" | "parent" | "children"


@dataclass
class PropertyEntry:
    tag: PropertyTag
    value: float
    weight: float          # force de la contribution (0.0 a N)
    source_node_id: str


class PropertyBag:
    def __init__(self) -> None:
        self.entries: list[PropertyEntry] = []

    def add(self, tag: PropertyTag, value: float, weight: float, source_node_id: str) -> None:
        self.entries.append(PropertyEntry(tag=tag, value=value, weight=weight, source_node_id=source_node_id))

    def query(self, domain: str, name: str = "*") -> list[PropertyEntry]:
        """Retourne les entries qui matchent (name='*' = wildcard)."""
        results: list[PropertyEntry] = []
        for e in self.entries:
            if e.tag.domain != domain:
                continue
            if name != "*" and e.tag.name != name:
                continue
            results.append(e)
        return results

    def net(self, domain: str, name: str) -> float:
        """Somme ponderee : sum(entry.value * entry.weight) pour les entries matchantes."""
        total = 0.0
        for e in self.entries:
            if e.tag.domain == domain and e.tag.name == name:
                total += e.value * e.weight
        return total

    def merge(self, other: PropertyBag) -> PropertyBag:
        """Fusionne deux bags, retourne un nouveau bag avec toutes les entries."""
        merged = PropertyBag()
        merged.entries = list(self.entries) + list(other.entries)
        return merged

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        return f"PropertyBag({len(self.entries)} entries)"


# ---------------------------------------------------------------------------
# Contexte de resolution (nouvelle API)
# ---------------------------------------------------------------------------

@dataclass
class ResolutionContext:
    node:       Any                   # ASTNode
    depth:      int
    child_bags: list[PropertyBag]     # bags des enfants deja resolus (pass bottom-up)

    @staticmethod
    def empty(node: Any, tree: Any = None) -> ResolutionContext:
        """Cree un contexte vide, utile pour les tests."""
        return ResolutionContext(
            node=node,
            depth=getattr(node, "depth", 0),
            child_bags=[],
        )


# ---------------------------------------------------------------------------
# Protocole SymbolRule
# ---------------------------------------------------------------------------

class SymbolRule(Protocol):
    def __call__(self, node: ASTNode, ctx: ResolutionContext) -> PropertyBag: ...


# ---------------------------------------------------------------------------
# Regles par symbole — emission de compression et proprietes associees
#
# Principe : AUCUN tag "behavior" ici.
# Le comportement EMERGE dans le resolver a partir des valeurs continues.
# ---------------------------------------------------------------------------

def rule_circle(node: ASTNode, ctx: ResolutionContext) -> PropertyBag:
    bag = PropertyBag()
    nid = node.node_id
    radius = node.drawing_features.get("radius_normalized", 0.5)

    # Faible compression — le cercle ne resiste pas, il contient
    bag.add(PropertyTag("energy", "compression", "self"), 0.2, 1.0, nid)

    # Echelle spatiale
    bag.add(PropertyTag("space", "scale", "self"), radius, 1.0, nid)

    # Un cercle seul (sans enfants) cree une zone persistante
    if not ctx.child_bags:
        bag.add(PropertyTag("space", "spread", "self"), radius * 0.8, 1.0, nid)
        bag.add(PropertyTag("time", "fade_rate", "self"), 0.6, 1.0, nid)

    return bag


def rule_arrow(node: ASTNode, ctx: ResolutionContext) -> PropertyBag:
    bag = PropertyBag()
    nid = node.node_id
    length = node.drawing_features.get("length_normalized", 0.5)
    dir_x = node.drawing_features.get("direction_x", 1.0)
    dir_y = node.drawing_features.get("direction_y", 0.0)
    angle_deg = math.degrees(math.atan2(dir_y, dir_x)) % 360.0

    # Dans tous les cas : contribue direction + vélocité au parent (ou à soi si depth=0)
    # Seul un cercle parent peut activer le sort — la flèche seule ne cast rien.
    target = "self" if ctx.depth == 0 else "parent"
    bag.add(PropertyTag("motion", "direction", target), angle_deg / 360.0, 1.0, nid)
    bag.add(PropertyTag("motion", "velocity", target), length * 0.5, 1.0, nid)

    return bag


def rule_triangle(node: ASTNode, ctx: ResolutionContext) -> PropertyBag:
    bag = PropertyBag()
    nid = node.node_id
    area_n = node.drawing_features.get("area_normalized", 0.3)
    sharp = node.drawing_features.get("apex_sharpness", 0.5)

    compression = sharp + area_n * 0.5
    spread = math.sqrt(area_n) * (1.0 - sharp * 0.5)

    bag.add(PropertyTag("energy", "compression", "self"), compression, 1.0, nid)
    bag.add(PropertyTag("space", "spread", "self"), spread, 1.0, nid)
    bag.add(PropertyTag("space", "directional", "self"), 1.0, 1.0, nid)

    return bag


def rule_segment(node: ASTNode, ctx: ResolutionContext) -> PropertyBag:
    bag = PropertyBag()
    nid = node.node_id
    depth = ctx.depth
    length = node.drawing_features.get("length_normalized", 0.5)
    angle = node.drawing_features.get("angle_deg", 0.0)

    if depth == 0:
        # Segment standalone : haute compression, forme un mur
        compression = 1.5 + length * 2.0
        elongation = 1.0 + length * 3.0
        angle_norm = angle / 360.0

        bag.add(PropertyTag("energy", "compression", "self"), compression, 1.0, nid)
        bag.add(PropertyTag("space", "axis", "self"), angle_norm, 1.0, nid)
        bag.add(PropertyTag("space", "elongation", "self"), elongation, 1.0, nid)
        bag.add(PropertyTag("time", "duration", "self"), length * 3.0, 1.0, nid)
    else:
        # Segment enfant : donne l'axe directeur au parent
        angle_norm = angle / 360.0
        bag.add(PropertyTag("space", "axis", "parent"), angle_norm, 1.0, nid)

    return bag


def rule_zigzag(node: ASTNode, ctx: ResolutionContext) -> PropertyBag:
    bag = PropertyBag()
    nid = node.node_id
    amplitude = node.drawing_features.get("amplitude", 0.3)
    frequency = node.drawing_features.get("frequency", 0.5)

    bag.add(PropertyTag("time", "chaos", "self"), amplitude, 1.0, nid)
    bag.add(PropertyTag("time", "rate", "self"), frequency, 1.0, nid)

    return bag


def rule_rune_fire(node: ASTNode, ctx: ResolutionContext) -> PropertyBag:
    bag = PropertyBag()
    nid = node.node_id

    bag.add(PropertyTag("energy", "compression", "self"), 0.3, 1.0, nid)
    bag.add(PropertyTag("energy", "element", "self"), 1.0, 1.0, nid)   # 1.0 = fire
    bag.add(PropertyTag("polarity", "unstable", "self"), 1.0, 1.0, nid)
    bag.add(PropertyTag("polarity", "burn", "self"), 1.0, 1.0, nid)

    return bag
