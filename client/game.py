import queue
import time

import pygame

from network import NetworkClient

from enemy import EnemyEye
from game_manager import GameManager
from remote_player import RemotePlayer
from settings import WIDTH, HEIGHT, FPS, BLACK
from player import Player
from utils import get_random_location_away_from_screen_circle


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

    def join_the_server(self):
        if self.net is not None:
            self.net.send_join_request()

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
        elif t == "game_state":
            self.handle_full_game_state(msg)
        elif t == "game_update":
            self.handle_game_update(msg)
        elif t == "player_joined":
            self.handle_player_joined(msg)
        elif t == "player_left":
            self.handle_player_left(msg)
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
            self.handle_server_message(msg)

    def __init__(self):
        pygame.init()
        self.game_manager = GameManager()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
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

        # états du jeu
        self.state = "menu"  # menu, playing, game_over

        # Chargement du background
        self.load_background()

        # entités
        self.player = Player("client/assets/images/player.png", (WIDTH / 2, HEIGHT / 2))

        # IMPORTANT: Ajouter le joueur au gestionnaire s'il hérite de GameObject
        # Sinon, on le gère séparément
        # self.game_manager.add_object(self.player)  # Décommenter si Player hérite de GameObject

        self.enemies = []  # Peut être supprimé si on utilise que le game_manager

    def load_background(self):
        """Charge et prépare l'image de background"""
        try:
            # Essayer de charger l'image de background
            self.background = pygame.image.load("client/assets/images/dirt_and_grass.png").convert()
            self.has_background = True
        except pygame.error:
            # Si l'image n'existe pas, utiliser une couleur de fond
            print("Background image not found, using solid color")
            self.background = pygame.Surface((WIDTH, HEIGHT))
            self.background.fill(BLACK)  # ou une autre couleur comme (50, 50, 80)
            self.has_background = False

    def draw_background(self):
        """Dessine le background"""
        self.screen.blit(self.background, (0, 0))

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
                    self.state = "playing"
                    self.connect_to_server()
                    self.join_the_server()

            elif self.state == "game_over":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    self.state = "menu"

    def update(self, dt):
        """Logique du jeu selon l'état"""
        if self.state == "menu":
            # futur menu
            pass
        elif self.state == "playing":
            if self.start_time is None:
                self.start_time = pygame.time.get_ticks()

            elapsed = (pygame.time.get_ticks() - self.start_time) / 1000
            current_time = pygame.time.get_ticks() / 1000.0

            # Spawn enemies
            if elapsed > 2.5 and len(self.enemies) == 0:
                enemy = EnemyEye(pos=get_random_location_away_from_screen_circle(min_radius=100),
                                 targeted_player=self.player)
                # IMPORTANT: Définir le game_manager pour que l'ennemi puisse créer des projectiles
                enemy.set_game_manager(self.game_manager)
                self.game_manager.add_object(enemy)
                self.enemies.append(enemy)  # Pour le comptage (optionnel)

            inp = self.player.read_local_input()
            self.player.apply_input(inp, dt)
            self.send_input_if_needed(inp)

            # Mettre à jour tous les objets gérés
            self.game_manager.update_all(dt, self.player, current_time)

            # Vérifier les collisions
            self.check_collisions()

        elif self.state == "game_over":
            pass

    def check_collisions(self):
        """Vérification des collisions entre projectiles et joueur"""
        from projectile import Projectile  # Import local pour éviter les imports circulaires

        projectiles = self.game_manager.get_objects_by_type(Projectile)

        for projectile in projectiles:
            if projectile.rect.colliderect(self.player.rect):
                # Le joueur prend des dégâts
                remaining_health = self.player.take_damage(projectile.damage)
                # Supprimer le projectile
                self.game_manager.remove_object(projectile)

                # Vérifier si le joueur est mort
                if remaining_health <= 0:
                    self.state = "game_over"

    def draw(self):
        """Rendu graphique"""
        # Dessiner le background en premier
        self.draw_background()

        if self.state == "menu":
            self.draw_text("Appuie sur une touche pour jouer", 40, (255, 255, 255), WIDTH / 2, HEIGHT / 2)
        elif self.state == "playing":

            # Dessiner le joueur (s'il n'est pas dans le game_manager)
            self.player.draw(self.screen)

            # Dessiner tous les objets gérés (ennemis, projectiles, etc.)
            self.game_manager.draw_all(self.screen)

            # Debug info (optionnel)
            count = self.game_manager.get_object_count()
            self.draw_text(f"Objets: {count}", 20, (255, 255, 255), 100, 30)

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
        remote_player_list = msg.get("players")
        remote_player_list.pop(self.client_id, None)
        for player in remote_player_list:
            player_remote_new_status = remote_player_list.get(player)
            remote_player: RemotePlayer = self.game_manager.get_remote_player(player)
            if remote_player:
                remote_player.update_from_server(player_remote_new_status)


    def handle_full_game_state(self, msg):
        print("Get full game state from server")
        your_player_data = msg.get("your_player", {})
        if your_player_data:
            self.player.pos.x = your_player_data.get("x", self.player.pos.x)
            self.player.pos.y = your_player_data.get("y", self.player.pos.y)
            self.player.life.life_current = your_player_data.get("healh", self.player.life.life_current)
            print(f"Your player spawned at ({self.player.pos.x}, {self.player.pos.y})")

        all_players = msg.get("players", {})
        self.sync_remote_players(all_players)
        pass

    def handle_player_joined(self, msg):
        player = msg.get("player")
        self.game_manager.add_object(RemotePlayer(player.get("id"), x=player.get("x"), y=player.get("y")))


    def handle_player_left(self, msg):
        print("Player left from server")
        player_to_remove = self.game_manager.get_remote_player(msg.get("player_id"))
        self.game_manager.remove_object(player_to_remove)



    def update_or_create_remote_player(self, player_id, player_data):
        """Met à jour ou crée un joueur distant"""
        # Chercher si le joueur existe déjà dans le game_manager
        self.game_manager.get_remote_player(player_id)

    def sync_remote_players(self, all_players):
        for player_id in all_players:
            if player_id != self.client_id:
                self.update_or_create_remote_player(player_id, all_players[player_id])
                player_dict = all_players.get(player_id)
                player_obj = RemotePlayer(player_id, x=player_dict.get("x"), y=player_dict.get("y"))
                self.game_manager.add_object(player_obj)
