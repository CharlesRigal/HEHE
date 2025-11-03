import asyncio
import time
import logging
from typing import Dict, Callable, List


from config import TICK_INTERVAL, PLAYER_SPEED


class GameInstance:
    def __init__(self, map_id: str, map_data: dict, broadcast_callback: Callable):
        self.map_id = map_id
        self.map_data = map_data
        self.players: Dict[str, dict] = {}
        self.pending_inputs: Dict[str, List[dict]] = {}
        self.running = True
        self.broadcast_callback = broadcast_callback

        # Stats monitoring
        self.tick_count = 0
        self.dt_samples: list[float] = []
        self.last_stats_log = time.time()
        self.inputs_processed = 0
        self.messages_sent = 0

        logging.info(f"Created game instance for map '{map_id}' - {map_data.get('name', 'Unnamed')}")

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
            self.pending_inputs.setdefault(client_id, []).append(input_data)

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

        # Calculer la nouvelle position
        new_x = player["x"] + vx * TICK_INTERVAL
        new_y = player["y"] + vy * TICK_INTERVAL

        # Vérifier les limites de la map
        MAP_WIDTH, MAP_HEIGHT = self.map_data.get("size", [1280, 720])
        PLAYER_SIZE = 32

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
        self.inputs_processed += 1

    async def broadcast_to_players(self, message: dict):
        """Diffuse un message à tous les joueurs de cette instance"""
        if self.broadcast_callback:
            player_ids = list(self.players.keys())
            await self.broadcast_callback(message, player_ids)
            self.messages_sent += 1

    async def game_loop(self):
        logging.info(f"Starting game loop for instance {self.map_id}")
        last_time = time.time()

        try:
            while self.running:
                current_time = time.time()
                dt = current_time - last_time
                last_time = current_time

                self.dt_samples.append(dt)
                self.tick_count += 1

                # Traiter les inputs
                for client_id, input_list in list(self.pending_inputs.items()):
                    for input_dict in input_list:
                        if client_id in self.players:
                            self.process_input(self.players[client_id], input_dict)
                self.pending_inputs.clear()

                # ===== ENVOYER last_input_seq DANS game_update =====
                if self.players:
                    # Créer un dict avec last_input_seq inclus
                    players_state = {}
                    for player_id, player_data in self.players.items():
                        players_state[player_id] = {
                            "x": player_data["x"],
                            "y": player_data["y"],
                            "health": player_data["health"],
                            "alive": player_data["alive"],
                            "last_input_seq": player_data["last_input_seq"]  # ← IMPORTANT
                        }

                    await self.broadcast_to_players({
                        "t": "game_update",
                        "players": players_state,
                        "timestamp": current_time,
                    })

                # Log périodique
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

                # Attente tick
                sleep_time = max(0, TICK_INTERVAL - (time.time() - current_time))
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError as e:
            raise e
        except Exception as e:
            raise e
        finally:
            logging.info(f"Game loop stopped for instance {self.map_id}")

    def stop(self):
        """Arrête cette instance de jeu"""
        self.running = False