---
name: AST Phase 1 Implementation
description: SpellAST and ASTBuilder implemented using spatial containment from GraphGeo relations
type: project
---

Phase 1 of emergent spell system AST completed on 2026-04-09.

Key design decision: GraphGeo._contains() can produce mutual containment (A contains B AND B contains A) when a small triangle's center check falsely claims it contains a large circle. ASTBuilder resolves this by comparing bounding sizes and keeping only the larger primitive as container.

**Why:** The existing GraphGeo containment logic uses point-in-polygon for triangles and center-distance for circles, which can produce false mutual containment. Fixing this in ASTBuilder (not GraphGeo) avoids breaking existing spell chain logic.

**How to apply:** Any future code that consumes containment relations from GraphGeo should be aware of this edge case. The bounding-size disambiguation pattern in ASTBuilder._build_tree_from_containment is the reference approach.
