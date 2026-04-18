import json
import queue
import threading
import socket


class NetworkClient(threading.Thread):

    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.socket = None
        self.stop_event = threading.Event()
        self.send_q = queue.Queue()
        self.recv_q = queue.Queue()
        self.connected = False

    def connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(3.0)
        s.connect((self.host, self.port))
        s.settimeout(0.05)
        self.socket = s
        self.connected = True

    def run(self):
        buf = b""
        try:
            while not self.stop_event.is_set():
                # envoi
                try:
                    while True:
                        msg = self.send_q.get_nowait()
                        data = (json.dumps(msg) + "\n").encode("utf-8")
                        self.socket.sendall(data)
                except queue.Empty:
                    pass
                except Exception as e:
                    self.recv_q.put({"t": "_error", "where": "send", "error": str(e)})
                    break

                try:
                    chunk = self.socket.recv(4096)
                    if not chunk:
                        self.recv_q.put({"t": "_info", "event": "server_closed"})
                        break
                    buf += chunk
                    while True:
                        nl = buf.find(b"\n")
                        if nl == -1:
                            break
                        line = buf[:nl]
                        buf  = buf[nl+1:]
                        if not line:
                            continue
                        try:
                            obj = json.loads(line.decode("utf-8"))
                        except json.JSONDecodeError:
                            obj = {"t": "_raw", "data": line.decode("utf-8", errors="ignore")}
                        self.recv_q.put(obj)
                except socket.timeout:
                    pass
                except Exception as e:
                    self.recv_q.put({"t": "_error", "where": "recv", "error": str(e)})
                    break
        finally:
            try:
                if self.socket:
                    self.socket.close()
            except Exception:
                pass
            self.connected = False

    def _send(self, obj:dict):
        if not self.connected:
            return
        self.send_q.put(obj)

    def send_request_map(self) -> dict:
        msg = {"t": "list_maps"}
        self._send(msg)
        return msg

    def send_ast_spell(self, ast_spell: dict) -> dict:
        # Le spec issu de params_to_network_spec inclut deja "t": "s".
        # On se contente de s'assurer qu'il est present puis on envoie tel quel.
        msg = dict(ast_spell) if isinstance(ast_spell, dict) else {}
        msg.setdefault("t", "s")
        self._send(msg)
        return msg

    def send_join_request(self, map, uid: str = "") -> dict:
        msg = {"t": "join", "map": map}
        if uid:
            msg["uid"] = uid
        self._send(msg)
        return msg

    def send_input(self, input) -> dict:
        msg = {"t": "in", "seq": input.get("seq"), "k": input.get("k")}
        self._send(msg)
        return msg

    def close(self):
        self.stop_event.set()
        try:
            if self.socket:
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.socket.close()
        except Exception:
            pass

