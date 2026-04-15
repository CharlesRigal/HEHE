"""
ast_builder.py — Construction du SpellAST depuis un GraphGeo.

Feature extraction universelle : aucune branche par type de primitive
pour les métriques géométriques. Seul l'accès aux points bruts dépend du type.
"""
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

# Références de normalisation
_REF_AREA  = 300.0 * 300.0   # px²  — bounding box 300×300
_REF_PERIM = 600.0            # px   — périmètre de référence


class ASTBuilder:
    """Construit un SpellAST à partir d'un GraphGeo en utilisant la containance spatiale."""

    def build(self, graph) -> SpellAST:
        nodes = graph.iter_nodes()
        primitives = [n.primitive for n in nodes]
        relations = graph.build_spatial_relations()

        root = self._build_tree_from_containment(primitives, relations)

        all_nodes: list[ASTNode] = []
        max_depth = 0
        if root is not None:
            queue = [root]
            while queue:
                current = queue.pop(0)
                if current.symbol_type != "root":
                    all_nodes.append(current)
                if current.depth > max_depth:
                    max_depth = current.depth
                queue.extend(current.children)

        if root is not None and root.symbol_type == "root":
            max_depth = max((n.depth for n in all_nodes), default=0)

        return SpellAST(
            root=root,
            all_nodes=all_nodes,
            depth=max_depth,
            node_count=len(all_nodes),
            spatial_relations=relations,
        )

    # ------------------------------------------------------------------
    # Extraction de features géométriques universelles
    # ------------------------------------------------------------------

    def _get_primitive_points(self, primitive) -> list[tuple[float, float]]:
        """
        Retourne les points bruts représentatifs de la primitive.
        Seul endroit où le type de primitive est inspecté.
        """
        if isinstance(primitive, Circle):
            cx, cy = primitive.center
            r = primitive.radius or 1.0
            n = 32
            pts = [(cx + r * math.cos(2 * math.pi * i / n),
                    cy + r * math.sin(2 * math.pi * i / n))
                   for i in range(n)]
            pts.append(pts[0])          # cercle fermé
            return pts

        if isinstance(primitive, (Arrow, ArrowWithBase)):
            # Shaft uniquement : tail→tip pour préserver la directionnalité pure
            return [tuple(primitive.tail), tuple(primitive.tip)]

        if isinstance(primitive, Triangle):
            v = list(primitive.vertices)
            return v + [v[0]]           # forme fermée

        if isinstance(primitive, Segment):
            return [tuple(primitive.start), tuple(primitive.end)]

        if isinstance(primitive, ZigZag):
            return [tuple(v) for v in primitive.vertices]

        if isinstance(primitive, RuneFire):
            pts = [tuple(v) for v in primitive.vertices]
            # Fermer si les extrémités sont proches
            if pts and math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 30.0:
                pts.append(pts[0])
            return pts

        return []

    def _extract_universal_features(self, primitive) -> dict[str, float]:
        """
        Extrait des features géométriques universelles.
        Fonctionne identiquement pour tout type de primitive.
        """
        pts = self._get_primitive_points(primitive)

        if len(pts) < 2:
            return {
                "area_n": 0.0, "scale_n": 0.0, "compactness": 0.0,
                "elongation": 1.0, "closure": 0.0, "linearity": 0.0,
                "angularity": 0.0, "direction_n": 0.0, "convexity": 1.0,
                "is_directional": 0.0,
            }

        # ── Périmètre ─────────────────────────────────────────────────
        perimeter = sum(
            math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(len(pts) - 1)
        )
        perimeter = max(perimeter, 1e-6)

        # ── Aire (shoelace) ────────────────────────────────────────────
        area = abs(sum(
            pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
            for i in range(len(pts) - 1)
        )) * 0.5

        # ── Normalisations ─────────────────────────────────────────────
        area_n     = min(1.0, area / _REF_AREA)
        perimeter_n = min(1.0, perimeter / _REF_PERIM)
        scale_n    = max(area_n, perimeter_n * 0.5)

        # ── Compactness (rondeur) ──────────────────────────────────────
        # = 1 pour un cercle parfait, → 0 pour une ligne
        compactness = min(1.0, 4.0 * math.pi * area / (perimeter ** 2))

        # ── Elongation (PCA) ───────────────────────────────────────────
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        n  = len(xs)
        sxx = sum((x - cx) ** 2 for x in xs) / n
        sxy = sum((xs[i] - cx) * (ys[i] - cy) for i in range(n)) / n
        syy = sum((y - cy) ** 2 for y in ys) / n

        trace = sxx + syy
        det   = sxx * syy - sxy * sxy
        disc  = max(0.0, trace * trace / 4.0 - det)
        l1 = trace / 2.0 + math.sqrt(disc)
        l2 = max(trace / 2.0 - math.sqrt(disc), 0.0)
        elongation = min(20.0, math.sqrt(l1 / max(l2, 1e-8)))

        # ── Direction principale (PCA, angle de l'axe majeur) ─────────
        pca_angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy)

        # Pour les formes ouvertes, préférer la direction endpoints
        gap = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
        if gap > perimeter * 0.05:
            ep_angle = math.atan2(pts[-1][1] - pts[0][1], pts[-1][0] - pts[0][0])
            direction_n = (math.degrees(ep_angle) % 360.0) / 360.0
        else:
            direction_n = (math.degrees(pca_angle) % 360.0) / 360.0

        # ── Closure ────────────────────────────────────────────────────
        closure = max(0.0, 1.0 - gap / perimeter)

        # ── Linearity ─────────────────────────────────────────────────
        linearity = min(1.0, gap / perimeter)

        # ── Angularité (fraction de coins aigus, virage > 30°) ────────
        sharp = 0
        valid = 0
        for i in range(1, len(pts) - 1):
            ax = pts[i][0] - pts[i - 1][0];  ay = pts[i][1] - pts[i - 1][1]
            bx = pts[i + 1][0] - pts[i][0];  by = pts[i + 1][1] - pts[i][1]
            la = math.hypot(ax, ay);          lb = math.hypot(bx, by)
            if la < 1e-6 or lb < 1e-6:
                continue
            dot = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
            angle_between = math.degrees(math.acos(dot))
            valid += 1
            if angle_between < 150.0:   # virage > 30°
                sharp += 1
        angularity = sharp / max(valid, 1)

        # ── Convexité (fraction de virages cohérents) ─────────────────
        signs = []
        for i in range(1, len(pts) - 1):
            ax = pts[i][0] - pts[i - 1][0];  ay = pts[i][1] - pts[i - 1][1]
            bx = pts[i + 1][0] - pts[i][0];  by = pts[i + 1][1] - pts[i][1]
            cross = ax * by - ay * bx
            if abs(cross) > 1e-6:
                signs.append(1 if cross > 0 else -1)
        if signs:
            pos = sum(1 for s in signs if s > 0)
            convexity = max(pos, len(signs) - pos) / len(signs)
        else:
            convexity = 1.0

        # ── is_directional : vraie tête directionnelle (flèche) ───────
        # Propriété géométrique : présence d'une arrowhead reconnue
        is_directional = 1.0 if isinstance(primitive, (Arrow, ArrowWithBase)) else 0.0

        features: dict[str, float] = {
            "area_n":        area_n,
            "scale_n":       scale_n,
            "compactness":   compactness,
            "elongation":    elongation,
            "closure":       closure,
            "linearity":     linearity,
            "angularity":    angularity,
            "direction_n":   direction_n,
            "convexity":     convexity,
            "is_directional": is_directional,
        }
        conf = getattr(primitive, "confidence", None)
        if conf is not None:
            features["confidence"] = float(conf)
        return features

    # ------------------------------------------------------------------
    # Détermination du symbol_type (pour la containance et le debug)
    # ------------------------------------------------------------------

    def _determine_symbol_type(self, primitive) -> str:
        kind = getattr(primitive, "kind", None)
        if kind is not None:
            return str(kind)
        type_map = {
            Circle: "circle", Arrow: "arrow", ArrowWithBase: "arrow_with_base",
            Triangle: "triangle", Segment: "segment", ZigZag: "zigzag",
            RuneFire: "rune_fire",
        }
        for cls, name in type_map.items():
            if isinstance(primitive, cls):
                return name
        return "unknown"

    # ------------------------------------------------------------------
    # Construction de l'arbre AST par containance
    # ------------------------------------------------------------------

    def _build_tree_from_containment(
        self,
        primitives: list[Any],
        spatial_relations: list[Any],
    ) -> ASTNode | None:
        if not primitives:
            return None

        n = len(primitives)
        sizes = [self._primitive_bounding_size(p) for p in primitives]

        raw_contains: dict[int, set[int]] = {i: set() for i in range(n)}
        for rel in spatial_relations:
            if rel.relation == "contains":
                raw_contains[rel.source_index].add(rel.target_index)

        for i in range(n):
            for j in range(i + 1, n):
                if j in raw_contains[i] and i in raw_contains[j]:
                    if sizes[i] >= sizes[j]:
                        raw_contains[j].discard(i)
                    else:
                        raw_contains[i].discard(j)

        direct_children: dict[int, set[int]] = {i: set() for i in range(n)}
        for parent_idx in range(n):
            contained = raw_contains[parent_idx]
            for child_idx in contained:
                has_intermediate = any(
                    mid_idx != child_idx and child_idx in raw_contains[mid_idx]
                    for mid_idx in contained
                )
                if not has_intermediate:
                    direct_children[parent_idx].add(child_idx)

        has_parent: set[int] = set()
        for children in direct_children.values():
            has_parent.update(children)

        root_indices = [i for i in range(n) if i not in has_parent]

        intersecting_pairs: set[tuple[int, int]] = set()
        for rel in spatial_relations:
            if rel.relation == "intersects":
                intersecting_pairs.add((rel.source_index, rel.target_index))

        def build_node(idx: int, depth: int, ordinal: int, sibling_count: int) -> ASTNode:
            prim   = primitives[idx]
            symbol = self._determine_symbol_type(prim)
            feats  = self._extract_universal_features(prim)

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
                drawing_features=feats,
            )

            children_indices = sorted(direct_children[idx])
            for ord_idx, child_idx in enumerate(children_indices):
                child_node = build_node(child_idx, depth + 1, ord_idx, len(children_indices))
                node.children.append(child_node)

            return node

        if len(root_indices) == 1:
            return build_node(root_indices[0], depth=0, ordinal=0, sibling_count=1)

        virtual_root = ASTNode(
            node_id="root_virtual",
            symbol_type="root",
            primitive=None,
            depth=-1,
            ordinal=0,
            sibling_count=1,
            spatial_role="container",
        )
        sorted_roots = sorted(root_indices)
        for ord_idx, root_idx in enumerate(sorted_roots):
            child_node = build_node(root_idx, depth=0, ordinal=ord_idx, sibling_count=len(sorted_roots))
            virtual_root.children.append(child_node)

        return virtual_root

    @staticmethod
    def _primitive_bounding_size(primitive) -> float:
        if isinstance(primitive, Circle):
            r = primitive.radius or 0.0
            return math.pi * r * r
        if isinstance(primitive, (Triangle, RuneFire)) and len(primitive.vertices) >= 3:
            a, b, c = primitive.vertices[0], primitive.vertices[1], primitive.vertices[2]
            return 0.5 * abs(a[0]*(b[1]-c[1]) + b[0]*(c[1]-a[1]) + c[0]*(a[1]-b[1]))
        if isinstance(primitive, Segment):
            return math.hypot(primitive.end[0]-primitive.start[0], primitive.end[1]-primitive.start[1])
        if isinstance(primitive, (Arrow, ArrowWithBase)):
            return math.hypot(primitive.tip[0]-primitive.tail[0], primitive.tip[1]-primitive.tail[1])
        if isinstance(primitive, ZigZag) and primitive.vertices:
            xs = [v[0] for v in primitive.vertices]
            ys = [v[1] for v in primitive.vertices]
            return (max(xs) - min(xs)) * (max(ys) - min(ys))
        return 0.0

    @staticmethod
    def _triangle_area(a: tuple, b: tuple, c: tuple) -> float:
        return 0.5 * abs(a[0]*(b[1]-c[1]) + b[0]*(c[1]-a[1]) + c[0]*(a[1]-b[1]))


# ---------------------------------------------------------------------------
# Test de validation minimal
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.primitives import Circle, Triangle, Segment
    from client.magic.graph_geo import GraphGeo

    big_circle = Circle(_points=[], center=(200.0, 200.0), radius=150.0)
    mid_triangle = Triangle(_points=[], vertices=[(170.0, 230.0), (230.0, 230.0), (200.0, 180.0)])
    small_segment = Segment(start=(190.0, 210.0), end=(210.0, 210.0))

    graph = GraphGeo()
    graph.add_node(big_circle)
    graph.add_node(mid_triangle)
    graph.add_node(small_segment)

    builder = ASTBuilder()
    ast = builder.build(graph)

    def print_tree(node: "ASTNode", indent: int = 0) -> None:
        prefix = "  " * indent
        print(f"{prefix}[{node.node_id}] type={node.symbol_type} depth={node.depth} "
              f"role={node.spatial_role} children={len(node.children)}")
        feats = node.drawing_features
        print(f"{prefix}  compactness={feats.get('compactness',0):.3f} "
              f"elongation={feats.get('elongation',1):.2f} "
              f"closure={feats.get('closure',0):.3f} "
              f"linearity={feats.get('linearity',0):.3f} "
              f"angularity={feats.get('angularity',0):.3f} "
              f"is_directional={feats.get('is_directional',0):.0f}")
        for child in node.children:
            print_tree(child, indent + 1)

    print("=== SpellAST ===")
    if ast.root:
        print_tree(ast.root)

    assert ast.root is not None
    assert ast.root.symbol_type == "circle"
    assert len(ast.root.children) == 1
    assert ast.root.children[0].symbol_type == "triangle"

    # Vérifier les features géométriques du cercle
    circle_feats = ast.root.drawing_features
    assert circle_feats["compactness"] > 0.9, f"Circle should be compact, got {circle_feats['compactness']:.3f}"
    assert circle_feats["closure"] > 0.9, f"Circle should be closed, got {circle_feats['closure']:.3f}"
    assert circle_feats["is_directional"] == 0.0

    # Vérifier que la flèche serait directionnelle
    arrow = Arrow(_points=[], tail=(0.0, 0.0), tip=(100.0, 0.0),
                  left_head=(90.0, -10.0), right_head=(90.0, 10.0))
    arrow_feats = builder._extract_universal_features(arrow)
    assert arrow_feats["is_directional"] == 1.0
    assert arrow_feats["linearity"] > 0.9, f"Arrow should be linear, got {arrow_feats['linearity']:.3f}"

    # Vérifier que le segment n'est pas directionnel
    seg = Segment(start=(0.0, 0.0), end=(100.0, 0.0))
    seg_feats = builder._extract_universal_features(seg)
    assert seg_feats["is_directional"] == 0.0
    assert seg_feats["linearity"] > 0.9

    print("\nAll ast_builder assertions passed.")
