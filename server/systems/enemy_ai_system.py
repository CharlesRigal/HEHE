"""EnemyAISystem : IA minimale pour Entity avec composant EnemyAI.

Comportement (identique a l'ancien GameInstance._update_enemies) :
  1. Cible le joueur vivant le plus proche
  2. Avance vers lui a `ai.speed * state.speed_multiplier`
  3. S'arrete a `ai.stop_distance`
  4. Frappe si hitbox d'attaque chevauche hurtbox du joueur et cooldown ok
  5. Applique les modifiers d'etat : `frozen` immobilise, `speed_multiplier` scale

Le systeme ecrit `body.velocity_x/y`, `ai.direction`, `ai.attack_seq` ; il ne
deplace pas lui-meme : MovementSystem le fait au pass suivant.
"""
from __future__ import annotations

import math
import time
from typing import Any

from server.config import TICK_INTERVAL
from server.entities.components import Entity


class EnemyAISystem:
    def tick(self, world: Any, dt: float, now: float) -> None:
        _ = dt
        enemies = [e for e in world.entities if e.ai is not None and e.combat is not None]
        if not enemies:
            return

        alive_players = [p for p in world.players.values() if p.is_alive()]
        if not alive_players:
            for entity in enemies:
                entity.body.velocity_x = 0.0
                entity.body.velocity_y = 0.0
            return

        map_w, map_h = world.map_data.get("size", [1280, 720])

        for entity in enemies:
            if not entity.combat.alive:
                continue

            ai = entity.ai
            body = entity.body
            states = entity.states

            speed_mult = float(states.get("speed_multiplier", 1.0))
            if states.get("frozen", False) or speed_mult < 0.01:
                body.velocity_x = 0.0
                body.velocity_y = 0.0
                continue

            target = min(
                alive_players,
                key=lambda p: (p.x - body.x) ** 2 + (p.y - body.y) ** 2,
            )
            dx = target.x - body.x
            dy = target.y - body.y
            distance = math.hypot(dx, dy)

            effective_speed = ai.speed * speed_mult
            vx = vy = 0.0
            if distance > ai.stop_distance:
                vx = (dx / distance) * effective_speed
                vy = (dy / distance) * effective_speed

            new_x = body.x + vx * TICK_INTERVAL
            new_y = body.y + vy * TICK_INTERVAL
            half = body.radius
            new_x = max(half, min(new_x, map_w - half))
            new_y = max(half, min(new_y, map_h - half))

            if not _collides(world, new_x, new_y, body.radius * 2):
                body.x = new_x
                body.y = new_y
            else:
                vx = vy = 0.0

            body.velocity_x = vx
            body.velocity_y = vy
            if dx < 0:
                ai.direction = -1
            elif dx > 0:
                ai.direction = 1

            if _attack_overlap(ai, body, target, world):
                if now - ai.last_attack_at >= ai.attack_cooldown:
                    self._apply_attack(ai, target, now)

            entity.combat.last_update = time.time()

    def _apply_attack(self, ai, target, now: float) -> None:
        if not target.is_alive():
            return
        target.take_damage(ai.attack_damage)
        ai.last_attack_at = now
        ai.attack_seq += 1


def _attack_overlap(ai, body, target, world) -> bool:
    pw = world.player_attack_hurtbox_w
    ph = world.player_attack_hurtbox_h
    left1 = body.x - ai.attack_hitbox_w / 2
    right1 = body.x + ai.attack_hitbox_w / 2
    top1 = body.y - ai.attack_hitbox_h / 2
    bottom1 = body.y + ai.attack_hitbox_h / 2
    left2 = target.x - pw / 2
    right2 = target.x + pw / 2
    top2 = target.y - ph / 2
    bottom2 = target.y + ph / 2
    return left1 < right2 and right1 > left2 and top1 < bottom2 and bottom1 > top2


def _collides(world, x: float, y: float, size: float) -> bool:
    """Delegue la collision terrain a GameInstance (preserve l'existant)."""
    return world._check_collision_with_objects(x, y, size)


if __name__ == "__main__":
    from server.entities.components import EnemyAI, EntityBody, EntityCombat

    class FakePlayer:
        def __init__(self, x, y): self.x, self.y = x, y
        def is_alive(self): return True
        def take_damage(self, amt):
            self.hits = getattr(self, "hits", 0) + 1

    class FakeWorld:
        map_data = {"size": [1000, 1000]}
        player_attack_hurtbox_w = 18.0
        player_attack_hurtbox_h = 18.0
        entities = []
        players = {}
        def _check_collision_with_objects(self, x, y, s): return False

    world = FakeWorld()
    p = FakePlayer(500.0, 500.0)
    world.players["p1"] = p
    e = Entity(
        id="e1", type="enemy",
        body=EntityBody(x=400.0, y=500.0, radius=12.0),
        combat=EntityCombat(health=100.0, max_health=100.0),
        ai=EnemyAI(speed=180.0),
    )
    world.entities.append(e)

    sys = EnemyAISystem()
    sys.tick(world, dt=TICK_INTERVAL, now=0.0)
    # Ennemi se dirige a droite vers le joueur
    assert e.body.velocity_x > 0.0
    assert e.ai.direction == 1

    # Frozen : ne bouge pas
    e.states.flags["frozen"] = True
    sys.tick(world, dt=TICK_INTERVAL, now=0.0)
    assert e.body.velocity_x == 0.0

    print("enemy_ai_system: OK")
