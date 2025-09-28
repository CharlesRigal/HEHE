from importlib import resources

import pygame
import yaml
from pygame.transform import scale


class MapRenderer:
    """Gestion du rendu, collisions et informations d'une map"""

    def __init__(self):
        self.current_map = None
        self.map_surface = None
        self.collision_objects = []
        sprite_package = resources.files("client.assets")

        for sprite_list in sprite_package.iterdir():
            if sprite_list.is_file() and sprite_list.suffix in {".yaml", ".yml"}:
                self.sprite_config = yaml.safe_load(sprite_list.read_text()).get("sprites")

        self.loaded_sprites = {}

    def _get_sprite(self, obj_type: str):
        conf = self.sprite_config.get(obj_type)
        if not conf:
            return None

        if "image" in conf:
            if obj_type not in self.loaded_sprites:
                # Charger via importlib.resources
                asset_file = resources.files("client.assets.sprites") / conf["image"]
                try:
                    img = pygame.image.load(str(asset_file)).convert_alpha()
                except FileNotFoundError:
                    return None

                scale = conf.get("scale", 1.0)
                if scale != 1.0:
                    w, h = img.get_size()
                    img = pygame.transform.scale(img, (int(w * scale), int(h * scale)))

                self.loaded_sprites[obj_type] = img

            return self.loaded_sprites[obj_type]
        return None

    # --- Chargement ---
    def load_map(self, map_data: dict):
        """Charge une map complète"""
        self.current_map = map_data
        self.collision_objects = map_data.get("objects", [])
        self._prepare_map_surface()

    def _prepare_map_surface(self):
        """Crée une surface pygame avec tous les objets statiques"""
        if not self.current_map:
            return

        size = self.current_map.get("size", [1280, 720])
        self.map_surface = pygame.Surface(size, pygame.SRCALPHA)

        for obj in self.collision_objects:
            self._draw_object(obj)

    def _draw_object(self, obj: dict):
        """Dessine un objet unique"""
        points = obj.get("points", [])
        if len(points) < 3:
            return  # Il faut au moins 3 points pour un polygone

        obj_type = obj.get("type", "default")

        sprite = self._get_sprite(obj_type)

        if sprite:
            # Placer le sprite au premier point (ou au barycentre si tu veux centrer)
            rect = sprite.get_rect()
            rect.topleft = points[0]
            self.map_surface.blit(sprite, rect)
        else:
            # Dessiner un polygone avec la couleur correspondante
            color = self._get_color(obj_type)
            pygame.draw.polygon(self.map_surface, color, points)


    def _get_color(self, obj_type: str):
        palette = {
            "rock": (100, 100, 100),
            "tree": (34, 139, 34),
            "water": (30, 144, 255),
            "wall": (139, 69, 19),
            "default": (128, 128, 128),
        }
        return palette.get(obj_type, palette["default"])

    # --- Rendu ---
    def draw(self, screen: pygame.Surface, camera_offset=(0, 0)):
        if self.map_surface:
            screen.blit(self.map_surface, camera_offset)

    def draw_debug(self, screen: pygame.Surface, font: pygame.font.Font):
        if not self.current_map:
            return

        y = 10
        debug_lines = [
            f"Map: {self.current_map.get('name', 'Unknown')}",
            f"Size: {self.current_map.get('size', [0,0])[0]}x{self.current_map.get('size', [0,0])[1]}",
            f"Objects: {len(self.collision_objects)}",
        ]

        for line in debug_lines:
            text = font.render(line, True, (255, 255, 255))
            screen.blit(text, (10, y))
            y += 25

    # --- Collisions ---
    def check_collision(self, x, y, size=32) -> bool:
        """Collision joueur (AABB)"""
        x1, x2 = x - size / 2, x + size / 2
        y1, y2 = y - size / 2, y + size / 2

        for obj in self.collision_objects:
            pts = obj.get("points", [])
            if len(pts) >= 4:
                xs, ys = zip(*pts)
                if (x1 < max(xs) and x2 > min(xs) and
                        y1 < max(ys) and y2 > min(ys)):
                    return True
        return False

    def get_spawn_points(self):
        return self.current_map.get("spawn_points", []) if self.current_map else []
