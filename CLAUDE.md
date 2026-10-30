# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Source of truth

- **README.md is the spec.** It defines the spell-drawing rules (circle C*, emblem E*, signs F*, reading L*, quality, support S*). Read it before any spell-system work.
- **plan.md is a draft**, not normative. Never treat it as a requirement.
- The user speaks French; README and docs are in French.

## Running the project

```bash
python -m server.server_run          # server (listens on 9000; server/config.yaml holds tick_rate, player_speed)
python -m client.main                # pygame client
python -m unittest discover -s tests -v   # test suite (headless, also run by .github/workflows/tests.yml)
```

CI uses Python 3.13, `PyYAML`, `numpy`, `pygame-ce==2.5.8`, `SDL_VIDEODRIVER=dummy`.

In-game: right-click opens/closes the drawing board, left-click draws; the spell is cast when the circle closes. Map `elements_lab` is the sandbox for the element world.

## Current state of the code

The spell system follows the README rules (plan in `plan.md`, draft). The old AST pipeline was deleted in `9c70177`; the old torch/affinity system was removed (README M0 forbids rules naming elements or entities).

- Emblem and sign glyphs in `client/magic/templates.py` are **placeholders** until the real glyphs are drawn.
- `client/ui/grimoire.py` is unused and still assumes the old spell spec.
- Two enemy AI tests in `tests/test_gameplay.py` fail independently of the spell system.

## Architecture

Pygame client ↔ asyncio TCP server, newline-delimited JSON. Server is authoritative for simulation.

### Network messages (`"t"` field)
- client → server: `ping`, `join {map}`, `quit`, `list_maps`, `in {k: bitmask, seq}`, `chat`, `s` (spell reading: `R`, `q`, `e`, `eq`, `ink`, `signs[]` — see README)
- server → client: `welcome {your_id}`, `pong`, `map_data`, `game_state` (incl. `world`, `spells`), `game_update` (incl. sparse `world` cells and `spells` at ≤10 Hz), `player_joined`, `player_left`, `maps_list`, `chat`

### Server (`server/`)
- `server_run.py` — connection handling and message routing.
- `game_instance.py` — one instance per map: players, enemies, interactive entities, world grid, active spells, input processing, tick loop. `add_spell_cast_from_spec` centers a spell on the caster (S1).
- `world/grid.py` — `WorldGrid`: numpy cells (water, earth, air, signed heat, charge, light), conservative transport, diffusion, walls, M1 heat thresholds.
- `world/spell.py` — message validation, `ActiveSpell` field built from signs relative to the circle center, element creation (E4), `combine_flows`.
- `entities/components.py` — composable components: `EntityBody` (position, velocity, mass), `EntityStates`, `EntityReactive`, `EntityCombat`, `EnemyAI`.
- `entities/interactive.py` — crystals, altars, plates, doors loaded from map YAML (no element reactions).
- `systems/` — `physics_system`, `movement_system`, `enemy_ai_system`, `proximity_system`, `world_system` (spells → grid → matter pushes bodies), `inventory`.
- `maps/*.yaml` — maps, including `elements_lab` and `levitation_puzzle`; optional `world:` entries seed the grid.
- `save/` — player persistence (`save.yml`).

### Client (`client/`)
- `core/` — game loop (`game.py`), state handling, interpolation, settings.
- `entities/` — local/remote players, enemies, portal, interactive entity rendering, camera.
- `game_state/playing.py`, `graphics/`, `gui/`, `ui/` (grimoire, health bar).
- `network/network.py` — threaded socket client with send/recv queues.
- `magic/` — pentacle reading: `grouping` (contact), `circle` (closed round loop), `dollar_p` ($P with rotation sweep), `templates`, `reader`, `spell_message`, `drawing_board` (input, reading in a worker thread).
- `graphics/world_renderer.py` — draws the world grid and active spell rings.

## Spell system design (README summary)

Pipeline: `strokes → grouping by contact → role by position → $P / measurement → field map → server grid simulation`.

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
