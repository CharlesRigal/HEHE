import asyncio
import time
import logging
from typing import Dict, Set, Callable, Optional

from config import TICK_INTERVAL


class GameInstance:
    def __init__(self, map_id: str, map_data: dict, broadcast_callback: Callable):
        self.map_id = map_id
        self.map_data = map_data
        self.players: Dict[str, dict] = {}
        self.pending_inputs: Dict[str, dict] = {}
        self.running = True
        self.broadcast_callback = broadcast_callback

        logging.info(f"Created game instance for map '{map_id}' - {map_data.get('name', 'Unnamed')}")

    def create_player(self, client_id: str, x=100, y=100) -> dict:
        """Crée un nouveau joueur"""
        # Vérifier s'il y a des points de spawn définis dans la map
        spawn_points = self.map_data.get('spawn_points', [])
        if spawn_points:
            # Utiliser le premier point de spawn disponible ou un aléatoire
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
            "last_input": 0,
            "last_update": time.time()
        }

        self.players[client_id] = player
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
            self.pending_inputs[client_id] = input_data

    def _check_collision_with_objects(self, x: float, y: float, player_size: float = 32) -> bool:
        """Vérifie les collisions avec les objets de la map"""
        objects = self.map_data.get('objects', [])

        for obj in objects:
            # Supposer que les objets sont des rectangles définis par leurs points
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

    def process_input(self, player: dict, input_data: dict, dt: float):
        """Traite l'input d'un joueur"""
        if not player["alive"]:
            return

        k = input_data.get("k", 0)
        speed = 200.0

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
        new_x = player["x"] + vx * dt
        new_y = player["y"] + vy * dt

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

    async def broadcast_to_players(self, message: dict):
        """Diffuse un message à tous les joueurs de cette instance"""
        if self.broadcast_callback:
            player_ids = list(self.players.keys())
            await self.broadcast_callback(message, player_ids)

    async def game_loop(self):
        """Boucle principale du jeu pour cette instance"""
        logging.info(f"Starting game loop for instance {self.map_id}")
        last_time = time.time()

        try:
            while self.running:
                current_time = time.time()
                dt = current_time - last_time
                last_time = current_time

                # Traiter tous les inputs en attente
                for client_id, input_data in list(self.pending_inputs.items()):
                    if client_id in self.players:
                        self.process_input(self.players[client_id], input_data, dt)

                self.pending_inputs.clear()

                # Envoyer l'état du jeu aux joueurs s'il y en a
                if self.players:
                    await self.broadcast_to_players({
                        "t": "game_update",
                        "players": self.players,
                        "timestamp": current_time,
                        "map_id": self.map_id
                    })

                # Attendre le prochain tick
                sleep_time = max(0, TICK_INTERVAL - (time.time() - current_time))
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logging.info(f"Game loop cancelled for instance {self.map_id}")
        except Exception as e:
            logging.error(f"Error in game loop for instance {self.map_id}: {e}")
        finally:
            logging.info(f"Game loop stopped for instance {self.map_id}")

    def stop(self):
        """Arrête cette instance de jeu"""
        self.running = False