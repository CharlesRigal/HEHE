import queue
import time
import logging
import pygame

from client.entities.magical_draw import MagicalDraw
from client.game_state.playing import playing
from client.graphics.map_renderer import MapRenderer
from client.graphics.map_selector import MapSelector
from client.magic.geometry_analyzer import GeometryAnalyzer
from client.network.network import NetworkClient
from client.core.game_manager import GameManager
from client.entities.remote_enemy import RemoteEnemy
from client.entities.remote_player import RemotePlayer
from client.core.settings import FPS, TICK_INTERVAL
from client.entities.player import Player, IN_BOARD
from client.entities.camera import Camera


class Game:
    def __init__(self):
        pygame.init()
        self.game_manager = GameManager()
        self.screen = pygame.display.set_mode((1000,500), pygame.RESIZABLE)
        self.background = pygame.Surface(self.screen.get_size())
        self.camera = Camera(self.screen)
        self.net = None
        self.net_connected = False
        pygame.display.set_caption("Fala world")
        self.clock = pygame.time.Clock()
        self.running = True
        self.start_time = None
        self.input_seq = 0
        self.last_input_time = time.time()
        self.last_input_send = 0.0
        self.input_send_hz = 60.0
        self.input_prev_mask = 0
        self.prev_board_pressed = False
        self.last_sid_ack = None
        self.msg_old = ""
        self.last_unknown_msg = None

        self.geometry_analyzer = GeometryAnalyzer()

        self.state = "menu"

        self.map_renderer:MapRenderer = MapRenderer()
        self.map_selector:MapSelector = MapSelector(self.screen.get_width(), self.screen.get_height())
        self.player:Player = Player("1", 0, 0, "client/assets/images/full_mage.png", magical_draw=MagicalDraw(self.screen))
        self.player.map_renderer = self.map_renderer

        # ===== VARIABLES POUR FIXED TIMESTEP =====
        self.accumulator = 0.0  # Temps accumulé pour les ticks de logique
        self.current_time = time.time()
        self.max_frame_time = 0.25  # Protection contre la spirale de la mort

    def run(self):
        """Boucle principale avec fixed timestep"""
        while self.running:
            # Calculer le temps écoulé depuis la dernière frame
            new_time = time.time()
            frame_time = new_time - self.current_time
            self.current_time = new_time

            # Protection contre de trop grandes accumulations (spiral of death)
            if frame_time > self.max_frame_time:
                frame_time = self.max_frame_time

            # Accumuler le temps
            self.accumulator += frame_time

            # Gérer les événements à chaque frame
            self.handle_events()

            # Pomper le réseau
            self.pump_network()

            # Exécuter autant de ticks logiques que nécessaire
            while self.accumulator >= TICK_INTERVAL:
                # Tick de logique à fréquence fixe
                self.update_logic(TICK_INTERVAL)
                self.accumulator -= TICK_INTERVAL

            # Calculer l'alpha pour l'interpolation (optionnel)
            # alpha = self.accumulator / TICK_INTERVAL

            # Rendu (à chaque frame, fréquence variable)
            self.draw()

            # Limiter le FPS maximum
            self.clock.tick(FPS)

        pygame.quit()

    def update_logic(self, dt):
        """Mise à jour de la logique du jeu à fréquence fixe (60 Hz)"""
        if self.state == "playing":
            playing(self, tick_rate=dt)
        elif self.state == "menu":
            pass
        elif self.state == "map_selection":
            pass
        elif self.state == "waiting_for_game":
            pass
        elif self.state == "game_over":
            pass

    def draw(self):
        """Rendu graphique (fréquence variable)"""
        if self.state in ("menu", "map_selection", "game_over"):
            self.draw_background()

        if self.state == "menu":
            self.draw_text("Appuie sur une touche pour jouer", 40, (255, 255, 255), self.screen.get_width() / 2, self.screen.get_height() / 2)
        elif self.state == "map_selection":
            self.map_selector.draw(self.screen)
        elif self.state == "playing":
            self.draw_playing()
        elif self.state == "game_over":
            self.draw_text("Game Over - Appuie sur R pour recommencer", 40, (255, 0, 0), self.screen.get_width() / 2, self.screen.get_height() / 2)

        pygame.display.flip()

    def build_input_message(self, inp):
        now = time.time()
        self.last_input_time = now
        msg = {
            "t": "in",
            "seq": inp.get("seq", 0),
            "k": inp.get("k", 0),
        }
        if self.last_sid_ack is not None:
            msg["ack"] = self.last_sid_ack
        return msg, now

    def send_input_if_needed(self, inp):
        if not getattr(self, "net_connected", False) or self.net is None:
            return False
        msg, now = self.build_input_message(inp)
        period = 1.0 / self.input_send_hz
        should_send = (now - self.last_input_send >= period) or (inp["k"] != self.input_prev_mask)
        if should_send:
            self.net.send(msg)
            self.last_input_send = now
            self.input_prev_mask = inp["k"]
            return True
        return False

    def connect_to_server(self, host="82.65.89.84", port=9000):
        if self.net is not None:
            return
        self.net = NetworkClient(host, port)
        try:
            self.net.connect()
            self.net.start()
            self.net_connected = True
            logging.info(f"Connected to server: {host}:{port}")
        except Exception as e:
            logging.warning(f"Connect to server failed: {e}")
            self.net = None
            self.net_connected = False

    def join_the_server(self, map):
        if self.net is not None:
            self.net.send_join_request(map)

    def disconnect_from_server(self):
        if self.net is not None:
            try:
                self.net.close()
            except Exception:
                pass
            self.net = None
        self.net_connected = False
        self.client_id = None

    def handle_server_message(self, msg):
        self.msg_old = msg
        t = msg.get("t")
        if t == "welcome":
            self.client_id = msg.get("your_id")
            logging.info(f"Welcome, id={self.client_id}")
            self.map_selector.set_available_maps(msg.get("available_maps"))
        elif t == "pong":
            pass
        elif t == "_info":
            if msg.get("event") == "server_closed":
                logging.info("The server closed the connection")
                self.disconnect_from_server()
        elif t == "_error":
            logging.warning("Network error")
            self.disconnect_from_server()
        elif t == "_exit":
            self.disconnect_from_server()
        elif t == "map_data":
            self.handle_map_data(msg)
            self.state = "playing"
        elif t == "game_state":
            self.handle_full_game_state(msg)
        elif t == "game_update":
            self.handle_game_update(msg)
        elif t == "player_joined":
            self.handle_player_joined(msg)
        elif t == "player_left":
            self.handle_player_left(msg)
        elif t == "maps_list":
            available_maps = msg.get("maps", {})
            self.map_selector.set_available_maps(available_maps)
        else:
            if msg != self.last_unknown_msg:
                logging.info(f"Unhandled server message: {msg}")
                self.last_unknown_msg = msg

    def pump_network(self, max_msgs=50):
        if not self.net_connected or self.net is None:
            return
        for _ in range(max_msgs):
            try:
                msg = self.net.recv_q.get_nowait()
            except queue.Empty:
                break
            except AttributeError:
                pass
            self.handle_server_message(msg)

    def draw_background(self):
        self.screen.blit(self.background, (0, 0))

    def resize_window(self, width: int, height: int):
        width = max(320, int(width))
        height = max(240, int(height))

        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.background = pygame.Surface((width, height))
        self.camera.set_screen(self.screen)
        self.map_selector.resize(width, height)
        if self.player and self.player.magical_draw:
            self.player.magical_draw.resize_surface((width, height))

    def handle_events(self):
        window_size_changed_event = getattr(pygame, "WINDOWSIZECHANGED", -1)

        for event in pygame.event.get():
            if event.type == pygame.VIDEORESIZE or event.type == window_size_changed_event:
                width = getattr(event, "w", None)
                height = getattr(event, "h", None)
                if width is None or height is None:
                    width = getattr(event, "x", self.screen.get_width())
                    height = getattr(event, "y", self.screen.get_height())
                self.resize_window(width, height)
                continue

            if event.type == pygame.QUIT:
                self.running = False
                self.disconnect_from_server()

            if self.state == "menu":
                if event.type == pygame.KEYDOWN:
                    self.connect_to_server()
                    if self.net_connected:
                        self.state = "map_selection"

            if self.state == "map_selection":
                selected_map = None
                if event.type == pygame.KEYDOWN:
                    selected_map = self.map_selector.handle_key(event.key)
                elif event.type == pygame.MOUSEMOTION:
                    self.map_selector.handle_hover(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    selected_map = self.map_selector.handle_click(event)

                if selected_map:
                    self.join_the_server(selected_map)
                    self.state = "waiting_for_game"

            elif self.state == "game_over":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    self.state = "menu"

    def draw_text(self, text, size, color, x, y):
        font = pygame.font.Font(None, size)
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(x, y))
        self.screen.blit(surf, rect)

    def handle_game_update(self, msg):
        remote_player_list = msg.get("players", {})
        for player_id, player_data in remote_player_list.items():
            if player_id == self.client_id:
                self.player.data_from_the_server(player_data)
                continue

            remote_player = self.game_manager.get_remote_player(player_id)
            if remote_player:
                remote_player.update_from_server(player_data)
            else:
                logging.warning(f"Remote player {player_id} not found in game_manager")

        remote_enemy_list = msg.get("enemies", {})
        self.sync_remote_enemies(remote_enemy_list)

    def handle_map_data(self, msg: dict):
        map_data = msg.get("map")
        if not map_data:
            logging.warning("No map data received")
            return
        self.map_renderer.load_map(map_data)
        logging.info(f"Map '{map_data.get('name')}' loaded successfully")

    def handle_full_game_state(self, msg):
        """
        FIX: reset la réconciliation après le spawn pour éviter que les
        pending_inputs stale soient re-appliqués et téléportent le joueur.
        """
        #print("Get full game state from server")
        your_player_data = msg.get("your_player", {})
        if your_player_data:
            self.player.pos.x = your_player_data.get("x", self.player.pos.x)
            self.player.pos.y = your_player_data.get("y", self.player.pos.y)
            self.player.render_pos = self.player.pos.copy()  # sync render immédiat
            self.player.life.life_current = your_player_data.get("health", self.player.life.life_current)
            self.player.alive = your_player_data.get("alive", self.player.alive)
            #print(f"Your player spawned at ({self.player.pos.x}, {self.player.pos.y})")

            # FIX: vider les inputs stale accumulés avant le spawn
            self.player.pending_inputs.clear()
            self.player.last_processed_seq = -1
            self.input_seq = 0

        all_players = msg.get("players", {})
        all_players.pop(self.client_id, None)
        self.sync_remote_players(all_players)
        self.sync_remote_enemies(msg.get("enemies", {}))

    def handle_player_joined(self, msg):
        player = msg.get("player")
        logging.info(f"Player join from server: {player.get('id')}")
        if self.client_id != player.get("id"):
            self.game_manager.add_object(RemotePlayer(player.get("id"), x=player.get("x"), y=player.get("y")))

    def handle_player_left(self, msg):
        logging.info("Player left from server")
        player_to_remove = self.game_manager.get_remote_player(msg.get("player_id"))
        self.game_manager.remove_object(player_to_remove)

    def update_or_create_remote_player(self, player_id, player_data):
        if player_id == self.client_id:
            return
        remote_player = self.game_manager.get_remote_player(player_id)
        if remote_player:
            remote_player.update_from_server(player_data)
        else:
            new_remote = RemotePlayer(player_id, x=player_data.get("x"), y=player_data.get("y"))
            self.game_manager.add_object(new_remote)

    def sync_remote_players(self, all_players):
        for player_id in all_players:
            if player_id != self.client_id:
                self.update_or_create_remote_player(player_id, all_players[player_id])

    def update_or_create_remote_enemy(self, enemy_id, enemy_data):
        remote_enemy = self.game_manager.get_remote_enemy(enemy_id)
        if remote_enemy:
            remote_enemy.update_from_server(enemy_data)
        else:
            new_enemy = RemoteEnemy(enemy_id, x=enemy_data.get("x"), y=enemy_data.get("y"))
            new_enemy.update_from_server(enemy_data)
            self.game_manager.add_object(new_enemy)

    def sync_remote_enemies(self, all_enemies):
        for enemy_id, enemy_data in all_enemies.items():
            self.update_or_create_remote_enemy(enemy_id, enemy_data)

    def draw_playing(self):
        self.screen.fill((0, 0, 0))  # ← efface l'écran avant chaque frame
        self.camera.update(self.player.render_pos)
        self.map_renderer.draw(self.screen, self.camera)
        self.player.draw(self.screen, self.camera)
        self.game_manager.draw_all(self.screen, self.camera)
        now = pygame.time.get_ticks() / 1000.0
        board_pressed = bool(self.player.mask & IN_BOARD)
        if self.player.magical_draw.should_render(now, board_pressed):
            self.screen.blit(self.player.magical_draw.draw(), (0, 0))
        self.draw_hud()

    def draw_hud(self):
        self.draw_text("server_request: {}".format(self.msg_old), 20, (255, 255, 255), 100, 50)
        count = self.game_manager.get_object_count()
        self.draw_text(f"Objets: {count}", 20, (255, 255, 255), 100, 30)
