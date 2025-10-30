# server/config.py
import yaml, pathlib

CONFIG_PATH = pathlib.Path(__file__).parent / "config.yaml"

with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

HOST = CONFIG.get("server", {}).get("host", "0.0.0.0")
PORT = CONFIG.get("server", {}).get("port", 9000)
TICK_RATE = CONFIG.get("server", {}).get("tick_rate", 60)
TICK_INTERVAL = 1.0 / TICK_RATE
print(f"[DEBUG] Server TICK_INTERVAL = {TICK_INTERVAL*1000:.4f}ms")