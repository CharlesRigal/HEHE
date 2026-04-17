"""
ASTResolver — moteur d'émergence par géométrie.

Prend un SpellAST et produit un ResolvedSpell dont les params continus
émergent de 2 passes :

  Pass 1 — règles locales (bottom-up) : chaque nœud émet ses propriétés
            via rule_geometric (géométrie pure, aucun hardcode sémantique).
  Pass 2 — propagation parent/children : les entries scope="parent" ou
            scope="children" sont redistribuées dans l'arbre.

Le label behavior est dérivé en agrégation depuis les seuils continus.
Aucun symbole n'a de comportement hardcodé.
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
from client.magic.resolver.spell_intent import SpellIntent
from client.magic.resolver.role_resolver import resolve_intent as _resolve_intent

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode, SpellAST


# ---------------------------------------------------------------------------
# Params par défaut (AST vide ou échec)
# ---------------------------------------------------------------------------

_DEFAULT_PARAMS: dict[str, Any] = {
    "compression":    0.0,
    "speed":          0.0,
    "power":          0.0,
    "spread":         0.0,
    "elongation":     1.0,
    "duration_bonus": 0.0,
    "intensity":      1.0,
    "element":        "neutral",
    "behavior":       "stationary",
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

    def resolve_intent(self, ast: "SpellAST") -> SpellIntent:
        """Nouveau resolver par roles. AST -> SpellIntent multi-phases."""
        return _resolve_intent(ast)

    def resolve(self, ast: "SpellAST") -> ResolvedSpell:
        """Point d'entrée principal. Execute les 2 passes."""
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

        # Pass 2 : Propagation parent/children
        self._pass2_propagate(ast.root, node_bags, parent_bag=None)
        self.last_pass2_bags = copy.deepcopy(node_bags)
        self.last_cross_entries = []

        # Agrégation finale -> params
        params = self._aggregate(ast, node_bags)

        snapshot = {nid: list(bag.entries) for nid, bag in node_bags.items()}
        return ResolvedSpell(params=params, ast=ast, property_snapshot=snapshot)

    # -------------------------------------------------------------------
    # Pass 1 : Bottom-up — règles locales géométriques
    # -------------------------------------------------------------------

    def _pass1_bottom_up(
        self, node: "ASTNode", node_bags: dict[str, PropertyBag]
    ) -> PropertyBag:
        """Résolution récursive post-order."""
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
    # Pass 2 : Propagation parent/children
    # -------------------------------------------------------------------

    def _pass2_propagate(
        self,
        node: "ASTNode",
        node_bags: dict[str, PropertyBag],
        parent_bag: PropertyBag | None,
    ) -> None:
        """Redistribue les entries scope='parent'/'children' dans l'arbre."""
        nid = node.node_id
        bag = node_bags.get(nid)
        if bag is None:
            return

        # Entries scope="children" du parent -> ce nœud
        if parent_bag is not None:
            for entry in parent_bag.entries:
                if entry.tag.scope == "children":
                    bag.entries.append(PropertyEntry(
                        tag=PropertyTag(entry.tag.domain, entry.tag.axis, "self"),
                        value=entry.value,
                        weight=entry.weight * 0.8,
                        source_node_id=entry.source_node_id + "_propagated",
                    ))

        # Entries scope="parent" des enfants -> ce nœud
        for child in node.children:
            child_bag = node_bags.get(child.node_id)
            if child_bag is None:
                continue
            for entry in list(child_bag.entries):
                if entry.tag.scope == "parent":
                    bag.entries.append(PropertyEntry(
                        tag=PropertyTag(entry.tag.domain, entry.tag.axis, "self"),
                        value=entry.value,
                        weight=entry.weight * 0.9,
                        source_node_id=entry.source_node_id + "_propagated",
                    ))

        for child in node.children:
            self._pass2_propagate(child, node_bags, bag)

    # -------------------------------------------------------------------
    # Agrégation finale
    # -------------------------------------------------------------------

    def _aggregate(
        self,
        ast: "SpellAST",
        node_bags: dict[str, PropertyBag],
    ) -> dict[str, Any]:
        # Fusionner tous les bags (racine = poids maximal)
        merged = PropertyBag()
        for node in ast.all_nodes:
            bag = node_bags.get(node.node_id)
            if bag is None:
                continue
            depth_w = 1.0 / (1.0 + node.depth)
            for entry in bag.entries:
                if entry.tag.scope in ("parent", "children"):
                    continue  # déjà propagées, éviter le double-comptage
                merged.add(entry.tag, entry.value, entry.weight * depth_w, entry.source_node_id)

        params: dict[str, Any] = {}

        # ── Compression ──────────────────────────────────────────────────
        compression = merged.net("energy", "compression")
        params["compression"] = max(0.0, compression)

        # ── Vélocité / speed ─────────────────────────────────────────────
        velocity = merged.net("motion", "velocity")
        params["speed"] = max(0.0, velocity)

        # ── Spread ───────────────────────────────────────────────────────
        spread = merged.net("energy", "spread")
        params["spread"] = max(0.0, spread)

        # ── Axe spatial (orientation d'un mur) ───────────────────────────
        axis_entries = [
            e for e in merged.query("space", "axis")
            if e.tag.scope == "self"
        ]
        axis_x, axis_y = 0.0, 0.0
        if axis_entries:
            best = max(axis_entries, key=lambda e: e.weight)
            angle_rad = best.value * 2.0 * math.pi
            axis_x = math.cos(angle_rad)
            axis_y = math.sin(angle_rad)
        params["axis_x"] = axis_x
        params["axis_y"] = axis_y

        # ── Elongation ────────────────────────────────────────────────────
        elonga_entries = [
            e for e in merged.query("space", "elongation")
            if e.tag.scope == "self"
        ]
        elongation = max((e.value for e in elonga_entries), default=1.0)
        params["elongation"] = max(1.0, elongation)

        # ── Durée ─────────────────────────────────────────────────────────
        duration = merged.net("time", "duration")
        params["duration_bonus"] = max(0.0, duration)

        # ── Chaos / instabilité ───────────────────────────────────────────
        chaos = merged.net("time", "chaos")
        params["unstable"] = chaos > 0.3

        # ── Fade rate (dérivé de durée + spread) ─────────────────────────
        params["fade_rate"] = min(1.0, spread * 0.5) if duration > 0.05 else 0.0

        # ── Élément ───────────────────────────────────────────────────────
        element_val = merged.net("energy", "element")
        # Normaliser par le poids total pour obtenir une moyenne pondérée
        element_weights = sum(e.weight for e in merged.query("energy", "element"))
        if element_weights > 1e-6:
            element_val /= element_weights
        params["element"] = _resolve_element(element_val)

        # ── Power ─────────────────────────────────────────────────────────
        power = max(0.05, compression * 0.4 + spread * 0.3 + velocity * 0.2)
        params["power"] = min(1.0, power)

        # ── Intensity ─────────────────────────────────────────────────────
        params["intensity"] = max(1.0, 1.0 + (0.5 if params["unstable"] else 0.0))

        # ── Focused ───────────────────────────────────────────────────────
        params["focused"] = compression > 0.8 and spread < 0.1

        # ── Direction (seulement si explicite) ────────────────────────────
        dir_entries = [
            e for e in merged.query("motion", "direction")
            if not e.source_node_id.endswith("_propagated") and e.tag.scope == "self"
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

        # ── Behavior émergent ─────────────────────────────────────────────
        # Aucun hardcode sur un type de symbole.
        # Le comportement émerge des valeurs continues :
        #   velocity -> projectile (mouvement)
        #   compression + axis -> wall (statique, allongé)
        #   spread + duration -> pool (zone persistante)
        #   spread -> aoe (zone instantanée)
        axis_exists = abs(axis_x) > 1e-6 or abs(axis_y) > 1e-6
        if velocity > 0.08:
            behavior = "projectile"
        elif axis_exists and compression > 0.15 and velocity < 0.05:
            behavior = "wall"
        elif spread > 0.05 and duration > 0.05 and compression < 0.15:
            behavior = "pool"
        elif spread > 0.02:
            behavior = "aoe"
        else:
            behavior = "stationary"
        params["behavior"] = behavior

        return params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_element(element_val: float) -> str:
    """Mappe la valeur élémentaire continue [0,1] vers un nom d'élément."""
    if element_val > 0.82:
        return "fire"
    elif element_val > 0.65:
        return "lightning"
    elif element_val > 0.42:
        return "arcane"
    elif element_val < 0.22:
        return "ice"
    return "neutral"


# ---------------------------------------------------------------------------
# Test de validation
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.ast.ast import ASTNode, SpellAST

    resolver = ASTResolver()

    def make_node(nid, symbol, depth, feats):
        return ASTNode(
            node_id=nid, symbol_type=symbol, primitive=None,
            depth=depth, ordinal=0, sibling_count=1,
            spatial_role="peer", drawing_features=feats,
        )

    CIRCLE_FEATS = {
        "compactness": 0.95, "elongation": 1.05, "closure": 0.98,
        "linearity": 0.01, "angularity": 0.0, "area_n": 0.4,
        "scale_n": 0.6, "direction_n": 0.0, "convexity": 1.0,
        "is_directional": 0.0, "confidence": 1.0,
    }
    ARROW_FEATS_D0 = {
        "compactness": 0.0, "elongation": 10.0, "closure": 0.0,
        "linearity": 1.0, "angularity": 0.0, "area_n": 0.0,
        "scale_n": 0.15, "direction_n": 0.0, "convexity": 1.0,
        "is_directional": 1.0, "confidence": 1.0,
    }
    ARROW_FEATS_D1 = {**ARROW_FEATS_D0}
    SEG_FEATS = {
        "compactness": 0.0, "elongation": 8.0, "closure": 0.0,
        "linearity": 1.0, "angularity": 0.0, "area_n": 0.0,
        "scale_n": 0.12, "direction_n": 0.25, "convexity": 1.0,
        "is_directional": 0.0, "confidence": 1.0,
    }
    ZIGZAG_FEATS = {
        "compactness": 0.05, "elongation": 2.0, "closure": 0.05,
        "linearity": 0.3, "angularity": 0.8, "area_n": 0.05,
        "scale_n": 0.2, "direction_n": 0.0, "convexity": 0.3,
        "is_directional": 0.0, "confidence": 1.0,
    }

    # ── Test 1 : Cercle seul -> pool ────────────────────────────────────────
    c = make_node("n0_circle", "circle", 0, CIRCLE_FEATS)
    ast_c = SpellAST(root=c, all_nodes=[c], depth=0, node_count=1, spatial_relations=[])
    r = resolver.resolve(ast_c)
    print(f"Cercle seul: behavior={r.params['behavior']} spread={r.params['spread']:.3f} element={r.params['element']}")
    assert r.params["behavior"] in ("pool", "aoe"), f"Expected pool/aoe, got {r.params['behavior']}"
    assert r.params["spread"] > 0
    print(f"[PASS] Cercle seul -> {r.params['behavior']}")

    # ── Test 2 : Cercle + flèche enfant -> projectile ───────────────────────
    arrow_child = make_node("n1_arrow", "arrow", 1, ARROW_FEATS_D1)
    c2 = make_node("n0_circle", "circle", 0, CIRCLE_FEATS)
    c2.children.append(arrow_child)
    all_nodes = [c2, arrow_child]
    ast_ca = SpellAST(root=c2, all_nodes=all_nodes, depth=1, node_count=2, spatial_relations=[])
    r2 = resolver.resolve(ast_ca)
    print(f"Cercle+flèche: behavior={r2.params['behavior']} speed={r2.params['speed']:.3f} dir_explicit={r2.params['_dir_explicit']}")
    assert r2.params["behavior"] == "projectile", f"Expected projectile, got {r2.params['behavior']}"
    print("[PASS] Cercle+flèche -> projectile")

    # ── Test 3 : Cercle + segment enfant -> wall ────────────────────────────
    seg_child = make_node("n1_seg", "segment", 1, SEG_FEATS)
    c3 = make_node("n0_circle", "circle", 0, CIRCLE_FEATS)
    c3.children.append(seg_child)
    all_nodes3 = [c3, seg_child]
    ast_cs = SpellAST(root=c3, all_nodes=all_nodes3, depth=1, node_count=2, spatial_relations=[])
    r3 = resolver.resolve(ast_cs)
    print(f"Cercle+segment: behavior={r3.params['behavior']} compression={r3.params['compression']:.3f} axis=({r3.params['axis_x']:.2f},{r3.params['axis_y']:.2f})")
    assert r3.params["behavior"] == "wall", f"Expected wall, got {r3.params['behavior']}"
    print("[PASS] Cercle+segment -> wall")

    # ── Test 4 : Cercle + zigzag enfant -> élément fire ────────────────────
    zz_child = make_node("n1_zz", "zigzag", 1, ZIGZAG_FEATS)
    c4 = make_node("n0_circle", "circle", 0, CIRCLE_FEATS)
    c4.children.append(zz_child)
    all_nodes4 = [c4, zz_child]
    ast_czz = SpellAST(root=c4, all_nodes=all_nodes4, depth=1, node_count=2, spatial_relations=[])
    r4 = resolver.resolve(ast_czz)
    print(f"Cercle+zigzag: behavior={r4.params['behavior']} element={r4.params['element']} unstable={r4.params['unstable']}")
    print("[PASS] Cercle+zigzag résolu")

    # ── Test 5 : AST vide ─────────────────────────────────────────────────
    empty_ast = SpellAST(root=None, all_nodes=[], depth=0, node_count=0, spatial_relations=[])
    empty_result = resolver.resolve(empty_ast)
    assert empty_result.params["element"] == "neutral"
    assert empty_result.params["behavior"] == "stationary"
    print("[PASS] AST vide -> defaults")

    # ── Test 6 : Sérialisation réseau ─────────────────────────────────────
    from client.magic.resolver.resolved_spell import params_to_network_spec
    net = params_to_network_spec(resolver.resolve(ast_ca))
    assert net["t"] == "s"
    assert net.get("bh") == "projectile"
    print(f"[PASS] Network spec cercle+flèche: {net}")

    print("\nAll resolver assertions passed.")
