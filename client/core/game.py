import queue
import time

import pygame

from client.game_state.playing import playing
from client.graphics.map_renderer import MapRenderer
from client.graphics.map_selector import MapSelector
from client.network.network import NetworkClient

from client.core.game_manager import GameManager
from client.entities.remote_player import RemotePlayer
from client.core.settings import WIDTH, HEIGHT, FPS
from client.entities.player import Player


class Game:
    def build_input_message(self, inp):
        now = time.time()
        dt = now - self.last_input_time
        self.last_input_time = now
        msg = {
            "t": "in",
            "seq": self.input_seq,
            "dt": dt,
            "k": inp.get("k", 0),
        }
        if self.last_sid_ack is not None:
            msg["ack"] = self.last_sid_ack
        return msg, now

    def send_input_if_needed(self, inp):
        if not getattr(self, "net_connected", False) or self.net is None:
           return
        msg, now = self.build_input_message(inp)
        period = 1.0 / self.input_send_hz
        should_send = (now - self.last_input_send >= period) or (inp["k"] != self.input_prev_mask)
        if should_send:
            self.net.send(msg)
            self.last_input_send = now
            self.input_prev_mask = inp["k"]
            self.input_seq += 1


    def connect_to_server(self, host="127.0.0.1", port=9000):
        if self.net is not None:
            return
        self.net = NetworkClient(host, port)
        try:
            self.net.connect()
            self.net.start()
            self.net_connected = True
            print("connected to server: ", host, port)
        except Exception as e:
            print("Connect to server faild: ", e)
            self.net = None
            self.net_connected = False

    def join_the_server(self, maps):
        if self.net is not None:
            self.net.send_join_request(maps)

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
        t = msg.get("t")
        if t == "welcome":
            self.client_id = msg.get("your_id")
            print("welcome, id = ", self.client_id)
            self.map_selector.set_available_maps(msg.get("available_maps"))

        elif t == "pong":
            pass
        elif t == "_info":
            if msg.get("event") == "server_closed":
                print("The server closed the connection")
                self.disconnect_from_server()
        elif t == "_error":
            print("Network error")
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
            if self.msg_old and msg != self.msg_old:
                print("get from server : ", msg)
                self.msg_old = msg
            pass
            #TODO to game_manager


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
            self.msg_old = msg
            self.handle_server_message(msg)

    def __init__(self):
        pygame.init()
        self.game_manager = GameManager()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.background = pygame.Surface(self.screen.get_size())
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
        self.last_sid_ack = None
        self.msg_old = ""

        self.state = "menu"  # menu, playing, game_over

        self.map_renderer = MapRenderer()
        self.map_selector = MapSelector()

        self.player = Player("1", WIDTH / 2, HEIGHT / 2, "client/assets/images/player.png")

        self.enemies = []

    def draw_background(self):
        """Dessine le background"""
        self.screen.blit(self.background,(0, 0))

    def run(self):
        """Boucle principale"""

        while self.running:
            dt = self.clock.tick(FPS) / 1000
            self.handle_events()
            self.update(dt)
            self.draw()
            self.pump_network()
        pygame.quit()

    def handle_events(self):
        """Gestion des entrées"""
        for event in pygame.event.get():
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
                    print(f"Selected map: {selected_map}")
                    self.join_the_server(selected_map)
                    self.state = "waiting_for_game"

            elif self.state == "game_over":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    self.state = "menu"

    def update(self, dt):
        """Logique du jeu selon l'état"""
        if self.state == "menu":
            pass

        elif self.state == "map_selection":
            pass

        elif self.state == "waiting_for_game":
            # Attente du message game_state du serveur
            pass

        elif self.state == "playing":
            playing(self, dt=dt)

        elif self.state == "game_over":
            pass

    def draw(self):
        """Rendu graphique"""
        # Dessiner le background en premier
        if self.state in ("menu", "map_selection", "game_over"):
            self.draw_background()

        if self.state == "menu":
            self.draw_text("Appuie sur une touche pour jouer", 40, (255, 255, 255), WIDTH / 2, HEIGHT / 2)
        elif self.state == "map_selection":
            self.map_selector.draw(self.screen)
        elif self.state == "playing":
            self.draw_playing()
        elif self.state == "game_over":
            self.draw_text("Game Over - Appuie sur R pour recommencer", 40, (255, 0, 0), WIDTH / 2, HEIGHT / 2)

        pygame.display.flip()

    def draw_text(self, text, size, color, x, y):
        """Utilitaire pour dessiner du texte centré"""
        font = pygame.font.Font(None, size)
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(x, y))
        self.screen.blit(surf, rect)


    def handle_game_update(self, msg):
        """Traite les mises à jour d'état du jeu depuis le serveur"""
        remote_player_list = msg.get("players")

        if not remote_player_list:
            return

        # Traiter chaque joueur
        for player_id in remote_player_list:
            player_data = remote_player_list.get(player_id)

            # ===== JOUEUR LOCAL : Réconciliation =====
            if player_id == self.client_id:
                self.player.reconcile_with_server(player_data)
                continue

            # ===== JOUEURS DISTANTS : Interpolation =====
            remote_player = self.game_manager.get_remote_player(player_id)
            if remote_player:
                remote_player.update_from_server(player_data)
            else:
                # Joueur distant pas encore créé localement (ne devrait pas arriver)
                print(f"[WARN] Remote player {player_id} not found in game_manager")

    def handle_map_data(self, msg: dict):
        """Reçoit et charge une map envoyée par le serveur"""
        map_data = msg.get("map")
        if not map_data:
            print("No map data received")
            return

        self.map_renderer.load_map(map_data)
        print(f"Map '{map_data.get('name')}' loaded successfully.")

    def handle_full_game_state(self, msg):
        print("Get full game state from server")
        your_player_data = msg.get("your_player", {})
        if your_player_data:
            self.player.pos.x = your_player_data.get("x", self.player.pos.x)
            self.player.pos.y = your_player_data.get("y", self.player.pos.y)
            self.player.life.life_current = your_player_data.get("healh", self.player.life.life_current)
            print(f"Your player spawned at ({self.player.pos.x}, {self.player.pos.y})")

        all_players = msg.get("players", {})
        all_players.pop(self.client_id)
        self.sync_remote_players(all_players)

    def handle_player_joined(self, msg):
        player = msg.get("player")
        print("Player join from server", player.get("id"))
        if self.client_id != player.get("id"):
            self.game_manager.add_object(RemotePlayer(player.get("id"), x=player.get("x"), y=player.get("y")))


    def handle_player_left(self, msg):
        print("Player left from server")
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

    def draw_playing(self):
        self.map_renderer.draw(self.screen)
        self.player.draw(self.screen)
        self.game_manager.draw_all(self.screen)
        self.draw_hud()

    def draw_hud(self):
        self.draw_text("server_request: {}".format(self.msg_old), 20, (255, 255, 255), 100, 50)
        count = self.game_manager.get_object_count()
        self.draw_text(f"Objets: {count}", 20, (255, 255, 255), 100, 30)
