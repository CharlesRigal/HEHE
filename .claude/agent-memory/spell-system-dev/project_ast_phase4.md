---
name: AST Phase 4 Integration
description: Wiring the AST pipeline into the live game - replacing SpellChainBuilder with ASTBuilder+ASTResolver in playing.py
type: project
---

Phase 4 completed on 2026-04-10.

Integration: the AST emergent pipeline is now the live cast path.

**Files modified:**
- `client/core/game.py` — added `ast_builder` and `ast_resolver` as instance fields in `__init__`; added `cast_ast_spell(net_spec: dict)` method that sends the compact dict directly to the server
- `client/game_state/playing.py` — replaced the `SpellChainBuilder` block with: `ASTBuilder.build(graph)` → `ASTResolver.resolve(ast)` → `params_to_network_spec(resolved)` → `game.cast_ast_spell(net_spec)`

**Why:** The 3 prior phases built the full pipeline but never connected it to the game loop. The old `SpellChainBuilder` (discrete lookup) was the only thing being called at cast time.

**How to apply:** The old `SpellChainBuilder` / `spell_chain.py` / `spell_spec.py` (client-side) still exist but are no longer called. The server already handled `{"t":"s"}` via `add_spell_cast_from_spec` → `cast_parametric_spell` — no server changes needed.

Key flow: draw strokes → geometry_analyzer → add_node → ASTBuilder.build(graph) → ASTResolver.resolve → params_to_network_spec → net.send({"t":"s",...}) → server cast_parametric_spell.
