"""ASTResolver : moteur d'emergence par compression.

Prend un SpellAST et produit un ResolvedSpell dont les params continus
emergent de 3 passes :

  Pass 1 — regles locales (bottom-up) : chaque noeud emet ses proprietes
  Pass 2 — fleches zero-sum : quand des fleches s'annulent mutuellement,
            elles boostent la compression de leur voisin non-fleche
  Pass 3 — propagation parent/children : les entries target="parent" ou
            target="children" sont redistribuees dans l'arbre

Aucun tag "behavior" dans les regles.  Le label behavior est derive en
agregation depuis les seuils continus (compression, velocity, spread, ...).
"""

from __future__ import annotations

import copy
import math
from typing import Any, TYPE_CHECKING

from client.magic.ast.symbol_rules import (
    PropertyBag,
    PropertyEntry,
    PropertyTag,
    ResolutionContext,
)
from client.magic.ast.symbol_registry import REGISTRY, SymbolRegistry
from client.magic.resolver.resolved_spell import ResolvedSpell

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode, SpellAST


# ---------------------------------------------------------------------------
# Params par defaut (AST vide ou echec)
# ---------------------------------------------------------------------------

_DEFAULT_PARAMS: dict[str, Any] = {
    "compression":    0.0,
    "speed":          0.0,
    "power":          0.5,
    "spread":         0.0,
    "elongation":     1.0,
    "duration_bonus": 0.0,
    "intensity":      1.0,
    "element":        "neutral",
    "behavior":       "aoe",
    "focused":        False,
    "unstable":       False,
    "axis_x":         0.0,
    "axis_y":         0.0,
    "dir_x":          1.0,
    "dir_y":          0.0,
    "fade_rate":      0.0,
    "_dir_explicit":  False,
}


class ASTResolver:
    def __init__(self, registry: SymbolRegistry | None = None):
        self.registry = registry or REGISTRY
        self.last_pass1_bags: dict[str, PropertyBag] = {}
        self.last_pass2_bags: dict[str, PropertyBag] = {}
        self.last_cross_entries: list[PropertyEntry] = []

    def resolve(self, ast: SpellAST) -> ResolvedSpell:
        """Point d'entree principal. Execute les 3 passes."""
        if ast.root is None:
            return ResolvedSpell(
                params=dict(_DEFAULT_PARAMS),
                ast=ast,
                property_snapshot={},
            )

        node_bags: dict[str, PropertyBag] = {}

        # Pass 1 : Bottom-up (feuilles -> racine)
        self._pass1_bottom_up(ast.root, node_bags)
        self.last_pass1_bags = copy.deepcopy(node_bags)

        # Pass 2 : Zero-sum arrows (detection + boost compression)
        self._pass2_zero_sum_arrows(ast, node_bags)
        # (on stocke le resultat apres pass2 comme "pass2_bags" pour le debug)

        # Pass 3 : Propagation parent/children
        self._pass3_propagate(ast.root, node_bags, parent_bag=None)
        self.last_pass2_bags = copy.deepcopy(node_bags)
        self.last_cross_entries = []

        # Agregation finale -> params
        params = self._aggregate(ast, node_bags)

        snapshot = {nid: list(bag.entries) for nid, bag in node_bags.items()}
        return ResolvedSpell(params=params, ast=ast, property_snapshot=snapshot)

    # -------------------------------------------------------------------
    # Pass 1 : Bottom-up — regles locales
    # -------------------------------------------------------------------

    def _pass1_bottom_up(
        self, node: ASTNode, node_bags: dict[str, PropertyBag]
    ) -> PropertyBag:
        """Resolution recursive post-order."""
        child_bags = [
            self._pass1_bottom_up(child, node_bags) for child in node.children
        ]

        ctx = ResolutionContext(
            node=node,
            depth=node.depth,
            child_bags=child_bags,
        )

        rule = self.registry.get(node.symbol_type)
        bag = rule(node, ctx)
        node_bags[node.node_id] = bag
        return bag

    # -------------------------------------------------------------------
    # Pass 2 : Zero-sum arrows
    # -------------------------------------------------------------------

    def _pass2_zero_sum_arrows(
        self, ast: SpellAST, node_bags: dict[str, PropertyBag]
    ) -> None:
        """
        Pour chaque groupe de noeuds freres (meme parent) :
        si >= 2 fleches s'annulent (net direction ~ 0), elles boostent
        la compression du frere non-fleche le plus proche.
        """
        if ast.root is None:
            return
        self._process_peer_group(ast.root, ast, node_bags)

    def _process_peer_group(
        self, parent: ASTNode, ast: SpellAST, node_bags: dict[str, PropertyBag]
    ) -> None:
        children = parent.children
        if not children:
            return

        # Recurser d'abord sur les enfants
        for child in children:
            self._process_peer_group(child, ast, node_bags)

        # Trouver les fleches au meme niveau
        arrow_nodes = [n for n in children if n.symbol_type in ("arrow", "arrow_with_base")]
        non_arrow_nodes = [n for n in children if n.symbol_type not in ("arrow", "arrow_with_base")]

        if len(arrow_nodes) < 2 or not non_arrow_nodes:
            return

        # Calculer la somme vectorielle des directions
        net_x = 0.0
        net_y = 0.0
        for an in arrow_nodes:
            ang_norm = node_bags[an.node_id].net("motion", "direction")
            # direction dans les bags enfants pointe vers "parent" — ignorer
            # Utiliser direction_x/y des features directement
            dx = an.drawing_features.get("direction_x", 1.0)
            dy = an.drawing_features.get("direction_y", 0.0)
            net_x += dx
            net_y += dy

        net_norm = math.hypot(net_x, net_y)
        threshold = 0.25 * len(arrow_nodes)

        if net_norm >= threshold:
            return  # les fleches ne s'annulent pas suffisamment

        # Les fleches s'annulent : booster la compression du frere non-fleche
        # On prend le premier non-fleche (ou le plus grand si on voulait etendre)
        target_node = non_arrow_nodes[0]
        boost = len(arrow_nodes) * 0.8
        scale_factor = max(0.3, 1.0 - len(arrow_nodes) * 0.15)

        node_bags[target_node.node_id].add(
            PropertyTag("energy", "compression", "self"),
            boost,
            1.2,
            "arrow_zerosum",
        )
        node_bags[target_node.node_id].add(
            PropertyTag("space", "scale_factor", "self"),
            scale_factor,
            1.0,
            "arrow_zerosum",
        )

    # -------------------------------------------------------------------
    # Pass 3 : Propagation parent/children
    # -------------------------------------------------------------------

    def _pass3_propagate(
        self,
        node: ASTNode,
        node_bags: dict[str, PropertyBag],
        parent_bag: PropertyBag | None,
    ) -> None:
        """Redistribue les entries target="parent"/"children" dans l'arbre."""
        nid = node.node_id
        bag = node_bags.get(nid)
        if bag is None:
            return

        # Propager les entries "parent" de ce noeud vers le parent (deja fait au-dessus)
        # Ici on recoit les entries "children" du parent
        if parent_bag is not None:
            for entry in parent_bag.entries:
                if entry.tag.target == "children":
                    new_entry = PropertyEntry(
                        tag=PropertyTag(
                            domain=entry.tag.domain,
                            name=entry.tag.name,
                            target="self",
                        ),
                        value=entry.value,
                        weight=entry.weight * 0.8,
                        source_node_id=entry.source_node_id + "_propagated",
                    )
                    bag.entries.append(new_entry)

        # Propager les entries "children" de ce noeud vers ses enfants
        # et les entries "parent" des enfants vers ce noeud
        for child in node.children:
            child_bag = node_bags.get(child.node_id)
            if child_bag is None:
                continue
            # Les entries target="parent" du child remontent dans ce bag
            for entry in list(child_bag.entries):
                if entry.tag.target == "parent":
                    new_entry = PropertyEntry(
                        tag=PropertyTag(
                            domain=entry.tag.domain,
                            name=entry.tag.name,
                            target="self",
                        ),
                        value=entry.value,
                        weight=entry.weight * 0.9,
                        source_node_id=entry.source_node_id + "_propagated",
                    )
                    bag.entries.append(new_entry)

        # Recurser sur les enfants avec le bag courant comme parent_bag
        for child in node.children:
            self._pass3_propagate(child, node_bags, bag)

    # -------------------------------------------------------------------
    # Agregation finale
    # -------------------------------------------------------------------

    def _aggregate(
        self,
        ast: SpellAST,
        node_bags: dict[str, PropertyBag],
    ) -> dict[str, Any]:
        # Fusionner tous les bags (racine a plus de poids)
        merged = PropertyBag()
        for node in ast.all_nodes:
            bag = node_bags.get(node.node_id)
            if bag is None:
                continue
            depth_w = 1.0 / (1.0 + node.depth)
            for entry in bag.entries:
                # Ne pas re-propager les entries "parent"/"children" dans la fusion
                # (elles ont deja ete propagees en Pass 3)
                if entry.tag.target in ("parent", "children"):
                    continue
                merged.add(entry.tag, entry.value, entry.weight * depth_w, entry.source_node_id)

        params: dict[str, Any] = {}

        # ── Compression ──────────────────────────────────────────────────
        compression = merged.net("energy", "compression")
        params["compression"] = max(0.0, compression)

        # ── Velocity / speed ─────────────────────────────────────────────
        velocity = merged.net("motion", "velocity")
        params["speed"] = max(0.0, velocity)

        # ── Spread ───────────────────────────────────────────────────────
        spread = merged.net("space", "spread")
        params["spread"] = max(0.0, spread)

        # ── Axis (pour les murs) ──────────────────────────────────────────
        axis_entries = [e for e in merged.query("space", "axis") if e.tag.target == "self"]
        axis_x, axis_y = 0.0, 0.0
        if axis_entries:
            # Prendre la valeur ponderee la plus forte
            best = max(axis_entries, key=lambda e: e.value * e.weight)
            angle_rad = best.value * 2.0 * math.pi
            axis_x = math.cos(angle_rad)
            axis_y = math.sin(angle_rad)
        params["axis_x"] = axis_x
        params["axis_y"] = axis_y

        # ── Elongation ────────────────────────────────────────────────────
        elongation = merged.net("space", "elongation")
        if elongation < 1e-6:
            elongation = 1.0
        params["elongation"] = max(1.0, elongation)

        # ── Scale factor (influence de arrows zero-sum) ───────────────────
        scale_factor = merged.net("space", "scale_factor")
        if scale_factor < 1e-6:
            scale_factor = 1.0
        params["scale_factor"] = max(0.1, scale_factor)

        # ── Duration bonus ────────────────────────────────────────────────
        duration = merged.net("time", "duration")
        params["duration_bonus"] = max(0.0, duration)

        # ── Fade rate ─────────────────────────────────────────────────────
        fade_rate = merged.net("time", "fade_rate")
        params["fade_rate"] = max(0.0, min(1.0, fade_rate))

        # ── Element ───────────────────────────────────────────────────────
        element_val = merged.net("energy", "element")
        params["element"] = _resolve_element(element_val)

        # ── Power (magnitude de base) ─────────────────────────────────────
        power = max(0.1, compression * 0.3 + spread * 0.2 + velocity * 0.1)
        params["power"] = min(1.0, power)

        # ── Intensity ────────────────────────────────────────────────────
        unstable_val = merged.net("polarity", "unstable")
        burn_val = merged.net("polarity", "burn")
        params["intensity"] = max(1.0, 1.0 + burn_val * 0.3 + (1.0 if unstable_val > 0.5 else 0.0))

        # ── Focused / Unstable ───────────────────────────────────────────
        params["focused"] = False
        params["unstable"] = unstable_val > 0.5

        # ── Direction (seulement si explicite, non-propagee) ─────────────
        dir_entries = [
            e for e in merged.query("motion", "direction")
            if not e.source_node_id.endswith("_propagated") and e.tag.target == "self"
        ]
        dir_x, dir_y = 1.0, 0.0
        dir_explicit = False
        if dir_entries:
            best_dir = max(dir_entries, key=lambda e: e.weight)
            angle_rad = best_dir.value * 2.0 * math.pi
            dir_x = math.cos(angle_rad)
            dir_y = math.sin(angle_rad)
            dir_explicit = True
        params["dir_x"] = dir_x
        params["dir_y"] = dir_y
        params["_dir_explicit"] = dir_explicit

        # ── Behavior emergent ─────────────────────────────────────────────
        # Aucun hard-code : uniquement des seuils sur des valeurs continues
        if velocity > 0.05:
            behavior = "projectile"
        elif compression > 1.5 and (abs(axis_x) > 1e-6 or abs(axis_y) > 1e-6):
            behavior = "wall"
        elif spread > 0.3 and fade_rate > 0.0 and compression < 1.0:
            behavior = "pool"
        elif spread > 0.05:
            behavior = "aoe"
        else:
            behavior = "stationary"
        params["behavior"] = behavior

        return params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_element(element_val: float) -> str:
    """Mappe une valeur continue vers un nom d'element."""
    if element_val > 0.75:
        return "fire"
    elif element_val > 0.35:
        return "lightning"
    elif element_val > 0.1:
        return "arcane"
    elif element_val < -0.1:
        return "ice"
    return "neutral"


# ---------------------------------------------------------------------------
# Validation test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.ast.ast import ASTNode, SpellAST

    resolver = ASTResolver()

    # ── Test 1 : Segment seul -> wall ──────────────────────────────────────
    seg_node = ASTNode(
        node_id="node_0_segment",
        symbol_type="segment",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        spatial_role="peer",
        drawing_features={"length_normalized": 0.5, "angle_deg": 90.0},
    )
    ast_seg = SpellAST(root=seg_node, all_nodes=[seg_node], depth=0, node_count=1, spatial_relations=[])
    r_seg = resolver.resolve(ast_seg)
    print(f"Segment seul: compression={r_seg.params['compression']:.3f} behavior={r_seg.params['behavior']}")
    assert r_seg.params["compression"] > 1.5, f"Expected compression > 1.5, got {r_seg.params['compression']}"
    assert r_seg.params["behavior"] == "wall", f"Expected wall, got {r_seg.params['behavior']}"
    print("[PASS] Segment seul -> wall")

    # ── Test 2 : Cercle seul -> pool ────────────────────────────────────────
    circle_node = ASTNode(
        node_id="node_0_circle",
        symbol_type="circle",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        spatial_role="peer",
        drawing_features={"radius_normalized": 0.7},
    )
    ast_circle = SpellAST(root=circle_node, all_nodes=[circle_node], depth=0, node_count=1, spatial_relations=[])
    r_circle = resolver.resolve(ast_circle)
    print(f"Cercle seul: compression={r_circle.params['compression']:.3f} behavior={r_circle.params['behavior']} fade={r_circle.params['fade_rate']:.3f}")
    assert r_circle.params["behavior"] == "pool", f"Expected pool, got {r_circle.params['behavior']}"
    assert r_circle.params["fade_rate"] > 0, f"Expected fade_rate > 0"
    print("[PASS] Cercle seul -> pool")

    # ── Test 3 : Fleche seule -> projectile ────────────────────────────────
    arrow_node = ASTNode(
        node_id="node_0_arrow",
        symbol_type="arrow",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        spatial_role="peer",
        drawing_features={"length_normalized": 0.6, "direction_x": 1.0, "direction_y": 0.0},
    )
    ast_arrow = SpellAST(root=arrow_node, all_nodes=[arrow_node], depth=0, node_count=1, spatial_relations=[])
    r_arrow = resolver.resolve(ast_arrow)
    print(f"Fleche seule: speed={r_arrow.params['speed']:.3f} behavior={r_arrow.params['behavior']}")
    assert r_arrow.params["behavior"] == "projectile", f"Expected projectile, got {r_arrow.params['behavior']}"
    assert r_arrow.params["_dir_explicit"] is True
    print("[PASS] Fleche seule -> projectile + dir_explicit")

    # ── Test 4 : Triangle seul -> aoe ──────────────────────────────────────
    tri_node = ASTNode(
        node_id="node_0_triangle",
        symbol_type="triangle",
        primitive=None,
        depth=0,
        ordinal=0,
        sibling_count=1,
        spatial_role="peer",
        drawing_features={"area_normalized": 0.4, "apex_sharpness": 0.5},
    )
    ast_tri = SpellAST(root=tri_node, all_nodes=[tri_node], depth=0, node_count=1, spatial_relations=[])
    r_tri = resolver.resolve(ast_tri)
    print(f"Triangle seul: spread={r_tri.params['spread']:.3f} behavior={r_tri.params['behavior']}")
    assert r_tri.params["behavior"] in ("aoe", "wall"), f"Expected aoe/wall, got {r_tri.params['behavior']}"
    assert r_tri.params["spread"] > 0
    print(f"[PASS] Triangle seul -> {r_tri.params['behavior']} (spread>0)")

    # ── Test 5 : AST vide ─────────────────────────────────────────────────
    empty_ast = SpellAST(root=None, all_nodes=[], depth=0, node_count=0, spatial_relations=[])
    empty_result = resolver.resolve(empty_ast)
    assert empty_result.params["element"] == "neutral"
    assert empty_result.params["behavior"] == "aoe"
    print("[PASS] AST vide -> defaults")

    # ── Test 6 : Serialisation reseau ─────────────────────────────────────
    from client.magic.resolver.resolved_spell import params_to_network_spec
    net = params_to_network_spec(resolver.resolve(ast_seg))
    assert net["t"] == "s"
    assert "cmp" in net and net["cmp"] > 1.5
    assert "ax" in net
    print(f"[PASS] Network spec segment: {net}")

    print()
    print("All resolver assertions passed.")
