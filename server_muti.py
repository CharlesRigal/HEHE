import asyncio
import json
import logging
import signal
import socket
import sys
import time
from typing import Dict, Optional

HOST = "0.0.0.0"
PORT = 9000
TICK_RATE = 60  # Fréquence de simulation du jeu (Hz)
TICK_INTERVAL = 1.0 / TICK_RATE  # Intervalle entre chaque tick

# Clients connectés: client_id -> (reader, writer)
CLIENTS: Dict[str, tuple] = {}
CLIENT_SEQ = 0

# État des joueurs: client_id -> état du joueur
PLAYERS: Dict[str, dict] = {}

# Inputs en attente de traitement: client_id -> dernier input reçu
PENDING_INPUTS: Dict[str, dict] = {}

# Config logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


async def send_json(writer: asyncio.StreamWriter, obj: dict):
    """Envoie un objet JSON au client"""
    try:
        data = (json.dumps(obj) + "\n").encode("utf-8")
        writer.write(data)
        await writer.drain()
    except Exception as e:
        logging.warning(f"Failed to send data: {e}")


async def broadcast_json(obj: dict, exclude_client: Optional[str] = None):
    """Diffuse un message JSON à tous les clients connectés"""
    disconnected_clients = []

    for client_id, (_, writer) in CLIENTS.items():
        if client_id == exclude_client:
            continue

        try:
            await send_json(writer, obj)
        except Exception as e:
            logging.warning(f"Failed to broadcast to {client_id}: {e}")
            disconnected_clients.append(client_id)

    # Nettoyer les clients déconnectés
    for client_id in disconnected_clients:
        await cleanup_client(client_id)


def next_client_id() -> str:
    global CLIENT_SEQ
    CLIENT_SEQ += 1
    return f"p{CLIENT_SEQ}"


def peername(writer: asyncio.StreamWriter) -> str:
    try:
        return str(writer.get_extra_info("peername"))
    except Exception:
        return "unknown"


def create_player(client_id: str, x: float = 100, y: float = 100) -> dict:
    """Crée un nouveau joueur avec état initial"""
    return {
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


def process_input(player: dict, input_data: dict, dt: float):
    """Traite les inputs d'un joueur et met à jour sa position"""
    if not player["alive"]:
        return

    # Récupérer le masque d'input (comme dans votre Player class)
    k = input_data.get("k", 0)
    speed = 200.0  # Vitesse de base

    # Constantes d'input (même que dans Player.py)
    IN_UP = 1
    IN_DOWN = 2
    IN_LEFT = 4
    IN_RIGHT = 8
    IN_FIRE = 32

    # Calcul de la vélocité
    vx = vy = 0.0
    if k & IN_UP:
        vy -= speed
    if k & IN_DOWN:
        vy += speed
    if k & IN_LEFT:
        vx -= speed
    if k & IN_RIGHT:
        vx += speed

    # Normalisation diagonale
    if vx != 0 and vy != 0:
        diagonal_factor = 0.7071067811865476  # 1/sqrt(2)
        vx *= diagonal_factor
        vy *= diagonal_factor

    # Mise à jour de la position
    player["vx"] = vx
    player["vy"] = vy
    player["x"] += vx * dt
    player["y"] += vy * dt

    # Contraintes de map (ajustez selon votre jeu)
    MAP_WIDTH = 800
    MAP_HEIGHT = 600
    PLAYER_SIZE = 32

    player["x"] = max(PLAYER_SIZE / 2, min(player["x"], MAP_WIDTH - PLAYER_SIZE / 2))
    player["y"] = max(PLAYER_SIZE / 2, min(player["y"], MAP_HEIGHT - PLAYER_SIZE / 2))

    player["last_update"] = time.time()


async def handle_input_message(client_id: str, msg: dict):
    """Traite un message d'input d'un client"""
    if client_id not in PLAYERS:
        logging.warning(f"Input from unknown player {client_id}")
        return

    # Stocker l'input pour le prochain tick de simulation
    PENDING_INPUTS[client_id] = {
        "k": msg.get("k", 0),
        "timestamp": time.time(),
        "seq": msg.get("seq", 0)  # Numéro de séquence pour la synchronisation
    }

    logging.debug(f"Input from {client_id}: {msg.get('k', 0)}")


async def handle_join_message(client_id: str, msg: dict):
    """Traite une demande de connexion au jeu"""
    if client_id in PLAYERS:
        logging.warning(f"Player {client_id} already exists")
        return

    # Créer le joueur
    player = create_player(client_id)
    PLAYERS[client_id] = player

    # Envoyer l'état initial au nouveau joueur
    if client_id in CLIENTS:
        _, writer = CLIENTS[client_id]
        await send_json(writer, {
            "t": "game_state",
            "your_player": player,
            "players": PLAYERS
        })

    # Notifier les autres joueurs
    await broadcast_json({
        "t": "player_joined",
        "player": player
    }, exclude_client=client_id)

    logging.info(f"Player {client_id} joined the game")


async def cleanup_client(client_id: str):
    """Nettoie un client déconnecté"""
    # Supprimer de toutes les structures
    CLIENTS.pop(client_id, None)
    if client_id in PLAYERS:
        PLAYERS.pop(client_id)
        PENDING_INPUTS.pop(client_id, None)

        # Notifier les autres joueurs
        await broadcast_json({
            "t": "player_left",
            "player_id": client_id
        })

        logging.info(f"Cleaned up player {client_id}")


async def game_loop():
    """Boucle principale du jeu - traite la logique à intervalles réguliers"""
    last_time = time.time()

    while True:
        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time

        # Traiter tous les inputs en attente
        for client_id, input_data in PENDING_INPUTS.items():
            if client_id in PLAYERS:
                process_input(PLAYERS[client_id], input_data, dt)

        # Vider les inputs traités
        PENDING_INPUTS.clear()

        # Envoyer l'état du jeu à tous les clients (si des joueurs ont bougé)
        if PLAYERS:
            game_state = {
                "t": "game_update",
                "players": PLAYERS,
                "timestamp": current_time
            }
            await broadcast_json(game_state)

        # Attendre jusqu'au prochain tick
        await asyncio.sleep(max(0, TICK_INTERVAL - (time.time() - current_time)))


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Gère la connexion d'un client"""
    # Baisser la latence TCP
    try:
        sock = writer.get_extra_info("socket")
        if sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass

    client_id = next_client_id()
    CLIENTS[client_id] = (reader, writer)
    logging.info(f"Client connected {client_id} from {peername(writer)} (total={len(CLIENTS)})")

    # Message de bienvenue
    try:
        await send_json(writer, {"t": "welcome", "your_id": client_id})
    except Exception as e:
        logging.warning(f"Failed to send welcome to {client_id}: {e}")
        return

    buf_limit = 256 * 1024

    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            if len(raw) > buf_limit:
                logging.warning(f"Line too long from {client_id}, closing.")
                break

            line = raw.strip()
            if not line:
                continue

            try:
                msg = json.loads(line.decode("utf-8"))
                logging.debug(f"<- {client_id}: {msg}")
            except json.JSONDecodeError:
                logging.info(f"<- {client_id} (text): {line!r}")
                continue

            # Router les messages par type
            if isinstance(msg, dict):
                msg_type = msg.get("t")

                if msg_type == "ping":
                    await send_json(writer, {"t": "pong"})

                elif msg_type == "join":
                    await handle_join_message(client_id, msg)

                elif msg_type == "in":
                    await handle_input_message(client_id, msg)

                elif msg_type == "chat":
                    # Relayer le message de chat
                    await broadcast_json({
                        "t": "chat",
                        "from": client_id,
                        "message": msg.get("message", "")
                    })

                else:
                    logging.warning(f"Unknown message type from {client_id}: {msg_type}")

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.warning(f"Error with {client_id}: {e}")
    finally:
        await cleanup_client(client_id)


async def shutdown(server: asyncio.AbstractServer):
    """Arrêt propre du serveur"""
    logging.info("Shutting down server...")
    server.close()
    await server.wait_closed()

    # Fermer les connexions actives
    for cid, (_, w) in list(CLIENTS.items()):
        try:
            w.close()
        except Exception:
            pass
    for cid, (_, w) in list(CLIENTS.items()):
        try:
            await w.wait_closed()
        except Exception:
            pass

    CLIENTS.clear()
    PLAYERS.clear()
    PENDING_INPUTS.clear()
    logging.info("Server shut down complete.")


async def main():
    host = HOST
    port = PORT
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    server = await asyncio.start_server(handle_client, host, port)
    addr = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    logging.info(f"Server listening on {addr}")

    # Démarrer la boucle de jeu en parallèle
    game_task = asyncio.create_task(game_loop())

    # Gestion des signaux
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    try:
        await stop.wait()
    finally:
        game_task.cancel()
        try:
            await game_task
        except asyncio.CancelledError:
            pass
        await shutdown(server)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass