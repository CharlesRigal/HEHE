import asyncio
import time
import logging
import math
from collections import deque
from typing import Any, Dict, Callable


from server.config import TICK_INTERVAL, PLAYER_SPEED
from server.spells.default_spells import build_default_spell_registry


class GameInstance:
    def __init__(self, map_id: str, map_data: dict, broadcast_callback: Callable):
        self.map_id = map_id
        self.map_data = map_data
        self.players: Dict[str, dict] = {}
        self.pending_inputs: Dict[str, deque[dict]] = {}
        self.players_previous_state = {}
        self.enemies: Dict[str, dict] = {}
        self.enemies_previous_state = {}
        self.running = True
        self.broadcast_callback = broadcast_callback
        self.enemy_speed = 180.0
        self.player_collision_size = 26.0
        self.enemy_collision_size = 24.0
        self.player_attack_hurtbox_w = 18.0
        self.player_attack_hurtbox_h = 18.0
        self.enemy_attack_hitbox_w = 22.0
        self.enemy_attack_hitbox_h = 22.0
        self.enemy_stop_distance = max(
            2.0,
            (self.enemy_attack_hitbox_w + self.player_attack_hurtbox_w) * 0.25 - 2.0
        )
        self.enemy_attack_damage = 12
        self.enemy_attack_cooldown = 1.1
        self.active_spells: list[dict] = []
        self.fire_rune_tick_damage = 12
        self.fire_rune_tick_interval = 0.20
        self.fire_rune_duration = 2.4
        self.fire_rune_min_radius = 12.0
        self.fire_rune_max_radius = 320.0
        self.fire_rune_max_cast_distance = 520.0
        self.spell_registry = build_default_spell_registry()

        # Stats monitoring
        self.tick_count = 0
        self.dt_samples: list[float] = []
        self.last_stats_log = time.time()
        self.inputs_processed = 0
        self.messages_sent = 0

        logging.info(f"Created game instance for map '{map_id}' - {map_data.get('name', 'Unnamed')}")
        self._spawn_map_enemies()

    def create_player(self, client_id: str, x=100, y=100) -> dict:
        """Crée un nouveau joueur"""
        spawn_points = self.map_data.get('spawn_points', [])
        if spawn_points:
            spawn = spawn_points[len(self.players) % len(spawn_points)]
            x, y = spawn.get('x', x), spawn.get('y', y)

        player = {
            "id": client_id,
            "x": x,
            "y": y,
            "vx": 0.0,
            "vy": 0.0,
            "facing_x": 1.0,
            "facing_y": 0.0,
            "health": 100,
            "max_health": 100,
            "alive": True,
            "last_input_seq": -1,  # ← AJOUT: Dernier input traité
            "last_update": time.time()
        }

        self.players[client_id] = player
        self.running = True
        return player

    def remove_player(self, client_id: str):
        """Supprime un joueur de cette instance"""
        if client_id in self.players:
            del self.players[client_id]
        if client_id in self.pending_inputs:
            del self.pending_inputs[client_id]

    def add_input(self, client_id: str, input_data: dict):
        """Ajoute un input en attente pour un joueur"""
        if client_id in self.players:
            self.pending_inputs.setdefault(client_id, deque()).append(input_data)

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def add_spell_cast_from_spec(self, client_id: str, msg: dict) -> None:
        """Traite un sort issu du système émergent (format compact réseau)."""
        from server.magic.spell_spec import spec_from_network
        from server.magic.spec_router import route_spec

        player = self.players.get(client_id)
        if player is None or not player.get("alive", True):
            return

        spec = spec_from_network(msg)
        spell_id = route_spec(spec)

        cast_handler = self.spell_registry.get_cast_handler(spell_id)
        if cast_handler is None:
            return

        # Traduit la SpellSpec en payload + modifiers pour les handlers existants
        payload: dict = {}

        if spec.power is not None:
            payload["power"] = spec.power
            payload["hitbox_radius"] = self._clamp(
                self.fire_rune_min_radius
                + spec.power * (self.fire_rune_max_radius - self.fire_rune_min_radius),
                self.fire_rune_min_radius,
                self.fire_rune_max_radius,
            )

        if spec.direction is not None:
            payload["direction_x"] = spec.direction[0]
            payload["direction_y"] = spec.direction[1]

        payload["focused"] = spec.focused
        payload["unstable"] = spec.unstable

        # Modifiers de compatibilité pour fire_rune (reach/volatility/precision)
        modifiers: list[dict] = []
        if spec.direction is not None:
            modifiers.append({
                "id": "reach",
                "payload": {
                    "direction_x":  spec.direction[0],
                    "direction_y":  spec.direction[1],
                    "has_base":     1.0,
                    "base_score":   0.6,
                    "vector_length": math.hypot(spec.direction[0], spec.direction[1]),
                    "strength":     1.0,
                },
            })
        if spec.unstable:
            modifiers.append({"id": "volatility", "payload": {"strength": 1.5}})
        if spec.focused:
            modifiers.append({"id": "precision", "payload": {"strength": 1.5}})

        cast_handler(self, client_id, payload, modifiers)

    def add_spell_cast(self, client_id: str, spell_data: dict):
        if client_id not in self.players:
            return

        player = self.players[client_id]
        if not player.get("alive", True):
            return

        spell_id, payload, modifiers = self._decode_spell_cast_message(spell_data)
        if spell_id is None:
            return

        cast_handler = self.spell_registry.get_cast_handler(spell_id)
        if cast_handler is None:
            return
        cast_handler(self, client_id, payload, modifiers)

    def _decode_spell_cast_message(
        self,
        spell_data: dict[str, Any],
    ) -> tuple[str | None, dict[str, Any], list[dict[str, Any]]]:
        spell_id = spell_data.get("spell_id", spell_data.get("spell"))
        if not isinstance(spell_id, str) or not spell_id:
            return None, {}, []

        payload = spell_data.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        # Compatibilité avec l'ancien format (paramètres au niveau racine).
        for key in ("texture_radius", "hitbox_radius", "damage_per_tick", "tick_interval", "duration"):
            if key in spell_data and key not in payload:
                payload[key] = spell_data[key]

        modifiers: list[dict[str, Any]] = []
        raw_modifiers = spell_data.get("modifiers", [])
        if isinstance(raw_modifiers, list):
            for raw_modifier in raw_modifiers:
                if not isinstance(raw_modifier, dict):
                    continue
                modifier_id = raw_modifier.get("id", raw_modifier.get("modifier_id"))
                if not isinstance(modifier_id, str) or not modifier_id:
                    continue
                modifier_payload = raw_modifier.get("payload", {})
                if not isinstance(modifier_payload, dict):
                    modifier_payload = {}
                modifiers.append(
                    {
                        "id": modifier_id,
                        "payload": modifier_payload,
                    }
                )

        return spell_id, payload, modifiers

    def _apply_server_spell_modifiers(
        self,
        spell_id: str,
        base_params: dict[str, float],
        modifiers: list[dict[str, Any]],
    ) -> dict[str, float]:
        params = dict(base_params)
        for modifier in modifiers:
            modifier_id = modifier.get("id")
            if not isinstance(modifier_id, str):
                continue
            strength = self._extract_modifier_strength(modifier, 1.0)

            if modifier_id == "power":
                params["damage_per_tick"] = float(params.get("damage_per_tick", 0.0)) * (1.0 + 0.22 * strength)
            elif modifier_id == "reach":
                params["cast_distance_bonus"] = float(params.get("cast_distance_bonus", 0.0)) + 18.0 * strength
                has_base = self._extract_modifier_payload_float(modifier, "has_base", 0.0) >= 0.5
                base_score = self._clamp(self._extract_modifier_payload_float(modifier, "base_score", 0.0), 0.0, 1.0)
                base_length = max(0.0, self._extract_modifier_payload_float(modifier, "base_length", 0.0))
                direction_x = self._extract_modifier_payload_float(modifier, "direction_x", 0.0)
                direction_y = self._extract_modifier_payload_float(modifier, "direction_y", 0.0)
                vector_length = max(0.0, self._extract_modifier_payload_float(modifier, "vector_length", 0.0))
                shape_pressure = max(0.0, self._extract_modifier_payload_float(modifier, "shape_pressure", 0.0))
                speed_seed = max(0.0, self._extract_modifier_payload_float(modifier, "speed_seed", 0.0))

                direction_norm = math.hypot(direction_x, direction_y)
                if direction_norm > 1e-6:
                    direction_x /= direction_norm
                    direction_y /= direction_norm

                base_factor = 1.0 + (0.22 * base_score if has_base else 0.0)
                pressure_factor = 1.0 + (0.18 * base_score if has_base else 0.0)
                speed_bonus = (vector_length * 0.18 + speed_seed * 32.0) * strength
                if has_base:
                    speed_bonus += (base_length * 0.10 + base_score * 24.0) * strength

                params["motion_vector_x"] = float(params.get("motion_vector_x", 0.0)) + direction_x * strength * base_factor
                params["motion_vector_y"] = float(params.get("motion_vector_y", 0.0)) + direction_y * strength * base_factor
                params["shape_pressure"] = float(params.get("shape_pressure", 0.0)) + shape_pressure * strength * pressure_factor
                params["move_speed_bonus"] = float(params.get("move_speed_bonus", 0.0)) + speed_bonus
            elif modifier_id == "volatility":
                params["tick_interval"] = float(params.get("tick_interval", self.fire_rune_tick_interval)) * max(
                    0.45,
                    1.0 - 0.10 * strength,
                )
                params["duration"] = float(params.get("duration", self.fire_rune_duration)) * max(
                    0.50,
                    1.0 - 0.08 * strength,
                )
            elif modifier_id == "precision":
                params["damage_per_tick"] = float(params.get("damage_per_tick", 0.0)) * (1.0 + 0.08 * strength)
            elif modifier_id == "stability":
                params["duration"] = float(params.get("duration", self.fire_rune_duration)) * (1.0 + 0.14 * strength)
                params["tick_interval"] = float(params.get("tick_interval", self.fire_rune_tick_interval)) * (
                    1.0 + 0.05 * strength
                )

        _ = spell_id
        return params

    @staticmethod
    def _extract_modifier_strength(modifier: dict[str, Any], fallback: float = 1.0) -> float:
        payload = modifier.get("payload", {})
        if not isinstance(payload, dict):
            return fallback
        raw = payload.get("strength", fallback)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = fallback
        return max(0.1, min(3.0, value))

    @staticmethod
    def _extract_modifier_payload_float(
        modifier: dict[str, Any],
        key: str,
        fallback: float = 0.0,
    ) -> float:
        payload = modifier.get("payload", {})
        if not isinstance(payload, dict):
            return fallback
        raw = payload.get(key, fallback)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return fallback

    def _spawn_map_enemies(self):
        spawn_points = self.map_data.get("enemy_spawn_points", [])
        for index, spawn in enumerate(spawn_points):
            enemy_id = str(spawn.get("id", f"e{index + 1}"))
            self.enemies[enemy_id] = {
                "id": enemy_id,
                "x": float(spawn.get("x", 100.0)),
                "y": float(spawn.get("y", 100.0)),
                "vx": 0.0,
                "vy": 0.0,
                "direction": 1,
                "health": 100,
                "max_health": 100,
                "alive": True,
                "attack_seq": 0,
                "last_attack_at": 0.0,
                "last_update": time.time(),
            }
        if spawn_points:
            logging.info(f"[{self.map_id}] Spawned {len(spawn_points)} enemies")

    def _enemy_public_state(self, enemy_data: dict) -> dict:
        return {
            "x": enemy_data["x"],
            "y": enemy_data["y"],
            "health": enemy_data["health"],
            "alive": enemy_data["alive"],
            "direction": enemy_data["direction"],
            "attack_seq": enemy_data["attack_seq"],
        }

    def get_enemies_state(self) -> dict:
        return {
            enemy_id: self._enemy_public_state(enemy_data)
            for enemy_id, enemy_data in self.enemies.items()
        }

    @staticmethod
    def _aabb_overlap(
        x1: float,
        y1: float,
        w1: float,
        h1: float,
        x2: float,
        y2: float,
        w2: float,
        h2: float
    ) -> bool:
        left1 = x1 - w1 / 2
        right1 = x1 + w1 / 2
        top1 = y1 - h1 / 2
        bottom1 = y1 + h1 / 2

        left2 = x2 - w2 / 2
        right2 = x2 + w2 / 2
        top2 = y2 - h2 / 2
        bottom2 = y2 + h2 / 2

        return left1 < right2 and right1 > left2 and top1 < bottom2 and bottom1 > top2

    def _update_enemies(self):
        alive_players = [p for p in self.players.values() if p.get("alive")]
        if not alive_players:
            for enemy in self.enemies.values():
                enemy["vx"] = 0.0
                enemy["vy"] = 0.0
            return

        map_width, map_height = self.map_data.get("size", [1280, 720])
        now = time.time()

        for enemy in self.enemies.values():
            if not enemy.get("alive", True):
                continue

            target = min(
                alive_players,
                key=lambda player: (player["x"] - enemy["x"]) ** 2 + (player["y"] - enemy["y"]) ** 2
            )

            dx = target["x"] - enemy["x"]
            dy = target["y"] - enemy["y"]
            distance = math.hypot(dx, dy)

            vx = 0.0
            vy = 0.0
            if distance > self.enemy_stop_distance:
                vx = (dx / distance) * self.enemy_speed
                vy = (dy / distance) * self.enemy_speed

            new_x = enemy["x"] + vx * TICK_INTERVAL
            new_y = enemy["y"] + vy * TICK_INTERVAL

            new_x = max(self.enemy_collision_size / 2, min(new_x, map_width - self.enemy_collision_size / 2))
            new_y = max(self.enemy_collision_size / 2, min(new_y, map_height - self.enemy_collision_size / 2))

            if not self._check_collision_with_objects(new_x, new_y, self.enemy_collision_size):
                enemy["x"] = new_x
                enemy["y"] = new_y
            else:
                vx = 0.0
                vy = 0.0

            enemy["vx"] = vx
            enemy["vy"] = vy
            if dx < 0:
                enemy["direction"] = -1
            elif dx > 0:
                enemy["direction"] = 1

            has_attack_overlap = self._aabb_overlap(
                enemy["x"],
                enemy["y"],
                self.enemy_attack_hitbox_w,
                self.enemy_attack_hitbox_h,
                target["x"],
                target["y"],
                self.player_attack_hurtbox_w,
                self.player_attack_hurtbox_h,
            )
            if has_attack_overlap and (now - enemy["last_attack_at"] >= self.enemy_attack_cooldown):
                self._apply_enemy_attack(enemy, target, now)

            enemy["last_update"] = time.time()

    def _apply_enemy_attack(self, enemy: dict, target_player: dict, now: float):
        if not target_player.get("alive", True):
            return

        target_player["health"] = max(0, target_player["health"] - self.enemy_attack_damage)
        if target_player["health"] <= 0:
            target_player["alive"] = False
            target_player["vx"] = 0.0
            target_player["vy"] = 0.0

        enemy["last_attack_at"] = now
        enemy["attack_seq"] += 1

    def _update_active_spells(self, now: float):
        if not self.active_spells:
            return

        next_spells: list[dict] = []
        map_width, map_height = self.map_data.get("size", [1280, 720])
        for spell in self.active_spells:
            spell["remaining"] -= TICK_INTERVAL
            if spell["remaining"] <= 0.0:
                continue

            velocity_x = float(spell.get("velocity_x", 0.0))
            velocity_y = float(spell.get("velocity_y", 0.0))
            if abs(velocity_x) > 1e-6 or abs(velocity_y) > 1e-6:
                x = float(spell.get("x", 0.0)) + velocity_x * TICK_INTERVAL
                y = float(spell.get("y", 0.0)) + velocity_y * TICK_INTERVAL
                radius_x = max(
                    1.0,
                    float(
                        spell.get(
                            "hitbox_radius_x",
                            spell.get("hitbox_radius", self.fire_rune_min_radius),
                        )
                    ),
                )
                radius_y = max(
                    1.0,
                    float(
                        spell.get(
                            "hitbox_radius_y",
                            spell.get("hitbox_radius", self.fire_rune_min_radius),
                        )
                    ),
                )
                spell["x"] = self._clamp(x, radius_x, max(radius_x, map_width - radius_x))
                spell["y"] = self._clamp(y, radius_y, max(radius_y, map_height - radius_y))

            tick_interval = max(0.05, float(spell.get("tick_interval", self.fire_rune_tick_interval)))
            spell_id = str(spell.get("spell_id", spell.get("spell", "")))
            tick_handler = self.spell_registry.get_tick_handler(spell_id)
            while now >= spell["next_tick_at"] and spell["remaining"] > 0.0:
                if tick_handler is not None:
                    tick_handler(self, spell)
                spell["next_tick_at"] += tick_interval
            next_spells.append(spell)

        self.active_spells = next_spells

    def _check_collision_with_objects(self, x: float, y: float, player_size: float = 32) -> bool:
        """Vérifie les collisions avec les objets de la map"""
        objects = self.map_data.get('objects', [])

        for obj in objects:
            points = obj.get('points', [])
            if len(points) >= 4:
                # Rectangle simple : prendre min/max x et y
                x_coords = [p[0] for p in points]
                y_coords = [p[1] for p in points]

                obj_x1, obj_x2 = min(x_coords), max(x_coords)
                obj_y1, obj_y2 = min(y_coords), max(y_coords)

                # Collision AABB simple
                player_x1 = x - player_size / 2
                player_x2 = x + player_size / 2
                player_y1 = y - player_size / 2
                player_y2 = y + player_size / 2

                if (player_x1 < obj_x2 and player_x2 > obj_x1 and
                        player_y1 < obj_y2 and player_y2 > obj_y1):
                    return True

        return False

    def process_input(self, player: dict, input_data: dict):
        """Traite l'input d'un joueur"""
        if not player["alive"]:
            return

        # ===== ENREGISTRER LE SEQ TRAITÉ =====
        seq = input_data.get("seq", -1)
        if seq > player["last_input_seq"]:
            player["last_input_seq"] = seq

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

        # Normaliser la vitesse en diagonale
        if vx != 0 and vy != 0:
            diag = 0.70710678
            vx *= diag
            vy *= diag

        if vx != 0.0 or vy != 0.0:
            norm = math.hypot(vx, vy)
            if norm > 1e-9:
                player["facing_x"] = vx / norm
                player["facing_y"] = vy / norm

        # Calculer la nouvelle position
        new_x = player["x"] + vx * TICK_INTERVAL
        new_y = player["y"] + vy * TICK_INTERVAL

        # Vérifier les limites de la map
        MAP_WIDTH, MAP_HEIGHT = self.map_data.get("size", [1280, 720])
        PLAYER_SIZE = self.player_collision_size

        new_x = max(PLAYER_SIZE / 2, min(new_x, MAP_WIDTH - PLAYER_SIZE / 2))
        new_y = max(PLAYER_SIZE / 2, min(new_y, MAP_HEIGHT - PLAYER_SIZE / 2))

        # Vérifier les collisions avec les objets
        if not self._check_collision_with_objects(new_x, new_y, PLAYER_SIZE):
            player["x"] = new_x
            player["y"] = new_y
            player["vx"] = vx
            player["vy"] = vy
        else:
            # Arrêter le mouvement en cas de collision
            player["vx"] = 0.0
            player["vy"] = 0.0

        player["last_update"] = time.time()

    async def broadcast_to_players(self, message: dict):
        """Diffuse un message à tous les joueurs de cette instance"""
        if self.broadcast_callback:
            player_ids = list(self.players.keys())
            await self.broadcast_callback(message, player_ids)
            self.messages_sent += 1

    async def game_loop(self):
        logging.info(f"Starting game loop for instance {self.map_id}")
        last_time = time.time()

        MAX_INPUTS_PER_TICK = 60  # limite pour éviter de surcharger le serveur

        try:
            while self.running:
                current_time = time.time()
                dt = current_time - last_time
                last_time = current_time

                self.dt_samples.append(dt)
                self.tick_count += 1

                # ===== TRAITER LES INPUTS =====
                for client_id, input_list in list(self.pending_inputs.items()):
                    if client_id in self.players and input_list:
                        # Traiter jusqu'à MAX_INPUTS_PER_TICK
                        for _ in range(min(MAX_INPUTS_PER_TICK, len(input_list))):
                            input_dict = input_list.popleft()
                            self.process_input(self.players[client_id], input_dict)
                            self.inputs_processed += 1
                self._update_enemies()
                self._update_active_spells(current_time)

                # ===== ENVOYER L'ÉTAT AUX CLIENTS =====
                if self.players:
                    players_state = {}
                    enemies_state = {}
                    for player_id, player_data in self.players.items():
                        current_data = {
                            "x": player_data["x"],
                            "y": player_data["y"],
                            "health": player_data["health"],
                            "alive": player_data["alive"],
                            "last_input_seq": player_data["last_input_seq"]
                        }

                        # n'envoyer que si différent de l'état précédent
                        if self.players_previous_state.get(player_id) != current_data:
                            players_state[player_id] = current_data

                    for enemy_id, enemy_data in self.enemies.items():
                        current_data = self._enemy_public_state(enemy_data)
                        if self.enemies_previous_state.get(enemy_id) != current_data:
                            enemies_state[enemy_id] = current_data

                    if players_state or enemies_state:
                        message = {
                            "t": "game_update",
                            "timestamp": current_time,
                        }
                        if players_state:
                            message["players"] = players_state
                        if enemies_state:
                            message["enemies"] = enemies_state
                        await self.broadcast_to_players(message)

                    # Mettre à jour l'état précédent pour comparer au prochain tick
                    self.players_previous_state = {
                        player_id: {
                            "x": player_data["x"],
                            "y": player_data["y"],
                            "health": player_data["health"],
                            "alive": player_data["alive"],
                            "last_input_seq": player_data["last_input_seq"]
                        }
                        for player_id, player_data in self.players.items()
                    }
                    self.enemies_previous_state = {
                        enemy_id: self._enemy_public_state(enemy_data)
                        for enemy_id, enemy_data in self.enemies.items()
                    }

                # ===== LOG STATISTIQUES =====
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

                # ===== ATTENTE TICK =====
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
        """Arrête cette instance de jeu"""
        self.running = False
