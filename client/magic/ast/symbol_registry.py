from __future__ import annotations

from typing import TYPE_CHECKING

from client.magic.ast.symbol_rules import (
    PropertyBag,
    ResolutionContext,
    SymbolRule,
    rule_arrow,
    rule_circle,
    rule_rune_fire,
    rule_segment,
    rule_triangle,
    rule_zigzag,
)

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode


def _rule_neutral(node: ASTNode, ctx: ResolutionContext) -> PropertyBag:
    """Regle neutre pour les symboles inconnus : bag vide, zero effet."""
    return PropertyBag()


class SymbolRegistry:
    """
    Registre extensible : symbol_type -> SymbolRule.
    Aucune regle n'est hardcodee en dehors du registre.
    Les regles par defaut sont enregistrees a l'init.
    """

    def __init__(self) -> None:
        self._rules: dict[str, SymbolRule] = {}
        self._register_defaults()

    def register(self, symbol_type: str, rule: SymbolRule) -> None:
        """Enregistre ou ecrase une regle. Extensible sans modifier le fichier."""
        self._rules[symbol_type] = rule

    def get(self, symbol_type: str) -> SymbolRule:
        """Retourne la regle ou une regle neutre si symbole inconnu."""
        return self._rules.get(symbol_type, _rule_neutral)

    def _register_defaults(self) -> None:
        """Enregistre toutes les regles de symbol_rules.py."""
        self._rules["circle"] = rule_circle
        self._rules["arrow"] = rule_arrow
        self._rules["arrow_with_base"] = rule_arrow  # meme logique que arrow
        self._rules["triangle"] = rule_triangle
        self._rules["segment"] = rule_segment
        self._rules["zigzag"] = rule_zigzag
        self._rules["rune_fire"] = rule_rune_fire

    @property
    def registered_types(self) -> list[str]:
        """Liste des types de symboles enregistres."""
        return list(self._rules.keys())


# Singleton global
REGISTRY = SymbolRegistry()


# ---------------------------------------------------------------------------
# Validation test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.ast.ast import ASTNode
    from client.magic.ast.symbol_rules import PropertyTag, ResolutionContext

    # --- Test 1 : cercle seul (depth=0, sans enfants) → compression=0.2 + spread + fade ---
    node_circle = ASTNode(
        node_id="test_0_circle",
        symbol_type="circle",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        drawing_features={"radius_normalized": 0.8},
    )
    ctx_circle = ResolutionContext(node=node_circle, depth=0, child_bags=[])

    bag = REGISTRY.get("circle")(node_circle, ctx_circle)

    cmp_entries = bag.query("energy", "compression")
    assert len(cmp_entries) == 1, f"Expected 1 energy.compression, got {len(cmp_entries)}"
    assert cmp_entries[0].value == 0.2, f"Expected 0.2, got {cmp_entries[0].value}"
    print(f"[PASS] circle solo: compression = {cmp_entries[0].value}")

    spread_entries = bag.query("space", "spread")
    assert len(spread_entries) == 1, f"Expected 1 space.spread, got {len(spread_entries)}"
    assert abs(spread_entries[0].value - 0.8 * 0.8) < 1e-6
    print(f"[PASS] circle solo: spread = {spread_entries[0].value:.3f}")

    fade_entries = bag.query("time", "fade_rate")
    assert len(fade_entries) == 1, f"Expected 1 time.fade_rate, got {len(fade_entries)}"
    print(f"[PASS] circle solo: fade_rate = {fade_entries[0].value}")

    # --- Test 2 : cercle avec enfants → pas de spread ni fade_rate ---
    child_bag = PropertyBag()
    child_bag.add(PropertyTag("energy", "compression", "self"), 0.3, 1.0, "child")
    ctx_circle_with_children = ResolutionContext(node=node_circle, depth=0, child_bags=[child_bag])

    bag_wc = REGISTRY.get("circle")(node_circle, ctx_circle_with_children)
    assert len(bag_wc.query("space", "spread")) == 0, "Circle with children should have no spread"
    print("[PASS] circle with children: no spread")

    # --- Test 3 : segment standalone (depth=0) → haute compression + axe ---
    node_seg = ASTNode(
        node_id="test_0_segment",
        symbol_type="segment",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        drawing_features={"length_normalized": 0.6, "angle_deg": 90.0},
    )
    ctx_seg = ResolutionContext(node=node_seg, depth=0, child_bags=[])
    bag_seg = REGISTRY.get("segment")(node_seg, ctx_seg)

    expected_cmp = 1.5 + 0.6 * 2.0  # = 2.7
    seg_cmp = bag_seg.net("energy", "compression")
    assert abs(seg_cmp - expected_cmp) < 1e-6, f"Expected compression={expected_cmp}, got {seg_cmp}"
    print(f"[PASS] segment standalone: compression = {seg_cmp:.3f}")

    assert len(bag_seg.query("space", "axis")) == 1
    print(f"[PASS] segment standalone: has axis")

    # --- Test 4 : fleche standalone (depth=0) → velocity + direction ---
    node_arrow = ASTNode(
        node_id="test_0_arrow",
        symbol_type="arrow",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        drawing_features={"length_normalized": 0.5, "direction_x": 1.0, "direction_y": 0.0},
    )
    ctx_arrow = ResolutionContext(node=node_arrow, depth=0, child_bags=[])
    bag_arrow = REGISTRY.get("arrow")(node_arrow, ctx_arrow)

    vel = bag_arrow.net("motion", "velocity")
    assert vel > 0, f"Expected velocity > 0, got {vel}"
    print(f"[PASS] arrow standalone: velocity = {vel:.3f}")

    dir_entries = bag_arrow.query("motion", "direction")
    assert len(dir_entries) == 1 and dir_entries[0].tag.target == "self"
    print(f"[PASS] arrow standalone: direction.self present")

    # --- Test 5 : fleche enfant (depth=1) → direction vers parent, pas de velocity ---
    node_arrow_child = ASTNode(
        node_id="test_1_arrow",
        symbol_type="arrow",
        primitive=None,
        depth=1,
        ordinal=0,
        sibling_count=1,
        drawing_features={"length_normalized": 0.5, "direction_x": 1.0, "direction_y": 0.0},
    )
    ctx_arrow_child = ResolutionContext(node=node_arrow_child, depth=1, child_bags=[])
    bag_arrow_child = REGISTRY.get("arrow")(node_arrow_child, ctx_arrow_child)

    assert bag_arrow_child.net("motion", "velocity") == 0.0, "Child arrow should have no velocity"
    dir_parent = bag_arrow_child.query("motion", "direction")
    assert len(dir_parent) == 1 and dir_parent[0].tag.target == "parent"
    print(f"[PASS] child arrow: direction.parent only, no velocity")

    # --- Test 6 : PropertyBag.net ---
    test_bag = PropertyBag()
    test_bag.add(PropertyTag("energy", "compression", "self"), 2.0, 1.5, "a")
    test_bag.add(PropertyTag("energy", "compression", "self"), 1.0, 0.5, "b")
    expected_net = 2.0 * 1.5 + 1.0 * 0.5  # 3.5
    assert test_bag.net("energy", "compression") == expected_net, (
        f"Expected net={expected_net}, got {test_bag.net('energy', 'compression')}"
    )
    print(f"[PASS] PropertyBag.net = {expected_net}")

    # --- Test 7 : symbole inconnu → bag vide ---
    unknown_node = ASTNode(
        node_id="test_unknown",
        symbol_type="splork",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
    )
    ctx_unknown = ResolutionContext(node=unknown_node, depth=0, child_bags=[])
    bag_unknown = REGISTRY.get("splork")(unknown_node, ctx_unknown)
    assert len(bag_unknown) == 0
    print("[PASS] unknown symbol: empty bag")

    print()
    print("All symbol_registry assertions passed.")
