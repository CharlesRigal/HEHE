from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ASTNode:
    node_id: str                          # identite stable ex: "node_0_circle"
    symbol_type: str                      # "circle", "arrow", "triangle", "segment", "zigzag", "rune_fire"
    primitive: Any                        # la primitive geometrique brute
    depth: int                            # distance depuis la racine (0 = racine)
    ordinal: int                          # position gauche-droite parmi les siblings
    sibling_count: int                    # total des siblings a ce niveau
    children: list[ASTNode] = field(default_factory=list)
    spatial_role: str = "peer"            # "container" | "contained" | "peer" | "intersecting"
    drawing_features: dict[str, float] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)  # peuple pendant la resolution


@dataclass
class SpellAST:
    root: ASTNode | None
    all_nodes: list[ASTNode]              # cache de traversal a plat
    depth: int                            # profondeur maximale de l'arbre
    node_count: int                       # nombre total de symboles
    spatial_relations: list[Any]          # liste des SpatialRelation de GraphGeo