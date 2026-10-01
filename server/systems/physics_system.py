"""Simulation physique autoritaire et index spatial leger.

Le systeme ne connait ni sorts ni elements. Les producteurs de magie futurs
appelleront seulement ``GameInstance.apply_force*``.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class ActiveForce:
    target_id: str
    fx: float
    fy: float
    remaining: float


class SpatialGrid:
    """Grille uniforme : broad phase partagee par physique et proximite."""
    def __init__(self, cell_size: float = 96.0) -> None:
        self.cell_size = cell_size
        self.cells: dict[tuple[int, int], list[Any]] = defaultdict(list)

    def rebuild(self, actors: list[Any]) -> None:
        self.cells.clear()
        for actor in actors:
            body = actor.body
            self.cells[(int(body.x // self.cell_size), int(body.y // self.cell_size))].append(actor)

    def query_circle(self, x: float, y: float, radius: float) -> list[Any]:
        start_x = int((x - radius) // self.cell_size)
        end_x = int((x + radius) // self.cell_size)
        start_y = int((y - radius) // self.cell_size)
        end_y = int((y + radius) // self.cell_size)
        found: list[Any] = []
        seen: set[str] = set()
        for cx in range(start_x, end_x + 1):
            for cy in range(start_y, end_y + 1):
                for actor in self.cells.get((cx, cy), ()):
                    if actor.id not in seen:
                        seen.add(actor.id)
                        found.append(actor)
        return found


class PhysicsSystem:
    MAX_ACTIVE_FORCES = 128
    MAX_FORCE = 2400.0
    MAX_SPEED = 900.0
    DAMPING_PER_SECOND = 5.0
    VELOCITY_EPSILON = 1.0

    def __init__(self) -> None:
        self.active_forces: list[ActiveForce] = []
        self.grid = SpatialGrid()

    @staticmethod
    def actors(world: Any) -> list[Any]:
        return [*world.players.values(), *world.entities]

    def apply_force(self, world: Any, target_id: str, fx: float, fy: float, duration: float = 0.0) -> bool:
        if len(self.active_forces) >= self.MAX_ACTIVE_FORCES:
            return False
        magnitude = math.hypot(fx, fy)
        if magnitude == 0.0:
            return False
        if magnitude > self.MAX_FORCE:
            scale = self.MAX_FORCE / magnitude
            fx, fy = fx * scale, fy * scale
        # Une force instantanee vit exactement un tick.
        self.active_forces.append(ActiveForce(str(target_id), float(fx), float(fy), max(0.0, min(float(duration), 10.0))))
        return True

    def apply_force_in_radius(self, world: Any, x: float, y: float, radius: float, fx: float, fy: float, duration: float = 0.0) -> list[str]:
        if radius <= 0.0:
            return []
        if not self.grid.cells:
            self.grid.rebuild(self.actors(world))
        target_ids: list[str] = []
        radius_sq = radius * radius
        for actor in self.grid.query_circle(x, y, radius):
            body = actor.body
            if body.static or (body.x - x) ** 2 + (body.y - y) ** 2 > radius_sq:
                continue
            if self.apply_force(world, actor.id, fx, fy, duration):
                target_ids.append(actor.id)
        return target_ids

    def tick(self, world: Any, dt: float, now: float) -> None:
        _ = now
        actors = self.actors(world)
        by_id = {actor.id: actor for actor in actors}
        retained: list[ActiveForce] = []
        for force in self.active_forces:
            actor = by_id.get(force.target_id)
            if actor is not None:
                actor.body.apply_force(force.fx, force.fy, dt)
            if force.remaining > dt:
                force.remaining -= dt
                retained.append(force)
        self.active_forces = retained

        damping = math.exp(-self.DAMPING_PER_SECOND * dt)
        for actor in actors:
            body = actor.body
            if body.static:
                continue
            body.force_velocity_x *= damping
            body.force_velocity_y *= damping
            if abs(body.force_velocity_x) < self.VELOCITY_EPSILON:
                body.force_velocity_x = 0.0
            if abs(body.force_velocity_y) < self.VELOCITY_EPSILON:
                body.force_velocity_y = 0.0
            # Les joueurs conservent leur prediction/reconciliation historique :
            # leur input les deplace deja dans process_input. La physique leur
            # ajoute uniquement la composante externe (poussee/attraction).
            if hasattr(actor, "sync_body"):
                vx, vy = body.force_velocity_x, body.force_velocity_y
            else:
                vx = body.intent_velocity_x + body.force_velocity_x
                vy = body.intent_velocity_y + body.force_velocity_y
            speed = math.hypot(vx, vy)
            if speed > self.MAX_SPEED:
                scale = self.MAX_SPEED / speed
                vx, vy = vx * scale, vy * scale
            body.velocity_x, body.velocity_y = vx, vy
            world._move_body_with_collision(body, vx * dt, vy * dt)
            if hasattr(actor, "sync_body"):
                actor.sync_body()
        self.grid.rebuild(actors)
