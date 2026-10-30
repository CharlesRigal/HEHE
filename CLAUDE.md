# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source of truth

- **README.md is the spec.** It defines the spell-drawing rules (circle C*, emblem E*, signs F*, reading L*, quality, support S*). Read it before any spell-system work.
- **plan.md is a draft**, not normative. Never treat it as a requirement.
- The user speaks French; README and docs are in French.

## Running the project

```bash
python -m server.server_run          # server (config: server/config.yaml — host, port, tick_rate, player_speed)
python -m client.main                # pygame client
python -m unittest discover -s tests -v   # test suite (headless, also run by .github/workflows/tests.yml)
```

CI uses Python 3.13, `PyYAML`, `pygame-ce==2.5.8`, `SDL_VIDEODRIVER=dummy`.

## Current state of the code

The old spell pipeline (`client/magic/`: recognition, $1, heuristics, AST, resolver; `server/magic/`, `server/spells/`, `server/effects/`) was **deleted** in commit `9c70177`. The spell system is being redesigned from the README rules and does not exist in code yet.

Leftovers to be aware of:
- `server/server_run.py` still routes `{"t": "s"}` to `GameInstance.add_spell_cast_from_spec`, which no longer exists.
- `server/systems/effect_tick_system.py` has its effect-runtime imports commented out.
- `client/ui/grimoire.py` still assumes `{"t": "s", ...}` spell specs.

## Architecture

Pygame client ↔ asyncio TCP server, newline-delimited JSON. Server is authoritative for simulation.

### Network messages (`"t"` field)
- client → server: `ping`, `join {map}`, `quit`, `list_maps`, `in {k: bitmask, seq}`, `chat`, `s` (spell — format to be redefined)
- server → client: `welcome {your_id}`, `pong`, `map_data`, `game_state`, `game_update`, `player_joined`, `player_left`, `maps_list`, `chat`

### Server (`server/`)
- `server_run.py` — connection handling and message routing.
- `game_instance.py` — one instance per map: players, enemies, interactive entities, input processing, tick loop. Exposes `apply_force` / `apply_force_in_radius`.
- `entities/components.py` — composable components: `EntityBody` (position, velocity, mass), `EntityAffinities`, `EntityStates`, `EntityReactive`.
- `entities/interactive.py` — torches, braziers, plates, doors loaded from map YAML with threshold reactions.
- `systems/` — `physics_system`, `movement_system`, `enemy_ai_system`, `proximity_system`, `effect_tick_system`, `inventory`.
- `maps/*.yaml` — maps, including puzzle maps (`torch_puzzle`, `levitation_puzzle`).
- `save/` — player persistence (`save.yml`).

### Client (`client/`)
- `core/` — game loop (`game.py`), state handling, interpolation, settings.
- `entities/` — local/remote players, enemies, portal, interactive entity rendering, camera.
- `game_state/playing.py`, `graphics/`, `gui/`, `ui/` (grimoire, health bar).
- `network/network.py` — threaded socket client with send/recv queues.

## Spell system design (README summary)

Pipeline target: `strokes → grouping by contact → role by position → $P / measurement → field map → server grid simulation`.

- **Reading happens once, at circle closure** (no real-time feedback), on the **client** (no anti-cheat).
- **Contact = rendering**: strokes touch iff distance ≤ rendered stroke thickness. Touching strokes = one symbol; distinct symbols never touch.
- **Roles by position**: enclosing closed loop = circle (multi-stroke allowed); symbol nearest center = emblem; others = signs.
- **$P recognizer for emblem and signs**. Signs use a rotation sweep; templates annotate head/base; best angle = orientation; base/head ambiguity (θ vs θ+180°) = dead sign. Everything else (position, size, circle) is measured.
- **Quality** per symbol = min of its criteria; below threshold the symbol is dead.
- **A spell acts only on its own element**, never directly on objects. The emblem creates its element (quantity ∝ circle size); traction pulls existing element. Only cost = ink per stroke.
- **Pentacle = field map** centered on the circle center: each sign samples a field (vector: direction/traction; signed scalar: convergence(+)/dispersion(−); suspension; local duration: repetition), softly interpolated. Sign distance from center maps to the same relative radius in the effect zone ("dehors agit dehors"). Sign size = coverage, not force; force comes from circle size.
- **World is 2D.** Planned simulation: grid of cells holding element quantities (water, earth, air, signed temperature, charge, light). Ice = negative temperature (fire and ice emblems share one quantity). Matter states change by **temperature thresholds**, not recipes.
- **Spell end releases** accumulated element (side effects intended).
- **Never** `pattern → effect` lookup tables.

## Working conventions

- Don't raise balancing limits/caps in design discussions; they are added later.
- Prefer the simplest physical model; new physics must be expressible as thresholds on cell quantities.
