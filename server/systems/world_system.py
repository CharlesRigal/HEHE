"""WorldSystem : avance les sorts actifs et la grille, puis pousse les corps.

Un sort ne touche jamais un corps directement (README, principe 5). Le corps
recoit la poussee de la matiere qui s'ecoule dans sa cellule :
force = K * quantite * vitesse, pour l'eau, la terre et l'air. L'air ambiant
compte toujours : un sort de vent pousse sans rien creer.
"""
from __future__ import annotations

from typing import Any

from server.world.grid import AMBIENT_AIR, MATTER_FIELDS, Flow
from server.world.spell import combine_flows

PUSH_PER_UNIT = 3.0


class WorldSystem:
    def tick(self, world: Any, dt: float, now: float) -> None:
        _ = now
        grid = world.world_grid
        spells = world.active_spells
        flows = combine_flows(grid, spells)
        self._push_bodies(world, flows)
        grid.step(dt, flows)
        for spell in spells:
            spell.advance(dt)
        # C7 : un sort termine disparait ; la physique naturelle relache l'element.
        world.active_spells = [spell for spell in spells if not spell.is_over()]

    @staticmethod
    def _push_bodies(world: Any, flows: dict[str, Flow]) -> None:
        matter = [name for name in MATTER_FIELDS if name in flows]
        if not matter:
            return
        grid = world.world_grid
        for actor in [*world.players.values(), *world.entities]:
            body = actor.body
            if body.static:
                continue
            cell = grid.cell_of(body.x, body.y)
            if cell is None:
                continue
            fx = fy = 0.0
            for name in matter:
                amount = float(grid.fields[name][cell])
                if name == "air":
                    amount += AMBIENT_AIR
                flow = flows[name]
                fx += PUSH_PER_UNIT * amount * float(flow.vx[cell])
                fy += PUSH_PER_UNIT * amount * float(flow.vy[cell])
            if fx or fy:
                world.apply_force(actor.id, fx, fy)
