import sys
import uuid
from pathlib import Path


def _identity_file(slot: str | None) -> Path:
    if slot:
        return Path(f"player_uuid_{slot}")
    return Path("player_uuid")


def get_player_uuid(slot: str | None = None) -> str:
    path = _identity_file(slot)
    if path.exists():
        stored = path.read_text().strip()
        if stored:
            return stored
    new_uuid = uuid.uuid4().hex[:12]
    path.write_text(new_uuid)
    return new_uuid


def parse_slot_from_argv() -> str | None:
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--slot" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--slot="):
            return arg.split("=", 1)[1]
    return None
