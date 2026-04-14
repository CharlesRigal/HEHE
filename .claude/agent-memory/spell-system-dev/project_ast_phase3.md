---
name: AST Phase 3 Resolver
description: ASTResolver with 3-pass emergence engine producing ResolvedSpell with continuous params for server
type: project
---

Phase 3 implemented: ASTResolver in `client/magic/resolver/`.

Three files created:
- `resolved_spell.py` — ResolvedSpell dataclass + params_to_network_spec serialization
- `interaction_algebra.py` — pure functions for interference (trig-based), depth weighting (gaussian), bag accumulation
- `resolver.py` — ASTResolver with 3 passes: bottom-up, top-down propagation, cross-node interference

**Why:** The 3-pass architecture enables emergence — same symbol contributes differently based on position (depth weight), parent context (top-down propagation of scope="children"/"global" entries), and spatial neighbors (cross-node interference via trig formulas).

**How to apply:** The resolver is symbol-agnostic — it only sees PropertyBags and tags. Adding new behaviors means adding new symbol rules in Phase 2, not modifying the resolver. The params dict maps directly to ServerSpellSpec fields via params_to_network_spec.

Key design decisions:
- PropertyBag.query doesn't support wildcard on domain — top-down pass filters entries directly
- SpatialRelation uses source_index/target_index (int) — resolver builds index->node_id map from node_id pattern "node_{idx}_{type}"
- Behavior determined by dominance scoring (velocity->projectile, barrier->wall, spread->aoe, rate+velocity->beam)
- Element mapped from continuous energy.element value (>0.75=fire, >0.35=lightning, >0.1=arcane, <-0.1=ice)
