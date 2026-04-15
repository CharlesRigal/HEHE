import queue
import time
import logging
import pygame

from client.entities.magical_draw import MagicalDraw
from client.game_state.playing import playing
from client.graphics.map_renderer import MapRenderer
from client.graphics.map_selector import MapSelector
from client.graphics.game_menu import GameMenu
from client.magic.geometry_analyzer import GeometryAnalyzer
from client.network.network import NetworkClient
from client.ui.spell_debug_overlay import SpellDebugOverlay
from client.debug.spell_logger import SpellLogger
from client.entities.active_spell_renderer import ActiveSpellRenderer
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

        self.game_menu:GameMenu = GameMenu(screen_width=self.screen.get_width(), screen_height=self.screen.get_height())

        self.map_renderer:MapRenderer = MapRenderer()
        self.map_selector:MapSelector = MapSelector(self.screen.get_width(), self.screen.get_height())
        self.player:Player = Player(
            "1",
            0,
            0,
            "client/assets/images/full_mage.png",
            magical_draw=MagicalDraw(self.screen),
        )
        self.player.map_renderer = self.map_renderer

        # ===== VARIABLES POUR FIXED TIMESTEP =====
        self.accumulator = 0.0  # Temps accumulé pour les ticks de logique
        self.current_time = time.time()
        self.max_frame_time = 0.25  # Protection contre la spirale de la mort
        self._font_cache: dict[int, pygame.font.Font] = {}
        self.debug_mode = False
        self.spell_debug_overlay = SpellDebugOverlay(self)
        self.spell_logger = SpellLogger()
        self._server_spells: list[dict] = []
        self._spell_renderer = ActiveSpellRenderer()

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

            # Ticks logiques seulement si l'état en a besoin
            if self.state == "playing":
                while self.accumulator >= TICK_INTERVAL:
                    self.update_logic(TICK_INTERVAL)
                    self.accumulator -= TICK_INTERVAL
            else:
                self.accumulator = 0.0

            # Calculer l'alpha pour l'interpolation (optionnel)
            # alpha = self.accumulator / TICK_INTERVAL

            # Rendu (à chaque frame, fréquence variable)
            self.draw()

            # Limiter le FPS maximum
            self.clock.tick(FPS)

        pygame.quit()

    def update_logic(self, dt):
        """Mise à jour de la logique du jeu à fréquence fixe (60 Hz)"""
        playing(self, tick_rate=dt)

    def draw(self):
        """Rendu graphique (fréquence variable)"""
        if self.state in ("menu", "map_selection", "game_over"):
            self.draw_background()

        if self.state == "menu":
            self.game_menu.draw(self.screen)
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
        self.spell_logger.close()

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

            if event.type == pygame.KEYDOWN and event.key == pygame.K_F1 and (event.mod & pygame.KMOD_CTRL):
                self._toggle_debug_mode()
                continue

            if event.type == pygame.KEYDOWN and event.key == pygame.K_F5:
                self.spell_debug_overlay.toggle()
                continue

            if event.type == pygame.KEYDOWN and self.spell_debug_overlay.visible:
                if event.key == pygame.K_LEFTBRACKET:
                    self.spell_debug_overlay.prev_stage()
                    continue
                elif event.key == pygame.K_RIGHTBRACKET:
                    self.spell_debug_overlay.next_stage()
                    continue

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

    def _get_font(self, size: int) -> pygame.font.Font:
        font = self._font_cache.get(size)
        if font is None:
            font = pygame.font.Font(None, size)
            self._font_cache[size] = font
        return font

    def draw_text(self, text, size, color, x, y):
        font = self._get_font(size)
        surf = font.render(str(text), True, color)
        rect = surf.get_rect(center=(x, y))
        self.screen.blit(surf, rect)

    def _toggle_debug_mode(self) -> None:
        self.debug_mode = not self.debug_mode
        logging.info(f"Debug mode: {'ON' if self.debug_mode else 'OFF'} (toggle Alt+F1)")

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

        if "spells" in msg:
            self._server_spells = msg["spells"]

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
        self._spell_renderer.draw(self.screen, self._server_spells, self.camera)
        if self.player.magical_draw.should_render(now, board_pressed):
            self.screen.blit(self.player.magical_draw.draw(), (0, 0))
        self.draw_hud()
        self.spell_debug_overlay.draw(self.screen)

    def draw_hud(self):
        if not self.debug_mode:
            return

        msg_type = "-"
        if isinstance(self.msg_old, dict):
            msg_type = str(self.msg_old.get("t", "?"))
        elif self.msg_old:
            msg_type = str(self.msg_old)

        player_pos = getattr(self.player, "pos", pygame.Vector2())
        render_pos = getattr(self.player, "render_pos", pygame.Vector2())
        recv_q = self._safe_queue_size(getattr(self.net, "recv_q", None))
        send_q = self._safe_queue_size(getattr(self.net, "send_q", None))
        pending_inputs = len(getattr(self.player, "pending_inputs", []))
        object_count = self.game_manager.get_object_count()
        fps = self.clock.get_fps()
        logic_backlog = int(self.accumulator / TICK_INTERVAL)
        map_surface = getattr(self.map_renderer, "map_surface", None)
        map_size = (
            f"{map_surface.get_width()}x{map_surface.get_height()}"
            if map_surface is not None
            else "-"
        )

        magical_snapshot = {}
        if self.player and self.player.magical_draw and hasattr(self.player.magical_draw, "debug_snapshot"):
            magical_snapshot = self.player.magical_draw.debug_snapshot()

        lines = [
            "DEBUG MODE [Alt+F1]",
            f"state={self.state} fps={fps:.1f} backlog={logic_backlog}",
            f"net={'on' if self.net_connected else 'off'} send_q={send_q} recv_q={recv_q} msg={msg_type}",
            f"objects={object_count} pending_inputs={pending_inputs}",
            f"player=({player_pos.x:.1f},{player_pos.y:.1f}) render=({render_pos.x:.1f},{render_pos.y:.1f})",
            f"map={map_size}",
        ]
        if magical_snapshot:
            lines.append(
                "magic "
                f"strokes={magical_snapshot.get('strokes', 0)} "
                f"active_points={magical_snapshot.get('active_points', 0)} "
                f"primitives={magical_snapshot.get('primitives', 0)} "
                f"order_fx={magical_snapshot.get('order_effects', 0)} "
                f"clear_waiting={1 if magical_snapshot.get('clear_waiting', False) else 0}"
            )

        font = self._get_font(18)
        line_height = 20
        panel_padding = 8
        max_width = max(font.size(line)[0] for line in lines) + panel_padding * 2
        panel_height = len(lines) * line_height + panel_padding * 2

        panel = pygame.Surface((max_width, panel_height), pygame.SRCALPHA)
        panel.fill((8, 12, 18, 170))
        pygame.draw.rect(panel, (92, 170, 255, 210), panel.get_rect(), width=1)
        self.screen.blit(panel, (12, 12))

        text_x = 12 + panel_padding
        text_y = 12 + panel_padding
        for line in lines:
            surf = font.render(line, True, (230, 244, 255))
            self.screen.blit(surf, (text_x, text_y))
            text_y += line_height

    @staticmethod
    def _safe_queue_size(queue_obj) -> int:
        if queue_obj is None:
            return 0
        try:
            return int(queue_obj.qsize())
        except Exception:
            return -1

    def cast_spell(self, net_spec: dict) -> None:
        """Envoie un sort au serveur."""
        logging.info(f"Spell cast: {net_spec}")
        if self.net_connected and self.net is not None:
            try:
                self.net.send(net_spec)
            except Exception as e:
                logging.warning(f"Failed to send AST spell to server: {e}")
        else:
            logging.info("AST spell cast locally (not connected to server)")

    def _compute_forward_cast_center(
        self,
        *,
        hitbox_radius: float,
        fallback_center: tuple[float, float],
        distance_bonus: float = 0.0,
    ) -> tuple[float, float]:
        player = getattr(self, "player", None)
        map_renderer = getattr(self, "map_renderer", None)
        if player is None:
            return fallback_center

        try:
            px, py = player.get_position()
        except Exception:
            return fallback_center

        if hasattr(player, "get_facing_vector"):
            try:
                facing = player.get_facing_vector()
            except Exception:
                facing = pygame.Vector2(1.0, 0.0)
        else:
            facing = pygame.Vector2(1.0, 0.0)

        if facing.length_squared() <= 1e-9:
            facing = pygame.Vector2(1.0, 0.0)
        else:
            facing = facing.normalize()

        cast_distance = max(24.0, float(hitbox_radius) + 10.0 + max(0.0, float(distance_bonus)))
        cx = float(px + facing.x * cast_distance)
        cy = float(py + facing.y * cast_distance)

        if map_renderer and getattr(map_renderer, "map_surface", None) is not None:
            width = map_renderer.map_surface.get_width()
            height = map_renderer.map_surface.get_height()
            margin = max(1.0, float(hitbox_radius))
            cx = max(margin, min(cx, width - margin))
            cy = max(margin, min(cy, height - margin))

        return (cx, cy)
