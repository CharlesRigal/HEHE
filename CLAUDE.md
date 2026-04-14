# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the project

```bash
# Start the server
python -m server.server_run

# Start the client
python -m client.main

# Run a module's built-in validation test (each key module has an if __name__ == "__main__" block)
python -m client.magic.ast.ast_builder
python -m client.magic.ast.symbol_registry
python -m client.magic.resolver.resolver
```

The server reads config from `server/config.yaml` (host, port, tick_rate, player_speed). No external test runner is configured — validation is done via the `__main__` blocks in each module.

## Architecture

This is a multiplayer wizard game: a Pygame client communicates with an asyncio TCP server via newline-delimited JSON.

### Network protocol (README.md)
- `{"t": "ping"}` / `{"t": "pong"}` — keepalive
- `{"t": "s", ...}` — cast a spell by parametric spec (compact format)
- `{"t": "in", "k": int}` — player input (key bitmask)
- `{"t": "join", "map": str}` — join a game instance

### Client-side spell pipeline

Drawing strokes go through this pipeline:

```
Strokes
  → geometry_analyzer.py     (raw stroke → shape candidates)
  → recognition/pipeline.py  (dollar-one + complex composers → primitives)
  → primitives.py             (Circle, Arrow, Triangle, Segment, ZigZag, RuneFire, ...)
  → graph_geo.py (GraphGeo)   (spatial relations: contains, near, intersects)
  → ast/ast_builder.py        (containment tree → SpellAST)
  → ast/symbol_rules.py       (per-symbol rules → PropertyBag with tagged entries)
  → resolver/resolver.py      (3-pass resolution → ResolvedSpell with continuous params)
  → resolver/resolved_spell.py (params_to_network_spec → compact dict {"t":"s",...})
  → TCP → server
```

The **old pipeline** (`spell_chain.py` → `spell_spec.py`) still exists and uses ring-ordering + a rune registry. The **new AST pipeline** (`ast/` + `resolver/`) is the emergent system under development.

### AST / resolver design (the emergent spell system)

The key idea: instead of a lookup table `(element, behavior) → spell_id`, every drawn symbol contributes `PropertyEntry` objects tagged with `(domain, axis, scope)` (e.g. `energy.magnitude.self`). The resolver runs 3 passes:

1. **Bottom-up** — children resolve first, child bags flow into parents
2. **Top-down** — parent entries scoped `children`/`global` propagate down
3. **Cross-node** — `interaction_algebra.py` computes trigonometric interference between peer nodes linked by spatial relations

Final aggregation maps the merged `PropertyBag` to continuous params (`speed`, `power`, `spread`, `element`, `behavior`, etc.) sent to the server.

Adding a new symbol = add a `rule_xxx` function in `symbol_rules.py` and register it in `symbol_registry.py`. No other files need to change.

### Server-side spell routing

```
TCP message {"t":"s",...}
  → spec_from_network()       (server/magic/spell_spec.py)
  → route_spec()              (server/magic/spec_router.py)
  → spell_id → GameInstance   (server/game_instance.py dispatches to server/spells/)
```

`spec_router.py` maps `(element, behavior)` pairs to spell implementations. Only 3 spell implementations exist today: `fire_projectile`, `fire_rune`, `lightning_rune`. Anything unmapped falls back to `fire_rune`.

### Key data structures

- `PropertyBag` — list of `PropertyEntry(tag, value, weight, source_node_id)`. `net(domain, axis)` = weighted sum. `merge()` returns a new bag.
- `PropertyTag(domain, axis, scope)` — tags entries. Domains: `energy`, `space`, `time`, `motion`, `polarity`. Scopes: `self`, `children`, `parent`, `siblings`, `global`.
- `SpellAST` — tree of `ASTNode` built from containment. Virtual root node (`symbol_type="root"`) created when multiple top-level shapes exist.
- `ResolvedSpell` — final output with `params` dict and `property_snapshot` for debugging.
- `ServerSpellSpec` — server-side deserialized spell with typed fields (element, behavior, direction, power, etc.).