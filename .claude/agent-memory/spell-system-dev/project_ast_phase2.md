---
name: AST Phase 2 Symbol Rules
description: PropertyBag-based symbol rules system - each symbol emits continuous tagged properties, no predefined spells
type: project
---

Phase 2 of emergent spell system completed on 2026-04-09.

Key design: symbols emit PropertyBag entries (tagged with domain/axis/scope) instead of mapping to predefined spells. Emergence comes from combining these continuous properties in the resolver (Phase 3).

**Why:** Predefined spell lists create a combinatorial explosion. Continuous property bags let N symbols produce unbounded combinations via weighted sums, without any cross-symbol logic in the rules themselves.

**How to apply:** When building Phase 3 (resolver), consume PropertyBags via `bag.net(domain, axis)` for weighted sums. Rules are context-aware (depth modulates output) but never reference other symbol types directly. New symbols are added by registering a single function in SymbolRegistry.
