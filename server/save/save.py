from pathlib import Path

import yaml

from server.save.error import PlayerNotFound

BASE_SAVE_DICT = {
    "maps": {},
    "players": {},
}

_instance: "Save | None" = None


def get_save() -> "Save":
    global _instance
    if _instance is None:
        _instance = Save()
    return _instance


class Save:
    def __init__(self) -> None:
        self.file = Path("save.yml")
        if self.file.exists():
            with open(self.file, "r") as stream:
                self.yaml_data = yaml.safe_load(stream) or {}
        else:
            self.yaml_data = dict(BASE_SAVE_DICT)
            self._flush()

    def get_player_state(self, player_id: str) -> dict | None:
        players = self.yaml_data.get("players", {})
        state = players.get(player_id)
        if state is None:
            raise PlayerNotFound(f"Player {player_id} not found")
        return state

    def create_player(self, player_id: str) -> None:
        players = self.yaml_data.setdefault("players", {})
        if player_id not in players:
            players[player_id] = {}
            self._flush()

    def update_player_state(self, player_id: str, state: dict) -> None:
        players = self.yaml_data.setdefault("players", {})
        existing = players.get(player_id, {})
        existing.update(state)
        players[player_id] = existing
        self._flush()

    def update_pos_player_map(self, map_name: str, player_id: str, position: tuple[float, float]) -> None:
        maps = self.yaml_data.setdefault("maps", {})
        map_entry = maps.setdefault(map_name, {"players": {}})
        map_entry.setdefault("players", {})[player_id] = list(position)
        self._flush()

    def get_player_pos_on_a_map(self, map_name: str, player_id: str) -> tuple[float, float]:
        maps = self.yaml_data.get("maps", {})
        map_entry = maps.get(map_name, {})
        players = map_entry.get("players", {})
        pos = players.get(player_id)
        if pos is None:
            raise PlayerNotFound(f"Player {player_id} not found on map {map_name}")
        return (pos[0], pos[1])

    def _flush(self) -> None:
        with open(self.file, "w") as stream:
            yaml.dump(self.yaml_data, stream)
