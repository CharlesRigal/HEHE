# server/map_loader.py
import yaml
import importlib.resources as resources

maps_package = resources.files("server.maps")

import pathlib
from typing import Dict, Optional


class MapLoader:
    def __init__(self, package: str = "server.maps"):
        self.package = package
        self.loaded_maps = {}
        self._load_all_maps()

    def _load_all_maps(self):
        """Charge toutes les maps contenues dans le package donné"""
        maps_package = resources.files(self.package)

        for map_file in maps_package.iterdir():
            if not map_file.name.endswith(".yaml"):
                continue

            try:
                with map_file.open("r", encoding="utf-8") as f:
                    map_data = yaml.safe_load(f)

                map_id = map_file.stem  # nom du fichier sans extension
                self.loaded_maps[map_id] = map_data
                print(f"Loaded map: {map_id} - {map_data.get('name', 'Unnamed')}")

            except Exception as e:
                print(f"Error loading map {map_file}: {e}")

    def get_map(self, map_id: str) -> Optional[dict]:
        """Récupère une map par son ID"""
        return self.loaded_maps.get(map_id)

    def list_maps(self) -> Dict[str, str]:
        """Retourne la liste des maps disponibles avec leurs noms"""
        return {
            map_id: map_data.get('name', 'Unnamed')
            for map_id, map_data in self.loaded_maps.items()
        }

    def get_default_map(self) -> Optional[dict]:
        """Retourne la première map disponible comme map par défaut"""
        if self.loaded_maps:
            return next(iter(self.loaded_maps.values()))
        return None