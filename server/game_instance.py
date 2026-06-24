import asyncio
import logging
import math
import time
from collections import deque
from typing import Callable

from server.config import PLAYER_SPEED, TICK_INTERVAL
from server.effects.effect_types import DamageEffect, ShapeKind
from server.effects.runtime import LiveEffect, spawn_effect
from server.effects.spell_to_effects import spec_to_effects
from server.entities.components import Entity, EnemyAI, EntityBody, EntityCombat
from server.entities.interactive import build_entity, entity_public_state
from server.magic.spell_spec import spec_from_network
from server.players.player import Player
from server.save.error import PlayerNotFound
from server.save.save import get_save
from server.systems import (
    EffectTickSystem,
    EnemyAISystem,
    MovementSystem,
    ProximitySystem,
)


class GameInstance:
    def __init__(self, map_id: str, map_data: dict, broadcast_callback: Callable):
        self.map_id = map_id
        self.map_data = map_data
        self.players: dict[str, Player] = {}
        self.pending_inputs: dict[str, deque[dict]] = {}
        self.players_previous_state: dict[str, dict] = {}
        self.enemies_previous_state: dict[str, dict] = {}
        self.running = True
        self.broadcast_callback = broadcast_callback
        self.player_collision_size = 26.0
        self.player_attack_hurtbox_w = 18.0
        self.player_attack_hurtbox_h = 18.0

        # Pipeline emergent : sorts -> effects -> LiveEffect
        self.live_effects: list[LiveEffect] = []
        self._had_effects_last_tick: bool = False

        # Unified ECS : ennemis + interactives + futures (caisses, cristaux...)
        self.entities: list[Entity] = []
        self._entities_dirty: bool = False
        self._entities_previous_state: dict[str, dict] = {}

        # Systems (ordre : IA -> mouvement -> effets -> proximite)
        self._enemy_ai_system = EnemyAISystem()
        self._movement_system = MovementSystem()
        self._effect_tick_system = EffectTickSystem()
        self._proximity_system = ProximitySystem()

        # Stats monitoring
        self.tick_count = 0
        self.dt_samples: list[float] = []
        self.last_stats_log = time.time()
        self.inputs_processed = 0
        self.messages_sent = 0

        logging.info(
            f"Created game instance for map '{map_id}' - {map_data.get('name', 'Unnamed')}"
        )
        self._spawn_map_enemies()
        self._load_interactive_entities()

    def create_player(self, client_id: str, x=100, y=100) -> Player:
        save = get_save()
        save.create_player(client_id)

        try:
            pos = save.get_player_pos_on_a_map(self.map_id, client_id)
            x, y = pos
        except PlayerNotFound:
            spawn_points = self.map_data.get("spawn_points", [])
            if spawn_points:
                spawn = spawn_points[len(self.players) % len(spawn_points)]
                x, y = spawn.get("x", x), spawn.get("y", y)

        health = 100.0
        max_health = 100.0
        alive = True
        try:
            state = save.get_player_state(client_id)
            health = float(state.get("health", health))
            max_health = float(state.get("max_health", max_health))
            alive = bool(state.get("alive", alive))
        except PlayerNotFound:
            pass

        player = Player(
            id=client_id,
            x=float(x),
            y=float(y),
            health=health,
            max_health=max_health,
            alive=alive,
        )

        self.players[client_id] = player
        self.running = True
        return player

    def save_player(self, client_id: str) -> None:
        player = self.players.get(client_id)
        if player is None:
            return
        save = get_save()
        save.update_pos_player_map(self.map_id, client_id, player.position())
        save.update_player_state(
            client_id,
            {
                "health": player.health,
                "max_health": player.max_health,
                "alive": player.alive,
            },
        )

    def save_all_players(self) -> None:
        for client_id in self.players:
            self.save_player(client_id)

    def remove_player(self, client_id: str):
        self.save_player(client_id)
        if client_id in self.players:
            del self.players[client_id]
        if client_id in self.pending_inputs:
            del self.pending_inputs[client_id]

    def add_input(self, client_id: str, input_data: dict):
        if client_id in self.players:
            self.pending_inputs.setdefault(client_id, deque()).append(input_data)

    def get_players_state(self) -> dict[str, dict]:
        return {
            player_id: player.to_full_state()
            for player_id, player in self.players.items()
        }

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def add_spell_cast_from_spec(self, client_id: str, msg: dict) -> None:
        """Pipeline emergent : spec reseau -> effects -> LiveEffect."""
        player = self.players.get(client_id)
        if player is None or not player.can_cast_a_spell():
            return

        spec = spec_from_network(msg)
        effects = spec_to_effects(spec, player)

        map_w, map_h = self.map_data.get("size", [1280, 720])
        now = time.time()
        for effect in effects:
            shape = effect.shape
            r = max(shape.radius, shape.radius_x, shape.radius_y, 1.0)
            shape.x = self._clamp(shape.x, r, max(r, map_w - r))
            shape.y = self._clamp(shape.y, r, max(r, map_h - r))
            self.live_effects.append(spawn_effect(effect, now=now))

    def _load_interactive_entities(self):
        configs = self.map_data.get("interactive", []) or []
        before = len(self.entities)
        for cfg in configs:
            try:
                self.entities.append(build_entity(cfg))
            except Exception as e:
                logging.exception(f"[{self.map_id}] failed to load interactive entity {cfg}: {e}")
        loaded = len(self.entities) - before
        if loaded:
            logging.info(f"[{self.map_id}] Loaded {loaded} interactive entities")
        self._entities_dirty = bool(self.entities)

    def _on_entity_state_changed(self, entity: Entity) -> None:
        """Hook appele par le runtime apres mutation d'etat."""
        self._entities_dirty = True

    def _spawn_map_enemies(self):
        """Spawn des ennemis sous forme d'Entity (body + combat + ai).

        Remplace l'ancien dict d'ennemis. Les `enemy_spawn_points` restent
        reconnus tels quels ; chaque entree produit une Entity complete.
        """
        spawn_points = self.map_data.get("enemy_spawn_points", [])
        for index, spawn in enumerate(spawn_points):
            enemy_id = str(spawn.get("id", f"e{index + 1}"))
            radius = self._enemy_collision_radius()
            entity = Entity(
                id=enemy_id,
                type="enemy",
                body=EntityBody(
                    x=float(spawn.get("x", 100.0)),
                    y=float(spawn.get("y", 100.0)),
                    mass=float(spawn.get("mass", 1.0)),
                    radius=radius,
                ),
                combat=EntityCombat(
                    health=float(spawn.get("health", 100.0)),
                    max_health=float(spawn.get("max_health", 100.0)),
                    alive=True,
                    last_update=time.time(),
                ),
                ai=EnemyAI(
                    speed=float(spawn.get("speed", 180.0)),
                    stop_distance=max(
                        2.0,
                        (22.0 + self.player_attack_hurtbox_w) * 0.25 - 2.0,
                    ),
                ),
            )
            self.entities.append(entity)
        if spawn_points:
            logging.info(f"[{self.map_id}] Spawned {len(spawn_points)} enemies")

    @staticmethod
    def _enemy_collision_radius() -> float:
        # Compatibilite : l'ancien code utilisait self.enemy_collision_size=24.0
        # en AABB ; traduit en rayon de collision circulaire equivalent.
        return 12.0

    def _iter_enemies(self):
        return (e for e in self.entities if e.ai is not None and e.combat is not None)

    def _iter_interactives(self):
        return (e for e in self.entities if e.ai is None)

    @staticmethod
    def _enemy_public_state(entity: Entity) -> dict:
        body = entity.body
        combat = entity.combat
        ai = entity.ai
        return {
            "x": body.x,
            "y": body.y,
            "health": combat.health,
            "alive": combat.alive,
            "direction": ai.direction,
            "attack_seq": ai.attack_seq,
        }

    def get_enemies_state(self) -> dict:
        return {e.id: self._enemy_public_state(e) for e in self._iter_enemies()}

    def _check_collision_with_objects(self, x: float, y: float, player_size: float = 32) -> bool:
        objects = self.map_data.get("objects", [])
        for obj in objects:
            points = obj.get("points", [])
            if len(points) < 4:
                continue
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            obj_x1, obj_x2 = min(x_coords), max(x_coords)
            obj_y1, obj_y2 = min(y_coords), max(y_coords)

            px1, px2 = x - player_size / 2, x + player_size / 2
            py1, py2 = y - player_size / 2, y + player_size / 2
            if px1 < obj_x2 and px2 > obj_x1 and py1 < obj_y2 and py2 > obj_y1:
                return True
        return False

    def process_input(self, player: Player, input_data: dict):
        if not player.can_receive_input():
            return

        seq = input_data.get("seq", -1)
        player.record_input_seq(seq)

        k = input_data.get("k", 0)
        speed = PLAYER_SPEED

        in_up, in_down, in_left, in_right = 1, 2, 4, 8

        vx = vy = 0.0
        if k & in_up:
            vy -= speed
        if k & in_down:
            vy += speed
        if k & in_left:
            vx -= speed
        if k & in_right:
            vx += speed

        if vx != 0 and vy != 0:
            diag = 0.70710678
            vx *= diag
            vy *= diag

        if vx != 0.0 or vy != 0.0:
            player.set_facing_from_vector(vx, vy)

        new_x = player.x + vx * TICK_INTERVAL
        new_y = player.y + vy * TICK_INTERVAL

        map_w, map_h = self.map_data.get("size", [1280, 720])
        size = self.player_collision_size

        new_x = max(size / 2, min(new_x, map_w - size / 2))
        new_y = max(size / 2, min(new_y, map_h - size / 2))

        if not self._check_collision_with_objects(new_x, new_y, size):
            player.set_motion(x=new_x, y=new_y, vx=vx, vy=vy)
        else:
            player.stop()

    async def broadcast_to_players(self, message: dict):
        if self.broadcast_callback:
            player_ids = list(self.players.keys())
            await self.broadcast_callback(message, player_ids)
            self.messages_sent += 1

    def _serialize_live_effects(self) -> list[dict]:
        """Serialise pour le client (format historique 'spells')."""
        out: list[dict] = []
        for live in self.live_effects:
            if not isinstance(live.effect, DamageEffect):
                # StateChange/Force : invisibles cote rendu pour l'instant
                continue
            shape = live.effect.shape
            r = max(shape.radius, shape.radius_x, shape.radius_y)
            entry = {
                "x": round(shape.x, 1),
                "y": round(shape.y, 1),
                "r": round(r, 1),
                "e": live.effect.element,
                "vx": round(shape.velocity_x, 1),
                "vy": round(shape.velocity_y, 1),
                "bh": "parametric",
            }
            if shape.kind is ShapeKind.ELLIPSE:
                entry["rx"] = round(shape.radius_x, 1)
                entry["ry"] = round(shape.radius_y, 1)
                entry["ea"] = round(math.degrees(shape.angle))
            out.append(entry)
        return out

    async def game_loop(self):
        logging.info(f"Starting game loop for instance {self.map_id}")
        last_time = time.time()
        MAX_INPUTS_PER_TICK = 60

        try:
            while self.running:
                current_time = time.time()
                dt = current_time - last_time
                last_time = current_time

                self.dt_samples.append(dt)
                self.tick_count += 1

                for client_id, input_list in list(self.pending_inputs.items()):
                    if client_id in self.players and input_list:
                        for _ in range(min(MAX_INPUTS_PER_TICK, len(input_list))):
                            input_dict = input_list.popleft()
                            self.process_input(self.players[client_id], input_dict)
                            self.inputs_processed += 1

                # ECS pipeline : IA lit joueurs + ecrit vx/vy
                #                MovementSystem integre les corps non static
                #                EffectTickSystem dispatche les LiveEffect
                self._enemy_ai_system.tick(self, TICK_INTERVAL, current_time)
                self._movement_system.tick(self, TICK_INTERVAL, current_time)
                self._effect_tick_system.tick(self, TICK_INTERVAL, current_time)
                self._proximity_system.tick(self, TICK_INTERVAL, current_time)

                if self.players:
                    players_state = {}
                    enemies_state = {}
                    for player_id, player_data in self.players.items():
                        current_data = player_data.to_update_state()
                        if self.players_previous_state.get(player_id) != current_data:
                            players_state[player_id] = current_data

                    for enemy in self._iter_enemies():
                        current_data = self._enemy_public_state(enemy)
                        if self.enemies_previous_state.get(enemy.id) != current_data:
                            enemies_state[enemy.id] = current_data

                    spells_state = self._serialize_live_effects()

                    # Diff inconditionnel : capture etats (reactions) ET positions
                    # (cristaux en levitation bougent sans que _entities_dirty
                    # soit mis par une reaction). Cout faible : peu d'entites.
                    entities_state: list[dict] = []
                    for ent in self._iter_interactives():
                        pub = entity_public_state(ent)
                        prev = self._entities_previous_state.get(ent.id)
                        if prev != pub:
                            entities_state.append(pub)
                            self._entities_previous_state[ent.id] = pub
                    self._entities_dirty = False

                    if (
                        players_state
                        or enemies_state
                        or spells_state
                        or entities_state
                        or self._had_effects_last_tick
                    ):
                        message = {"t": "game_update", "timestamp": current_time}
                        if players_state:
                            message["players"] = players_state
                        if enemies_state:
                            message["enemies"] = enemies_state
                        if spells_state or self._had_effects_last_tick:
                            message["spells"] = spells_state
                        if entities_state:
                            message["entities"] = entities_state
                        await self.broadcast_to_players(message)

                    self._had_effects_last_tick = bool(spells_state)

                    self.players_previous_state = {
                        player_id: player_data.to_update_state()
                        for player_id, player_data in self.players.items()
                    }
                    self.enemies_previous_state = {
                        e.id: self._enemy_public_state(e)
                        for e in self._iter_enemies()
                    }

                if time.time() - self.last_stats_log >= 5:
                    if self.dt_samples:
                        avg_dt = sum(self.dt_samples) / len(self.dt_samples)
                        max_dt = max(self.dt_samples)
                        logging.info(
                            f"[Instance {self.map_id}] ticks={self.tick_count}, "
                            f"avg_dt={avg_dt * 1000:.2f}ms, max_dt={max_dt * 1000:.2f}ms, "
                            f"inputs={self.inputs_processed}, msgs={self.messages_sent}"
                        )
                    self.dt_samples.clear()
                    self.inputs_processed = 0
                    self.messages_sent = 0
                    self.last_stats_log = time.time()

                sleep_time = max(0, TICK_INTERVAL - (time.time() - current_time))
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception(f"Exception in game loop {self.map_id}: {e}")
            raise
        finally:
            logging.info(f"Game loop stopped for instance {self.map_id}")

    def stop(self):
        self.running = False
