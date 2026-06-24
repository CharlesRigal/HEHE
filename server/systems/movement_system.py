"""MovementSystem : integre la physique continue pour toute Entity non static.

Itere sur `world.entities` et applique :
  - integration x += vx*dt
  - clamp aux bounds de la map
  - frottement leger (0.92 par tick)
  - snap a zero sous un seuil

Les ennemis ont leur `body.velocity_x/y` fixes par `EnemyAISystem` juste
avant. Les interactives statiques (torches) sont ignorees. Les interactives
mobiles (caisse poussee par ForceEffect) sont integrees ici.
"""
from __future__ import annotations

from typing import Any

from server.entities.components import Entity


_FRICTION = 0.92
_VELOCITY_EPSILON = 1.0


class MovementSystem:
    def tick(self, world: Any, dt: float, now: float) -> None:
        _ = now
        bounds = tuple(world.map_data.get("size", [1280, 720]))
        for entity in world.entities:
            body = entity.body
            if body.static:
                continue
            if body.velocity_x == 0.0 and body.velocity_y == 0.0:
                continue
            body.integrate(dt, bounds)
            # Frottement : les ennemis doivent re-acquerir leur velocite chaque
            # frame via EnemyAISystem, sinon ils decelerent ; les entites
            # passives (caisses) s'arretent naturellement.
            body.velocity_x *= _FRICTION
            body.velocity_y *= _FRICTION
            if abs(body.velocity_x) < _VELOCITY_EPSILON:
                body.velocity_x = 0.0
            if abs(body.velocity_y) < _VELOCITY_EPSILON:
                body.velocity_y = 0.0


if __name__ == "__main__":
    class _World:
        map_data = {"size": [1000, 1000]}
        entities = [
            Entity(id="a", type="test"),
        ]

    w = _World()
    w.entities[0].body.x = 100.0
    w.entities[0].body.y = 100.0
    w.entities[0].body.velocity_x = 50.0
    w.entities[0].body.velocity_y = 0.0

    sys = MovementSystem()
    sys.tick(w, dt=0.5, now=0.0)
    assert w.entities[0].body.x == 125.0
    # Frottement applique
    assert w.entities[0].body.velocity_x < 50.0

    # Static ignore
    w.entities.append(Entity(id="b", type="wall"))
    w.entities[1].body.static = True
    w.entities[1].body.velocity_x = 100.0
    sys.tick(w, dt=0.5, now=0.0)
    assert w.entities[1].body.x == 0.0  # pas bouge

    print("movement_system: OK")
