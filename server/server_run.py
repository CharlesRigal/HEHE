import asyncio
import json
import logging
import signal
import socket
import sys
import time
from typing import Optional, List

from server.config import HOST, PORT
from server.game_instance import GameInstance
from server.map_loader import MapLoader
from server.state import CLIENTS, INSTANCES, CLIENT_SEQ

# Config logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Chargeur de maps global
map_loader = MapLoader("maps")


async def send_json(writer: asyncio.StreamWriter, obj: dict):
    try:
        raw = json.dumps(obj) + "\n"
        data = raw.encode("utf-8")
        writer.write(data)
        await writer.drain()
        logging.debug(f"-> Sent {len(data)} bytes to {peername(writer)}")
    except Exception as e:
        logging.warning(f"Failed to send data: {e}")


async def broadcast_json_to_players(obj: dict, player_ids: List[str], exclude_client: Optional[str] = None):
    """Diffuse un message JSON aux joueurs spécifiés"""
    disconnected_clients = []

    for client_id in player_ids:
        if client_id == exclude_client or client_id not in CLIENTS:
            continue

        try:
            _, writer = CLIENTS[client_id]
            await send_json(writer, obj)
        except Exception as e:
            logging.warning(f"Failed to broadcast to {client_id}: {e}")
            disconnected_clients.append(client_id)

    # Nettoyer les clients déconnectés
    for client_id in disconnected_clients:
        await cleanup_client(client_id)


async def broadcast_json(obj: dict, exclude_client: Optional[str] = None):
    """Diffuse un message JSON à tous les clients connectés"""
    player_ids = list(CLIENTS.keys())
    await broadcast_json_to_players(obj, player_ids, exclude_client)


def next_client_id() -> str:
    global CLIENT_SEQ
    CLIENT_SEQ += 1
    return f"p{CLIENT_SEQ}"


def peername(writer: asyncio.StreamWriter) -> str:
    try:
        return str(writer.get_extra_info("peername"))
    except Exception:
        return "unknown"


def find_player_instance(client_id: str) -> Optional[GameInstance]:
    """Trouve l'instance dans laquelle se trouve un joueur"""
    for instance in INSTANCES.values():
        if client_id in instance.players:
            return instance
    return None


async def handle_input_message(client_id: str, msg: dict):
    """Traite un message d'input d'un client"""
    instance = find_player_instance(client_id)
    if not instance:
        logging.warning(f"Input from player {client_id} not in any instance")
        return

    # Ajouter l'input à l'instance appropriée
    instance.add_input(client_id, {
        "k": msg.get("k", 0),
        "timestamp": time.time(),
        "seq": msg.get("seq", 0)
    })

    logging.debug(f"Input from {client_id}: {msg.get('k', 0)}")


async def handle_join_message(client_id: str, msg: dict):
    """Traite une demande de connexion au jeu"""
    map_id = msg.get("map", "forest")  # map par défaut

    # Vérifier si le joueur est déjà dans une instance
    current_instance = find_player_instance(client_id)
    if current_instance:
        logging.warning(f"Player {client_id} already in instance {current_instance.map_id}")
        return

    # Charger les données de la map
    map_data = map_loader.get_map(map_id)
    if not map_data:
        # Utiliser la map par défaut si la map demandée n'existe pas
        map_data = map_loader.get_default_map()
        if not map_data:
            await send_json(CLIENTS[client_id][1], {
                "t": "_error",
                "message": "No maps available"
            })
            return
        map_id = "default"

    # Créer ou récupérer l'instance de jeu
    if map_id not in INSTANCES:
        # Callback pour le broadcast spécifique à cette instance
        async def instance_broadcast(message, player_ids):
            await broadcast_json_to_players(message, player_ids)

        INSTANCES[map_id] = GameInstance(map_id, map_data, instance_broadcast)
        asyncio.create_task(INSTANCES[map_id].game_loop())

    instance = INSTANCES[map_id]

    # send the map to the client
    if client_id in CLIENTS:
        _, writer = CLIENTS[client_id]
        await send_json(writer, {
            "t": "map_data",
            "map": {
                "id": map_id,
                "name": map_data.get("name", "Unnamed"),
                "size": map_data.get("size", [1280, 720]),
                "objects": map_data.get("objects", [])
            }
        })

    # Créer le joueur dans l'instance
    player = instance.create_player(client_id)

    # on laisse le player qui se connect pour lui indiquer sont emplacement
    if client_id in CLIENTS:
        _, writer = CLIENTS[client_id]
        await send_json(writer, {
            "t": "game_state",
            "your_player": player,
            "players": instance.players
        })

    # Notifier les autres joueurs de cette instance
    await instance.broadcast_to_players({
        "t": "player_joined",
        "player": player
    })

    logging.info(f"Player {client_id} joined instance {map_id}")


async def handle_list_maps_message(client_id: str, msg: dict):
    """Envoie la liste des maps disponibles au client"""
    if client_id not in CLIENTS:
        return

    _, writer = CLIENTS[client_id]
    maps_list = map_loader.list_maps()

    await send_json(writer, {
        "t": "maps_list",
        "maps": maps_list
    })


async def cleanup_client(client_id: str):
    """Nettoie un client déconnecté"""
    # Supprimer de toutes les structures
    CLIENTS.pop(client_id, None)

    # Supprimer de son instance de jeu
    instance = find_player_instance(client_id)
    if instance:
        instance.remove_player(client_id)

        # Notifier les autres joueurs de cette instance
        await instance.broadcast_to_players({
            "t": "player_left",
            "player_id": client_id
        })

        # Si l'instance est vide, on peut la fermer (optionnel)
        if not instance.players:
            instance.stop()
            # On peut garder l'instance pour les prochains joueurs
            # ou la supprimer : INSTANCES.pop(instance.map_id, None)

        logging.info(f"Cleaned up player {client_id} from instance {instance.map_id}")


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, line=None, client_id=None):
    """Gère la connexion d'un client
    :type line: object
    """
    # Optimisation TCP
    try:
        sock = writer.get_extra_info("socket")
        if sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass

    client_id = next_client_id()
    CLIENTS[client_id] = (reader, writer)
    logging.info(f"Client connected {client_id} from {peername(writer)} (total={len(CLIENTS)})")

    # Message de bienvenue avec liste des maps
    try:
        maps_list = map_loader.list_maps()
        await send_json(writer, {
            "t": "welcome",
            "your_id": client_id,
            "available_maps": maps_list
        })
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
                logging.debug(f"<- {client_id}: {msg} ({len(line)} bytes)")
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

                elif msg_type == "list_maps":
                    await handle_list_maps_message(client_id, msg)

                elif msg_type == "chat":
                    # Chat global ou par instance
                    instance = find_player_instance(client_id)
                    if instance:
                        await instance.broadcast_to_players({
                            "t": "chat",
                            "from": client_id,
                            "message": msg.get("message", "")
                        })
                    else:
                        # Chat global si pas dans une instance
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

    # Arrêter toutes les instances de jeu
    for instance in INSTANCES.values():
        instance.stop()

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
    INSTANCES.clear()
    logging.info("Server shut down complete.")


async def main():
    host = HOST
    port = PORT
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    logging.info(f"Available maps: {map_loader.list_maps()}")

    server = await asyncio.start_server(handle_client, host, port)
    addr = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    logging.info(f"Server listening on {addr}")

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
        await shutdown(server)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass