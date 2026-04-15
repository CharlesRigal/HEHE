"""
symbol_registry.py — Registre des règles de résolution.

Une seule règle : rule_geometric.
Elle est enregistrée pour tous les types connus et sert de fallback universel.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from client.magic.ast.symbol_rules import (
    PropertyBag,
    ResolutionContext,
    SymbolRule,
    rule_geometric,
)

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode


def _rule_neutral(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """Nœud virtuel (root) : bag vide, zéro effet."""
    return PropertyBag()


class SymbolRegistry:
    """
    Registre extensible : symbol_type -> SymbolRule.
    Toutes les primitives utilisent rule_geometric par défaut.
    Extensible sans modifier ce fichier via register().
    """

    def __init__(self) -> None:
        self._rules: dict[str, SymbolRule] = {}
        self._register_defaults()

    def register(self, symbol_type: str, rule: SymbolRule) -> None:
        self._rules[symbol_type] = rule

    def get(self, symbol_type: str) -> SymbolRule:
        # "root" = nœud virtuel -> neutre
        if symbol_type == "root":
            return _rule_neutral
        # Tout autre symbole -> règle géométrique universelle
        return self._rules.get(symbol_type, rule_geometric)

    def _register_defaults(self) -> None:
        for symbol_type in ("circle", "arrow", "arrow_with_base", "triangle",
                             "segment", "zigzag", "rune_fire"):
            self._rules[symbol_type] = rule_geometric

    @property
    def registered_types(self) -> list[str]:
        return list(self._rules.keys())


# Singleton global
REGISTRY = SymbolRegistry()


# ---------------------------------------------------------------------------
# Test de validation
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.ast.ast import ASTNode
    from client.magic.ast.symbol_rules import PropertyTag

    # Simuler un nœud avec des features géométriques typiques d'un cercle
    circle_node = ASTNode(
        node_id="test_circle",
        symbol_type="circle",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        drawing_features={
            "compactness": 0.95, "elongation": 1.05, "closure": 0.98,
            "linearity": 0.01, "angularity": 0.0, "area_n": 0.5,
            "scale_n": 0.7, "direction_n": 0.0, "convexity": 1.0,
            "is_directional": 0.0, "confidence": 1.0,
        },
    )
    ctx = ResolutionContext(node=circle_node, depth=0, child_bags=[])
    bag = REGISTRY.get("circle")(circle_node, ctx)

    # Cercle : spread > 0, velocity = 0
    spread = bag.net("energy", "spread")
    velocity = bag.net("motion", "velocity")
    assert spread > 0, f"Circle should have spread, got {spread}"
    assert velocity == 0.0, f"Circle should have no velocity, got {velocity}"
    print(f"[PASS] circle: spread={spread:.3f} velocity={velocity:.3f}")

    # Simuler une flèche
    arrow_node = ASTNode(
        node_id="test_arrow",
        symbol_type="arrow",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        drawing_features={
            "compactness": 0.0, "elongation": 10.0, "closure": 0.0,
            "linearity": 1.0, "angularity": 0.0, "area_n": 0.0,
            "scale_n": 0.15, "direction_n": 0.0, "convexity": 1.0,
            "is_directional": 1.0, "confidence": 1.0,
        },
    )
    ctx_arrow = ResolutionContext(node=arrow_node, depth=0, child_bags=[])
    bag_arrow = REGISTRY.get("arrow")(arrow_node, ctx_arrow)

    velocity_arrow = bag_arrow.net("motion", "velocity")
    compression_arrow = bag_arrow.net("energy", "compression")
    assert velocity_arrow > 0, f"Arrow should have velocity, got {velocity_arrow}"
    assert compression_arrow == 0.0, f"Arrow should have no compression (no angularity, directional), got {compression_arrow}"
    print(f"[PASS] arrow: velocity={velocity_arrow:.3f} compression={compression_arrow:.3f}")

    # Simuler un segment (non-directionnel, statique)
    seg_node = ASTNode(
        node_id="test_segment",
        symbol_type="segment",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        drawing_features={
            "compactness": 0.0, "elongation": 8.0, "closure": 0.0,
            "linearity": 1.0, "angularity": 0.0, "area_n": 0.0,
            "scale_n": 0.12, "direction_n": 0.25, "convexity": 1.0,
            "is_directional": 0.0, "confidence": 1.0,
        },
    )
    ctx_seg = ResolutionContext(node=seg_node, depth=0, child_bags=[])
    bag_seg = REGISTRY.get("segment")(seg_node, ctx_seg)

    velocity_seg = bag_seg.net("motion", "velocity")
    compression_seg = bag_seg.net("energy", "compression")
    assert velocity_seg == 0.0, f"Segment should have no velocity, got {velocity_seg}"
    assert compression_seg > 0, f"Segment should have compression (static_cmp), got {compression_seg}"
    print(f"[PASS] segment: velocity={velocity_seg:.3f} compression={compression_seg:.3f}")

    # Symbole inconnu -> rule_geometric (pas neutre)
    bag_unknown = REGISTRY.get("new_symbol")(circle_node, ctx)
    assert len(bag_unknown) > 0, "Unknown symbol should still use rule_geometric"
    print("[PASS] unknown symbol -> rule_geometric (not neutral)")

    # Nœud root virtuel -> neutre
    root_node = ASTNode(node_id="root_v", symbol_type="root", primitive=None,
                        depth=-1, ordinal=0, sibling_count=1)
    ctx_root = ResolutionContext(node=root_node, depth=-1, child_bags=[])
    bag_root = REGISTRY.get("root")(root_node, ctx_root)
    assert len(bag_root) == 0
    print("[PASS] root node -> empty bag")

    print("\nAll symbol_registry assertions passed.")
