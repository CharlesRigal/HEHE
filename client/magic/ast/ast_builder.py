from __future__ import annotations

import math
from typing import Any

from client.magic.ast.ast import ASTNode, SpellAST
from client.magic.primitives import (
    Arrow,
    ArrowWithBase,
    Circle,
    RuneFire,
    Segment,
    Triangle,
    ZigZag,
)


class ASTBuilder:
    """Construit un SpellAST a partir d'un GraphGeo en utilisant la containance spatiale."""

    def build(self, graph) -> SpellAST:
        """
        graph: instance de GraphGeo avec ses primitives et spatial_relations.
        Retourne un SpellAST construit par containance spatiale.
        """
        nodes = graph.iter_nodes()
        primitives = [n.primitive for n in nodes]
        relations = graph.build_spatial_relations()

        root = self._build_tree_from_containment(primitives, relations)

        # Collect all ASTNodes via BFS
        all_nodes: list[ASTNode] = []
        max_depth = 0
        if root is not None:
            queue = [root]
            while queue:
                current = queue.pop(0)
                # Skip virtual root in the flat list
                if current.symbol_type != "root":
                    all_nodes.append(current)
                if current.depth > max_depth:
                    max_depth = current.depth
                queue.extend(current.children)

        # If virtual root, the real max_depth is already correct (children start at 0)
        # If single root that is real, max_depth is from real nodes
        # Adjust: virtual root has depth -1, we want max depth of real nodes
        if root is not None and root.symbol_type == "root":
            max_depth = max((n.depth for n in all_nodes), default=0)

        return SpellAST(
            root=root,
            all_nodes=all_nodes,
            depth=max_depth,
            node_count=len(all_nodes),
            spatial_relations=relations,
        )

    def _determine_symbol_type(self, primitive) -> str:
        """Mappe le type de primitive vers un string symbole via le champ kind."""
        kind = getattr(primitive, "kind", None)
        if kind is not None:
            return str(kind)
        # Fallback par isinstance
        type_map = {
            Circle: "circle",
            Arrow: "arrow",
            ArrowWithBase: "arrow_with_base",
            Triangle: "triangle",
            Segment: "segment",
            ZigZag: "zigzag",
            RuneFire: "rune_fire",
        }
        for cls, name in type_map.items():
            if isinstance(primitive, cls):
                return name
        return "unknown"

    def _extract_drawing_features(self, primitive) -> dict[str, float]:
        """
        Extrait des features continues normalisees de la primitive.
        Ces features permettent au resolver de moduler les effets
        en fonction de la taille/forme du dessin.
        """
        features: dict[str, float] = {}

        if isinstance(primitive, Circle):
            if primitive.radius is not None:
                features["radius_normalized"] = primitive.radius / 110.0
                features["area_normalized"] = (math.pi * primitive.radius ** 2) / (math.pi * 110.0 ** 2)

        elif isinstance(primitive, Arrow):
            dx = primitive.tip[0] - primitive.tail[0]
            dy = primitive.tip[1] - primitive.tail[1]
            length = math.hypot(dx, dy)
            features["length_normalized"] = length / 200.0
            angle = math.degrees(math.atan2(dy, dx))
            features["angle_deg"] = angle % 360.0
            norm = length if length > 1e-6 else 1.0
            features["direction_x"] = dx / norm
            features["direction_y"] = dy / norm

        elif isinstance(primitive, ArrowWithBase):
            dx = primitive.tip[0] - primitive.tail[0]
            dy = primitive.tip[1] - primitive.tail[1]
            length = math.hypot(dx, dy)
            features["length_normalized"] = length / 200.0
            angle = math.degrees(math.atan2(dy, dx))
            features["angle_deg"] = angle % 360.0
            norm = length if length > 1e-6 else 1.0
            features["direction_x"] = dx / norm
            features["direction_y"] = dy / norm
            base_length = math.hypot(
                primitive.base_end[0] - primitive.base_start[0],
                primitive.base_end[1] - primitive.base_start[1],
            )
            features["base_length_normalized"] = base_length / 100.0

        elif isinstance(primitive, Triangle):
            if len(primitive.vertices) >= 3:
                area = self._triangle_area(
                    primitive.vertices[0],
                    primitive.vertices[1],
                    primitive.vertices[2],
                )
                features["area_normalized"] = area / (110.0 * 110.0)
                xs = [v[0] for v in primitive.vertices]
                ys = [v[1] for v in primitive.vertices]
                bbox_w = max(xs) - min(xs) or 1.0
                bbox_h = max(ys) - min(ys) or 1.0
                features["apex_sharpness"] = min(1.0, (bbox_h / bbox_w) / 2.0)

        elif isinstance(primitive, Segment):
            length = math.hypot(
                primitive.end[0] - primitive.start[0],
                primitive.end[1] - primitive.start[1],
            )
            features["length_normalized"] = length / 200.0
            angle = math.degrees(
                math.atan2(
                    primitive.end[1] - primitive.start[1],
                    primitive.end[0] - primitive.start[0],
                )
            )
            features["angle_deg"] = angle % 360.0

        elif isinstance(primitive, ZigZag):
            if primitive.vertices and len(primitive.vertices) >= 2:
                total = 0.0
                for i in range(1, len(primitive.vertices)):
                    total += math.hypot(
                        primitive.vertices[i][0] - primitive.vertices[i - 1][0],
                        primitive.vertices[i][1] - primitive.vertices[i - 1][1],
                    )
                features["total_length_normalized"] = total / 300.0
                seg_count = float(len(primitive.vertices) - 1)
                features["segment_count"] = seg_count
                ys_zig = [v[1] for v in primitive.vertices]
                features["amplitude"] = (max(ys_zig) - min(ys_zig)) / 200.0
                features["frequency"] = seg_count / max(total * 0.01, 1.0)

        elif isinstance(primitive, RuneFire):
            if len(primitive.vertices) >= 3:
                area = self._triangle_area(
                    primitive.vertices[0],
                    primitive.vertices[1],
                    primitive.vertices[2],
                )
                features["area_normalized"] = area / (110.0 * 110.0)
                features["cut_count"] = float(len(primitive.cuts))

        # Add confidence as universal feature
        confidence = getattr(primitive, "confidence", None)
        if confidence is not None:
            features["confidence"] = float(confidence)

        return features

    def _build_tree_from_containment(
        self,
        primitives: list[Any],
        spatial_relations: list[Any],
    ) -> ASTNode | None:
        """
        Construit l'arbre AST a partir des relations de containance.
        Containance directe: A est parent de B ssi A contient B
        et il n'existe pas de C tel que A contient C et C contient B.
        """
        if not primitives:
            return None

        n = len(primitives)

        # Precompute bounding sizes to resolve mutual containment conflicts
        sizes = [self._primitive_bounding_size(p) for p in primitives]

        # Build containment matrix: contains[i] = set of indices that i directly contains
        # First pass: raw containment from spatial relations
        raw_contains: dict[int, set[int]] = {i: set() for i in range(n)}
        for rel in spatial_relations:
            if rel.relation == "contains":
                raw_contains[rel.source_index].add(rel.target_index)

        # Sanitize: if A contains B AND B contains A, keep only the larger one as container
        for i in range(n):
            for j in range(i + 1, n):
                if j in raw_contains[i] and i in raw_contains[j]:
                    if sizes[i] >= sizes[j]:
                        raw_contains[j].discard(i)
                    else:
                        raw_contains[i].discard(j)

        # Second pass: compute direct containment (remove transitive)
        # A is direct parent of B if A contains B and there's no C where A contains C and C contains B
        direct_children: dict[int, set[int]] = {i: set() for i in range(n)}
        for parent_idx in range(n):
            contained = raw_contains[parent_idx]
            for child_idx in contained:
                # Check if there's an intermediate container
                has_intermediate = False
                for mid_idx in contained:
                    if mid_idx != child_idx and child_idx in raw_contains[mid_idx]:
                        has_intermediate = True
                        break
                if not has_intermediate:
                    direct_children[parent_idx].add(child_idx)

        # Find root nodes: nodes that have no parent (not contained by anyone directly)
        has_parent: set[int] = set()
        for parent_idx, children in direct_children.items():
            for child_idx in children:
                has_parent.add(child_idx)

        root_indices = [i for i in range(n) if i not in has_parent]

        # Build intersecting relations index for spatial_role
        intersecting_pairs: set[tuple[int, int]] = set()
        for rel in spatial_relations:
            if rel.relation == "intersects":
                intersecting_pairs.add((rel.source_index, rel.target_index))

        # Recursive tree builder
        def build_node(idx: int, depth: int, ordinal: int, sibling_count: int) -> ASTNode:
            prim = primitives[idx]
            symbol = self._determine_symbol_type(prim)
            features = self._extract_drawing_features(prim)

            # Determine spatial role
            if direct_children[idx]:
                role = "container"
            elif idx in has_parent:
                role = "contained"
            elif any((idx, other) in intersecting_pairs for other in range(n) if other != idx):
                role = "intersecting"
            else:
                role = "peer"

            node = ASTNode(
                node_id=f"node_{idx}_{symbol}",
                symbol_type=symbol,
                primitive=prim,
                depth=depth,
                ordinal=ordinal,
                sibling_count=sibling_count,
                spatial_role=role,
                drawing_features=features,
            )

            # Build children sorted by drawing order (index)
            children_indices = sorted(direct_children[idx])
            child_count = len(children_indices)
            for ord_idx, child_idx in enumerate(children_indices):
                child_node = build_node(child_idx, depth + 1, ord_idx, child_count)
                node.children.append(child_node)

            return node

        # Single root: use it directly
        if len(root_indices) == 1:
            return build_node(root_indices[0], depth=0, ordinal=0, sibling_count=1)

        # Multiple roots: create virtual root
        root_count = len(root_indices)
        sorted_roots = sorted(root_indices)  # order by drawing order

        virtual_root = ASTNode(
            node_id="root_virtual",
            symbol_type="root",
            primitive=None,
            depth=-1,
            ordinal=0,
            sibling_count=1,
            spatial_role="container",
        )

        for ord_idx, root_idx in enumerate(sorted_roots):
            child_node = build_node(root_idx, depth=0, ordinal=ord_idx, sibling_count=root_count)
            virtual_root.children.append(child_node)

        return virtual_root

    @staticmethod
    def _primitive_bounding_size(primitive) -> float:
        """Estimate a primitive's spatial extent for disambiguation.
        Returns an area-like scalar: bigger value = bigger primitive.
        """
        if isinstance(primitive, Circle):
            r = primitive.radius or 0.0
            return math.pi * r * r
        if isinstance(primitive, Triangle) and len(primitive.vertices) >= 3:
            a, b, c = primitive.vertices[0], primitive.vertices[1], primitive.vertices[2]
            return 0.5 * abs(
                a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1])
            )
        if isinstance(primitive, RuneFire) and len(primitive.vertices) >= 3:
            a, b, c = primitive.vertices[0], primitive.vertices[1], primitive.vertices[2]
            return 0.5 * abs(
                a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1])
            )
        if isinstance(primitive, Segment):
            return math.hypot(
                primitive.end[0] - primitive.start[0],
                primitive.end[1] - primitive.start[1],
            )
        if isinstance(primitive, (Arrow, ArrowWithBase)):
            return math.hypot(
                primitive.tip[0] - primitive.tail[0],
                primitive.tip[1] - primitive.tail[1],
            )
        if isinstance(primitive, ZigZag) and primitive.vertices:
            xs = [v[0] for v in primitive.vertices]
            ys = [v[1] for v in primitive.vertices]
            return (max(xs) - min(xs)) * (max(ys) - min(ys))
        return 0.0

    @staticmethod
    def _triangle_area(a: tuple, b: tuple, c: tuple) -> float:
        """Aire d'un triangle par formule du shoelace."""
        return 0.5 * abs(
            a[0] * (b[1] - c[1])
            + b[0] * (c[1] - a[1])
            + c[0] * (a[1] - b[1])
        )


# ---------------------------------------------------------------------------
# Minimal validation test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.primitives import Circle, Triangle, Segment
    from client.magic.graph_geo import GraphGeo

    # Create 3 primitives: circle contains triangle contains segment
    big_circle = Circle(
        _points=[],
        center=(200.0, 200.0),
        radius=150.0,
    )
    mid_triangle = Triangle(
        _points=[],
        vertices=[(170.0, 230.0), (230.0, 230.0), (200.0, 180.0)],
    )
    small_segment = Segment(
        start=(190.0, 210.0),
        end=(210.0, 210.0),
    )

    # Build graph
    graph = GraphGeo()
    graph.add_node(big_circle)
    graph.add_node(mid_triangle)
    graph.add_node(small_segment)

    # Build AST
    builder = ASTBuilder()
    ast = builder.build(graph)

    # Print tree
    def print_tree(node: "ASTNode", indent: int = 0) -> None:
        prefix = "  " * indent
        print(f"{prefix}[{node.node_id}] type={node.symbol_type} depth={node.depth} "
              f"ordinal={node.ordinal} role={node.spatial_role} "
              f"children={len(node.children)}")
        for child in node.children:
            print_tree(child, indent + 1)

    print("=== SpellAST ===")
    print(f"depth={ast.depth}, node_count={ast.node_count}, "
          f"relations={len(ast.spatial_relations)}")
    print()
    if ast.root:
        print_tree(ast.root)

    # Assertions
    assert ast.depth == 2, f"Expected depth=2, got {ast.depth}"
    assert ast.root is not None
    assert ast.root.symbol_type == "circle", f"Expected root=circle, got {ast.root.symbol_type}"
    assert len(ast.root.children) == 1
    assert ast.root.children[0].symbol_type == "triangle", (
        f"Expected child=triangle, got {ast.root.children[0].symbol_type}"
    )
    assert len(ast.root.children[0].children) == 1
    assert ast.root.children[0].children[0].symbol_type == "segment"
    assert ast.node_count == 3

    print()
    print("All assertions passed.")