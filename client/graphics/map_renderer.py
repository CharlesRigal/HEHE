from importlib import resources
import pygame
import yaml


class MapRenderer:
    """Gestion du rendu, collisions et informations d'une map"""

    def __init__(self):
        self.current_map = None
        self.map_surface = None
        self.collision_objects = []

        # Charger la config sprites + backgrounds
        sprite_package = resources.files("client.assets")

        for sprite_list in sprite_package.iterdir():
            if sprite_list.is_file() and sprite_list.suffix in {".yaml", ".yml"}:
                file = yaml.safe_load(sprite_list.read_text())
                self.sprite_config = file.get("sprites", {})
                self.background_config = file.get("backgrounds", {})

        self.loaded_sprites = {}
        self.loaded_backgrounds = {}

    # --- Gestion sprites ---
    def _get_sprite(self, obj_type: str):
        conf = self.sprite_config.get(obj_type)
        if not conf:
            return None

        if "image" in conf:
            if obj_type not in self.loaded_sprites:
                asset_file = resources.files("client.assets.sprites") / conf["image"]
                try:
                    img = pygame.image.load(str(asset_file)).convert_alpha()
                except FileNotFoundError:
                    print(f"[WARN] Sprite introuvable: {conf['image']}")
                    return None

                scale = conf.get("scale", 1.0)
                if scale != 1.0:
                    w, h = img.get_size()
                    img = pygame.transform.scale(img, (int(w * scale), int(h * scale)))

                self.loaded_sprites[obj_type] = img
                print(f"[INFO] Sprite chargé: {obj_type}")

            return self.loaded_sprites[obj_type]
        return None

    # --- Gestion backgrounds ---
    def _get_background(self, bg_name: str):
        if not bg_name or bg_name not in self.background_config:
            return None

        if bg_name not in self.loaded_backgrounds:
            asset_file = resources.files("client.assets.backgrounds") / self.background_config[bg_name]
            try:
                img = pygame.image.load(str(asset_file)).convert()
            except FileNotFoundError:
                print(f"[WARN] Background introuvable: {self.background_config[bg_name]}")
                return None

            self.loaded_backgrounds[bg_name] = img
            print(f"[INFO] Background chargé: {bg_name}")

        return self.loaded_backgrounds[bg_name]

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

        # Charger le background
        bg_name = self.current_map.get("background")
        bg = self._get_background(bg_name)

        if bg:
            bw, bh = bg.get_size()
            mw, mh = size

            # Tuilage du background si trop petit
            for x in range(0, mw, bw):
                for y in range(0, mh, bh):
                    self.map_surface.blit(bg, (x, y))
        else:
            # Fallback couleur
            self.map_surface.fill((50, 50, 50))
            print("[INFO] Aucun background trouvé, couleur grise appliquée")

        # Dessiner les objets
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
            rect = sprite.get_rect()
            rect.topleft = points[0]
            self.map_surface.blit(sprite, rect)
        else:
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
