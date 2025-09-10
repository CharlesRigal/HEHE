import asyncio
import json
import logging
import signal
import socket
import sys
from typing import Dict

HOST = "0.0.0.0"
PORT = 9000

# Clients connectés: client_id -> (reader, writer)
CLIENTS: Dict[str, tuple] = {}
CLIENT_SEQ = 0

# Config logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


async def send_json(writer: asyncio.StreamWriter, obj: dict):
    data = (json.dumps(obj) + "\n").encode("utf-8")
    writer.write(data)
    await writer.drain()


def next_client_id() -> str:
    global CLIENT_SEQ
    CLIENT_SEQ += 1
    return f"p{CLIENT_SEQ}"


def peername(writer: asyncio.StreamWriter) -> str:
    try:
        return str(writer.get_extra_info("peername"))
    except Exception:
        return "unknown"


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
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

    # Message de bienvenue pour permettre au client de s’identifier
    try:
        await send_json(writer, {"type": "welcome", "your_id": client_id})
    except Exception as e:
        logging.warning(f"Failed to send welcome to {client_id}: {e}")

    buf_limit = 256 * 1024  # limite simple pour éviter les lignes trop longues

    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            if len(raw) > buf_limit:
                logging.warning(f"Line too long from {client_id}, closing.")
                break

            # Nettoyer fin de ligne et parser JSON si possible
            line = raw.strip()
            if not line:
                continue

            try:
                msg = json.loads(line.decode("utf-8"))
                logging.info(f"<- {client_id}: {msg}")
            except json.JSONDecodeError:
                # Si ce n’est pas du JSON, on log simplement le texte
                logging.info(f"<- {client_id} (text): {line!r}")
                msg = None

            if isinstance(msg, dict) and msg.get("type") == "ping":
                await send_json(writer, {"type": "pong"})
            # TODO Ici router par type: input, chat, join_room, etc.

    except asyncio.CancelledError:
        # Arrêt propre demandé
        pass
    except Exception as e:
        logging.warning(f"Error with {client_id}: {e}")
    finally:
        # Nettoyage
        CLIENTS.pop(client_id, None)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        logging.info(f"Client disconnected {client_id} (total={len(CLIENTS)})")


async def shutdown(server: asyncio.AbstractServer):
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
    logging.info("Server shut down complete.")


async def main():
    host = HOST
    port = PORT
    # Permettre de passer host/port en CLI: python server.py 0.0.0.0 9000
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    server = await asyncio.start_server(handle_client, host, port)
    addr = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    logging.info(f"Server listening on {addr}")

    # Gestion des signaux pour un arrêt propre (Ctrl+C)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # Windows: pas de signal handler dans asyncio
            pass

    # Attente jusqu’au signal d’arrêt
    await stop.wait()
    await shutdown(server)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
