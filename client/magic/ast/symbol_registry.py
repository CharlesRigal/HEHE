"""
symbol_registry.py — Registre des règles de résolution.

Chaque type de primitive est associé à sa règle sémantique dédiée.
rule_geometric reste disponible comme fallback pour les types inconnus.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from client.magic.ast.symbol_rules import (
    PropertyBag,
    ResolutionContext,
    SymbolRule,
    rule_geometric,
    rule_circle,
    rule_arrow,
    rule_arrow_with_base,
    rule_triangle,
    rule_segment,
    rule_zigzag,
    rule_rune_fire,
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
        # Chaque type a sa règle sémantique dédiée
        self._rules["circle"]          = rule_circle
        self._rules["arrow"]           = rule_arrow
        self._rules["arrow_with_base"] = rule_arrow_with_base
        self._rules["triangle"]        = rule_triangle
        self._rules["segment"]         = rule_segment
        self._rules["zigzag"]          = rule_zigzag
        self._rules["rune_fire"]       = rule_rune_fire

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

    def make_node(nid, sym, depth, feats, children=None):
        n = ASTNode(node_id=nid, symbol_type=sym, primitive=None,
                    depth=depth, ordinal=0, sibling_count=1,
                    drawing_features=feats)
        if children:
            n.children = children
        return n

    # ── Cercle → spread + duration, pas de velocity ─────────────────────────
    circle_node = make_node("test_circle", "circle", 0, {
        "compactness": 0.95, "elongation": 1.05, "closure": 0.98,
        "linearity": 0.01, "angularity": 0.0, "area_n": 0.5,
        "scale_n": 0.7, "direction_n": 0.0, "convexity": 1.0,
        "is_directional": 0.0, "confidence": 1.0,
    })
    ctx = ResolutionContext(node=circle_node, depth=0, child_bags=[])
    bag = REGISTRY.get("circle")(circle_node, ctx)

    spread   = bag.net("energy", "spread")
    velocity = bag.net("motion", "velocity")
    duration = bag.net("time",   "duration")
    role_zone = sum(e.value for e in bag.entries if e.tag.domain == "semantic" and e.tag.axis == "role_zone")
    assert spread > 0,    f"circle: spread attendu, got {spread}"
    assert velocity == 0, f"circle: velocity=0 attendu, got {velocity}"
    assert duration > 0,  f"circle: duration attendu, got {duration}"
    assert role_zone > 0, f"circle: role_zone manquant"
    print(f"[PASS] circle: spread={spread:.3f} duration={duration:.3f} velocity={velocity:.3f}")

    # ── Flèche → velocity + direction, pas de compression ───────────────────
    arrow_node = make_node("test_arrow", "arrow", 0, {
        "compactness": 0.0, "elongation": 10.0, "closure": 0.0,
        "linearity": 1.0, "angularity": 0.0, "area_n": 0.0,
        "scale_n": 0.15, "direction_n": 0.25, "convexity": 1.0,
        "is_directional": 1.0, "confidence": 1.0,
    })
    ctx_arrow = ResolutionContext(node=arrow_node, depth=0, child_bags=[])
    bag_arrow = REGISTRY.get("arrow")(arrow_node, ctx_arrow)

    velocity_arrow    = bag_arrow.net("motion", "velocity")
    compression_arrow = bag_arrow.net("energy", "compression")
    role_vector       = sum(e.value for e in bag_arrow.entries
                            if e.tag.domain == "semantic" and e.tag.axis == "role_vector")
    assert velocity_arrow >= 0.15, f"arrow: velocity>=0.15 attendu, got {velocity_arrow}"
    assert compression_arrow == 0, f"arrow: compression=0 attendu, got {compression_arrow}"
    assert role_vector > 0,        f"arrow: role_vector manquant"
    print(f"[PASS] arrow: velocity={velocity_arrow:.3f} compression={compression_arrow:.3f}")

    # ── Segment → compression + axis, pas de velocity ───────────────────────
    seg_node = make_node("test_segment", "segment", 0, {
        "compactness": 0.0, "elongation": 8.0, "closure": 0.0,
        "linearity": 1.0, "angularity": 0.0, "area_n": 0.0,
        "scale_n": 0.12, "direction_n": 0.25, "convexity": 1.0,
        "is_directional": 0.0, "confidence": 1.0,
    })
    ctx_seg = ResolutionContext(node=seg_node, depth=0, child_bags=[])
    bag_seg = REGISTRY.get("segment")(seg_node, ctx_seg)

    velocity_seg    = bag_seg.net("motion", "velocity")
    compression_seg = bag_seg.net("energy", "compression")
    role_barrier    = sum(e.value for e in bag_seg.entries
                          if e.tag.domain == "semantic" and e.tag.axis == "role_barrier")
    assert velocity_seg == 0,       f"segment: velocity=0 attendu, got {velocity_seg}"
    assert compression_seg >= 0.3,  f"segment: compression>=0.3 attendu, got {compression_seg}"
    assert role_barrier > 0,        f"segment: role_barrier manquant"
    print(f"[PASS] segment: velocity={velocity_seg:.3f} compression={compression_seg:.3f}")

    # ── ZigZag → chaos garanti, count présent ───────────────────────────────
    zz_node = make_node("test_zigzag", "zigzag", 0, {
        "compactness": 0.05, "elongation": 2.0, "closure": 0.05,
        "linearity": 0.3, "angularity": 0.8, "area_n": 0.05,
        "scale_n": 0.2, "direction_n": 0.0, "convexity": 0.3,
        "is_directional": 0.0, "confidence": 1.0,
    })
    ctx_zz = ResolutionContext(node=zz_node, depth=0, child_bags=[])
    bag_zz = REGISTRY.get("zigzag")(zz_node, ctx_zz)

    chaos_zz = bag_zz.net("time", "chaos")
    count_entries = [e for e in bag_zz.entries
                     if e.tag.domain == "semantic" and e.tag.axis == "count"]
    assert chaos_zz >= 0.35,   f"zigzag: chaos>=0.35 attendu, got {chaos_zz}"
    assert count_entries,      f"zigzag: semantic.count manquant"
    assert count_entries[0].value >= 2, f"zigzag: count>=2 attendu"
    print(f"[PASS] zigzag: chaos={chaos_zz:.3f} count={count_entries[0].value:.0f}")

    # ── Rune → element avec poids x2 ────────────────────────────────────────
    rune_node = make_node("test_rune", "rune_fire", 0, {
        "compactness": 0.3, "elongation": 1.5, "closure": 0.4,
        "linearity": 0.3, "angularity": 0.6, "area_n": 0.15,
        "scale_n": 0.2, "direction_n": 0.0, "convexity": 0.5,
        "is_directional": 0.0, "confidence": 1.0,
    })
    ctx_rune = ResolutionContext(node=rune_node, depth=0, child_bags=[])
    bag_rune = REGISTRY.get("rune_fire")(rune_node, ctx_rune)

    elem_entries = [e for e in bag_rune.entries
                    if e.tag.domain == "energy" and e.tag.axis == "element"]
    assert elem_entries, "rune: element entry manquant"
    # Poids de la rune doit être >= 2x (conf * 2.0 = 2.0 ici)
    assert elem_entries[0].weight >= 1.9, f"rune: poids element >= 1.9 attendu, got {elem_entries[0].weight}"
    print(f"[PASS] rune_fire: element={elem_entries[0].value:.3f} poids={elem_entries[0].weight:.2f}")

    # ── Symbole inconnu → rule_geometric (fallback) ──────────────────────────
    bag_unknown = REGISTRY.get("new_symbol")(circle_node, ctx)
    assert len(bag_unknown) > 0, "Symbole inconnu doit utiliser rule_geometric"
    print("[PASS] unknown symbol -> rule_geometric (fallback)")

    # ── Root virtuel → bag vide ──────────────────────────────────────────────
    root_node = ASTNode(node_id="root_v", symbol_type="root", primitive=None,
                        depth=-1, ordinal=0, sibling_count=1)
    ctx_root = ResolutionContext(node=root_node, depth=-1, child_bags=[])
    bag_root = REGISTRY.get("root")(root_node, ctx_root)
    assert len(bag_root) == 0
    print("[PASS] root node -> empty bag")

    print("\nAll symbol_registry assertions passed.")
